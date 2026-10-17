#!/usr/bin/env python3
"""The Ugly Duckling String Band run without its page, for a while, then stopped: its status as it goes and what
it measured. With the desktop's config (`config/ud-desktop.toml`: no device, a recorded take as the input) the
whole loop runs and nothing is heard.

    tools/ud_run.py [--config config/ud-desktop.toml] [--tune red-wing] [--bpm N] [--seconds 30] [--count band|voice]
        [--input ID] [--instrument dobro] [--json OUT]

Each second: the state, the beat and chord, the parts; at the end: the clock (L estimated and measured), every
cue's margin when it reached the engine (min, median), late and dropped notes, underruns, the listening's and the
engine's CPU (ms a second), and, against the tune's chart, how often each part played the chart's chord.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from ugly_duckling.config import load_config  # noqa: E402
from ugly_duckling.server import Band  # noqa: E402
from ugly_duckling.session import RATE  # noqa: E402
from ugly_duckling.tunes import chord_name  # noqa: E402


def grade(sess) -> dict:
    """Each part's plays against the chart beat the band says it is on (its count from the first beat after the
    count-in): the share with the chart's root."""
    band = sess.band if not hasattr(sess.band, "bands") else sess.band.band
    chart = sess.tune.chart
    out = {}
    if band is None:
        return out
    for part in ("bass", "comp", "chop"):
        n = right = 0
        for lg in band.logs:
            p = lg.plays.get(part)
            if p is None:
                continue
            want = chart[lg.i % len(chart)]
            n += 1
            right += p.chord[0] == want[0]
        out[part] = {"plays": n, "root_right": round(right / n, 3) if n else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config" / "ud-desktop.toml"))
    ap.add_argument("--tune", default="red-wing")
    ap.add_argument("--bpm", type=float, default=None)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--count", default="band")
    ap.add_argument("--input", default=None)
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--volume", type=float, default=0.0)
    ap.add_argument("--json", default=None)
    ap.add_argument("--logs", type=int, default=0, help="print the band's first N beats' logs")
    a = ap.parse_args()
    cfg = load_config(Path(a.config))
    band = Band(cfg)
    body = {"tune": a.tune, "bpm": a.bpm, "count": a.count, "input": a.input, "instrument": a.instrument,
            "volume_db": a.volume, "listen_stop": False}
    band.start(body)
    sess = band.session
    t0 = time.monotonic()
    while time.monotonic() - t0 < a.seconds and sess.running:
        time.sleep(1.0)
        s = sess.status()
        b = s["beat"] or {}
        parts = " ".join(f"{k}:{'on' if v['playing'] else '-'}" for k, v in s["parts"].items())
        print(f"{s['seconds']:6.1f} s  {s['state']:24s} beat {b.get('bar_beat')} chord {b.get('chord')!s:4s} "
              f"{parts}  input {s['input_db']} dBFS", flush=True)
    timing = sess.timing()
    band.stop()
    report = {"tune": a.tune, "status": sess.status()["state"], "error": sess.error, "message": sess.message,
              "L_estimate_frames": sess.L_est_ref, "L_frames": sess.L, "L_measured": sess.L_measured,
              "count_in": [round(t, 4) for t in sess.count_in], "timing": timing, "final": sess.final,
              "grade": grade(sess)}
    print(json.dumps(report, indent=1, default=str))
    lb = sess.band if not hasattr(sess.band, "bands") else sess.band.band
    for lg in (lb.logs[: a.logs] if lb is not None else []):
        print(lg.i, round(lg.t, 3), lg.bar, round(lg.beat_conf, 2), chord_name(lg.predicted), round(lg.pred_conf, 2),
              {k: chord_name(v.chord) for k, v in lg.plays.items()}, chord_name(sess.tune.chart[lg.i % len(sess.tune.chart)]))
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
