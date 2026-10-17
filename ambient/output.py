"""Where an engine's audio goes: a playback device, or a file at the pace of one.

Each output takes blocks of stereo float frames (`write`), blocking while the device's buffer is full, and counts
underruns. The config picks one (`[output] kind`, `[band] kind`):

- `aplay`: through the `aplay` program, as the ambient music has always played. The buffer is aplay's; the pipe to
  it holds up to 85 ms more (16 KB; a pipe is at least a page, 21 ms). For music that needs no quick response.
- `alsa`: straight to an ALSA device through alsa-lib (no program, no pipe), with the period and buffer asked for.
  What the device granted is read back (`granted`), and how far ahead of the sound the writer is (`ahead`).
- `paced`: no device. The frames are consumed at the pace of a device clock (the monotonic clock) from a buffer of
  the size asked for, and kept (`capture`): a replay hears what a sound card would have played, when it would
  have played it, and nothing is heard. A block that comes after the buffer ran dry is an underrun; the silence a
  device would have played is put in the capture, so its frame n is always the device's frame n. The capture is
  written by a thread of its own: a write to a file can wait on the disk (on the practice unit, 33-72 ms while the
  kernel writes the file's dirty pages back, about every 30 s of capture), and the engine's loop must not.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import queue
import subprocess
import threading
import time
import wave
from pathlib import Path

import numpy as np


class OutputError(Exception):
    pass


def to_s16(frames: np.ndarray) -> bytes:
    return np.clip(frames * 32767.0, -32768, 32767).astype("<i2").tobytes()


class Output:
    """A playback device: `open()`, then `write()` blocks of (n, 2) float frames, `close()`."""

    rate: int
    underruns = 0
    started_at: float | None = None  # monotonic time its frame 0 was (or will be) played, when known

    def open(self) -> None:
        pass

    def write(self, frames: np.ndarray) -> int:
        """Play these frames after those before (blocking while the buffer is full). Returns the frames of silence
        the device played before them (an underrun), where the output knows; else 0."""
        raise NotImplementedError

    def ahead(self) -> float | None:
        """Seconds between the next frame written and when it is heard (the buffered audio), if known."""
        return None

    def latency(self) -> float:
        """The most audio the device holds ahead of what is heard (s)."""
        raise NotImplementedError

    def granted(self) -> dict:
        return {}

    def close(self) -> None:
        pass


class AplayOutput(Output):
    """The `aplay` program, fed through a pipe (the ambient music's output since 2026-10-11)."""

    PIPE = 16384  # bytes: 85 ms of 16-bit stereo at 48 kHz

    def __init__(self, device: str, rate: int, buffer_ms: int):
        self.device, self.rate, self.buffer_ms = device, rate, buffer_ms
        self.proc: subprocess.Popen | None = None
        self.underruns = 0

    def open(self) -> None:
        self.proc = subprocess.Popen(
            ["aplay", "-D", self.device, "-f", "S16_LE", "-r", str(self.rate), "-c", "2",
             f"--buffer-time={self.buffer_ms * 1000}", "-t", "raw", "-"],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(0.3)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read().decode(errors="replace").strip()
            raise OutputError(f"could not open {self.device}: {err}")
        try:  # a small pipe, so control changes land sooner
            import fcntl
            fcntl.fcntl(self.proc.stdin.fileno(), 1031, self.PIPE)  # F_SETPIPE_SZ
        except OSError:
            pass
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def write(self, frames: np.ndarray) -> int:
        try:
            self.proc.stdin.write(to_s16(frames))
        except (BrokenPipeError, ValueError):
            raise OutputError("the playback device went away")
        return 0

    def latency(self) -> float:
        return self.buffer_ms / 1000 + self.PIPE / (4 * self.rate)

    def granted(self) -> dict:
        return {"buffer_ms": self.buffer_ms, "pipe_ms": 1000 * self.PIPE / (4 * self.rate)}

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None

    def _read_stderr(self) -> None:
        for line in self.proc.stderr:
            if b"underrun" in line:
                self.underruns += 1


_asound = None


def asound():
    """alsa-lib, loaded once."""
    global _asound
    if _asound is None:
        lib = ctypes.CDLL(ctypes.util.find_library("asound") or "libasound.so.2")
        vp, ci, cu, cl, pvp = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p)
        pul, pi = ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int)
        for fn, res, args in (
                ("snd_pcm_open", ci, [pvp, ctypes.c_char_p, ci, ci]), ("snd_pcm_close", ci, [vp]),
                ("snd_pcm_hw_params_malloc", ci, [pvp]), ("snd_pcm_hw_params_free", None, [vp]),
                ("snd_pcm_hw_params_any", ci, [vp, vp]), ("snd_pcm_hw_params_set_access", ci, [vp, vp, ci]),
                ("snd_pcm_hw_params_set_format", ci, [vp, vp, ci]), ("snd_pcm_hw_params_set_channels", ci, [vp, vp, cu]),
                ("snd_pcm_hw_params_set_rate", ci, [vp, vp, cu, ci]),
                ("snd_pcm_hw_params_set_rate_resample", ci, [vp, vp, cu]),
                ("snd_pcm_hw_params_set_period_size_near", ci, [vp, vp, pul, pi]),
                ("snd_pcm_hw_params_set_buffer_size_near", ci, [vp, vp, pul]),
                ("snd_pcm_hw_params", ci, [vp, vp]),
                ("snd_pcm_hw_params_get_period_size", ci, [vp, pul, pi]),
                ("snd_pcm_hw_params_get_buffer_size", ci, [vp, pul]),
                ("snd_pcm_sw_params_malloc", ci, [pvp]), ("snd_pcm_sw_params_free", None, [vp]),
                ("snd_pcm_sw_params_current", ci, [vp, vp]),
                ("snd_pcm_sw_params_set_start_threshold", ci, [vp, vp, ctypes.c_ulong]),
                ("snd_pcm_sw_params", ci, [vp, vp]),
                ("snd_pcm_writei", cl, [vp, vp, ctypes.c_ulong]), ("snd_pcm_recover", ci, [vp, ci, ci]),
                ("snd_pcm_delay", ci, [vp, ctypes.POINTER(ctypes.c_long)]), ("snd_pcm_drop", ci, [vp]),
                ("snd_strerror", ctypes.c_char_p, [ci])):
            f = getattr(lib, fn)
            f.restype, f.argtypes = res, args
        _asound = lib
    return _asound


