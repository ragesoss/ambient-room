"""How close can the melody generator get to a real tune? (2026-10-14)

    PYTHONPATH=. .venv/bin/python tools/tune_fit.py [--half] [--search N] [--joint] [--moods] [--detail]

The three dobro tunes of ~/play/dobro-transcription (Red Wing, Down Yonder, Big Sciota, all in
G) are the goals. For each: its chord chart becomes the harmony (a loop, as the "Fiddle tune
chart" preset), its tempo the beat, and the melody settings are searched for the line whose
traits come closest to the tune's: notes a bar, where in the bar they fall, how far apart, steps
against skips and leaps, the span, chord tones on beats 1 and 3. The conductor plays the chart
for real, against a stand-in clock (as ambient/render.py), and the melody notes are taken as it
plans them: nothing is heard.

Two ways to lay a tune on the app's bars: at its own tempo, a bar for a bar; or (--half) at
half the tempo, two of its bars to one of the app's, so that the app's sixteenths are the
tune's eighths (a fiddle tune's running eighths are the generator's running sixteenths).

Then, bar by bar, whether the generator could ever play the tune's own bar (an octave moved is
the same bar), under its rules (ambient/melody.py): a bar is beat-sized rhythm cells; its first
note is a chord tone, or a neighbour leaning on one; a note on beat 1 or 3, or one a quarter
long or more, is a chord tone (or a neighbour resolving to it by step); the scale's notes only
(as they are under the chord sounding), or a weak note a half step from the strong note after
it; within the melody's range. A phrase's last bar is the idea's head and a held arrival (on
beat 3 or an eighth either side; in a running line anywhere in the bar's second half), perhaps
followed by pickups (a run by step or by half steps), and the arrival is the chord's root over
the home chord, another chord tone but the home note over any other. Also: how many bars, over
many times round, it played exactly as the tune. Reads the tunes with dobro-transcription's
score reader.
"""

from __future__ import annotations

import argparse
import copy
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from ambient import music  # noqa: E402
from ambient.conductor import Conductor, melody_range  # noqa: E402
from ambient.harmony import at_step, chord_scale, loop_chord, parse_chart  # noqa: E402
from ambient.melody import CELLS, STEPS, busyness  # noqa: E402
from ambient.state import MOODS  # noqa: E402

TUNES = ["red-wing", "down-yonder", "big-sciota"]
MOOD_OF = {"red-wing": "Red Wing", "down-yonder": "Down Yonder", "big-sciota": "Big Sciota"}
MOOD_K = {"red-wing": 2, "down-yonder": 2, "big-sciota": 1}  # how each mood lays its tune (ambient/presets.py)
# Big Sciota's key is written with repeats and second endings: the bars as played
PLAYED = {"big-sciota": [1, 2, 3, 4, 1, 2, 3, 5, 6, 7, 8, 9, 6, 7, 8, 10]}
# The charts as the presets write them: the dominants as sevenths (the melodies lean on them:
# Red Wing's C over D, Down Yonder's G over A), and Down Yonder's G7 into C (its F)
SEVENTHS = {"red-wing": ({"D": "D7", "A": "A7"}, {}),
            "down-yonder": ({"D": "D7", "A": "A7"}, {2: "G7", 14: "G7"}),
            "big-sciota": ({"D": "D7"}, {})}
SLOTS = music.preset_slots("major")


# ---- the tunes, laid on the app's bars ----

