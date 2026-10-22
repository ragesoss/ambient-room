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

**The phrase.** Four of the tune's bars (a part's remainder joined to its last phrase). Its **arrival** is the
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

**Its own dice.** A break has a random generator of its own (`seed`): the melody's choices alone, so the band under
it is the same at every setting and seed (the A/B clips). Which rules are style and which idiom is recorded in the
transcription project's `docs/knowledge-layers.md`.
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
    its bars, and the pickup into bar 1 (`lead_in`, before it)."""
    name: str
    key: int  # the home note's pitch class
    bars: int
    notes: list[Note]
    lead_in: list[Note] = field(default_factory=list)
    phrase_bars: int = 4

    @property
    def beats(self) -> float:
        return self.bars * BAR

    def melody(self) -> list[Note]:
        return [n for n in self.notes if n.how != "double"]

    def phrases(self) -> list[tuple[int, int]]:
        """Bars [start, end) of each phrase: phrase_bars each, a remainder joined to the last."""
        n = max(1, self.bars // self.phrase_bars)
        out = [(i * self.phrase_bars, (i + 1) * self.phrase_bars) for i in range(n)]
        out[-1] = (out[-1][0], self.bars)
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
def load_tune(folder: str, key: str, bars: int, project: str | None = None) -> Tune:
    """One pass of a tune's key (`tunes/dobro/<folder>/<folder>.musicxml`): its first `bars` bars from bar 1, and
    the pickup before bar 1, which is played into the next pass (its last bar's notes from there on cut)."""
    from .music import KEYS
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
    return Tune(folder, KEYS.index(key), bars, notes, lead_in)


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


PARAMS = BreakParams()


class Break:
    """A break on a tune: its phrases planned one at a time (`phrase`), each pass a little further from the tune, and
    played a bar of the synth at a time (`plan_bar`, `at`) into the conductor's grid.

    `chords`: a beat each over one pass, the chord sounding (pitch classes, root first) in the tune's own key.
    `k`: the tune's bars to one of the synth's (2: laid in two). `shift`: semitones from the tune's key to the key
    played. `seed`: the break's own dice."""

    def __init__(self, tune: Tune, chords: list[tuple[int, ...]], pull: float, seed=None, k: int = 1,
                 shift: int = 0, idiom: Idiom | None = None, params: BreakParams = PARAMS):
        self.tune, self.chords, self.k, self.shift = tune, chords, k, shift
        self.pull = pull
        self.rng = random.Random(seed)
        self.idiom = idiom or IDIOMS["any"]
        self.params = params
        self.first_pass = 0  # passes before it are not counted as later passes
        lo, hi = tune.range()
        self.lo, self.hi = max(self.idiom.lo, lo - 3), min(self.idiom.hi, hi + 5)
        self.reset()

    def reset(self) -> None:
        self.done: dict[tuple[int, int], list] = {}  # (pass, phrase) -> its plan
        self.plan: dict[int, list] = {}  # the synth's sixteenth -> [(MIDI, length, velocity, offset, how)]
        self.heard: list[tuple[int, Note]] = []  # (pass, note in the pass's beats) as played

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

    def phrase(self, pass_i: int, j: int) -> list:
        """Phrase j's notes on pass `pass_i` (beats from the pass's start), and the free stretches in it."""
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
        if d > p.free_from:
            pf = ((d - p.free_from) / (1 - p.free_from)) ** 1.5
            land = {self._app_bar(n.t) for n in [arr, *approach]}
            for a in range(self._app_bar(t0), self._app_bar(t1 - EPS) + 1):
                if a not in land and rng.random() < pf:
                    free.add(a)
        span = BAR * self.k
        if free:  # the tune's notes there left out, and none ringing into them
            mel = [n for n in mel if self._app_bar(n.t) not in free]
            starts = sorted(a * span for a in free)
            mel = [replace(n, dur=min(n.dur, min([s for s in starts if s > n.t + EPS], default=n.end) - n.t))
                   for n in mel]

        # a strong note substituted by another tone of its chord
        keep = 1.0 if d <= p.keep_from else 1 - (1 - p.keep_floor) * ((d - p.keep_from) / (1 - p.keep_from)) ** 1.5
        out = []
        for n in mel:
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
                    and rng.random() < p.anticipate * d):
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
            chance = p.fill * d ** 0.7 * (0.5 if n == arr else 1.0)
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
            chance = p.passing * d * (0.3 if n in after else 1.0)
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

    def _fill(self, n: Note, nxt: int | None) -> list[Note]:
        """A held note as eighths (or a roll's triplets): its own pitch first, the rest moving on to the next."""
        rng = self.rng
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

    # -- played a bar of the synth at a time --

    def plan_bar(self, pass_i: int, a: int, step0: int, free: dict[int, list] | None = None) -> None:
        """The synth's bar `a` of the chart (its sixteenths from `step0`), on pass `pass_i`: the break's notes into
        `plan`. `free`: the free line's notes for this bar ({sixteenth: [(MIDI, length, velocity, offset)]}), the
        melodist's, played where the break takes the free line (all of them at pull 0)."""
        free = free or {}
        span = BAR * self.k
        t0, t1 = a * span, (a + 1) * span
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


def measure(line: list[Note], tune: Tune) -> dict:
    """How much of the tune a line (one pass, in its beats) keeps: the tune's notes on the strong beats (those
    starting on 1 or 3), the line sounding the same there (the pitch, and the pitch class: an octave moved); its
    arrivals sounding at their time (within an eighth); the line's notes that are the tune's own (onset and pitch);
    and the moves made."""
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
    return {"strong_kept": same / max(1, len(pairs)), "strong_pc_kept": pc / max(1, len(pairs)),
            "arrivals_kept": hit / max(1, len(arrs)),
            "tune_notes": sum((round(n.t, 3), n.midi) in own for n in mel) / max(1, len(mel)),
            "notes_a_bar": len(mel) / tune.bars, "moves": dict(sorted(moves.items()))}


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
