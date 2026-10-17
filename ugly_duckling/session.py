"""One run of the band: from Start to Stop.

    s = Session(cfg, tune, input, settings, voicing, words)
    s.start()      # asks the other apps to let go, opens the device both ways, starts listening
    s.status()     # the beat, the bar, the chord, the parts
    s.stop()       # the band stops; what rings rings out; a short fade; the device let go

What happens in between (in a thread of its own; the device and the band's sound in the engine's process,
`ambient/bandengine.py`, `ugly_duckling/duplex.py`):

1. **The clock.** The device's two sample counts differ by `L` (`duplex.py`); a cue meant for stream time t (the
   capture's frame t * rate) is played at engine frame `t * rate - L - converters`, so it is heard in the room
   when the player's sound at t is (`ambient/bandplayer.py`, `StreamClock`). `L` starts as the driver's estimate.
2. **The count-in** ("band clicks a bar", the default): a bar of clicks (two bars in 2/4), scheduled on the
   engine's clock 0.6 s ahead. The first click is found in the device's return of its own playback (its loopback
   channels) to the sample, which measures `L`. Then the band (`transcribe.liveband.LiveBand`) is made with the
   clicks' times in the stream as its `count_in`, given every frame captured so far, and the chart from its
   first beat after the clicks.
   **"I count it in"** (`transcribe.voicecount.VoiceBand`, with Vosk's words): the band starts on a spoken
   count, stops on "stop", and starts again on the next count.
3. **Listening.** The capture is read from the ring in `in_block` frames and pushed to the band; each part's
   play (`band.Cue`) goes to the band player as it comes, unless that part is off. With voice on, "stop" stops
   the band (a click start: the whole run).
4. **Stop** (the page, a peer's `/api/yield`, an error, the voice, or `idle_minutes` with nothing played): the
   band decides nothing more; no note starts after now; what is sounding rings out for `RING_S`, then everything
   fades out over `FADE_S`, and the device closes.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ambient import bandplayer, peers
from ambient.bandengine import EngineProcess, EngineSpec

from . import duplex
from .config import Config, Input
from .tunes import Tune, chord_name

RATE = 48000
RING_S = 20.0  # seconds of capture the ring holds
LEAD_IN_S = 0.6  # the first click this long after the band is ready
RING_OUT_S = 0.6  # on stop, what sounds rings this long ...
FADE_S = 0.2  # ... then fades out over this long
PARTS = ("bass", "chop", "comp")
PART_NAMES = {"bass": "Bass", "chop": "Chop", "comp": "Chords"}


class Busy(Exception):
    """The band cannot start: a recording runs, or the device is held."""


@dataclass
class Settings:
    tune: str
    bpm: float
    input: str
    instrument: str = "guitar"
    parts: dict = field(default_factory=lambda: {p: True for p in PARTS})
    volume_db: float = 0.0
    count: str = "band"  # "band": the band clicks a bar; "voice": the player counts it in
    listen_stop: bool = True  # with words: "stop" stops the band


def set_controls(card: str, controls: list[dict]) -> list[str]:
    """The device's controls the config names (amixer); a line for each that could not be set."""
    out = []
    for c in controls:
        r = subprocess.run(["amixer", "-c", card, "-q", "cset", f"name={c['name']}", str(c["set"])],
                           capture_output=True, text=True)
        if r.returncode:
            out.append(f"{c['name']}: {r.stderr.strip() or r.returncode}")
    return out


