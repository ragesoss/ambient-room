"""Harmony's form: chords that wander, progressions with a direction, or a loop.

Chords are named by scale degree, 1 to 7 (1 is the key's home chord), so a
progression fits any scale: 1-5-6-4 is I-V-vi-IV in major and i-v-VI-iv in
minor. A scale without a degree (a pentatonic has no 4 or 7) uses a degree
with the same job instead.

The scale rules the harmony, with exceptions as Borrowing allows: chords
from the parallel key (iv, ♭VI, ♭VII in major; a major V in minor) and
secondary dominants (V/V, V/vi ...), which lead into the chord after them.
A progression item is a degree (an int) or a borrowed chord's name (a str).

Functional harmony moves by job: home (1, 6, 3), away (4, 2), tension
(5, 7). A cycle ends in a cadence: tension to home (an authentic cadence,
5-1), away to home (plagal, 4-1), a stop on 5 (a half cadence, open like a
question), or now and then 5-6 (deceptive: home, almost).

Chords change on bar lines, each `chord_bars` long, counted from the start
(chord slot 0, 1, 2 ...). A loop's first chord falls on a slot that is a
multiple of its length, a functional cycle's likewise, so they line up with
the melody's phrases, which count bars from the start too.

A loop can be a chart: each chord with its own length in beats (half a
bar, a bar, two ...), and chords written as Roman numerals from the major
scale when the scale does not have them (III and III7 in C: E and E7). A
chart in letter names (Strum Machine's: "| C / | F G |") is read in the
key: parse_chart().

Chord size sets how many notes the chords part plays (0 to 5: none, the
root, root and fifth, a triad, a seventh, a ninth). The harmony itself, which
the melody and bass follow, is always at least a triad.
"""

import math
import random
import re

from . import music

STYLES = {
    "Wander": "chords chosen freely from the scale, the home chord most often: no direction",
    "Functional": "progressions with a direction: from home, away, to tension, and home again, in cycles that end in cadences",
    "Loop": "a set progression, repeating",
}

# Loops, as scale degrees
PRESETS = {
    "1-5-6-4": ([1, 5, 6, 4], "the pop progression"),
    "1-6-4-5": ([1, 6, 4, 5], "doo-wop, the '50s progression"),
    "6-4-1-5": ([6, 4, 1, 5], "the pop progression, starting sad"),
    "4-5-3-6": ([4, 5, 3, 6], "the royal road: J-pop, lo-fi"),
    "2-5-1": ([2, 5, 1, 1], "jazz's ii-V-I"),
    "6-2-5-1": ([6, 2, 5, 1], "round the circle of fifths"),
    "1-4": ([1, 4], "two chords: a vamp"),
    "1-4-5-4": ([1, 4, 5, 4], "rock and blues"),
    "1-7-6-7": ([1, 7, 6, 7], "Aeolian rock (in minor: i-VII-VI-VII)"),
    "1-6-3-7": ([1, 6, 3, 7], "epic (in minor: i-VI-III-VII)"),
    "1-7-6-5": ([1, 7, 6, 5], "the Andalusian cadence (in minor)"),
    "Canon": ([1, 5, 6, 3, 4, 1, 4, 5], "Pachelbel's Canon"),
    "1-♭VII-IV-1": ([1, "♭VII", 4, 1], "the Mixolydian rock cadence, borrowing ♭VII"),
    "1-iv-1": ([1, 4, "iv", 1], "IV, then the minor iv: the minor plagal cadence"),
    "1-♭VI-♭VII-1": ([1, "♭VI", "♭VII", 1], "the Mario cadence: borrowed ♭VI and ♭VII"),
}

