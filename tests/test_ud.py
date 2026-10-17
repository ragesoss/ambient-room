"""The Ugly Duckling String Band: the ring, the tunes, the engine's live controls, the whole loop with no device (a
recorded take as the input), the hand-over and the API."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np
import pytest

from ambient.bandengine import BandEngine, Voice
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
                    "saint-annes-reel": 32, "tennessee-waltz": 32, "g-c-g-d": 16}
    assert tunes["tennessee-waltz"].beats_per_bar == 3 and tunes["g-c-g-d"].beats_per_bar == 2
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