class AlsaOutput(Output):
    """An ALSA device written straight through alsa-lib: 16-bit stereo, interleaved, the period and buffer asked
    for (the device may grant others: `granted`). Blocking writes pace the engine by the device's own clock.
    The device starts when its buffer is first full.

    When frame 0 was heard (`started_at`) is estimated after every write from the device's delay (`ahead`: the
    frames between the next one written and the one being played, as the driver reports them), smoothed; after an
    underrun the device restarts later, and the jump in that estimate is the silence it played."""

    S16_LE, RW_INTERLEAVED = 2, 3

    def __init__(self, device: str, rate: int, period: int, periods: int):
        self.device, self.rate, self.want = device, rate, (period, period * periods)
        self.pcm = None
        self.period = self.buffer = 0
        self.underruns = 0
        self.written = 0  # frames written, with the silence of underruns
        self.started_at: float | None = None
        self.residuals: list[float] = []  # each estimate of started_at less the smoothed one (s)
        self.gaps: list[tuple[int, int]] = []

    def _check(self, r: int, what: str) -> None:
        if r < 0:
            raise OutputError(f"{self.device}: {what}: {asound().snd_strerror(r).decode()}")

    def open(self) -> None:
        lib = asound()
        pcm = ctypes.c_void_p()
        self._check(lib.snd_pcm_open(ctypes.byref(pcm), self.device.encode(), 0, 0), "could not open")
        self.pcm = pcm
        hw = ctypes.c_void_p()
        lib.snd_pcm_hw_params_malloc(ctypes.byref(hw))
        try:
            self._check(lib.snd_pcm_hw_params_any(pcm, hw), "no configuration")
            lib.snd_pcm_hw_params_set_rate_resample(pcm, hw, 0)
            self._check(lib.snd_pcm_hw_params_set_access(pcm, hw, self.RW_INTERLEAVED), "access")
            self._check(lib.snd_pcm_hw_params_set_format(pcm, hw, self.S16_LE), "16-bit")
            self._check(lib.snd_pcm_hw_params_set_channels(pcm, hw, 2), "stereo")
            self._check(lib.snd_pcm_hw_params_set_rate(pcm, hw, self.rate, 0), f"{self.rate} Hz")
            period, buf, d = ctypes.c_ulong(self.want[0]), ctypes.c_ulong(self.want[1]), ctypes.c_int(0)
            self._check(lib.snd_pcm_hw_params_set_period_size_near(pcm, hw, ctypes.byref(period), ctypes.byref(d)),
                        "period")
            self._check(lib.snd_pcm_hw_params_set_buffer_size_near(pcm, hw, ctypes.byref(buf)), "buffer")
            self._check(lib.snd_pcm_hw_params(pcm, hw), "parameters")
            lib.snd_pcm_hw_params_get_period_size(hw, ctypes.byref(period), ctypes.byref(d))
            lib.snd_pcm_hw_params_get_buffer_size(hw, ctypes.byref(buf))
            self.period, self.buffer = period.value, buf.value
        finally:
            lib.snd_pcm_hw_params_free(hw)
        sw = ctypes.c_void_p()
        lib.snd_pcm_sw_params_malloc(ctypes.byref(sw))
        try:
            lib.snd_pcm_sw_params_current(pcm, sw)
            lib.snd_pcm_sw_params_set_start_threshold(pcm, sw, self.buffer)
            self._check(lib.snd_pcm_sw_params(pcm, sw), "start threshold")
        finally:
            lib.snd_pcm_sw_params_free(sw)

    def write(self, frames: np.ndarray) -> int:
        lib, data = asound(), to_s16(frames)
        n, done, ran_dry = len(frames), 0, False
        while done < n:
            r = lib.snd_pcm_writei(self.pcm, ctypes.c_char_p(data[done * 4:]), n - done)
            if r == -errno.EAGAIN:
                continue
            if r < 0:
                if r == -errno.EPIPE:
                    self.underruns += 1
                    ran_dry = True
                self._check(lib.snd_pcm_recover(self.pcm, int(r), 1), "recover")
                continue
            done += r
        self.written += n
        if self.written < self.buffer:  # not started yet
            return 0
        a = self.ahead()
        if a is None:
            return 0
        est = time.monotonic() + a - self.written / self.rate
        if self.started_at is None:
            self.started_at = est
            return 0
        if ran_dry:  # it restarted when full again: frames from here on are heard this much later
            gap = max(0, int(round((est - self.started_at) * self.rate)))
            self.gaps.append((self.written - n, gap))
            self.written += gap
            self.started_at = est - gap / self.rate
            return gap
        self.residuals.append(est - self.started_at)
        self.started_at += 0.01 * (est - self.started_at)
        return 0

    @property
    def underrun_frames(self) -> int:
        return sum(n for _, n in self.gaps)

    def ahead(self) -> float | None:
        d = ctypes.c_long(0)
        if asound().snd_pcm_delay(self.pcm, ctypes.byref(d)) < 0:
            return None
        return d.value / self.rate

    def latency(self) -> float:
        return (self.buffer or self.want[1]) / self.rate  # what it got; before it opens, what it asks for

    def granted(self) -> dict:
        r = np.asarray(self.residuals[100:] or [0.0])
        return {"period": self.period, "buffer": self.buffer, "period_ms": 1000 * self.period / self.rate,
                "buffer_ms": 1000 * self.buffer / self.rate, "asked": self.want,
                "clock_spread_ms": [1000 * float(np.percentile(r, 1)), 1000 * float(np.percentile(r, 99))]}

    def close(self) -> None:
        if self.pcm is not None:
            asound().snd_pcm_drop(self.pcm)
            asound().snd_pcm_close(self.pcm)
            self.pcm = None