# Chords from outside the scale: (root, in semitones above the key note;
# quality; what it is). Their notes: QUALITY, in order root, third, fifth,
# seventh, ninth.
BORROWED = {
    "♭II": (1, "maj", "the Neapolitan: a major chord a half step above home"),
    "V/V": (2, "dom", "a secondary dominant: the V of V, leading to V"),
    "♭III": (3, "maj", "from the minor key"),
    "V/vi": (4, "dom", "the V of vi, leading to vi"),
    "iv": (5, "min", "the minor iv, from the minor key"),
    "IV": (5, "maj", "a major IV in a minor key (Dorian)"),
    "V": (7, "dom", "a major V in a minor key: a real dominant (harmonic minor)"),
    "♭VI": (8, "maj", "from the minor key"),
    "V/ii": (9, "dom", "the V of ii, leading to ii"),
    "♭VII": (10, "maj", "from the minor key, or Mixolydian"),
    "I": (0, "maj", "a major home chord in a minor key: a Picardy third"),
    "V/IV": (0, "dom", "the home chord with a flat seventh, leading to IV"),
}
QUALITY = {"maj": [0, 4, 7, 11, 2], "min": [0, 3, 7, 10, 2], "dom": [0, 4, 7, 10, 2]}
LEADS_TO = {"V/V": 5, "V/vi": 6, "V/ii": 2, "V/IV": 4}  # a secondary dominant and the degree it leads into

JOBS = {"home": [1, 6, 3], "away": [4, 2], "tension": [5, 7]}
JOB = {d: job for job, ds in JOBS.items() for d in ds}
# how likely each job is to follow each: away leads to tension, tension home
NEXT_JOB = {"home": {"home": 0.7, "away": 3, "tension": 1}, "away": {"home": 0.5, "away": 0.8, "tension": 3},
            "tension": {"home": 3, "away": 0.4, "tension": 0.6}}
DEGREE_WEIGHT = {1: 3, 6: 2, 3: 1, 4: 3, 2: 2, 5: 4, 7: 1}  # within a job: the common chords more often
SAME_JOB = {1: [6, 3], 2: [4, 6], 3: [6, 5], 4: [2, 6], 5: [7, 3], 6: [3, 4], 7: [5, 2]}
MAX_LOOP = 32
RHYTHM_BARS = [16, 8, 4, 2, 1]  # the harmonic rhythm control's stops: bars a chord


def chord_bars(rhythm: float) -> int:
    """Bars a chord lasts: 16, 8, 4, 2 or 1."""
    return RHYTHM_BARS[min(4, max(0, round(rhythm * 4)))]


ROMAN_RE = re.compile(r"^([b♭#♯]?)(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)(°|ø|\+)?(maj7|7)?$")


def roman(item: str):
    """A chord written as a Roman numeral, counted on the major scale: III7
    is a dominant seventh on the 3rd (E7 in C), ♭VI a major chord on the
    flat 6th, ii° diminished. (root in semitones above the key note, its
    notes as intervals root first, whether its seventh is written); None if
    it is not one."""
    m = ROMAN_RE.match(item)
    if not m:
        return None
    acc, num, mark, sev = m.groups()
    root = (music.MAJOR[music.ROMAN.index(num.upper())] + {"b": -1, "♭": -1, "#": 1, "♯": 1}.get(acc, 0)) % 12
    upper = num.isupper()
    if mark == "°":
        ivs = [0, 3, 6, 9]
    elif mark == "ø":
        ivs = [0, 3, 6, 10]
    elif mark == "+":
        ivs = [0, 4, 8, 10]
    elif upper:
        ivs = [0, 4, 7, 10 if sev == "7" else 11]
    else:
        ivs = [0, 3, 7, 11 if sev == "maj7" else 10]
    return root, ivs + [2], bool(sev) or mark == "ø"


# Any chord on any root: the root counted on the major scale, and a kind.
ROOT_NAMES = {0: "I", 1: "♭II", 2: "II", 3: "♭III", 4: "III", 5: "IV", 6: "♯IV", 7: "V", 8: "♭VI", 9: "VI",
              10: "♭VII", 11: "VII"}
KINDS = {"maj": ("major", False, ""), "min": ("minor", True, ""), "7": ("7", False, "7"), "m7": ("m7", True, "7"),
         "maj7": ("maj7", False, "maj7"), "dim": ("dim", True, "°")}


def any_chord(root: int, kind: str) -> str:
    """The Roman numeral for a chord of this kind on a root (semitones above
    the key note): any_chord(4, "7") is III7 (E7 in C)."""
    _, lower, mark = KINDS[kind]
    name = ROOT_NAMES[root % 12]
    num = name.lstrip("♭♯")
    return name[: len(name) - len(num)] + (num.lower() if lower else num) + mark


def vocabulary(slots) -> list:
    """Every chord a loop can hold, in this scale: its own chords (degrees 1
    to 7; one it lacks has a stand-in), the borrowed ones, and any chord on
    any root. The page's chord picker,
    evolution and the chart reader all draw on it, so whatever one can make,
    the others can reach."""
    return list(range(1, 8)) + list(BORROWED) + [any_chord(r, k) for r in range(12) for k in KINDS]


