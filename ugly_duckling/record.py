"""Each run of the band kept, so it can be replayed and graded offline: a folder per session under `[record] dir`
(default `~/ud-sessions`), named by its start time (`2026-10-17_163254`), holding

- `capture.flac`: 48 kHz, 24-bit, four channels: 0 the chosen input as captured (the room mic, the Nadine, the
  piezo), 1 the device's own return of the band's output (the loopback, capture channels 11-12 mixed, as the ring
  holds it: the clicks and the band, sample-aligned with channel 0), 2 the input as the band heard it (the band's
  own sound taken out, `transcribe.echo`; channel 0 again with echo removal off), 3 the room mic (`[device] room`,
  whichever input the band follows; silence if none). Frame n is the capture's frame n,
  the stream time the log's times are in.
- `session.jsonl`: one JSON object a line, each with `"ev"`: `start` (the settings, the tune and its chart, the
  config's device and band settings), `clock` (L estimated and measured), `count_in` (the clicks, engine frames and
  stream times), `beat` (each beat the band was given), `cue` (each part's play: chord, tone, muted, its time, the
  beat's time, decided at), `decision` (each beat's log once heard: what the band knew, predicted, heard, played),
  `level` (every half second: the input's rms and peak, before and after echo removal, the loopback's), `room` (every
  2 s: the delay of the echo path learnt on the room mic, from the loopback: the output to the room to the mic;
  `reliable` false when its peak hardly stands out or little of the band was heard), `state`,
  `stop` (why), `end` (the timing, the engine's counts, every note's frame as the engine started it).

Everything is written by a thread of its own (`Recorder`), never by the engine's process or the listening loop: they
only put arrays and dicts on a queue. Disk: before a session the oldest sessions are deleted until at most
`keep - 1` remain and they take under `max_gb`; nothing is recorded when the disk has under `min_free_gb` free (the
exercise takes share it), and a session stops recording at `max_minutes`.
"""

from __future__ import annotations

import json
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 48000


@dataclass
class RecordConfig:
    on: bool = True
    dir: str = "~/ud-sessions"
    keep: int = 40  # sessions kept at most ...
    max_gb: float = 2.0  # ... and their size at most
    min_free_gb: float = 2.0  # no recording with less than this free on the disk
    max_minutes: float = 30.0  # a session's capture stops here (the log goes on)


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def prune(root: Path, keep: int, max_bytes: float) -> list[str]:
    """Delete the oldest sessions until at most `keep` remain and they take under `max_bytes`; their names."""
    if not root.is_dir():
        return []
    sessions = sorted(p for p in root.iterdir() if p.is_dir())
    sizes = {p: _size(p) for p in sessions}
    gone = []
    while sessions and (len(sessions) > keep or sum(sizes[p] for p in sessions) > max_bytes):
        p = sessions.pop(0)
        shutil.rmtree(p, ignore_errors=True)
        gone.append(p.name)
    return gone


def _clean(v):
    """JSON for numpy values, tuples, dataclasses' dicts."""
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if not np.isfinite(f) else round(f, 6)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, np.ndarray):
        return _clean(v.tolist())
    if isinstance(v, Path):
        return str(v)
    return v


class Recorder:
    """One session's folder, written by a thread of its own. `audio(block)`: frames (n, 3) float; `log(ev, **fields)`.
    `close()` waits for the writer. If the disk is short or recording is off, `on` is False and both do nothing."""

    def __init__(self, cfg: RecordConfig, name: str | None = None):
        self.cfg = cfg
        self.on = False
        self.why = ""
        self.path: Path | None = None
        self.frames = 0
        self.max_frames = int(cfg.max_minutes * 60 * RATE)
        self.errors = 0
        self.q: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        if not cfg.on:
            self.why = "recording is off ([record] on)"
            return
        root = Path(cfg.dir).expanduser()
        try:
            root.mkdir(parents=True, exist_ok=True)
            self.pruned = prune(root, max(0, cfg.keep - 1), cfg.max_gb * 1e9)
            free = shutil.disk_usage(root).free / 1e9
        except OSError as e:
            self.why = f"no session folder: {e}"
            return
        if free < cfg.min_free_gb:
            self.why = f"only {free:.1f} GB free (under {cfg.min_free_gb:g}): not recording"
            return
        name = name or time.strftime("%Y-%m-%d_%H%M%S")
        self.path = root / name
        k = 1
        while self.path.exists():
            k += 1
            self.path = root / f"{name}-{k}"
        self.path.mkdir()
        self.on = True
        self.thread = threading.Thread(target=self._write, daemon=True, name="ud-recorder")
        self.thread.start()

    def audio(self, block: np.ndarray) -> None:
        if not self.on or self.frames >= self.max_frames:
            return
        block = block[: self.max_frames - self.frames]
        self.frames += len(block)
        self.q.put(("audio", np.asarray(block, dtype=np.float32).copy()))

    def log(self, ev: str, **fields) -> None:
        if self.on:
            self.q.put(("log", {"ev": ev, "wall": round(time.time(), 3), **fields}))

    def close(self) -> None:
        if self.thread is not None:
            self.q.put(("end", None))
            self.thread.join(timeout=30)
            self.thread = None

    def _write(self) -> None:
        import soundfile as sf
        snd = None
        logf = open(self.path / "session.jsonl", "w")
        try:
            while True:
                kind, item = self.q.get()
                if kind == "end":
                    break
                try:
                    if kind == "audio":
                        if snd is None:
                            snd = sf.SoundFile(str(self.path / "capture.flac"), "w", RATE, item.shape[1], "PCM_24",
                                               format="FLAC")
                        snd.write(np.clip(item, -1.0, 1.0))
                    else:
                        logf.write(json.dumps(_clean(item)) + "\n")
                except Exception:  # noqa: BLE001 (a full disk must not stop the band)
                    self.errors += 1
        finally:
            if snd is not None:
                snd.close()
            logf.close()