class PacedOutput(Output):
    """No device: a buffer of `buffer` frames that a device clock (the monotonic clock) empties at `rate`, starting
    when it is first full, as an ALSA device does. `write` waits for room. What is played is kept in `capture`
    (a 16-bit WAV, as a device would get it) with the silence of any underrun, so the capture's frame n is the one
    the device played at `started_at + n / rate`."""

    def __init__(self, rate: int, buffer: int, capture: Path | None = None, realtime: bool = True):
        self.rate, self.buffer, self.capture = rate, buffer, capture
        self.realtime = realtime  # False: no waiting, as fast as the writer goes (tests)
        self.written = 0  # frames the writer has given, silence of underruns included
        self.started_at: float | None = None
        self.underruns = 0
        self.underrun_frames = 0
        self.gaps: list[tuple[int, int]] = []  # (frame the silence began at, its frames)
        # for each block, from the moment the one before could go in to the moment this one came (s): the
        # writer's compute and its wake-up. It ran dry where that exceeded the buffer, so the largest of these is
        # the smallest buffer the run would have kept fed.
        self.responses: list[float] = []
        self._room_at: float | None = None
        self._wav = None
        self._q: queue.SimpleQueue | None = None  # the capture's 16-bit frames, for its writer thread
        self._writer: threading.Thread | None = None
        self._pending: list[np.ndarray] = []  # frames written before the start

    def open(self) -> None:
        if self.capture is not None:
            self._wav = wave.open(str(self.capture), "wb")
            self._wav.setnchannels(2)
            self._wav.setsampwidth(2)
            self._wav.setframerate(self.rate)
            self._q = queue.SimpleQueue()
            self._writer = threading.Thread(target=self._write_capture, daemon=True, name="capture-writer")
            self._writer.start()

    def _write_capture(self) -> None:
        while (data := self._q.get()) is not None:
            self._wav.writeframes(data)

    def played(self, now: float | None = None) -> float:
        """Frames the device has played by `now` (fractional)."""
        if self.started_at is None:
            return 0.0
        return ((time.monotonic() if now is None else now) - self.started_at) * self.rate

    def write(self, frames: np.ndarray) -> int:
        n = len(frames)
        if not self.realtime:
            self.started_at = self.started_at or time.monotonic()
            self._keep(frames)
            self.written += n
            return 0
        if self.started_at is None:
            self._keep(frames)
            self.written += n
            if self.written >= self.buffer:
                self.started_at = time.monotonic()
            return 0
        now = time.monotonic()
        if self._room_at is not None:
            self.responses.append(now - self._room_at)
        played = self.played(now)
        gap = 0
        if played > self.written:  # ran dry: the device played silence until now
            gap = int(np.ceil(played - self.written))
            self.underruns += 1
            self.underrun_frames += gap
            self.gaps.append((self.written, gap))
            self._keep(np.zeros((gap, 2), dtype=np.float32))
            self.written += gap
        room_at = self.started_at + (self.written + n - self.buffer) / self.rate
        while True:  # wait for room
            wait = room_at - time.monotonic()
            if wait <= 0:
                break
            time.sleep(wait)
        self._room_at = room_at
        self._keep(frames)
        self.written += n
        return gap

    def _keep(self, frames: np.ndarray) -> None:
        if self._q is not None:
            self._q.put(to_s16(frames))

    def ahead(self) -> float | None:
        if self.started_at is None:
            return self.written / self.rate
        return max(0.0, self.written - self.played()) / self.rate

    def latency(self) -> float:
        return self.buffer / self.rate

    def granted(self) -> dict:
        r = np.asarray(self.responses or [0.0])
        return {"buffer": self.buffer, "buffer_ms": 1000 * self.buffer / self.rate,
                "response_ms": {"median": 1000 * float(np.median(r)), "p99": 1000 * float(np.percentile(r, 99)),
                                "p99.9": 1000 * float(np.percentile(r, 99.9)), "max": 1000 * float(r.max()),
                                "n": len(self.responses)}}

    def close(self) -> None:
        if self._writer is not None:
            self._q.put(None)
            self._writer.join()
            self._writer, self._q = None, None
        if self._wav is not None:
            self._wav.close()
            self._wav = None


def make_output(kind: str, device: str, rate: int, buffer_ms: float, period_ms: float | None = None,
                capture: Path | None = None) -> Output:
    """The output the config names. `period_ms`: the device's period (alsa; default a quarter of the buffer)."""
    buffer = max(1, int(round(buffer_ms * rate / 1000)))
    if kind == "aplay":
        return AplayOutput(device, rate, int(round(buffer_ms)))
    if kind == "alsa":
        period = max(1, int(round((period_ms or buffer_ms / 4) * rate / 1000)))
        return AlsaOutput(device, rate, period, max(2, int(round(buffer / period))))
    if kind == "paced":
        return PacedOutput(rate, buffer, capture)
    raise OutputError(f"no output called {kind!r}: aplay, alsa or paced")
