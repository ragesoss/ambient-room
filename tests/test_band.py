"""The band player: cues to notes on the engine's clock, the engine's timing and lateness, the outputs, the band's
profile in the config."""

import importlib.util
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ambient.bandengine import BandEngine, Voice
from ambient.bandplayer import LATE_S, BandPlayer, StreamClock
from ambient.config import load_config
from ambient.output import AlsaOutput, OutputError, PacedOutput, make_output

REPO = Path(__file__).resolve().parent.parent
FONTS = [REPO / "sounds" / "generaluser.sf2", REPO / "sounds" / "upright.sf2"]
VOICES = {"bass": Voice(0, 32, 0.0, 0.0), "comp": Voice(1, 25, -0.35, -8.3), "chop": Voice(2, 105, 0.35, -9.5)}
RATE = 48000


def fluidsynth_here() -> bool:
    try:
        from ambient.fluid import library
        library()
    except Exception:
        return False
    return all(f.is_file() for f in FONTS)


class Voicing:
    """Stands in for transcribe.bandvoice: a bass note, or a two-note strum 12 ms apart."""

    @staticmethod
    def play_notes(part, play, at, spb, bar):
        if part == "bass":
            return [(at, 0.9 * spb, 0, 31, 96)]
        return [(at, 0.45 * spb, 1, 55, 96 if bar in (2, 4) else 76), (at + 0.012, 0.45 * spb, 1, 59, 76)]


class Engine:
    """Stands in for the band engine: records what it is given."""
    rate = RATE
    committed = 4800

    def __init__(self):
        self.groups = []

    def started_at(self):
        return 100.0

    def play(self, group, late_s, tag=None):
        self.groups.append((group, late_s, tag))


def cue(part, t, i=0, bar=1):
    return SimpleNamespace(i=i, part=part, play=SimpleNamespace(), t=t, beat_t=t, decided_at=t - 0.05, bar=bar)


def test_a_cue_becomes_one_group_of_notes_at_the_engines_time():
    # a replay: the stream's sample 0 at wall 102.0 s, the engine's frame 0 heard at 100.0 s
    clock = StreamClock.replay(102.0, 100.0)
    assert clock.engine_time(1.0) == pytest.approx(3.0) and clock.stream_time(3.0) == pytest.approx(1.0)
    eng = Engine()
    player = BandPlayer(eng, clock, 0.5, Voicing())
    player.cue(cue("comp", 1.0, i=7, bar=2))
    (group, late_s, tag), = eng.groups
    assert [round(g[0], 3) for g in group] == [3.0, 3.012]  # the strum kept
    assert [g[2:] for g in group] == [("comp", 55, 96), ("comp", 59, 76)] and late_s == LATE_S["comp"] and tag == (7, "comp")
    assert group[0][1] == pytest.approx(0.225)  # the length from the tune's beat, as offline
    # the margin: its first note's engine time less the first frame still open (0.1 s)
    assert player.log[0].margin == pytest.approx(2.9)


def test_late_groups_sound_together_shifted_or_are_dropped():
    eng = BandEngine(FONTS, VOICES, PacedOutput(RATE, 384, realtime=False))
    eng.pos = RATE  # 1 s computed
    strum = lambda t: [(t, 0.2, "comp", 55, 96), (t + 0.012, 0.2, "comp", 59, 96)]  # noqa: E731
    eng.q.put((strum(1.5), 0.03, "on time", 0.0, 0))
    eng.q.put((strum(0.99), 0.03, "late", 0.0, 0))  # 10 ms late: allowed 30
    eng.q.put(([(0.95, 0.4, "bass", 31, 96)], 0.03, "too late", 0.0, 0))  # 50 ms late
    eng._drain()
    assert eng.counts["comp"] == {"on time": 1, "late": 1, "dropped": 0}
    assert eng.counts["bass"] == {"on time": 0, "late": 0, "dropped": 1}
    ons = sorted(e[0] for e in eng.events if e[1] == 1)
    assert ons == [RATE, RATE + 576, 72000, 72576]  # the late strum starts now, its second note 12 ms after
    assert eng.late_s["comp"] == [pytest.approx(0.01)]
    dropped = [lg for lg in eng.log if lg.tag == "too late"]
    assert len(dropped) == 1 and dropped[0].start is None


