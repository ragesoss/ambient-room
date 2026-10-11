import math
import random

from ambient import music


def cents(a, b):
    return 1200 * math.log2(a / b)


MAJOR = music.default_tones(music.preset_slots("major"))


EQUAL = music.default_tones(music.preset_slots("major"), "equal")


def test_equal_tempered_tones_are_standard_pitch():
    r = music.resolve_pitches("C", EQUAL, [9, 0, 4])
    assert abs(music.freq(69, "C", r) - 440.0) < 1e-9


def test_the_key_note_stays_at_standard_pitch():
    for key in music.KEYS:
        root = 48 + music.KEYS.index(key)
        r = music.resolve_pitches(key, MAJOR, [])
        assert abs(cents(music.freq(root, key, r), music.hz(root))) < 1e-9


def test_fixed_just_has_a_wolf_on_ii_and_a_second_ratio_cures_it():
    dm7 = [2, 5, 9, 0]  # D F A C in C
    r = music.resolve_pitches("C", MAJOR, dm7)
    d, a = (music.freq(n, "C", r) for n in (62, 69))
    assert abs(cents(a, d) - 680.4) < 0.1  # 40/27: the wolf fifth
    both = dict(MAJOR, **{"2": ["9/8", "10/9"]})
    r = music.resolve_pitches("C", both, dm7)
    d, a = (music.freq(n, "C", r) for n in (62, 69))
    assert abs(cents(a, d) - 701.955) < 0.01
    assert r[2][0] == "10/9"


def test_tunings_mix_and_each_chord_takes_the_purer_pitch():
    mixed = dict(MAJOR, **{"4": ["ET", "5/4"], "7": ["ET"]})
    assert music.check_tones(mixed)["4"] == ["ET", "5/4"]
    r = music.resolve_pitches("C", mixed, [0, 4, 7])
    assert r[4][0] == "5/4" and r[7] == ("ET", 700.0)


def test_adaptive_tunes_every_chord_pure_and_keeps_roots_fixed():
    r = music.resolve_pitches("C", MAJOR, [2, 5, 9, 0], adaptive=True)
    d, f, a = (music.freq(n, "C", r) for n in (62, 65, 69))
    assert abs(cents(a, d) - 701.955) < 0.01 and abs(cents(f, d) - 315.641) < 0.01
    assert r[2][0] == "9/8"


def test_scales_are_spelled_one_letter_per_degree():
    def notes(key, scale):
        return music.describe_scale(key, music.default_tones(music.preset_slots(scale)))["notes"]
    assert notes("Eb", "minor") == "E♭ F G♭ A♭ B♭ C♭ D♭"
    assert notes("D", "lydian") == "D E F♯ G♯ A B C♯"
    assert notes("G", "hirajoshi") == "G A B♭ D E♭"
    assert notes("A", "whole_tone") == "A B C♯ D♯ E♯ G"


def test_custom_sets_and_presets_are_recognised():
    d = music.describe_scale("C", MAJOR)
    assert d["name"] == "Major (Ionian)" and d["steps"] == "W W H W W W H"
    assert music.describe_scale("C", dict(MAJOR, **{"2": ["10/9"]}))["tuning"] == "just intonation, your ratios"
    assert music.describe_scale("C", EQUAL)["tuning"] == "equal temperament"
    assert music.describe_scale("C", {"0": ["1"], "4": ["5/4"], "7": ["3/2"]})["name"] == "Custom"


def test_chords_in_major_get_numerals_and_symbols():
    slots, names, rng = music.preset_slots("major"), music.spell("C", music.preset_slots("major")), random.Random(1)
    got = []
    for root in [0, 2, 4, 5, 7, 9, 11]:
        pcs = music.build_chord("C", slots, root, 4, rng)
        got.append((music.numeral("C", slots, pcs), music.chord_symbol(pcs, names)))
    assert got == [("I", "Cmaj7"), ("ii", "Dm7"), ("iii", "Em7"), ("IV", "Fmaj7"),
                   ("V", "G7"), ("vi", "Am7"), ("vii°", "Bm7♭5")]


def test_inverted_shapes_are_slash_chords():
    names = music.spell("A", [0, 4, 7, 10])
    assert music.chord_symbol([4, 7, 9, 1], names) == "A7/E"
    assert music.numeral("A", [0, 4, 7, 10], [4, 7, 9, 1]) == "I/5"


def test_check_tones_keeps_the_key_note_and_rejects_strangers():
    assert music.check_tones({"4": ["5/4"]}) == {"0": ["1/1"], "4": ["5/4"]}
    for bad in ({"4": ["6/5"]}, {"12": ["1"]}, {"4": []}, {"0": ["ET"]}):
        try:
            music.check_tones(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_voicing_stays_near_the_center_without_doubles():
    prev, slots, rng = None, music.preset_slots("minor"), random.Random(2)
    for root in slots:
        v = music.voice(music.build_chord("Eb", slots, root, 5, rng), 59, prev)
        assert len(v) == len(set(v)) and all(abs(n - 59) <= 10 for n in v)
        prev = v
