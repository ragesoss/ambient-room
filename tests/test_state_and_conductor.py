import copy
import random

import pytest

from ambient.conductor import Conductor
from ambient.engine import FakeEngine
from ambient.sounds import LAYERS
from ambient import explain
from ambient.state import DEFAULT, MOODS, Invalid, merge, surprise, upgrade


class Clock(FakeEngine):
    def __init__(self):
        super().__init__()
        self.t = 0.0

    def time(self):
        return self.t


def run(c, clock, seconds):
    end = clock.t + seconds
    while clock.t < end:
        c.tick()
        clock.t += 0.2


def test_moods_and_surprises_are_valid():
    for m in MOODS.values():
        assert merge(DEFAULT, m) == merge(DEFAULT, m)
    rng = random.Random(3)
    for _ in range(50):
        s = surprise(DEFAULT, rng)
        assert merge(DEFAULT, s)["layers"]["pad"]["voice"] in LAYERS["pad"]


def test_merge_rejects_unknowns_and_clamps():
    with pytest.raises(Invalid):
        merge(DEFAULT, {"key": "H"})
    with pytest.raises(Invalid):
        merge(DEFAULT, {"layers": {"pad": {"voice": "Kazoo"}}})
    assert merge(DEFAULT, {"shape": {"bright": 7}})["shape"]["bright"] == 1.0


def test_conductor_plays_every_layer():
    clock = Clock()
    c = Conductor(clock, random.Random(1))
    s = copy.deepcopy(DEFAULT)
    s["beat"]["pulse"] = "Arp"
    c.apply(s)
    run(c, clock, 60)
    instrs = {int(abs(n[1])) for n in clock.notes}
    assert {11, 21, 31, 41, 52} <= instrs
    assert all(n[0] <= 61 for n in clock.notes)


def test_adaptive_replays_the_same_chord_and_fades_the_old():
    clock = Clock()
    c = Conductor(clock, random.Random(2))
    c.apply(copy.deepcopy(DEFAULT))
    run(c, clock, 5)
    pcs, n0 = c.pcs, len(clock.notes)
    s = merge(DEFAULT, {"adaptive": True})
    c.apply(s)
    assert clock.channels["gen"] == 1
    run(c, clock, 1)
    assert c.pcs == pcs
    new_pads = [n for n in clock.notes[n0:] if n[1] == 11]
    assert new_pads and all(n[-1] == 1 for n in new_pads)  # p8: the new chord number


def test_old_saved_settings_are_upgraded():
    s = merge(DEFAULT, upgrade({"key": "A", "feel": "Wistful", "tuning": "Standard"}))
    assert sorted(map(int, s["tones"])) == [0, 2, 3, 5, 7, 9, 10]
    assert s["tones"]["3"] == ["ET"] and "tuning" not in s
    s = merge(DEFAULT, upgrade({"key": "A", "scale": "lydian", "tuning": "adaptive"}))
    assert s["adaptive"] is True and s["tones"]["4"] == ["5/4"]
    assert "6" in s["tones"] and "scale" not in s


def test_new_ratios_for_the_same_tones_replay_the_same_chord():
    clock = Clock()
    c = Conductor(clock, random.Random(5))
    s = merge(DEFAULT, {"scale": "major"})
    c.apply(s)
    run(c, clock, 3)
    pcs = c.pcs
    c.apply(merge(s, {"tones": dict(s["tones"], **{"2": ["10/9"]})}))
    run(c, clock, 1)
    assert c.pcs == pcs and clock.channels["gen"] == 1


def test_explain_says_what_is_playing():
    clock = Clock()
    c = Conductor(clock, random.Random(4))
    s = merge(DEFAULT, {"key": "C", "scale": "major"})
    c.apply(s)
    run(c, clock, 2)
    ex = explain.describe(s, c, clock.t)
    assert ex["scale"]["formula"] == "1 2 3 4 5 6 7"
    now = ex["now"]
    assert now["numeral"] and now["chord"] and len(now["notes"]) >= 3
    assert all(n["pitch"] for n in now["notes"])
    assert "BPM" in ex["shape"]["tempo"] and "chord" in ex["harmony"]["rhythm"] and "dB" in ex["volume"]


