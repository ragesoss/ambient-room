#!/usr/bin/env python3
"""A room-like impulse response for the no-device runs (`[device] file_room_ir`, `tools/ud_run.py --room-ir`): the
speakers heard by a microphone across a room. The direct sound after `--delay-ms`, six early reflections 1-21 ms after
it, and a diffuse tail decaying by 60 dB over `--rt60` s, darker as it decays, `--drr` dB under the direct sound in
energy. Written as float32 .npy at 48 kHz.

    tools/ud_room.py local/room-ir.npy [--delay-ms 4] [--rt60 0.5] [--drr 0] [--length 0.6] [--seed 1]
"""

from __future__ import annotations

import argparse

import numpy as np


def room_ir(sr: int = 48000, delay_ms: float = 4.0, rt60: float = 0.5, drr_db: float = 0.0, length_s: float = 0.6,
            seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(length_s * sr)
    h = np.zeros(n)
    d = int(delay_ms * sr / 1000)
    h[d] = 1.0
    for _ in range(6):
        h[d + int(rng.uniform(1, 21) * sr / 1000)] += rng.uniform(-0.6, 0.6)
    t = np.arange(n) / sr
    tail = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)
    tail[: d + int(0.005 * sr)] = 0
    w = np.clip(t / rt60, 0, 1)
    tail = (1 - w) * tail + w * np.convolve(tail, np.ones(8) / 8, "same")
    tail *= np.sqrt(10 ** (-drr_db / 10) / np.sum(tail ** 2))
    return (h + tail).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--delay-ms", type=float, default=4.0)
    ap.add_argument("--rt60", type=float, default=0.5)
    ap.add_argument("--drr", type=float, default=0.0)
    ap.add_argument("--length", type=float, default=0.6)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    np.save(a.out, room_ir(48000, a.delay_ms, a.rt60, a.drr, a.length, a.seed))


if __name__ == "__main__":
    main()
