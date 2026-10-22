"""Breaks on a tune's melody, rendered for the ear (2026-10-22): the Tune line (ambient/breaks.py) at points along
its pull, each one pass of the tune over the same band, to files. Nothing is played: Csound renders to files.

    .venv/bin/python tools/tune_breaks.py [--out DIR] [--tunes "Red Wing,Down Yonder,Big Sciota"]
        [--pulls 1,0.75,0.25,0] [--middle 0.5] [--seeds 1,2,3] [--lufs -20]

For each tune, its mood (presets.WHOLE: its chart, the band, its tempo) with the Tune line on the voice in VOICES
(the mood's dobro; the fiddle for Down Yonder). Each version is the conductor run with the band's dice and the
melody's apart (`Conductor(melody_rng=...)`, the break's own seed): the band's notes are the same in every version
of a tune (checked, note for note), so the band is rendered once and each break's melody alone, then the two mixed.
The clip: one bar of the tune before the pass (the band, and the pickup into bar 1), the pass, and the first note of
the next pass with two beats of the band, faded over its last second; every clip brought to the same loudness
(`--lufs`, integrated, ffmpeg's ebur128; a gain alone). The versions: the pulls at one seed, and the middle pull at
each seed. Written: `<tune>-<version>.flac` (48 kHz, 24-bit, stereo) and `breaks.json` (each clip's version, timing,
loudness and gain, and how much of the tune its break keeps: `breaks.measure`) in DIR, by default the transcription
project's review cache for `2026-10-22-tune-breaks` (outside both repos).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from ambient import breaks, samples  # noqa: E402
from ambient.conductor import Conductor, bpm  # noqa: E402
from ambient.engine import init_csound, orchestra  # noqa: E402
from ambient.presets import TUNE_MELODIES  # noqa: E402
from ambient.render import RATE, _Clock, read_float_wav  # noqa: E402
from ambient.sounds import instr  # noqa: E402
from ambient.state import MOODS  # noqa: E402

OUT = Path.home() / ".cache" / "challenge-reviews" / "2026-10-22-tune-breaks"
VOICES = {"Red Wing": "Dobro", "Down Yonder": "Fiddle", "Big Sciota": "Dobro"}
BAND_SEED, MELODY_SEED = 1, 100  # the band's dice, and the free line's (the melodist's), the same in every version
TAIL_BEATS, FADE_S = 2.0, 1.0


def state_for(mood: str, voice: str, pull: float) -> dict:
    s = copy.deepcopy(MOODS[mood])
    s["melody"]["style"] = "Tune"
    s["melody"]["pull"] = pull
    s["layers"]["melody"]["voice"] = voice
    s["evolve"]["rate"] = 0.0
    return s


def melody_instruments(state: dict) -> set[int]:
    """The instrument numbers the melody's notes play on (a held string's are its fraction of one)."""
    v = state["layers"]["melody"]["voice"]
    out = {int(instr("melody", v))}
    s = samples.strung("melody", v)
    if s:
        out.add(int(s[0]))
    return out


def run(mood: str, voice: str, pull: float, seed: int) -> dict:
    """One version: the conductor over the lead-in pass, the pass, the tail; its notes split into the band's and the
    melody's, the clip's times, and the pass's line as the break played it."""
    state = state_for(mood, voice, pull)
    clock = _Clock()
    c = Conductor(clock, random.Random(BAND_SEED), melody_rng=random.Random(MELODY_SEED))
    c.break_seed = seed
    c.apply(state)
    br = c.breaker
    if br is None:
        raise SystemExit(f"{mood}: no tune melody (is the transcription project here?)")
    br.first_pass = 1  # the pass heard is the break's first
    src = TUNE_MELODIES[mood]
    k, tune = src["k"], br.tune
    chart_bars = tune.bars // k
    step_s = 60 / bpm(state["shape"]["tempo"]) / 4
    tune_beat = 4 * step_s / k  # a beat of the tune, in seconds
    pass_steps = chart_bars * 16
    start_step = pass_steps  # pass 1
    lead = tune.into_top()
    c.melody_from = start_step + ((lead[0].t - tune.beats) * 4 / k if lead else 0)
    c.melody_until = 2 * pass_steps + 0.5  # and the next pass's first note
    t0 = 0.1 + start_step * step_s  # the conductor's first step is at 0.1 s
    clip = (t0 - 4 * tune_beat, t0 + tune.beats * tune_beat + TAIL_BEATS * tune_beat)
    while clock.t < clip[1] + 1.5:
        c.tick()
        clock.t += 0.2
    c.silence_texture()
    mel = melody_instruments(state)
    notes = sorted(clock.notes, key=lambda n: (n[0], n[1]))
    band = [n for n in notes if int(abs(n[1])) not in mel]
    melody = [n for n in notes if int(abs(n[1])) in mel]
    line = [n for p, n in br.heard if p == 1]
    return {"band": band, "melody": melody, "channels": dict(clock.channels), "clip": clip, "t0": t0,
            "played": played(line, melody, t0, tune_beat, br.shift),
            "tune_beat": tune_beat, "tune": tune, "line": line, "k": k,
            "measure": breaks.measure(line, tune), "pull": pull, "seed": seed}