def test_chords_change_on_the_downbeat_and_drums_sit_on_the_grid():
    clock = Clock()
    c = Conductor(clock, random.Random(6))
    s = merge(DEFAULT, {"beat": {"drums": "House", "bass": "Offbeat"}, "layers": {"bass": {"voice": "Synth"}},
                        "harmony": {"rhythm": 1.0}, "shape": {"tempo": 0.7, "swing": 0.0}})
    c.apply(s)
    run(c, clock, 12)
    bar = 4 * 60 / 120  # 120 BPM
    first = 0.1  # the grid starts at the conductor's first step
    kicks = [n[0] for n in clock.notes if n[1] == 61]
    assert len(kicks) >= 16  # four on the floor
    beat = bar / 4
    assert all(abs(((k - first) / beat) - round((k - first) / beat)) < 1e-6 for k in kicks)
    assert any(n[1] == 24 for n in clock.notes)  # the offbeat bass


def test_swing_delays_the_off_sixteenths():
    clock = Clock()
    c = Conductor(clock, random.Random(7))
    s = merge(DEFAULT, {"beat": {"drums": "Techno"}, "shape": {"tempo": 0.7, "swing": 1.0}})
    c.apply(s)
    run(c, clock, 4)
    step = 60 / 120 / 4
    hats = sorted(n[0] for n in clock.notes if n[1] == 64 and n[2] < 0.2)
    first = 0.1
    offs = [((h - first) / step) % 1 for h in hats]
    assert any(abs(o - 1 / 3) < 1e-6 for o in offs)  # a third of a step late


def test_evolution_changes_one_unlocked_setting_at_a_time():
    from ambient import evolve
    rng = random.Random(8)
    s = merge(DEFAULT, {"locks": {"tones": True, "key": True}})
    seen = set()
    for _ in range(200):
        new, what = evolve.step(s, rng, 0.5)
        assert new["tones"] == s["tones"] and new["key"] == s["key"] and new["volume"] == s["volume"]
        diff = [k for k in ("adaptive",) if new[k] != s[k]]
        diff += [f"shape.{k}" for k in new["shape"] if new["shape"][k] != s["shape"][k]]
        diff += [f"layers.{k}" for k in new["layers"] if new["layers"][k] != s["layers"][k]]
        diff += [f"melody.{k}" for k in new["melody"] if new["melody"][k] != s["melody"][k]]
        diff += [f"harmony.{k}" for k in new["harmony"] if new["harmony"][k] != s["harmony"][k]]
        diff += [f"beat.{k}" for k in new["beat"] if new["beat"][k] != s["beat"][k]]
        assert len(diff) == 1, (what, diff)
        seen.add(diff[0].split(".")[0])
        s = new
    assert {"shape", "layers"} <= seen


def test_scale_evolves_a_tone_at_a_time_and_keeps_the_key_note():
    from ambient import evolve
    rng = random.Random(9)
    locks = [p for p in evolve.lockable() if p != "tones"]
    s = merge(DEFAULT, {"scale": "major", "locks": locks})
    for _ in range(60):
        new, what = evolve.step(s, rng, 0.3)
        assert what.startswith("Scale")
        a, b = set(s["tones"]), set(new["tones"])
        assert "0" in b and 4 <= len(b) <= 9 and len(a ^ b) <= 2
        s = new


def test_moods_and_surprises_keep_locked_settings():
    from ambient.state import keep_locked
    s = merge(DEFAULT, {"key": "F#", "scale": "dorian", "locks": {"key": True, "tones": True}})
    m = keep_locked(merge(DEFAULT, MOODS["Trance"]), s)
    assert m["key"] == "F#" and m["tones"] == s["tones"] and m["layers"]["pad"]["voice"] == "Supersaw"


