"""Breaks on a tune's melody: the tune as written, varied as an improvising bluegrass player varies it, out to the
free line over the chords (2026-10-22; the transcription project's card `ambient-tune-melody`).

The player (2026-10-21): "add a representation of the actual melody to the fiddle tunes that are set, but make it
treat those as an improvising bluegrass musician would: something to vary, iterate on, decorate, and play with (to
varying degrees, from an exact replication of the melody to a completely free melody that only takes the chords
into account (like the current version), but the interesting parts are all in the middle where the melody has a
strong influence but there's also lots of variation and room for surprise)."

**The source.** A tune's melody is its answer key in the transcription project (`tunes/dobro/<tune>/<tune>.musicxml`,
read by that project's score reader with its repeats played out): one pass of the chart the synth plays
(`presets.TUNE_MELODIES`), its notes in the tune's own beats from bar 1's downbeat, each with how it was played
(picked, slid from the note before, slid into, hammered on, pulled off), a double stop's lower note apart. A pickup
into bar 1 (Down Yonder's three notes, Big Sciota's D) is played at the end of the pass, into the next. The chords
are the ones the band plays (the loop's, a beat at a time), so a chord tone is what sounds under the note.

**The phrase.** Four of the tune's bars, within a part (a part's remainder joined to its last phrase: Cherokee
Shuffle's B, 10 bars, is phrases of 4 and 6; a tune whose parts are not given is one part). Its **arrival** is the
longest note in its last bar (the later of two as long): the cadence, where the phrase lands (Red Wing's A over D,
then G); the notes up to two beats before it are its **approach**, those after it lead into the next phrase.
A phrase that plays an earlier one again (three quarters of its notes the same) is a **repeat**.

**The control, the melody's pull** (`pull`): 1 is the tune as written, 0 the free line (the melodist's own phrases
over the chords, `melody.py`: today's line). Its departure `d = 1 - pull` sets how likely each move is
(`BreakParams`); `bell(d) = 4 d (1 - d)`, 1 in the middle and 0 at either end. What a player **keeps**: the notes
on the strong beats (1 and 3 of the tune's bar) up to d 0.3, then fewer; a phrase's first note on its downbeat up to
d 0.7; every arrival and its approach (the cadences and the pickups into them), unless a lick takes their place and
lands on the same note. What they **play with**, each move landing back on the tune by the phrase's end:

- a held note (a beat or more) **filled** in eighths: a chord's notes, a run by step toward the next note, a
  neighbour and back, or (an instrument that rolls) a roll in triplets, three of the chord's notes round again; its
  own note first, the next note reached by step;
- a **passing note changed**: a note of the scale within a fourth, likelier a chord tone or a step into the next
  note, or the chromatic half step into a strong one; never a leap over a fourth, nor the note before again;
- a strong note **substituted** by another tone of its chord (past d 0.3);
- a **rhythm displaced**: a strong note pushed an eighth early, tied over the beat;
- **half a phrase moved an octave** (within the tune's register and a fifth over it, and no further than a sixth
  from the note before it), back for the arrival;
- a **lick at a cadence**: on an arrival at the home note over the home chord with two beats or more held, a run
  there (the G run's shape: the home note, the blue third hammered to the major, up through the fifth and sixth
  and back; or its short form); or a run of three eighths into an arrival, from the side the note before it is
  on (down the scale from above; up it, or the chromatic steps, from below);
- a **phrase answered rather than repeated**: a repeat departs further (`answer`), and an octave move there goes
  as far from the earlier phrase's register as it can (staying put, if the earlier one moved);
- **later passes further**: each pass after the first departs a little more (`passes`, three passes at most);
- past d 0.55, whole bars (the phrase's last never) taken from the **free line**, moved by octaves to the tune's
  register and their last note turned to step into the tune's next note.

**Decoration** is chosen by the style (whether a note is decorated) and played by the instrument's idiom
(`Idiom`, `IDIOMS`): a slide into the note, a hammer-on from below or a pull-off from above (on the dobro only from
or to an open string: the bar does neither), a double stop (a third or a sixth under it, from the chord), a triplet
on a beat of two eighths; and the instrument's range (a fiddle has nothing under its G string: the tune's lower
notes come up an octave). Only the tune's notes and those the passing changes, substitutions, octaves and pushes
made are decorated, not a fill's, a lick's or a run's. The conductor plays them as its voice can
(`conductor.play_strung_as`: the dobro's samples slide, hammer and pull on the string; a struck voice takes a slide
into a note as a grace note).

**The density** (`density`, the page's Note density; 2026-10-22, the transcription project's card
`ambient-break-density`): the break's notes against the tune's own, apart from its pull. The player (2026-10-22): "a
player would play different notes and rhythms from the standard melody, but not necessarily play something far
busier ... with low note density, i'd want to hear it actually simplify the melody in some cases rather than ornament
it". At 1, the default, a break is as its pull makes it (its fills and the free line as before). **Below 1** a phrase
is held to that share of the tune's notes in it (from `1 - density_ease` down; between, the notes it plays over the
tune's own give way in proportion), simplified as a player simplifies: the skeleton kept (the phrase's first note and
its arrival always; then the notes on beats 1 and 3, the arrival's approach, a note where the chord changes, one
where the tune strikes a note), and first dropped a fill's or a run's notes, a grace note, a repeated note (held
instead), a passing or neighbour note; of the rest, the tune's own kept where the pull is high and the chord's tones
where it is low. Each note left is held to the next (never into a bar the free line takes); where one would be held
past its own length over a chord it is not in, a note dropped there is struck again (the harmonic rhythm heard), and
one held longer than it was over other notes, out of its chord, moves to the chord's nearest. The free line's bars
are held likewise to the share of the tune's notes in them (the tune's notes a bar, so a busy stretch of the tune
keeps more), so a break near the free end plays other notes and rhythms, not more of them. **Above 1** a phrase's
held notes are filled (as the pull fills them) until it has that share of the tune's notes, if it has fewer; the free
line is not filled. The tune as written (pull 1) is the same at every density.

**The departure by the tune's own density** (`BreakParams.local`, off unless set; the player, 2026-10-22, on Down
Yonder: "a fiddle player would usually hit most of the standard notes in the low density portions ... and then
innovate on the density parts more freely"): each note's moves and each bar's chance of the free line at a departure
raised or lowered by how busy the tune is in that bar, so a sparse bar keeps more of the tune and a busy one departs
further.

**Its own dice.** A break has a random generator of its own (`seed`): the melody's choices alone, so the band under
it is the same at every setting and seed (the A/B clips). The density has dice of its own besides, a phrase's and a
free bar's from the seed, so a break at a density is its seed's break at 1, simplified or filled phrase by phrase.
Which rules are style and which idiom is recorded in the transcription project's `docs/knowledge-layers.md`.
"""

from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

BAR = 4.0  # a fiddle tune's bar, in beats; its strong beats are 1 and 3 (the two-feel's)
EPS = 1e-6
LEGATO = ("slide", "hammer", "pull")
DECORATED = ("tune", "passing", "substitute", "octave", "anticipate")  # notes a decoration may go on (not a lick's)
MAJOR = (0, 2, 4, 5, 7, 9, 11)


@dataclass(frozen=True)
class Note:
    """A note of a line, in the tune's beats from bar 1's downbeat."""
    t: float
    dur: float
    midi: int
    how: str = "pick"  # pick; slide (from the note before, no pick); slide-in (picked `bend` semitones below and
    # slid up); hammer, pull (sounded from the note before with no pick); double (a double stop's added note)
    bend: int = 0
    by: str = "tune"  # the tune's own note, or the move that made it

    @property
    def end(self) -> float:
        return self.t + self.dur


@dataclass(frozen=True)
class FreeSpan:
    """A stretch of a phrase (tune beats, whole bars of the synth) taken from the free line."""
    t0: float
    t1: float


