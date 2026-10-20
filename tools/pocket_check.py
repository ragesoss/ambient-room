#!/usr/bin/env python3
"""The band's pocket, checked: the band alone on a chart, its notes placed by each pocket and played by the band
player and engine as live (no device, nothing heard), each part's stem through the transcription project's pocket
analyzer, and what it measures against what the pocket set.

    LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6 OPENBLAS_NUM_THREADS=4 \\
        python3 tools/pocket_check.py [--pockets none,pushed,even] [--bpm 100] [--out DIR] [--like] [--transcribe DIR]

On the desktop with miniconda's python (the analyzer needs librosa; FluidSynth's library under it needs the system's
C++ library preloaded). DIR: the transcription project (default ~/play/dobro-transcription).

- **The notes:** Red Wing's chart (`tunes/dobro/red-wing/chords.txt` there, once through, 32 bars) at 100 bpm from
  0.5 s, as the pocket review had it (`pipeline/tools/pocket_ab.py`, `alone-100`), the band's three parts as it plays
  them with a chart: the bass on every beat (root and fifth by turns while the chord holds, the root on a change and
  on the bar's 1), the chords strummed on every beat, the chop on every "and" (`transcribe.band.Cue`, `Play`), voiced
  by `transcribe.bandvoice.play_notes`.
- **Played** as live: every cue to the band player (`BandPlayer.cue`, with the pocket) and the band engine
  (`BandEngine` in its own thread, its 128-frame blocks, each part's stem kept), into a paced output that keeps no
  time; every cue queued before the engine starts, so none is late. The engine's log gives each note's frame as
  played (a 64-frame block's start).
- **Measured** as the review checked its renders: the analyzer (`python -m transcribe.pocket`) on the three stems
  (bass, guitar: the chords, mandolin: the chop), told the bar's 1 at a band beat well inside the render and the
  quarter's tempo; each part's median offset per class (the band's beat is the analyzer's 1 and 3, "down"; its "and"
  their 2 and 4, "back"), less the "none" render's (each sample's attack reads early or late against its note-on).
- **Expected:** the notes as played, against their own consensus (the analyzer's grid is the band's consensus, so a
  pocket that moves every part early moves the grid with it: `pocket_ab.expected_offsets`), less the "none" render's.
- `--like`: the review's own notes and render (`pocket_ab.plays`, `stems`: the guitar's boom on the beat and its strum
  on the "and", a banjo behind), the bass, the guitar and the chop placed by this pocket (`Pocket.shift_ms`, the
  guitar's boom and strum the chords' beat and "and"), the banjo as the review had it; analyzed as the review's check
  did, against the review's own measurements of its preset of the same name (its manifest).

Written to OUT (default `renders/pocket-check/`, not in git): each pocket's stems, the analyzer's output, and
`check.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from ambient import bandplayer  # noqa: E402
from ambient import pocket as pockets  # noqa: E402
from ambient.bandengine import BandEngine  # noqa: E402
from ambient.output import PacedOutput  # noqa: E402

RATE = 48000
ANALYZER = {"bass": "bass", "comp": "guitar", "chop": "mandolin"}  # the band's parts as the analyzer names them
AB_PART = {"bass": "bass", "comp": "guitar", "chop": "chop"}  # ... and as pocket_ab's notes name them
CELL = {"beat": "down", "and": "back"}
ROWS = (("bass", "beat"), ("comp", "beat"), ("comp", "and"), ("chop", "and"))


def project(root: Path):
    """The transcription project's package and the pocket review's tool, from its checkout."""
    for sub in ("pipeline/src", "pipeline/tools"):
        p = str(root / sub)
        if p not in sys.path:
            sys.path.insert(0, p)
    import pocket_ab
    from transcribe import bandvoice
    from transcribe.band import Cue, Play
    return pocket_ab, bandvoice, Cue, Play


# ----------------------------------------------------------------------------------------------- the band's own

def band_cues(beats, Cue, Play) -> list:
    """The band's plays on each beat of the chart (module docstring), as cues."""
    out, last = [], None
    for k, b in enumerate(beats):
        spb = b.nxt - b.t
        fifth = last is not None and last[0] == b.chord and b.bar_beat != 1 and last[1] == 0
        tone = 7 if fifth else 0
        last = (b.chord, tone)
        out += [Cue(k, "bass", Play(b.chord, tone=tone), b.t, b.t, b.t - 0.05, b.bar_beat),
                Cue(k, "comp", Play(b.chord), b.t, b.t, b.t - 0.05, b.bar_beat),
                Cue(k, "chop", Play(b.chord, offset=0.5), b.t + 0.5 * spb, b.t, b.t - 0.05, b.bar_beat)]
    return out


