"""Sampled voices: recordings of real instruments, from SoundFonts.

The fonts live in sounds/ (built by tools/soundfonts; the config's
[sounds] dir says where). A sampled voice keeps its name and plays the same
patterns as any other; if its font is missing, the voice plays its
synthesized model instead (ambient/sounds.py), so nothing breaks.

Csound plays them with sfplay3m at each note's exact frequency (the sample
nearest in pitch, resampled), so just intonation works as for every voice.
Each sampled instrument gets three instrument numbers, one per calling
convention: struck notes (melody, rhythm part, struck chords) at 200 + n,
bass notes at 300 + n, and, for a sample that slides (the dobro), the melody's
notes at 400 + n: held by string (a fraction of the number), tied to slide.
"""

from dataclasses import dataclass
from pathlib import Path

FONTS = {"acoustic": "acoustic.sf2", "generaluser": "generaluser.sf2", "dobro": "dobro.sf2", "upright": "upright.sf2"}


@dataclass(frozen=True)
class Sample:
    font: str
    bank: int
    program: int
    about: str
    # seconds to fade 60 dB, for a plucked recording that settles into a
    # quiet loop (FluidR3's do, 14-30 dB down); None: as recorded
    decay: float | None = None
    # the melody plays it by string: notes ring until their string is picked again, and slide
    # (ambient/conductor.py, Strings); the strings' open notes, highest first
    strings: tuple[int, ...] | None = None


SAMPLES = {
    "fiddle": Sample("acoustic", 0, 110, "Recorded: a fiddle (FluidR3 GM)."),
    # GeneralUser GS's (2026-10-15): its envelopes fall 60 dB in 2.6 s (the banjo) and 6 s (the guitar)
    "banjo": Sample("generaluser", 0, 105, "Recorded: a five-string banjo (GeneralUser GS).", 2.6),
    "steel guitar": Sample("generaluser", 0, 25, "Recorded: a steel-string acoustic guitar (GeneralUser GS).", 6.0),
    "nylon guitar": Sample("acoustic", 0, 24, "Recorded: a nylon-string classical guitar (FluidR3 GM).", 3.5),
    "acoustic bass": Sample("acoustic", 0, 32, "Recorded: an upright bass, plucked (FluidR3 GM).", 3.0),
    "harmonica": Sample("acoustic", 0, 22, "Recorded: a harmonica (FluidR3 GM)."),
    "dobro": Sample("dobro", 0, 25, "Recorded: the player's own Beard squareneck resonator guitar, in open G.",
                    strings=(62, 59, 55, 50, 47, 43)),
    "upright bass": Sample("upright", 0, 32, "Recorded: the player's own upright bass, plucked (through a pickup "
                                             "on its tailpiece)."),
}

# Which voices are sampled: (part, voice) -> sample, and its loudness trim in
# dB: to the same levels as the synthesized voices (ambient/sounds.py), in
# two passes of tools/calibrate on the desktop, 2026-10-11. The guitar and the
# banjo from GeneralUser GS (2026-10-15) at FluidR3's levels, measured alone
# (Boom-chick, Roll) on the same notes; the melody's by the chords' offsets
VOICES = {
    ("melody", "Fiddle"): ("fiddle", 7.6), ("melody", "Banjo"): ("banjo", 23.4),
    ("melody", "Acoustic guitar"): ("steel guitar", 24.3), ("melody", "Nylon guitar"): ("nylon guitar", 25.0),
    ("melody", "Harmonica"): ("harmonica", 20.2), ("melody", "Dobro"): ("dobro", 27.4),
    ("pad", "Acoustic guitar"): ("steel guitar", 24.3), ("pad", "Nylon guitar"): ("nylon guitar", 23.1),
    ("pad", "Banjo"): ("banjo", 25.7),
    ("pulse", "Banjo"): ("banjo", 23.0), ("pulse", "Acoustic guitar"): ("steel guitar", 16.7),
    # the player's own upright (2026-10-15): 6.6 dB under FluidR3's at its trim, Eighths alone, so 16.8 + 6.6
    ("bass", "Upright"): ("upright bass", 23.4),
}

# Melody voices playing phrases, against their scattered level (dB), as PHRASE in ambient/sounds.py
PHRASE: dict[str, float] = {"Fiddle": 9.1, "Banjo": 1.6, "Acoustic guitar": -1.1, "Nylon guitar": 0.1,
                            "Harmonica": 4.7, "Dobro": -2.1}

# What loaded: sample name -> preset index. Set by orchestra(); empty (every
# voice synthesized) until an engine has loaded the fonts.
AVAILABLE: dict[str, int] = {}

STRUCK, BASS, STRUNG = 200, 300, 400
RING_S = 4.0  # a note held by string sounds at most this long (the dobro's samples fade out by 1.2-7.6 s)