def test_evolution_can_change_several_settings_at_once():
    from ambient import evolve
    rng = random.Random(10)
    s = merge(DEFAULT, {})
    new, what = evolve.step(s, rng, 0.5, 5)
    changed = [k for k in new["shape"] if new["shape"][k] != s["shape"][k]]
    changed += [k for k in new["layers"] if new["layers"][k] != s["layers"][k]]
    changed += [k for k in ("key", "tones", "adaptive") if new[k] != s[k]]
    changed += [f"melody.{k}" for k in new["melody"] if new["melody"][k] != s["melody"][k]]
    changed += [f"harmony.{k}" for k in new["harmony"] if new["harmony"][k] != s["harmony"][k]]
    changed += [f"beat.{k}" for k in new["beat"] if new["beat"][k] != s["beat"][k]]
    assert len(changed) == 5 and what.count("; ") == 4


def test_evolution_cannot_break_the_conductor():
    from ambient import evolve
    for seed in range(25):
        rng = random.Random(seed)
        clock = Clock()
        c = Conductor(clock, random.Random(seed))
        s = merge(DEFAULT, {"layers": {"bass": {"voice": "Acid"}, "pad": {"voice": "Synth stab"}},
                            "beat": {"bass": "Acid line", "drums": "Techno", "pulse": "Arp", "chords": "Stabs"}})
        c.apply(s)
        for _ in range(120):
            new, _ = evolve.step(s, rng, 1.0, rng.choice([1, 3, 8]))
            if new:
                s = new
                c.apply(s)
            for _ in range(rng.choice([0, 1, 3])):
                c.tick()
                clock.t += 0.2
            explain.describe(s, c, clock.t)
            assert c.error is None, (seed, c.error, sorted(map(int, s["tones"])))


def test_the_compass_places_moods_sensibly():
    from ambient import evolve
    calm, energetic = evolve.position(MOODS["Deep"]), evolve.position(MOODS["Techno"])
    assert calm[0] < 0.3 < 0.55 < energetic[0]
    assert evolve.scale_brightness([0, 2, 4, 6, 7, 9, 11]) == 1.0      # Lydian
    assert evolve.scale_brightness([0, 1, 3, 5, 6, 8, 10]) == 0.0      # Locrian
    assert abs(evolve.scale_brightness([0, 2, 3, 5, 7, 9, 10]) - 0.5) < 1e-9  # Dorian


def test_a_direction_pulls_the_walk_toward_it():
    from ambient import evolve
    rng = random.Random(11)
    s = merge(DEFAULT, {"locks": {"volume": True}})
    start = evolve.position(s)
    for _ in range(40):
        s, _ = evolve.step(s, rng, 0.4, 2, target=[1.0, 1.0], pull=1.0)
    end = evolve.position(s)
    assert end[0] > start[0] + 0.2 and end[1] > start[1] + 0.1


def _melodist_run(style, bars, seed, chord=(7, 11, 2, 5), notes=None, **line):
    """Bars of a melody against one chord: [(bar, onset, note, length, phrase kind, last bar of phrase)]."""
    from ambient import music
    from ambient.melody import Melodist
    s = merge(DEFAULT, {"key": "C", "scale": "major", "melody": {"style": style, **line},
                        "shape": {} if notes is None else {"notes": notes}})
    scale = music.scale_notes("C", music.slots_of(s["tones"]), 60, 84)
    m = Melodist(random.Random(seed))
    out = []
    for bar in range(bars):
        m.begin_bar(bar, s)
        m.plan_bar(bar, bar * 16, s, scale, list(chord))
        for k in range(16):
            for note, length, vel, frac in m.at(bar * 16 + k):
                out.append((bar, k + frac, note, length, m.phrase["kind"], bar == m.phrase["end"] - 1))
    return out


def test_phrases_start_on_the_downbeat_without_syncopation_or_pickups():
    for seed in range(10):
        played = _melodist_run("Phrases", 16, seed, phrase=0.6, syncopation=0.0, pickups=0.0)
        starts = {b for b in range(0, 16, 4)}
        first = {}
        for bar, k, *_ in played:
            first.setdefault(bar, k)
        assert all(first.get(b) == 0 for b in starts if b in first), (seed, first)


