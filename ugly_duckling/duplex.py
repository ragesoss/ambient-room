"""The band's device, both ways on one clock: the band out and the player in, through one output object that the
band engine (`ambient/bandengine.py`) writes to in its own process.

Each `write` plays a block (the engine's) and then takes whatever the capture has (never waiting for it), so the
capture is read every engine block (2.7 ms at 128 frames), in the process that keeps the device fed. What it
captured goes into a `Ring` in shared memory, which the service's listening reads at its own pace: the input
(the chosen channels mixed to mono) and the device's own return of what it played (its loopback channels).

The ring's frame n is the capture's frame n: after a capture overrun the frames lost are put back as silence, so
its index stays the device's sample count. The engine's frame m is the playback's frame m (the engine moves its
clock on after an underrun, `BandEngine._skip`). Both counts run on the device's one sample clock, so they differ
by a constant, `L`:

    the capture frame that holds the device's return of playback frame m is m + L.

`L` is estimated after every block from the two streams' delays as the driver reports them (`snd_pcm_delay`: the
playback frame being played now, and the capture frame being captured now), and the median of the last
`ESTIMATES` goes in the ring's header. The service times the count-in's clicks in the loopback channels to measure
it exactly (`ugly_duckling/session.py`).

Two kinds:

- `AlsaDuplex`: an ALSA device (the 18i8: the band to PCM 1-2 through `plughw`, 16-bit stereo; the capture of all
  its channels through `hw`, 32-bit). Playback and capture use the same period and the same number of periods:
  the 18i8's playback is clocked by its capture (implicit feedback), and the kernel holds the two to the same
  period and buffer once one is open.
- `FileDuplex`: no device. The playback keeps a sound card's pace (`PacedOutput`) and the capture is a recorded
  take, given as if it came from the device, at the same pace; its loopback is what was played, `latency` frames
  later. For the desktop and the tests: the whole loop runs, nothing is heard.
"""

from __future__ import annotations

import ctypes
import errno
import time
from collections import deque
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

from ambient.output import AlsaOutput, Output, OutputError, PacedOutput, asound

ESTIMATES = 256  # L is the median of this many blocks' estimates
CHANNELS = 3  # the ring's: 0 the input followed, 1 the loopback, 2 the room mic

# the ring's header: float64 slots
H_WRITE, H_L, H_OVERRUNS, H_INSERTED, H_PLAY_PERIOD, H_PLAY_BUFFER, H_CAP_PERIOD, H_CAP_BUFFER, H_FILE_START, \
    H_L_SPREAD, H_N_EST, H_LEVEL = range(12)
HEADER = 16


class Ring:
    """Captured frames in shared memory: `channels` float32 channels (0 the input, mono; 1 the loopback; 2 the room
    mic), `frames`
    of them, written by one process (`write`) and read by another (`read`). The header (float64) holds the frames
    written in all and the clock's estimate (module docstring)."""

    def __init__(self, frames: int, channels: int = CHANNELS, name: str | None = None):
        self.frames, self.channels = frames, channels
        size = 8 * HEADER + 4 * frames * channels
        if name is None:
            self.shm = shared_memory.SharedMemory(create=True, size=size)
            self.owner = True
        else:
            try:  # a reader or writer that did not make it: not the resource tracker's to remove (3.13)
                self.shm = shared_memory.SharedMemory(name=name, track=False)
            except TypeError:
                self.shm = shared_memory.SharedMemory(name=name)
            self.owner = False
        self.name = self.shm.name
        self.header = np.ndarray((HEADER,), dtype=np.float64, buffer=self.shm.buf)
        self.data = np.ndarray((frames, channels), dtype=np.float32, buffer=self.shm.buf, offset=8 * HEADER)
        if self.owner:
            self.header[:] = 0.0
            self.header[H_L] = np.nan
            self.header[H_FILE_START] = np.nan  # no take yet

    @property
    def written(self) -> int:
        return int(self.header[H_WRITE])

    def write(self, block: np.ndarray) -> None:
        """Frames (n, channels) after those before."""
        w, total = self.written, len(block)
        if total == 0:
            return
        block = block[-self.frames:]
        n = len(block)
        a = (w + total - n) % self.frames
        k = min(n, self.frames - a)
        self.data[a: a + k] = block[:k]
        if k < n:
            self.data[: n - k] = block[k:]
        self.header[H_WRITE] = w + total

    def read(self, a: int, b: int) -> np.ndarray:
        """A copy of frames a..b (b at most `written`; a no more than `frames` behind it)."""
        w = self.written
        if b > w or a < w - self.frames:
            raise ValueError(f"frames {a}..{b} are not in the ring (written {w}, holds {self.frames})")
        n = b - a
        i = a % self.frames
        k = min(n, self.frames - i)
        out = np.empty((n, self.channels), dtype=np.float32)
        out[:k] = self.data[i: i + k]
        if k < n:
            out[k:] = self.data[: n - k]
        return out

    def close(self) -> None:
        self.header = self.data = None
        self.shm.close()
        if self.owner:
            try:
                self.shm.unlink()
            except FileNotFoundError:
                pass