def chord_of(entry):
    """A loop entry's chord: a degree, a borrowed chord or a Roman numeral."""
    return entry["chord"] if isinstance(entry, dict) else entry


def beats_of(entry) -> float | None:
    """A loop entry's length in beats (None: the harmonic rhythm's)."""
    return entry.get("beats") if isinstance(entry, dict) else None


def valid_chord(item) -> bool:
    if isinstance(item, bool):
        return False
    if isinstance(item, int):
        return 1 <= item <= 7
    return isinstance(item, str) and (item in BORROWED or roman(item) is not None)


def timeline(h: dict) -> tuple[list[tuple[int, int]], int]:
    """A loop's chords in time, in sixteenths: (start, length) for each, and
    the whole loop's length. A chord without a length lasts the harmonic
    rhythm's bars."""
    bar_len = chord_bars(h["rhythm"]) * 16
    out, t = [], 0
    for e in h["loop"]:
        b = beats_of(e)
        n = max(1, round(4 * b)) if b else bar_len
        out.append((t, n))
        t += n
    return out, t


def at_step(h: dict, step: int) -> tuple[int, int, int]:
    """Where a loop is at a sixteenth counted from the start: (chord slot,
    position in the loop, sixteenths left in that chord). Slots count chords
    from the start: (times round) x (chords in the loop) + position."""
    tl, total = timeline(h)
    rnd, p = divmod(step, total)
    for i, (start, n) in enumerate(tl):
        if start <= p < start + n:
            return rnd * len(tl) + i, i, start + n - p
    return rnd * len(tl), 0, tl[0][1]


LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
CHORD_RE = re.compile(r"^([A-G])([#♯b♭]?)(maj7|m7b5|m7|min|m|dim7|dim|°|aug|\+|7|sus4|sus2|sus|6|9|add9)?(?:/[A-G][#♯b♭]?)?$")


def chord_item(name: str, key: str, slots):
    """A chord in letter names (Am, E7, G/D: the bass note after / is left
    out) as a loop item in this key and scale: the scale's own chord as a
    degree, anything else as a Roman numeral. ValueError if not a chord."""
    m = CHORD_RE.match(name.strip())
    if not m:
        raise ValueError(f"not a chord: {name!r}")
    letter, acc, q = m.groups()
    slot = (LETTERS[letter] + {"#": 1, "♯": 1, "b": -1, "♭": -1}.get(acc, 0) - music.KEYS.index(key)) % 12
    q = q or ""
    kind = {"m": "min", "min": "min", "m7": "min", "m7b5": "half", "dim": "dim", "dim7": "dim", "°": "dim",
            "aug": "aug", "+": "aug"}.get(q, "maj")
    seventh = q in ("7", "m7", "maj7", "m7b5", "dim7")
    if not seventh and kind in ("maj", "min") and slot in slots and _triad_quality(slots, slot) == kind:
        d = slot_degree(slots, slot)
        if degree_slot(slots, d) == slot:
            return d  # the scale's own chord
    if slot in music.MAJOR:
        acc, num = "", music.ROMAN[music.MAJOR.index(slot)]
    elif (slot + 1) % 12 in music.MAJOR:
        acc, num = "♭", music.ROMAN[music.MAJOR.index((slot + 1) % 12)]
    else:
        acc, num = "♯", music.ROMAN[music.MAJOR.index(slot - 1)]
    if kind in ("min", "dim", "half"):
        num = num.lower()
    mark = {"dim": "°", "half": "ø", "aug": "+"}.get(kind, "")
    suffix = "maj7" if q == "maj7" else "7" if seventh and kind != "half" else ""
    return acc + num + mark + suffix


def parse_chart(text: str, key: str, slots) -> list:
    """A chart in letter names, bar by bar: "| C / | F G | C / |". A bar's
    chords share it evenly (two: two beats each); "/" carries the chord on.
    Returns loop entries with their lengths in beats."""
    out = []
    for bar in text.replace("\n", "|").split("|"):
        toks = bar.split()
        if not toks:
            continue
        b = 4 / len(toks)
        for tok in toks:
            if tok in ("/", "%", "-", "."):
                if not out:
                    raise ValueError("a chart starts with a chord")
                out[-1][1] += b
            else:
                out.append([chord_item(tok, key, slots), b])
    if not out:
        raise ValueError("no chords in the chart")
    return [{"chord": c, "beats": round(b, 3)} for c, b in out]