@dataclass
class Tune:
    """One pass of a tune's melody: its notes from bar 1 (the pickup into the next pass in its last bar), its key,
    its bars, the pickup into bar 1 (`lead_in`, before it), and the bars of each part (`parts`; none: one part)."""
    name: str
    key: int  # the home note's pitch class
    bars: int
    notes: list[Note]
    lead_in: list[Note] = field(default_factory=list)
    phrase_bars: int = 4
    parts: tuple[int, ...] = ()

    @property
    def beats(self) -> float:
        return self.bars * BAR

    def melody(self) -> list[Note]:
        return [n for n in self.notes if n.how != "double"]

    def phrases(self) -> list[tuple[int, int]]:
        """Bars [start, end) of each phrase: phrase_bars each within a part, a part's remainder joined to its last."""
        out, b0 = [], 0
        for size in self.parts or (self.bars,):
            n = max(1, size // self.phrase_bars)
            ph = [(b0 + i * self.phrase_bars, b0 + (i + 1) * self.phrase_bars) for i in range(n)]
            ph[-1] = (ph[-1][0], b0 + size)
            out += ph
            b0 += size
        return out

    def phrase_of(self, t: float) -> int:
        for j, (b0, b1) in enumerate(self.phrases()):
            if b0 * BAR - EPS <= t < b1 * BAR - EPS:
                return j
        return len(self.phrases()) - 1

    def arrival(self, j: int) -> Note:
        """The phrase's arrival: the longest melody note starting in its last bar (the later of two as long)."""
        b0, b1 = self.phrases()[j]
        last = [n for n in self.melody() if (b1 - 1) * BAR - EPS <= n.t < b1 * BAR - EPS]
        if not last:
            last = [n for n in self.melody() if b0 * BAR - EPS <= n.t < b1 * BAR - EPS][-1:]
        return max(reversed(last), key=lambda n: n.dur)

    def into_top(self) -> list[Note]:
        """The notes that lead into bar 1 from the pass before: the written pickup, else the last bar's notes after
        its arrival."""
        arr = self.arrival(len(self.phrases()) - 1)
        return [n for n in self.notes if n.t > arr.t + EPS and n.how != "double"]

    def repeats(self, j: int) -> int | None:
        """The earlier phrase this one plays again (three quarters of its notes at the same place and pitch)."""
        ph = self.phrases()
        mine = self._shape(j)
        for i in range(j):
            if ph[i][1] - ph[i][0] != ph[j][1] - ph[j][0]:
                continue
            other = self._shape(i)
            if mine and len(mine & other) >= 0.75 * max(len(mine), len(other)):
                return i
        return None

    def _shape(self, j: int) -> set:
        b0, b1 = self.phrases()[j]
        return {(round(n.t - b0 * BAR, 3), n.midi) for n in self.melody() if b0 * BAR - EPS <= n.t < b1 * BAR - EPS}

    def range(self) -> tuple[int, int]:
        ms = [n.midi for n in self.melody()]
        return min(ms), max(ms)


def strong(t: float) -> bool:
    """On beat 1 or 3 of the tune's bar."""
    b = t % BAR
    return abs(b) < EPS or abs(b - 2) < EPS or abs(b - BAR) < EPS


def bell(d: float) -> float:
    return 4 * d * (1 - d)


# ---- the tune, read from the transcription project ----

ROOTS = ["~/play/dobro-transcription", "~/dobro-transcription"]


def use_project(root) -> None:
    """Look for the tunes in this transcription project first (the config's, from the server)."""
    r = str(root)
    if r in ROOTS:
        ROOTS.remove(r)
    ROOTS.insert(0, r)
    load_tune.cache_clear()


def project_root() -> Path | None:
    for r in [os.environ.get("AMBIENT_TRANSCRIPTION")] + ROOTS:
        if r and (Path(r).expanduser() / "tunes").is_dir():
            return Path(r).expanduser()
    return None


@lru_cache(maxsize=16)
def load_tune(folder: str, key: str, bars: int, project: str | None = None, parts: tuple[int, ...] = ()) -> Tune:
    """One pass of a tune's key (`tunes/dobro/<folder>/<folder>.musicxml`): its first `bars` bars from bar 1, and
    the pickup before bar 1, which is played into the next pass (its last bar's notes from there on cut). `parts`:
    the bars of each part in the pass, adding up to `bars` (none: the pass is one part)."""
    from .music import KEYS
    if parts and sum(parts) != bars:
        raise ValueError(f"{folder}: its parts {parts} are not its {bars} bars")
    root = Path(project).expanduser() if project else project_root()
    if root is None:
        raise FileNotFoundError("the transcription project's tunes are not here")
    src = str(root / "pipeline" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from transcribe.score import read_score
    ev, meta = read_score(root / "tunes" / "dobro" / folder / f"{folder}.musicxml")
    pickup = float(meta.get("pickup_beats") or 0.0)
    by_onset: dict[float, list] = {}
    for e in ev:
        by_onset.setdefault(round(e.onset_beats - pickup, 4), []).append(e)
    notes, lead_in, prev = [], [], None
    for t in sorted(by_onset):
        if t >= bars * BAR - EPS:
            break
        group = sorted(by_onset[t], key=lambda e: -e.midi)
        top = group[0]
        how, bend = "pick", 0
        if top.technique in LEGATO and not top.attack:
            how = top.technique
        elif top.technique == "slide-in":
            how, bend = "slide-in", max(1, min(3, round(top.slide_in_st or 2)))
        elif top.technique == "slide" and prev is not None and 0 < top.midi - prev <= 4:
            how, bend = "slide-in", top.midi - prev  # picked and slid on up from the note before (a shift slide)
        elif top.technique == "slide" and prev is not None and 0 < prev - top.midi <= 4:
            how = "slide"  # slid on down from the note before
        out = lead_in if t < 0 else notes
        out.append(Note(t, top.duration_beats, top.midi, how, bend))
        out += [Note(t, e.duration_beats, e.midi, "double") for e in group[1:]]
        prev = top.midi
    end = bars * BAR
    if lead_in:  # the pickup into bar 1, at the end of the pass: what the last bar holds there gives way to it
        start = end + lead_in[0].t
        notes = [replace(n, dur=min(n.dur, start - n.t)) for n in notes if n.t < start - EPS]
        notes += [replace(n, t=n.t + end) for n in lead_in]
    return Tune(folder, KEYS.index(key), bars, notes, lead_in, parts=tuple(parts))


# ---- the instrument's idiom ----

@dataclass(frozen=True)
class Idiom:
    """What an instrument does with a note: its range, and the ornaments it plays."""
    lo: int
    hi: int
    slide_in: tuple[int, ...] = (1, 2)  # semitones a note is slid into from (none: no slides)
    open_strings: tuple[int, ...] = ()  # a dobro hammers on only from these and pulls off only to them
    open_only: bool = False
    double: tuple[int, ...] = (3, 4, 8, 9)  # intervals under a note a double stop adds
    triplet: bool = True
    roll: bool = False  # a held note may be filled with a roll (three strings' notes of the chord, in triplets)
    weights: tuple[tuple[str, float], ...] = (("slide-in", 3), ("hammer", 2), ("pull", 1), ("double", 2),
                                              ("triplet", 1))


IDIOMS = {
    # open G, G2 to the 15th fret of the D string; the bar slides, the fingers hammer and pull only on open strings
    "Dobro": Idiom(43, 77, (1, 2, 3), (43, 47, 50, 55, 59, 62), True, (3, 4, 8, 9), True, True,
                   (("slide-in", 3), ("hammer", 2), ("pull", 1), ("double", 2), ("triplet", 1.5))),
    "Fiddle": Idiom(55, 88, (1, 2), (55, 62, 69, 76), False, (3, 4, 8, 9), True, False,
                    (("slide-in", 3), ("hammer", 2), ("pull", 2), ("double", 2), ("triplet", 2))),
    "Mandolin": Idiom(55, 88, (1,), (55, 62, 69, 76), False, (3, 4, 8, 9), True, False,
                      (("slide-in", 1), ("hammer", 2), ("pull", 2), ("double", 2), ("triplet", 2))),
    "Banjo": Idiom(50, 81, (1, 2), (50, 55, 59, 62, 67), False, (3, 4, 8, 9), True, True,
                   (("slide-in", 2), ("hammer", 3), ("pull", 3), ("double", 1), ("triplet", 1))),
    "any": Idiom(40, 88),
}


# ---- the moves ----

@dataclass(frozen=True)
class BreakParams:
    """How likely each move is at a departure d (1 - the pull). Set by hand on 2026-10-22 from how bluegrass breaks
    on fiddle tunes are played; the player's ear to settle them (the transcription project's review
    2026-10-22-tune-breaks). Each is a chance per chance to make it (a note, a phrase, a bar)."""
    keep_from: float = 0.3  # every strong-beat note the tune's up to this departure; past it fewer ...
    keep_floor: float = 0.2  # ... down to this share at d 1 (1 - (1 - floor) x ((d - from) / (1 - from)) ** 1.5)
    free_from: float = 0.55  # a bar from the free line past this departure: ((d - from) / (1 - from)) ** 1.5
    anticipate: float = 0.25  # a strong note pushed an eighth early: this x d
    fill: float = 0.7  # a held note filled: this x d ** 0.7 (half as often an arrival, its attack kept; never a push)
    passing: float = 0.55  # a weak note changed: this x d (0.3 as often a pickup into the next phrase)
    octave: float = 0.25  # half a phrase an octave away (in the tune's register and a fifth over): this x bell(d)
    # x min(1, 2 d) (rarer while the tune is only decorated) ...
    octave_answer: float = 0.15  # ... and this more on a repeat
    decorate: float = 0.18  # a note decorated: this x min(1, 2.5 d) x (1 - 0.6 d)
    lick: float = 0.6  # a run on a held arrival at the home note: this x bell(d)
    approach: float = 0.3  # a run into an arrival: this x bell(d)
    answer: float = 0.2  # a repeat's departure: up by this x bell(d)
    passes: float = 0.1  # each pass after the first: the departure up by this x bell(d), three passes at most
    # The density (2026-10-22, by hand, the player's ear to settle it: review 2026-10-22-break-density). Below 1, the
    # notes a stretch plays over the tune's own give way over this much of the density, and from 1 - this down it is
    # held to that share of the tune's notes; above 1, filled up to that share over this much. So the control has no
    # step at 1, where the break is as before.
    density_ease: float = 0.25
    # The departure by the tune's own density, bar by bar (2026-10-22; the player on Down Yonder at 0.25: "a fiddle
    # player would usually hit most of the standard notes in the low density portions ... and then innovate on the
    # density parts more freely"). None: off, one departure for the phrase (as before). A number g: a note's moves
    # and a bar's free line at d ** (1 / r ** g), r the tune's notes in its bar against its mean (from a quarter): a
    # sparse bar keeps more of the tune, a busy one departs further; as written and free unchanged. Set by hand (2)
    # for the player's ear (review 2026-10-22-break-density); not on until they say.
    local: float | None = None


PARAMS = BreakParams()

DENSITY_LO, DENSITY_HI = 0.25, 2.0  # the page's Note density, its ends: a quarter of the tune's notes, twice them


def density_of(x: float) -> float:
    """The page's Note density (0 to 1, 0.5 the default) as a share of the tune's notes: a quarter of them to the
    tune's own over its lower half, the tune's own to twice them over its upper."""
    x = max(0.0, min(1.0, float(x)))
    r = DENSITY_LO + (1 - DENSITY_LO) * 2 * x if x <= 0.5 else 1 + (DENSITY_HI - 1) * 2 * (x - 0.5)
    return round(r, 6)


def density_setting(r: float) -> float:
    """The page's Note density for a share of the tune's notes (density_of's inverse)."""
    r = max(DENSITY_LO, min(DENSITY_HI, float(r)))
    return (r - DENSITY_LO) / (1 - DENSITY_LO) / 2 if r <= 1 else 0.5 + (r - 1) / (DENSITY_HI - 1) / 2


class Break:
    """A break on a tune: its phrases planned one at a time (`phrase`), each pass a little further from the tune, and
    played a bar of the synth at a time (`plan_bar`, `at`) into the conductor's grid.

    `chords`: a beat each over one pass, the chord sounding (pitch classes, root first) in the tune's own key.
    `k`: the tune's bars to one of the synth's (2: laid in two). `shift`: semitones from the tune's key to the key
    played. `seed`: the break's own dice. `density`: its notes against the tune's (1: as its pull makes it)."""

    def __init__(self, tune: Tune, chords: list[tuple[int, ...]], pull: float, seed=None, k: int = 1,
                 shift: int = 0, idiom: Idiom | None = None, params: BreakParams = PARAMS, density: float = 1.0):
        self.tune, self.chords, self.k, self.shift = tune, chords, k, shift
        self.pull = pull
        self.density = density
        self.rng = random.Random(seed)
        # the density's dice, a phrase's and a free bar's own from this (not the break's: a break at a density is its
        # seed's break at 1, simplified or filled)
        self.dense_seed = seed if seed is not None else random.getrandbits(32)
        self.idiom = idiom or IDIOMS["any"]
        self.params = params
        self.first_pass = 0  # passes before it are not counted as later passes
        lo, hi = tune.range()
        self.lo, self.hi = max(self.idiom.lo, lo - 3), min(self.idiom.hi, hi + 5)
        self.reset()

    def reset(self) -> None:
        self.done: dict[tuple[int, int], list] = {}  # (pass, phrase) -> its plan as varied
        self.played: dict[tuple[int, int], list] = {}  # ... and as played, at the density
        self.plan: dict[int, list] = {}  # the synth's sixteenth -> [(MIDI, length, velocity, offset, how)]
        self.heard: list[tuple[int, Note]] = []  # (pass, note in the pass's beats) as played

    def dense(self) -> bool:
        """The density moved from 1 (else the break is as its pull makes it, its dice untouched)."""
        return abs(self.density - 1.0) > 1e-9

    # -- harmony --

    def chord_at(self, t: float) -> tuple[int, ...]:
        if not self.chords:
            return (self.tune.key, (self.tune.key + 4) % 12, (self.tune.key + 7) % 12)
        return self.chords[int(math.floor(t + EPS)) % len(self.chords)]

    def scale_at(self, t: float) -> set[int]:
        """The key's major scale, with the chord's own notes (A7's C#, G7's F)."""
        s = {(self.tune.key + x) % 12 for x in MAJOR}
        c = self.chord_at(t)
        for p in c:  # a chord's note outside the scale replaces the scale's note a half step from it
            if p not in s:
                for q in ((p - 1) % 12, (p + 1) % 12):
                    if q in s and q not in c:
                        s.discard(q)
                        break
                s.add(p)
        return s

    def _in_scale(self, m: int, t: float) -> bool:
        return m % 12 in self.scale_at(t)

    def _step(self, m: int, t: float, d: int) -> int:
        """The next note of the scale from m, up (d 1) or down (-1)."""
        x = m + d
        while not self._in_scale(x, t):
            x += d
        return x

    def _tones_near(self, m: int, t: float, span: int = 5) -> list[int]:
        c = set(self.chord_at(t))
        return [x for x in range(m - span, m + span + 1) if x % 12 in c and self.lo <= x <= self.hi]

    # -- planning a phrase --

    def departure(self, pass_i: int, j: int) -> float:
        d = 1.0 - self.pull
        if d <= EPS or d >= 1 - EPS:
            return max(0.0, min(1.0, d))
        b = bell(d)
        d += self.params.passes * b * min(3, max(0, pass_i - self.first_pass))
        if self.tune.repeats(j) is not None:
            d += self.params.answer * b
        return min(d, 0.97)

    def local_d(self, d: float, t0: float, span: float = BAR) -> float:
        """The departure over [t0, t0 + span) by the tune's own density there (`BreakParams.local`); d when off."""
        g = self.params.local
        if g is None or d <= EPS or d >= 1 - EPS:
            return d
        mean = len(self.tune.melody()) / self.tune.bars
        b0 = math.floor((t0 + EPS) / BAR) * BAR
        here = sum(1 for n in self.tune.melody() if b0 - EPS <= n.t < b0 + max(span, BAR) - EPS)
        r = max(0.25, here / (mean * max(1.0, span / BAR)))
        return d ** (1 / r ** g)

    def phrase(self, pass_i: int, j: int) -> list:
        """Phrase j's notes on pass `pass_i` as played (beats from the pass's start), and the free stretches in it:
        as varied, at the density."""
        key = (pass_i, j)
        if key not in self.played:
            plan = self.varied(pass_i, j)
            if self.dense() and EPS < self.departure(pass_i, j) < 1 - EPS:
                plan = self._dense(plan, pass_i, j)
            self.played[key] = plan
        return self.played[key]

    def varied(self, pass_i: int, j: int) -> list:
        """Phrase j on pass `pass_i` as its pull varies it (the context of the phrases after it)."""
        key = (pass_i, j)
        if key not in self.done:
            b0, b1 = self.tune.phrases()[j]
            t0, t1 = b0 * BAR, b1 * BAR
            notes = [self._fit(n) for n in self.tune.notes if t0 - EPS <= n.t < t1 - EPS]
            d = self.departure(pass_i, j)
            if d <= EPS:
                plan = list(notes)
            elif d >= 1 - EPS:
                plan = [FreeSpan(t0, t1)]
            else:
                rep = self.tune.repeats(j)
                before = self.done.get((pass_i, j - 1) if j else (pass_i - 1, len(self.tune.phrases()) - 1)) or []
                last = [x for x in before if isinstance(x, Note) and x.how != "double"]
                prev_last = last[-1].midi if last and not isinstance(before[-1], FreeSpan) else None
                plan = self._vary(notes, j, d, t0, t1, self.done.get((pass_i, rep)) if rep is not None else None,
                                  prev_last)
            self.done[key] = plan
        return self.done[key]

    def _fit(self, n: Note) -> Note:
        """A note in the instrument's range, an octave at a time (a fiddle has nothing under its G string)."""
        m = n.midi
        while m < self.idiom.lo:
            m += 12
        while m > self.idiom.hi:
            m -= 12
        return n if m == n.midi else replace(n, midi=m)

    def _app_bar(self, t: float) -> int:
        return int(math.floor((t + EPS) / (BAR * self.k)))

    def _vary(self, notes: list[Note], j: int, d: float, t0: float, t1: float, earlier: list | None,
              prev_last: int | None = None) -> list:
        p, rng, tune = self.params, self.rng, self.tune
        b = bell(d)
        mel = [n for n in notes if n.how != "double"]
        doubles = [n for n in notes if n.how == "double"]
        arr = self._fit(tune.arrival(j))
        approach = [n for n in mel if arr.t - 2 - EPS <= n.t < arr.t - EPS][-2:]
        after = [n for n in mel if n.t > arr.t + EPS]
        guard = {arr, *approach}
        head = [n for n in mel if abs(n.t - t0) < EPS]  # the phrase's first note, on its downbeat

        # whole bars of the synth's from the free line (never the one the phrase lands in)
        free = set()
        span = BAR * self.k
        if p.local is None and d > p.free_from:
            pf = ((d - p.free_from) / (1 - p.free_from)) ** 1.5
            land = {self._app_bar(n.t) for n in [arr, *approach]}
            for a in range(self._app_bar(t0), self._app_bar(t1 - EPS) + 1):
                if a not in land and rng.random() < pf:
                    free.add(a)
        elif p.local is not None:  # each bar of the synth's by the tune's density there
            land = {self._app_bar(n.t) for n in [arr, *approach]}
            for a in range(self._app_bar(t0), self._app_bar(t1 - EPS) + 1):
                da = self.local_d(d, a * span, span)
                pf = ((da - p.free_from) / (1 - p.free_from)) ** 1.5 if da > p.free_from else 0.0
                if a not in land and pf > 0 and rng.random() < pf:
                    free.add(a)
        if free:  # the tune's notes there left out, and none ringing into them
            mel = [n for n in mel if self._app_bar(n.t) not in free]
            starts = sorted(a * span for a in free)
            mel = [replace(n, dur=min(n.dur, min([s for s in starts if s > n.t + EPS], default=n.end) - n.t))
                   for n in mel]

        # a strong note substituted by another tone of its chord
        def kept(x):
            return 1.0 if x <= p.keep_from else 1 - (1 - p.keep_floor) * ((x - p.keep_from) / (1 - p.keep_from)) ** 1.5
        keep = kept(d)
        out = []
        for n in mel:
            if p.local is not None:
                keep = kept(self.local_d(d, n.t))
            if strong(n.t) and n not in guard and (n not in head or d > 0.7) and rng.random() > keep:
                c = [x for x in self._tones_near(n.midi, n.t, 5) if x % 12 != n.midi % 12]
                if c:
                    w = [1 / (1 + abs(x - n.midi)) for x in c]
                    n = replace(n, midi=rng.choices(c, w)[0], how="pick" if n.how in LEGATO else n.how,
                                by="substitute")
            out.append(n)
        mel = out

        # a strong note pushed an eighth early, tied over the beat
        out = []
        for n in mel:
            if (strong(n.t) and out and n.t - 0.5 >= t0 - EPS and (n != arr or d >= 0.4)
                    and rng.random() < p.anticipate * self.local_d(d, n.t)):
                prev = out[-1]
                at = n.t - 0.5
                if prev.t >= at - EPS:
                    if prev in guard:
                        out.append(n)
                        continue
                    out.pop()
                else:
                    out[-1] = replace(prev, dur=min(prev.dur, at - prev.t))
                n2 = replace(n, t=at, dur=n.dur + 0.5, how="pick" if n.how in LEGATO else n.how, by="anticipate")
                if n == arr:
                    arr = n2
                guard = {arr, *approach}
                out.append(n2)
            else:
                out.append(n)
        mel = out

        # a held note filled, arriving at the next note by step
        out = []
        for i, n in enumerate(mel):
            nxt = mel[i + 1].midi if i + 1 < len(mel) else self._next_tune_note(t1)
            chance = p.fill * self.local_d(d, n.t) ** 0.7 * (0.5 if n == arr else 1.0)
            if n.dur >= 1 - EPS and n.by != "anticipate" and rng.random() < chance:
                filled = self._fill(n, nxt)
                if n in guard:  # its attack, the fill's first note, stays as kept as it was
                    guard = (guard - {n}) | {filled[0]}
                    if n == arr:
                        arr = filled[0]
                out += filled
            else:
                out.append(n)
        mel = out

        # a weak note changed
        out = []
        for i, n in enumerate(mel):
            chance = p.passing * self.local_d(d, n.t) * (0.3 if n in after else 1.0)
            if not strong(n.t) and n.by == "tune" and n not in guard and rng.random() < chance:
                prev = out[-1].midi if out else None
                nxt = mel[i + 1].midi if i + 1 < len(mel) else self._next_tune_note(t1)
                nxt_strong = strong(mel[i + 1].t) if i + 1 < len(mel) else True
                m = self._passing(prev, n, nxt, nxt_strong)
                if m is not None:
                    n = replace(n, midi=m, how="pick" if n.how in LEGATO else n.how, by="passing")
            out.append(n)
        mel = out

        # half the phrase an octave away, back for the arrival
        po = (p.octave + (p.octave_answer if earlier is not None else 0.0)) * b * min(1.0, 2 * d)
        if rng.random() < po:
            half = t0 + (t1 - t0) / 2
            part = [n for n in mel if n.t < half - EPS and n not in guard]
            if part:
                lo, hi = tune.range()
                ups = all(n.midi + 12 <= min(self.idiom.hi, hi + 7) for n in part)
                downs = all(n.midi - 12 >= max(self.idiom.lo, lo - 2) for n in part)
                ways = [x for x, ok in ((12, ups), (-12, downs)) if ok]
                if prev_last is not None and part[0].t < t0 + 1 - EPS:  # into it from the phrase before: no wider
                    gap = abs(part[0].midi - prev_last)  # than a sixth, or than the tune's own leap there
                    ways = [x for x in ways if abs(part[0].midi + x - prev_last) <= max(9, gap)]
                if earlier is not None and ways:  # an answer: as far from the earlier phrase's register as it
                    e0 = min(x.t if isinstance(x, Note) else x.t0 for x in earlier)  # can be (staying put, too)
                    then = [x.midi for x in earlier if isinstance(x, Note) and x.how != "double"
                            and x.t < e0 + (half - t0) - EPS]
                    if then:
                        mine = sum(n.midi for n in part) / len(part)
                        before = sum(then) / len(then)
                        ways = sorted(ways + [0], key=lambda x: -abs(mine + x - before))[:1]
                if ways and ways != [0]:
                    x = rng.choice(ways)
                    moved = set(part)
                    mel = [replace(n, midi=n.midi + x, by="octave") if n in moved else n for n in mel]

        # a lick at the cadence: a run on a held home note, or a run into the arrival
        nxt_after = min([n.t for n in mel if n.t > arr.t + EPS], default=t1)
        room = nxt_after - arr.t
        home = arr.midi % 12 == tune.key and self.chord_at(arr.t)[0] == tune.key
        if home and room >= 2 - EPS and rng.random() < p.lick * b:
            run = self._run(arr, room)
            if run:
                mel = [n for n in mel if not (arr.t - EPS <= n.t < arr.t + room - EPS)] + run
                arr = run[-1]
        elif arr.t - t0 >= 2 - EPS and rng.random() < p.approach * b:
            before = [n for n in mel if n.t < arr.t - 1.5 - EPS]
            run = self._approach(arr, before[-1].midi if before else None)
            if run:
                start = run[0].t
                mel = [replace(n, dur=min(n.dur, start - n.t)) if n.t < start - EPS else n
                       for n in mel if not (start - EPS <= n.t < arr.t - EPS)] + run
        mel.sort(key=lambda n: n.t)

        # decoration, as the instrument plays it
        pd = p.decorate * min(1.0, 2.5 * d) * (1 - 0.6 * d)
        out = []
        i = 0
        while i < len(mel):
            n = mel[i]
            nxt = mel[i + 1] if i + 1 < len(mel) else None
            led = out and out[-1].by in ("approach", "lick")
            if p.local is not None:
                dn = self.local_d(d, n.t)
                pd = p.decorate * min(1.0, 2.5 * dn) * (1 - 0.6 * dn)
            if n.how == "pick" and n.dur >= 0.5 - EPS and n.by in DECORATED and not led and rng.random() < pd:
                orn = self._ornament(n, nxt, out[-1] if out else None)
                if orn is not None:
                    notes_, used_next = orn
                    out += notes_
                    i += 2 if used_next else 1
                    continue
            out.append(n)
            i += 1
        mel = out

        # the tune's double stops where their note stayed
        kept = {(round(n.t, 4), n.midi) for n in mel if n.by == "tune"}
        for x in doubles:
            top = next((m for m in notes if abs(m.t - x.t) < EPS and m.how != "double"), None)
            if top is not None and (round(top.t, 4), top.midi) in kept:
                mel.append(x)
        plan = self._clean(mel)
        if free:
            for a in sorted(free):
                plan.append(FreeSpan(a * span, (a + 1) * span))
        return sorted(plan, key=lambda x: x.t if isinstance(x, Note) else x.t0)

    def _next_tune_note(self, t: float) -> int | None:
        nxt = [n for n in self.tune.melody() if n.t >= t - EPS]
        return nxt[0].midi if nxt else (self.tune.melody()[0].midi if self.tune.notes else None)

    def _passing(self, prev: int | None, n: Note, nxt: int | None, nxt_strong: bool) -> int | None:
        """Another weak note between its neighbours: a note of the scale within a fourth of it (or the half step
        under a strong next note), the likelier the more it is a chord tone, a step into the next note, a step from
        the one before; never the note before again, nor a leap of more than a fourth either side."""
        rng, t = self.rng, n.t
        chord = set(self.chord_at(t))
        cands = [m for m in range(n.midi - 5, n.midi + 6) if self._in_scale(m, t)]
        if nxt is not None and nxt_strong:
            cands.append(nxt - 1)
        weights = {}
        for m in set(cands):
            if m == n.midi or m == prev or not self.lo <= m <= self.hi:
                continue
            if (prev is not None and abs(m - prev) > 5) or (nxt is not None and abs(m - nxt) > 5) or m == nxt:
                continue
            w = 1.0
            if m % 12 in chord:
                w += 1.5
            if nxt is not None and abs(m - nxt) <= 2:
                w += 1.5
            if prev is not None and abs(m - prev) <= 2:
                w += 0.5
            if not self._in_scale(m, t):  # the chromatic step into a strong note
                w = 1.0
            weights[m] = w
        if not weights:
            return None
        ms = sorted(weights)
        return rng.choices(ms, [weights[m] for m in ms])[0]

    def _fill(self, n: Note, nxt: int | None, rng: random.Random | None = None) -> list[Note]:
        """A held note as eighths (or a roll's triplets): its own pitch first, the rest moving on to the next."""
        rng = rng or self.rng
        kinds = [("arpeggio", 3), ("run", 3), ("neighbour", 2)]
        if self.idiom.roll:
            kinds.append(("roll", 2))
        kind = rng.choices([k for k, _ in kinds], [w for _, w in kinds])[0]
        target = nxt if nxt is not None else n.midi
        if kind == "roll":
            step, count = 1 / 3, int(round(n.dur * 3))
        else:
            step, count = 0.5, int(round(n.dur / 0.5))
        if count < 2:
            return [n]
        ps = [n.midi]
        direction = 1 if target > n.midi else -1 if target < n.midi else rng.choice([1, -1])
        cell = None
        if kind == "roll":  # three strings: the held note and the chord's next two over it (or under), round again
            c = sorted(set(self._tones_near(n.midi, n.t, 9)))
            up = [x for x in c if x > n.midi][:2]
            down = [x for x in c if x < n.midi][-2:][::-1]
            pick = up if len(up) == 2 and (direction > 0 or len(down) < 2) else down
            cell = [n.midi] + pick if len(pick) == 2 else None
            if cell is None:
                kind = "arpeggio"
        for i in range(1, count):
            t = n.t + i * step
            last = ps[-1]
            if cell is not None:
                m = cell[i % 3]
            elif kind == "arpeggio":
                c = sorted(set(self._tones_near(last, t, 9)))
                ahead = [x for x in c if (x - last) * direction > 0]
                if not ahead:
                    direction = -direction
                    ahead = [x for x in c if (x - last) * direction > 0]
                m = min(ahead, key=lambda x: abs(x - last)) if ahead else last
            elif kind == "run":  # by step toward the next note, turning back a step past it (or the register)
                m = self._step(last, t, direction)
                past = m >= max(target, n.midi) + 3 if direction > 0 else m <= min(target, n.midi) - 3
                if past or not self.lo <= m <= self.hi:
                    direction = -direction
                    m = self._step(last, t, direction)
            else:  # a neighbour and back, above then below
                m = n.midi if i % 2 == 0 else self._step(n.midi, t, 1 if (i // 2) % 2 == 0 else -1)
            m = max(self.lo, min(self.hi, m))
            ps.append(m)
        if nxt is not None and abs(ps[-1] - nxt) > 2 and count > 2:  # into the next note by step
            t = n.t + (count - 1) * step
            side = 1 if ps[-2] > nxt else -1
            m = self._step(nxt, t, side)
            if m == ps[-2]:
                m = self._step(nxt, t, -side)
            if self.lo <= m <= self.hi and m != ps[-2]:
                ps[-1] = m
        out = []
        for i, m in enumerate(ps):
            t = n.t + i * step
            dur = step if i < count - 1 else n.end - t
            if i == 0:
                out.append(replace(n, dur=step))
            else:
                out.append(Note(t, dur, m, "pick", 0, "fill"))
        return out

    def _run(self, arr: Note, room: float) -> list[Note]:
        """A lick on a held arrival at the home note: the G run's shape (the home note, the blue third hammered to
        the major, the fifth, the sixth, the fifth, the third, home), or its short form (home, the blue third to
        the major, the second, home)."""
        T = arr.midi
        if room >= 3 - EPS and T + 9 <= self.idiom.hi:
            shape = [(0, 0, 0.5, "pick"), (0.5, 3, 0.25, "pick"), (0.75, 4, 0.25, "hammer"), (1.0, 7, 0.5, "pick"),
                     (1.5, 9, 0.5, "pick"), (2.0, 7, 0.5, "pick"), (2.5, 4, 0.5, "pick"), (3.0, 0, room - 3, "pick")]
        elif T + 4 <= self.idiom.hi:
            shape = [(0, 0, 0.5, "pick"), (0.5, 3, 0.25, "pick"), (0.75, 4, 0.25, "hammer"), (1.0, 2, 0.5, "pick"),
                     (1.5, 0, room - 1.5, "pick")]
        else:
            return []
        out = [Note(arr.t + o, d, T + x, how, 0, "lick") for o, x, d, how in shape if d > EPS]
        out[0] = replace(out[0], how=arr.how, bend=arr.bend)
        return out

    def _approach(self, arr: Note, prev: int | None) -> list[Note]:
        """A run of three eighths into an arrival, from the side the note before it is on: down the scale from
        above; up it from below, or the chromatic steps from below."""
        rng, A = self.rng, arr.midi
        if prev is not None and prev > A + 2:
            kind = "above"
        elif prev is not None and prev < A - 2:
            kind = rng.choice(["below", "chromatic"])
        else:
            kind = rng.choice(["above", "below", "chromatic"])
        if kind == "chromatic":
            ps = [A - 3, A - 2, A - 1]
        else:
            d = 1 if kind == "above" else -1
            ps, m = [], A
            for _ in range(3):
                m = self._step(m, arr.t - 0.5, d)
                ps.insert(0, m)
        if not all(self.lo <= m <= self.hi for m in ps):
            return []
        return [Note(arr.t - 1.5 + 0.5 * i, 0.5, m, "pick", 0, "approach") for i, m in enumerate(ps)]

    def _ornament(self, n: Note, nxt: Note | None, prev: Note | None):
        """A decoration of n as the instrument plays it: (its notes, whether it took the next note in too), or None."""
        rng, idm, t = self.rng, self.idiom, n.t
        kinds = []
        for name, w in idm.weights:
            if name == "slide-in" and idm.slide_in:
                kinds.append((name, w))
            elif name == "hammer":
                below = [m for m in range(n.midi - 3, n.midi) if m >= idm.lo and (
                    m in idm.open_strings if idm.open_only else self._in_scale(m, t))]
                if below and n.dur >= 0.5 - EPS and n.midi - max(below) <= 2 and (prev is None or
                                                                                 prev.midi != max(below)):
                    kinds.append((name, w))
            elif name == "pull":
                above_ok = (n.midi in idm.open_strings) if idm.open_only else True
                up = self._step(n.midi, t, 1)
                if above_ok and n.dur >= 0.5 - EPS and up <= idm.hi and (prev is None or prev.midi != up):
                    kinds.append((name, w))
            elif name == "double" and idm.double and n.dur >= 1 - EPS:
                kinds.append((name, w))
            elif (name == "triplet" and idm.triplet and nxt is not None and abs(n.dur - 0.5) < EPS
                  and abs(n.t % 1) < EPS and abs(nxt.t - n.t - 0.5) < EPS and nxt.how == "pick"):
                kinds.append((name, w))
        if not kinds:
            return None
        kind = rng.choices([k for k, _ in kinds], [w for _, w in kinds])[0]
        if kind == "slide-in":
            return [replace(n, how="slide-in", bend=rng.choice(idm.slide_in), by="slide-in")], False
        if kind == "hammer":
            below = [m for m in range(n.midi - 3, n.midi) if m >= idm.lo and (
                m in idm.open_strings if idm.open_only else self._in_scale(m, t))]
            m = max(below)
            return [Note(t, 0.25, m, "pick", 0, "hammer"), replace(n, t=t + 0.25, dur=n.dur - 0.25, how="hammer",
                                                                    by="hammer")], False
        if kind == "pull":
            m = self._step(n.midi, t, 1)
            if m > self.idiom.hi:
                return None
            return [Note(t, 0.25, m, "pick", 0, "pull"), replace(n, t=t + 0.25, dur=n.dur - 0.25, how="pull",
                                                                  by="pull")], False
        if kind == "double":
            c = set(self.chord_at(t))
            under = [n.midi - x for x in idm.double if (n.midi - x) % 12 in c and n.midi - x >= idm.lo]
            if not under:
                return None
            return [replace(n, by="double stop"), Note(t, n.dur, rng.choice(under), "double", 0, "double stop")], False
        # a triplet over the beat: the note, one between, the next note
        a, b = n.midi, nxt.midi
        if abs(b - a) >= 3:
            mid = [m for m in range(min(a, b) + 1, max(a, b)) if self._in_scale(m, t)]
            m = rng.choice(mid) if mid else self._step(a, t, 1)
        else:  # a turn: a neighbour of the first away from the second (above it, the two the same)
            m = self._step(a, t, 1 if b <= a else -1)
        third = 1 / 3
        return [replace(n, dur=third, by="triplet"), Note(t + third, third, m, "pick", 0, "triplet"),
                replace(nxt, t=t + 2 * third, dur=nxt.end - (t + 2 * third), by="triplet")], True

    def _clean(self, mel: list[Note]) -> list[Note]:
        """In the instrument's range (an octave at a time), sorted, no melody note over the next, slides only where
        they can be played (a step or a few from the note before)."""
        out = sorted((self._fit(n) for n in mel), key=lambda n: (n.t, n.how == "double"))
        main = [n for n in out if n.how != "double"]
        res, prev = [], None
        for n in out:
            if n.how == "double":
                res.append(n)
                continue
            later = [x.t for x in main if x.t > n.t + EPS]
            end = min(later) if later else n.end
            n = replace(n, dur=max(0.05, min(n.dur, end - n.t)))
            if n.how in LEGATO and prev is not None:
                step = n.midi - prev.midi
                ok = {"slide": 0 < abs(step) <= 5, "hammer": 0 < step <= 4, "pull": -4 <= step < 0}[n.how]
                if not ok:
                    n = replace(n, how="pick")
            res.append(n)
            prev = n
        return [n for n in res if n.dur > 0.04]

    # -- the density --

    def target(self, own: int, have: int) -> float:
        """The notes a stretch plays at the density: `own` the tune's notes there, `have` the break's as varied.
        Below 1, never more than it has, and from 1 - density_ease down that share of the tune's; above 1, never
        fewer, and from 1 + density_ease up that share of the tune's."""
        r, ease = self.density, self.params.density_ease
        if r < 1:
            give = max(0.0, 1 - (1 - r) / ease)  # the share of its notes over the tune's still played
            return min(float(have), r * own + give * max(0, have - own))
        take = min(1.0, (r - 1) / ease)
        return have + take * max(0.0, r * own - have)

    @staticmethod
    def _count(x: float, rng: random.Random) -> int:
        """A whole number of notes for a target, rounded up or down by its fraction."""
        n = int(math.floor(x + EPS))
        return n + (1 if rng.random() < x - n - EPS else 0)

    def _dense(self, plan: list, pass_i: int, j: int) -> list:
        """A phrase as varied, at the density: simplified to the target, or its held notes filled up to it."""
        rng = random.Random(f"density {self.dense_seed} {pass_i} {j}")
        b0, b1 = self.tune.phrases()[j]
        t0, t1 = b0 * BAR, b1 * BAR
        spans = [x for x in plan if isinstance(x, FreeSpan)]
        notes = [x for x in plan if isinstance(x, Note)]
        mel = [n for n in notes if n.how != "double"]
        doubles = [n for n in notes if n.how == "double"]
        own = [n for n in self.tune.melody() if t0 - EPS <= n.t < t1 - EPS
               and not any(s.t0 - EPS <= n.t < s.t1 - EPS for s in spans)]
        want = self._count(self.target(len(own), len(mel)), rng)
        if want < len(mel):
            mel = self._simplify(mel, want, j, t0, rng, [x.t0 for x in spans])
        elif want > len(mel):
            mel = self._fill_to(mel, want, j, t1, {round(x.t, 4) for x in doubles}, rng)
        else:
            return plan
        tops = {round(n.t, 4) for n in mel}
        out = self._clean(mel + [x for x in doubles if round(x.t, 4) in tops])
        return sorted(out + spans, key=lambda x: x.t if isinstance(x, Note) else x.t0)

    def _weight(self, n: Note, prev: Note | None, nxt: Note | None, rng: random.Random) -> float:
        """How surely a player simplifying keeps a note: the meter's weight (beat 1, 3, 2 and 4, the offbeats); a
        note where the chord changes more, and one where the tune strikes a note (its rhythm heard); a fill's, a
        run's or the free line's notes, a grace note, a repeated note, a passing or neighbour note, a weak note out
        of its chord less; the tune's own more where the pull is high, the chord's tones where it is low; and a little
        chance. A push weighs as the beat it was pushed from."""
        b = (n.t + (0.5 if n.by == "anticipate" else 0.0)) % BAR
        on = lambda x: abs(x - round(x)) < EPS  # noqa: E731
        w = 3.0 if abs(b) < EPS or abs(b - BAR) < EPS else 2.5 if abs(b - 2) < EPS else 1.5 if on(b) else \
            1.0 if on(2 * b) else 0.5
        chord = set(self.chord_at(n.t))
        if prev is not None and set(self.chord_at(prev.t)) != chord:
            w += 1.0
        if round(n.t, 3) in self._tune_onsets():
            w += 0.5
        if n.by in ("fill", "lick", "approach", "free"):
            w -= 1.0
        if n.by in ("hammer", "pull", "triplet") and n.how == "pick" and n.dur < 0.5 - EPS:
            w -= 1.5
        if prev is not None and prev.midi == n.midi:  # held instead, before any other
            w -= 2.0
        elif (not strong(n.t) and prev is not None and nxt is not None and abs(n.midi - prev.midi) <= 2
              and abs(nxt.midi - n.midi) <= 2):
            w -= 0.5
        if not strong(n.t) and n.midi % 12 not in chord:
            w -= 0.5
        w += 0.4 * self.pull * (n.by == "tune") + 0.4 * (1 - self.pull) * (n.midi % 12 in chord)
        return w + 0.3 * rng.random()

    def _landing(self, mel: list[Note], j: int) -> int | None:
        """Where a varied phrase lands: its note nearest the tune's arrival, within an eighth, of its pitch class (a
        lick's first note, a push's, a fill's first)."""
        arr = self._fit(self.tune.arrival(j))
        land = [i for i, n in enumerate(mel) if abs(n.t - arr.t) <= 0.5 + EPS and n.midi % 12 == arr.midi % 12]
        return min(land, key=lambda i: abs(mel[i].t - arr.t)) if land else None

    def _tune_onsets(self) -> set:
        if not hasattr(self, "_onsets"):
            self._onsets = {round(n.t, 3) for n in self.tune.melody()}
        return self._onsets

    def _simplify(self, mel: list[Note], want: int, j: int, t0: float, rng: random.Random,
                  walls: list[float] = ()) -> list[Note]:
        """The phrase with `want` notes: its first and its arrival kept, the approach likelier, the rest by weight,
        none struck again just before the next phrase's first; a note struck where one left would be held over a
        chord it is not in; each note left held to the next (`_hold`), none into a bar of the free line's (`walls`).
        (A bonus for a repeat's notes where the phrase it repeats kept its own changed no choice over 20 seeds of
        three tunes: the skeleton is already the same; not kept.)"""
        land_i = self._landing(mel, j)
        must = {i for i, n in enumerate(mel) if abs(n.t - t0) < EPS}
        if land_i is not None:
            must.add(land_i)
        at = mel[land_i].t if land_i is not None else self.tune.arrival(j).t
        score = {}
        for i, n in enumerate(mel):
            w = self._weight(n, mel[i - 1] if i else None, mel[i + 1] if i + 1 < len(mel) else None, rng)
            score[i] = w + (1.0 if at - 2 - EPS <= n.t < at - EPS else 0.0)
        b1 = self.tune.phrases()[j][1]
        ahead = self._next_tune_note(b1 * BAR)  # the next phrase's first note, kept there: not struck just before it
        line = mel if ahead is None else mel + [self._fit(Note(b1 * BAR, 0.0, ahead))]
        end = max(n.end for n in mel)
        keep = self._choose(line, want + len(line) - len(mel), must | set(range(len(mel), len(line))), score)
        keep = [i for i in self._restrike(line, keep, end, walls) if i < len(mel)]
        return self._hold(mel, keep, end, must, rng, walls)

    @staticmethod
    def _stop(t: float, stop: float, walls) -> float:
        """Where a note held from t stops: at `stop`, or at a wall before it (a bar of the free line's)."""
        return min([stop] + [w for w in walls if t + EPS < w < stop])

    def _hold(self, line: list[Note], keep: list[int], end: float, must: set, rng: random.Random,
              walls=()) -> list[Note]:
        """The notes kept, each held to the next (the last to `end`; none into a bar of the free line's). A main note
        whose grace note is gone goes back on the grace note's time, and one sounded from a note gone is picked. A
        note held half a beat or more past its own length over other notes, not in its chord, moves to the chord's
        nearest note (not the note before or after it): always a fill's, a run's or the free line's, the tune's own
        as often as the pull is low."""
        out = []
        for k, i in enumerate(keep):
            n = line[i]
            if i and i - 1 not in keep and n.how in ("hammer", "pull"):  # the note it was sounded from is gone
                g = line[i - 1]
                if g.by == n.by and abs(g.end - n.t) < EPS and g.dur < 0.5 - EPS:  # its grace: back on its time
                    n = replace(n, t=g.t, dur=n.dur + g.dur)
                n = replace(n, how="pick")
            nxt = keep[k + 1] if k + 1 < len(keep) else None
            stop = self._stop(n.t, line[nxt].t if nxt is not None else end, walls)
            over = line[i + 1:nxt if nxt is not None else len(line)]
            if (any(x.midi != n.midi for x in over) and stop - n.t > n.dur + 0.5 - EPS and i not in must
                    and n.midi % 12 not in self.chord_at(n.t) and (n.by != "tune" or rng.random() < 1 - self.pull)):
                near = {out[-1].midi if out else None, line[nxt].midi if nxt is not None else None}
                chord = set(self.chord_at(n.t))  # in the line's own register (the free line's is moved after)
                c = [x for x in range(n.midi - 4, n.midi + 5) if x % 12 in chord and x not in near]
                if c:
                    n = replace(n, midi=min(c, key=lambda x: (abs(x - n.midi), x)), by="held")
            out.append(replace(n, dur=max(n.dur, stop - n.t)))
        return out

    @staticmethod
    def _choose(line: list[Note], want: int, must: set, score: dict) -> list[int]:
        """The notes kept (their places, in order): those that must be, then the rest by score, none the same note
        as the one kept before or after it within two beats (a repeated note is held instead)."""
        keep = set(must)
        for i in sorted((i for i in range(len(line)) if i not in must), key=lambda i: -score[i]):
            if len(keep) >= want:
                break
            before = max((k for k in keep if k < i), default=None)
            after = min((k for k in keep if k > i), default=None)
            if any(k is not None and line[k].midi == line[i].midi and abs(line[k].t - line[i].t) < 2 - EPS
                   for k in (before, after)):
                continue
            keep.add(i)
        return sorted(keep)

    def _restrike(self, line: list[Note], keep: list[int], end: float, walls=()) -> list[int]:
        """The notes kept, with a note struck where one left would be held, past its own length, over a chord it is
        not in: of the notes dropped there, the one sounding as that chord comes (else the first after it). A player
        simplifying still marks the changes."""
        keep = sorted(keep)
        k = 0
        while k < len(keep):
            n = line[keep[k]]
            nxt = keep[k + 1] if k + 1 < len(keep) else len(line)
            stop = self._stop(n.t, line[nxt].t if nxt < len(line) else end, walls)
            b, add = math.ceil(n.end - EPS), None
            while b < stop - EPS and add is None:
                if n.midi % 12 not in self.chord_at(b):
                    gone = [x for x in range(keep[k] + 1, nxt) if line[x].midi != n.midi and (
                        nxt >= len(line) or line[x].midi != line[nxt].midi or line[nxt].t - line[x].t >= 2 - EPS)]
                    on = [x for x in gone if line[x].t <= b + EPS]
                    add = on[-1] if on else next((x for x in gone if line[x].t > b), None)
                    if add is None:
                        break
                b += 1
            if add is not None:
                keep = sorted(keep + [add])
            else:
                k += 1
        return keep

    def _fill_to(self, mel: list[Note], want: int, j: int, t1: float, doubled: set,
                 rng: random.Random) -> list[Note]:
        """The phrase filled to `want` notes or more where it has room: its held notes (a beat or more; not a double
        stop's) filled as the pull fills them, in a random order, the arrival last."""
        land_i = self._landing(mel, j)
        cands = [i for i, n in enumerate(mel) if n.dur >= 1 - EPS and n.by in DECORATED
                 and round(n.t, 4) not in doubled]
        rng.shuffle(cands)
        cands.sort(key=lambda i: i == land_i)
        filled, have = {}, len(mel)
        for i in cands:
            if have >= want:
                break
            nxt = mel[i + 1].midi if i + 1 < len(mel) else self._next_tune_note(t1)
            f = self._fill(mel[i], nxt, rng)
            filled[i] = f
            have += len(f) - 1
        return [x for i, n in enumerate(mel) for x in filled.get(i, [n])]

    def _thin_free(self, notes: list[list], pass_i: int, a: int, t0: float, step0: int) -> list[list]:
        """A bar of the free line ([sixteenth, MIDI, length, velocity] each, in order) at a density under 1: held to
        the target against the tune's notes in the bar, its first note kept, the rest by the same weights as a
        phrase's (in the tune's beats), struck where the chord changes under a note left, each held to the next."""
        if not notes or self.density >= 1:
            return notes
        rng = random.Random(f"density {self.dense_seed} free {pass_i} {a}")
        t1 = t0 + BAR * self.k
        own = sum(1 for n in self.tune.melody() if t0 - EPS <= n.t < t1 - EPS)
        want = max(1, self._count(self.target(own, len(notes)), rng))
        if want >= len(notes):
            return notes
        beat = lambda x: t0 + (x[0] - step0) * self.k / 4  # noqa: E731
        line = [Note(beat(x), x[2] * self.k / 4, x[1] - self.shift, "pick", 0, "free") for x in notes]
        score = {i: self._weight(n, line[i - 1] if i else None, line[i + 1] if i + 1 < len(line) else None, rng)
                 for i, n in enumerate(line)}
        end = max(n.end for n in line)
        keep = self._restrike(line, self._choose(line, want, {0}, score), end)
        held = self._hold(line, keep, end, {0}, rng)
        return [[notes[i][0], h.midi + self.shift, h.dur * 4 / self.k, notes[i][3]] for i, h in zip(keep, held)]

    # -- played a bar of the synth at a time --

    def plan_bar(self, pass_i: int, a: int, step0: int, free: dict[int, list] | None = None) -> None:
        """The synth's bar `a` of the chart (its sixteenths from `step0`), on pass `pass_i`: the break's notes into
        `plan`. `free`: the free line's notes for this bar ({sixteenth: [(MIDI, length, velocity, offset)]}), the
        melodist's, played where the break takes the free line (all of them at pull 0)."""
        free = free or {}
        span = BAR * self.k
        t0, t1 = a * span, (a + 1) * span
        if self.pull <= EPS and self.dense():  # the free line, held to the density
            notes = [[st + frac, m, length, vel] for st in sorted(free) for m, length, vel, frac in free[st]]
            for at, m, length, vel in self._thin_free(notes, pass_i, a, t0, step0):
                st = int(math.floor(at + EPS))
                self.plan.setdefault(st, []).append((m, length, vel, at - st))
                self.heard.append((pass_i, Note(t0 + (at - step0) * self.k / 4, length * self.k / 4,
                                                m - self.shift, "pick", 0, "free")))
            return
        if self.pull <= EPS:
            for st, items in free.items():
                for m, length, vel, frac in items:
                    self.plan.setdefault(st, []).append((m, length, vel, frac))
                    self.heard.append((pass_i, Note(t0 + (st - step0 + frac) * self.k / 4, length * self.k / 4, m,
                                                    "pick", 0, "free")))
            return
        j = self.tune.phrase_of(t0)
        plan = self.phrase(pass_i, j)
        if any(isinstance(x, FreeSpan) and x.t0 - EPS <= t0 < x.t1 - EPS for x in plan):
            nxt = [x for x in plan if isinstance(x, Note) and x.t >= t1 - EPS and x.how != "double"]
            nxt_m = nxt[0].midi + self.shift if nxt else None
            notes = []
            for st in sorted(free):
                for m, length, vel, frac in free[st]:
                    notes.append([st + frac, m, length, vel])
            if self.dense():
                notes = self._thin_free(notes, pass_i, a, t0, step0)
            if notes:
                lo, hi = self.tune.range()
                mid = (lo + hi) / 2 + self.shift
                have = sum(x[1] for x in notes) / len(notes)
                octs = 12 * round((mid - have) / 12)
                for x in notes:
                    x[1] += octs
                    while x[1] < self.idiom.lo + self.shift:
                        x[1] += 12
                    while x[1] > self.idiom.hi + self.shift:
                        x[1] -= 12
                last = notes[-1]
                if nxt_m is not None and abs(last[1] - nxt_m) > 2:  # land by step on the tune's next note
                    side = 1 if last[1] > nxt_m else -1
                    last[1] = self._step(nxt_m - self.shift, t1 - 0.5, side) + self.shift
                for at, m, length, vel in notes:
                    st = int(math.floor(at + EPS))
                    self.plan.setdefault(st, []).append((m, length, vel, at - st))
                    self.heard.append((pass_i, Note(t0 + (at - step0) * self.k / 4, length * self.k / 4,
                                                    m - self.shift, "pick", 0, "free")))
            return
        for n in plan:
            if isinstance(n, Note) and t0 - EPS <= n.t < t1 - EPS:
                at = step0 + (n.t - t0) * 4 / self.k
                st = int(math.floor(at + EPS))
                how = f"slide-in:{n.bend}" if n.how == "slide-in" else n.how
                self.plan.setdefault(st, []).append((n.midi + self.shift, n.dur * 4 / self.k, accent(n), at - st, how))
                self.heard.append((pass_i, n))

    def at(self, step: int) -> list[tuple]:
        """What to play in this sixteenth: (MIDI, length in sixteenths, velocity, offset within it[, how])."""
        return self.plan.pop(step, [])


def accent(n: Note) -> float:
    """The meter's weight on a note of the tune's bar: 1, 3, 2 and 4, offbeats; a note sounded without a pick, or a
    double stop's added note, softer."""
    b = n.t % BAR
    if abs(b) < EPS:
        v = 1.0
    elif abs(b - 2) < EPS:
        v = 0.88
    elif abs(b - round(b)) < EPS:
        v = 0.78
    else:
        v = 0.9 if n.dur >= 1 - EPS else 0.68
    if n.how in LEGATO:
        v *= 0.75
    elif n.how == "double":
        v *= 0.8
    return v


# ---- measuring a line against the tune ----

def sounding(line: list[Note], t: float) -> Note | None:
    """The melody note sounding at t (the latest started)."""
    on = [n for n in line if n.how != "double" and n.t - EPS <= t < n.end - EPS]
    return max(on, key=lambda n: n.t) if on else None


def measure(line: list[Note], tune: Tune, chords: list[tuple[int, ...]] | None = None) -> dict:
    """How much of the tune a line (one pass, in its beats) keeps: the tune's notes on the strong beats (those
    starting on 1 or 3), the line sounding the same there (the pitch, and the pitch class: an octave moved); its
    arrivals sounding at their time (within an eighth); the line's notes that are the tune's own (onset and pitch);
    its notes a bar, and against the tune's (`density`); the tune's onsets where it strikes a note too
    (`onsets_kept`: its rhythm heard); each repeated phrase's notes at the same place and pitch class as the phrase
    it repeats (`repeats_alike`); with the chords (a beat each), the chord changes it strikes a note at, within an
    eighth before or a sixteenth after (`changes_struck`); and the moves made."""
    tm = tune.melody()
    pairs = [(n.t, n) for n in tm if strong(n.t) and n.t < tune.beats - EPS]
    same = pc = 0
    for t, n in pairs:
        x = sounding(line, t)
        if x is not None and x.midi == n.midi:
            same += 1
        if x is not None and x.midi % 12 == n.midi % 12:
            pc += 1
    arrs = [tune.arrival(j) for j in range(len(tune.phrases()))]
    hit = sum(any(abs(x.t - a.t) <= 0.5 + EPS and x.midi % 12 == a.midi % 12 for x in line if x.how != "double")
              for a in arrs)
    own = {(round(n.t, 3), n.midi) for n in tm}
    mel = [n for n in line if n.how != "double"]
    from collections import Counter
    moves = Counter(n.by for n in line if n.by != "tune")
    starts = sorted(n.t for n in mel)
    near = lambda t, lo, hi: any(t - lo - EPS <= x <= t + hi + EPS for x in starts)  # noqa: E731
    onsets = sum(near(n.t, 0.05, 0.05) for n in tm if n.t < tune.beats - EPS)
    alike, rep_n = 0, 0
    for j in range(len(tune.phrases())):
        i = tune.repeats(j)
        if i is None:
            continue
        (a0, a1), (b0, b1) = tune.phrases()[i], tune.phrases()[j]
        then = {(round(n.t - a0 * BAR, 3), n.midi % 12) for n in mel if a0 * BAR - EPS <= n.t < a1 * BAR - EPS}
        now = [(round(n.t - b0 * BAR, 3), n.midi % 12) for n in mel if b0 * BAR - EPS <= n.t < b1 * BAR - EPS]
        alike += sum(x in then for x in now)
        rep_n += len(now)
    extra = {}
    if chords:
        changes = [b for b in range(1, int(tune.beats)) if set(chords[b % len(chords)]) != set(chords[b - 1])]
        extra["changes_struck"] = sum(near(b, 0.5, 0.25) for b in changes) / max(1, len(changes))
    return {"strong_kept": same / max(1, len(pairs)), "strong_pc_kept": pc / max(1, len(pairs)),
            "onsets_kept": onsets / max(1, len([n for n in tm if n.t < tune.beats - EPS])),
            "repeats_alike": alike / max(1, rep_n), **extra,
            "arrivals_kept": hit / max(1, len(arrs)),
            "tune_notes": sum((round(n.t, 3), n.midi) in own for n in mel) / max(1, len(mel)),
            "notes_a_bar": len(mel) / tune.bars, "density": len(mel) / max(1, len(tm)),
            "moves": dict(sorted(moves.items()))}


def chart_beats(state: dict, k: int, beats: int, shift: int = 0) -> list[tuple[int, ...]]:
    """The loop's chord on each of the tune's beats over a pass (pitch classes, root first), in the tune's key
    (`shift` semitones from it to the key played)."""
    from . import music
    from .harmony import at_step, loop_chord
    h = state["harmony"]
    slots = music.slots_of(state["tones"])
    out = []
    for i in range(beats):
        _, idx, _ = at_step(h, int(round(i * 4 / k)))
        pcs = loop_chord(state["key"], slots, h, idx)[0]
        seen = []
        for p in pcs:
            q = (p - shift) % 12
            if q not in seen:
                seen.append(q)
        out.append(tuple(seen))
    return out


def tune_for(state: dict):
    """The tune whose chart the harmony plays (its name and `presets.TUNE_MELODIES` entry), or None."""
    from .presets import HARMONY, TUNE_MELODIES
    h = state["harmony"]
    if h.get("style") != "Loop":
        return None
    for name, src in TUNE_MELODIES.items():
        if HARMONY[name][1]["harmony"]["loop"] == h["loop"]:
            return name, src
    return None
