"""The Tune line (ambient/breaks.py): a break on a tune's melody, from as written to the free line."""

import copy
import math
import random
import re
from dataclasses import replace

import pytest

from ambient import breaks
from ambient.breaks import BAR, Break, Note, Tune, measure
from ambient.conductor import Conductor
from ambient.engine import FakeEngine
from ambient.music import KEYS
from ambient.presets import TUNE_MELODIES
from ambient.state import DEFAULT, MOODS, merge


class Clock(FakeEngine):
    def __init__(self):
        super().__init__()
        self.t = 0.0

    def time(self):
        return self.t


# A tune of 16 bars in G in two phrases played twice (the second pair answering the first), held notes, a cadence
# on D, a cadence on G held two beats and a half, and a pickup into the next pass
G3, A3, B3, C4, D4, E4, Fs4, G4 = 55, 57, 59, 60, 62, 64, 66, 67


def _phrase(start: float, end_note: int, end_beats: float) -> list[Note]:
    notes = []
    for b in range(3):
        t = start + b * BAR
        notes += [Note(t, 1.0, G3 if b % 2 == 0 else B3), Note(t + 1, 0.5, A3), Note(t + 1.5, 0.5, B3),
                  Note(t + 2, 1.5, D4, "slide-in", 1), Note(t + 3.5, 0.5, C4)]
    t = start + 3 * BAR
    notes += [Note(t, 0.5, B3), Note(t + 0.5, 0.5, A3), Note(t + 1, end_beats, end_note)]
    return notes


def synthetic() -> Tune:
    notes = (_phrase(0, D4, 3.0) + _phrase(16, G3, 2.5) + _phrase(32, D4, 3.0) + _phrase(48, G3, 2.5)
             + [Note(63.5, 0.5, D4)])
    return Tune("test", 7, 16, notes)


def chords() -> list[tuple[int, ...]]:
    G, D7 = (7, 11, 2), (2, 6, 9, 0)
    out = []
    for bar in range(16):
        out += [D7 if bar % 4 == 3 and bar % 8 != 7 else G] * 4
    return out


def line(br: Break, pass_i: int) -> list[Note]:
    out = []
    for j in range(len(br.tune.phrases())):
        out += [x for x in br.phrase(pass_i, j) if isinstance(x, Note)]
    return out


def test_as_written_is_the_tune():
    tune = synthetic()
    br = Break(tune, chords(), 1.0, seed=1, k=2)
    assert line(br, 0) == tune.notes
    m = measure(line(br, 0), tune)
    assert m["strong_kept"] == m["arrivals_kept"] == m["tune_notes"] == 1.0


def test_a_tunes_parts_split_its_phrases():
    """Four bars a phrase within a part, a part's remainder joined to its last phrase (Cherokee Shuffle's AABB:
    8, 8, 10, 10); a tune whose parts are not given is one part."""
    tune = synthetic()
    assert replace(tune, parts=(8, 8)).phrases() == tune.phrases()
    aabb = Tune("aabb", 9, 36, [Note(0, 1, 57)], parts=(8, 8, 10, 10))
    assert aabb.phrases() == [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 26), (26, 30), (30, 36)]
    assert replace(aabb, parts=()).phrases()[-3:] == [(24, 28), (28, 32), (32, 36)]


def test_phrases_arrivals_and_repeats():
    tune = synthetic()
    assert tune.phrases() == [(0, 4), (4, 8), (8, 12), (12, 16)]
    assert [tune.arrival(j).midi for j in range(4)] == [D4, G3, D4, G3]
    # three bars of four the same: each plays the first again
    assert [tune.repeats(j) for j in range(4)] == [None, 0, 0, 0]
    assert [n.midi for n in tune.into_top()] == [D4]


def test_the_middle_keeps_the_strong_beats_and_lands_every_phrase():
    tune = synthetic()
    kept, arrived, own = [], [], []
    for seed in range(30):
        m = measure(line(Break(tune, chords(), 0.5, seed=seed, k=2), 0), tune)
        kept.append(m["strong_kept"])
        arrived.append(m["arrivals_kept"])
        own.append(m["tune_notes"])
    assert 0.6 < sum(kept) / len(kept) < 0.95
    assert sum(arrived) / len(arrived) > 0.9
    assert sum(own) / len(own) < 0.85  # and plays with the rest