class _Estimates:
    """L from each block's estimate: the median of the last `ESTIMATES`, and their spread, into the header."""

    def __init__(self, ring: Ring):
        self.ring = ring
        self.values: deque = deque(maxlen=ESTIMATES)

    def add(self, est: float) -> None:
        self.values.append(est)
        v = np.fromiter(self.values, dtype=float)
        h = self.ring.header
        h[H_L] = float(np.median(v))
        h[H_L_SPREAD] = float(np.percentile(v, 90) - np.percentile(v, 10)) if len(v) > 4 else np.nan
        h[H_N_EST] = len(v)

    def reset(self, value: float) -> None:
        self.values.clear()
        self.values.append(value)


def _capture_lib():
    """alsa-lib with the capture side's functions declared too."""
    lib = asound()
    vp, ci, cl, cul = ctypes.c_void_p, ctypes.c_int, ctypes.c_long, ctypes.c_ulong
    for fn, res, args in (("snd_pcm_readi", cl, [vp, vp, cul]), ("snd_pcm_start", ci, [vp]),
                          ("snd_pcm_prepare", ci, [vp]), ("snd_pcm_avail_update", cl, [vp])):
        f = getattr(lib, fn)
        f.restype, f.argtypes = res, args
    return lib


class AlsaDuplex(Output):
    """The band out on `playback` (16-bit stereo, as `AlsaOutput`) and every channel of `capture` in (32-bit), on
    one device: `inputs` (capture channels, from 0) mixed to the ring's input, `loopback` (the device's return of
    its playback) to its second channel."""

    S32_LE, RW_INTERLEAVED = 10, 3

    def __init__(self, ring: str, ring_frames: int, playback: str, capture: str, rate: int, period: int,
                 periods: int, channels: int, inputs: list[int], loopback: list[int], room: list[int] | None = None):
        self.ring = Ring(ring_frames, CHANNELS, ring)
        self.play = AlsaOutput(playback, rate, period, periods)
        self.capture_device, self.rate, self.want = capture, rate, (period, period * periods)
        self.channels, self.inputs, self.loopback = channels, list(inputs), list(loopback)
        self.room = list(room or [])
        self.cap = None
        self.cap_period = self.cap_buffer = 0
        self.read_total = 0  # capture frames put in the ring, with the silence put back after overruns
        self.overruns = 0
        self.inserted = 0  # frames of silence put back after overruns
        self.est = _Estimates(self.ring)
        self.lost_pending = False
        self.buf: np.ndarray | None = None
        self.level = 0.0  # the input's peak since the header last had it

    # the output's outside: the playback's
    @property
    def underruns(self) -> int:
        return self.play.underruns

    @property
    def started_at(self):
        return self.play.started_at

    @property
    def gaps(self):
        return self.play.gaps

    @property
    def underrun_frames(self) -> int:
        return self.play.underrun_frames

    def latency(self) -> float:
        return self.play.latency()

    def ahead(self):
        return self.play.ahead()

    def granted(self) -> dict:
        g = dict(self.play.granted())
        g.update({"capture_period": self.cap_period, "capture_buffer": self.cap_buffer,
                  "capture_overruns": self.overruns, "inserted": self.inserted})
        return g

    def _check(self, r: int, what: str) -> None:
        if r < 0:
            raise OutputError(f"{self.capture_device}: {what}: {asound().snd_strerror(r).decode()}")

    def open(self) -> None:
        self.play.open()
        try:
            self._open_capture()
        except Exception:
            self.play.close()
            raise
        h = self.ring.header
        h[H_PLAY_PERIOD], h[H_PLAY_BUFFER] = self.play.period, self.play.buffer
        h[H_CAP_PERIOD], h[H_CAP_BUFFER] = self.cap_period, self.cap_buffer

    def _open_capture(self) -> None:
        lib = _capture_lib()
        pcm = ctypes.c_void_p()
        self._check(lib.snd_pcm_open(ctypes.byref(pcm), self.capture_device.encode(), 1, 1), "could not open")
        self.cap = pcm
        hw = ctypes.c_void_p()
        lib.snd_pcm_hw_params_malloc(ctypes.byref(hw))
        try:
            self._check(lib.snd_pcm_hw_params_any(pcm, hw), "no configuration")
            lib.snd_pcm_hw_params_set_rate_resample(pcm, hw, 0)
            self._check(lib.snd_pcm_hw_params_set_access(pcm, hw, self.RW_INTERLEAVED), "access")
            self._check(lib.snd_pcm_hw_params_set_format(pcm, hw, self.S32_LE), "32-bit")
            self._check(lib.snd_pcm_hw_params_set_channels(pcm, hw, self.channels), f"{self.channels} channels")
            self._check(lib.snd_pcm_hw_params_set_rate(pcm, hw, self.rate, 0), f"{self.rate} Hz")
            # the playback's period and buffer (module docstring)
            period = ctypes.c_ulong(self.play.period or self.want[0])
            buf, d = ctypes.c_ulong(self.play.buffer or self.want[1]), ctypes.c_int(0)
            self._check(lib.snd_pcm_hw_params_set_period_size_near(pcm, hw, ctypes.byref(period), ctypes.byref(d)),
                        "period")
            self._check(lib.snd_pcm_hw_params_set_buffer_size_near(pcm, hw, ctypes.byref(buf)), "buffer")
            self._check(lib.snd_pcm_hw_params(pcm, hw), "parameters")
            lib.snd_pcm_hw_params_get_period_size(hw, ctypes.byref(period), ctypes.byref(d))
            lib.snd_pcm_hw_params_get_buffer_size(hw, ctypes.byref(buf))
            self.cap_period, self.cap_buffer = period.value, buf.value
        finally:
            lib.snd_pcm_hw_params_free(hw)
        self.buf = np.empty((self.cap_buffer, self.channels), dtype=np.int32)
        self._check(lib.snd_pcm_start(pcm), "start")

    def write(self, frames: np.ndarray) -> int:
        gap = self.play.write(frames)
        self._read()
        self._estimate()
        return gap

    def _read(self) -> None:
        lib = _capture_lib()
        while True:
            r = lib.snd_pcm_readi(self.cap, self.buf.ctypes.data, self.cap_buffer)
            if r == -errno.EAGAIN or r == 0:
                return
            if r < 0:
                if r == -errno.EPIPE:  # an overrun: frames were lost; put back as silence once L says how many
                    self.overruns += 1
                    self.ring.header[H_OVERRUNS] = self.overruns
                    self.lost_pending = True
                    self._check(lib.snd_pcm_prepare(self.cap), "recover")
                    self._check(lib.snd_pcm_start(self.cap), "restart")
                    continue
                self._check(int(r), "read")
            x = self.buf[:r]
            scale = 1.0 / 2 ** 31
            block = np.empty((r, CHANNELS), dtype=np.float32)
            block[:, 0] = x[:, self.inputs].mean(axis=1) * scale if self.inputs else 0.0
            block[:, 1] = x[:, self.loopback].mean(axis=1) * scale if self.loopback else 0.0
            block[:, 2] = x[:, self.room].mean(axis=1) * scale if self.room else 0.0
            self.level = max(self.level, float(np.abs(block[:, 0]).max()))
            self.ring.header[H_LEVEL] = self.level
            self.ring.write(block)
            self.read_total += r

    def _estimate(self) -> None:
        if self.play.written < self.play.buffer:  # the playback has not started
            return
        dp, dc = ctypes.c_long(0), ctypes.c_long(0)
        lib = asound()
        if lib.snd_pcm_delay(self.play.pcm, ctypes.byref(dp)) < 0 or lib.snd_pcm_delay(self.cap, ctypes.byref(dc)) < 0:
            return
        est = (self.read_total + dc.value) - (self.play.written - dp.value)
        h = self.ring.header
        if self.lost_pending and not np.isnan(h[H_L]):
            lost = int(round(h[H_L] - est))
            if lost > 0:
                self.ring.write(np.zeros((lost, CHANNELS), dtype=np.float32))
                self.read_total += lost
                h[H_INSERTED] += lost
                self.inserted += lost
                est += lost
            self.est.reset(h[H_L])
            self.lost_pending = False
        self.est.add(est)

    def close(self) -> None:
        if self.cap is not None:
            lib = asound()
            lib.snd_pcm_drop(self.cap)
            lib.snd_pcm_close(self.cap)
            self.cap = None
        self.play.close()
        self.ring.close()


