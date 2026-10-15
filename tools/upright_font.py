"""Build sounds/upright.sf2: the player's own upright bass, from the bass exercise takes (2026-10-15).

    PYTHONPATH=. .venv/bin/python tools/upright_font.py [--collect] [--transcription DIR]

The bass is a New Standard Cleveland (laminate, 2007) with Pirastro Perpetual Stark strings,
recorded through the Ear Trumpet Labs Nadine on its afterlength, in the exercise takes of
~/play/dobro-transcription (exercises/bass, tunes/bass; the bowed ones left out). A prototype,
as the dobro's: the takes were not made for sampling, so the notes stop where the next one is
played, and some pitches were never played long or at all.

--collect: every answer-key note the bass detector found at its key's pitch, with how long it
rings until the next note and how clean its start is (the level 50-300 ms after it against
10-60 ms before), written to sounds/upright-candidates.json. It needs the transcription
project's pipeline (as tools/tune_fit.py).

Then, for each of SAMPLED, the longest clean candidate (start 10 dB or more above the sound
before it; through the Scarlett 18i8, the newest and cleanest chain, if it rings 1.2 s or
more): cut from 3 ms before its pluck to 40 ms before the next note (at most MAX_S), faded in
over 2 ms and out over 120 ms, matched in loudness on its first 300 ms, and tuned by its
measured pitch. Each covers the keys halfway to its sampled neighbours; the selection goes to
sounds/upright-selection.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parents[1]
SOUNDS = HERE / "sounds"
# the pitches the takes have long, clean notes of (2026-10-15): E1 G1 A1 C2 D2 G2, and A2 and D3 at the top
# (0.8 s: the top of a bass line is rarer)
SAMPLED = [28, 31, 33, 36, 38, 43, 45, 50]
MIN_CONTRAST_DB = 10.0
PREFER_18I8_S = 1.2
MAX_S = 4.0
LEVEL_RMS = 0.12  # the first 300 ms of every sample


def collect(root: Path) -> list[dict]:
    sys.path.insert(0, str(root / "pipeline" / "src"))
    from transcribe.bench import instrument_of
    from transcribe.detect import load
    from transcribe.evaluate import evaluate, read_takes
    from transcribe.score import read_score, take_key
    from transcribe.transcribe import transcribe
    out = []
    dirs = [d for base in ("exercises", "tunes") for d in sorted((root / base / "bass").iterdir())
            if (d / "takes.csv").exists() and "arco" not in d.name]
    for d in dirs:
        for take in read_takes(d):
            ref, _ = read_score(take_key(d, take))
            y = load(take.path)
            known = take.conditions.get("pickup_beats")
            tr = transcribe(y, take.bpm, pickup_beats=float(known) if known else None, metronome=take.metronome,
                            instrument=instrument_of(d, take), beats_per_bar=int(take.conditions.get("beats_per_bar") or 4))
            res = evaluate(ref, tr.detected, take.beat0_s, take.bpm)
            onsets = sorted(n.onset_s for n in tr.detected)
            x, sr = sf.read(take.path, always_2d=True)
            x = x[:, 0]
            for r, dn in res.matches:
                if dn.midi != r.midi:
                    continue
                t = dn.onset_s
                nxt = min([o for o in onsets if o > t + 0.05] or [len(x) / sr])
                pre = x[max(0, int((t - 0.06) * sr)):int((t - 0.01) * sr)]
                post = x[int((t + 0.05) * sr):int((t + 0.3) * sr)]
                rms = lambda v: np.sqrt(np.mean(v ** 2)) + 1e-9
                out.append(dict(take=str(take.path.relative_to(root)), session=take.conditions.get("session", ""),
                                onset=round(t, 4), midi=r.midi, string=r.string, fret=r.fret,
                                length=round(nxt - t, 3), contrast=round(float(20 * np.log10(rms(post) / rms(pre))), 1)))
    return out


def find_pluck(y: np.ndarray, sr: int, onset: float, before: float = 0.04, after: float = 0.08,
               within_db: float = 10.0) -> float:
    """The pluck near a detected onset (s): the first 1.5 ms frame in [onset - before, onset +
    after] whose level comes within `within_db` of the loudest there."""
    hop = int(round(0.0015 * sr))
    a = max(0, int((onset - before) * sr))
    x = y[a:int((onset + after) * sr)]
    n = len(x) // hop
    db = 10 * np.log10(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    k = int(np.nonzero(db >= db.max() - within_db)[0][0])
    return a / sr + k * hop / sr


def partial_cents(x: np.ndarray, sr: int, m: int) -> float:
    """The note's pitch in cents from m: the median of its partials 2-6, each found within 60
    cents of where it should be (peak-interpolated, over its own number). Through the Nadine the
    low strings' fundamentals are 25-35 dB under their octave (dobro-transcription, bass.py)."""
    nfft = 1 << 18
    mag = np.abs(np.fft.rfft(x * np.hanning(len(x)), nfft))
    hz, f0 = sr / nfft, librosa.midi_to_hz(m)
    est = []
    for h in range(2, 7):
        lo, hi = int(h * f0 * 2 ** (-0.6 / 12) / hz), int(h * f0 * 2 ** (0.6 / 12) / hz)
        k = lo + int(np.argmax(mag[lo:hi]))
        if lo < k < hi - 1:
            a, b, c = np.log(mag[k - 1:k + 2] + 1e-12)
            p = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else 0.0
            est.append(1200 * np.log2((k + p) * hz / h / f0))
    return float(np.median(est)) if len(est) >= 3 else 0.0