def test_the_pull_orders_how_much_of_the_tune_is_kept():
    tune = synthetic()
    means = []
    for pull in (1.0, 0.75, 0.5, 0.25):
        ms = [measure(line(Break(tune, chords(), pull, seed=s, k=2), 0), tune)["tune_notes"] for s in range(30)]
        means.append(sum(ms) / len(ms))
    assert means == sorted(means, reverse=True) and means[0] == 1.0


def test_later_passes_depart_further_and_a_repeat_answers():
    tune = synthetic()
    first, third = [], []
    for seed in range(30):
        br = Break(tune, chords(), 0.5, seed=seed, k=2)
        first.append(measure(line(br, 0), tune)["tune_notes"])
        third.append(measure(line(br, 2), tune)["tune_notes"])
    assert sum(third) < sum(first)
    br = Break(tune, chords(), 0.5, seed=0, k=2)
    assert br.departure(0, 2) > br.departure(0, 0)  # phrase 3 plays phrase 1 again: it departs further
    assert br.departure(2, 0) > br.departure(0, 0)


def test_its_own_dice():
    tune = synthetic()
    a = line(Break(tune, chords(), 0.5, seed=4, k=2), 0)
    assert a == line(Break(tune, chords(), 0.5, seed=4, k=2), 0)
    assert a != line(Break(tune, chords(), 0.5, seed=5, k=2), 0)


def test_free_bars_only_away_from_the_arrival():
    tune = synthetic()
    for seed in range(20):
        br = Break(tune, chords(), 0.15, seed=seed, k=2)
        for j in range(4):
            spans = [x for x in br.phrase(0, j) if isinstance(x, breaks.FreeSpan)]
            arr = tune.arrival(j)
            assert not any(s.t0 <= arr.t < s.t1 for s in spans)


def test_the_instruments_range_and_its_hammer_ons():
    tune = synthetic()
    low = Tune("low", 7, 16, [Note(n.t, n.dur, n.midi - 12, n.how, n.bend) for n in tune.notes])
    for seed in range(10):
        for pull in (1.0, 0.5):
            notes = line(Break(low, chords(), pull, seed=seed, k=2, idiom=breaks.IDIOMS["Fiddle"]), 0)
            assert min(n.midi for n in notes) >= 55  # nothing under the fiddle's G string
            dob = line(Break(tune, chords(), pull, seed=seed, k=2, idiom=breaks.IDIOMS["Dobro"]), 0)
            for a, b in zip(dob, dob[1:]):
                if b.how == "hammer" and b.by == "hammer":  # the dobro hammers on only from an open string
                    assert a.midi in breaks.IDIOMS["Dobro"].open_strings


def _tune_state(mood: str, style: str, pull: float = 0.5) -> dict:
    s = copy.deepcopy(MOODS[mood])
    s["melody"]["style"] = style
    s["melody"]["pull"] = pull
    s["evolve"]["rate"] = 0.0
    return s


def _red_wing_state(style: str, pull: float = 0.5) -> dict:
    return _tune_state("Red Wing", style, pull)


def _play(state, melody_seed, break_seed=None, seconds=80):
    clock = Clock()
    c = Conductor(clock, random.Random(1), melody_rng=random.Random(melody_seed))
    c.break_seed = break_seed
    c.apply(state)
    while clock.t < seconds:
        c.tick()
        clock.t += 0.2
    return c, clock.notes


@pytest.fixture
def red_wing_tune(monkeypatch):
    """Red Wing's chart with the synthetic tune for its melody (no transcription project needed)."""
    monkeypatch.setattr(breaks, "load_tune", lambda *a, **k: synthetic())


def _melody_instr(state) -> set:
    from ambient.sounds import instr
    return {int(instr("melody", state["layers"]["melody"]["voice"]))}


def test_the_tune_line_over_a_tunes_chart(red_wing_tune):
    c, notes = _play(_red_wing_state("Tune", 1.0), 7, 3)
    assert c.breaker is not None and c.breaker.k == 2
    heard = [n for p, n in c.breaker.heard if p == 0]
    assert heard == synthetic().notes  # as written, the first time round


