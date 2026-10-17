"""The band's sound engine: each part on its own FluidSynth (`ambient/fluid.py`), mixed with the part's gain and
pan, computed in short blocks and written to an output (`ambient/output.py`) with a short buffer.

Notes come in groups, one group a cue (`ambient/bandplayer.py`): the notes of one part's play, each at an engine
time (s; frame 0 is 0 s and the first frame the output plays). Before computing each block the engine takes the
groups queued since the last; a group whose first note is already past (its frame computed) is late. Late by no
more than the group's allowance, the whole group sounds now, shifted together (a strum stays a strum); later than
that, it is dropped. Every note's fate is logged (`log`), and counted by part.

Engine time is the output's own clock: after an underrun the output says how much silence the device played
(where it knows), and the engine moves its clock on by as much, so a frame computed for engine time t is still
heard at t.
"""

from __future__ import annotations

import heapq
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .fluid import STEP, Synth
from .output import Output


@dataclass
class NoteLog:
    tag: object  # the cue's (beat, part)
    part: str
    key: int
    vel: int
    want: int  # the frame it was asked for
    start: int | None  # the frame FluidSynth started it (a 64-frame boundary); None: dropped
    stop: int | None  # the frame it was let go
    late: int  # frames the group was shifted by (0: on time)
    queued_at: float  # monotonic time it was queued
    committed: int  # the first frame it could still have had when queued


@dataclass(frozen=True)
class Voice:
    channel: int
    program: int
    pan: float  # -1 left .. 1 right
    gain_db: float  # on the part's FluidSynth output


