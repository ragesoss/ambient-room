"""The Ugly Duckling String Band: the ring, the tunes, the engine's live controls, the whole loop with no device (a
recorded take as the input), the hand-over, the API, and the pocket."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np
import pytest

from ambient.bandengine import BandEngine, Voice
from ambient.pocket import note_class
from ambient.output import PacedOutput
from ugly_duckling import duplex
from ugly_duckling.config import load_config

REPO = Path(__file__).resolve().parent.parent
DESKTOP = REPO / "config" / "ud-desktop.toml"
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


@pytest.fixture(autouse=True)
def _keep_out_of_home(tmp_path, monkeypatch):
    """The sessions' recordings and the learnt rooms in the test's own folder, not the desktop's home."""
    import ugly_duckling.config as uc
    real = uc.load_config

    def load(path=None):
        cfg = real(path)
        cfg.record.dir = str(tmp_path / "ud-sessions")
        cfg.echo_state_dir = str(tmp_path / "echo")
        return cfg
    monkeypatch.setattr(uc, "load_config", load)
    monkeypatch.setitem(globals(), "load_config", load)


def transcription_here() -> bool:
    cfg = load_config(DESKTOP)
    return (Path(cfg.transcribe).expanduser() / "transcribe" / "liveband.py").is_file() and \
        Path(cfg.tunes_root).expanduser().is_dir()


needs_band = pytest.mark.skipif(not (fluidsynth_here() and transcription_here()),
                                reason="needs FluidSynth, the fonts and the transcription project")


# ------------------------------------------------------------------------------------------------- the ring

def test_ring_wraps_and_keeps_the_count():
    r = duplex.Ring(100, 2)
    try:
        other = duplex.Ring(100, 2, r.name)  # another process's view: the same memory
        x = np.arange(260, dtype=np.float32).reshape(130, 2)
        r.write(x[:70])
        r.write(x[70:130])
        assert other.written == 130
        assert np.array_equal(other.read(40, 130), x[40:130])
        with pytest.raises(ValueError):
            other.read(10, 50)  # overwritten
        r.write(np.zeros((250, 2), dtype=np.float32))  # more than it holds: the count still counts it all
        assert r.written == 380
        other.close()
    finally:
        r.close()


# ------------------------------------------------------------------------------------------------- the tunes