def cycle_length(length: float) -> int:
    """Chords per cycle: 2, 4 or 8."""
    return [2, 4, 8][min(2, int(length * 3))]


def played_size(size: float, u: float, plain: bool = False) -> int:
    """Notes the chords part plays: size 0 to 1 is 0 to 5 notes; between
    two counts, a mix of both (u in [0, 1) picks). Plain: 3 at most."""
    x = 5 * size
    n = int(x) + (1 if u < x - int(x) else 0)
    return min(n, 3) if plain else min(n, 5)


def played(pcs: list[int], n: int) -> list[int]:
    """The notes the chords part plays from a chord: none, the root, the
    root and fifth (a power chord), or the first n."""
    if n <= 0:
        return []
    if n == 1:
        return pcs[:1]
    if n == 2:
        return [pcs[0], pcs[2]] if len(pcs) > 2 else pcs[:2]
    return pcs[:n]


def _numbers(slots) -> dict[int, int]:
    """The degree numbers (1-7) the scale has, and each one's slot; where a
    number has two (2 and b2 in a chromatic scale), the plain one."""
    names = music.degree_names(slots)
    out = {}
    for s in sorted(slots, key=lambda s: len(names[s])):
        out.setdefault(int(names[s].strip("b#")), s)
    return out


def degree_slot(slots, degree: int) -> int:
    """The slot a degree's chord stands on: the scale's tone with that
    number, else one with the same job, else the nearest number."""
    have = _numbers(slots)
    for d in [degree] + SAME_JOB.get(degree, []):
        if d in have:
            return have[d]
    return have[min(have, key=lambda n: abs(n - degree))]


def slot_degree(slots, slot: int) -> int:
    return int(music.degree_names(slots)[slot].strip("b#"))


def item_slot(slots, item) -> int:
    """The root slot of a progression item: a degree, a borrowed chord or a Roman numeral."""
    item = chord_of(item)
    if isinstance(item, str):
        return BORROWED[item][0] if item in BORROWED else roman(item)[0]
    return degree_slot(slots, item)


def minorish(slots) -> bool:
    """A minor-like scale: a minor third and no major third."""
    return 3 in slots and 4 not in slots


def _triad_quality(slots, root: int) -> str | None:
    """'maj' or 'min' if the scale's triad on this root is major or minor."""
    rel = {(s - root) % 12 for s in slots}
    if 7 not in rel:
        return None
    return "maj" if 4 in rel and 3 not in rel else "min" if 3 in rel and 4 not in rel else None


def build(key: str, slots, item, size: int, plain: bool, rng: random.Random) -> list[int]:
    """The harmony's chord for a progression item: at least a triad.
    Plain: a major or minor triad, borrowing a note if the scale has none."""
    k = music.KEYS.index(key)
    item = chord_of(item)
    if isinstance(item, str):
        if item in BORROWED:
            root, q, _ = BORROWED[item]
            return [(k + root + i) % 12 for i in QUALITY[q][:3 if plain else max(3, size)]]
        root, ivs, seventh = roman(item)  # a written seventh is always there
        n = 3 if plain else max(3, size)
        return [(k + root + i) % 12 for i in ivs[:max(n, 4) if seventh else n]]
    root = degree_slot(slots, item)
    if plain:
        q = _triad_quality(slots, root)
        if q is None:  # a diminished, augmented or suspended triad: the nearest major or minor one
            q = "min" if (root + 3) % 12 in slots else "maj"
        return [(k + root + i) % 12 for i in QUALITY[q][:3]]
    return music.build_chord(key, slots, root, max(3, size), rng)


def loop_chord(key: str, slots, h: dict, i: int) -> tuple[list[int], int]:
    """A loop's chord at position i, the same every time round: the
    harmony's chord and how many notes of it the chords part plays."""
    item = chord_of(h["loop"][i])
    n = played_size(h["size"], (0.5 + 0.618034 * i) % 1, h["plain"])
    if n >= 3 and written_seventh(item):
        n = max(n, 4)
    seed = random.Random(f"{i}:{item}:{n}")
    return build(key, slots, item, n, h["plain"], seed), n