def engine_spec(cfg: Config, inp: Input | None, voicing, ring: duplex.Ring, audio: str | None = None,
                file_channel: int | None = None) -> EngineSpec:
    """The band engine on the config's device, both ways (`duplex.py`)."""
    d = cfg.device
    period = max(1, int(round(d.period_ms * RATE / 1000)))
    buffer = max(period, int(round(d.buffer_ms * RATE / 1000)))
    if d.kind == "alsa":
        factory = ("ugly_duckling.duplex:make_alsa_duplex", dict(
            ring=ring.name, ring_frames=ring.frames, playback=d.playback, capture=d.capture, rate=RATE,
            period=period, periods=max(2, int(round(buffer / period))), channels=d.channels,
            inputs=list(inp.channels) if inp else [], loopback=list(d.loopback)))
    elif d.kind == "file":
        factory = ("ugly_duckling.duplex:make_file_duplex", dict(
            ring=ring.name, ring_frames=ring.frames, rate=RATE, buffer=buffer, audio=audio, channel=file_channel,
            latency=d.file_latency))
    else:
        raise ValueError(f"no device kind {d.kind!r}: alsa or file")
    fonts = tuple(cfg.sounds_dir / f for f in voicing.FONTS)
    missing = [str(f) for f in fonts if not f.is_file()]
    if missing:
        raise Busy(f"the band's sounds are missing: {', '.join(missing)}")
    return EngineSpec(fonts, bandplayer.voices(voicing), "duplex", "", d.buffer_ms, d.period_ms, None, d.block, RATE,
                      0.0, cfg.rt_priority, False, factory, cfg.max_volume_db, cfg.ceiling_db, 2000)


def db(x: float) -> float | None:
    return None if x <= 0 else round(20 * np.log10(x), 1)


