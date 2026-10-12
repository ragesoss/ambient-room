"""The sound engine: Csound, computing audio that aplay plays.

Csound's own ALSA output ignores the buffer size on the Pi (it always takes
1024 frames, 21 ms), so Csound hands its audio to this module and aplay
plays it, with the buffer the config asks for. All Csound calls happen in
one thread; other threads queue notes and control changes.
"""

import queue
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

ORC = Path(__file__).parent / "orc" / "ambient.orc"


def init_csound(ctcsound) -> None:
    """Before the first Csound in this process: no signal handlers of its
    own. Csound's catch SIGTERM ("Csound tidy up: Terminated") and keep it
    from the web server, so systemd waited 90 s and killed the service on
    every restart while it had played (seen on the Pi, 2026-10-11)."""
    ctcsound.csoundInitialize(ctcsound.CSOUNDINIT_NO_SIGNAL_HANDLER | ctcsound.CSOUNDINIT_NO_ATEXIT)


def orchestra(sounds_dir: Path | None = None) -> str:
    """The orchestra, with the sampled voices whose SoundFonts are in sounds_dir."""
    from . import samples
    return ORC.read_text() + "\n" + samples.orchestra(sounds_dir)
RATE = 48000
BLOCK = 1024  # frames per Csound buffer


class EngineError(Exception):
    pass


class Engine:
    """Csound into aplay. start() opens the device; stop() releases it."""

    def __init__(self, device: str, buffer_ms: int, gain_db: float, sounds_dir: Path | None = None):
        self.sounds_dir = sounds_dir  # the sampled voices' SoundFonts
        self.device = device
        self.buffer_ms = buffer_ms
        self.gain_db = gain_db
        self.q: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self.now = 0.0  # score time, s: how far Csound has computed
        self.underruns = 0
        self.invalid = 0  # blocks of invalid audio (NaN), silenced
        self.error: str | None = None
        self.channels: dict[str, float] = {}

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def time(self) -> float:
        return self.now

    def latency(self) -> float:
        """How far the score runs ahead of what is heard: aplay's buffer,
        the 16 KB pipe (85 ms), and a Csound block (21 ms)."""
        return self.buffer_ms / 1000 + 0.085 + BLOCK / RATE

    def set(self, name: str, value: float) -> None:
        self.channels[name] = value
        self.q.put(("chn", name, float(value)))

    def note(self, at: float, instr: float, dur: float, *p: float) -> None:
        """A note at score time `at` (from time()); late notes start now."""
        self.q.put(("i", at, [instr, 0.0, dur, *p]))

    def start(self) -> None:
        if self.running:
            return
        try:
            import ctcsound  # only on the machine that plays
        except ImportError:
            raise EngineError("Csound is not installed on this computer: "
                              "sudo apt install csound python3-csound")

        self.error = None
        self.underruns = 0
        self.invalid = 0
        # A new Csound's score starts at 0. Kept from the last run, the time
        # put the conductor's grid (reset just after this) as far ahead as
        # that run was long: only texture played until the clock caught up
        # (seen on the Pi, 2026-10-11).
        self.now = 0.0
        self.stop_flag.clear()
        init_csound(ctcsound)
        cs = ctcsound.Csound()
        cs.setHostImplementedAudioIO(1, BLOCK)
        for o in ("-d", "-m0", "-odac", "-+rtaudio=null", f"-b{BLOCK}", f"-B{BLOCK * 2}"):
            cs.setOption(o)
        cs.createMessageBuffer(False)
        if cs.compileOrc(orchestra(self.sounds_dir)) != 0:
            raise EngineError("the orchestra did not compile:\n" + self._messages(cs))
        cs.readScore("f 0 z\n")
        if cs.start() != 0:
            raise EngineError("Csound did not start:\n" + self._messages(cs))
        aplay = subprocess.Popen(
            ["aplay", "-D", self.device, "-f", "S16_LE", "-r", str(RATE), "-c", "2",
             f"--buffer-time={self.buffer_ms * 1000}", "-t", "raw", "-"],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(0.3)
        if aplay.poll() is not None:
            err = aplay.stderr.read().decode(errors="replace").strip()
            cs.cleanup()
            raise EngineError(f"could not open {self.device}: {err}")
        self._shrink_pipe(aplay.stdin)
        cs.setControlChannel("gain_db", self.gain_db)
        for k, v in self.channels.items():
            cs.setControlChannel(k, v)
        threading.Thread(target=self._read_stderr, args=(aplay,), daemon=True).start()
        self.thread = threading.Thread(target=self._run, args=(cs, aplay), daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop at once (fade first, through the "fade" channel)."""
        self.stop_flag.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.thread = None

    def _run(self, cs, aplay) -> None:
        try:
            while not self.stop_flag.is_set():
                self._drain(cs)
                if cs.performBuffer() != 0:
                    break
                self.now = cs.scoreTime()
                out = cs.outputBuffer()
                if not np.all(np.isfinite(out)):  # never noise to the speakers; say so on the page
                    self.invalid += 1
                    self.error = ("the synthesis gave invalid audio (NaN) and was silenced; "
                                  "Stop and Play starts it again")
                    out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
                pcm = np.clip(out * 32767.0, -32768, 32767).astype("<i2")
                try:
                    aplay.stdin.write(pcm.tobytes())
                except (BrokenPipeError, ValueError):
                    self.error = "the playback device went away"
                    break
        except Exception as e:  # keep the reason for the status
            self.error = f"engine stopped: {e}"
        finally:
            try:
                aplay.stdin.close()
            except OSError:
                pass
            try:
                aplay.wait(timeout=2)
            except subprocess.TimeoutExpired:
                aplay.kill()
            cs.cleanup()

    def _drain(self, cs) -> None:
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                return
            if item[0] == "chn":
                cs.setControlChannel(item[1], item[2])
            else:
                _, at, p = item
                p[1] = max(0.0, at - cs.scoreTime())
                cs.scoreEvent("i", p)

    def _read_stderr(self, aplay) -> None:
        for line in aplay.stderr:
            if b"underrun" in line:
                self.underruns += 1

    @staticmethod
    def _shrink_pipe(f) -> None:
        """A 16 KB pipe (85 ms of audio), so control changes land sooner."""
        try:
            import fcntl
            fcntl.fcntl(f.fileno(), 1031, 16384)  # F_SETPIPE_SZ
        except OSError:
            pass

    @staticmethod
    def _messages(cs) -> str:
        lines = []
        while cs.messageCnt():
            lines.append(cs.firstMessage().rstrip())
            cs.popFirstMessage()
        return "\n".join(lines[-20:])


class FakeEngine(Engine):
    """No sound: keeps time and records notes. For tests and the desktop."""

    def __init__(self, *a, **kw):
        super().__init__("fake", 0, 0.0)
        self.notes: list[tuple] = []
        self.t0: float | None = None

    @property
    def running(self) -> bool:
        return self.t0 is not None

    def time(self) -> float:
        return 0.0 if self.t0 is None else time.monotonic() - self.t0

    def latency(self) -> float:
        return 0.0

    def set(self, name: str, value: float) -> None:
        self.channels[name] = value

    def note(self, at: float, instr: float, dur: float, *p: float) -> None:
        self.notes.append((at, instr, dur, *p))

    def start(self) -> None:
        if self.t0 is None:
            self.t0 = time.monotonic()

    def stop(self) -> None:
        self.t0 = None
