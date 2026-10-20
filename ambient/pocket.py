"""The band's pocket: where each part sits against the band's beat (2026-10-20).

The transcription project's `docs/pocket-parameters.md` has the schema, the measurements and the presets. The
player chose "pushed" (the pushed backbeat: the close mics' defaults) in its review of 2026-10-20, and rated "even"
better than the band as it was too. Offsets in ms against the band's beat, + late, - early; the scatter a standard
deviation (ms):

| preset | bass | chords (comp), on the beat / on its "and" | chop | scatter |
|---|---|---|---|---|
| pushed (the default) | -6 | +2 / -5 | -4 | 4 |
| even | -8 | 0 / 0 | -3 | 4 |
| none | 0 | 0 / 0 | 0 | 0 (the band as it was) |

- **The counts.** The band's beat is the recordings' 1 and 3, its "and" their 2 and 4 (the doc, "The counts"). A
  note's class is where it falls in its beat (`note_class`: within a quarter of a beat of the "and", the "and"; else
  the beat). The chords strum on every beat, so they sit where the recordings' guitar booms (+2 in "pushed"); their
  -5 on the "and" (the guitar's strum there) is for chords that play the "and" (the boom-chuck), which the band does
  not yet: voiced from one play, its boom and its strum would each take their own class's. The bass plays only on
  the beat and the chop only on the "and": each part's other class is set as its own (the player: the bass, "its
  notes").
- **Scatter** per play and class (a strum's or a chop's notes move together, its spread kept): a normal draw with the
  part's standard deviation, clipped at `CLIP` of them. It has its own generator, seeded by the pocket's seed, the
  part, the class and the beat (`Pocket.draw`), so a play's draw does not depend on the order the cues come in: a
  render and the live band, given the same cues, play the same notes. The player could not hear 4 ms; it stays.
- **Where it acts:** the band player (`ambient/bandplayer.py`, `BandPlayer.cue`), on the notes the voicing gives
  (`transcribe.bandvoice.play_notes`, the same in the transcription project's offline render) in the band's own time,
  before the stream clock maps them to the engine's. The band's clock, its beats and what the parts decide are not
  touched. An offline render places the voicing's notes with the same `Pocket.place`.
- **Apart from latency.** `lead_s` (how far ahead the band decides) and the stream clock's offset (the device's round
  trip) put the band's beat where the player's is; the pocket is style, around that beat. They add; neither is set to
  fix the other. The engine judges a note's lateness (`bandplayer.LATE_S`) against its shifted time, so a part late by
  design is not dropped for it.
- **The lead an early part takes.** A note moved early must reach the engine before its frame is computed: it spends
  that much of the margin the band's lead leaves when its cue reaches the player (`lead_s`, 50 ms, less the capture's
  block, the listening, the engine's block, the round trip: at least 22-25 ms on the control unit, median 33,
  PLAN.md). The earliest a pocket can put a note is its most negative offset less `CLIP` scatters
  (`Pocket.earliest_ms`: "pushed" -16 ms, "even" -18); one that would go earlier than `MAX_EARLY_MS` is refused.
- **Found with it** (PLAN.md, "The pocket"): the beat follower counts the player's rises only as far as they stand over
  the echo canceller's estimate of the band; a band ahead of the player's attacks lets a cold canceller predict them,
  and with no chart ("Any of my tunes") on a guitar the band could hear the player stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

PARTS = ("bass", "comp", "chop")
CLASSES = ("beat", "and")
KEYS = CLASSES + ("scatter",)
SEED = 20261020
CLIP = 2.5  # the scatter's draws clipped at this many standard deviations (1.2% of them; the sd stays 0.99 of it)
MAX_EARLY_MS = 20.0  # no note moved earlier than this: under the margin the band's lead leaves (module docstring)
MAX_LATE_MS = 30.0  # nor later: the bass's and the chords' lateness allowed (`bandplayer.LATE_S`)

PRESETS: dict[str, dict[str, dict[str, float]]] = {
    "pushed": {"bass": {"beat": -6.0, "and": -6.0, "scatter": 4.0},
               "comp": {"beat": 2.0, "and": -5.0, "scatter": 4.0},
               "chop": {"beat": -4.0, "and": -4.0, "scatter": 4.0}},
    "even": {"bass": {"beat": -8.0, "and": -8.0, "scatter": 4.0},
             "comp": {"beat": 0.0, "and": 0.0, "scatter": 4.0},
             "chop": {"beat": -3.0, "and": -3.0, "scatter": 4.0}},
    "none": {p: {"beat": 0.0, "and": 0.0, "scatter": 0.0} for p in PARTS},
}
DEFAULT = "pushed"


def note_class(t: float, beat_t: float, spb: float) -> str:
    """Where a note at `t` falls in the beat at `beat_t` (`spb` long): "and" within a quarter of a beat of its half,
    else "beat"."""
    frac = ((t - beat_t) / spb) % 1.0 if spb > 0 else 0.0
    return "and" if 0.25 <= frac < 0.75 else "beat"


@dataclass(frozen=True)
class Pocket:
    """A pocket: per part, an offset (ms, + late) for each class of note and a scatter (ms, a standard deviation)."""
    name: str
    parts: dict = field(default_factory=dict)  # part -> {"beat": ms, "and": ms, "scatter": ms}
    seed: int = SEED

    def offset_ms(self, part: str, cls: str) -> float:
        return float(self.parts.get(part, {}).get(cls, 0.0))

    def scatter_ms(self, part: str) -> float:
        return float(self.parts.get(part, {}).get("scatter", 0.0))

    def draw(self, part: str, cls: str, i: int) -> float:
        """The scatter's standard normal for one play (the part's, in its class, on beat `i`), clipped at `CLIP`."""
        rng = np.random.default_rng([self.seed, PARTS.index(part), CLASSES.index(cls), max(0, int(i))])
        return float(np.clip(rng.standard_normal(), -CLIP, CLIP))

    def shift_ms(self, part: str, cls: str, i: int) -> float:
        """How far the pocket moves a play of `part` in class `cls` on beat `i` (ms, + late)."""
        if part not in PARTS:
            return 0.0
        sd = self.scatter_ms(part)
        return self.offset_ms(part, cls) + (sd * self.draw(part, cls, i) if sd else 0.0)

    def place(self, notes: list, part: str, i: int, beat_t: float, spb: float) -> tuple[list, float]:
        """The voicing's notes for one play on beat `i` ((start s, length s, channel, key, velocity), the band's time;
        the beat at `beat_t`, `spb` long) moved by the pocket: each note by its class's shift, so the notes of a class
        move together (a strum keeps its spread). Returns them and the first note's shift (ms); the same list when
        nothing moves."""
        shifts: dict[str, float] = {}
        for t, *_ in notes:
            cls = note_class(t, beat_t, spb)
            if cls not in shifts:
                shifts[cls] = self.shift_ms(part, cls, i)
        if not any(shifts.values()):
            return notes, 0.0
        out = [(t + shifts[note_class(t, beat_t, spb)] / 1000.0, *rest) for t, *rest in notes]
        return out, shifts[note_class(notes[0][0], beat_t, spb)]

    def earliest_ms(self) -> float:
        """The earliest the pocket can put a note (ms; 0 if never early)."""
        return min([0.0] + [self.offset_ms(p, c) - CLIP * self.scatter_ms(p) for p in PARTS for c in CLASSES])

    def latest_ms(self) -> float:
        return max([0.0] + [self.offset_ms(p, c) + CLIP * self.scatter_ms(p) for p in PARTS for c in CLASSES])

    def describe(self) -> dict:
        """For the session's log and the status: enough to place every note again."""
        return {"name": self.name, "parts": {p: dict(v) for p, v in self.parts.items()}, "seed": self.seed,
                "clip": CLIP, "earliest_ms": round(self.earliest_ms(), 2), "latest_ms": round(self.latest_ms(), 2)}

    def words(self) -> str:
        """The pocket in plain words, for the page: the classes the band plays (the bass and the chords on the beat,
        the chop on its "and")."""
        if not any(self.offset_ms(p, c) or self.scatter_ms(p) for p in PARTS for c in CLASSES):
            return "Every note exactly on the beat or its \"and\", as the band always played."
        bits = []
        for part, name, cls, where in (("bass", "the bass", "beat", "the beat"), ("comp", "the chords", "beat", "it"),
                                       ("chop", "the chop", "and", "its \"and\"")):
            ms = self.offset_ms(part, cls)
            bits.append(f"{name} on {where}" if ms == 0 else
                        f"{name} {abs(ms):g} ms {'ahead of' if ms < 0 else 'behind'} {where}")
        text = ", ".join(bits)
        sd = max(self.scatter_ms(p) for p in PARTS)
        if sd:
            text += f"; each note moved a little at random ({sd:g} ms typical)"
        return text[0].upper() + text[1:] + "."