def play_band(cues, beats, pocket, bandvoice) -> tuple[dict, list]:
    """The cues through the band player and engine (module docstring): each part's stem, and every note as played
    (part, beat, class, the time its sound started, the pocket's shift)."""
    fonts = [HERE / "sounds" / f for f in bandvoice.FONTS]
    eng = BandEngine(fonts, bandplayer.voices(bandvoice), PacedOutput(RATE, 512, realtime=False), 128, RATE,
                     keep_stems=True)
    spb = beats[0].nxt - beats[0].t
    player = bandplayer.BandPlayer(eng, bandplayer.StreamClock(0.0), spb, bandvoice, pocket=pocket)
    for c in cues:
        player.cue(c)
    end = beats[-1].nxt + 2.0
    eng.start()
    while eng.running and eng.pos < end * RATE:
        time.sleep(0.02)
    eng.stop()
    if eng.error:
        raise RuntimeError(eng.error)
    late = {p: (c["late"], c["dropped"]) for p, c in eng.counts.items()}
    assert all(v == (0, 0) for v in late.values()), late
    cls = {(c.i, c.part): pockets.note_class(c.t, c.beat_t, spb) for c in cues}
    shift = {(lg.cue.i, lg.cue.part): lg.shift_ms for lg in player.log}
    notes = [{"part": AB_PART[lg.part], "band_part": lg.part, "kind": lg.part, "k": lg.tag[0],
              "j": 0 if cls[tuple(lg.tag)] == "beat" else 2, "cls": cls[tuple(lg.tag)], "t": lg.start / RATE,
              "want": lg.want / RATE, "shift_ms": shift[tuple(lg.tag)]} for lg in eng.log]
    return {p: np.concatenate(v) for p, v in eng.stems.items()}, notes


def analyze_stems(stems: dict, rate: int, bar1: float, bpm: float, out: Path, root: Path) -> dict:
    """The analyzer's command on the stems (written as `out/<part>.wav`): per analyzer part and class, the median
    offset (ms, against the band's grid), its quartiles and n."""
    out.mkdir(parents=True, exist_ok=True)
    args = []
    for part, x in stems.items():
        f = out / f"{ANALYZER.get(part, part)}.wav"
        sf.write(str(f), x.astype(np.float32), rate, subtype="FLOAT")
        args += ["--stem", f"{ANALYZER.get(part, part)}={f}"]
    names = ",".join(ANALYZER.get(p, p) for p in stems)
    env = dict(os.environ, PYTHONPATH=str(root / "pipeline" / "src"))
    cmd = [sys.executable, "-m", "transcribe.pocket", str(out / f"{ANALYZER.get(next(iter(stems)))}.wav"), *args,
           "--parts", names, "--beats-per-bar", "4", "--bar1", f"{bar1:.6f}", "--bpm", f"{2 * bpm:g}",
           "--publishable", "-o", str(out / "pocket")]
    subprocess.run(cmd, env=env, check=True, stdout=subprocess.DEVNULL)
    js = json.loads((out / "pocket" / "pocket.json").read_text())
    got = {}
    for part, info in js["parts"].items():
        sm = info.get("summary") or {}
        got[part] = {c: sm[c]["offset_ms"]["band"] for c in ("down", "back", "and")
                     if c in sm and (sm[c]["offset_ms"].get("band") or {}).get("n", 0) >= 10}
    return {"cells": got, "grid_bpm": js.get("tempo_bpm"), "bars": js.get("n_bars")}


