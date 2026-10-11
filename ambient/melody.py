"""Melody with a shape: phrases and motifs in bars, aware of the chords.

Time is the conductor's grid: 16 sixteenths to the bar. A motif is a bar
(sometimes two) of rhythm made from beat-sized cells (a quarter, two
eighths, a dotted eighth and a sixteenth ...), with a contour: steps and
leaps in the scale. Phrases are bars in a form, such as the sentence
(idea, idea varied, contrast, cadence). Each phrase starts on a bar line,
or with pickup notes leading into it.

Pitches are found bar by bar, against the chord sounding then: each bar's
figure starts on a chord tone, strong beats are chord tones (now and then a
dissonance that resolves by step), and a phrase ends on the root (an
answer) or on another chord tone (a question). When the harmony wanders,
the conductor asks cadence_wish() before it picks a chord, so the harmony
leans toward the home chord under an answer and toward V or IV under a
question. When the harmony has a form (a functional cycle or a loop), it
leads: a phrase that ends over the home chord is an answer, else a question.
"""

import random

STYLES = {
    "Scattered": "single notes at random times, wandering",
    "Motif": "a one-bar figure repeated every bar like a riff, following the chords and slowly changing",
    "Phrases": "phrases in bars: an idea, its variation, a contrast, a cadence; questions answered on the home chord",
}

STEPS = 16

# Rhythm cells: (span in sixteenths, [(onset, length)], syncopated?). The
# last three run in thirty-second notes: onsets between the sixteenths.
CELLS = {
    "q": (4, [(0, 4)], False), "ee": (4, [(0, 2), (2, 2)], False), "dot": (4, [(0, 3), (3, 1)], False),
    "snap": (4, [(0, 1), (1, 3)], True), "ssss": (4, [(0, 1), (1, 1), (2, 1), (3, 1)], False),
    "ess": (4, [(0, 2), (2, 1), (3, 1)], False), "sse": (4, [(0, 1), (1, 1), (2, 2)], False),
    "r": (4, [], False), "re": (4, [(2, 2)], True), "res": (4, [(2, 1), (3, 1)], True),
    "h": (8, [(0, 8)], False), "dq": (8, [(0, 6), (6, 2)], False), "qr": (8, [(0, 4)], False),
    "syn": (8, [(0, 2), (2, 4), (6, 2)], True), "sync2": (8, [(2, 4), (6, 2)], True),
    "tttt": (4, [(i / 2, 0.5) for i in range(8)], False), "tts": (4, [(0, 0.5), (0.5, 0.5), (1, 1), (2, 1), (3, 1)], False),
    "stt": (4, [(0, 1), (1, 1), (2, 0.5), (2.5, 0.5), (3, 1)], False),
}
# How likely each cell is when the line is sparse, middling or busy (Notes)
SPARSE = {"h": 3, "dq": 2, "q": 3, "r": 1.5, "qr": 1.2, "ee": 0.5, "syn": 0.5, "sync2": 0.5, "re": 0.4}
MIDDLE = {"q": 3, "ee": 3, "dot": 1.5, "dq": 1.5, "h": 1, "ess": 1, "sse": 1, "r": 0.7, "syn": 1, "snap": 0.6, "re": 0.6}
BUSY = {"ee": 3, "ssss": 2, "ess": 2, "sse": 2, "dot": 1.5, "snap": 1, "q": 1, "res": 0.8, "syn": 0.8}
# ... and past busy: running sixteenths (a fiddle's unbroken eighths), then frenetic runs of thirty-seconds
RUNNING = {"ssss": 8, "ess": 1, "sse": 1, "tts": 0.6, "stt": 0.6}
FRENETIC = {"tttt": 4, "tts": 3, "stt": 3, "ssss": 1.5}

FORMS = {
    1: [["cad"]],
    2: [["a", "cad"], ["a", "a2"]],
    4: [["a", "a2", "b", "cad"], ["a", "b", "a2", "cad"], ["a", "a2", "a3", "cad"]],
    8: [["a", "a2", "b", "b2", "a", "a3", "c", "cad"], ["a", "b", "a2", "cad", "a", "b2", "c", "cad"]],
}
CONTOURS = ["arch", "rise", "fall", "valley"]


