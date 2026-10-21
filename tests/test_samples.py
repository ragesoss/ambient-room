"""The sample extraction (tools/samples.py): its measurements on synthetic notes, the loop, the click gate, and the
SoundFont it writes from a map."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("samples", REPO / "tools" / "samples.py")
S = importlib.util.module_from_spec(spec)
sys.modules["samples"] = S  # its dataclasses look it up
spec.loader.exec_module(S)
SR = 48000


def pluck(f0: float, at_s: float, length_s: float = 2.0, decay_s: float = 0.8, partials: int = 8,
          noise: float = 0.0, seed: int = 0) -> np.ndarray:
    """A plucked string: silence, then partials decaying from `at_s`, with a burst of noise at the pluck."""
    n = int((at_s + length_s) * SR)
    t = np.arange(n - int(at_s * SR)) / SR
    x = np.zeros(n)
    x[int(at_s * SR):] = sum(0.3 / h * np.sin(2 * np.pi * f0 * h * t) * np.exp(-t * h ** 0.5 / decay_s)
                             for h in range(1, partials + 1))
    if noise:
        rng = np.random.default_rng(seed)
        k = int(at_s * SR)
        x[k:k + 96] += noise * rng.standard_normal(96) * np.exp(-np.arange(96) / 24)
    return x + 1e-6 * np.random.default_rng(seed + 1).standard_normal(n)


def test_find_attack_by_level_and_by_the_pick_band():
    x = pluck(41.2, 0.5, noise=0.2)
    for band in (None, (3000.0, 8000.0)):
        t = S.find_attack(x, SR, 0.52, band, 0.04, 0.08, 10.0)
        assert abs(t - 0.5) < 0.004, band  # the band's frame starts up to 3 ms before what it holds


def test_damped_against_rung_on():
    x = pluck(55.0, 0.0, 2.0)
    assert S.damped_at(x, SR) is None
    y = x.copy()
    y[int(0.6 * SR):] *= np.exp(-np.arange(len(y) - int(0.6 * SR)) / (0.01 * SR))
    assert abs(S.damped_at(y, SR) - 0.55) < 0.06


def test_tick_found_over_a_ring_and_not_without():
    x = pluck(41.2, 0.0, 1.5)
    clean, _ = S.tick_db(x, SR)
    tt = np.arange(int(0.03 * SR)) / SR
    y = x.copy()
    k = int(0.065 * SR)
    y[k:k + len(tt)] += 0.05 * np.sin(2 * np.pi * 2000 * tt) * np.exp(-tt / 0.006)
    ticked, where = S.tick_db(y, SR)
    assert clean < 6 and ticked > S.TICK_DB and abs(where - 0.065) < 0.01


def test_gate_takes_a_click_down_and_leaves_the_note():
    x = pluck(41.2, 0.0, 1.0, partials=6)
    tt = np.arange(int(0.03 * SR)) / SR
    click = 0.05 * np.sin(2 * np.pi * 2000 * tt) * np.exp(-tt / 0.006)
    k = int(0.4 * SR)
    y = x.copy()
    y[k:k + len(click)] += click
    g = S.gate_clicks(y, SR, (k,))
    hi = lambda z: S.rms_db(S.band(z, SR, 1500, 6000)[k:k + len(click)])
    assert hi(y) - hi(g) > 30
    low = lambda z: S.band(z, SR, 20, 300)
    assert np.max(np.abs(low(g) - low(y))) < 1e-3 * np.max(np.abs(x))


def test_pitch_checks():
    x = pluck(41.2 * 2 ** (10 / 1200), 0.0, 1.5)[int(0.1 * SR):int(1.2 * SR)]  # E1, 10 cents sharp
    assert abs(S.partial_cents(x, SR, 28) - 10) < 1.5
    assert abs(S.pyin_midi(x, SR, 28) - 28.1) < 0.2
    assert S.octave_doubt(x, SR, 41.2) is None
    e2 = pluck(82.4, 0.0, 1.5)[int(0.1 * SR):int(1.2 * SR)]  # an E2 labelled E1: no odd partials of E1
    assert S.octave_doubt(e2, SR, 41.2) == "up"


def test_ringing_note_before():
    a1 = pluck(55.0, 0.0, 1.2)
    e1 = pluck(41.2, 0.0, 1.2)
    seg = slice(int(0.1 * SR), int(1.1 * SR))
    alone = S.ringing_db(a1[seg], SR, 55.0, 41.2)
    under = S.ringing_db((a1 + 0.5 * e1)[seg], SR, 55.0, 41.2)
    assert alone < S.RINGING_DB < under


def test_loop_found_in_a_sustained_note_not_in_a_pluck():
    t = np.arange(int(3 * SR)) / SR
    bowed = sum(0.2 / h * np.sin(2 * np.pi * 55 * h * t + h) for h in range(1, 10)) * np.minimum(1, t / 0.2)
    lp = S.find_loop(bowed, SR, 55.0)
    assert lp is not None and lp[3] > 0.99 and lp[2] - lp[1] >= 0.3 * SR
    assert S.find_loop(pluck(55.0, 0.0, 3.0, decay_s=0.3), SR, 55.0) is None


def test_key_ranges_halfway():
    assert S.key_ranges([28, 31, 33]) == [(0, 29), (30, 32), (33, 127)]


def test_write_sf2_reads_back_with_loops_and_layers():
    sfm = S.soundfonts_module()
    zones = [dict(name="A1", data=0.5 * np.sin(np.arange(4800) / 10), root=33, cents=-12.4, keys=(0, 40),
                  velocity=(0, 127), articulation="pizz", loop=None),
             dict(name="A1 bowed", data=0.5 * np.sin(np.arange(9600) / 10), root=33, cents=3.0, keys=(0, 127),
                  velocity=(0, 90), articulation="arco", loop=(2000, 8000))]
    presets = {"pizz": ("Plucked", 0, 32), "arco": ("Bowed", 0, 43)}
    path = Path(__import__("tempfile").mkdtemp()) / "t.sf2"
    S.write_sf2(path, "Test", presets, zones, SR, 0.25)
    smpl, p = sfm.read(path)
    assert len(smpl) == 2 * (4800 + 46 + 9600 + 46)
    assert [(h[1], h[2]) for h in p["phdr"][:-1]] == [(32, 0), (43, 0)]
    name, start, end, ls, le, rate, pitch, corr, link, typ = p["shdr"][1]
    assert (end - start, ls - start, le - start, rate, pitch, corr) == (9600, 2000, 8000, SR, 33, 3)
    assert p["shdr"][0][7] == -12
    gens = [dict(p["igen"][p["ibag"][b][0]:p["ibag"][b + 1][0]]) for b in range(len(p["ibag"]) - 1)]
    assert gens[1][S.GEN["sampleModes"]] == 1 and gens[1][S.GEN["velRange"]] == 0 | (90 << 8)
    assert S.GEN["velRange"] not in gens[0] and gens[0][S.GEN["keyRange"]] == 0 | (40 << 8)


DOBRO_WRITER = Path.home() / "play" / "dobro-transcription" / "dobro-soundfont" / "tools" / "sf2write.py"


@pytest.mark.skipif(not DOBRO_WRITER.exists(), reason="dobro-soundfont's writer is not here")
def test_one_plain_preset_is_the_dobro_writers_font():
    """The upright's 2026-10-15 font was written by dobro-soundfont's writer: one preset of unlooped zones is the
    same file from this one."""
    s2 = importlib.util.spec_from_file_location("sf2write", DOBRO_WRITER)
    w = importlib.util.module_from_spec(s2)
    s2.loader.exec_module(w)
    rng = np.random.default_rng(3)
    zones = [dict(name=f"Z{i}", data=0.3 * rng.standard_normal(1000 + i), root=30 + i, cents=c, lo=lo, hi=hi)
             for i, (c, lo, hi) in enumerate([(-2.8, 0, 29), (6.1, 30, 32), (-0.4, 33, 127)])]
    d = Path(__import__("tempfile").mkdtemp())
    w.write_sf2(d / "a.sf2", "UprightBassPrototype", "Upright bass (Cleveland)", zones, SR, bank=0, program=32)
    mine = [dict(z, keys=(z["lo"], z["hi"]), articulation="pizz", loop=None) for z in zones]
    S.write_sf2(d / "b.sf2", "UprightBassPrototype", {"pizz": ("Upright bass (Cleveland)", 0, 32)}, mine, SR, 0.25)
    assert (d / "a.sf2").read_bytes() == (d / "b.sf2").read_bytes()


def test_the_upright_map_is_complete():
    """The map in git: every entry has what the build needs, the key ranges cover every key once."""
    m = json.loads((REPO / "sounds" / "samples" / "upright.json").read_text())
    keys = []
    for e in m["samples"]:
        for k in ("root", "keys", "articulation", "source", "cut", "rate", "tuning_cents"):
            assert k in e, (e.get("name"), k)
        keys += list(range(e["keys"][0], e["keys"][1] + 1))
    assert sorted(keys) == list(range(128))
