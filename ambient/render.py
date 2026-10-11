"""Render settings to a file, offline: to measure loudness and CPU cost.

The conductor runs against a clock that this module advances; Csound then
renders the notes as fast as it can. Used by tools/calibrate.
"""

import random
import time
from pathlib import Path

import numpy as np

from .conductor import Conductor
from .config import REPO
from .engine import init_csound, orchestra
from . import samples

RATE = 48000


class _Clock:
    """Stands in for the engine: collects notes and channel values."""

    running = True
    error = None
    underruns = 0

    def __init__(self):
        self.t = 0.0
        self.notes: list[tuple] = []
        self.channels: dict[str, float] = {}

    def time(self) -> float:
        return self.t

    def set(self, name: str, value: float) -> None:
        self.channels[name] = value

    def note(self, at: float, instr: float, dur: float, *p: float) -> None:
        self.notes.append((max(at, 0.0), instr, dur, *p))


def render(state: dict, seconds: float, path: Path, gain_db: float = 0.0, seed: int = 1,
           sounds_dir: Path | None = REPO / "sounds") -> dict:
    """Render `seconds` of `state` to a float WAV. Returns level and cost.
    The sampled voices play from sounds_dir's fonts (None: synthesized)."""
    import ctcsound

    orc = orchestra(sounds_dir)  # first: it says which voices are sampled
    clock = _Clock()
    c = Conductor(clock, random.Random(seed))
    c.apply(state)
    while clock.t < seconds:
        c.tick()
        clock.t += 0.2
    clock.t = seconds
    c.silence_texture()

    score = []
    for at, instr, dur, *p in sorted(clock.notes, key=lambda n: n[0]):
        score.append(f"i {instr:g} {at:.4f} {dur:.4f} " + " ".join(f"{x:.6g}" for x in p))
    init_csound(ctcsound)
    cs = ctcsound.Csound()
    for o in ("-d", "-m0", f"-o{path}", "-W", "-f"):
        cs.setOption(o)
    if cs.compileOrc(orc) != 0:
        raise RuntimeError("the orchestra did not compile")
    cs.readScore("\n".join(score) + "\n")
    cs.start()
    for k, v in clock.channels.items():
        cs.setControlChannel(k, v)
    cs.setControlChannel("fade", 1.0)
    cs.setControlChannel("gain_db", gain_db)
    c0 = time.process_time()
    while cs.performKsmps() == 0:
        if cs.scoreTime() > seconds + 12:  # tails beyond this are not needed
            break
    cpu = time.process_time() - c0
    cs.cleanup()
    x = read_float_wav(path)[: int(seconds * RATE)]
    return {"seconds": seconds, "cpu_pct": 100 * cpu / (len(read_float_wav(path)) / RATE),
            "gated_rms_dbfs": gated_rms_dbfs(x), "peak_dbfs": peak_dbfs(x), "notes": len(clock.notes)}


def read_float_wav(path: Path) -> np.ndarray:
    b = Path(path).read_bytes()
    i = 12
    while b[i:i + 4] != b"data":
        i += 8 + int.from_bytes(b[i + 4:i + 8], "little")
    n = int.from_bytes(b[i + 4:i + 8], "little")
    return np.frombuffer(b[i + 8:i + 8 + n], dtype="<f4").reshape(-1, 2)


def db(x: float) -> float:
    return 20 * np.log10(max(x, 1e-10))


def peak_dbfs(x: np.ndarray) -> float:
    return db(float(np.max(np.abs(x)))) if len(x) else -200.0


def gated_rms_dbfs(x: np.ndarray, block_s: float = 0.4, gate_dbfs: float = -70) -> float:
    """Mean power over 400 ms blocks above -70 dBFS, per channel (so a mono
    signal on both channels reads the same as piano-recorder's takes)."""
    n = int(block_s * RATE)
    blocks = [np.mean(x[i:i + n] ** 2) for i in range(0, len(x) - n + 1, n)]
    kept = [p for p in blocks if 10 * np.log10(max(p, 1e-20)) > gate_dbfs]
    return 10 * np.log10(np.mean(kept)) if kept else -200.0