class BandEngine:
    """The band's parts, each a `Voice`, from the SoundFonts `fonts` (loaded in order). `block`: frames computed at
    a time (a multiple of 64). `keep_stems`: keep each part's sound before its gain and pan (for replays)."""

    def __init__(self, fonts: list[Path], voices: dict[str, Voice], output: Output, block: int = 128,
                 rate: int = 48000, gain_db: float = 0.0, rt_priority: int | None = None, keep_stems: bool = False,
                 on_block=None):
        if block % STEP:
            raise ValueError(f"block {block} is not a multiple of {STEP}")
        self.fonts, self.voices, self.output = fonts, voices, output
        self.block, self.rate, self.gain = block, rate, 10 ** (gain_db / 20)
        self.rt_priority = rt_priority
        self.keep_stems = keep_stems
        self.on_block = on_block  # called in the engine's thread after each block is written
        self.q: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None
        self.synths: dict[str, Synth] = {}
        self.pairs = 0  # stereo pairs in a block's buffer: a part's MIDI channel is its pair
        self.pos = 0  # the next frame to compute
        self.committed = 0  # the first frame a note queued now can still get
        self.events: list = []  # (frame, 0 off | 1 on, seq, part, key, vel, log)
        self._seq = 0
        self.log: list[NoteLog] = []
        self.counts = {p: {"on time": 0, "late": 0, "dropped": 0} for p in voices}
        self.late_s: dict[str, list[float]] = {p: [] for p in voices}
        self.stems: dict[str, list[np.ndarray]] = {p: [] for p in voices}
        self.compute_s: list[float] = []  # each block's compute time, as the wall clock saw it (s)
        self.cpu_s = 0.0  # the engine thread's own CPU time over them
        self.skipped = 0  # frames the clock moved on after underruns
        self._applied: list = []  # (note log, "start" | "stop") applied in the block being computed
        self.error: str | None = None
        self.rt = False

    # ---- the outside

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def time(self) -> float:
        """Engine time computed so far (s)."""
        return self.pos / self.rate

    def latency(self) -> float:
        """The most a note can wait from being queued to being heard: a block, and the output's buffer."""
        return self.block / self.rate + self.output.latency()

    def started_at(self) -> float | None:
        """Monotonic time the output played (or will play) frame 0, if known."""
        return self.output.started_at

    @property
    def underruns(self) -> int:
        return self.output.underruns

    @property
    def underrun_frames(self) -> int:
        return getattr(self.output, "underrun_frames", 0)

    @property
    def gaps(self) -> list:
        return getattr(self.output, "gaps", [])

    @property
    def granted(self) -> dict:
        return self.output.granted()

    def play(self, group: list[tuple[float, float, str, int, int]], late_s: float, tag=None) -> None:
        """A cue's notes: (engine time s, length s, part, MIDI key, velocity); sounding late by up to `late_s`."""
        self.q.put((group, late_s, tag, time.monotonic(), self.committed))

    def start(self) -> None:
        if self.running:
            return
        self.pairs = max(v.channel for v in self.voices.values()) + 1
        for part, v in self.voices.items():  # a synth a part (ambient/fluid.py, Synth)
            self.synths[part] = Synth(self.fonts, self.rate)
            self.synths[part].program(v.channel, v.program)
        self.output.open()
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name="band-engine")
        self.thread.start()

    def stop(self) -> None:
        self.stop_flag.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.thread = None
        self.output.close()
        for synth in self.synths.values():
            synth.close()
        self.synths = {}

    # ---- the engine's thread

    def mix_matrix(self) -> np.ndarray:
        """(2 * pairs, 2): each part's stereo pair to its mono sound (the mean of the two, as the offline render
        takes it), then its gain and pan."""
        m = np.zeros((2 * self.pairs, 2), dtype=np.float32)
        for v in self.voices.values():
            g = 10 ** (v.gain_db / 20) * self.gain
            lr = (np.sqrt((1 - v.pan) / 2) * np.sqrt(2), np.sqrt((1 + v.pan) / 2) * np.sqrt(2))
            for row in (2 * v.channel, 2 * v.channel + 1):
                m[row] = (0.5 * g * lr[0], 0.5 * g * lr[1])
        return m

    def _run(self) -> None:
        if self.rt_priority:
            try:
                os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(self.rt_priority))
                self.rt = True
            except (OSError, AttributeError):
                self.rt = False
        m = self.mix_matrix()
        buf = np.zeros((2 * self.pairs, self.block), dtype=np.float32)
        try:
            while not self.stop_flag.is_set():
                c0, t0 = time.perf_counter(), time.thread_time()
                self.committed = self.pos + self.block
                self._applied = []
                self._drain()
                # a note starts on the 64-frame boundary nearest its frame: with one due in this block, the
                # block is computed 64 frames at a time; else all at once
                due = self.events and self.events[0][0] < self.pos + self.block - STEP // 2
                step = STEP if due else self.block
                for a in range(0, self.block, step):
                    f = self.pos + a
                    while self.events and self.events[0][0] < f + STEP // 2:
                        self._apply(heapq.heappop(self.events), f)
                    for part, synth in self.synths.items():
                        ch = self.voices[part].channel
                        synth.render_rows(buf, 2 * ch, 2 * ch + 1, a, a + step)
                out = buf.T @ m
                if self.keep_stems:
                    for part, v in self.voices.items():
                        self.stems[part].append(0.5 * (buf[2 * v.channel] + buf[2 * v.channel + 1]))
                self.pos += self.block
                self.compute_s.append(time.perf_counter() - c0)
                self.cpu_s += time.thread_time() - t0
                gap = self.output.write(out)
                if gap:  # the device played silence for `gap` frames: move the clock on
                    self._skip(gap)
                if self.on_block is not None:
                    self.on_block(self)
        except Exception as e:  # kept for the status
            self.error = f"band engine stopped: {e}"

    def _skip(self, n: int) -> None:
        """The device played `n` frames of silence before the block just written: that block, and the notes that
        started or stopped in it, were heard `n` frames later than computed, and the clock moves on by `n`, so the
        blocks after it are heard when computed. The synth itself goes on where it was."""
        for lg, which in self._applied:
            setattr(lg, which, getattr(lg, which) + n)
        if self.keep_stems:
            for part in self.voices:
                self.stems[part].insert(len(self.stems[part]) - 1, np.zeros(n, dtype=np.float32))
        self.pos += n
        self.skipped += n

    def _drain(self) -> None:
        while True:
            try:
                group, late_s, tag, queued_at, committed = self.q.get_nowait()
            except queue.Empty:
                return
            first = min(int(round(at * self.rate)) for at, *_ in group)
            late = max(0, self.pos - first)
            part = group[0][2]
            if late > late_s * self.rate:
                self.counts[part]["dropped"] += 1
                for at, length, p, key, vel in group:
                    self.log.append(NoteLog(tag, p, key, vel, int(round(at * self.rate)), None, None, late,
                                            queued_at, committed))
                continue
            self.counts[part]["late" if late else "on time"] += 1
            if late:
                self.late_s[part].append(late / self.rate)
            for at, length, p, key, vel in group:
                want = int(round(at * self.rate))
                lg = NoteLog(tag, p, key, vel, want, None, None, late, queued_at, committed)
                self.log.append(lg)
                on = want + late
                off = on + max(1, int(round(length * self.rate)))
                self._push(on, 1, p, key, vel, lg)
                self._push(off, 0, p, key, 0, lg)

    def _push(self, frame: int, kind: int, part: str, key: int, vel: int, lg) -> None:
        self._seq += 1
        heapq.heappush(self.events, (frame, kind, self._seq, part, key, vel, lg))

    def _apply(self, ev, f: int) -> None:
        frame, kind, _, part, key, vel, lg = ev
        ch = self.voices[part].channel
        if kind:
            self.synths[part].noteon(ch, key, vel)
            lg.start = f
            self._applied.append((lg, "start"))
        else:
            self.synths[part].noteoff(ch, key)
            lg.stop = f
            self._applied.append((lg, "stop"))