class Session:
    def __init__(self, cfg: Config, tune: Tune, inp: Input, settings: Settings, voicing, words_model=None,
                 on_end=None):
        self.cfg, self.tune, self.inp, self.s = cfg, tune, inp, settings
        self.voicing = voicing
        self.words_model = words_model  # a Vosk Model, or None (no voice)
        self.on_end = on_end
        self.state = "starting"
        self.message = ""
        self.error: str | None = None
        self.started = time.time()
        self.ended: float | None = None
        self._stop = threading.Event()
        self._stop_reason = ""
        self.thread: threading.Thread | None = None
        self.ring: duplex.Ring | None = None
        self.engine: EngineProcess | None = None
        self.player: bandplayer.BandPlayer | None = None
        self.band = None  # the LiveBand (click start) or VoiceBand (voice)
        self.words = None
        self.read = 0  # capture frames read from the ring
        self.L: float | None = None  # capture frame of the loopback of engine frame 0
        self.L_est_ref: float | None = None
        self.L_measured: float | None = None
        self.L_shifts: list[float] = []
        self.clicks: list[int] = []  # the count-in's engine frames
        self.count_in: list[float] = []  # their times in the stream (s)
        self.count = None  # the voice's CountIn
        self.last_cue: dict[str, object] = {}
        self.last_sounded = time.monotonic()
        self.compute: deque = deque(maxlen=2000)  # the listening's compute per block (s)
        self.cpu0 = (time.process_time(), time.monotonic())
        self.cpu_listen = 0.0  # this thread's CPU (s)
        self.level = deque(maxlen=50)  # the input's peak per block
        self.pre: list[np.ndarray] = []  # the input before the band was made
        self.final: dict = {}  # what the engine kept, once stopped
        self.conv = int(round(cfg.device.converter_ms * RATE / 1000))

    # ------------------------------------------------------------------------------------------- outside

    def start(self) -> None:
        """Ask the other apps to let go, open the device, start the listening. Raises Busy."""
        cfg = self.cfg
        try:
            peers.claim(cfg.peers)
        except peers.PeerBusy as e:
            raise Busy(str(e))
        if cfg.device.kind == "alsa" and cfg.device.controls:
            bad = set_controls(cfg.device.card, cfg.device.controls)
            if bad:
                self.message = "Could not set: " + "; ".join(bad)
        audio, ch = None, None
        if cfg.device.kind == "file":
            audio, ch = self._file_take()
        self.ring = duplex.Ring(int(RING_S * RATE), 2)
        try:
            spec = engine_spec(cfg, self.inp, self.voicing, self.ring, audio, ch)
            self.engine = EngineProcess(spec)
            self.engine.start()
        except Exception as e:
            self.ring.close()
            self.ring = None
            self.state = "error"
            raise Busy(f"the device would not open: {e}")
        self.engine.set_volume(self.s.volume_db)
        self.thread = threading.Thread(target=self._run, daemon=True, name="band-session")
        self.thread.start()

    def stop(self, reason: str = "stopped", wait: bool = True) -> None:
        if not self._stop_reason:
            self._stop_reason = reason
        self._stop.set()
        if wait and self.thread is not None and threading.current_thread() is not self.thread:
            self.thread.join(timeout=10)

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def set_volume(self, db_: float) -> None:
        self.s.volume_db = float(np.clip(db_, self.cfg.min_volume_db, self.cfg.max_volume_db))
        if self.engine is not None and self.running:
            self.engine.set_volume(self.s.volume_db)

    def set_parts(self, parts: dict) -> None:
        for p, on in parts.items():
            if p in PARTS:
                self.s.parts[p] = bool(on)

    # ------------------------------------------------------------------------------------------- the run

    def _file_take(self) -> tuple[str, int | None]:
        d = self.cfg.device
        if d.file_path:
            self._file_bar1 = d.file_bar1_s
            return str(Path(d.file_path).expanduser()), d.file_channel
        take = next((t for t in self.tune.takes if t.file == d.file_take), None)
        if take is None:
            raise Busy(f"no take {d.file_take!r} in {self.tune.folder}")
        self._file_bar1 = take.bar1_s
        return str(self.tune.folder / take.file), d.file_channel

    def _run(self) -> None:
        try:
            h = self.ring.header
            if not duplex.wait_for(lambda: h[duplex.H_N_EST] >= 32 or not self.engine.running, 3.0):
                raise RuntimeError("the device's clock was not seen (no estimate of its round trip)")
            if not self.engine.running:
                raise RuntimeError(self.engine.error or "the band engine stopped")
            self.L = self.L_est_ref = float(h[duplex.H_L])
            clock = bandplayer.StreamClock(self._offset())
            self.player = bandplayer.BandPlayer(self.engine, clock, 60.0 / self.s.bpm, self.voicing)
            self.player.log = deque(maxlen=2000)
            if self.words_model is not None and (self.s.count == "voice" or self.s.listen_stop):
                from transcribe.voicecount import CountWords
                self.words = CountWords(self.words_model, RATE)
            if self.s.count == "voice":
                self._voice_band()
            else:
                self._schedule_clicks()
            self._listen()
        except Exception as e:  # noqa: BLE001 (said on the page)
            self.error = f"{type(e).__name__}: {e}"
            self._stop_reason = self._stop_reason or "error"
        finally:
            self._shutdown()

    def _offset(self) -> float:
        return -(self.L + self.conv) / RATE

    def _schedule_clicks(self) -> None:
        bpb, spb = self.tune.beats_per_bar, 60.0 / self.s.bpm
        n = bpb if bpb >= 3 else 2 * bpb
        e0 = int(self.engine.value("committed")) + int(LEAD_IN_S * RATE)
        self.clicks = [e0 + int(round(k * spb * RATE)) for k in range(n)]
        amp = 10 ** (self.cfg.click_db / 20)
        for k, f in enumerate(self.clicks):
            self.engine.click(f, k % bpb == 0, amp)
        if self.cfg.device.kind == "file":  # the take's bar 1 on the beat after the clicks
            down = self.clicks[0] + n * spb * RATE + self.L + self.conv
            self.ring.header[duplex.H_FILE_START] = int(round(down - self._file_bar1 * RATE))
        self.state = "counting in"

    def _voice_band(self) -> None:
        from transcribe.voicecount import VoiceBand, VoiceCountParams
        if self.words is None:
            raise RuntimeError("counting in by voice needs the word recognizer (Vosk), which is not installed here")
        p = VoiceCountParams(beats_per_bar=self.tune.beats_per_bar, lead_s=self.cfg.lead_s)
        self.band = VoiceBand(RATE, words=self.words, params=p, chart=self.tune.chart, start=0,
                              instrument=self.s.instrument, lead_s=self.cfg.lead_s)
        self.words = None  # the VoiceBand pushes its own words
        self.state = "listening for your count"
        if self.cfg.device.kind == "file":
            self.ring.header[duplex.H_FILE_START] = self.read + int(0.5 * RATE)

    def _measure_clicks(self, upto: int) -> bool:
        """Once the first click's return is in the ring, `L` from it, and the band made. False until then."""
        f0 = self.clicks[0]
        a = int(f0 + self.L) - int(0.02 * RATE)
        b = int(f0 + self.L) + int(0.08 * RATE)
        if upto < b:
            return False
        x = np.abs(self.ring.read(max(a, upto - self.ring.frames + 1), b)[:, 1])
        peak = float(x.max()) if len(x) else 0.0
        if peak > 1e-5:
            onset = int(np.argmax(x >= 0.5 * peak))
            self.L_measured = float(max(a, upto - self.ring.frames + 1) + onset - f0)
            self.L = self.L_measured
            self.L_est_ref = float(self.ring.header[duplex.H_L])
            self.player.clock.offset = self._offset()
        else:
            self.message = "The band's click did not come back on the device's loopback: timing from its estimate"
        self.count_in = [(f + self.L + self.conv) / RATE for f in self.clicks]
        spb = 60.0 / self.s.bpm
        from transcribe.liveband import LiveBand
        self.band = LiveBand(RATE, self.s.bpm, self.tune.chart, self.tune.beats_per_bar, count_in=self.count_in,
                             start=0, instrument=self.s.instrument, lead_s=self.cfg.lead_s,
                             play_from=self.count_in[-1] + 0.5 * spb)
        pre = np.concatenate(self.pre) if self.pre else np.zeros(0, dtype=np.float32)
        self.pre = []
        self._cues(self.band.push(pre))
        self.state = "playing"
        return True

    def _listen(self) -> None:
        ring, h, blk = self.ring, self.ring.header, self.cfg.in_block
        idle = self.cfg.idle_minutes * 60
        while not self._stop.is_set():
            if not self.engine.running:
                raise RuntimeError(self.engine.error or "the band engine stopped (the device went away?)")
            w = ring.written
            if w - self.read > ring.frames - RATE:
                raise RuntimeError("the listening fell behind the capture")
            if w - self.read < blk:
                time.sleep(blk / RATE / 2)
                continue
            self._follow_clock(h)
            n = (w - self.read) // blk * blk
            x = ring.read(self.read, self.read + n)
            for k in range(0, n, blk):
                c0, t0 = time.perf_counter(), time.thread_time()
                self._block(x[k: k + blk, 0])
                self.read += blk
                self.compute.append(time.perf_counter() - c0)
                self.cpu_listen += time.thread_time() - t0
                if self._stop.is_set():
                    break
            if self.band is None and self.clicks and self.s.count == "band":
                self._measure_clicks(self.read)
            if time.monotonic() - self.last_sounded > idle:
                self.stop(f"nothing played for {self.cfg.idle_minutes:g} minutes", wait=False)

    def _follow_clock(self, h) -> None:
        """An xrun moves the two counts against each other: the estimate jumps, and L with it."""
        est = float(h[duplex.H_L])
        if self.L_est_ref is not None and abs(est - self.L_est_ref) > 0.002 * RATE:
            d = est - self.L_est_ref
            self.L += d
            self.L_est_ref = est
            self.L_shifts.append(d)
            self.player.clock.offset = self._offset()

    def _block(self, x: np.ndarray) -> None:
        self.level.append(float(np.abs(x).max()) if len(x) else 0.0)
        if self.band is None:
            self.pre.append(x.copy())
            return
        out = self.band.push(x)
        if self.s.count == "voice":
            self._voice_events(out)
        else:
            self._cues(out)
            if self.words is not None:
                for st in self.words.push(x):
                    self.message = "You said stop"
                    self.stop("you said stop", wait=False)
                    break

    def _voice_events(self, events) -> None:
        from transcribe.band import Cue
        from transcribe.voicecount import CountIn, Stop
        for e in events:
            if isinstance(e, CountIn):
                self.count = e
                self.player.spb = 60.0 / e.bpm
                self.state = "playing"
                self.message = f"Counted in at {e.bpm:.0f} bpm" + (" (again)" if e.revision else "")
            elif isinstance(e, Stop):
                self.engine.cut(int(e.decided_at * RATE - self.L - self.conv))
                self.state = "listening for your count"
                self.message = "You said stop: count it in again, or press Stop"
                self.last_cue = {}
            elif isinstance(e, Cue):
                self._cues([e])

    def _cues(self, cues) -> None:
        for c in cues:
            self.last_cue[c.part] = c
            if self.s.parts.get(c.part, False) and c.part in PARTS:
                self.player.cue(c)
                self.last_sounded = time.monotonic()

    def _shutdown(self) -> None:
        self.state = "stopping"
        try:
            if self.band is not None and hasattr(self.band, "stop"):
                self.band.stop()
            if self.engine is not None and self.engine.running:
                self.engine.cut(int(self.engine.value("committed")))
                if self._stop_reason != "error":
                    time.sleep(RING_OUT_S)
                self.engine.fade(int(FADE_S * RATE))
                time.sleep(FADE_S + 0.05)
        except Exception:  # noqa: BLE001 (the device is let go below whatever happened)
            pass
        if self.engine is not None:
            self.engine.stop()
            if getattr(self.engine, "error", None) and not self.error:
                self.error = self.engine.error
            self.final = {k: getattr(self.engine, k, None) for k in ("counts", "granted", "underruns", "limited",
                                                                     "cpu_s", "click_log")}
        if self.ring is not None:
            self.ring.close()
            self.ring = None
        self.ended = time.time()
        self.state = "error" if self.error else "stopped"
        if not self.message and self._stop_reason:
            self.message = self._stop_reason[0].upper() + self._stop_reason[1:]
        if self.on_end:
            try:
                self.on_end(self)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------------------------------- what to show

    def _live_band(self):
        """The LiveBand now playing, and its stream origin (s)."""
        b = self.band
        if b is None:
            return None, 0.0
        if hasattr(b, "bands"):  # a VoiceBand
            return b.band, b.origin / RATE
        return b, 0.0

    def status(self) -> dict:
        now = self.read / RATE
        out = {"state": self.state, "message": self.message, "error": self.error, "tune": self.tune.name,
               "tune_id": self.tune.id, "bpm": round(self.s.bpm), "beats_per_bar": self.tune.beats_per_bar,
               "settings": asdict(self.s), "input": self.inp.name if self.inp else None,
               "seconds": round(now, 1)}
        band, origin = self._live_band()
        beat = None
        if band is not None:
            logs = band.logs
            i = len(logs) - 1
            while i >= 0 and logs[i].t + origin > now:
                i -= 1
            if i >= 0:
                lg = logs[i]
                chord = next((p.chord for k in ("comp", "bass", "chop") if (p := lg.plays.get(k)) is not None), None)
                beat = {"i": lg.i, "bar_beat": lg.bar, "chord": chord_name(chord or lg.predicted),
                        "predicted": chord_name(lg.predicted), "sure": round(lg.pred_conf, 2),
                        "key": chord_name(lg.key), "bpm": round(band.beats[min(lg.i, len(band.beats) - 1)].bpm)
                        if band.beats else None}
        out["beat"] = beat
        parts = {}
        for p in PARTS:
            c = self.last_cue.get(p)
            playing = bool(c is not None and beat is not None and c.i >= beat["i"] - 1)
            parts[p] = {"name": PART_NAMES[p], "on": bool(self.s.parts.get(p)), "playing": playing}
        out["parts"] = parts
        lv = max(self.level) if self.level else 0.0
        out["input_db"] = db(lv)
        if self.count is not None:
            out["count"] = {"bpm": round(self.count.bpm, 1), "beats_per_bar": self.count.beats_per_bar}
        out["timing"] = self.timing()
        return out

    def timing(self) -> dict:
        """The clock, the margins, the CPU: for the page's details and the logs."""
        comp = np.asarray(self.compute) if self.compute else np.zeros(1)
        wall = max(1e-6, time.monotonic() - self.cpu0[1])
        out = {"L_ms": None if self.L is None else round(1000 * self.L / RATE, 2),
               "L_measured": self.L_measured is not None, "L_shifts": len(self.L_shifts),
               "converter_ms": self.cfg.device.converter_ms,
               "listen_ms_per_s": round(1000 * self.cpu_listen / wall, 1),
               "block_ms_median": round(1000 * float(np.median(comp)), 2),
               "block_ms_worst": round(1000 * float(comp.max()), 2)}
        if self.player is not None and self.player.log:
            m = np.array([c.margin for c in self.player.log])
            out["margin_ms"] = {"min": round(1000 * float(m.min()), 1), "median": round(1000 * float(np.median(m)), 1),
                                "n": len(m)}
        e = self.engine
        if e is not None and e.proc is not None:
            out.update({"engine_ms_per_s": round(1000 * e.value("cpu_s") / wall, 1),
                        "underruns": int(e.value("underruns")), "late": int(e.value("late")),
                        "dropped": int(e.value("dropped")), "limited": int(e.value("limited"))})
        if self.ring is not None:
            h = self.ring.header
            out.update({"L_estimate_ms": None if np.isnan(h[duplex.H_L]) else round(1000 * h[duplex.H_L] / RATE, 2),
                        "L_spread_ms": None if np.isnan(h[duplex.H_L_SPREAD]) else round(1000 * h[duplex.H_L_SPREAD] / RATE, 2),
                        "capture_overruns": int(h[duplex.H_OVERRUNS]),
                        "period": int(h[duplex.H_PLAY_PERIOD]), "buffer": int(h[duplex.H_PLAY_BUFFER]),
                        "capture_period": int(h[duplex.H_CAP_PERIOD]), "capture_buffer": int(h[duplex.H_CAP_BUFFER])})
        elif self.final:
            out["final"] = {k: v for k, v in self.final.items() if k != "click_log"}
        return out


