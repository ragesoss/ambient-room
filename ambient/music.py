"""Harmony: keys, scales as sets of tones, chords, tuning, and their names.

A scale is a set of tones above the key note: semitone slots 0-11. Each
tone has one or more pitches: equal-tempered ("ET", 100 cents a half step)
or just ratios from a 5-limit palette, mixed as you like. The named scales
are presets of slots. Names are given the way a musician reads them: notes
spelled in the key, degrees (1 2 ♭3 ...), steps (W W H ...), chords as
Roman numerals and chord symbols.
"""

import math
import random
from fractions import Fraction

KEYS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
LETTERS = "CDEFGAB"
MAJOR = [0, 2, 4, 5, 7, 9, 11]  # semitones of the major scale's degrees

# Presets: id -> (name, degree formula, description). The seven modes run
# from brightest to darkest.
SCALES = {
    "lydian": ("Lydian", "1 2 3 #4 5 6 7", "major with a raised 4th"),
    "major": ("Major (Ionian)", "1 2 3 4 5 6 7", "the major scale"),
    "mixolydian": ("Mixolydian", "1 2 3 4 5 6 b7", "major with a flat 7th"),
    "dorian": ("Dorian", "1 2 b3 4 5 6 b7", "minor with a raised 6th"),
    "minor": ("Natural minor (Aeolian)", "1 2 b3 4 5 b6 b7", "the minor scale"),
    "phrygian": ("Phrygian", "1 b2 b3 4 5 b6 b7", "minor with a flat 2nd"),
    "locrian": ("Locrian", "1 b2 b3 4 b5 b6 b7", "flat 2nd and flat 5th; its home chord is diminished"),
    "major_pentatonic": ("Major pentatonic", "1 2 3 5 6", "five notes of the major scale, no half steps"),
    "minor_pentatonic": ("Minor pentatonic", "1 b3 4 5 b7", "five notes of the minor scale, no half steps"),
    "whole_tone": ("Whole tone", "1 2 3 #4 #5 b7", "six notes a whole step apart; its chords are augmented"),
    "hirajoshi": ("Hirajoshi", "1 2 b3 5 b6", "a Japanese pentatonic scale, with two half steps"),
    "chromatic": ("Chromatic", "1 b2 2 b3 3 4 #4 5 b6 6 b7 7", "all twelve tones"),
}

# The usual name of each slot as a degree of the key.
DEGREES = ["1", "b2", "2", "b3", "3", "4", "#4", "5", "b6", "6", "b7", "7"]

# The 5-limit just ratios offered for each slot, the usual one first.
PALETTE: dict[int, list[Fraction]] = {s: [Fraction(r) for r in rs] for s, rs in {
    0: ["1"],
    1: ["16/15", "25/24", "27/25"],
    2: ["9/8", "10/9"],
    3: ["6/5", "32/27", "75/64"],
    4: ["5/4", "81/64"],
    5: ["4/3", "27/20"],
    6: ["45/32", "64/45", "25/18"],
    7: ["3/2", "40/27"],
    8: ["8/5", "25/16"],
    9: ["5/3", "27/16"],
    10: ["9/5", "16/9"],
    11: ["15/8", "50/27"],
}.items()}
JUST = {s: rs[0] for s, rs in PALETTE.items()}  # the pure interval of each size

RATIO_NAMES = {
    "1/1": "unison", "16/15": "diatonic semitone", "25/24": "chromatic semitone", "27/25": "large semitone",
    "9/8": "major whole tone", "10/9": "minor whole tone", "6/5": "minor third",
    "32/27": "Pythagorean minor third", "75/64": "augmented second", "5/4": "major third",
    "81/64": "Pythagorean major third", "4/3": "perfect fourth", "27/20": "wide fourth",
    "45/32": "augmented fourth", "64/45": "diminished fifth", "25/18": "small tritone",
    "3/2": "perfect fifth", "40/27": "narrow fifth (the wolf)", "8/5": "minor sixth",
    "25/16": "augmented fifth", "5/3": "major sixth", "27/16": "Pythagorean major sixth",
    "9/5": "large minor seventh", "16/9": "small minor seventh", "15/8": "major seventh",
    "50/27": "narrow major seventh",
}