def test_the_free_end_is_todays_line(red_wing_tune):
    s0 = _red_wing_state("Phrases")
    s1 = _red_wing_state("Tune", 0.0)
    _, a = _play(s0, 11)
    _, b = _play(s1, 11)
    assert a == b


def test_the_band_is_the_same_under_every_line(red_wing_tune):
    mel = _melody_instr(_red_wing_state("Tune"))
    bands = []
    for pull, seed, density in ((1.0, 1, 0.5), (0.5, 1, 0.5), (0.5, 2, 0.5), (0.0, 1, 0.5), (0.5, 1, 0.2),
                                (0.25, 2, 0.8), (0.0, 1, 0.1)):
        s = _red_wing_state("Tune", pull)
        s["melody"]["density"] = density
        _, notes = _play(s, 11, seed)
        bands.append([n for n in notes if int(abs(n[1])) not in mel])
        assert any(int(abs(n[1])) in mel for n in notes)
    assert all(b == bands[0] for b in bands[1:])


def test_the_tune_line_off_a_tunes_chart_is_the_free_line(red_wing_tune):
    s = merge(DEFAULT, {"melody": {"style": "Tune", "pull": 0.8}, "harmony": {"style": "Loop", "loop": [1, 4, 5, 1]}})
    c, notes = _play(s, 3, seconds=30)
    assert c.breaker is None and notes


def test_pull_is_a_setting():
    s = merge(DEFAULT, {"melody": {"pull": 0.3, "style": "Tune"}})
    assert s["melody"]["pull"] == 0.3 and s["melody"]["style"] == "Tune"
    assert DEFAULT["melody"]["style"] == "Scattered"  # chosen, not imposed


# ---- the density: a break's notes against the tune's (the transcription project's card ambient-break-density) ----

def test_density_is_a_setting_beside_the_pull():
    from ambient import explain
    assert DEFAULT["melody"]["density"] == 0.5 and breaks.density_of(0.5) == 1.0  # the default: as before
    assert breaks.density_of(0) == 0.25 and breaks.density_of(1) == 2.0
    for r in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        assert breaks.density_of(breaks.density_setting(r)) == pytest.approx(r)
    assert merge(DEFAULT, {"melody": {"density": 0.2}})["melody"]["density"] == 0.2
    ids = [q["id"] for q in explain.options()["melody"]["params"]]
    assert ids[ids.index("pull") + 1] == "density"
    assert explain._melody(DEFAULT)["density"].startswith("the tune's own")
    assert explain._melody(merge(DEFAULT, {"melody": {"density": 1 / 6}}))["density"].startswith("50%")


def test_at_density_one_its_rules_never_run(red_wing_tune, monkeypatch):
    """At 1, the default, a break is as its pull makes it: the density's rules are not asked, so its dice and its
    notes are as before (checked against the code before them, every note the conductor sent over the four tunes,
    five pulls and 20 seeds: the transcription project's findings)."""
    def ran(*a, **k):
        raise AssertionError("the density's rules ran at 1")
    for name in ("_dense", "_thin_free", "_simplify", "_fill_to"):
        monkeypatch.setattr(Break, name, ran)
    for pull in (0.75, 0.5, 0.25, 0.1, 0.0):
        c, notes = _play(_red_wing_state("Tune", pull), 11, 3)
        assert c.breaker.density == 1.0 and notes


def _repeats(notes: list[Note]) -> int:
    mel = [n for n in notes if n.how != "double"]
    return sum(a.midi == b.midi and b.t - a.t < 2 - 1e-6 for a, b in zip(mel, mel[1:]))


