"""The Tune line (ambient/breaks.py): a break on a tune's melody, from as written to the free line."""

import copy
import random

import pytest

from ambient import breaks
from ambient.breaks import BAR, Break, Note, Tune, measure
from ambient.conductor import Conductor
from ambient.engine import FakeEngine
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


def _red_wing_state(style: str, pull: float = 0.5) -> dict:
    s = copy.deepcopy(MOODS["Red Wing"])
    s["melody"]["style"] = style
    s["melody"]["pull"] = pull
    s["evolve"]["rate"] = 0.0
    return s


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
    for pull, seed in ((1.0, 1), (0.5, 1), (0.5, 2), (0.0, 1)):
        _, notes = _play(_red_wing_state("Tune", pull), 11, seed)
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


@pytest.mark.skipif(breaks.project_root() is None, reason="needs the transcription project's tunes")
def test_the_tunes_keys_read_as_one_pass():
    rw = breaks.load_tune("red-wing", "G", 16)
    assert rw.bars == 16 and rw.notes[0].midi == 55 and [n.midi for n in rw.into_top()] == [50]
    dy = breaks.load_tune("down-yonder", "G", 20)
    assert [n.midi for n in dy.lead_in] == [62, 61, 60] and [n.midi for n in dy.into_top()] == [62, 61, 60]
    bs = breaks.load_tune("big-sciota", "G", 16)
    assert [n.midi for n in bs.into_top()] == [50] and bs.notes[-1].t == 63.5