def frac(r: Fraction) -> str:
    return f"{r.numerator}/{r.denominator}"  # 1/1 for the key note, as in just intonation


def cents(r: Fraction) -> float:
    return 1200 * math.log2(float(r))


# ---- tones ----

def _degree(name: str) -> tuple[int, int]:
    """'b3' -> (3, -1): the degree number and its alteration."""
    return int(name.strip("b#")), name.count("#") - name.count("b")


def preset_slots(scale: str) -> list[int]:
    return sorted(MAJOR[n - 1] + alt for n, alt in map(_degree, SCALES[scale][1].split()))


ET = "ET"  # an equal-tempered pitch, as a scale tone: 100 cents per half step
FAMILIES = {
    "equal": ("Equal temperament", "the piano's 12 pitches: equal half steps of 100 cents"),
    "just": ("Just intonation", "pitches as whole-number ratios to the home note (5-limit)"),
}


def offered(slot: int) -> list:
    """The pitches a tone may take: equal-tempered, or one of its just ratios.
    The home note is 1/1 in both."""
    return [Fraction(1)] if slot == 0 else [ET] + PALETTE[slot]


def parse_pitch(p: str):
    return ET if p == ET else Fraction(p)


def pitch_str(p) -> str:
    return ET if p == ET else frac(p)


def pitch_cents(slot: int, p) -> float:
    """A pitch in cents above the home note."""
    return 100.0 * slot if p == ET else cents(p)


def default_tones(slots, family: str = "just") -> dict[str, list[str]]:
    """Each slot at its usual just ratio, or equal-tempered: the form saved
    in the settings."""
    return {str(s): [frac(PALETTE[s][0]) if family == "just" or s == 0 else ET] for s in sorted(slots)}


def parse_tones(tones: dict) -> dict:
    """Saved tones to {slot: pitches}, in the order offered."""
    out = {}
    for k, ps in tones.items():
        s = int(k)
        chosen = {parse_pitch(p) for p in ps}
        out[s] = [p for p in offered(s) if p in chosen]
    return dict(sorted(out.items()))


def check_tones(tones) -> dict[str, list[str]]:
    """Tones from the page, checked and tidied. Raises ValueError."""
    if not isinstance(tones, dict):
        raise ValueError("tones must be an object")
    out = {}
    for k, ps in tones.items():
        try:
            s = int(k)
        except ValueError:
            raise ValueError(f"tone {k!r} is not 0-11")
        if not 0 <= s <= 11:
            raise ValueError(f"tone {k!r} is not 0-11")
        if not isinstance(ps, list) or not ps:
            raise ValueError(f"tone {s} needs at least one pitch")
        chosen = set()
        for p in ps:
            try:
                q = parse_pitch(p)
            except (ValueError, ZeroDivisionError, TypeError):
                q = None
            if q not in offered(s):
                raise ValueError(f"{p!r} is not offered for tone {s}")
            chosen.add(q)
        out[str(s)] = [pitch_str(q) for q in offered(s) if q in chosen]
    out["0"] = ["1/1"]  # the key note is always in the scale
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def slots_of(tones: dict) -> list[int]:
    return sorted(int(k) for k in tones)


def matching_preset(slots: list[int]) -> str | None:
    for s in SCALES:
        if preset_slots(s) == list(slots):
            return s
    return None


def degree_names(slots) -> dict[int, str]:
    """Each slot's degree name, as the scale would spell it."""
    slots = set(slots)
    d = {s: DEGREES[s] for s in range(12)}
    if 6 in slots and 5 in slots and 7 not in slots:
        d[6] = "b5"  # Locrian
    if 8 in slots and 7 not in slots:
        d[8] = "#5"  # whole tone
    return d


