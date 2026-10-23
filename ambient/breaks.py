"""The Tune line on the synth's grid: a break on a tune's melody, from as written to the free line (2026-10-22).

The break itself, what an improvising bluegrass player does with a tune's melody, and how an instrument plays it, are
the transcription project's: its `transcribe.breaks` (the style: the phrase, its arrival, what a player keeps and
plays with, the pull, the density, `measure`) and `transcribe.idioms` (an instrument's range and ornaments). They were
built here and moved there on 2026-10-22 (that project's card `ud-member-breaks`), so that the Ugly Duckling String
Band's members take breaks by the same rules; the synth plays the same notes as before (PLAN.md, "Members' breaks in
the band": every note the conductor sends, over the four tunes, five voices, five pulls, four densities and ten
seeds). This module is the synth's side:

- finding that project (`project_root`, `use_project`; `$AMBIENT_TRANSCRIPTION` first) and importing its package
  from its `pipeline/src` (the same copy the band uses on the unit);
- a tune's key from its folder (`load_tune`, cached: `tunes/dobro/<tune>/<tune>.musicxml`, read by
  `transcribe.breaks.read_tune`);
- the loop's chords a beat at a time (`chart_beats`) and which tune's chart the harmony plays (`tune_for`,
  `presets.TUNE_MELODIES`);
- the idioms by the synth's voice names (`IDIOMS`: the dobro, the fiddle, the mandolin, the banjo; any other voice,
  the guitars among them, `any`, as before);
- the synth's `Break`: the style's, played a bar of the synth at a time into the conductor's grid (`plan_bar`, `at`),
  where the break takes the free line playing the melodist's bars (held to the note density by the style's
  `thin_free`), moved by octaves to the tune's register and landing by step on the tune's next note.

The rules themselves are told in `transcribe.breaks`' docstring; which are style and which idiom, in that project's
`docs/knowledge-layers.md`.
"""

from __future__ import annotations

import math
import os
import random
import sys
from functools import lru_cache
from pathlib import Path

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


def _import_path() -> None:
    """The transcription project's package on the path: its breaks are the style the Tune line plays."""
    root = project_root()
    if root is None or not (root / "pipeline" / "src" / "transcribe" / "breaks.py").is_file():
        raise ImportError("the Tune line's breaks are the transcription project's (transcribe.breaks), and no "
                          "pipeline/src with them was found ($AMBIENT_TRANSCRIPTION, then " + ", ".join(ROOTS)
                          + "); tools/deploy copies it to the unit")
    src = str(root / "pipeline" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


_import_path()
from transcribe import breaks as style  # noqa: E402
from transcribe.breaks import (BAR, DECORATED, DENSITY_HI, DENSITY_LO, EPS, LEGATO, MAJOR, PARAMS,  # noqa: E402,F401
                               BreakParams, FreeSpan, Note, Tune, accent, bell, density_of, density_setting, measure,
                               sounding, strong)
from transcribe.idioms import IDIOMS as _IDIOMS  # noqa: E402
from transcribe.idioms import Idiom  # noqa: E402,F401

# the synth's voices that have an idiom of their own (any other: `any`)
IDIOMS = {"Dobro": _IDIOMS["dobro"], "Fiddle": _IDIOMS["fiddle"], "Mandolin": _IDIOMS["mandolin"],
          "Banjo": _IDIOMS["banjo"], "any": _IDIOMS["any"]}


@lru_cache(maxsize=16)
def load_tune(folder: str, key: str, bars: int, project: str | None = None, parts: tuple[int, ...] = ()) -> Tune:
    """One pass of a tune's key (`tunes/dobro/<folder>/<folder>.musicxml`): its first `bars` bars from bar 1, and
    the pickup before bar 1, which is played into the next pass (`transcribe.breaks.read_tune`). `key`: the key's
    name (`music.KEYS`). `parts`: the bars of each part in the pass, adding up to `bars` (none: one part)."""
    from .music import KEYS
    if parts and sum(parts) != bars:
        raise ValueError(f"{folder}: its parts {parts} are not its {bars} bars")
    root = Path(project).expanduser() if project else project_root()
    if root is None:
        raise FileNotFoundError("the transcription project's tunes are not here")
    return style.read_tune(root / "tunes" / "dobro" / folder / f"{folder}.musicxml", KEYS.index(key), bars,
                           tuple(parts), folder)


class Break(style.Break):
    """A break on a tune (`transcribe.breaks.Break`), played a bar of the synth at a time (`plan_bar`, `at`) into the
    conductor's grid; where it takes the free line, the melodist's bars.

    `chords`: a beat each over one pass, the chord sounding (pitch classes, root first) in the tune's own key.
    `k`: the tune's bars to one of the synth's (2: laid in two). `shift`: semitones from the tune's key to the key
    played. `seed`: the break's own dice. `density`: its notes against the tune's (1: as its pull makes it)."""

    def reset(self) -> None:
        super().reset()
        self.plan: dict[int, list] = {}  # the synth's sixteenth -> [(MIDI, length, velocity, offset, how)]
        self.heard: list[tuple[int, Note]] = []  # (pass, note in the pass's beats) as played

    def _thin_free(self, notes: list[list], pass_i: int, a: int, t0: float, step0: int) -> list[list]:
        """A bar of the free line ([sixteenth, MIDI, length, velocity] each, in order) at a density under 1: held to
        the target against the tune's notes in the bar (`thin_free`), on the bar's own dice."""
        if not notes or self.density >= 1:
            return notes
        rng = random.Random(f"density {self.dense_seed} free {pass_i} {a}")
        beat = lambda x: t0 + (x[0] - step0) * self.k / 4  # noqa: E731
        line = [Note(beat(x), x[2] * self.k / 4, x[1] - self.shift, "pick", 0, "free") for x in notes]
        got = self.thin_free(line, t0, t0 + BAR * self.k, rng)
        if got is None:
            return notes
        keep, held = got
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