def test_answers_end_on_the_chord_root_held():
    for seed in range(10):
        played = _melodist_run("Phrases", 16, seed, phrase=0.6, syncopation=0.2, pickups=0.0)
        ends = [p for p in played if p[5] and p[4] == "answer"]
        last = max(ends, key=lambda p: (p[0], p[1]))
        assert last[2] % 12 == 7 and last[3] >= 4, (seed, last)  # G, the root of G7, held


def test_pickups_lead_into_the_next_bar():
    played = _melodist_run("Phrases", 32, 3, phrase=0.6, syncopation=0.0, pickups=1.0)
    lead_ins = [p for p in played if p[5] and p[1] >= 12]
    assert lead_ins and all(p[3] <= 2 for p in lead_ins)


def test_notes_sit_on_the_grid_and_in_range():
    played = _melodist_run("Motif", 16, 4, syncopation=0.7)
    assert played and all(60 <= p[2] <= 84 and 0 <= p[1] < 16 for p in played)


def test_answers_lean_the_harmony_home():
    from ambient.harmony import Harmonist
    s = merge(DEFAULT, {"key": "C", "scale": "major"})
    slots = [0, 2, 4, 5, 7, 9, 11]
    h = Harmonist(random.Random(14))
    home = [h._wander(s, slots, 7, "answer") for _ in range(300)].count(1) / 300
    away = [h._wander(s, slots, 7, "question") for _ in range(300)]
    free = [h._wander(s, slots, 7, None) for _ in range(300)].count(1) / 300
    assert home > 0.7 and free < 0.4 and away.count(2) + away.count(4) > 100  # V (from V: ii) and IV


def test_melody_moods_use_shaped_lines():
    for name in ("Song", "Nocturne", "Music box", "Elegy", "Anthem", "Chiptune", "Rock band", "Jazz club"):
        assert MOODS[name]["melody"]["style"] in ("Motif", "Phrases")


# ---- harmony's form ----

def _chords(c, clock, seconds):
    """The chord events heard in `seconds`: (slot, root, pos, notes' slots)."""
    run(c, clock, seconds)
    return [(e["slot"], e["root"], e["pos"], tuple(sorted({n["slot"] for n in e["notes"]})))
            for e in c.events if e["kind"] == "chord"]


def test_degrees_fit_any_scale():
    from ambient.harmony import degree_slot, numeral
    from ambient.music import preset_slots
    major, minor, pent = preset_slots("major"), preset_slots("minor"), preset_slots("major_pentatonic")
    assert [degree_slot(major, d) for d in (1, 5, 6, 4)] == [0, 7, 9, 5]
    assert [degree_slot(minor, d) for d in (1, 6, 3, 7)] == [0, 8, 3, 10]
    assert degree_slot(pent, 4) == 2 and degree_slot(pent, 7) == 7  # no 4 or 7: ii and V stand in
    assert degree_slot(preset_slots("chromatic"), 3) == 4  # the plain 3, not b3
    assert [numeral("C", major, d) for d in (1, 5, 6, 4)] == ["I", "V", "vi", "IV"]
    assert [numeral("C", minor, d) for d in (1, 5, 6, 4)] == ["i", "v", "♭VI", "iv"]


def test_a_loop_repeats_the_same_chords_from_its_first():
    clock = Clock()
    c = Conductor(clock, random.Random(20))
    s = merge(DEFAULT, {"key": "C", "scale": "major", "shape": {"tempo": 0.7},
                        "harmony": {"style": "Loop", "loop": "1-5-6-4", "size": 0.8, "rhythm": 1.0}})
    c.apply(s)
    heard = _chords(c, clock, 30)  # 15 bars at 120 BPM, a chord a bar
    assert len(heard) >= 12
    assert [h[1] for h in heard[:8]] == [0, 7, 9, 5] * 2
    assert all(slot % 4 == pos for slot, _, pos, _ in heard)
    by_pos = {}
    for _, _, pos, notes in heard:
        by_pos.setdefault(pos, set()).add(notes)
    assert all(len(v) == 1 for v in by_pos.values()), by_pos  # the same chord each time round