def test_below_one_a_break_simplifies_its_own_notes():
    """The break at a density under 1 is its seed's break at 1 with notes left out and held: each phrase's first note
    and its arrival kept, its notes that share of the tune's (and a note struck where the chord changes under one
    held); every note one the break at 1 played (its time and pitch), or a grace note's main note back on its time,
    or a note held longer moved to its chord; no note struck again within two beats of itself (held instead); none
    held past its own length over a chord it is not in while another note was there to strike."""
    tune = synthetic()
    for pull in (0.75, 0.5):
        for seed in range(20):
            full = [n for n in line(Break(tune, chords(), pull, seed=seed, k=2), 0) if n.how != "double"]
            was = {(round(n.t, 4), n.midi): n.dur for n in full}
            shares = []
            for dens in (0.75, 0.5):
                br = Break(tune, chords(), pull, seed=seed, k=2, density=dens)
                notes = line(br, 0)
                m = measure(notes, tune)
                assert m["arrivals_kept"] == 1.0 and m["density"] <= dens + 0.15
                shares.append(m["density"])
                mel = [n for n in notes if n.how != "double"]
                for n in mel:
                    assert ((round(n.t, 4), n.midi) in was or (round(n.t + 0.25, 4), n.midi) in was
                            or n.by == "held"), (pull, seed, dens, n)
                assert _repeats(notes) == 0
                kept = {(round(n.t, 4), n.midi) for n in mel}
                for n, after in zip(mel, mel[1:]):
                    own_end = n.t + was.get((round(n.t, 4), n.midi), n.dur)
                    for b in range(math.ceil(own_end - 1e-6), math.ceil(min(n.end, after.t) - 1e-6)):
                        if n.midi % 12 not in br.chord_at(b):
                            assert not [x for x in full if n.t < x.t < after.t and x.midi != n.midi
                                        and (round(x.t, 4), x.midi) not in kept], (pull, seed, dens, n, b)
                for j, (b0, b1) in enumerate(tune.phrases()):
                    plan = br.phrase(0, j)
                    spans = [x for x in plan if isinstance(x, breaks.FreeSpan)]
                    own = [n for n in tune.melody() if b0 * BAR <= n.t < b1 * BAR
                           and not any(s.t0 <= n.t < s.t1 for s in spans)]
                    mine = [x for x in plan if isinstance(x, Note) and x.how != "double"]
                    assert len(mine) <= max(2, math.ceil(dens * len(own))) + 3  # and a few struck under chords
                    varied = [x for x in br.varied(0, j) if isinstance(x, Note)]
                    if varied and abs(varied[0].t - b0 * BAR) < 1e-6:
                        assert mine[0].t == varied[0].t  # the phrase's first note
            assert shares[0] > shares[1]


def test_simplifying_keeps_the_tunes_notes_where_the_pull_is_high_and_the_chords_where_it_is_low():
    tune = synthetic()

    def shares(pull):
        own, chord = [], []
        for seed in range(30):
            br = Break(tune, chords(), pull, seed=seed, k=2, density=0.5)
            notes = [n for n in line(br, 0) if n.how != "double"]
            own.append(measure(notes, tune)["tune_notes"])
            chord.append(sum(n.midi % 12 in br.chord_at(n.t) for n in notes) / len(notes))
        return sum(own) / len(own), sum(chord) / len(chord)

    high, low = shares(0.75), shares(0.25)
    assert high[0] > 0.8 and high[0] > low[0] + 0.15  # the tune's own
    assert low[1] > 0.9  # the chord's


def test_above_one_a_break_fills_and_the_tune_as_written_stays():
    tune = synthetic()
    shares = []
    for seed in range(20):
        at1 = line(Break(tune, chords(), 0.75, seed=seed, k=2), 0)
        more = line(Break(tune, chords(), 0.75, seed=seed, k=2, density=1.5), 0)
        assert len(more) >= len(at1)
        shares.append(measure(more, tune)["density"])
        for dens in (0.5, 1.5):
            assert line(Break(tune, chords(), 1.0, seed=seed, k=2, density=dens), 0) == tune.notes
    assert sum(shares) / len(shares) > 1.4


def test_the_free_line_is_held_to_the_density(red_wing_tune):
    """Near the free end a break plays other notes and rhythms, not more of them: at pull 0 the free line's notes
    left out and held, to the share of the tune's notes in each bar (one at least, and one where the chord changes
    under a note held); a note held over others moved to its chord's nearest."""
    tune = synthetic()
    s = _red_wing_state("Tune", 0.0)
    c1, _ = _play(s, 11, 3, seconds=40)
    s["melody"]["density"] = breaks.density_setting(0.5)
    c2, _ = _play(s, 11, 3, seconds=40)
    at1 = {round(n.t, 4): n for p, n in c1.breaker.heard if p == 0}
    half = [n for p, n in c2.breaker.heard if p == 0]
    assert len(half) < 0.6 * len(at1) and len(half) <= 0.65 * len(tune.melody())
    for n in half:
        was = at1[round(n.t, 4)]
        assert n.midi == was.midi or (n.midi % 12 in c2.breaker.chord_at(n.t) and n.dur > was.dur)