def written_seventh(item) -> bool:
    return isinstance(item, str) and item not in BORROWED and roman(item) is not None and roman(item)[2]


def numeral(key: str, slots, item) -> str:
    """A progression item as a numeral in this scale. A degree is named from
    the degree it stands on (a stacked chord can spell another chord
    inverted; in a pentatonic scale, V is A-D-F# in D): I, ii, ♭VII, vii°,
    Vsus ... A borrowed chord, by its own name."""
    item = chord_of(item)
    if isinstance(item, str):
        return item
    root = degree_slot(slots, item)
    rel = {(p - root) % 12 for p in music.build_chord("C", slots, root, 3, random.Random(item))}
    name = music.degree_names(slots)[root]
    r = music.ROMAN[int(name.strip("b#")) - 1]
    if 3 in rel and 4 not in rel:
        r = r.lower() + ("°" if 6 in rel and 7 not in rel else "")
    elif 4 in rel and 8 in rel and 7 not in rel:
        r += "+"
    elif 3 not in rel and 4 not in rel:
        r += "sus"
    return music.pretty(name.rstrip("1234567")) + r


def borrowable(slots) -> list[str]:
    """The borrowed chords that are borrowed in this scale: not already its own."""
    out = []
    for name, (root, q, _) in BORROWED.items():
        notes = {(root + i) % 12 for i in QUALITY[q][:3 if q != "dom" else 4]}  # noqa
        if not notes <= set(slots):
            out.append(name)
    return out


LETTERS_UP = [0, 2, 4, 6, 1]  # letters above the root of a chord's tones as built: root, third, fifth, seventh, ninth


def chord_scale(slots, rel_pcs: list[int]) -> list[int]:
    """The scale while a chord sounds: a borrowed chord's note replaces the
    scale's tone of the same letter, the one it alters (over iv in C major,
    A♭ for A; over A7 in G, C♯ for C, and D stays). rel_pcs: the chord's
    tones above the key, as built (root, third, fifth, seventh, ninth). A
    chord tone or the home note is never taken out."""
    out = set(slots)
    names = music.degree_names(slots)
    number = {s: int(n.strip("b#")) for s, n in names.items()}  # each scale tone's degree number (its letter)
    root = rel_pcs[0] if rel_pcs else 0
    root_number = number.get(root, int(music.DEGREES[root].strip("b#")))
    for i, x in enumerate(rel_pcs):
        if x in out:
            continue
        letter = (root_number - 1 + LETTERS_UP[min(i, 4)]) % 7 + 1
        out -= {s for s in out if number.get(s) == letter and s not in rel_pcs and s != 0}
        out.add(x)
    return sorted(out)


