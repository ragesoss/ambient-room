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


def first_notes(sess) -> dict:
    """Each part's first note against where it belongs: the bass and the chords on beat 1 of bar 1 (the beat after
    the count-in), the chop on its "and", in engine frames (the count-in's clicks are on the same clock). ms late
    (+) or early (-), from the frame FluidSynth started the note."""
    log = list(getattr(sess.engine, "log", None) or [])
    if not sess.clicks or not log:
        return {}
    spb = 60.0 / sess.s.bpm
    n = len(sess.clicks)
    one = sess.clicks[0] + n * spb * RATE
    out = {}
    for part, off in (("bass", 0.0), ("comp", 0.0), ("chop", 0.5)):
        starts = [lg for lg in log if lg.part == part and lg.start is not None]
        if not starts:
            out[part] = None
            continue
        lg = min(starts, key=lambda g: g.start)
        beat = (lg.start - sess.clicks[0]) / (spb * RATE) - n
        out[part] = {"beat_of_tune": round(beat, 3), "cue_beat": lg.tag[0] if lg.tag else None,
                     "ms_from_its_place": round(1000 * (lg.start - (one + off * spb * RATE)) / RATE, 2)}
    return out


def drift(sess, every: int = 4) -> list:
    """The band's beats against the count-in's grid (the clicks' tempo, on from the beat after them): (beat, ms after
    its grid time, bpm, confidence), every `every` beats, and the last."""
    band = sess.band if not hasattr(sess.band, "bands") else sess.band.band
    if band is None or not sess.count_in:
        return []
    spb = 60.0 / sess.s.bpm
    one = sess.count_in[-1] + spb
    bs = band.beats
    return [(i, round(1000 * (b.t - (one + i * spb)), 1), round(b.bpm, 1), round(b.confidence, 2))
            for i, b in enumerate(bs) if i % every == 0 or i == len(bs) - 1]


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
    ap.add_argument("--take", default=None, help="the tune's take to give as the capture (no device), e.g. take-01.flac")
    ap.add_argument("--room-ir", default=None, help="no device: the band heard through this room response (.npy/.wav)")
    ap.add_argument("--room-gain-db", type=float, default=0.0)
    ap.add_argument("--take-gain", type=float, default=1.0, help="no device: the take's level (0: the player silent)")
    ap.add_argument("--take-seconds", type=float, default=0.0, help="no device: the take cut this long after its bar 1")
    ap.add_argument("--take-path", default=None, help="no device: any recording as the capture, its bar 1 at --bar1 s")
    ap.add_argument("--bar1", type=float, default=0.0)
    ap.add_argument("--no-echo", action="store_true", help="leave the band's own sound in the input")
    ap.add_argument("--count-bars", default="auto", help="the band's count-in: auto, 1 or 2 bars")
    ap.add_argument("--json", default=None)
    ap.add_argument("--logs", type=int, default=0, help="print the band's first N beats' logs")
    a = ap.parse_args()
    cfg = load_config(Path(a.config))
    if a.take:
        cfg.device.file_tune, cfg.device.file_take = a.tune, a.take
    if a.take_path:
        cfg.device.file_path, cfg.device.file_bar1_s = a.take_path, a.bar1
    if a.room_ir:
        cfg.device.file_room_ir, cfg.device.file_room_gain_db = a.room_ir, a.room_gain_db
    cfg.device.file_take_gain, cfg.device.file_take_seconds = a.take_gain, a.take_seconds
    if a.no_echo:
        cfg.echo = False
    band = Band(cfg)
    body = {"tune": a.tune, "bpm": a.bpm, "count": a.count, "input": a.input, "instrument": a.instrument,
            "volume_db": a.volume, "listen_stop": False,
            "count_bars": a.count_bars}
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
    ended = sess.ended - sess.started if sess.ended else None
    report = {"tune": a.tune, "status": sess.status()["state"], "error": sess.error, "message": sess.message,
              "stop_reason": sess._stop_reason, "stream_s": round(sess.read / RATE, 2), "ran_s": ended,
              "recording": str(sess.rec.path) if sess.rec and sess.rec.on else None,
              "L_estimate_frames": sess.L_est_ref, "L_frames": sess.L, "L_measured": sess.L_measured,
              "count_in": [round(t, 4) for t in sess.count_in], "timing": timing, "final": sess.final,
              "grade": grade(sess), "first_notes": first_notes(sess), "drift": drift(sess)}
    print(json.dumps(report, indent=1, default=str))
    lb = sess.band if not hasattr(sess.band, "bands") else sess.band.band
    for lg in (lb.logs[: a.logs] if lb is not None else []):
        print(lg.i, round(lg.t, 3), lg.bar, round(lg.beat_conf, 2), chord_name(lg.predicted), round(lg.pred_conf, 2),
              {k: chord_name(v.chord) for k, v in lg.plays.items()}, chord_name(sess.tune.chart[lg.i % len(sess.tune.chart)]))
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