def scale_notes(key: str, slots, lo: int, hi: int) -> list[int]:
    """Every MIDI note of the scale from lo to hi, inclusive."""
    root = KEYS.index(key)
    pcs = {(root + s) % 12 for s in slots}
    return [n for n in range(lo, hi + 1) if n % 12 in pcs]


# ---- names ----

def pretty(name: str) -> str:
    """ASCII accidentals to music symbols: 'Bb' -> 'B♭', '#4' -> '♯4'.
    (Note letters are capitals, so a lowercase b is always a flat.)"""
    return name.replace("##", "𝄪").replace("#", "♯").replace("bb", "𝄫").replace("b", "♭")


def spell(key: str, slots) -> dict[int, str]:
    """{pitch class: note name} for every slot, one letter per degree, as a
    musician would write it in this key (E♭ F G♭ A♭ B♭ C♭ D♭)."""
    letter = LETTERS.index(key[0])
    tonic_pc = (MAJOR[letter] + {"#": 1, "b": -1}.get(key[1:2], 0)) % 12
    names = degree_names(slots)
    out = {}
    for s in range(12):
        n, alt = _degree(names[s])
        let = (letter + n - 1) % 7
        pc = (tonic_pc + s) % 12
        acc = (pc - MAJOR[let] + 6) % 12 - 6
        out[pc] = LETTERS[let] + ("#" * acc if acc > 0 else "b" * -acc)
    return out