class FileDuplex(Output):
    """No device (module docstring): the band into a `PacedOutput` (nothing heard), the capture a recorded take.
    The take's sample 0 is the capture's frame `header[H_FILE_START]` (set by the service; until then, and after
    the take, room tone: noise at the level of the take's first 0.2 s, so that the take does not start out of
    digital silence, a step the beat follower hears as an attack; a real room is never silent). The loopback is the
    band's mix, `latency` frames after it played. The header's estimate of L is off by `bias` frames, as a driver's
    delays are, so the clicks' timing has something to correct."""

    def __init__(self, ring: str, ring_frames: int, rate: int, buffer: int, audio: str, channel: int | None = None,
                 latency: int = 300, bias: int = 37, capture: str | None = None, room_ir: str = "",
                 room_gain_db: float = 0.0, take_gain: float = 1.0, take_seconds: float = 0.0, take_bar1_s: float = 0.0):
        self.ring = Ring(ring_frames, CHANNELS, ring)
        self.paced = PacedOutput(rate, buffer, Path(capture) if capture else None)
        self.rate, self.latency_frames, self.bias = rate, int(latency), int(bias)
        self.audio_path, self.channel = audio, channel
        self.y = np.zeros(0, dtype=np.float32)
        self.played = np.zeros(1 << 20, dtype=np.float32)  # the band's mix by engine frame, mod its length
        self.cap = 0  # capture frames given
        self.est = _Estimates(self.ring)
        self.tone = 0.0  # the room tone's rms
        self.rng = np.random.default_rng(0)
        self.take_gain, self.take_seconds, self.take_bar1_s = float(take_gain), float(take_seconds), float(take_bar1_s)
        self.room = None  # the band through the room (`Convolver`), and what it gave, by engine frame
        if room_ir:
            ir = load_ir(room_ir, rate) * 10 ** (room_gain_db / 20)
            self.room = Convolver(ir, 128)
            self.room_out = np.zeros(1 << 20, dtype=np.float32)
            self.room_pos = 0  # engine frames given to the room
            self.room_in: list[np.ndarray] = []

    @property
    def underruns(self) -> int:
        return self.paced.underruns

    @property
    def started_at(self):
        return self.paced.started_at

    @property
    def gaps(self):
        return self.paced.gaps

    @property
    def underrun_frames(self) -> int:
        return self.paced.underrun_frames

    def latency(self) -> float:
        return self.paced.latency()

    def ahead(self):
        return self.paced.ahead()

    def granted(self) -> dict:
        return dict(self.paced.granted(), simulated_L=self.latency_frames)

    def open(self) -> None:
        self.y = (load_audio(self.audio_path, self.rate, self.channel) if self.audio_path
                  else np.zeros(0, dtype=np.float32))
        head = self.y[: int(0.2 * self.rate)]
        self.tone = float(np.sqrt(np.mean(head.astype(np.float64) ** 2))) if len(head) else 0.0
        if self.take_seconds > 0:
            self.y = self.y[: int((self.take_bar1_s + self.take_seconds) * self.rate)]
        self.y = (self.y * self.take_gain).astype(np.float32)
        self.paced.open()
        h = self.ring.header
        h[H_PLAY_BUFFER] = h[H_CAP_BUFFER] = self.paced.buffer

    def write(self, frames: np.ndarray) -> int:
        w0 = self.paced.written
        gap = self.paced.write(frames)
        mono = frames.mean(axis=1)
        n = len(self.played)
        for k in range(gap):  # silence played in an underrun
            self.played[(w0 + k) % n] = 0.0
        idx = (w0 + gap + np.arange(len(frames))) % n
        self.played[idx] = mono
        if self.room is not None:  # the room hears what was played, in order, silence in an underrun too
            if gap:
                self.room_in.append(np.zeros(gap, dtype=np.float32))
            self.room_in.append(mono.astype(np.float32))
            pend = np.concatenate(self.room_in)
            B = self.room.block
            k = len(pend) // B * B
            for a in range(0, k, B):
                out = self.room.push(pend[a: a + B])
                j = (self.room_pos + np.arange(B)) % len(self.room_out)
                self.room_out[j] = out
                self.room_pos += B
            self.room_in = [pend[k:]] if k < len(pend) else []
        if self.paced.started_at is None:
            return gap
        upto = int(self.paced.played()) + self.latency_frames
        if upto > self.cap:
            self._give(self.cap, upto)
        self.est.add(self.latency_frames + self.bias)
        return gap

    def _give(self, a: int, b: int) -> None:
        c = np.arange(a, b)
        block = np.zeros((b - a, CHANNELS), dtype=np.float32)
        if self.tone > 0:
            block[:, 0] = self.tone * self.rng.standard_normal(b - a)
        start = self.ring.header[H_FILE_START]
        if not np.isnan(start):  # (before frame 0 too: the take's start already gone by)
            start = int(start)
            i = c - start
            ok = (i >= 0) & (i < len(self.y))
            block[ok, 0] = self.y[i[ok]]
        e = c - self.latency_frames
        ok = (e >= 0) & (e < self.paced.written) & (e > self.paced.written - len(self.played))
        block[ok, 1] = self.played[e[ok] % len(self.played)]
        if self.room is not None:
            ok = (e >= 0) & (e < self.room_pos) & (e > self.room_pos - len(self.room_out))
            block[ok, 0] += self.room_out[e[ok] % len(self.room_out)]
        block[:, 2] = block[:, 0]  # the room mic: here the same room as the input
        if len(block):
            self.ring.header[H_LEVEL] = max(self.ring.header[H_LEVEL], float(np.abs(block[:, 0]).max()))
        self.ring.write(block)
        self.cap = b

    def close(self) -> None:
        self.paced.close()
        self.ring.close()


