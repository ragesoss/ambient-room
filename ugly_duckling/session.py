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
2. **The count-in** ("the band clicks it in", the default): a bar of clicks, two at or above `two_bar_bpm` (150; a
   reel at 170 is not counted in half time) or as the player chose (`count_bars`), each bar two in 2/4, scheduled on
   the engine's clock 0.6 s ahead; all of them go to the band as its `count_in`. The first click is found in the device's return of its own playback (its loopback
   channels) to the sample, which measures `L`. Then the band (`transcribe.liveband.LiveBand`) is made with the
   clicks' times in the stream as its `count_in`, given every frame captured so far, and the chart from its
   first beat after the clicks.
   **"I count it in"** (`transcribe.voicecount.VoiceBand`, with Vosk's words): the band starts on a spoken
   count, stops on "stop", and starts again on the next count.
3. **Listening.** The capture is read from the ring in `in_block` frames and pushed to the band; each part's
   play (`band.Cue`) goes to the band player as it comes, unless that part is off. With voice on, "stop" stops
   the band (a click start: the whole run). How much the band takes the player's tempo is the player's lead or
   follow (`Settings.follow`, `FOLLOW_STEPS`): from the count's tempo held to the player leading.
   **No tune chosen** ("Any of my tunes", `catalog`): the band starts with no chart and plays what it hears; once
   it is sure which of the tunes is played, it takes that tune's chart at the place heard, and lets it go again if
   it stops fitting (`transcribe.band.TuneFinder`). The status names the tune followed.
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
from .record import Recorder
from .tunes import Tune, chord_name

RATE = 48000
RING_S = 20.0  # seconds of capture the ring holds
LEAD_IN_S = 0.6  # the first click this long after the band is ready
RING_OUT_S = 0.6  # on stop, what sounds rings this long ...
FADE_S = 0.2  # ... then fades out over this long
LEVEL_EVERY_S = 0.5  # the log's levels: every this long
ROOM_EVERY_S = 2.0  # the echo path's delay: every this long
ROOM_PEAK_RATIO = 8.0  # its peak this many times the response's median magnitude ...
ROOM_MIN_REMOVED_DB = 1.0  # ... and this much of the input removed over the last 2 s, or it is marked unreliable
PARTS = ("bass", "chop", "comp")
PART_NAMES = {"bass": "Bass", "chop": "Chop", "comp": "Chords"}
# Lead or follow: how much of the player's tempo the band's clock takes (the transcription project's
# `livebeat.LiveBeatParams.follow`; its `docs/band-that-follows.md`, "Lead or follow"). "lead" is the band as before.
FOLLOW_STEPS = (
    {"id": "hold", "value": 0.0, "name": "The band holds steady", "note": "keeps the tempo it starts at"},
    {"id": "gentle", "value": 0.25, "name": "The band follows gently", "note": "comes along with a change you keep up"},
    {"id": "lead", "value": 1.0, "name": "You lead", "note": "the band follows you, as a band would"},
)
FOLLOW_DEFAULT = 1.0


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
    count: str = "band"  # "band": the band clicks it in (`count_in_plan`); "voice": the player counts it in
    listen_stop: bool = True  # with words: "stop" stops the band
    count_bars: str = "auto"  # the band's count-in: "1", "2" bars, or "auto" (two at or above `two_bar_bpm`)
    follow: float = FOLLOW_DEFAULT  # lead or follow (`FOLLOW_STEPS`): 1 the player leads, 0 the band holds the tempo


def count_in_plan(cfg: Config, bpm: float, beats_per_bar: int, count: str = "band", bars: str = "auto") -> dict:
    """What the count-in will be, for the page before Start and for the clicks: bars, clicks, and a line to show.
    The band's: one bar, or two at or above `cfg.two_bar_bpm` (a reel at 170 is not counted in half time), or as the
    player chose; in 2/4 each bar counted is two bars of the tune. The voice's: the player's, one or two bars."""
    unit = beats_per_bar if beats_per_bar >= 3 else 2 * beats_per_bar
    if count == "voice":
        return {"kind": "voice", "bars": None, "clicks": None,
                "text": f"Count-in: yours, out loud: one bar ({', '.join(str(k + 1) for k in range(beats_per_bar))}), "
                        f"or two (one ... two ... {', '.join(str(k + 1) for k in range(beats_per_bar))})"}
    auto = bars not in ("1", "2", 1, 2)
    n_bars = (2 if bpm >= cfg.two_bar_bpm else 1) if auto else int(bars)
    clicks = n_bars * unit
    why = f"at {bpm:.0f} bpm: two bars from {cfg.two_bar_bpm:.0f} bpm up" if auto else "your choice"
    return {"kind": "band", "bars": n_bars, "clicks": clicks, "auto": auto,
            "text": f"Count-in: {n_bars} bar{'s' if n_bars > 1 else ''} ({clicks} clicks; {why})"}


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
                file_channel: int | None = None, bar1_s: float = 0.0) -> EngineSpec:
    """The band engine on the config's device, both ways (`duplex.py`)."""
    d = cfg.device
    period = max(1, int(round(d.period_ms * RATE / 1000)))
    buffer = max(period, int(round(d.buffer_ms * RATE / 1000)))
    if d.kind == "alsa":
        factory = ("ugly_duckling.duplex:make_alsa_duplex", dict(
            ring=ring.name, ring_frames=ring.frames, playback=d.playback, capture=d.capture, rate=RATE,
            period=period, periods=max(2, int(round(buffer / period))), channels=d.channels,
            inputs=list(inp.channels) if inp else [], loopback=list(d.loopback), room=list(d.room)))
    elif d.kind == "file":
        factory = ("ugly_duckling.duplex:make_file_duplex", dict(
            ring=ring.name, ring_frames=ring.frames, rate=RATE, buffer=buffer, audio=audio, channel=file_channel,
            latency=d.file_latency, room_ir=d.file_room_ir, room_gain_db=d.file_room_gain_db, take_gain=d.file_take_gain,
            take_seconds=d.file_take_seconds, take_bar1_s=bar1_s))
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
                 on_end=None, echo_state: dict | None = None, catalog: list[Tune] | None = None):
        self.cfg, self.tune, self.inp, self.s = cfg, tune, inp, settings
        self.catalog = catalog  # no tune chosen (`tune` the server's stand-in): the tunes the band may find
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
        self.pre_echo: list[np.ndarray] = []  # and the band's own sound estimated in it
        self.final: dict = {}  # what the engine kept, once stopped
        self.conv = int(round(cfg.device.converter_ms * RATE / 1000))
        self.plan = count_in_plan(cfg, settings.bpm, tune.beats_per_bar, settings.count, settings.count_bars)
        self.echo = None  # the band's own sound taken out of the input (`transcribe.echo`)
        self.room_echo = None  # the same on the room mic, for the room's delay, when the band follows another input
        self.echo_state = echo_state  # a canceller's state from an earlier session on this input
        self.rec: Recorder | None = None
        self.lv = {"in": 0.0, "out": 0.0, "loop": 0.0, "n": 0, "in_peak": 0.0, "out_peak": 0.0, "loop_peak": 0.0}
        self.levels: deque = deque(maxlen=20)  # the last levels logged (for the status)
        self.next_level = 0
        self.logged = {"beats": 0, "heard": 0, "band": None}
        self.player_stop_at: float | None = None
        self._ring_lock = threading.Lock()
        self.room: dict | None = None  # the learnt echo path's delay (`_room_delay`)
        self.next_room = int(ROOM_EVERY_S * RATE)

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
        self._start_record()
        self.ring = duplex.Ring(int(RING_S * RATE))
        try:
            spec = engine_spec(cfg, self.inp, self.voicing, self.ring, audio, ch, getattr(self, "_file_bar1", 0.0))
            self.engine = EngineProcess(spec)
            self.engine.start()
        except Exception as e:
            self.ring.close()
            self.ring = None
            self.state = "error"
            if self.rec is not None:
                self.rec.log("stop", reason=f"the device would not open: {e}")
                self.rec.close()
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

    def _start_record(self) -> None:
        self.rec = Recorder(self.cfg.record)
        if not self.rec.on:
            return
        c = self.cfg
        self.rec.log("start", settings=asdict(self.s), tune={"id": self.tune.id, "name": self.tune.name,
                     "beats_per_bar": self.tune.beats_per_bar, "chart": [list(x) for x in self.tune.chart]},
                     input={"id": self.inp.id, "name": self.inp.name, "channels": self.inp.channels,
                            "echo": self.inp.echo} if self.inp else None,
                     catalog=[t.id for t in self.catalog] if self.catalog is not None else None,
                     count_in=self.plan, device=asdict(c.device),
                     band={"lead_s": c.lead_s, "in_block": c.in_block, "echo": c.echo, "echo_taps_s": c.echo_taps_s,
                           "stop_beats": c.stop_beats, "noise_gate_db": c.noise_gate_db,
                           "two_bar_bpm": c.two_bar_bpm, "click_db": c.click_db,
                           "transcribe": c.transcribe, "config": str(c.path)},
                     capture_channels=["input", "loopback", "input less the band", "room mic"], rate=RATE,
                     pruned=getattr(self.rec, "pruned", []))

    def _make_echo(self) -> None:
        from transcribe.echo import EchoCanceller
        if self.cfg.echo and self.inp is not None and self.inp.echo:
            self.echo = EchoCanceller(RATE, taps_s=self.cfg.echo_taps_s, block=self.cfg.in_block)
            if self.echo_state:
                self.echo.load(self.echo_state)
        room = list(self.cfg.device.room)
        if room and not (self.echo is not None and self.inp is not None and list(self.inp.channels) == room):
            # the room mic's echo path, for its delay: 0.1 s of it is enough for the direct sound
            self.room_echo = EchoCanceller(RATE, taps_s=0.1, block=self.cfg.in_block)

    def _file_take(self) -> tuple[str, int | None]:
        d = self.cfg.device
        if d.file_path:
            self._file_bar1 = d.file_bar1_s
            return str(Path(d.file_path).expanduser()), d.file_channel
        tune = self.tune
        if self.catalog is not None:  # no tune chosen: the config's tune plays
            tune = next((t for t in self.catalog if t.id == d.file_tune), None) or (self.catalog or [tune])[0]
        take = next((t for t in tune.takes if t.file == d.file_take), None)
        if take is None:
            raise Busy(f"no take {d.file_take!r} in {tune.folder}")
        self._file_bar1 = take.bar1_s
        return str(tune.folder / take.file), d.file_channel

    def _run(self) -> None:
        try:
            h = self.ring.header
            if not duplex.wait_for(lambda: h[duplex.H_N_EST] >= 32 or not self.engine.running, 3.0):
                raise RuntimeError("the device's clock was not seen (no estimate of its round trip)")
            if not self.engine.running:
                raise RuntimeError(self.engine.error or "the band engine stopped")
            self.L = self.L_est_ref = float(h[duplex.H_L])
            self._make_echo()
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
        n = self.plan["clicks"]
        e0 = int(self.engine.value("committed")) + int(LEAD_IN_S * RATE)
        self.clicks = [e0 + int(round(k * spb * RATE)) for k in range(n)]
        amp = 10 ** (self.cfg.click_db / 20)
        for k, f in enumerate(self.clicks):
            self.engine.click(f, k % bpb == 0, amp)
        if self.cfg.device.kind == "file":  # the take's bar 1 on the beat after the clicks
            down = self.clicks[0] + n * spb * RATE + self.L + self.conv
            self.ring.header[duplex.H_FILE_START] = int(round(down - self._file_bar1 * RATE))
        self.state = "counting in"
        if self.rec:
            self.rec.log("count_in", engine_frames=self.clicks, bars=self.plan["bars"], bpm=self.s.bpm)

    def _voice_band(self) -> None:
        from transcribe.voicecount import VoiceBand, VoiceCountParams
        if self.words is None:
            raise RuntimeError("counting in by voice needs the word recognizer (Vosk), which is not installed here")
        p = VoiceCountParams(beats_per_bar=self.tune.beats_per_bar, lead_s=self.cfg.lead_s)
        self.band = VoiceBand(RATE, words=self.words, params=p, chart=self.tune.chart or None, start=0,
                              instrument=self.s.instrument, lead_s=self.cfg.lead_s, beat_params=self._beat_params(),
                              tunes=self._band_tunes())
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
        self.band = LiveBand(RATE, self.s.bpm, self.tune.chart or None, self.tune.beats_per_bar,
                             count_in=self.count_in, start=0, instrument=self.s.instrument, lead_s=self.cfg.lead_s,
                             play_from=self.count_in[-1] + 0.5 * spb, beat_params=self._beat_params(),
                             tunes=self._band_tunes())
        if self.rec:
            self.rec.log("clock", L_estimate=self.L_est_ref, L_measured=self.L_measured, L=self.L, conv=self.conv,
                         count_in=self.count_in)
        pre = np.concatenate(self.pre) if self.pre else np.zeros(0, dtype=np.float32)
        pre_echo = np.concatenate(self.pre_echo) if self.pre_echo else None
        self.pre, self.pre_echo = [], []
        self._cues(self.band.push(pre, echo=pre_echo))
        self.state = "playing"
        return True

    def _beat_params(self):
        """The beat follower's preset for the instrument, with the band's stop rule (`stop_beats`) and the player's
        lead or follow (`follow`; passed only when it is not the default, so that an older transcription project
        still runs the default)."""
        from dataclasses import replace
        from transcribe.livebeat import PRESETS
        lead = {} if self.s.follow == FOLLOW_DEFAULT else {"follow": self.s.follow}
        return replace(PRESETS[self.s.instrument], stop_beats=self.cfg.stop_beats,
                       noise_gate_db=self.cfg.noise_gate_db, **lead)

    def _band_tunes(self):
        """No tune chosen: the tunes as the band finds them (`transcribe.band.Tune`); else None."""
        if self.catalog is None:
            return None
        from transcribe.band import Tune as BandTune
        return [BandTune(t.id, t.name, tuple(tuple(c) for c in t.chart), t.beats_per_bar) for t in self.catalog]

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
                raw, loop, room = x[k: k + blk, 0], x[k: k + blk, 1], x[k: k + blk, 2]
                heard = raw if self.echo is None else self.echo.filter(raw, loop).astype(np.float32)
                room_out = None if self.room_echo is None else self.room_echo.filter(room, loop)
                self._levels(raw, heard, loop, room, room_out)
                if self.rec:
                    self.rec.audio(np.stack([raw, loop, heard, room], axis=1))
                self._block(heard, None if self.echo is None else (raw - heard))
                self.read += blk
                self.compute.append(time.perf_counter() - c0)
                self.cpu_listen += time.thread_time() - t0
                if self._stop.is_set():
                    break
            if self.band is None and self.clicks and self.s.count == "band":
                self._measure_clicks(self.read)
            self._log_band()
            if self.band is not None and self.s.count == "band" and getattr(self.band, "player_stopped", False):
                self.message = "You stopped playing: the band stopped with you"
                self.stop("you stopped playing", wait=False)
            if time.monotonic() - self.last_sounded > idle:
                self.stop(f"nothing played for {self.cfg.idle_minutes:g} minutes", wait=False)

    def _levels(self, raw, heard, loop, room=None, room_out=None) -> None:
        lv = self.lv
        if room_out is not None:
            lv["room_in"] = lv.get("room_in", 0.0) + float(np.dot(room, room))
            lv["room_out"] = lv.get("room_out", 0.0) + float(np.dot(room_out, room_out))
        for k, v in (("in", raw), ("out", heard), ("loop", loop)):
            lv[k] += float(np.dot(v, v))
            lv[k + "_peak"] = max(lv[k + "_peak"], float(np.abs(v).max()) if len(v) else 0.0)
        lv["n"] += len(raw)
        if self.read + len(raw) >= self.next_level and lv["n"]:
            d = {k: db(np.sqrt(lv[k] / lv["n"])) for k in ("in", "out", "loop")}
            d.update({k + "_peak": db(lv[k + "_peak"]) for k in ("in", "out", "loop")})
            d["removed_db"] = None if not (lv["in"] and lv["out"]) else round(10 * np.log10(lv["in"] / lv["out"]), 1)
            if lv.get("room_in") and lv.get("room_out"):
                d["room_removed_db"] = round(10 * np.log10(lv["room_in"] / lv["room_out"]), 1)
            d["t"] = round(self.read / RATE, 3)
            self.levels.append(d)
            if self.rec:
                self.rec.log("level", **d)
            self.lv = {k: 0.0 for k in ("in", "out", "loop", "in_peak", "out_peak", "loop_peak")}
            self.lv["n"] = 0
            self.next_level = self.read + int(LEVEL_EVERY_S * RATE)
        if (self.echo is not None or self.room_echo is not None) and self.read + len(raw) >= self.next_room:
            self._room_delay()
            self.next_room = self.read + int(ROOM_EVERY_S * RATE)

    def _room_delay(self) -> None:
        """The delay of the echo path the canceller has learnt, from the loopback to the input: its response's main
        peak (the converters out and in, the speakers, the air). Unreliable when the peak hardly stands out of the
        response or the canceller removed little of the input lately (a pickup, the band quiet)."""
        ec, key = (self.room_echo, "room_removed_db") if self.room_echo is not None else (self.echo, "removed_db")
        h = np.abs(ec.response())
        k = int(np.argmax(h))
        med = float(np.median(h)) + 1e-12
        recent = [d[key] for d in list(self.levels)[-4:] if d.get(key) is not None]
        removed = float(np.mean(recent)) if recent else 0.0
        ratio = float(h[k] / med)
        self.room = {"t": round(self.read / RATE, 3), "mic": "room" if self.room_echo is not None or (
                         self.inp is not None and list(self.inp.channels) == list(self.cfg.device.room)) else "input",
                     "delay_ms": round(1000 * k / RATE, 2), "peak_ratio": round(ratio, 1),
                     "removed_db": round(removed, 1),
                     "reliable": bool(ratio >= ROOM_PEAK_RATIO and removed >= ROOM_MIN_REMOVED_DB)}
        if self.rec:
            self.rec.log("room", **self.room)

    def _log_band(self) -> None:
        """The beats and the decisions since last time, into the session's log."""
        band, origin = self._live_band()
        if band is None or self.rec is None or not self.rec.on:
            return
        if self.logged["band"] is not band:
            self.logged = {"beats": 0, "heard": 0, "band": band}
            self.rec.log("band", origin=origin)
        while self.logged["beats"] < len(band.beats):
            b = band.beats[self.logged["beats"]]
            self.rec.log("beat", i=self.logged["beats"], t=b.t + origin, made_at=b.made_at + origin, bpm=b.bpm,
                         confidence=b.confidence, beat=b.beat, bar_confidence=b.bar_confidence)
            self.logged["beats"] += 1
        bs = band.band
        while self.logged["heard"] < min(bs.n_heard, len(bs.logs)):
            lg = bs.logs[self.logged["heard"]]
            self.rec.log("decision", i=lg.i, t=lg.t + origin, bar=lg.bar, beat=lg.beat, beat_conf=lg.beat_conf,
                         key=lg.key, key_conf=lg.key_conf, predicted=lg.predicted, pred_conf=lg.pred_conf,
                         heard_before=lg.heard_before, heard_conf=lg.heard_conf, react=lg.react,
                         react_conf=lg.react_conf, open=lg.open, decided_at=lg.decided_at + origin,
                         plays={k: {"chord": v.chord, "tone": v.tone, "muted": v.muted, "offset": v.offset}
                                for k, v in lg.plays.items()},
                         **({"tune": lg.tune, "named": lg.named, "named_conf": lg.named_conf, "held": lg.held}
                            if self.catalog is not None else {}))
            self.logged["heard"] += 1

    def _follow_clock(self, h) -> None:
        """An xrun moves the two counts against each other: the estimate jumps, and L with it."""
        est = float(h[duplex.H_L])
        if self.L_est_ref is not None and abs(est - self.L_est_ref) > 0.002 * RATE:
            d = est - self.L_est_ref
            self.L += d
            self.L_est_ref = est
            self.L_shifts.append(d)
            self.player.clock.offset = self._offset()

    def _block(self, x: np.ndarray, echo: np.ndarray | None = None) -> None:
        self.level.append(float(np.abs(x).max()) if len(x) else 0.0)
        if self.band is None:
            self.pre.append(x.copy())
            if echo is not None:
                self.pre_echo.append(echo.copy())
            return
        if self.s.count == "voice":  # no estimate for a spoken count's band yet: with it the chase of a quick
            out = self.band.push(x)    # speed-up failed (Big Sciota replayed: 1.26 s behind, 15 ms without)
        else:
            out = self.band.push(x, echo=echo)
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
            elif isinstance(e, Stop):  # "stop" said, or the player stopped playing (`VoiceBand.stop_with_player`)
                self.engine.cut(int(e.decided_at * RATE - self.L - self.conv))
                self.state = "listening for your count"
                self.message = ("You stopped playing: the band stopped with you" if e.how == "player stopped"
                                else "You said stop") + ". Count it in again, or press Stop"
                self.last_cue = {}
            elif isinstance(e, Cue):
                self._cues([e])

    def _cues(self, cues) -> None:
        for c in cues:  # in the stream's seconds (a VoiceBand's already shifted by its origin)
            if self.rec:
                self.rec.log("cue", i=c.i, part=c.part, chord=c.play.chord, tone=c.play.tone, muted=c.play.muted,
                             t=c.t, beat_t=c.beat_t, decided_at=c.decided_at, bar=c.bar,
                             on=bool(self.s.parts.get(c.part, False)), heard_to=self.read / RATE)
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
        if self.echo is not None:
            self.echo_state = self.echo.state()
        with self._ring_lock:
            if self.ring is not None:
                self.ring.close()
                self.ring = None
        self.ended = time.time()
        self.state = "error" if self.error else "stopped"
        if not self.message and self._stop_reason:
            self.message = self._stop_reason[0].upper() + self._stop_reason[1:]
        if self.rec is not None and self.rec.on:
            try:
                self._log_band()
                notes = [{"beat": lg.tag[0] if lg.tag else None, "part": lg.part, "key": lg.key, "vel": lg.vel,
                          "want": lg.want, "start": lg.start, "stop": lg.stop, "late": lg.late}
                         for lg in (getattr(self.engine, "log", None) or [])]
                self.rec.log("stop", reason=self._stop_reason, error=self.error)
                self.rec.log("end", timing=self.timing(), final={k: v for k, v in self.final.items()},
                             notes=notes, clicks=self.clicks, L=self.L, conv=self.conv)
            finally:
                self.rec.close()
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
        if self.catalog is not None:
            out["find"] = self.found_status(band)
            if out["find"]["found"]:
                out["tune"] = out["find"]["title"]
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
        out["count_in"] = self.plan
        out["echo"] = {"on": self.echo is not None, "removed_db": self.levels[-1]["removed_db"] if self.levels else None,
                       "room": self.room}
        out["levels"] = self.levels[-1] if self.levels else None
        out["recording"] = ({"on": True, "folder": self.rec.path.name, "minutes": round(self.rec.frames / RATE / 60, 1)}
                            if self.rec and self.rec.on else {"on": False, "why": self.rec.why if self.rec else ""})
        return out

    def found_status(self, band) -> dict:
        """No tune chosen: the tune whose chart the band follows (None while it listens), and the one the matcher
        names, how surely."""
        found = getattr(band, "found", None) if band is not None else None
        named = getattr(band, "named", None) if band is not None else None
        titles = {t.id: t.name for t in self.catalog or []}
        out = {"found": None, "title": None, "key": None, "named": None, "named_title": None, "sure": None}
        if found is not None:
            from transcribe.livechords import chart_key
            k = chart_key(found.chart)
            out.update(found=found.tune.id, title=titles.get(found.tune.id, found.tune.title),
                       key=chord_name((k[0], "min" if k[1] == "minor" else "maj")))
        if named is not None:
            out.update(named=named.id, named_title=titles.get(named.id, named.title), sure=round(named.confidence, 2))
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
        with self._ring_lock:  # (the ring closes under the lock: a status call never reads a closed one)
            h = self.ring.header if self.ring is not None else None
            if h is not None:
                out.update({"L_estimate_ms": None if np.isnan(h[duplex.H_L]) else round(1000 * h[duplex.H_L] / RATE, 2),
                            "L_spread_ms": None if np.isnan(h[duplex.H_L_SPREAD]) else round(1000 * h[duplex.H_L_SPREAD] / RATE, 2),
                            "capture_overruns": int(h[duplex.H_OVERRUNS]),
                            "period": int(h[duplex.H_PLAY_PERIOD]), "buffer": int(h[duplex.H_PLAY_BUFFER]),
                            "capture_period": int(h[duplex.H_CAP_PERIOD]), "capture_buffer": int(h[duplex.H_CAP_BUFFER])})
        if self.ring is None and self.final:
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
    ring = duplex.Ring(int(RING_S * RATE))
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