def test_a_simplified_repeat_keeps_the_core_of_the_phrase_it_repeats_and_holds_nothing_into_the_free_line():
    """The player (2026-10-22, Big Sciota at 0.5): "the simplified core of the repeated phrases ... would be kept,
    and elaborated on, rather than replaced". Simplified, a repeat's notes are more the earlier phrase's own (at the
    same place and pitch class) than at 1, the skeleton being the same; and no note is held into a bar the free line
    takes."""
    tune = synthetic()
    alike = {1.0: [], 0.5: []}
    for seed in range(20):
        for dens in alike:
            br = Break(tune, chords(), 0.4, seed=seed, k=2, density=dens)
            notes = line(br, 0)
            alike[dens].append(measure(notes, tune)["repeats_alike"])
            for j in range(len(tune.phrases())):
                plan = br.phrase(0, j)
                walls = [x.t0 for x in plan if isinstance(x, breaks.FreeSpan)]
                for n in plan:
                    if isinstance(n, Note):
                        assert not any(n.t < w < n.end - 1e-6 for w in walls), (seed, dens, n)
    assert sum(alike[0.5]) > sum(alike[1.0])


def _sparse_and_busy() -> Tune:
    """A tune in G whose bars are by turns two half notes and eight eighths."""
    notes, scale = [], [55, 57, 59, 60, 62, 64, 66, 67]
    for bar in range(16):
        t = bar * BAR
        if bar % 2 == 0:
            notes += [Note(t, 2.0, 55 if bar % 4 == 0 else 59), Note(t + 2, 2.0, 62)]
        else:
            notes += [Note(t + 0.5 * i, 0.5, scale[(i + bar) % 8]) for i in range(8)]
    return Tune("sparse-busy", 7, 16, notes)