def test_functional_cycles_end_in_cadences():
    from ambient.harmony import Harmonist
    from ambient.music import preset_slots
    major = preset_slots("major")
    h = Harmonist(random.Random(21))
    for _ in range(50):
        cyc = h.functional_cycle(4, 1.0, major)
        assert len(cyc) == 4 and cyc[-1] == 1 and cyc[-2] in (4, 5), cyc  # always home: V-I or IV-I
        assert all(a != b for a, b in zip(cyc, cyc[1:])), cyc
    ends = [h.functional_cycle(4, 0.0, major)[-1] for _ in range(200)]
    assert ends.count(5) > 120  # rarely home: half cadences
    # in the middle, question and answer: an open cycle is mostly followed by one that comes home
    pairs = [(h.functional_cycle(4, 0.5, major)[-1]) for _ in range(400)]
    after_open = [b for a, b in zip(pairs, pairs[1:]) if a == 5]
    assert sum(b in (1, 6) for b in after_open) / len(after_open) > 0.7


def test_functional_harmony_cycles_on_the_bar_grid():
    clock = Clock()
    c = Conductor(clock, random.Random(22))
    s = merge(DEFAULT, {"key": "C", "scale": "major", "shape": {"tempo": 0.7},
                        "harmony": {"style": "Functional", "length": 0.5, "resolve": 0.6, "rhythm": 1.0}})
    c.apply(s)
    heard = _chords(c, clock, 70)
    ends = [root for slot, root, pos, _ in heard if slot % 4 == 3]
    assert len(ends) >= 6 and all(r in (0, 7, 9) for r in ends), ends  # I, V or (deceptive) vi
    assert ends.count(0) >= 2
    assert all(slot % 4 == pos for slot, _, pos, _ in heard)


def test_the_melody_follows_the_harmony_home():
    def cadences(loop):
        clock = Clock()
        c = Conductor(clock, random.Random(23))
        s = merge(DEFAULT, {"key": "C", "scale": "major", "shape": {"tempo": 0.7, "notes": 0.5},
                            "layers": {"melody": {"voice": "Felt"}},
                            "melody": {"style": "Phrases", "phrase": 0.6, "pickups": 0.0},
                            "harmony": {"style": "Loop", "loop": loop, "rhythm": 1.0}})
        c.apply(s)
        run(c, clock, 40)
        bar, out, step_k = -1, [], {}
        for e in c.events:
            if e["kind"] == "step":
                bar += e["k"] == 0
                step_k[e["t"]] = (bar, e["k"])
            elif e["kind"] == "melody" and step_k.get(e["t"]) and step_k[e["t"]][1] == 8 and step_k[e["t"]][0] % 4 == 3:
                out.append(e["slot"])  # the cadence note: beat 3 of a phrase's last bar
        return out
    home = cadences([6, 2, 5, 1])  # phrases end over I: answers, on the home note
    assert len(home) >= 3 and all(x == 0 for x in home), home
    away = cadences([1, 5, 6, 4])  # over IV: questions, on a chord tone that is not F
    assert len(away) >= 3 and all(x in (9, 0, 4) for x in away), away


def test_loops_are_checked():
    s = merge(DEFAULT, {"harmony": {"loop": "Canon"}})
    assert s["harmony"]["loop"] == [1, 5, 6, 3, 4, 1, 4, 5]
    for bad in ([], [0], [8], [1] * 33, ["1"], [True], "nope", 5, [{"chord": 1, "beats": 0}], [{"chord": "X"}]):
        with pytest.raises(Invalid):
            merge(DEFAULT, {"harmony": {"loop": bad}})
    with pytest.raises(Invalid):
        merge(DEFAULT, {"harmony": {"style": "Jazz"}})


def test_evolution_changes_a_loop_a_chord_at_a_time():
    from ambient import evolve
    rng = random.Random(24)
    locks = [p for p in evolve.lockable() if p != "harmony.loop"]
    s = merge(DEFAULT, {"harmony": {"style": "Loop", "loop": [1, 5, 6, 4]}, "locks": locks})
    for _ in range(40):
        new, what = evolve.step(s, rng, 0.2)
        assert what.startswith("Loop") and 1 <= len(new["harmony"]["loop"]) <= 32, what
        s = new