def check_band(names, bpm, out: Path, root: Path) -> dict:
    AB, bandvoice, Cue, Play = project(root)
    beats = AB.chart_beats(AB.RED_WING / "chords.txt", None, bpm, 0.5)
    cues = band_cues(beats, Cue, Play)
    res = {}
    for name in ["none"] + [n for n in names if n != "none"]:
        pk = pockets.make(name)
        print(f"band {name}: playing {len(cues)} cues ...", flush=True)
        stems, notes = play_band(cues, beats, pk, bandvoice)
        meas = analyze_stems(stems, RATE, beats[4].t, bpm, out / "band" / name, root)
        exp = AB.expected_offsets(notes, beats)
        placed = [abs(1000 * (n["t"] - n["want"])) for n in notes]  # FluidSynth's 64-frame start against the want
        res[name] = {"measured": meas, "expected": exp, "notes": len(notes), "placed_ms_max": round(max(placed), 3),
                     "shift_ms": {f"{p}/{c}": round(float(np.median([n["shift_ms"] for n in notes
                                                                      if n["band_part"] == p and n["cls"] == c])), 2)
                                  for p, c in ROWS if any(n["band_part"] == p and n["cls"] == c for n in notes)}}
    return {"beats": len(beats), "bpm": bpm, "pockets": res, "rows": rows_of(res)}


def rows_of(res: dict) -> list:
    """Set, expected and measured per pocket, part and class, each less the "none" render's."""
    zero = res["none"]
    rows = []
    for name, r in res.items():
        if name == "none":
            continue
        for part, cls in ROWS:
            ap, c = ANALYZER[part], CELL[cls]
            m, m0 = r["measured"]["cells"].get(ap, {}).get(c), zero["measured"]["cells"].get(ap, {}).get(c)
            e, e0 = r["expected"].get(ap, {}).get(c), zero["expected"].get(ap, {}).get(c)
            if m is None or m0 is None or e is None or e0 is None:
                continue
            rows.append({"pocket": name, "part": part, "cls": cls, "set_ms": pockets.make(name).offset_ms(part, cls),
                         "expected_ms": round(e - e0, 1), "measured_ms": round(m["median"] - m0["median"], 1),
                         "error_ms": round((m["median"] - m0["median"]) - (e - e0), 1),
                         "iqr_ms": round(m["q75"] - m["q25"], 1), "n": m["n"]})
    return rows


# ------------------------------------------------------------------------------------- like the review's render

def timed_like(AB, notes, beats, pk: pockets.Pocket, ab_preset) -> list:
    """The review's notes timed by this pocket: the bass, the guitar (its boom the chords' beat, its strum on the
    "and" the chords' "and") and the chop by `pk.shift_ms` (a play's notes together); the banjo as the review's
    preset of the same name places it (`pocket_ab.timed`)."""
    banjo = [n for n in AB.timed(notes, beats, ab_preset) if n["part"] == "banjo"]
    out = []
    for n in notes:
        if n["part"] == "banjo":
            continue
        part = {"bass": "bass", "guitar": "comp", "chop": "chop"}[n["part"]]
        cls = "beat" if n["j"] < 2 else "and"
        ms = pk.shift_ms(part, cls, n["k"])
        out.append(dict(n, t=n["nominal"] + ms / 1000.0, shift_ms=ms))
    return out + banjo