# ---- the engine in a process of its own


@dataclass(frozen=True)
class EngineSpec:
    """What a band engine is made of, to build it in another process."""
    fonts: tuple[Path, ...]
    voices: dict
    output: str  # ambient/output.py's kind
    device: str
    buffer_ms: float
    period_ms: float | None = None
    capture: Path | None = None
    block: int = 128
    rate: int = 48000
    gain_db: float = 0.0
    rt_priority: int = 0
    keep_stems: bool = False

    def build(self, on_block=None) -> BandEngine:
        from .output import make_output
        out = make_output(self.output, self.device, self.rate, self.buffer_ms, self.period_ms, self.capture)
        return BandEngine(list(self.fonts), self.voices, out, self.block, self.rate, self.gain_db,
                          self.rt_priority or None, self.keep_stems, on_block)


_SHARED = ("committed", "pos", "started_at", "running")


def _engine_process(spec: EngineSpec, conn, shared) -> None:
    """The child: the engine, fed the groups the pipe brings; its clock in `shared`; at the end, what it kept."""
    def mirror(e: BandEngine) -> None:  # the engine's clock, for the parent
        shared[0], shared[1] = e.committed, e.pos
        shared[2] = e.started_at() or -1.0

    eng = spec.build(mirror)
    try:
        eng.start()
    except Exception as e:  # noqa: BLE001 (said to the parent)
        conn.send(("error", str(e)))
        return
    shared[3] = 1.0
    conn.send(("ready", None))
    while True:
        msg = conn.recv()
        if msg[0] == "play":
            _, group, late_s, tag, queued_at, committed = msg
            eng.q.put((group, late_s, tag, queued_at, committed))
        elif msg[0] == "stop":
            break
    shared[3] = 0.0
    eng.stop()
    out = eng.output
    conn.send(("done", {"log": eng.log, "counts": eng.counts, "late_s": eng.late_s,
                        "stems": eng.stems if spec.keep_stems else {}, "compute_s": eng.compute_s, "cpu_s": eng.cpu_s,
                        "skipped": eng.skipped, "error": eng.error, "rt": eng.rt, "underruns": out.underruns,
                        "underrun_frames": getattr(out, "underrun_frames", 0), "gaps": getattr(out, "gaps", []),
                        "granted": out.granted(),
                        "pairs": eng.pairs, "gain": eng.gain}))


class EngineProcess:
    """A band engine in a process of its own, so the listening's work (the same program's other threads) never
    holds it up: Python runs one thread at a time, and a thread waiting for its turn can wait for milliseconds.
    It has the engine's outside (`play`, `time`, `committed`, `started_at`, `latency`); `stop` brings back what it
    kept (`log`, `counts`, `stems`, ...), as attributes of the same names."""

    def __init__(self, spec: EngineSpec):
        import multiprocessing as mp
        self.spec, self.rate, self.block = spec, spec.rate, spec.block
        self.voices, self.fonts = spec.voices, list(spec.fonts)
        self._mp = mp.get_context("spawn")
        self.shared = self._mp.Array("d", len(_SHARED), lock=False)
        self.proc = None
        self.conn = None
        self.error: str | None = None

    def start(self) -> None:
        self.conn, child = self._mp.Pipe()
        self.shared[2] = -1.0
        self.proc = self._mp.Process(target=_engine_process, args=(self.spec, child, self.shared), daemon=True,
                                     name="band-engine")
        self.proc.start()
        kind, info = self.conn.recv()
        if kind == "error":
            self.proc.join()
            raise RuntimeError(f"the band engine did not start: {info}")

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.is_alive() and self.shared[3] > 0

    @property
    def committed(self) -> int:
        return int(self.shared[0])

    def time(self) -> float:
        return self.shared[1] / self.rate

    def started_at(self) -> float | None:
        return None if self.shared[2] < 0 else self.shared[2]

    def latency(self) -> float:
        return self.block / self.rate + self.spec.buffer_ms / 1000

    def play(self, group, late_s: float, tag=None) -> None:
        self.conn.send(("play", group, late_s, tag, time.monotonic(), self.committed))

    def stop(self) -> None:
        if self.proc is None:
            return
        self.conn.send(("stop",))
        kind, kept = self.conn.recv()
        self.proc.join(timeout=5)
        self.proc = None
        for k, v in kept.items():
            setattr(self, k, v)