class Harmonist:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.reset()

    def reset(self) -> None:
        self.cycle: list = []  # Functional: the cycle being played
        self.cycle_at: int | None = None  # its first chord slot
        self.pending: tuple[int, list] | None = None  # the next cycle, if looked at early
        self.ending = None  # the last cycle's final item
        self.planned: dict[int, object] = {}  # Wander: chords chosen ahead (for a walking bass)
        self.played: dict[int, object] = {}  # chord slot -> item, the last few

    def _functional(self, s: dict, slot: int, slots) -> list:
        h = s["harmony"]
        n = cycle_length(h["length"])
        start = slot - slot % n
        if start != self.cycle_at or len(self.cycle) != n:
            if self.pending and self.pending[0] == start and len(self.pending[1]) == n:
                self.cycle = self.pending[1]
            else:
                self.cycle = self.functional_cycle(n, h["resolve"], slots, h["borrow"], h["plain"])
            self.cycle_at, self.pending = start, None
        return self.cycle

    def peek(self, s: dict, slot: int, last_root: int | None) -> int | None:
        """The root slot of the chord at chord slot `slot`, ahead of time."""
        h, slots = s["harmony"], music.slots_of(s["tones"])
        if h["style"] == "Loop":
            return item_slot(slots, h["loop"][slot % len(h["loop"])])
        if h["style"] == "Functional":
            n = cycle_length(h["length"])
            if self.cycle_at is not None and 0 <= slot - self.cycle_at < len(self.cycle):
                return item_slot(slots, self.cycle[slot - self.cycle_at])
            start = slot - slot % n
            if not self.pending or self.pending[0] != start:
                self.pending = (start, self.functional_cycle(n, h["resolve"], slots, h["borrow"], h["plain"]))
            return item_slot(slots, self.pending[1][slot - start])
        if slot not in self.planned:
            self.planned[slot] = self._wander(s, slots, last_root, None)
        return item_slot(slots, self.planned[slot])

    def next(self, s: dict, slot: int, last_root: int | None, wish: str | None, u: float) -> tuple[int, list[int], int]:
        """The chord for chord slot `slot`: its root's slot, the harmony's
        notes (pitch classes), and how many the chords part plays. `wish` is
        the melody's ('answer' or 'question') when a phrase ends over this
        chord: Wander leans toward a cadence for it."""
        h, rng = s["harmony"], self.rng
        slots = music.slots_of(s["tones"])
        if h["style"] == "Loop":
            i = slot % len(h["loop"])
            pcs, n = loop_chord(s["key"], slots, h, i)
            item = chord_of(h["loop"][i])
        else:
            if h["style"] == "Functional":
                cyc = self._functional(s, slot, slots)
                item = cyc[slot - self.cycle_at]
            else:
                item = self.planned.pop(slot, None)
                if item is None:
                    item = self._wander(s, slots, last_root, wish)
            n = played_size(h["size"], u, h["plain"])
            pcs = build(s["key"], slots, item, n, h["plain"], rng)
        for k in [k for k in self.planned if k <= slot]:
            del self.planned[k]
        self.played[slot] = item
        for k in [k for k in self.played if k <= slot - MAX_LOOP]:
            del self.played[k]
        return item_slot(slots, item), pcs, n

    def _wander(self, s: dict, slots, last_root: int | None, wish: str | None):
        """A free choice, leaning to a cadence under a phrase's last bar;
        now and then, as Borrowing allows, a chord from outside the scale."""
        h, rng = s["harmony"], self.rng
        if h["borrow"] > 0 and rng.random() < 0.35 * h["borrow"]:
            pool = [b for b in borrowable(slots) if b in (("V", "IV", "♭VII", "♭VI", "♭III", "iv")
                                                          if minorish(slots) else ("iv", "♭VI", "♭VII", "♭III", "V/V", "V/vi"))]
            pool = [b for b in pool if BORROWED[b][0] != last_root]
            if pool:
                return rng.choice(pool)
        cands = list(slots)
        if h["plain"]:  # roots whose triad in the scale is major or minor
            cands = [x for x in slots if _triad_quality(slots, x)] or cands
        lean = [0] if wish == "answer" else [7, 5, 2] if wish == "question" else []
        lean = [x for x in lean if x in cands and x != last_root]
        if lean and rng.random() < (0.75 if wish == "answer" else 0.6):
            root = lean[0]
        else:
            root = music.pick_root(cands, last_root, rng)
        return slot_degree(slots, root)

    def functional_cycle(self, n: int, resolve: float, slots, borrow: float = 0.0, plain: bool = False) -> list:
        """n chords, ending in a cadence. Resolution sets how often a cycle
        comes home; after one that ended open, coming home is likelier, so
        cycles pair up as question and answer."""
        rng, prev = self.rng, self.ending
        have = set(_numbers(slots))
        if plain:  # only degrees whose triad is major or minor
            have = {d for d in have if _triad_quality(slots, degree_slot(slots, d))} or have

        def real(d):  # what a degree becomes in this scale
            d = slot_degree(slots, degree_slot(slots, d))
            if d in have:
                return d
            return next((x for x in SAME_JOB.get(d, []) if x in have), d)
        p_home = resolve ** 2 if prev in (1, "I", None) else min(1.0, 0.35 + 1.1 * resolve)
        if rng.random() < p_home:
            r, deceptive = rng.random(), 0.25 * (1 - resolve)
            end = [5, 6] if r < deceptive else [4, 1] if r < deceptive + 0.2 else [5, 1]
        else:  # a half cadence, from away or from home
            end = [rng.choices([4, 2, 1], weights=[0.4, 0.3, 0.3])[0], 5]
        # it opens at home; after a cadence home, sometimes elsewhere, so the tonic is not held across the join
        if prev in (None, 5, 7, "V"):
            opener = 1
        elif prev in (6, "♭VI"):
            opener = rng.choice([4, 2, 1])
        else:
            opener = rng.choices([1, 6, 4], weights=[0.3, 0.35, 0.35])[0]
        if n == 2:
            seq = end if end[1] != 5 else [opener, 5]
            if real(seq[0]) == prev:  # not the same chord across the join: V | V I becomes V | IV I
                seq[0] = {5: 4, 4: 5, 1: 6, 6: 4, 2: 4}.get(seq[0], seq[0])
        else:
            seq = [opener]
            while len(seq) < n - 2:
                job = JOB[seq[-1]]
                after = JOB[end[0]] if len(seq) == n - 3 else None  # the chord before the cadence leads into it
                w = {j: NEXT_JOB[job][j] * (NEXT_JOB[j][after] if after else 1) for j in JOBS}
                job = rng.choices(list(w), weights=list(w.values()))[0]
                ds = [d for d in JOBS[job] if d in have and d != seq[-1]] or JOBS[job]
                seq.append(rng.choices(ds, weights=[DEGREE_WEIGHT[d] for d in ds])[0])
            seq += end
        seq = [real(d) for d in seq]
        # no chord twice in a row: change the one that matters less (never the first or the last)
        for i in range(1, len(seq)):
            if seq[i] != seq[i - 1]:
                continue
            j = i - 1 if 0 < i - 1 < len(seq) - 2 or i == len(seq) - 1 else i
            if j == 0 or j == len(seq) - 1:
                continue
            near = {seq[j - 1], seq[j + 1] if j + 1 < len(seq) else None}
            pref = [5, 4, 2, 7, 6, 3] if j == len(seq) - 2 else rng.sample(sorted(have), len(have))
            seq[j] = next((real(d) for d in pref if real(d) not in near), seq[j])
        if borrow > 0:
            seq = self._borrow(seq, slots, borrow)
        self.ending = seq[-1]
        return seq

    def _borrow(self, seq: list, slots, b: float) -> list:
        """Exceptions to the scale, as Borrowing allows: in minor, a major V
        (the most common); secondary dominants before ii, IV, V and vi; in
        major, the minor iv, a ♭VI for a deceptive vi, ♭VII before I."""
        rng, out = self.rng, list(seq)
        can = set(borrowable(slots))
        minor = minorish(slots)
        for i, d in enumerate(out):
            if i == 0:
                continue
            nxt = out[i + 1] if i + 1 < len(out) else None
            if minor and d == 5 and "V" in can and rng.random() < min(1.0, 2 * b):
                out[i] = "V"
            elif minor and d == 4 and "IV" in can and rng.random() < 0.3 * b:
                out[i] = "IV"
            elif minor and i == len(out) - 1 and d == 1 and "I" in can and rng.random() < 0.15 * b:
                out[i] = "I"  # a Picardy third
            elif not minor and d == 4 and "iv" in can and nxt in (1, None) and rng.random() < 0.5 * b:
                out[i] = "iv"
            elif not minor and d == 6 and i == len(out) - 1 and "♭VI" in can and rng.random() < 0.5 * b:
                out[i] = "♭VI"
            elif not minor and d in (4, 2) and nxt == 1 and "♭VII" in can and rng.random() < 0.25 * b:
                out[i] = "♭VII"
        # a secondary dominant in place of the chord before ii, IV, V or vi
        for i in range(1, len(out) - 1):
            target = out[i + 1]
            sec = {5: "V/V", 6: "V/vi", 2: "V/ii", 4: "V/IV"}.get(target)
            if sec and sec in can and isinstance(out[i], int) and out[i] != 1 and rng.random() < 0.5 * b:
                out[i] = sec
        return out

    def view(self, s: dict, slot: int) -> tuple[list, int]:
        """The progression to show, and where in it chord slot `slot` is:
        the loop, the cycle, or (wandering) the last few chords."""
        h = s["harmony"]
        if h["style"] == "Loop":
            return [chord_of(e) for e in h["loop"]], slot % len(h["loop"])
        if h["style"] == "Functional" and self.cycle_at is not None and 0 <= slot - self.cycle_at < len(self.cycle):
            return list(self.cycle), slot - self.cycle_at
        n = cycle_length(h["length"])
        recent = [self.played[k] for k in range(slot - n + 1, slot + 1) if k in self.played]
        return recent, len(recent) - 1