# ---- parts: voices and patterns, presets ----

def _notes_by_instr(state, seconds=12, seed=30):
    clock = Clock()
    c = Conductor(clock, random.Random(seed))
    c.apply(state)
    run(c, clock, seconds)
    return clock, c


def test_any_bass_voice_plays_any_line():
    from ambient.sounds import LAYERS, PATTERNS
    for line in PATTERNS["bass"]:
        for voice in ("Upright", "808", "Reese"):
            s = merge(DEFAULT, {"beat": {"bass": line}, "layers": {"bass": {"voice": voice}},
                                "shape": {"tempo": 0.7}, "harmony": {"rhythm": 1.0}})
            clock, c = _notes_by_instr(s)
            bass = [n for n in clock.notes if n[1] == LAYERS["bass"][voice][0]]
            assert c.error is None and bass, (line, voice)
            if line == "Walking":  # a note on every beat
                beat = 0.5
                assert all(abs((n[0] - 0.1) / beat - round((n[0] - 0.1) / beat)) < 1e-6 for n in bass)
                assert len(bass) >= 20


def test_chord_size_and_plain_triads():
    s = merge(DEFAULT, {"harmony": {"size": 0.0}})
    clock, c = _notes_by_instr(s, 20)
    assert not [n for n in clock.notes if n[1] == 11] and c.pcs and len(c.pcs) >= 3  # no chord notes; the harmony goes on
    s = merge(DEFAULT, {"scale": "major", "harmony": {"size": 1.0, "plain": True, "rhythm": 1.0}, "shape": {"tempo": 0.7}})
    clock, c = _notes_by_instr(s, 30)
    for e in c.events:
        if e["kind"] == "chord":
            rel = sorted({(n["slot"] - e["root"]) % 12 for n in e["notes"]})
            assert rel in ([0, 4, 7], [0, 3, 7]), rel


def test_borrowing_brings_chords_from_outside_the_scale():
    from ambient.harmony import BORROWED, Harmonist
    from ambient.music import preset_slots
    h = Harmonist(random.Random(31))
    major, minor = preset_slots("major"), preset_slots("minor")
    none = [d for _ in range(50) for d in h.functional_cycle(4, 0.7, major, 0.0)]
    assert all(isinstance(d, int) for d in none)
    some = [d for _ in range(80) for d in h.functional_cycle(4, 0.7, major, 0.8)]
    assert {"iv", "V/V"} & set(some) and all(isinstance(d, int) or d in BORROWED for d in some)
    minor_v = [d for _ in range(80) for d in h.functional_cycle(4, 1.0, minor, 0.6)]
    assert "V" in minor_v and 5 not in minor_v  # a minor key's dominant made major
    s = merge(DEFAULT, {"harmony": {"style": "Loop", "loop": [1, "♭VII", 4, 1], "rhythm": 1.0}, "shape": {"tempo": 0.7}})
    clock, c = _notes_by_instr(s, 20)
    assert c.error is None and 10 in {e["root"] for e in c.events if e["kind"] == "chord"}


def test_a_part_preset_changes_only_its_part():
    from ambient.presets import PARTS
    from ambient.state import apply_values, get_path, preset_values
    s = merge(DEFAULT, {"key": "E", "layers": {"pad": {"voice": "Organ"}}, "locks": {"beat.bass": True}})
    for part in PARTS:
        from ambient.presets import BY_PART
        for name in BY_PART[part]:
            new = apply_values(s, preset_values(part, name))
            for other, (_, paths) in PARTS.items():
                for p in paths:
                    if other != part or p in s["locks"]:
                        assert get_path(new, p) == get_path(s, p), (part, name, p)
            assert new["key"] == "E"