def played(line: list, melody: list[tuple], t0: float, beat: float, shift: int) -> list[int]:
    """How many of the pass's notes the engine was given ([found, planned]): a note (picked, or tied to slide) at
    its pitch (within 30 cents: the tuning is just) starting at its time, or up to 0.45 s before it (a slide's
    start), or 25 ms after (the swing)."""
    found = 0
    for n in line:
        at, want = t0 + n.t * beat, n.midi + shift
        for e in melody:
            if e[1] > 0 and at - 0.45 <= e[0] <= at + 0.025 and len(e) > 3 and e[3] > 0:
                if abs(12 * np.log2(e[3] / 440) + 69 - want) < 0.3:
                    found += 1
                    break
    return [found, len(line)]


def digest(notes: list[tuple]) -> str:
    return hashlib.sha1(repr([tuple(round(x, 6) if isinstance(x, float) else x for x in n) for n in notes])
                        .encode()).hexdigest()[:12]


def render(notes: list[tuple], channels: dict, seconds: float, path: Path) -> np.ndarray:
    """The notes through the orchestra, to a float WAV (Csound offline, as ambient/render.py): its samples."""
    import ctcsound
    orc = orchestra(REPO / "sounds")
    score = [f"i {i:g} {at:.4f} {dur:.4f} " + " ".join(f"{x:.6g}" for x in p) for at, i, dur, *p in notes]
    init_csound(ctcsound)
    cs = ctcsound.Csound()
    for o in ("-d", "-m0", f"-o{path}", "-W", "-f"):
        cs.setOption(o)
    if cs.compileOrc(orc) != 0:
        raise RuntimeError("the orchestra did not compile")
    cs.readScore("\n".join(score + [f"f 0 {seconds + 0.1:.3f}"]) + "\n")  # running to the end, held notes or not
    cs.start()
    for k, v in channels.items():
        cs.setControlChannel(k, v)
    cs.setControlChannel("fade", 1.0)
    cs.setControlChannel("gain_db", 0.0)
    while cs.performKsmps() == 0:
        if cs.scoreTime() > seconds:
            break
    cs.cleanup()
    del cs
    x = read_float_wav(path)[: int(seconds * RATE)]
    return np.pad(x, ((0, int(seconds * RATE) - len(x)), (0, 0)))