def note_name(midi: int, names: dict[int, str]) -> str:
    """A MIDI note named from the scale's spelling, with its octave (C4 = 60)."""
    name = names.get(midi % 12) or KEYS[midi % 12]
    # the octave follows the letter: B#3 is MIDI 60, Cb4 is MIDI 59
    acc = name.count("#") - name.count("b")
    return pretty(name) + str((midi - MAJOR[LETTERS.index(name[0])] - acc) // 12 - 1)


STEP_NAMES = {1: "H", 2: "W", 3: "m3", 4: "M3", 5: "P4", 6: "TT", 7: "P5"}


def step_pattern(slots) -> str:
    """The gaps between notes: W (whole step), H (half), m3 (three half steps)."""
    st = sorted(slots) + [12]
    return " ".join(STEP_NAMES.get(b - a, f"{b - a}") for a, b in zip(st, st[1:]))


def describe_scale(key: str, tones: dict) -> dict:
    parsed = parse_tones(tones)
    slots = list(parsed)
    names = spell(key, slots)
    deg = degree_names(slots)
    root = KEYS.index(key)
    preset = matching_preset(slots)
    pitches = [p for s, ps in parsed.items() if s for p in ps]
    if all(p == ET for p in pitches):
        tuning = "equal temperament"
    elif all(p != ET for p in pitches):
        tuning = "just intonation" + ("" if all(ps == [JUST[s]] for s, ps in parsed.items()) else ", your ratios")
    else:
        tuning = "mixed tuning"
    if preset:
        name, about = SCALES[preset][0], SCALES[preset][2]
    else:
        name, about = "Custom", f"{len(slots)} tones of your choice"
    return {
        "preset": preset,
        "name": name,
        "tuning": tuning,
        "about": about,
        "notes": " ".join(pretty(names[(root + s) % 12]) for s in slots),
        "formula": " ".join(pretty(deg[s]) for s in slots),
        "steps": step_pattern(slots),
        "names": {str(pc): pretty(n) for pc, n in names.items()},  # every pitch class, spelled
        "degrees": {str(s): pretty(deg[s]) for s in range(12)},
    }


# ---- chords ----

# How often each slot is chosen as a chord's root, if it is in the scale.
ROOT_WEIGHTS = {0: 4, 1: 1, 2: 1, 3: 1.5, 4: 1.5, 5: 2, 6: 0.7, 7: 2, 8: 1.5, 9: 1.5, 10: 1.5, 11: 0.7}


def pick_root(slots, last: int | None, rng: random.Random) -> int:
    choices = [s for s in slots if s != last] or list(slots)
    return rng.choices(choices, weights=[ROOT_WEIGHTS[s] for s in choices])[0]


def build_chord(key: str, slots, root_slot: int, size: int, rng: random.Random) -> list[int]:
    """Pitch classes of a chord on `root_slot`, root first: thirds stacked
    where the scale has them (either third at random if it has both), else a
    fourth or a second. In a seven-note scale this is every other note."""
    avail, rel, cur = set(slots), [root_slot], root_slot
    while len(rel) < size:
        thirds = [d for d in (3, 4) if (cur + d) % 12 in avail and (cur + d) % 12 not in rel]
        if thirds:
            d = rng.choice(thirds)
        else:
            others = [d for d in (5, 2) if (cur + d) % 12 in avail and (cur + d) % 12 not in rel]
            if not others:
                if len(rel) == 1:  # no third, fourth or second: the most consonant tone the scale has
                    rest = [d for d in (7, 5, 4, 3, 9, 8, 2, 10, 6, 11, 1) if (root_slot + d) % 12 in avail]
                    if rest:
                        rel.append((root_slot + rest[0]) % 12)
                break
            d = others[0]
        cur = (cur + d) % 12
        rel.append(cur)
    k = KEYS.index(key)
    return [(k + r) % 12 for r in rel]


CHORD_SYMBOLS = {
    (0, 4, 7): "", (0, 3, 7): "m", (0, 3, 6): "dim", (0, 4, 8): "aug",
    (0, 2, 7): "sus2", (0, 5, 7): "sus4",
    (0, 4, 7, 11): "maj7", (0, 3, 7, 10): "m7", (0, 4, 7, 10): "7", (0, 3, 6, 10): "m7♭5",
    (0, 3, 6, 9): "dim7", (0, 3, 7, 11): "m(maj7)", (0, 4, 8, 11): "maj7♯5", (0, 4, 8, 10): "7♯5",
    (0, 4, 7, 9): "6", (0, 3, 7, 9): "m6", (0, 2, 4, 7): "add9", (0, 2, 3, 7): "m(add9)",
    (0, 5, 7, 10): "7sus4", (0, 2, 4, 9): "6/9 (no 5)", (0, 2, 5, 10): "9sus4 (no 5)",
    (0, 2, 4, 7, 11): "maj9", (0, 2, 3, 7, 10): "m9", (0, 2, 4, 7, 10): "9", (0, 1, 4, 7, 10): "7♭9",
    (0, 1, 3, 7, 10): "m7♭9", (0, 1, 3, 6, 10): "m7♭5♭9", (0, 2, 3, 6, 10): "m9♭5",
    (0, 2, 4, 6, 11): "maj9♯11 (no 5)", (0, 4, 6, 7, 11): "maj7♯11", (0, 2, 4, 7, 9): "6/9",
    (0, 2, 5, 7, 10): "9sus4", (0, 3, 5, 7, 10): "m7(add11)", (0, 2, 3, 7, 11): "m(maj9)",
    (0, 2, 4, 8, 11): "maj9♯5", (0, 2, 4, 8, 10): "9♯5", (0, 2, 5, 7, 9): "6/9sus4",
    (0, 3, 5, 10): "m7(add11) (no 5)", (0, 3, 5, 8, 10): "m7♭6(add11)", (0, 1, 3, 7): "m(add♭9)",
    (0, 2, 3, 7, 8): "m(add9, ♭6)", (0, 2, 5, 9): "6/9sus4 (no 5)", (0, 4, 7, 9, 11): "maj13 (no 9)",
    (0, 3, 6, 9, 10): "dim7(add♭7)", (0, 3, 7, 8): "m(add♭6)", (0, 4, 7, 8): "(add♭6)",
    (0, 3, 6, 8): "m7♭5 (no 7)", (0, 4, 8, 9): "aug(add6)",
}
CHORD_TONES = {0: "1", 1: "♭9", 2: "9", 3: "♭3", 4: "3", 5: "11", 6: "♯11", 7: "5",
               8: "♭13", 9: "13", 10: "♭7", 11: "7"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]


def identify(pcs: list[int]) -> tuple[int, str | None]:
    """The chord's root and symbol suffix. The bass (pcs[0]) is tried first;
    if its shape has no name, another note may be the root of a known chord
    over that bass (A7 over E: A7/E). (root, None) when nothing matches."""
    for root in [pcs[0]] + pcs[1:]:
        rel = tuple(sorted({(p - root) % 12 for p in pcs}))
        if rel in CHORD_SYMBOLS:
            return root, CHORD_SYMBOLS[rel]
    return pcs[0], None


def chord_symbol(pcs: list[int], names: dict[int, str]) -> str:
    """Cmaj7, Dm9, A7/E; or the root and its chord tones when the shape has
    no common name: E(1 ♭3 11 13)."""
    name = lambda pc: pretty(names.get(pc, KEYS[pc]))
    root, sym = identify(pcs)
    if sym is None:
        rel = sorted({(p - root) % 12 for p in pcs})
        return name(root) + "(" + " ".join(CHORD_TONES[r] for r in rel) + ")"
    return name(root) + sym + ("" if root == pcs[0] else "/" + name(pcs[0]))


def numeral(key: str, slots, pcs: list[int]) -> str:
    """The chord's root as a degree of the key, in the usual Roman form:
    I, ii, ♭III, iv°, ♭VI+ ... (relative to the major scale). Over another
    bass note: I/5 (the bass's degree)."""
    k = KEYS.index(key)
    deg = degree_names(slots)
    root, _ = identify(pcs)
    n, alt = _degree(deg[(root - k) % 12])
    rel = {(p - root) % 12 for p in pcs}
    r = ROMAN[n - 1]
    if 3 in rel and 4 not in rel:
        r = r.lower()
    if {3, 6} <= rel and 7 not in rel:
        r += "°"
    elif {4, 8} <= rel and 7 not in rel:
        r += "+"
    r = pretty("#" * alt if alt > 0 else "b" * -alt) + r
    if root != pcs[0]:
        r += "/" + pretty(deg[(pcs[0] - k) % 12])
    return r


# ---- voicing ----

def voice(pcs: list[int], center: float, prev: list[int] | None) -> list[int]:
    """Place each pitch class in the octave nearest the last chord's notes
    (or the center), within 10 semitones of the center."""
    out = []
    for pc in pcs:
        target = center if not prev else min(prev, key=lambda n: min(abs((n - pc) % 12), abs((pc - n) % 12)))
        cands = [pc + 12 * o for o in range(1, 10) if abs(pc + 12 * o - center) <= 10]
        out.append(min(cands, key=lambda n: (abs(n - target), abs(n - center))))
    return sorted(set(out))


GUITAR = (40, 45, 50, 55, 59, 64)  # a guitar in standard tuning, low E to high E


def guitar_shape(pcs: list[int], max_fret: int = 4) -> list[int] | None:
    """An open-position guitar chord for these pitch classes (root first), low to high: the root
    on the lowest of the E, A and D strings that has it within `max_fret`, the strings below it
    left out, and each string above at its lowest fret (0 to `max_fret`) on a chord tone. G: G2
    B2 D3 G3 B3 G4; C: x32010; D7: xx0212; A7: x02020. None if no low string has the root."""
    if not pcs:
        return None
    root, tones = pcs[0] % 12, {p % 12 for p in pcs}
    for k, low in enumerate(GUITAR[:3]):
        frets = [f for f in range(max_fret + 1) if (low + f) % 12 == root]
        if not frets:
            continue
        shape = [low + frets[0]]
        for string in GUITAR[k + 1:]:
            fs = [f for f in range(max_fret + 1) if (string + f) % 12 in tones]
            if fs:
                shape.append(string + fs[0])
        return shape
    return None


def bass_note(pc: int, lo: int = 36) -> int:
    """The pitch class in the octave from `lo` (C2, 65 Hz) up."""
    return lo + (pc - lo) % 12


# ---- tuning ----

ADAPTIVE = ("each chord is retuned pure around its root: pure thirds and fifths above "
            "the root's pitch. No wolves, but a tone can shift between chords.")


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _near(r: Fraction, semis: int) -> Fraction:
    """The ratio moved by octaves to within a half octave of `semis`."""
    et = 2 ** (semis / 12)
    while r < et / 2 ** 0.5:
        r *= 2
    while r > et * 2 ** 0.5:
        r /= 2
    return r


def _impurity(c: float, root_c: float, semis: int) -> float:
    """How far (cents) the interval root -> tone is from the pure one."""
    d = (c - root_c - 100 * semis + 600) % 1200 - 600 + 100 * semis
    return abs(d - cents(JUST[semis]))


def resolve_pitches(key: str, tones: dict, pcs: list[int], adaptive: bool = False) -> dict[int, tuple[str, float]]:
    """The pitch each slot plays while this chord sounds: {slot: (label,
    cents above the home note)}.

    Each tone plays at its chosen pitch. Where a tone has more than one,
    the chord's notes take the one purest against the chord's root (trying
    each of the root's own pitches). Adaptive: the root at its pitch, each
    next chord note a pure interval above the one below.
    """
    parsed = parse_tones(tones)
    out = {s: (pitch_str(ps[0]), pitch_cents(s, ps[0])) for s, ps in parsed.items()}
    if not pcs:
        return out
    # a note from outside the scale (a borrowed chord's): in a just scale,
    # the just ratios for its slot; in an equal-tempered one, equal temperament
    just = any(p != ET for k, ps in parsed.items() if k for p in ps)
    for pc in pcs:
        slot = (pc - KEYS.index(key)) % 12
        if slot not in parsed:
            parsed[slot] = list(PALETTE[slot]) if just else [ET]
    k = KEYS.index(key)
    rel = [(pc - k) % 12 for pc in pcs]
    root = rel[0]
    roots = parsed.get(root, [ET])
    if adaptive:
        rp = roots[0]
        c, r = pitch_cents(root, rp), (None if rp == ET else rp)
        for a, b in zip(rel, rel[1:]):
            c += cents(JUST[(b - a) % 12])
            if r is not None:
                r = _near(r * JUST[(b - a) % 12], b)
            cn = (c - 100 * b + 600) % 1200 - 600 + 100 * b  # the octave nearest the slot
            out[b] = (frac(r) if r is not None else "pure above ET", cn)
        return out
    best = None
    for rp in roots:
        rc = pitch_cents(root, rp)
        pick, total = {root: (pitch_str(rp), rc)}, 0.0
        for s in rel[1:]:
            semis = (s - root) % 12
            p = min(parsed.get(s, [ET]), key=lambda q: _impurity(pitch_cents(s, q), rc, semis))
            pick[s] = (pitch_str(p), pitch_cents(s, p))
            total += _impurity(pitch_cents(s, p), rc, semis)
        if best is None or total < best[0]:
            best = (total, pick)
    out.update(best[1])
    return out


def freq(midi: int, key: str, pitches: dict[int, tuple[str, float]] | None = None) -> float:
    """A note's frequency: the key note at standard pitch, every other note
    at its pitch above it (equal-tempered if the scale does not say)."""
    root = KEYS.index(key)
    octave, rel = divmod(midi - root, 12)
    c = (pitches or {}).get(rel, (ET, 100.0 * rel))[1]
    return hz(root + 12 * octave) * 2 ** (c / 1200)


def cents_from_equal(slot: int, ratio: Fraction) -> float:
    return cents(ratio) - 100 * slot