def test_old_saved_voices_and_pace_are_split():
    s = merge(DEFAULT, upgrade({"layers": {"bass": {"voice": "Offbeat", "level": 0.5},
                                           "pad": {"voice": "Stabs", "level": 0.6},
                                           "pulse": {"voice": "Arp", "level": 0.4},
                                           "drums": {"voice": "House", "level": 0.7}},
                                "shape": {"pace": 0.75, "tempo": 0.7}, "harmony": {"color": 0.5},
                                "locks": ["volume", "layers.drums", "shape.pace"]}))
    assert s["beat"] == {"drums": "House", "bass": "Offbeat", "chords": "Stabs", "pulse": "Arp"}
    assert s["layers"]["bass"]["voice"] == "Synth" and s["layers"]["drums"]["voice"] == "Electronic"
    assert s["harmony"]["rhythm"] == 0.75 and s["harmony"]["size"] == 0.8  # 2 bars a chord; four notes
    assert {"beat.drums", "layers.drums", "harmony.rhythm"} <= set(s["locks"])


# ---- charts ----

CHART = """| C / | F G | C / | F G/D |
| C / | F G | C / | F/C E/B |
| Am / | Em / | F / | C Em/B |
| Am / | Em / | F / | / / |
| E / | E7 / |"""


def test_a_chart_is_read_in_the_key():
    from ambient.harmony import numeral, parse_chart, timeline
    from ambient.music import preset_slots
    major = preset_slots("major")
    loop = parse_chart(CHART, "C", major)
    assert " ".join(numeral("C", major, e) for e in loop) == \
        "I IV V I IV V I IV V I IV III vi iii IV I iii vi iii IV III III7"
    assert timeline({"loop": loop, "rhythm": 1.0})[1] == 18 * 16  # 18 bars
    assert loop[1] == {"chord": 4, "beats": 2.0} and loop[19] == {"chord": 4, "beats": 8.0}
    assert parse_chart("| G / | C D |", "G", major) == parse_chart("| C / | F G |", "C", major)  # degrees: any key
    s = merge(DEFAULT, {"key": "C", "scale": "major", "harmony": {"chart": CHART}})
    assert s["harmony"]["style"] == "Loop" and len(s["harmony"]["loop"]) == 22
    with pytest.raises(Invalid):
        merge(DEFAULT, {"harmony": {"chart": "| C / | Qm |"}})


def test_a_chart_changes_chords_where_it_says():
    s = merge(DEFAULT, {"key": "C", "scale": "major", "shape": {"tempo": 0.7},
                        "melody": {"style": "Phrases", "phrase": 0.6}, "harmony": {"chart": CHART, "plain": True, "size": 0.6}})
    clock, c = _notes_by_instr(s, 80, seed=40)  # 40 bars at 120 BPM: twice round
    steps = []
    for e in c.events:  # the chords, by bar and sixteenth: a bar is 2 s, the grid starts at 0.1 s
        if e["kind"] == "chord":
            bar, rest = divmod(round((e["t"] - 0.1) / 0.125), 16)
            steps.append((bar, rest, e["root"], len(e["notes"])))
    assert c.error is None
    assert [x for x in steps if 18 <= x[0] <= 20][:4] == [(18, 0, 0, 3), (19, 0, 5, 3), (19, 8, 7, 3), (20, 0, 0, 3)]  # C | F G | C
    assert (35, 0, 4, 4) in steps and (34, 0, 4, 3) in steps  # E then E7: the seventh is written
    assert (36, 0, 0, 3) in steps  # round again
    # the melody's phrases start with the chart: bars 0, 4, 8, 12, 16 (two bars left), 18
    starts = []
    from ambient.melody import Melodist
    m, st = Melodist(random.Random(3)), s
    for b in range(40):
        m.begin_bar(b, st, (b % 18, 18))
        if m.phrase["start"] == b:
            starts.append(b)
    assert starts[:7] == [0, 4, 8, 12, 16, 18, 22]


def test_every_preset_is_reachable_by_hand_and_by_evolution():
    """No preset may need anything the controls and evolution cannot make:
    its loop's chords come from the shared vocabulary, its lengths from
    splitting, merging, doubling and halving."""
    from ambient.harmony import beats_of, chord_of, vocabulary
    from ambient.presets import BY_PART
    from ambient.music import slots_of
    from ambient.state import preset_values
    for name in BY_PART["harmony"]:
        v = preset_values("harmony", name)
        vocab = vocabulary(slots_of(v["tones"]))
        for e in v["harmony.loop"]:
            assert chord_of(e) in vocab, (name, e)
            assert beats_of(e) is None or 1 <= beats_of(e) <= 32, (name, e)