def load_tune(name: str, root: Path, k: int = 1) -> dict:
    """The tune: its melody (the top note at each onset) in the app's sixteenths, `k` of the
    tune's sixteenths to one (1: a bar for a bar; 2: two of its bars to one of the app's), and
    its chart, a chord per beat of the tune."""
    sys.path.insert(0, str(root / "pipeline" / "src"))
    from transcribe.score import read_score
    d = root / "tunes" / "dobro" / name
    ev, meta = read_score(d / f"{name}.musicxml")
    pickup = float(meta.get("pickup_beats") or 0.0)
    chart_bars = {}
    for line in (d / "chords.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            b, chords = line.split(":")
            chart_bars[int(b)] = chords.split()
    names, swap = SEVENTHS.get(name, ({}, {}))
    beats = []
    for i, b in enumerate(PLAYED.get(name, sorted(chart_bars)), 1):
        beats.append([swap[i]] * 4 if i in swap else [names.get(c, c) for c in chart_bars[b]])
    top = {}
    for e in ev:
        t = round((e.onset_beats - pickup) * 4)  # the tune's sixteenths from its bar 1
        if t not in top or e.midi > top[t][0]:
            top[t] = (e.midi, max(1, round(e.duration_beats * 4)))
    notes = sorted((t / k, m, l / k) for t, (m, l) in top.items())
    return {"name": name, "bpm": float(meta["tempo_bpm"]), "k": k, "beats": beats, "notes": notes,
            "bars": -(-len(beats) // k), "pickup": pickup}


def chart_text(tune: dict) -> str:
    """The chart in the app's notation, a bar of the app's at a time: its chords share it evenly."""
    k, beats = tune["k"], tune["beats"]
    out = []
    for i in range(0, len(beats), k):
        slots = [c for bar in beats[i:i + k] for c in bar]  # chords on the app bar's 4k equal parts
        for n in (1, 2, 4, 8, 16):  # the fewest equal parts that say the same
            if n <= len(slots) and len(slots) % n == 0:
                part = len(slots) // n
                toks = [slots[j * part] for j in range(n)]
                if all(slots[j] == toks[j // part] for j in range(len(slots))):
                    break
        out.append(" ".join(toks))
    return "| " + " | ".join(out) + " |"


def tune_state(tune: dict, melody: dict, shape: dict, base: str = "Country") -> dict:
    """A whole state: the base mood's sound and beat, the tune's chart, key and tempo, the
    melody settings given."""
    s = copy.deepcopy(MOODS[base])
    s["key"] = "G"
    s["tones"] = music.default_tones(SLOTS)
    s["harmony"].update({"style": "Loop", "plain": True, "borrow": 0.0, "loop": parse_chart(chart_text(tune), "G", SLOTS)})
    s["melody"].update(melody)
    s["shape"].update(shape)
    s["shape"]["tempo"] = max(0.0, (tune["bpm"] / tune["k"] - 50) / 100)
    s["evolve"]["rate"] = 0.0
    return s


# ---- the generator, played without sound ----

class _Clock:
    running, error, underruns = True, None, 0

    def __init__(self):
        self.t = 0.0

    def time(self) -> float:
        return self.t

    def set(self, name, value) -> None:
        pass

    def note(self, *a) -> None:
        pass


def generate(state: dict, bars: int, seed: int) -> list[tuple[float, int, float]]:
    """The melody the conductor plans over `bars` bars: (sixteenth from the start, MIDI, length)."""
    clock = _Clock()
    c = Conductor(clock, random.Random(seed))
    c.apply(state)
    out = []
    at = c.melodist.at

    def record(step):
        got = at(step)
        out.extend((step + f, n, l) for n, l, v, f in got)
        return got
    c.melodist.at = record
    end = bars * 4 * 60 / (50 + 100 * state["shape"]["tempo"])
    while clock.t < end + 1:
        c.tick()
        clock.t += 0.2
    return sorted(n for n in out if n[0] < bars * STEPS)


# ---- traits, in the tune's own sixteenths, and how far apart two lines are ----

def chord_at(state: dict, step: float) -> list[int]:
    """The chord sounding at an app sixteenth (pitch classes, root first)."""
    h = state["harmony"]
    _, i, _ = at_step(h, int(step))
    return [p % 12 for p in loop_chord(state["key"], SLOTS, h, i)[0]]


def traits(notes: list[tuple[float, int, float]], state: dict, bars: int, k: int) -> dict:
    """Traits of a line given in app sixteenths, measured in the tune's (k to one)."""
    if not notes:
        return {}
    tn = [(t * k, m, l * k) for t, m, l in notes]
    pos = Counter()
    for t, m, l in tn:
        q = t % STEPS
        pos["1/3" if q % 8 == 0 else "2/4" if q % 4 == 0 else "8th" if q % 2 == 0 else "16th"] += 1
    pairs = [(a, b) for a, b in zip(tn, tn[1:]) if b[0] - a[0] <= 8]
    lens = Counter("16th" if g <= 1 else "8th" if g <= 2 else "dotted" if g <= 3 else "4th" if g <= 4 else "long"
                   for g in (b[0] - a[0] for a, b in pairs))
    ivc = Counter("same" if i == 0 else "step" if i <= 2 else "skip" if i <= 4 else "leap"
                  for i in (abs(b[1] - a[1]) for a, b in pairs))
    strong = [(t, m) for t, m, l in tn if t % 8 == 0 and t >= 0]
    ct = sum(m % 12 in chord_at(state, t / k) for t, m in strong) / max(1, len(strong))
    mids = sorted(m for _, m, _ in tn)
    n, p = len(tn), max(1, len(pairs))
    out = {"notes/bar": n / (bars * k), "chord tones on 1 and 3": ct,
           "span": mids[int(0.9 * (n - 1))] - mids[int(0.1 * (n - 1))]}
    out.update({f"on {q}": pos[q] / n for q in ("1/3", "2/4", "8th", "16th")})
    out.update({f"gap {q}": lens[q] / p for q in ("16th", "8th", "dotted", "4th", "long")})
    out.update({f"interval {q}": ivc[q] / p for q in ("same", "step", "skip", "leap")})
    return out


SCALE = {"notes/bar": 4.0, "span": 6.0}  # what a difference of 1 is worth, for these; 0.25 in a share


def distance(a: dict, b: dict) -> float:
    if not a or not b:
        return 99.0
    return sum(abs(a[q] - b[q]) / SCALE.get(q, 0.25) for q in a)


def score(tune: dict, state: dict, seeds=(1, 2, 3, 4, 5, 6), passes: int = 2) -> tuple[float, dict]:
    target = traits(tune["notes"], state, tune["bars"], tune["k"])
    ds, got = [], []
    for seed in seeds:
        g = traits(generate(state, tune["bars"] * passes, seed), state, tune["bars"] * passes, tune["k"])
        ds.append(distance(target, g))
        got.append(g)
    return statistics.mean(ds), {q: statistics.mean(x[q] for x in got) for q in got[0]} if got[0] else {}


# ---- could it play the tune's bar? ----

def _cells() -> tuple[set, set]:
    beat = {tuple(sorted(o for o, _ in hits)) for span, hits, _ in CELLS.values() if span == 4}
    two = {tuple(sorted(o for o, _ in hits)) for span, hits, _ in CELLS.values() if span == 8}
    return beat, two


def rhythm_ok(onsets: list[float]) -> bool:
    """Whether a bar's onsets (app sixteenths, halves for thirty-seconds) are a sequence of cells."""
    beat, two = _cells()

    def fits(t):
        if t == STEPS:
            return True
        if tuple(sorted(o - t for o in onsets if t <= o < t + 4)) in beat and fits(t + 4):
            return True
        return t + 8 <= STEPS and tuple(sorted(o - t for o in onsets if t <= o < t + 8)) in two and fits(t + 8)
    return fits(0)


def bar_scale(state: dict, bar: int) -> list[int]:
    """The scale as the bar's melody is planned: as it is under the chord on its downbeat (a chord
    from outside the scale brings its notes: conductor.chord)."""
    key = music.KEYS.index(state["key"])
    return chord_scale(SLOTS, [(p - key) % 12 for p in chord_at(state, bar * STEPS)])


def window(state: dict, bar: int = 0) -> list[int]:
    """The scale's notes the melody can reach in a bar: its range, around the middle (melody.plan_bar)."""
    lo, hi = melody_range(state["shape"]["height"], state["melody"]["range"])
    scale = music.scale_notes(state["key"], bar_scale(state, bar), lo, hi)
    span, mid = 3 + int(8 * state["melody"]["range"]), len(scale) // 2
    return scale[max(0, mid - span):mid + span + 1]


def octave_shift(tune: dict, state: dict) -> int:
    """One shift by octaves for the whole tune: the one that puts most of its notes in reach."""
    w = window(state)
    return max((12 * j for j in range(-3, 4)), key=lambda s: sum(w[0] <= m + s <= w[-1] for _, m, _ in tune["notes"]))


def head_ok(onsets: list[float], at: int) -> bool:
    """Whether onsets before `at` begin some sequence of cells (a cadence bar's head: the idea's
    first notes, cut at its arrival)."""
    beat, two = _cells()

    def fits(t):
        if t >= at:
            return True
        for span, cells in ((4, beat), (8, two)):
            if t + span > STEPS:
                continue
            here = tuple(sorted(o - t for o in onsets if t <= o < min(t + span, at)))
            if any(tuple(o for o in c if o < at - t) == here for c in cells) and fits(t + span):
                return True
        return False
    return fits(0)


# melody.plan_bar: a phrase's last notes, leading into the next (a running line's in sixteenths)
PICKUPS = {False: [(14,), (12, 14), (14, 15), (13, 14, 15)], True: [(15,), (14, 15), (13, 14, 15)]}


def scale_at(state: dict, bar: int, t: float) -> set[int]:
    """The scale's pitch classes for a note at sixteenth t of a bar: under the chord sounding then
    (conductor.respell_in_bar)."""
    key = music.KEYS.index(state["key"])
    return {(x + key) % 12 for x in chord_scale(SLOTS, [(p - key) % 12 for p in chord_at(state, bar * STEPS + t)])}


def check_bar(tune: dict, state: dict, bar: int, phrase_end: bool, shift: int, cells_end: bool = False) -> list[str]:
    """The rules the tune's notes in this app bar break (empty: the generator could play them),
    moved by `shift` semitones. A phrase's last bar: its last note (before any pickups) ends the
    phrase; its rhythm is a cadence (the idea's head, then a held note arriving on beat 3 or an
    eighth either side), or (`cells_end`, a two-bar phrase's second idea) cells."""
    notes = [(t - bar * STEPS, m + shift, l) for t, m, l in tune["notes"] if bar * STEPS <= t < (bar + 1) * STEPS]
    if not notes:
        return ["no notes (the generator plays in every bar)"]
    why = []
    body = notes
    x = busyness(state["shape"]["notes"])[1]
    pickups = []
    if phrase_end and state["melody"]["style"] == "Phrases":
        for pk in PICKUPS[x > 0.5]:  # pickups at the end, a run by step, take the place of the cadence's tail
            tail = tuple(t for t, _, _ in notes[-len(pk):])
            if len(notes) > len(pk) and tail == pk:
                body, pickups = notes[:-len(pk)], notes[-len(pk):]
                break
        arrivals = (8, 10, 11, 12) if x > 0.5 else (6, 8, 10)
        last_t = body[-1][0]
        cad = last_t in arrivals and head_ok([t for t, _, _ in body[:-1]], last_t) and len(body) - 1 <= 3 + int(12 * x)
        cells = cells_end and rhythm_ok([t for t, _, _ in notes])
        if not (cad or cells):
            why.append(f"cadence: the arrival at step {last_t:g}, not at {arrivals} after the idea's head")
    elif not rhythm_ok([t for t, _, _ in notes]):
        why.append("rhythm: no sequence of cells has these onsets")
    w = window(state, bar)
    strong_at = lambda t, l: t % 8 == 0 or l >= 4
    outside = set()
    chromatic_run = len(pickups) > 1 and all(abs(b[1] - a[1]) == 1 for a, b in zip(pickups, pickups[1:]))
    for j, (t, m, l) in enumerate(notes):
        if m % 12 in scale_at(state, bar, t) or (chromatic_run and (t, m, l) in pickups):
            continue
        nxt = notes[j + 1] if j + 1 < len(notes) else None  # a chromatic approach: weak, a half step from the strong note next
        if not (nxt and not strong_at(t, l) and strong_at(nxt[0], nxt[2]) and abs(nxt[1] - m) == 1):
            outside.add(music.KEYS[m % 12])
    if outside:
        why.append(f"outside the scale: {', '.join(sorted(outside))}")
    out_range = [m for _, m, _ in notes if not w[0] - 2 <= m <= w[-1] + 2]  # respelt or approach notes stray a step
    if out_range:
        why.append(f"out of range ({w[0]}-{w[-1]}): {len(out_range)} notes")
    idx = {m: j for j, m in enumerate(w)}
    first_chord = chord_at(state, bar * STEPS)
    if notes[0][1] % 12 not in first_chord:
        nxt = notes[1] if len(notes) > 1 else None  # or a neighbour leaning on it, resolving next (the first note's appoggiatura)
        if not (nxt and notes[0][1] in idx and nxt[1] in idx
                and abs(idx[notes[0][1]] - idx[nxt[1]]) == 1 and nxt[1] % 12 in first_chord):
            why.append("first note not a tone of the bar's first chord, nor leaning on one")
    for j, (t, m, l) in enumerate(body):
        pcs = chord_at(state, bar * STEPS + t)
        if (t % 8 == 0 or l >= 4) and m % 12 not in pcs:
            nxt = body[j + 1] if j + 1 < len(body) else None
            ok = (nxt is not None and m in idx and nxt[1] in idx and abs(idx[m] - idx[nxt[1]]) == 1
                  and nxt[1] % 12 in chord_at(state, bar * STEPS + nxt[0]))
            if not ok:
                why.append(f"step {t:g}: {music.KEYS[m % 12]} on a strong beat, not a chord tone, not resolved by step")
    if phrase_end:
        t, m, l = body[-1]
        chord = chord_at(state, bar * STEPS + t)
        home = music.KEYS.index(state["key"])
        if chord[0] == home:
            if m % 12 != home:
                why.append("phrase end over the home chord: not on its root")
        elif m % 12 == home or m % 12 not in chord:
            why.append("phrase end away from home: not a chord tone, or the home note")
    return why


def feasibility(tune: dict, state: dict) -> dict:
    """The app bars the generator could play, with the phrase length that allows the most."""
    best, shift = None, octave_shift(tune, state)
    for n in (1, 2, 4, 8):
        res = {bar: check_bar(tune, state, bar, bar % n == n - 1 or bar == tune["bars"] - 1, shift, cells_end=n == 2)
               for bar in range(tune["bars"])}
        ok = sum(1 for w in res.values() if not w)
        if best is None or ok > best["ok"]:
            best = {"phrase_bars": n, "ok": ok, "bars": res, "shift": shift}
    return best


def exact_bars(tune: dict, state: dict, passes: int, seed: int = 100) -> tuple[int, int]:
    """App bars played exactly as the tune does at the same place in the chart (the same onsets,
    the same notes, an octave apart allowed), over `passes` times round: (matches, bars)."""
    want = {b: [(t - b * STEPS, m) for t, m, _ in tune["notes"] if b * STEPS <= t < (b + 1) * STEPS]
            for b in range(tune["bars"])}
    played = {}
    for t, m, _ in generate(state, tune["bars"] * passes, seed):
        played.setdefault(int(t // STEPS), []).append((t % STEPS, m))
    hits = 0
    for b, notes in played.items():
        w = want[b % tune["bars"]]
        if w and len(w) == len(notes) and all(x[0] == y[0] for x, y in zip(w, notes)):
            d = {y[1] - x[1] for x, y in zip(w, notes)}
            hits += len(d) == 1 and d.pop() % 12 == 0
    return hits, tune["bars"] * passes


# ---- the search ----

def random_melody(rng: random.Random, style: str | None) -> tuple[dict, dict]:
    mel = {"style": style or rng.choice(["Phrases", "Phrases", "Motif"]), "phrase": rng.random(),
           "variation": rng.random(), "range": rng.random(), "leaps": rng.random(),
           "syncopation": rng.random() * 0.6, "pickups": rng.random()}
    return mel, {"notes": 0.3 + 0.7 * rng.random(), "height": 0.4 * rng.random()}


def nudge(rng: random.Random, mel: dict, shape: dict) -> tuple[dict, dict]:
    mel, shape = copy.deepcopy(mel), copy.deepcopy(shape)
    for q in ("phrase", "variation", "range", "leaps", "syncopation", "pickups"):
        mel[q] = min(1.0, max(0.0, mel[q] + rng.gauss(0, 0.08)))
    for q in ("notes", "height"):
        shape[q] = min(1.0, max(0.0, shape[q] + rng.gauss(0, 0.05)))
    return mel, shape


def search(tunes: list[dict], n: int, style: str | None, rng: random.Random) -> tuple[float, dict, dict]:
    """Melody settings with the least mean distance over the tunes: n tried at random, n/2 near
    the best, then the ten best scored again on seeds the search never saw."""
    def mean_d(mel, shape, seeds=(1, 2, 3, 4, 5, 6)):
        return statistics.mean(score(t, tune_state(t, mel, shape), seeds)[0] for t in tunes)
    tried = [(mean_d(*ms), ms) for ms in (random_melody(rng, style) for _ in range(n))]
    for _ in range(n // 2):
        ms = nudge(rng, *min(tried, key=lambda x: x[0])[1])
        tried.append((mean_d(*ms), ms))
    fresh = [(mean_d(*ms, seeds=tuple(range(31, 39))), ms) for _, ms in sorted(tried, key=lambda x: x[0])[:10]]
    d, (mel, shape) = min(fresh, key=lambda x: x[0])
    return d, mel, shape


def report(tune: dict, state: dict, label: str, passes: int, detail: bool) -> None:
    hits, n = exact_bars(tune, state, passes)
    f = feasibility(tune, state)
    print(f"  {label}: bars played exactly as the tune's in {passes} times round: {hits} of {n}")
    print(f"  {label}: bars it could play as written: {f['ok']} of {tune['bars']} (phrases of {f['phrase_bars']} "
          f"bars, the tune moved {f['shift']:+d} semitones)")
    for w, c in Counter(w.split(":")[0] for ws in f["bars"].values() for w in ws).most_common():
        print(f"      {c:3d} bars: {w}")
    if detail:
        for bar, ws in f["bars"].items():
            if ws:
                print(f"        bar {bar + 1}: {'; '.join(ws)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dobro", type=Path, default=Path.home() / "play" / "dobro-transcription")
    ap.add_argument("--tune", action="append", choices=TUNES, help="only these (default: all three)")
    ap.add_argument("--half", action="store_true", help="the tune at half tempo, two of its bars to one of the app's")
    ap.add_argument("--search", type=int, default=0, help="melody settings to try (0: the app's presets only)")
    ap.add_argument("--style", choices=["Phrases", "Motif"], help="search this melody style only")
    ap.add_argument("--joint", action="store_true", help="one melody for all the tunes")
    ap.add_argument("--moods", action="store_true", help="each tune's mood as the app has it (ambient/presets.py)")
    ap.add_argument("--passes", type=int, default=200, help="times round the chart, counting bars played exactly")
    ap.add_argument("--detail", action="store_true", help="list each bar the generator could not play, and why")
    a = ap.parse_args()
    from ambient.presets import MELODY
    k = 2 if a.half else 1
    tunes = [load_tune(n, a.dobro, MOOD_K[n] if a.moods else k) for n in (a.tune or TUNES)]
    rng = random.Random(7)
    found = {}
    if a.search:
        if a.joint:
            d, mel, shape = search(tunes, a.search, a.style, rng)
            print(f"one melody for all: mean distance {d:.2f} on fresh seeds")
            print("   ", {q: (round(v, 2) if isinstance(v, float) else v) for q, v in {**mel, **shape}.items()})
            found = {t["name"]: (mel, shape) for t in tunes}
        else:
            for t in tunes:
                d, mel, shape = search([t], a.search, a.style, rng)
                found[t["name"]] = (mel, shape)
    for t in tunes:
        k = t["k"]
        print(f"\n=== {t['name']}: {len(t['beats'])} bars at {t['bpm']:g}"
              f"{', laid two to a bar at half tempo' if k == 2 else ''}; {len(t['notes'])} notes")
        base = tune_state(t, {}, {})
        if a.moods:  # the mood as the app has it: its own chart, beat and sound
            base = copy.deepcopy(MOODS[MOOD_OF[t["name"]]])
            base["evolve"]["rate"] = 0.0
            print(f"  the mood {MOOD_OF[t['name']]!r}, at {50 + 100 * base['shape']['tempo']:g} bpm")
        else:
            print(f"  chart: {chart_text(t)}")
        target = traits(t["notes"], base, t["bars"], k)
        rows = {}
        candidates = [(f"preset {name}", MELODY[name][1]["melody"], MELODY[name][1]["shape"])
                      for name in ("Fiddle tune in two", "Fiddle tune", "Song", "Questions", "Bluegrass break")
                      if name in MELODY]
        if a.moods:
            candidates.insert(0, (f"the mood {MOOD_OF[t['name']]!r}", base["melody"],
                                  {q: base["shape"][q] for q in ("notes", "height")}))
        if t["name"] in found:
            candidates.insert(0, ("found", *found[t["name"]]))
        for label, mel, shape in candidates:
            st = copy.deepcopy(base)
            st["melody"].update(mel)
            st["shape"].update(shape)
            d, g = score(t, st, seeds=tuple(range(31, 39)))
            rows[label] = (d, g, st, mel, shape)
            print(f"  {label:26s} distance {d:5.2f}")
        first = next(iter(rows))
        d, g, st, mel, shape = rows[first]
        print(f"  {first}: {({q: (round(v, 2) if isinstance(v, float) else v) for q, v in {**mel, **shape}.items()})}")
        print(f"  {'trait':24s} {'tune':>6s} {first[:12]:>12s}")
        for q in target:
            print(f"  {q:24s} {target[q]:6.2f} {g.get(q, 0):12.2f}")
        report(t, st, first, a.passes, a.detail)


if __name__ == "__main__":
    main()