def phrase_bars(phrase: float) -> int:
    """Bars per phrase: 1, 2, 4 or 8."""
    return [1, 2, 4, 8][min(3, int(phrase * 4))]


def busyness(notes: float) -> tuple[float, float]:
    """The Notes control, for a shaped line: (d, x). d blends sparse, middle
    and busy rhythms, from 0 to 1 at Notes 0.75 (below 0.6, Notes itself);
    x, past 0.75, blends busy into running sixteenths (x 0.5) and frenetic
    thirty-seconds (x 1, at Notes 1)."""
    if notes <= 0.6:
        return notes, 0.0
    if notes <= 0.75:
        return 0.6 + (notes - 0.6) * 0.4 / 0.15, 0.0
    return 1.0, (notes - 0.75) / 0.25


def accent(onset: int, length: int) -> float:
    """The meter's weight on a note: beat 1, beat 3, beats 2 and 4, offbeats."""
    if onset % STEPS == 0:
        return 1.0
    if onset % 8 == 0:
        return 0.88
    if onset % 4 == 0:
        return 0.78
    return 0.9 if length >= 3 else 0.68  # a long note off the beat is a syncopation: lean on it


class Melodist:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.reset()

    def reset(self) -> None:
        self.phrase: dict | None = None
        self.motif: dict | None = None
        self.plan: dict = {}  # absolute step -> [(MIDI note, length, velocity, offset within the step)]
        self.bar = -1
        self.prev_idx: int | None = None
        self.kind = "answer"  # the last phrase's: the next is a question

    # ---- rhythm and contour ----

    @staticmethod
    def _weights(density: float, sync: float) -> dict:
        """How likely each rhythm cell is at this busyness and syncopation."""
        d, x = busyness(density)
        w = {}
        for name in CELLS:
            w[name] = (SPARSE.get(name, 0) * (1 - d) ** 2 + MIDDLE.get(name, 0) * 2 * d * (1 - d)
                       + BUSY.get(name, 0) * d * d)
            if x > 0:  # past busy: into running sixteenths, then frenetic thirty-seconds
                w[name] = (w[name] * (1 - x) ** 2 + RUNNING.get(name, 0) * 2 * x * (1 - x)
                           + FRENETIC.get(name, 0) * x * x)
            if CELLS[name][2]:
                w[name] *= 0.15 + 3.5 * sync
        return w

    def _cells(self, density: float, sync: float, beats: int) -> list:
        rng = self.rng
        w = self._weights(density, sync)
        out, left = [], beats * 4
        while left > 0:
            fit = {k: v for k, v in w.items() if CELLS[k][0] <= left and v > 0}
            name = rng.choices(list(fit), weights=list(fit.values()))[0]
            out.append(name)
            left -= CELLS[name][0]
        return out

    @staticmethod
    def _on_beat(cell: str) -> bool:
        hits = CELLS[cell][1]
        return bool(hits) and hits[0][0] == 0

    def _rhythm(self, cells: list) -> list[tuple[int, int]]:
        t, notes = 0, []
        for name in cells:
            span, hits, _ = CELLS[name]
            notes += [(t + o, l) for o, l in hits]
            t += span
        return notes

    def new_motif(self, s: dict, contrast: dict | None = None) -> dict:
        """A bar of rhythm and a contour. A contrast differs from `contrast`:
        sparser if it was busy (and the reverse), moving the other way."""
        rng, mel, sh = self.rng, s["melody"], s["shape"]
        density = sh["notes"]
        if contrast is not None:  # sparser or busier, but not past busy unless the line is already there
            density = max(0.05, min(max(density, 0.75), density + (-0.3 if contrast["busy"] else 0.3)))
        for _ in range(6):
            cells = self._cells(density, mel["syncopation"], 4)
            # a phrase starts on the downbeat, unless it is syncopated on purpose
            if not self._on_beat(cells[0]) and rng.random() > mel["syncopation"]:
                cells[0] = "q" if CELLS[cells[0]][0] == 4 else rng.choice(["h", "dq"])
            rhythm = self._rhythm(cells)
            if len(rhythm) >= 2:
                break
        else:
            cells, rhythm = ["q", "q", "h"], self._rhythm(["q", "q", "h"])
        direction = rng.choice([1, -1]) if contrast is None else -contrast["direction"]
        steps, last = [0], 0
        for _ in rhythm[1:]:
            if abs(last) >= 3:  # after a leap, a step back the other way
                d = -1 if last > 0 else 1
            elif rng.random() < 0.1 + 0.6 * mel["leaps"]:
                d = rng.choice([2, 3, 4] if mel["leaps"] > 0.5 else [2, 2, 3]) * (direction if rng.random() < 0.7 else -direction)
            else:  # by step; a note repeated now and then, rarely in a fast run
                again = 1.0 if sh["notes"] < 0.6 else max(0.1, 1 - 2.5 * (sh["notes"] - 0.6))
                d = rng.choices([1, 0, -1], weights=[2, again, 1])[0] * direction if rng.random() < 0.75 else rng.choice([-1, 1])
            steps.append(d)
            last = d
        return {"cells": cells, "rhythm": rhythm, "steps": steps, "direction": direction,
                "busy": len(rhythm) > 5}

    def _vary(self, m: dict, s: dict, amount: float) -> dict:
        """The motif developed, keeping its meter: a pitch moved, a cell swapped, turned over."""
        rng = self.rng
        m = {**m, "steps": list(m["steps"]), "cells": list(m["cells"])}
        for _ in range(1 + int(amount * 2.5)):
            r = rng.random()
            if r < 0.5 and len(m["steps"]) > 1:
                i = rng.randrange(1, len(m["steps"]))
                m["steps"][i] += rng.choice([-1, 1])
            elif r < 0.8:  # a cell swapped for another of the same span: the bar keeps its meter
                i = rng.randrange(len(m["cells"]))
                span = CELLS[m["cells"][i]][0]
                w = self._weights(s["shape"]["notes"], s["melody"]["syncopation"])  # only cells this busyness plays
                same = [k for k, c in CELLS.items() if c[0] == span and c[1] and k != m["cells"][i] and w.get(k, 0) > 0
                        and (i or self._on_beat(k) or rng.random() < s["melody"]["syncopation"])]
                if same:
                    m["cells"][i] = rng.choice(same)
                    rhythm = self._rhythm(m["cells"])
                    if len(rhythm) >= 2:
                        m["rhythm"] = rhythm
                        steps = m["steps"][:len(rhythm)]
                        while len(steps) < len(rhythm):
                            steps.append(rng.choice([1, -1]))
                        m["steps"] = steps
            else:  # upside down
                m["steps"] = [0] + [-x for x in m["steps"][1:]]
                m["direction"] = -m["direction"]
        return m

    # ---- phrases ----

    def begin_bar(self, bar: int, s: dict, cycle: tuple[int, int] | None = None) -> None:
        """At each bar line, before the chord: start a phrase if one is due.
        cycle: (this bar's place in a chart, the chart's length in bars):
        a phrase starts with the chart and ends by its end."""
        self.bar = bar
        if s["melody"]["style"] == "Scattered":
            return
        if cycle and cycle[0] == 0 and self.phrase is not None and self.phrase["start"] != bar:
            self.phrase["end"] = bar  # the chart starts again: so does the melody
        if self.phrase is None or bar >= self.phrase["end"]:
            self._start_phrase(bar, s, None if cycle is None else cycle[1] - cycle[0])

    def _start_phrase(self, bar: int, s: dict, bars_left: int | None = None) -> None:
        rng, mel = self.rng, s["melody"]
        n = phrase_bars(mel["phrase"])
        if bars_left:  # no further than the chart's end: the longest form that fits
            n = max(k for k in FORMS if k <= max(1, min(n, bars_left)))
        if self.phrase is not None:
            bar = max(bar, self.phrase["end"])
        # bars count from the start, so phrases and chord changes share bar lines
        if self.motif is None or rng.random() < 0.1 + 0.5 * mel["variation"] ** 2:
            self.motif = self.new_motif(s)
        elif rng.random() < 0.3 + 0.6 * mel["variation"]:
            self.motif = self._vary(self.motif, s, mel["variation"] * 0.6)
        if mel["style"] == "Motif":
            form, kind = ["a"] * n, None
        else:
            form = rng.choice(FORMS[n])
            kind = "question" if self.kind == "answer" else "answer"
            self.kind = kind
        self.phrase = {"start": bar, "end": bar + n, "form": form, "kind": kind,
                       "contour": rng.choice(CONTOURS), "parts": {"a": self.motif}}

    def cadence_wish(self, bar: int, chord_bars: int) -> str | None:
        """'answer' or 'question' if a chord starting at `bar` for `chord_bars`
        bars will sound under this phrase's last bar (and is not its first)."""
        ph = self.phrase
        if not ph or not ph["kind"]:
            return None
        last = ph["end"] - 1
        if ph["start"] < bar <= last < bar + chord_bars:
            return ph["kind"]
        return None

    def _part(self, label: str, s: dict) -> dict:
        ph, parts, var = self.phrase, self.phrase["parts"], s["melody"]["variation"]
        if label not in parts:
            a = parts["a"]
            if label in ("a2", "a3"):
                parts[label] = self._vary(a, s, 0.3 + 0.7 * var)
            elif label in ("b", "b2"):
                parts[label] = self.new_motif(s, contrast=a) if label == "b" or "b" not in parts else self._vary(parts["b"], s, 0.5)
            elif label == "c":  # a fragment: the first half of the idea, twice
                half = [(o, l) for o, l in a["rhythm"] if o < 8]
                n = len(half)
                rhythm = half + [(o + 8, l) for o, l in half]
                steps = a["steps"][:n] + [1 if a["direction"] > 0 else -1] + a["steps"][1:n]
                parts[label] = {**a, "rhythm": rhythm, "steps": steps[:len(rhythm)]}
            elif label == "cad":  # the idea's head, then a long note on beat 3, held to the bar's end
                x = busyness(s["shape"]["notes"])[1]  # a fast line runs on: more of the head, the long note later
                at = 12 if x > 0.5 else 8
                head = [(o, min(l, at - o)) for o, l in a["rhythm"] if o < at][:3 + int(12 * x)] or [(0, 4)]
                rhythm = head + [(at, STEPS - at)]
                parts[label] = {**a, "rhythm": rhythm, "steps": a["steps"][:len(rhythm) - 1] + [0]}
        return parts[label]

    def _contour(self, i: int, n: int, shape: str, peak: int) -> int:
        import math
        x = (i + 0.5) / n
        return round(peak * {"arch": math.sin(math.pi * x), "rise": x, "fall": 1 - x,
                             "valley": -math.sin(math.pi * x)}[shape])

    # ---- a bar of notes, against the chord ----

    def plan_bar(self, bar: int, step0: int, s: dict, notes: list[int], chord_pcs,
                 lead=None) -> None:
        """This bar's notes, from the phrase's form, sounding against the
        chords: `chord_pcs` is a chord (pitch classes, root first) or a
        function from a sixteenth in the bar to the chord sounding then. `lead`:
        the harmony's own cadence ('answer' over the home chord, else
        'question') when the harmony leads; a function of the sixteenth too."""
        ph = self.phrase
        chord_at = chord_pcs if callable(chord_pcs) else (lambda onset: chord_pcs)
        lead_at = lead if callable(lead) else (lambda onset: lead)
        if not ph or not notes or not chord_at(0):
            return
        rng, mel = self.rng, s["melody"]
        i = bar - ph["start"]
        if not 0 <= i < len(ph["form"]):
            return
        label = ph["form"][i]
        part = self._part(label, s)
        if mel["style"] == "Motif" and i and rng.random() < 0.25 + 0.6 * mel["variation"]:
            part = self._vary(part, s, mel["variation"] * 0.5)  # the riff, a little different each time
        n_notes = len(notes)
        span = 3 + int(8 * mel["range"])
        mid = n_notes // 2
        lo, hi = max(0, mid - span), min(n_notes - 1, mid + span)

        def chord(onset):  # the chord's tones and roots in the scale's notes, at this sixteenth
            c = chord_at(onset) or chord_at(0)
            pcs = {p % 12 for p in c}
            tones = [k for k, m in enumerate(notes) if m % 12 in pcs and lo <= k <= hi] or \
                    [k for k, m in enumerate(notes) if m % 12 in pcs]
            return pcs, tones, [k for k in tones if notes[k] % 12 == c[0] % 12]
        pcs, tones, roots = chord(0)
        # the bar's starting point: the phrase's contour, moved to the nearest chord tone
        target = mid + self._contour(i, len(ph["form"]), ph["contour"], 2 + int(3 * mel["range"]))
        anchor = min(tones, key=lambda k: abs(k - target)) if tones else target
        idx, resolve = anchor, None
        for j, ((onset, length), step) in enumerate(zip(part["rhythm"], part["steps"])):
            pcs, tones, roots = chord(int(onset))
            kind = (lead_at(int(onset)) or ph["kind"]) if ph["kind"] else None
            cad = label == "cad" or (i == len(ph["form"]) - 1 and kind)
            if j:
                idx += step
            if resolve is not None:  # the dissonance before: step to the chord tone
                idx = resolve
                resolve = None
            if idx < lo or idx > hi:  # bounce off the edges of the range
                idx = max(lo, min(hi, idx - 2 * step))
            last = j == len(part["rhythm"]) - 1
            strong = onset % 8 == 0 or length >= 4
            if cad and last and kind == "answer" and roots:
                idx = min(roots, key=lambda k: abs(k - idx))
            elif cad and last and tones:
                others = [k for k in tones if k not in roots] or tones
                idx = min(others, key=lambda k: abs(k - idx))
            elif strong and tones and notes[idx] % 12 not in pcs:
                near = min(tones, key=lambda k: abs(k - idx))
                if abs(near - idx) == 1 and length >= 2 and rng.random() < 0.08 + 0.2 * mel["variation"]:
                    resolve = near  # an appoggiatura: keep the dissonance, resolve on the next note
                else:
                    idx = near
            vel = accent(onset, length)
            self._put(step0 + onset, notes[idx], length, vel)
            self.prev_idx = idx
        # pickups: the last notes of a phrase's final bar lead into the next phrase
        if i == len(ph["form"]) - 1 and rng.random() < mel["pickups"]:
            k = rng.choice([1, 2, 3])
            onsets = {1: [14], 2: [12, 14], 3: [13, 14, 15]}[k]
            cut = step0 + onsets[0]
            for t0 in [t for t in self.plan if step0 <= t < cut]:  # shorten what would ring over them
                self.plan[t0] = [(m, max(0.5, min(l, cut - t0 - f)), v, f) for m, l, v, f in self.plan[t0]]
            for t in [t for t in self.plan if cut <= t < step0 + STEPS]:
                del self.plan[t]
            # a run by step toward where the next phrase will start (near the middle of the range)
            start = mid + rng.choice([-2, -1, 1, 2])
            d = 1 if rng.random() < 0.5 else -1
            for q, o in enumerate(onsets):
                pi = max(lo, min(hi, start - d * (len(onsets) - q)))
                self._put(step0 + o, notes[pi], 1 if k == 3 else 2, 0.65)

    def _put(self, at: float, note: int, length: float, vel: float) -> None:
        """A note into the plan, at a sixteenth (or between two: a thirty-second)."""
        step = int(at)
        self.plan.setdefault(step, []).append((note, length, vel, at - step))

    def at(self, step: int) -> list[tuple[int, float, float, float]]:
        """What to play in this sixteenth: (MIDI note, length in sixteenths,
        velocity, how far into the sixteenth it starts: 0 or 0.5)."""
        return self.plan.pop(step, [])