def test_evolution_reaches_what_a_chart_holds():
    from ambient import evolve
    from ambient.harmony import BORROWED, beats_of, chord_of, roman
    rng = random.Random(50)
    s = merge(DEFAULT, {"key": "C", "scale": "major",
                        "harmony": {"style": "Loop", "loop": [1, 5, 6, 4], "borrow": 0.5, "rhythm": 1.0}})
    half = seventh = long = False
    for _ in range(600):
        change, _ = evolve._harmony("loop", s, rng, 0.4)
        if change:
            s = merge(s, change)
        loop = s["harmony"]["loop"]
        half |= any(beats_of(e) == 2 for e in loop)
        seventh |= any(isinstance(chord_of(e), str) and chord_of(e) not in BORROWED and roman(chord_of(e))[2] for e in loop)
        long |= len(loop) > 8
    assert half and seventh and long


def test_every_voice_and_pattern_is_known_to_the_conductor_and_orchestra():
    """A voice needs an instrument in the orchestra and, for the melody, its
    note lengths; a pattern needs its notes in the conductor."""
    from ambient import conductor
    from ambient.engine import ORC
    from ambient.sounds import LAYERS, PATTERNS
    orc = ORC.read_text()
    for layer, voices in LAYERS.items():
        for v, spec in voices.items():
            if layer != "drums":
                assert f"instr {spec[0]} " in orc, (layer, v)
            if layer == "melody":
                assert v in conductor.MELODY_DUR or v in conductor.MELODY_STEPS, v
    assert set(PATTERNS["drums"]) == set(conductor.DRUMS)
    assert set(PATTERNS["bass"]) - {"Held", "Walking", "Acid line", "Walk-ups"} == set(conductor.BASS_LINES)
    chords = set(conductor.CHORD_HITS) | {"Held", "Stabs", "Strum", "Comp", "Boom-chick", "Travis"}
    assert set(PATTERNS["chords"]) <= chords
    assert set(PATTERNS["pulse"]) <= {"Arp", "Arp 16ths", "Glints", "Heartbeat"} | set(conductor.ROLLS)


def test_notes_past_busy_run_on_and_then_go_frenetic():
    """Notes 0.75 is the old busiest; past it, running sixteenths, then thirty-seconds."""
    def per_bar(notes):
        played = _melodist_run("Phrases", 32, 7, notes=notes, phrase=0.3)
        return len(played) / 32, sum(p[1] % 1 for p in played) > 0, played
    busy, busy32, _ = per_bar(0.75)
    running, _, run = per_bar(0.875)
    frantic, frantic32, fr = per_bar(1.0)
    assert busy < running < frantic and not busy32 and frantic32
    assert frantic > 16  # faster than sixteenths
    steps = [abs(b[2] - a[2]) for a, b in zip(run, run[1:])]
    assert steps.count(0) / len(steps) < 0.1  # a fast run rarely repeats a note


def test_sampled_voices_fall_back_to_their_models():
    """A sampled voice plays its recording when its font loaded, its synthesized model when not."""
    from pathlib import Path
    from ambient import samples
    from ambient.sounds import LAYERS, instr
    try:
        assert samples.orchestra(None) == "" and instr("melody", "Fiddle") == LAYERS["melody"]["Fiddle"][0]
        assert samples.orchestra(Path("/nowhere")) == "" and instr("bass", "Upright") == LAYERS["bass"]["Upright"][0]
        here = Path(__file__).resolve().parent.parent / "sounds"
        if (here / samples.FONTS["acoustic"]).is_file():
            orc = samples.orchestra(here)
            assert "sfload" in orc and instr("melody", "Fiddle") >= samples.STRUCK
            assert instr("bass", "Upright") >= samples.BASS and instr("melody", "Bell") == LAYERS["melody"]["Bell"][0]
    finally:
        samples.orchestra(None)  # the other tests use the models