def make(name: str = DEFAULT, overrides: dict | None = None, seed: int = SEED) -> Pocket:
    """A preset (`PRESETS`), with per-part overrides ({part: {"beat" | "and" | "scatter": ms}}). Raises ValueError for
    an unknown preset, part or key, a negative scatter, or a note that could go earlier than `MAX_EARLY_MS` or later
    than `MAX_LATE_MS`."""
    if name not in PRESETS:
        raise ValueError(f"no pocket {name!r}: {', '.join(PRESETS)}")
    parts = {p: dict(v) for p, v in PRESETS[name].items()}
    for part, given in (overrides or {}).items():
        if part not in PARTS:
            raise ValueError(f"the pocket has no part {part!r}: {', '.join(PARTS)}")
        if not isinstance(given, dict):
            raise ValueError(f"the pocket's {part}: a table of {', '.join(KEYS)} (ms)")
        for k, v in given.items():
            if k not in KEYS:
                raise ValueError(f"the pocket's {part} has no {k!r}: {', '.join(KEYS)}")
            try:
                parts[part][k] = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"the pocket's {part} {k}: a number of ms, not {v!r}")
        if parts[part]["scatter"] < 0:
            raise ValueError(f"the pocket's {part} scatter: 0 or more ms")
    pk = Pocket(name, parts, int(seed))
    if pk.earliest_ms() < -MAX_EARLY_MS:
        raise ValueError(f"the pocket would put a note {-pk.earliest_ms():g} ms early (its offset less {CLIP:g} "
                         f"scatters): at most {MAX_EARLY_MS:g}, the band's lead leaves little more")
    if pk.latest_ms() > MAX_LATE_MS:
        raise ValueError(f"the pocket would put a note {pk.latest_ms():g} ms late: at most {MAX_LATE_MS:g}")
    return pk


NONE = make("none")