def test_the_departure_by_the_tunes_own_density_off_unless_set():
    """The player (2026-10-22, Down Yonder at 0.25): "a fiddle player would usually hit most of the standard notes in
    the low density portions ... and then innovate on the density parts more freely". With `local`, the strong-beat
    notes of the tune's sparse bars are kept more and its busy bars' less; off (None, the default) as before; as
    written the same either way."""
    tune = _sparse_and_busy()
    on = replace(breaks.PARAMS, local=2.0)
    assert breaks.PARAMS.local is None

    def kept(params, sparse):
        same = total = 0
        for seed in range(30):
            notes = line(Break(tune, chords(), 0.4, seed=seed, k=2, params=params), 0)
            for n in tune.melody():
                if breaks.strong(n.t) and (int(n.t // BAR) % 2 == 0) == sparse:
                    x = breaks.sounding(notes, n.t)
                    same += x is not None and x.midi == n.midi
                    total += 1
        return same / total

    assert kept(on, True) > kept(breaks.PARAMS, True) + 0.05
    assert kept(on, False) < kept(breaks.PARAMS, False) - 0.05
    assert line(Break(tune, chords(), 1.0, seed=1, k=2, params=on), 0) == tune.notes


@pytest.mark.skipif(breaks.project_root() is None, reason="needs the transcription project's tunes")
def test_the_tunes_keys_read_as_one_pass():
    rw = breaks.load_tune("red-wing", "G", 16)
    assert rw.bars == 16 and rw.notes[0].midi == 55 and [n.midi for n in rw.into_top()] == [50]
    dy = breaks.load_tune("down-yonder", "G", 20)
    assert [n.midi for n in dy.lead_in] == [62, 61, 60] and [n.midi for n in dy.into_top()] == [62, 61, 60]
    bs = breaks.load_tune("big-sciota", "G", 16)
    assert [n.midi for n in bs.into_top()] == [50] and bs.notes[-1].t == 63.5


def _chord_names(chords: list[tuple[int, ...]]) -> list[str]:
    return [KEYS[c[0]] + ("m" if (c[1] - c[0]) % 12 == 3 else "") for c in chords]


# Cherokee Shuffle's chart, a chord a beat (the transcription project's tunes/dobro/cherokee-shuffle/chords.txt):
# A (8 bars), A, B (10), B
CHEROKEE_A = ["A", "A", "A", "F#m", "D", "A", "E", "A"]
CHEROKEE_B = ["D", "A", "D", "A", "D", "A", "A", "F#m", "D E", "A"]


def test_cherokee_shuffles_chart():
    s = _tune_state("Cherokee Shuffle", "Tune")
    assert s["key"] == "A" and breaks.tune_for(s)[0] == "Cherokee Shuffle"
    src = TUNE_MELODIES["Cherokee Shuffle"]
    assert (src["k"], src["bars"], sum(src["parts"])) == (2, 36, 36)
    assert sum(x["beats"] for x in s["harmony"]["loop"]) == 4 * 36 / 2  # one pass, laid in two
    want = []
    for bar in CHEROKEE_A * 2 + CHEROKEE_B * 2:
        cs = bar.split()
        want += [c for c in cs for _ in range(4 // len(cs))]
    assert _chord_names(breaks.chart_beats(s, 2, 4 * 36)) == want


@pytest.mark.skipif(breaks.project_root() is None, reason="needs the transcription project's tunes")
def test_the_tune_line_plays_cherokee_shuffle():
    folder = breaks.project_root() / "tunes" / "dobro" / "cherokee-shuffle"
    bars = dict(re.findall(r"^([AB]\d+):\s+(.+)$", (folder / "chords.txt").read_text(), re.M))
    played = [f"A{i}" for i in range(1, 9)] * 2 + [f"B{i}" for i in range(1, 11)] * 2
    s = _tune_state("Cherokee Shuffle", "Tune", 1.0)
    assert _chord_names(breaks.chart_beats(s, 2, 4 * 36)) == " ".join(bars[b] for b in played).split()
    src = TUNE_MELODIES["Cherokee Shuffle"]
    tune = breaks.load_tune(src["folder"], src["key"], src["bars"], parts=src["parts"])
    assert tune.bars == 36 and tune.key == 9 and len(tune.melody()) == 110
    assert tune.notes[0].midi == 57 and [n.midi for n in tune.into_top()] == [52]  # A3; E3 back to the top
    # A's phrases land on F#4 and home; B's on E5 and, its last six bars, home
    assert [tune.arrival(j).midi for j in range(8)] == [66, 57, 66, 57, 76, 57, 76, 57]
    assert [tune.repeats(j) for j in range(8)] == [None, None, 0, 1, None, None, 4, 5]
    c, _ = _play(s, 7, 3, seconds=36 * 4 * 60 / 170 + 3)
    assert c.breaker is not None and c.breaker.k == 2 and c.breaker.shift == 0
    assert [n for p, n in c.breaker.heard if p == 0] == tune.notes  # as written, the first time round


def test_a_pick_stops_the_strings_note_while_it_may_sound(monkeypatch):
    """A pick on a string stops the note it holds until that note has surely ended (samples.RING_S, and a margin):
    without the stop, Csound ties the pick into a note still sounding, 3.8-4.0 s after it was picked, and it is lost."""
    from ambient import conductor as cmod
    monkeypatch.setattr(cmod.samples, "strung", lambda layer, voice: (406, (62, 59, 55, 50, 47, 43)))
    for gap, stopped in ((2.0, True), (3.9, True), (4.2, True), (5.0, False)):
        for tune_line in (True, False):
            clock = Clock()
            c = Conductor(clock, random.Random(1))
            c.apply(merge(DEFAULT, {}))
            for at in (10.0, 10.0 + gap):
                if tune_line:
                    c.play_strung_as(at, 61, 1.0, 0.1, "pick")
                else:
                    c.play_strung(at, 61, 1.0, 0.1)
            on = [n for n in clock.notes if int(n[1]) == 406]
            assert len(on) == 2 and on[0][1] == on[1][1]  # the same string
            offs = [n for n in clock.notes if n[1] == -on[0][1] and abs(n[0] - 10.0 - gap) < 1e-9]
            assert bool(offs) == stopped, (gap, tune_line)
