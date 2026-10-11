"""Step 1 test: play the test sound, live or into a file.

Live, to a sound device, until stopped:
    python3 spike.py --device plughw:CARD=spker,DEV=0 [--ctl /tmp/ambient.ctl]
  Each line written to the control file changes a control, e.g.
  "bright 0.8", or "stop" for a 10 s fade and exit.

Into a file, as fast as the CPU allows (to measure level and CPU cost):
    python3 spike.py --render out.wav --seconds 60
"""

import argparse
import os
import random
import threading
import time
from pathlib import Path

import ctcsound

HERE = Path(__file__).parent

CONTROLS = {"volume": 0.5, "bright": 0.4, "motion": 0.3, "space": 0.6, "wind": 0.3}

# One mood for the test: D major, chords voiced as MIDI notes, with a bass root.
CHORDS = [
    ([57, 61, 64, 66, 69], 38),  # Dmaj9
    ([57, 62, 64, 66, 71], 47),  # Bm11
    ([55, 59, 61, 66, 69], 43),  # Gmaj7(#11)
    ([57, 59, 64, 66, 69], 45),  # A6sus2
]
SCALE = [62, 64, 66, 69, 71]  # D major pentatonic
BELL_EVERY_S = 6.0


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def events(seconds: float, rng: random.Random):
    """(time s, instr, pfields after p3) for `seconds` of music."""
    out = []
    t, last = 0.0, None
    while t < seconds:
        i = rng.choice([c for c in range(len(CHORDS)) if c != last])
        last = i
        notes, bass = CHORDS[i]
        hold = rng.uniform(14, 22)
        dur = hold + 10
        for n in notes:
            out.append((t + rng.uniform(0, 2), 10, dur, hz(n), rng.uniform(0.09, 0.13), 6, 9))
        out.append((t, 15, dur, hz(bass), 0.25, 8, 9))
        t += hold
    t, note = rng.expovariate(1 / BELL_EVERY_S), rng.choice(SCALE) + 12
    while t < seconds:
        steps = [s + 12 for s in SCALE] + [s + 24 for s in SCALE[:3]]
        k = steps.index(note) if note in steps else 0
        note = steps[max(0, min(len(steps) - 1, k + rng.choice([-2, -1, 1, 2])))]
        out.append((t, 20, rng.uniform(4, 7), hz(note), rng.uniform(0.05, 0.1)))
        t += rng.expovariate(1 / BELL_EVERY_S)
    return sorted(out, key=lambda e: e[0])


def make_csound(options: list[str]) -> ctcsound.Csound:
    cs = ctcsound.Csound()
    for o in options:
        cs.setOption(o)
    if cs.compileOrc((HERE / "ambient.orc").read_text()) != 0:
        raise SystemExit("the orchestra did not compile")
    return cs


def set_controls(cs, values: dict, fade: float, gain_db: float):
    for k, v in values.items():
        cs.setControlChannel(k, v)
    cs.setControlChannel("fade", fade)
    cs.setControlChannel("gain_db", gain_db)


def render(path: str, seconds: float, gain_db: float, seed: int):
    cs = make_csound(["-d", "-m0", f"-o{path}", "-W", "-f"])
    score = [f"f 0 {seconds}"]
    for t, instr, dur, *p in events(seconds, random.Random(seed)):
        score.append(f"i {instr} {t:.3f} {dur:.3f} " + " ".join(f"{x:.4f}" for x in p))
    cs.readScore("\n".join(score) + "\n")
    cs.start()
    set_controls(cs, CONTROLS, 1.0, gain_db)
    t0, c0 = time.monotonic(), time.process_time()
    while cs.performKsmps() == 0:
        pass
    wall, cpu = time.monotonic() - t0, time.process_time() - c0
    cs.cleanup()
    print(f"rendered {seconds:g} s in {wall:.1f} s wall, {cpu:.1f} s CPU: "
          f"{100 * cpu / seconds:.0f}% of one core in real time")


def live(device: str, ctl: str | None, gain_db: float, buffer_frames: int, seed: int):
    cs = make_csound(["-d", "-m4", "-+rtaudio=alsa", f"-odac:{device}",
                      f"-b{buffer_frames // 4}", f"-B{buffer_frames}"])
    cs.readScore("f 0 z\n")
    cs.start()
    set_controls(cs, CONTROLS, 0.0, gain_db)
    pt = ctcsound.CsoundPerformanceThread(cs.csound())
    pt.play()
    time.sleep(0.5)  # let the controls start at zero, so the fade-in glides
    cs.setControlChannel("fade", 1.0)
    stop = threading.Event()

    def conductor():
        rng = random.Random(seed)
        start = time.monotonic()
        while not stop.is_set():
            for t, instr, dur, *p in events(600, rng):
                wait = start + t - time.monotonic()
                if stop.wait(max(0.0, wait)):
                    return
                pt.scoreEvent(False, "i", [instr, 0, dur, *p])
            start += 600

    threading.Thread(target=conductor, daemon=True).start()
    print(f"playing to {device}; controls: {CONTROLS}", flush=True)
    try:
        if ctl:
            if not os.path.exists(ctl):
                os.mkfifo(ctl)
            while True:
                with open(ctl) as f:
                    for line in f:
                        words = line.split()
                        if words == ["stop"]:
                            raise KeyboardInterrupt
                        if len(words) == 2 and words[0] in CONTROLS:
                            v = max(0.0, min(1.0, float(words[1])))
                            cs.setControlChannel(words[0], v)
                            print(f"{time.strftime('%H:%M:%S')} {words[0]} -> {v}", flush=True)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    print("fading out", flush=True)
    cs.setControlChannel("fade", 0.0)
    time.sleep(12)
    stop.set()
    pt.stop()
    pt.join()
    cs.cleanup()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", help="ALSA playback device")
    ap.add_argument("--ctl", help="control file (a named pipe is made if missing)")
    ap.add_argument("--render", metavar="WAV")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--gain-db", type=float, default=0.0, help="output gain, from the level calibration")
    ap.add_argument("--buffer-frames", type=int, default=8192, help="ALSA buffer, frames")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if a.render:
        render(a.render, a.seconds, a.gain_db, a.seed)
    elif a.device:
        live(a.device, a.ctl, a.gain_db, a.buffer_frames, a.seed)
    else:
        ap.error("give --device or --render")


if __name__ == "__main__":
    main()