# ------------------------------------------------------------------------------------------------- self-check

def selfcheck(cfg: Config, voicing, inp: Input | None = None, seconds: float = 2.0) -> dict:
    """The device opened both ways, run `seconds` with nothing played (no note, no click: the band engine's
    silence), and closed: what it granted, the clock's estimate, xruns, the input's level, and the loopback's
    (which should be silence, so nothing was played). Asks the other apps to let go first (Busy if one is
    recording)."""
    try:
        peers.claim(cfg.peers)
    except peers.PeerBusy as e:
        raise Busy(str(e))
    ring = duplex.Ring(int(RING_S * RATE), 2)
    audio = "" if cfg.device.kind == "file" else None  # no device: the take's place is silence
    engine = None
    t_open = time.monotonic()
    report: dict = {"device": cfg.device.kind, "ok": False}
    try:
        spec = engine_spec(cfg, inp, voicing, ring, audio)
        engine = EngineProcess(spec)
        engine.start()
        report["open_s"] = round(time.monotonic() - t_open, 2)
        h = ring.header
        duplex.wait_for(lambda: h[duplex.H_N_EST] >= 32 or not engine.running, 3.0)
        time.sleep(seconds)
        w = ring.written
        x = ring.read(max(0, w - int(seconds * RATE)), w)
        report.update({
            "running": engine.running, "captured_s": round(w / RATE, 3),
            "L_ms": None if np.isnan(h[duplex.H_L]) else round(1000 * h[duplex.H_L] / RATE, 3),
            "L_spread_ms": None if np.isnan(h[duplex.H_L_SPREAD]) else round(1000 * h[duplex.H_L_SPREAD] / RATE, 3),
            "capture_overruns": int(h[duplex.H_OVERRUNS]),
            "period": int(h[duplex.H_PLAY_PERIOD]), "buffer": int(h[duplex.H_PLAY_BUFFER]),
            "capture_period": int(h[duplex.H_CAP_PERIOD]), "capture_buffer": int(h[duplex.H_CAP_BUFFER]),
            "input_peak_db": db(float(np.abs(x[:, 0]).max())) if len(x) else None,
            "input_rms_db": db(float(np.sqrt(np.mean(x[:, 0] ** 2)))) if len(x) else None,
            "loopback_peak": float(np.abs(x[:, 1]).max()) if len(x) else None,
            "engine_ms_per_s": round(1000 * engine.value("cpu_s") / max(1e-6, w / RATE), 1),
        })
    except Exception as e:  # noqa: BLE001
        report["error"] = f"{type(e).__name__}: {e}"
    finally:
        if engine is not None:
            engine.stop()
            report["underruns"] = getattr(engine, "underruns", None)
            report["granted"] = getattr(engine, "granted", None)
            if getattr(engine, "error", None):
                report["error"] = report.get("error") or engine.error
        ring.close()
    report["closed"] = True
    report["ok"] = bool(report.get("running")) and "error" not in report and report.get("captured_s", 0) > 0 \
        and report.get("loopback_peak") == 0.0 and not report.get("underruns") and not report.get("capture_overruns")
    report["seconds"] = round(time.monotonic() - t_open, 2)
    return report


def pid_cpu(pid: int) -> float:
    """A process's CPU time so far (s), from /proc."""
    try:
        f = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, IndexError, ValueError):
        return 0.0