@pytest.mark.skipif(not fluidsynth_here(), reason="no FluidSynth library or SoundFonts")
def test_notes_start_on_the_nearest_64_frame_boundary_and_each_part_sounds_as_if_alone(tmp_path):
    from ambient.fluid import STEP, Synth
    cap = tmp_path / "out.wav"
    eng = BandEngine(FONTS, VOICES, PacedOutput(RATE, 384, cap, realtime=False), 128, keep_stems=True)
    t = 0.2
    for k in range(6):
        eng.play([(t, 0.45, "bass", 31 + 2 * (k % 2), 96)], 0.03, k)
        eng.play([(t + 0.012 * j, 0.22, "comp", m, 76) for j, m in enumerate((43, 55, 59, 62))], 0.03, k)
        eng.play([(t + 0.25 + 0.004 * j, 0.09, "chop", m, 96) for j, m in enumerate((62, 67, 71))], 0.015, k)
        t += 0.5
    eng.start()
    while eng.pos < (t + 1.0) * RATE and eng.running:
        time.sleep(0.01)
    eng.stop()
    assert eng.error is None
    assert all(lg.start is not None and abs(lg.start - lg.want) <= STEP // 2 and lg.start % STEP == 0 for lg in eng.log)
    stems = {p: np.concatenate(v) for p, v in eng.stems.items()}
    n = min(len(v) for v in stems.values()) // STEP * STEP
    for part, v in VOICES.items():  # each part rendered alone from the log: the same to the bit
        ev = sorted([(lg.start, 1, lg.key, lg.vel) for lg in eng.log if lg.part == part]
                    + [(lg.stop, 0, lg.key, 0) for lg in eng.log if lg.part == part])
        s = Synth(FONTS, RATE)
        s.program(v.channel, v.program)
        x, j = np.zeros((n, 2), dtype=np.float32), 0
        for f in range(0, n, STEP):
            while j < len(ev) and ev[j][0] <= f:
                s.noteon(v.channel, ev[j][2], ev[j][3]) if ev[j][1] else s.noteoff(v.channel, ev[j][2])
                j += 1
            s.render(STEP, x[f:f + STEP])
        s.close()
        assert np.array_equal(x.mean(axis=1), stems[part][:n]), part
    with wave.open(str(cap), "rb") as w:  # the output got the parts mixed with their gains and pans
        got = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2) / 32767.0
    mixed = np.zeros((n, 2))
    for part, v in VOICES.items():
        g = 10 ** (v.gain_db / 20)
        mixed[:, 0] += g * np.sqrt(1 - v.pan) * stems[part][:n]
        mixed[:, 1] += g * np.sqrt(1 + v.pan) * stems[part][:n]
    assert np.abs(got[:n] - mixed).max() < 2 / 32767


def test_the_paced_output_plays_at_a_sound_cards_pace_and_keeps_an_underruns_silence(tmp_path):
    out = PacedOutput(RATE, 480, tmp_path / "c.wav")  # 10 ms
    out.open()
    block = np.zeros((48, 2), dtype=np.float32)
    t0 = time.monotonic()
    for _ in range(60):  # 60 ms of audio: all but the buffer's 10 ms wait for the clock
        assert out.write(block) == 0
    assert 0.040 <= time.monotonic() - t0 < 0.2
    assert 0.0 < out.ahead() <= 0.0105
    time.sleep(0.03)  # the writer stalls: the device runs dry
    gap = out.write(block)
    assert out.underruns == 1 and gap >= int(0.015 * RATE) and out.gaps[0] == (60 * 48, gap)
    out.close()
    with wave.open(str(tmp_path / "c.wav"), "rb") as w:
        assert w.getnframes() == 61 * 48 + gap  # the capture's frame n is the device's frame n


def test_the_band_profile_is_read_from_the_config(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[output]\nengine = "fake"\nblock = 256\n[band]\noutput = "alsa"\ndevice = "hw:X"\nblock = 64\n'
                 'buffer_ms = 4.0\n[band.late_ms]\nchop = 10\n')
    c = load_config(f)
    assert c.block == 256 and c.output == "aplay"
    assert (c.band.output, c.band.device, c.band.block, c.band.buffer_ms) == ("alsa", "hw:X", 64, 4.0)
    assert c.band.late_ms == {"bass": 30.0, "comp": 30.0, "chop": 10.0}
    f.write_text('[band]\nbufer_ms = 4\n')
    with pytest.raises(ValueError):
        load_config(f)


def alsa_null() -> bool:
    try:
        out = AlsaOutput("null", RATE, 128, 3)
        out.open()
        out.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not alsa_null(), reason="no alsa-lib or ALSA null device")
def test_the_alsa_output_asks_for_its_buffer_and_reads_back_what_it_got():
    out = make_output("alsa", "null", RATE, 8.0, 2.0)
    out.open()
    try:
        g = out.granted()
        assert g["asked"] == (96, 384) and g["period"] > 0 and g["buffer"] >= g["period"]
        assert out.write(np.zeros((256, 2), dtype=np.float32)) == 0
    finally:
        out.close()
    with pytest.raises(OutputError):
        make_output("no such kind", "null", RATE, 8.0)


def test_the_offline_renders_onsets_are_where_the_fluidsynth_program_puts_them():
    # measured from the program's renders (2026-10-16): a note at 0.5 s sounds from block 376 (64 frames), one at
    # 0.52960 s from 398, one at 0.53848 s from 406, one at 0 s from 1
    spec = importlib.util.spec_from_file_location("band_replay", REPO / "tools" / "band_replay.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert [m.cli_frame(t) // 64 for t in (0.5, 0.5296, 0.53848, 0.0)] == [376, 398, 406, 1]