def choose(candidates: list[dict], m: int) -> dict | None:
    clean = [r for r in candidates if r["midi"] == m and r["contrast"] >= MIN_CONTRAST_DB]
    newest = [r for r in clean if r["session"].endswith("18i8") and r["length"] >= PREFER_18I8_S]
    pool = newest or clean
    return max(pool, key=lambda r: r["length"]) if pool else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcription", type=Path, default=Path.home() / "play" / "dobro-transcription")
    ap.add_argument("--collect", action="store_true", help="find the candidate notes afresh")
    a = ap.parse_args()
    cand_path = SOUNDS / "upright-candidates.json"
    if a.collect or not cand_path.exists():
        json.dump(collect(a.transcription), open(cand_path, "w"), indent=0)
    candidates = json.load(open(cand_path))
    sys.path.insert(0, str(a.transcription / "dobro-soundfont" / "tools"))
    from sf2write import write_sf2

    chosen = [(m, choose(candidates, m)) for m in SAMPLED]
    chosen = [(m, r) for m, r in chosen if r]
    zones, selection, rate = [], [], None
    for i, (m, r) in enumerate(chosen):
        y, sr = sf.read(a.transcription / r["take"], always_2d=True)
        y = y[:, 0]  # the Nadine (a two-channel raw take's first channel; the takes are that channel alone)
        rate = rate or sr
        assert sr == rate, "all takes must share a sample rate"
        pluck = find_pluck(y, sr, r["onset"])
        start = max(int((pluck - 0.003) * sr), 0)
        end = int((min(r["onset"] + r["length"] - 0.04, pluck + MAX_S)) * sr)
        x = y[start:end].copy()
        fade_in, fade_out = int(0.002 * sr), int(0.12 * sr)
        x[:fade_in] *= np.linspace(0, 1, fade_in)
        x[-fade_out:] *= np.linspace(1, 0, fade_out)
        x *= LEVEL_RMS / (np.sqrt(np.mean(x[:int(0.3 * sr)] ** 2)) + 1e-9)
        x /= max(1.0, np.abs(x).max() / 0.98)
        cents = partial_cents(x[int(0.1 * sr):int(min(len(x), 1.2 * sr))], sr, m)
        lo = 0 if i == 0 else (chosen[i - 1][0] + m) // 2 + 1
        hi = 127 if i == len(chosen) - 1 else (m + chosen[i + 1][0]) // 2
        name = librosa.midi_to_note(m, unicode=False)
        zones.append(dict(name=f"{name} {r['string']}-{r['fret']}", data=x, root=m, cents=-cents, lo=lo, hi=hi))
        selection.append(dict(midi=m, note=name, string=r["string"], fret=r["fret"], take=r["take"], session=r["session"],
                              onset=r["onset"], pluck_ms=round(1000 * (pluck - r["onset"]), 1),
                              length=round(len(x) / sr, 3), tuning_cents=round(cents, 1),
                              keys=[librosa.midi_to_note(lo, unicode=False), librosa.midi_to_note(hi, unicode=False)]))
        print(f"{name:4s} {r['string']}/{r['fret']:<2d} {len(x) / sr:4.2f} s  keys {selection[-1]['keys'][0]}-"
              f"{selection[-1]['keys'][1]}  tuning {cents:+5.1f} cents  pluck {selection[-1]['pluck_ms']:+5.1f} ms  ({r['take']})")
    out = SOUNDS / "upright.sf2"
    write_sf2(out, "UprightBassPrototype", "Upright bass (Cleveland)", zones, rate, bank=0, program=32)
    json.dump(selection, open(SOUNDS / "upright-selection.json", "w"), indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
