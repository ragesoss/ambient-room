"""FluidSynth, through its C library: the SoundFonts played with their own envelopes, filters and velocity layers.

The band's voices (`ambient/bandplayer.py`) are rendered here because that is how the transcription project's
offline render (`tools/band_render.py` there, the `fluidsynth` program) voices them; Csound's `sfplay3m`, which
the ambient voices use, plays a font's samples without its envelopes and filters. Debian's Csound has no
FluidSynth opcodes. The library is Debian's `libfluidsynth3`.

FluidSynth computes 64 frames at a time: a note starts on a 64-frame boundary (1.3 ms at 48 kHz).
"""

from __future__ import annotations

import ctypes
import ctypes.util
from pathlib import Path

import numpy as np

STEP = 64  # FluidSynth's own block (FLUID_BUFSIZE)


class FluidError(Exception):
    pass


_lib = None


def library():
    """libfluidsynth, loaded once."""
    global _lib
    if _lib is None:
        name = ctypes.util.find_library("fluidsynth") or "libfluidsynth.so.3"
        try:
            lib = ctypes.CDLL(name)
        except OSError as e:
            raise FluidError(f"FluidSynth's library is not installed: sudo apt install libfluidsynth3 ({e})")
        vp, ci, cd, cs = ctypes.c_void_p, ctypes.c_int, ctypes.c_double, ctypes.c_char_p
        for fn, res, args in (
                ("new_fluid_settings", vp, []), ("delete_fluid_settings", None, [vp]),
                ("fluid_settings_setnum", ci, [vp, cs, cd]), ("fluid_settings_setint", ci, [vp, cs, ci]),
                ("new_fluid_synth", vp, [vp]), ("delete_fluid_synth", None, [vp]),
                ("fluid_synth_sfload", ci, [vp, cs, ci]), ("fluid_synth_program_change", ci, [vp, ci, ci]),
                ("fluid_synth_noteon", ci, [vp, ci, ci, ci]), ("fluid_synth_noteoff", ci, [vp, ci, ci]),
                ("fluid_synth_all_sounds_off", ci, [vp, ci]),
                ("fluid_synth_write_float", ci, [vp, ci, vp, ci, ci, vp, ci, ci]),
                ("fluid_set_log_function", vp, [ci, vp, vp])):
            f = getattr(lib, fn)
            f.restype, f.argtypes = res, args
        for level in range(5):  # quiet: its warnings would go to the service's log on every start
            lib.fluid_set_log_function(level, None, None)
        _lib = lib
    return _lib


class Synth:
    """One FluidSynth: the fonts loaded in order (a later font's presets win), no reverb or chorus, `gain` as the
    `fluidsynth` program's `-g`. `render(n)` gives n frames, stereo float32; `render_rows` into two rows of an
    array.

    One synth a part, as the offline render has it: parts sharing a synth share its voices, and a voice another
    part used last starts a little differently (the chop's notes up to 0.015 apart after the chords had played,
    2026-10-16), so the sound would no longer be the offline render's to the bit."""

    def __init__(self, fonts: list[Path], rate: int = 48000, gain: float = 0.6):
        lib = self.lib = library()
        self.settings = lib.new_fluid_settings()
        lib.fluid_settings_setnum(self.settings, b"synth.sample-rate", float(rate))
        lib.fluid_settings_setnum(self.settings, b"synth.gain", float(gain))
        lib.fluid_settings_setint(self.settings, b"synth.reverb.active", 0)
        lib.fluid_settings_setint(self.settings, b"synth.chorus.active", 0)
        self.synth = lib.new_fluid_synth(self.settings)
        if not self.synth:
            raise FluidError("FluidSynth did not start")
        for f in fonts:
            if lib.fluid_synth_sfload(self.synth, str(f).encode(), 1) < 0:
                self.close()
                raise FluidError(f"FluidSynth could not load {f}")
        self.rate = rate

    def program(self, chan: int, program: int) -> None:
        self.lib.fluid_synth_program_change(self.synth, chan, program)

    def noteon(self, chan: int, key: int, vel: int) -> None:
        self.lib.fluid_synth_noteon(self.synth, chan, key, max(1, min(127, vel)))

    def noteoff(self, chan: int, key: int) -> None:
        self.lib.fluid_synth_noteoff(self.synth, chan, key)

    def silence(self) -> None:
        for chan in range(16):
            self.lib.fluid_synth_all_sounds_off(self.synth, chan)

    def render(self, n: int, out: np.ndarray | None = None) -> np.ndarray:
        """The next n frames, (n, 2) float32 (into `out` if given)."""
        if out is None:
            out = np.empty((n, 2), dtype=np.float32)
        p = out.ctypes.data
        self.lib.fluid_synth_write_float(self.synth, n, p, 0, 2, p + 4, 0, 2)
        return out

    def render_rows(self, out: np.ndarray, left: int, right: int, a: int = 0, b: int | None = None) -> None:
        """Frames a..b of rows `left` and `right` of `out` (float32, C-contiguous, (rows, n)): the next b - a."""
        b = out.shape[1] if b is None else b
        base, n = out.ctypes.data, out.shape[1]
        self.lib.fluid_synth_write_float(self.synth, b - a, base + 4 * (left * n + a), 0, 1,
                                         base + 4 * (right * n + a), 0, 1)

    def close(self) -> None:
        if getattr(self, "synth", None):
            self.lib.delete_fluid_synth(self.synth)
            self.synth = None
        if getattr(self, "settings", None):
            self.lib.delete_fluid_settings(self.settings)
            self.settings = None