_BODIES = f"""
; ---- sampled voices (ambient/samples.py): p1 - {STRUCK} or - {BASS} is the preset ----

; a plucked recording's fade: 60 dB over its decay time (giDecay; 0: as recorded)
opcode Fade, k, i
  iP xin
  iDec = giDecay[iP]
  kD expseg 1, max(iDec, 0.01), 0.001
  xout (iDec > 0 ? kD : 1)
endop

instr {{struck}} ; a sampled note: p4 Hz, p5 level, p6 whose level (Lvl)
  iP = int(p1) - {STRUCK}
  iKey = limit(round(69 + 12 * log2(p4 / 440)), 0, 127)
  iRel = min(0.08, p3 * 0.3)
  kE linseg 1, max(p3 - iRel, 0.01), 1, iRel, 0
  kE = kE * Fade(iP)
  ; mono, placed by us: on the Pi (aarch64, Csound 6.18) the stereo sfplay and
  ; sfplay3 give NaN on the right for zones panned hard left, as FluidR3's
  ; stereo samples are; on the desktop not (tested 2026-10-11; reported as
  ; csound/csound#3403); the mono ones are fine on both
  aS sfplay3m 100, iKey, p5 / 32768, p4, iP, 1
  aL, aR Place aS * kE * Lvl(p6), random:i(0.3, 0.7)
  Send aL, aR, 0.85, 0.6, 0.35
endin

instr {{strung}} ; a sampled note held on a string (p1's fraction): p4 Hz, p5 level, p6 whose level (Lvl), p7 slide-in
  ; (semitones below, 0: none), p8 slide time (s). Held (p3 < 0) until the string is picked again (-p1) or {RING_S:g} s
  ; have passed; a note tied to it (the same p1) slides there from wherever the string is, with no new pick
  iStart = p4 * 2 ^ (-p7 / 12)
  kTarget = p4
  iHalf = max(p8, 0.005) / 3
  tigoto Sounding
  iP = int(p1) - {STRUNG}
  iKey = limit(round(69 + 12 * log2(p4 / 440)), 0, 127)
  iPan random 0.3, 0.7
  kF portk kTarget, iHalf, iStart
  kE linsegr 1, 3600, 1, 0.04, 0
  kAge timeinsts
  aS sfplay3m 100, iKey, p5 / 32768, kF, iP, 1
Sounding:
  if kAge > {RING_S:g} then
    turnoff
  endif
  aL, aR Place aS * kE * Lvl(p6), iPan
  Send aL, aR, 0.85, 0.6, 0.35
endin

instr {{bass}} ; a sampled bass note: p4 Hz, p5 level, p6 attack, p7 release, p8 chord, p9 accent
  iP = int(p1) - {BASS}
  iKey = limit(round(69 + 12 * log2(p4 / 440)), 0, 127)
  kE Env min(p6, 0.02), max(p3 - min(p6, 0.02) - p7, 0.01), p7
  kE = kE * Cut(p8) * Fade(iP)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  aS sfplay3m 100, iKey, p5 / 32768, p4, iP, 1
  aS = aS * kE * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.15, 0
endin
"""


def orchestra(sounds_dir: Path | None) -> str:
    """The Csound code that loads the fonts found in sounds_dir and defines
    the sampled instruments; sets AVAILABLE. Empty if there are none."""
    AVAILABLE.clear()
    if sounds_dir is None:
        return ""
    lines, handles = [], {}
    for name, s in SAMPLES.items():
        path = Path(sounds_dir) / FONTS[s.font]
        if not path.is_file():
            continue
        if s.font not in handles:
            handles[s.font] = f"giSF_{s.font}"
            lines.append(f'{handles[s.font]} sfload "{path}"')
        n = len(AVAILABLE)
        lines.append(f"giSP_{n} sfpreset {s.program}, {s.bank}, {handles[s.font]}, {n}")
        AVAILABLE[name] = n
    if not AVAILABLE:
        return ""
    nums = lambda base: ", ".join(str(base + n) for n in AVAILABLE.values())
    decays = [SAMPLES[name].decay or 0 for name in AVAILABLE]
    lines.append("giDecay[] fillarray " + ", ".join(f"{d:g}" for d in decays))
    strung = [STRUNG + n for name, n in AVAILABLE.items() if SAMPLES[name].strings]
    bodies = _BODIES.replace("{struck}", nums(STRUCK)).replace("{bass}", nums(BASS))
    if strung:
        bodies = bodies.replace("{strung}", ", ".join(map(str, strung)))
    else:  # no strung sample loaded: leave its instrument out
        bodies = bodies[:bodies.index("instr {strung}")] + bodies[bodies.index("instr " + nums(BASS).split(",")[0]):]
    return "\n".join(lines) + "\n" + bodies


def sampled(layer: str, voice: str) -> str | None:
    """The sample a voice plays now, if it is sampled and its font loaded."""
    v = VOICES.get((layer, voice))
    return v[0] if v and v[0] in AVAILABLE else None


def instrument(layer: str, voice: str) -> int | None:
    s = sampled(layer, voice)
    if s is None:
        return None
    return (BASS if layer == "bass" else STRUCK) + AVAILABLE[s]


def strung(layer: str, voice: str) -> tuple[int, tuple[int, ...]] | None:
    """For a melody voice played by string (the dobro): its held instrument and its strings."""
    s = sampled(layer, voice)
    if layer != "melody" or s is None or not SAMPLES[s].strings:
        return None
    return STRUNG + AVAILABLE[s], SAMPLES[s].strings


def trim_db(layer: str, voice: str) -> float:
    return VOICES[(layer, voice)][1]