@pytest.mark.skipif(not transcription_here(), reason="needs the transcription project")
def test_tunes_give_one_pass_of_each_form():
    from ugly_duckling.tunes import load_tunes
    cfg = load_config(DESKTOP)
    tunes, problems = load_tunes(Path(cfg.tunes_root), cfg.tunes, cfg.transcribe)
    assert not problems
    bars = {k: len(t.chart) // t.beats_per_bar for k, t in tunes.items()}
    assert bars == {"red-wing": 16, "down-yonder": 20, "big-sciota": 16, "cherokee-shuffle": 36,
                    "saint-annes-reel": 32, "tennessee-waltz": 32, "g-c-g-d": 16,
                    "everybody-wants-to-go-to-heaven": 18}
    assert tunes["tennessee-waltz"].beats_per_bar == 3 and tunes["g-c-g-d"].beats_per_bar == 2
    assert tunes["everybody-wants-to-go-to-heaven"].beats_per_bar == 2 and tunes["everybody-wants-to-go-to-heaven"].bpm == 85
    assert tunes["red-wing"].bpm == 100 and tunes["down-yonder"].bpm == 120  # its metronome take's
    # Big Sciota's second ending (bar 5 of the file: D D G G) closes the A part's second pass
    assert tunes["big-sciota"].chart[7 * 4: 8 * 4] == [(2, "maj"), (2, "maj"), (7, "maj"), (7, "maj")]
    # Cherokee's B part starts after two A parts
    assert tunes["cherokee-shuffle"].chart[16 * 4] == (2, "maj")


# ------------------------------------------------------------------------------------------------- the engine

def run_engine(eng: BandEngine, blocks: int) -> np.ndarray:
    """The engine's loop, block by block in this thread, into a paced output that keeps no time."""
    out = []
    eng.pairs = max(v.channel for v in eng.voices.values()) + 1
    from ambient.fluid import Synth
    for part, v in eng.voices.items():
        eng.synths[part] = Synth(eng.fonts, eng.rate)
        eng.synths[part].program(v.channel, v.program)
    m = eng.mix_matrix()
    buf = np.zeros((2 * eng.pairs, eng.block), dtype=np.float32)
    for _ in range(blocks):
        eng.committed = eng.pos + eng.block
        eng._control()
        eng._drain()
        for a in range(0, eng.block, 64):
            f = eng.pos + a
            while eng.events and eng.events[0][0] < f + 32:
                import heapq
                eng._apply(heapq.heappop(eng.events), f)
            for part, synth in eng.synths.items():
                ch = eng.voices[part].channel
                synth.render_rows(buf, 2 * ch, 2 * ch + 1, a, a + 64)
        o = buf.T @ m
        eng._finish(o)
        out.append(o.copy())
        eng.pos += eng.block
    for s in eng.synths.values():
        s.close()
    return np.concatenate(out)


@pytest.mark.skipif(not fluidsynth_here(), reason="needs FluidSynth and the fonts")
def test_clicks_land_on_their_frame_and_the_cap_holds():
    eng = BandEngine(FONTS, VOICES, PacedOutput(RATE, 512, realtime=False), 128, RATE, 0.0,
                     max_gain_db=12.0, ceiling_db=-1.0)
    eng.click(1000, True, 0.25)
    eng.click(5003, False, 0.25)
    eng.set_volume(40.0)  # asked far over the cap
    y = run_engine(eng, 400)
    first = int(np.argmax(np.abs(y[:, 0]) > 1e-6))
    assert first == 1000
    assert 0.25 <= y[1000, 0] <= 0.25 * 1.1  # its first sample at its level, the volume gliding up
    assert int(np.argmax(np.abs(y[2500:, 0]) > 1e-6)) + 2500 == 5003
    assert eng.vol <= 10 ** (12 / 20) + 1e-6  # capped at +12 dB
    assert np.abs(y).max() <= 10 ** (-1 / 20) + 1e-6  # and nothing over the ceiling


@pytest.mark.skipif(not fluidsynth_here(), reason="needs FluidSynth and the fonts")
def test_cut_drops_later_notes_and_fade_ends_in_silence():
    eng = BandEngine(FONTS, VOICES, PacedOutput(RATE, 512, realtime=False), 128, RATE, 0.0)
    eng.play([(0.01, 0.3, "bass", 40, 96)], 0.03, tag=(0, "bass"))
    eng.play([(0.5, 0.3, "bass", 43, 96)], 0.03, tag=(1, "bass"))
    eng.cut(int(0.3 * RATE))
    eng.fade(int(0.2 * RATE))
    y = run_engine(eng, int(0.8 * RATE) // 128)
    started = [lg.key for lg in eng.log if lg.start is not None]
    assert started == [40]  # the note after the cut never started
    assert eng.counts["bass"].get("cut") == 1
    assert np.abs(y[int(0.2 * RATE) + 128:]).max() == 0.0  # silent after the fade


# ------------------------------------------------------------------------------------------------- the whole loop

@needs_band
def test_band_follows_a_take_with_no_device():
    """Red Wing streamed in as if captured, the count-in's first click found in the loopback (the round trip known
    exactly), the band on the take: on time, the chart's roots."""
    from ugly_duckling.server import Band
    cfg = load_config(DESKTOP)
    band = Band(cfg)
    band.start({"tune": "red-wing", "count": "band", "listen_stop": False})
    s = band.session
    try:
        assert duplex.wait_for(lambda: s.state == "playing", 6.0, 0.05)
        time.sleep(10.0)
        st = band.status()
        assert st["playing"] and st["beat"] is not None and st["beat"]["chord"]
    finally:
        band.stop()
    assert not s.running and s.state == "stopped" and s.error is None
    assert s.L_measured == cfg.device.file_latency  # the loopback's click, to the frame
    assert s.ring is None and s.engine.proc is None  # the device let go
    counts = s.final["counts"]
    assert sum(c["on time"] for c in counts.values()) >= 16
    assert all(c["late"] == 0 and c["dropped"] == 0 for c in counts.values())
    clicks = [f for f, _ in s.final["click_log"]]
    assert len(clicks) == 4 and np.allclose(np.diff(clicks), 0.6 * RATE, atol=1)
    lb = s.band
    rights = [lg.plays["bass"].chord[0] == s.tune.chart[lg.i % len(s.tune.chart)][0]
              for lg in lb.logs if "bass" in lg.plays]
    assert len(rights) >= 8 and np.mean(rights) >= 0.85
    # the pocket, "pushed" by default: each cue's notes moved by its part's place, and still ahead of the engine (its
    # margin is after the move), so nothing late or dropped (above); the engine asked for each at the moved frame
    assert s.s.pocket == "pushed" and s.pocket.name == "pushed" and s.player.pocket is s.pocket
    cues = list(s.player.log)
    assert all(c.shift_ms == s.pocket.shift_ms(c.cue.part, note_class(c.cue.t, c.cue.beat_t, s.player.spb), c.cue.i)
               for c in cues)
    assert {c.cue.part for c in cues if c.shift_ms < -4} >= {"bass", "chop"} and min(c.margin for c in cues) > 0
    first = {}
    for lg in s.engine.log:
        first[tuple(lg.tag)] = min(first.get(tuple(lg.tag), lg.want), lg.want)
    assert all(first[(c.cue.i, c.cue.part)] == round(c.at * RATE) for c in cues)


@needs_band
def test_selfcheck_opens_and_closes_with_nothing_played():
    from ugly_duckling.server import Band
    band = Band(load_config(DESKTOP))
    r = band.check(None, 0.5)
    assert r["ok"], r
    assert r["loopback_peak"] == 0.0 and r["closed"]


# ------------------------------------------------------------------------------------------------- the hand-over

class _Peer(BaseHTTPRequestHandler):
    busy = False

    def do_POST(self):
        if self.path == "/api/yield" and type(self).busy:
            body = json.dumps({"detail": "Practice is recording"}).encode()
            self.send_response(409)
        else:
            body = b'{"released": true}'
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def peer():
    srv = HTTPServer(("127.0.0.1", 0), _Peer)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


@needs_band
def test_api_refuses_during_a_recording_and_yields_when_asked(peer):
    from fastapi.testclient import TestClient
    from ugly_duckling.server import create_app
    cfg = load_config(DESKTOP)
    cfg.peers = [f"http://127.0.0.1:{peer.server_port}"]
    with TestClient(create_app(cfg)) as c:
        o = c.get("/api/options").json()
        assert {t["id"] for t in o["tunes"]} >= {"red-wing", "tennessee-waltz"}
        assert o["volume"]["max"] == 12.0
        assert c.get("/api/status").json() == {"state": "stopped", "playing": False}
        _Peer.busy = True
        r = c.post("/api/start", json={"tune": "red-wing"})
        assert r.status_code == 409 and "recording" in r.json()["detail"]
        assert c.get("/api/status").json()["playing"] is False
        _Peer.busy = False
        assert c.post("/api/start", json={"tune": "nope"}).status_code == 400
        r = c.post("/api/start", json={"tune": "down-yonder", "bpm": 120, "parts": {"comp": False}, "volume_db": 30})
        assert r.status_code == 200, r.text
        assert r.json()["settings"]["volume_db"] == 12.0  # capped
        assert c.post("/api/start", json={"tune": "red-wing"}).status_code == 409  # one band at a time
        assert c.patch("/api/live", json={"volume_db": -6, "parts": {"chop": False}}).json()["parts"]["chop"]["on"] is False
        y = c.post("/api/yield").json()
        assert y["released"] is True
        st = c.get("/api/status").json()
        assert st["playing"] is False and st["state"] == "stopped"
        assert "another app" in st["message"].lower()
        assert c.post("/api/stop").status_code == 200  # stopping a stopped band is fine


# ------------------------------------------------------------------------------------------------- 2026-10-17

def test_the_count_in_is_two_bars_from_150_bpm_or_as_chosen():
    from ugly_duckling.session import count_in_plan
    cfg = load_config(DESKTOP)
    assert count_in_plan(cfg, 170, 4)["clicks"] == 8 and count_in_plan(cfg, 149, 4)["clicks"] == 4
    assert count_in_plan(cfg, 170, 4, bars="1")["clicks"] == 4 and count_in_plan(cfg, 100, 4, bars="2")["clicks"] == 8
    assert count_in_plan(cfg, 120, 3)["clicks"] == 3 and count_in_plan(cfg, 160, 2)["clicks"] == 8
    assert "2 bars (8 clicks" in count_in_plan(cfg, 170, 4)["text"]
    assert count_in_plan(cfg, 170, 4, count="voice")["kind"] == "voice"


@needs_band
def test_lead_or_follow_is_offered_and_taken_at_start():
    """The page's steps, the default the band as before; a step's id or a number from 0 to 1 taken, anything else
    refused; the setting in the session's settings."""
    from fastapi.testclient import TestClient
    from ugly_duckling.server import create_app
    from ugly_duckling.session import FOLLOW_STEPS
    cfg = load_config(DESKTOP)
    with TestClient(create_app(cfg)) as c:
        o = c.get("/api/options").json()["follow"]
        assert o["default"] == 1.0 and [s["id"] for s in o["steps"]] == ["hold", "gentle", "lead"]
        assert [s["value"] for s in o["steps"]] == [s["value"] for s in FOLLOW_STEPS]
        assert [s["value"] for s in o["steps"]][0] == 0.0 and [s["value"] for s in o["steps"]][-1] == 1.0
        for bad in (1.5, -0.1, "steady", None):
            r = c.post("/api/start", json={"tune": "red-wing", "follow": bad})
            assert r.status_code == 400 and "follow" in r.json()["detail"], bad
        for given, want in ((None, 1.0), ("hold", 0.0), (0.25, 0.25), ("lead", 1.0)):
            body = {"tune": "red-wing", "listen_stop": False} | ({} if given is None else {"follow": given})
            r = c.post("/api/start", json=body)
            assert r.status_code == 200, r.text
            assert r.json()["settings"]["follow"] == want, given
            c.post("/api/stop")


@needs_band
def test_the_beat_params_carry_lead_or_follow_only_when_not_the_default():
    """The follower gets the preset with the band's stop rule, and `follow` only when it is not the default (so an
    older transcription project runs the default)."""
    from dataclasses import replace

    from transcribe.livebeat import PRESETS
    from ugly_duckling.server import Band
    from ugly_duckling.session import Session, Settings
    cfg = load_config(DESKTOP)
    b = Band(cfg)
    tune, inp = b.tunes["red-wing"], b.inputs["take"]
    lead = Session(cfg, tune, inp, Settings("red-wing", 100.0, "take", "dobro"), b.voicing)._beat_params()
    assert lead == replace(PRESETS["dobro"], stop_beats=cfg.stop_beats, noise_gate_db=cfg.noise_gate_db)
    hold = Session(cfg, tune, inp, Settings("red-wing", 100.0, "take", "dobro", follow=0.0), b.voicing)._beat_params()
    assert hold == replace(lead, follow=0.0)


@needs_band
def test_the_steady_clock_and_the_onset_lead_by_default(tmp_path):
    """The steady band clock over half a bar and the onset lead: on in the config unless it says otherwise (the
    player's choice by ear, 2026-10-21: `config.STEADY_BARS`, `ONSET_LEAD`), "off" turning the clock off in a config
    or a start request; a start's own width passed to the follower (the onset lead only where the transcription
    project has measured one: the bass); a width out of range refused."""
    from dataclasses import replace

    from fastapi.testclient import TestClient
    from transcribe.livebeat import ONSET_LEAD_S, PRESETS
    from ugly_duckling.config import ONSET_LEAD, STEADY_BARS, steady_entry
    from ugly_duckling.server import Band, create_app
    from ugly_duckling.session import Session, Settings
    cfg = load_config(DESKTOP)
    assert (STEADY_BARS, ONSET_LEAD) == (0.5, True)
    assert cfg.steady_bars == 0.5 and cfg.onset_lead is True
    for name in ("ud-pi.toml", "ud-desktop.toml"):
        c = load_config(REPO / "config" / name)
        assert c.steady_bars == 0.5 and c.onset_lead is True, name
    off = tmp_path / "off.toml"
    off.write_text(DESKTOP.read_text().replace("[band]\n", '[band]\nsteady_bars = "off"\nonset_lead = false\n', 1))
    assert (load_config(off).steady_bars, load_config(off).onset_lead) == (None, False)
    assert steady_entry("x", None) is None and steady_entry("x", "off") is None and steady_entry("x", 2) == 2.0
    b = Band(cfg)
    tune, inp = b.tunes["red-wing"], b.inputs["take"]
    base = replace(PRESETS["bass"], stop_beats=cfg.stop_beats, noise_gate_db=cfg.noise_gate_db)
    params = lambda **kw: Session(cfg, tune, inp, Settings("red-wing", 100.0, "take", "bass", **kw),
                                  b.voicing)._beat_params()
    assert params() == base
    assert params(steady=2.0) == replace(base, steady_bars=2.0)
    assert params(steady=1.0, follow=0.25, onset_lead=True) == replace(base, steady_bars=1.0, follow=0.25,
                                                                      onset_lead_s=ONSET_LEAD_S["bass"])
    dobro = Session(cfg, tune, inp, Settings("red-wing", 100.0, "take", "dobro", onset_lead=True), b.voicing)
    assert dobro._beat_params() == replace(PRESETS["dobro"], stop_beats=cfg.stop_beats,
                                           noise_gate_db=cfg.noise_gate_db)  # none measured for the dobro
    with TestClient(create_app(cfg)) as c:
        assert c.get("/api/options").json()["steady"] == {"default": 0.5, "onset_lead": True}
        for bad in ({"steady": 0.1}, {"steady": 40}, {"steady": "wide"}, {"onset_lead": "yes"}):
            r = c.post("/api/start", json={"tune": "red-wing", "listen_stop": False} | bad)
            assert r.status_code == 400, bad
        for given, want in (({}, (0.5, True)), ({"steady": 2}, (2.0, True)), ({"steady": "off"}, (None, True)),
                            ({"steady": "off", "onset_lead": False}, (None, False)), ({"onset_lead": False}, (0.5, False)),
                            ({"steady": 1, "onset_lead": True}, (1.0, True))):
            r = c.post("/api/start", json={"tune": "red-wing", "listen_stop": False} | given)
            assert r.status_code == 200, r.text
            st = r.json()["settings"]
            assert (st["steady"], st["onset_lead"]) == want, given
            c.post("/api/stop")


def test_old_sessions_are_pruned_by_count_and_size(tmp_path):
    from ugly_duckling.record import prune
    for k in range(5):
        d = tmp_path / f"2026-10-17_00000{k}"
        d.mkdir()
        (d / "capture.flac").write_bytes(b"x" * 1000)
    assert prune(tmp_path, 3, 1e9) == ["2026-10-17_000000", "2026-10-17_000001"]
    assert prune(tmp_path, 10, 1500) == ["2026-10-17_000002", "2026-10-17_000003"]
    assert [p.name for p in tmp_path.iterdir()] == ["2026-10-17_000004"]


@needs_band
def test_a_session_is_recorded_and_the_band_plays_from_beat_one(tmp_path):
    """Cherokee Shuffle at 170 (two bars of count-in): every part's first note on beat 1 (the chop on its "and"),
    within a millisecond of where its pocket puts it; the capture and the log written, the pocket in it."""
    import json as _json

    import soundfile as sf
    from ugly_duckling.server import Band
    cfg = load_config(DESKTOP)
    cfg.device.file_take = "take-01.flac"
    band = Band(cfg)
    band.start({"tune": "cherokee-shuffle", "count": "band", "listen_stop": False, "instrument": "dobro"})
    s = band.session
    try:
        assert duplex.wait_for(lambda: s.state == "playing", 8.0, 0.05)
        time.sleep(4.0)
    finally:
        band.stop()
    assert s.error is None and len(s.clicks) == 8
    spb = 60.0 / s.s.bpm
    one = s.clicks[0] + 8 * spb * RATE
    for part, off in (("bass", 0.0), ("comp", 0.0), ("chop", 0.5)):
        # where the band put it (a loaded machine may sound a cue late: the engine shifts it, and counts it)
        lg = min((lg for lg in s.engine.log if lg.part == part and lg.start is not None), key=lambda g: g.want)
        shift = s.pocket.shift_ms(part, "and" if off else "beat", lg.tag[0])
        assert lg.tag[0] == 0 and abs(lg.want - (one + (off * spb + shift / 1000) * RATE)) < 0.001 * RATE, part
    d = s.rec.path
    info = sf.info(str(d / "capture.flac"))
    assert info.channels == 5 and info.samplerate == RATE and info.duration > 4
    # channel 4, the band as the beat follower had it: the part of the canceller's estimate it is sure of, never more
    # than all it subtracted (channel 0 less 2); here no band is in the input, so much less
    y, _ = sf.read(str(d / "capture.flac"), dtype="float64")
    sure, full = np.sqrt(np.mean(y[:, 4] ** 2)), np.sqrt(np.mean((y[:, 0] - y[:, 2]) ** 2))
    assert 0 < sure <= full
    log = [_json.loads(x) for x in open(d / "session.jsonl")]
    evs = [e["ev"] for e in log]
    for k in ("start", "count_in", "clock", "beat", "cue", "decision", "level", "stop", "end"):
        assert k in evs, k
    start = next(e for e in log if e["ev"] == "start")
    assert start["settings"]["pocket"] == "pushed" and start["pocket"]["parts"]["bass"]["beat"] == -6.0
    cue = next(e for e in log if e["ev"] == "cue" and e["part"] == "bass")
    assert cue["pocket_ms"] == round(s.pocket.shift_ms("bass", "beat", cue["i"]), 3)


# ------------------------------------------------------------------------------------------------- 2026-10-18

@pytest.mark.skipif(not transcription_here(), reason="needs the transcription project")
def test_any_tune_is_offered_in_the_meters_the_tunes_have():
    from ugly_duckling.server import Band
    band = Band(load_config(DESKTOP))
    o = band.options()
    assert o["any"]["available"] and o["any"]["meters"] == [4, 3]  # the waltz in 3; the 2/4 take in a count of 4
    assert band.plan("any", 100)["clicks"] == 4 and band.plan("any-3", 100)["clicks"] == 3
    assert band.tune_for("any").chart == [] and band.tune_for("red-wing").chart


@needs_band
def test_with_no_tune_chosen_the_band_names_the_tune_and_follows_its_chart():
    """The free guitar take (G C G D, 2/4) with no tune chosen, counted in 4, the default pocket ("pushed"): the band
    plays what it hears, then names the tune (the status shows its title) and plays its chart from the place heard.
    Before the beat follower was given only the part of the echo canceller's estimate the canceller is sure of, the band
    stopped here after about 10 beats in 7 runs of 10 with "pushed" ("You stopped playing": a cold canceller explained
    the guitar's booms by the band's bass just before them, with no band in this input; PLAN.md, "The pocket and the
    echo estimate")."""
    from ugly_duckling.server import Band
    cfg = load_config(DESKTOP)
    cfg.device.file_tune = "g-c-g-d"
    band = Band(cfg)
    band.start({"tune": "any", "bpm": 103, "count": "band", "listen_stop": False, "instrument": "guitar"})
    s = band.session
    try:
        assert duplex.wait_for(lambda: s.state == "playing", 6.0, 0.05)
        assert band.status()["find"]["found"] is None and band.status()["tune"] == "Any of my tunes"
        assert duplex.wait_for(lambda: (band.status().get("find") or {}).get("found") == "g-c-g-d", 40.0, 0.2)
        st = band.status()
        assert st["tune"] == "G C G D (the free guitar take)" and st["find"]["key"] == "G"
        assert st["pocket"]["name"] == "pushed"
        time.sleep(3.0)
    finally:
        band.stop()
    assert s.error is None
    logs = s.band.logs
    first = next(lg.i for lg in logs if lg.tune == "g-c-g-d")
    assert all(lg.tune is None and "comp" not in lg.plays for lg in logs[:first])  # listening: no chords part
    after = [lg for lg in logs[first:] if "comp" in lg.plays]
    assert len(after) >= 4 and all(lg.plays["comp"].chord == lg.predicted for lg in after)


# ------------------------------------------------------------------------------------------------- 2026-10-20

def test_the_pocket_is_read_from_the_config(tmp_path):
    """`[band] pocket`: a preset's name or a table with overrides of it; none given, "pushed" (the unit's config from
    before works as it is); anything else refused when the config is read."""
    f = tmp_path / "ud.toml"
    f.write_text("[band]\n")
    c = load_config(f)
    assert (c.pocket, c.pocket_parts) == ("pushed", {}) and c.pocket_for().offset_ms("bass", "beat") == -6.0
    for name in ("ud-pi.toml", "ud-desktop.toml"):
        assert load_config(REPO / "config" / name).pocket == "pushed"
    f.write_text('[band]\npocket = "even"\n')
    assert load_config(f).pocket_for().offset_ms("bass", "beat") == -8.0
    f.write_text('[band.pocket]\npreset = "pushed"\nseed = 5\nbass = { beat = -5, scatter = 3 }\n')
    c = load_config(f)
    p = c.pocket_for()
    assert (p.offset_ms("bass", "beat"), p.scatter_ms("bass"), p.offset_ms("chop", "and"), p.seed) == (-5, 3, -4, 5)
    assert c.pocket_for("even").offset_ms("bass", "beat") == -8.0  # the overrides are its own preset's
    for bad in ('[band]\npocket = "laid back"', "[band]\npocket = 3", "[band.pocket]\nbanjo = { beat = 5 }",
                "[band.pocket]\nswing = 1.1", "[band.pocket]\nbass = { beat = -30 }"):
        f.write_text(bad + "\n")
        with pytest.raises(ValueError):
            load_config(f)


@needs_band
def test_the_pocket_is_offered_and_taken_at_start():
    """The page's choices (Pushed, Even, None) with their numbers and words, the config's the default; a step's id
    taken at Start, anything else refused; the session's band player in that pocket."""
    from fastapi.testclient import TestClient
    from ugly_duckling.server import Band, create_app
    cfg = load_config(DESKTOP)
    with TestClient(create_app(cfg)) as c:
        o = c.get("/api/options").json()["pocket"]
        assert o["default"] == "pushed" and [s["id"] for s in o["steps"]] == ["pushed", "even", "none"]
        pushed, even, none = o["steps"]
        assert pushed["offset_ms"] == {"bass": {"beat": -6.0, "and": -6.0}, "comp": {"beat": 2.0, "and": -5.0},
                                       "chop": {"beat": -4.0, "and": -4.0}}
        assert pushed["scatter_ms"] == {"bass": 4.0, "comp": 4.0, "chop": 4.0} and none["scatter_ms"]["bass"] == 0.0
        assert "bass 6 ms ahead" in pushed["words"] and "bass 8 ms ahead" in even["words"]
        for bad in ("laid back", 3, ""):
            r = c.post("/api/start", json={"tune": "red-wing", "pocket": bad})
            assert r.status_code == 400 and "pocket" in r.json()["detail"], bad
        for given, want in ((None, "pushed"), ("even", "even"), ("none", "none")):
            body = {"tune": "red-wing", "listen_stop": False} | ({} if given is None else {"pocket": given})
            r = c.post("/api/start", json=body)
            assert r.status_code == 200, r.text
            st = r.json()
            assert st["settings"]["pocket"] == want and st["pocket"]["name"] == want, given
            c.post("/api/stop")
    cfg.pocket, cfg.pocket_parts = "even", {"bass": {"beat": -5}}  # the config's own preset, with an override
    o = Band(cfg).options()["pocket"]
    assert o["default"] == "even" and o["steps"][1]["offset_ms"]["bass"]["beat"] == -5.0
    assert o["steps"][0]["offset_ms"]["bass"]["beat"] == -6.0
