#!/usr/bin/env python3
"""The band's timing in a recorded session (`ugly_duckling/record.py`; `tools/pull-ud-session`), from the device's own
return of what it played (the loopback, `capture.flac` channel 1), against its count-in's grid:

- each click, where the engine put it (its log) and where the loopback has it: the round trip `L`;
- the band's first notes against beat 1 (the beat after the count-in), from the loopback;
- the band's beats against the count's grid as the session went (the bass's notes as the engine started them,
  the beats the band was given), and its tempo: does the band hold the count's time, follow the player, or drift.

    tools/ud_session_timing.py SESSION_DIR [--every 4]

Frames: the engine's (playback) frame m is heard in the capture at m + L (the log's `clock`/`end`); stream time t is
capture frame t x 48000.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

RATE = 48000


def onset(x: np.ndarray, a: int, b: int, rel: float = 0.25) -> int | None:
    """The first frame in [a, b) where |x| reaches `rel` of its peak there (None: silence)."""
    a, b = max(0, a), min(len(x), b)
    seg = np.abs(x[a:b])
    if not len(seg) or seg.max() < 1e-5:
        return None
    return a + int(np.argmax(seg >= rel * seg.max()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("--every", type=int, default=4)
    a = ap.parse_args()
    import soundfile as sf
    d = Path(a.session)
    ev = [json.loads(line) for line in open(d / "session.jsonl")]
    first = lambda k: next((e for e in ev if e["ev"] == k), None)  # noqa: E731
    start, clock, end = first("start"), first("clock"), first("end")
    if start is None or end is None:
        raise SystemExit("no start or end in the log (a session cut short?)")
    bpm = start["settings"]["bpm"]
    spb = 60.0 / bpm
    clicks = end.get("clicks") or []
    L, conv = end.get("L"), end.get("conv", 0)
    print(f"{start['tune']['name']} at {bpm:g} bpm, input {start['input']['name'] if start['input'] else '-'}, "
          f"count-in {start['count_in']['text'] if start.get('count_in') else '-'}")
    if not clicks or L is None:
        print("no count-in clicks (a voice count-in?)")
        return
    if clock:
        print(f"L: estimated {clock['L_estimate']:.1f} frames, measured {clock['L_measured']}, used {L:.1f} "
              f"({1000 * L / RATE:.2f} ms); converters assumed {1000 * conv / RATE:.2f} ms")
    y, sr = sf.read(str(d / "capture.flac"), always_2d=True)
    loop = y[:, 1]
    print("\nclicks in the loopback (frames after where the engine put them, + L):")
    offs = []
    for k, f in enumerate(clicks):
        o = onset(loop, int(f + L) - 480, int(f + L) + 960, 0.5)
        offs.append(None if o is None else o - (f + L))
    print("  " + ", ".join("-" if x is None else f"{x:+.0f}" for x in offs))
    n = len(clicks)
    one = clicks[0] + n * spb * RATE  # beat 1, engine frames
    notes = [x for x in end.get("notes", []) if x.get("start") is not None]
    print("\nbeat 1 (the beat after the count-in):")
    for part, off in (("bass", 0.0), ("comp", 0.0), ("chop", 0.5)):
        mine = [x for x in notes if x["part"] == part]
        if not mine:
            print(f"  {part:5s} never played")
            continue
        fst = min(mine, key=lambda x: x["start"])
        place = one + off * spb * RATE
        print(f"  {part:5s} first note: beat {(fst['start'] - one) / (spb * RATE):+.2f} of the tune, "
              f"{1000 * (fst['start'] - place) / RATE:+.2f} ms from its place (engine)")
    o = onset(loop, int(clicks[-1] + L + 0.1 * spb * RATE), int(one + L + 1.5 * spb * RATE), 0.1)
    if o is not None:
        print(f"  the band's first sound in the loopback: {1000 * (o - (one + L)) / RATE:+.2f} ms from beat 1")
    beats = [e for e in ev if e["ev"] == "beat"]
    one_t = (one + L + conv) / RATE
    print(f"\nthe band's beats against the count's grid (stream time; beat 1 at {one_t:.3f} s):")
    print("  beat   ms off   bpm   confidence")
    for b in beats:
        if b["i"] % a.every == 0 or b is beats[-1]:
            print(f"  {b['i']:4d} {1000 * (b['t'] - (one_t + b['i'] * spb)):+8.1f} {b['bpm']:6.1f} {b['confidence']:6.2f}")
    rooms = [e for e in ev if e["ev"] == "room"]
    if rooms:
        ok = [r["delay_ms"] for r in rooms if r["reliable"]]
        print(f"\nroom delay (the echo path learnt on the {rooms[-1].get('mic', 'input')} mic): "
              + (f"{np.median(ok):.2f} ms (median of {len(ok)} reliable of {len(rooms)})" if ok else "never reliable"))
    stop = first("stop")
    if stop:
        print(f"stopped: {stop['reason']}")


if __name__ == "__main__":
    main()