def check_like(names, out: Path, root: Path) -> dict:
    AB, *_ = project(root)
    from pocket_bench import class_offsets
    from transcribe import pocket as P
    beats, _ = AB.context_beats("alone-100")
    notes = AB.plays(beats)
    man = json.loads((AB.OUT / "manifest.json").read_text())
    ab_rows = {(r["preset"], r["part"], r["cls"]): r for r in man["check"]["alone-100"]["rows"] if "measured_ms" in r}
    res = {}
    ids = {"none": "as-it-is", "pushed": "pushed", "even": "even"}
    for name in ["none"] + [n for n in names if n != "none"]:
        ab_p = AB.BY_ID[ids[name]]
        timed = timed_like(AB, notes, beats, pockets.make(name), ab_p)
        print(f"like {name}: rendering ...", flush=True)
        st = AB.stems(timed, rate=P.SR)
        sig = P.from_stems({AB.ANALYZER[k]: v.astype(np.float32) for k, v in st.items()})
        pk = P.analyze(sig, f"like-{name}", "stems", beats_per_bar=4, bar1_s=beats[4].t, bpm_hint=200.0)
        P.write(pk, out / "like" / name, publishable=True)
        got = class_offsets(pk)
        res[name] = {"measured": {part: {c: v for c, v in cells.items() if not c.startswith("_")}
                                  for part, cells in got.items()},
                     "expected": AB.expected_offsets(timed, beats)}
    rows = []
    zero = res["none"]
    for name, r in res.items():
        if name == "none":
            continue
        for part, cls in (("bass", "beat"), ("guitar", "beat"), ("guitar", "and"), ("chop", "and"),
                          ("banjo", "beat"), ("banjo", "and")):
            ap, c = AB.ANALYZER[part], AB.CLASS[cls]
            m, m0 = r["measured"].get(ap, {}).get(c), zero["measured"].get(ap, {}).get(c)
            e, e0 = r["expected"].get(ap, {}).get(c), zero["expected"].get(ap, {}).get(c)
            ab = ab_rows.get((ids[name], part, cls))
            if None in (m, m0, e, e0):
                continue
            band_part = {"bass": "bass", "guitar": "comp", "chop": "chop"}.get(part)
            rows.append({"pocket": name, "part": part, "cls": cls,
                         "set_ms": pockets.make(name).offset_ms(band_part, cls) if band_part else None,
                         "expected_ms": round(e - e0, 1), "measured_ms": round(m - m0, 1),
                         "review_expected_ms": ab and ab["expected_ms"], "review_measured_ms": ab and ab["measured_ms"],
                         "against_review_ms": None if ab is None else round((m - m0) - ab["measured_ms"], 1)})
    return {"pockets": res, "rows": rows}


# ----------------------------------------------------------------------------------------------------------- main

def print_rows(title: str, rows: list, like: bool = False) -> None:
    print(f"\n{title}")
    head = f"{'pocket':8s} {'part':7s} {'class':6s} {'set':>6s} {'expect':>7s} {'measured':>9s}"
    head += f" {'review':>7s} {'vs rev':>7s}" if like else f" {'error':>6s} {'IQR':>5s} {'n':>4s}"
    print(head)
    for r in rows:
        s = "" if r["set_ms"] is None else f"{r['set_ms']:+6.1f}"
        line = (f"{r['pocket']:8s} {r['part']:7s} {r['cls']:6s} {s:>6s} {r['expected_ms']:+7.1f} "
                f"{r['measured_ms']:+9.1f}")
        if like:
            rv, d = r["review_measured_ms"], r["against_review_ms"]
            line += f" {'' if rv is None else f'{rv:+.1f}':>7s} {'' if d is None else f'{d:+.1f}':>7s}"
        else:
            line += f" {r['error_ms']:+6.1f} {r['iqr_ms']:5.1f} {r['n']:4d}"
        print(line)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pockets", default="none,pushed,even")
    ap.add_argument("--bpm", type=float, default=100.0)
    ap.add_argument("--out", type=Path, default=HERE / "renders" / "pocket-check")
    ap.add_argument("--like", action="store_true", help="also the review's own notes, placed by this pocket")
    ap.add_argument("--transcribe", type=Path, default=Path("~/play/dobro-transcription"))
    a = ap.parse_args()
    root = a.transcribe.expanduser()
    names = [n.strip() for n in a.pockets.split(",") if n.strip()]
    report = {"band": check_band(names, a.bpm, a.out, root)}
    print_rows(f"The band's own notes, Red Wing's chart at {a.bpm:g} bpm (ms, + late; less the \"none\" render's):",
               report["band"]["rows"])
    print("the pocket's median shift per part and class:",
          {k: v["shift_ms"] for k, v in report["band"]["pockets"].items()})
    print("each note's start against its want (FluidSynth's 64-frame block), at most:",
          {k: v["placed_ms_max"] for k, v in report["band"]["pockets"].items()}, "ms")
    if a.like:
        report["like"] = check_like(names, a.out, root)
        print_rows("The review's own notes, placed by this pocket, against the review's own measurements (ms):",
                   report["like"]["rows"], like=True)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "check.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    print(f"\n{a.out / 'check.json'}")


if __name__ == "__main__":
    main()