class Convolver:
    """A long impulse response applied a block at a time (uniformly partitioned overlap-save): each block's output
    is the response to everything given so far, with no delay of its own."""

    def __init__(self, h: np.ndarray, block: int):
        self.block = B = int(block)
        P = max(1, int(np.ceil(len(h) / B)))
        hp = np.zeros(P * B)
        hp[: len(h)] = h
        self.H = np.fft.rfft(np.concatenate([hp.reshape(P, B), np.zeros((P, B))], axis=1), axis=1)
        self.X = np.zeros_like(self.H)
        self.prev = np.zeros(B)

    def push(self, x: np.ndarray) -> np.ndarray:
        X0 = np.fft.rfft(np.concatenate([self.prev, x]))
        self.prev = np.asarray(x, dtype=float).copy()
        self.X = np.roll(self.X, 1, axis=0)
        self.X[0] = X0
        return np.fft.irfft(np.einsum("pk,pk->k", self.H, self.X))[self.block:].astype(np.float32)


def load_ir(path: str, rate: int) -> np.ndarray:
    p = Path(path).expanduser()
    if p.suffix == ".npy":
        return np.load(p).astype(np.float64)
    return load_audio(str(p), rate).astype(np.float64)


def load_audio(path: str, rate: int, channel: int | None = None) -> np.ndarray:
    """A recorded take at `rate`, mono (its `channel`, or the channels' mean), float32."""
    import soundfile as sf
    y, sr = sf.read(str(Path(path).expanduser()), always_2d=True, dtype="float32")
    y = y[:, channel] if channel is not None else y.mean(axis=1)
    if sr != rate:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=rate)
    return np.ascontiguousarray(y, dtype=np.float32)


def make_alsa_duplex(**kw) -> AlsaDuplex:
    return AlsaDuplex(**kw)


def make_file_duplex(**kw) -> FileDuplex:
    return FileDuplex(**kw)


def wait_for(cond, timeout: float, step: float = 0.005) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()