def write_wav(path: Path, x: np.ndarray) -> None:
    data = x.astype("<f4").tobytes()
    head = (b"RIFF" + (36 + len(data)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
            + (3).to_bytes(2, "little") + (2).to_bytes(2, "little") + RATE.to_bytes(4, "little")
            + (RATE * 8).to_bytes(4, "little") + (8).to_bytes(2, "little") + (32).to_bytes(2, "little")
            + b"data" + len(data).to_bytes(4, "little"))
    path.write_bytes(head + data)


def lufs(path: Path) -> float:
    """Integrated loudness (ffmpeg's ebur128), LUFS."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=framelog=quiet",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1])


def clip_of(band: np.ndarray, melody: np.ndarray, clip: tuple[float, float]) -> np.ndarray:
    a, b = (int(round(t * RATE)) for t in clip)
    x = band[a:b] + melody[a:b]
    n = len(x)
    fade_in, fade_out = int(0.03 * RATE), int(FADE_S * RATE)
    env = np.ones(n)
    env[:fade_in] = np.linspace(0, 1, fade_in)
    env[n - fade_out:] = np.linspace(1, 0, fade_out) ** 2
    return x * env[:, None]


def versions(pulls: list[float], middle: float, seeds: list[int]) -> list[tuple[str, float, int]]:
    out = [(f"p{round(100 * p):03d}-s{seeds[0]}", p, seeds[0]) for p in pulls]
    out += [(f"p{round(100 * middle):03d}-s{s}", middle, s) for s in seeds]
    return sorted(set(out), key=lambda v: (-v[1], v[2]))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--tunes", default="Red Wing,Down Yonder,Big Sciota")
    ap.add_argument("--pulls", default="1,0.75,0.25,0")
    ap.add_argument("--middle", type=float, default=0.5)
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--lufs", type=float, default=-20.0)
    ap.add_argument("--keep", action="store_true", help="keep the stems (tmp/: the band, each melody) to check")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    samples.orchestra(REPO / "sounds")  # first: which voices are sampled (their instrument numbers)
    pulls = [float(x) for x in a.pulls.split(",")]
    seeds = [int(x) for x in a.seeds.split(",")]
    manifest = {"made": time.strftime("%Y-%m-%d %H:%M"), "lufs": a.lufs, "band_seed": BAND_SEED,
                "melody_seed": MELODY_SEED, "params": breaks.PARAMS.__dict__, "tunes": []}
    for mood in [x.strip() for x in a.tunes.split(",")]:
        voice = VOICES[mood]
        runs = {vid: run(mood, voice, pull, seed) for vid, pull, seed in versions(pulls, a.middle, seeds)}
        bands = {vid: digest(r["band"]) for vid, r in runs.items()}
        if len(set(bands.values())) != 1:
            raise SystemExit(f"{mood}: the band differs between versions: {bands}")
        first = next(iter(runs.values()))
        clip, end = first["clip"], first["clip"][1] + 0.5
        slug = TUNE_MELODIES[mood]["folder"]
        tmp = a.out / "tmp"
        tmp.mkdir(exist_ok=True)
        band = render(first["band"], first["channels"], end, tmp / f"{slug}-band.wav")
        tune_rec = {"mood": mood, "tune": slug, "voice": voice, "k": first["k"],
                    "band_digest": bands[next(iter(bands))],
                    "tune_bpm": round(60 / first["tune_beat"], 2), "bars": first["tune"].bars,
                    "clip_s": round(clip[1] - clip[0], 3), "clip_from_s": round(clip[0], 3),
                    "pass_starts_s": round(first["t0"] - clip[0], 3),
                    "pass_ends_s": round(first["t0"] - clip[0] + first["tune"].beats * first["tune_beat"], 3),
                    "versions": []}
        for vid, r in runs.items():
            mel = render(r["melody"], r["channels"], end, tmp / f"{slug}-{vid}-melody.wav")
            x = clip_of(band, mel, clip)
            raw = tmp / f"{slug}-{vid}.wav"
            write_wav(raw, x)
            before = lufs(raw)
            gain = a.lufs - before
            top = 20 * np.log10(np.max(np.abs(x)) + 1e-12)
            if top + gain > -1.0:  # its peak kept under -1 dBFS: a little under the loudness, then (said)
                gain = -1.0 - top
            write_wav(raw, x * 10 ** (gain / 20))
            out = a.out / f"{slug}-{vid}.flac"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-c:a", "flac",
                            "-sample_fmt", "s32", "-bits_per_raw_sample", "24", str(out)], check=True)
            after = lufs(out)
            m = r["measure"]
            tune_rec["versions"].append({
                "id": vid, "pull": r["pull"], "seed": r["seed"], "file": str(out), "seconds": round(len(x) / RATE, 3),
                "lufs_before": round(before, 2), "gain_db": round(gain, 2), "lufs": round(after, 2),
                "peak_dbfs": round(float(top + gain), 2), "engine_notes": r["played"],
                "measure": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()},
                "line": [[round(n.t, 4), round(n.dur, 4), n.midi, n.how, n.by] for n in r["line"]]})
            print(f"{mood} {vid}: {len(x) / RATE:.1f} s, {before:.1f} -> {after:.1f} LUFS, the engine's notes "
                  f"{r['played'][0]}/{r['played'][1]}, strong kept "
                  f"{m['strong_kept']:.2f}, arrivals {m['arrivals_kept']:.2f}, the tune's notes {m['tune_notes']:.2f}")
        manifest["tunes"].append(tune_rec)
    (a.out / "breaks.json").write_text(json.dumps(manifest, indent=1))
    if not a.keep:
        for f in (a.out / "tmp").glob("*.wav"):
            f.unlink()
        (a.out / "tmp").rmdir()
    print(f"wrote {a.out / 'breaks.json'}")


if __name__ == "__main__":
    main()
