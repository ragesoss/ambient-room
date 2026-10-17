#!/usr/bin/env python3
"""The band, replayed end to end without a sound card: a recorded take streamed through the live band at the
wall clock's pace, its cues sounded by the band player and engine into an output that runs at a sound card's pace
and keeps what it plays, then compared with the transcription project's offline render of the same take.

    tools/band_replay.py [CASE ...] [--config FILE] [--transcribe DIR] [--block 128] [--buffer-ms 8]
        [--in-block 256] [--lead 0.05] [--out DIR] [--clip-s 25] [--thread]
    tools/band_replay.py levels [--transcribe DIR]
    tools/band_replay.py sweep [CASE ...] --blocks 64,128,256 (--buffers-ms 2.7,5.3,8 | --mults 2,3,4) [--out DIR]
    tools/band_replay.py [CASE ...] --output alsa [--device DEV] [--out DIR]     # ALOUD

CASE: the transcription project's band harness takes (`red-wing`, `bass-dy`, ...; default those two). DIR: that
project's checkout (default the config's `[band] transcribe`, less `pipeline/src`). The block and buffer default to
the config's `[band]`. Nothing is played aloud unless `--output alsa` is given: the output is `paced`
(`ambient/output.py`) whatever the config says. With `--output alsa` the band (not the take) plays on the device,
and what the device granted and how steady its clock looked are reported instead of the capture's checks and clips.

For each take:
- **Live:** `transcribe.liveband.LiveBand` as `tools/band_stream_timing.py` there builds it (the chart known and
  where it starts, the beat live from a cold start, `lead_s` as given), fed the take at 48 kHz in `--in-block`
  blocks, each when its last sample would have been captured. Every cue goes to the band player as it comes; the
  engine computes `--block` frames at a time into a `--buffer-ms` buffer emptied at a sound card's pace, and the
  capture is what that card would have played.
- **Offline:** the same decisions over the whole take (`livebeat.follow`, `band.run`, at 48 kHz) voiced as
  `tools/band_render.py` voices them (`notes_for`, `stems_for`: the `fluidsynth` program), and its mix.
- **Compared:** every note, live against offline, by part: its onset as heard (the live one from the engine's log,
  checked against the capture; the offline one as the `fluidsynth` program places it, checked against its render);
  the cues that came late (played late, or dropped); each cue's margin when it reached the player (how long before
  its first note the engine would have computed past it) and the engine's delay (from a cue's arrival until the
  first frame still open is heard).
- **Clips** (OUT/CASE-offline.mp3, CASE-live.mp3): the take with the band, the same `--clip-s` seconds from the
  first beat the chords play, both at -20 LUFS (`ffmpeg`'s loudness measure).

`levels`: each part's loudness on its own FluidSynth over the harness takes' offline renders, and the gains that set
the parts as the offline render sets them (`ambient/bandplayer.py`, `PART_GAIN_DB`).
`sweep`: what this computer sustains: the replay at each engine block and buffer: underruns, late cues, and the
engine's response (from the moment one block could go into the buffer to the moment the next came: its largest is
the smallest buffer that run would have kept fed).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from ambient import bandplayer  # noqa: E402
from ambient.bandengine import EngineProcess, EngineSpec  # noqa: E402
from ambient.config import load_config  # noqa: E402
from ambient.fluid import STEP, Synth  # noqa: E402

RATE = 48000


# ---------------------------------------------------------------------------------------------- the project


class Project:
    """The transcription project's code, used as a library: its package and the harness's tools."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser()
        for sub in ("pipeline/src", "pipeline/tools"):
            p = str(self.root / sub)
            if p not in sys.path:
                sys.path.insert(0, p)
        import band_harness as bh
        import band_render as br
        import band_stream_timing as bst
        import realtime_chords_study as rcs
        from transcribe import band as B
        from transcribe import bandvoice
        self.bh, self.br, self.bst, self.rcs, self.B, self.voicing = bh, br, bst, rcs, B, bandvoice

    def case(self, name: str):
        return next(c for c in self.rcs.CASES if c.name == name)


def project_root(args, cfg) -> Path:
    if args.transcribe:
        return Path(args.transcribe)
    src = Path(cfg.band.transcribe).expanduser()
    return src.parent.parent  # .../pipeline/src


# ---------------------------------------------------------------------------------------------- one replay


def replay(pj: Project, case_name: str, fonts: list[Path], block: int, buffer_ms: float, in_block: int,
           lead_s: float | None, capture: Path | None, late_s: dict | None = None, gain_db: float = 0.0,
           voices=None, process: bool = True, keep_stems: bool = True, output: str = "paced", device: str = "",
           period_ms: float | None = None, rt_priority: int = 0) -> dict:
    """The take streamed through the live band at the wall clock's pace into the band player and engine (in a
    process of its own, or a thread of this one). `output` "alsa" plays it on `device`: aloud."""
    case = pj.case(case_name)
    tk = pj.bst.take_at(case, RATE)
    chart = pj.bh.chart_of(case)
    band = pj.bst.band_for(case, tk, RATE, chart, 0, lead_s)
    if output != "paced":
        capture = None
    spec = EngineSpec(tuple(fonts), voices or bandplayer.voices(pj.voicing), output, device, buffer_ms, period_ms,
                      capture, block, RATE, gain_db, rt_priority, keep_stems)
    engine = EngineProcess(spec) if process else spec.build()
    engine.start()
    while engine.started_at() is None:
        time.sleep(0.001)
    zero = time.monotonic() + 0.1  # the stream's sample 0, at the wall clock
    clock = bandplayer.StreamClock.replay(zero, engine.started_at())
    player = bandplayer.BandPlayer(engine, clock, tk.spb, pj.voicing)
    if late_s is not None:
        player.late_s = dict(late_s)
    y = tk.y
    n_blocks = (len(y) + in_block - 1) // in_block
    compute = np.zeros(n_blocks)
    cues = []
    for k in range(n_blocks):
        arrival = zero + min((k + 1) * in_block, len(y)) / RATE
        wait = arrival - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        c0 = time.perf_counter()
        got = band.push(y[k * in_block: (k + 1) * in_block])
        compute[k] = time.perf_counter() - c0
        for c in got:
            player.cue(c)
            cues.append(c)
    for c in band.finish():
        player.cue(c)
        cues.append(c)
    end = clock.engine_time(len(y) / RATE) + 2.5  # the last notes' tails
    while engine.time() < end and engine.running:
        time.sleep(0.05)
    engine.stop()
    if engine.error:
        raise RuntimeError(engine.error)
    return dict(case=case, tk=tk, chart=chart, band=band, engine=engine, capture=capture, clock=clock,
                player=player, cues=cues, compute=compute, block=block, buffer_ms=buffer_ms, in_block=in_block,
                lead_s=band.band.p.lead_s, process=process, zero=zero)


# ---------------------------------------------------------------------------------------------- offline


def cli_frame(t: float) -> int:
    """The frame the `fluidsynth` program starts an event of a MIDI file written by band_render's `midi` (ticks of
    1/960 s): its file player runs before each 64-frame block, on the whole milliseconds rendered so far, and sends
    the events up to the tick that rounds to; the note sounds from the block after. Found by probing it, checked
    against its renders (`offline`)."""
    tick = round(t * 960)
    delta = 500000 / 480 / 1000  # ms a tick: the file's tempo over its division
    k = max(0, int(0.75 * (tick - 0.5) * delta) - 3)
    while int((STEP * 1000 * k) // RATE / delta + 0.5) < tick:
        k += 1
    return (k + 1) * STEP


def render_like_cli(notes, fonts: list[Path], voicing, length: int) -> dict[str, np.ndarray]:
    """The notes through this FluidSynth at `cli_frame`'s frames, each part on its own, mono."""
    out = {}
    for part, (ch, prog, _, _) in voicing.VOICE.items():
        mine = [x for x in notes if x[2] == ch]
        if not mine:
            continue
        ev = sorted([(cli_frame(t), 1, key, vel) for t, n, _, key, vel in mine]
                    + [(cli_frame(t + n), 0, key, 0) for t, n, _, key, vel in mine])
        s = Synth(fonts, RATE)
        s.program(ch, prog)
        x = np.zeros((length, 2), dtype=np.float32)
        pos, j = 0, 0
        while pos < length:
            while j < len(ev) and ev[j][0] <= pos:
                f, kind, key, vel = ev[j]
                s.noteon(ch, key, vel) if kind else s.noteoff(ch, key)
                j += 1
            nxt = min(length, ev[j][0] if j < len(ev) else length)
            nxt = max(nxt, pos + STEP) if nxt > pos else pos + STEP
            nxt = min(nxt, length)
            s.render(nxt - pos, x[pos:nxt])
            pos = nxt
        s.close()
        out[part] = x.mean(axis=1)
    return out


def offline(pj: Project, r: dict, fonts: list[Path]) -> dict:
    """The same take's decisions over the whole take, voiced and rendered as band_render does."""
    tk, B = r["tk"], pj.B
    logs = B.run(tk.y, RATE, pj.bh.beats_for(tk, "live", RATE), r["chart"], None, tk.bpb, tk.notch, 0)
    notes = pj.br.notes_for(logs, tk.spb)
    stems = pj.br.stems_for(notes, fonts[0].parent)
    y = pj.br.take_audio(r["case"])
    # the program's onsets: rendered here at `cli_frame`'s frames, the same sound to 16 bits
    mine = render_like_cli(notes, fonts, pj.voicing, max(len(x) for x in stems.values()))
    check = {p: float(np.abs(mine[p][: len(stems[p])] - stems[p]).max()) for p in stems}
    return dict(logs=logs, notes=notes, stems=stems, y=y, cli_check=check)


# ---------------------------------------------------------------------------------------------- compare


def live_notes(r: dict) -> list[dict]:
    """Every note the engine was given: part, key, asked and started frames, as stream times."""
    clock, eng = r["clock"], r["engine"]
    rows = []
    for lg in eng.log:
        rows.append({"tag": lg.tag, "part": lg.part, "key": lg.key, "vel": lg.vel,
                     "want": clock.stream_time(lg.want / RATE),
                     "start": None if lg.start is None else clock.stream_time(lg.start / RATE), "late": lg.late / RATE})
    return rows


def match(off_notes, live: list[dict], voicing) -> dict[str, list]:
    """Pairs (offline note, live note) by part and key, nearest in time within 60 ms; None where one has no pair."""
    parts = {ch: part for part, (ch, *_) in voicing.VOICE.items()}
    out = {p: [] for p in voicing.VOICE}
    for part in voicing.VOICE:
        ch = voicing.VOICE[part][0]
        offs = sorted((t, key) for t, n, c, key, v in off_notes if c == ch)
        lives = sorted((x["want"], i) for i, x in enumerate(live) if x["part"] == part)
        used = set()
        for t, key in offs:
            best, bi = None, None
            for w, i in lives:
                if i in used or live[i]["key"] != key or abs(w - t) > 0.06:
                    continue
                if best is None or abs(w - t) < abs(best - t):
                    best, bi = w, i
            if bi is not None:
                used.add(bi)
            out[part].append(((t, key), None if bi is None else live[bi]))
        for w, i in lives:
            if i not in used:
                out[part].append((None, live[i]))
    assert set(parts.values()) == set(out)
    return out


def capture_check(r: dict) -> dict:
    """The output against the engine: (1) the capture is the engine's parts mixed as it mixes them (to 16 bits),
    nothing shifted or lost; (2) each part's sound is its logged notes rendered again at their logged frames (to the
    float's precision), so the log's onsets are what was played."""
    import wave
    with wave.open(str(r["capture"]), "rb") as w:
        cap = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2) / 32767.0
    eng = r["engine"]
    stems = {p: np.concatenate(v) if v else np.zeros(0, dtype=np.float32) for p, v in eng.stems.items()}
    n = min(len(cap), min(len(v) for v in stems.values()))
    mixed = np.zeros((n, 2))
    for p, v in eng.voices.items():
        g = 10 ** (v.gain_db / 20) * eng.gain
        mixed[:, 0] += g * np.sqrt((1 - v.pan) / 2) * np.sqrt(2) * stems[p][:n]
        mixed[:, 1] += g * np.sqrt((1 + v.pan) / 2) * np.sqrt(2) * stems[p][:n]
    log_check = {}
    for part, v in eng.voices.items():
        ev = sorted([(lg.start, 1, lg.key, lg.vel) for lg in eng.log if lg.part == part and lg.start is not None]
                    + [(lg.stop, 0, lg.key, 0) for lg in eng.log if lg.part == part and lg.stop is not None])
        s = Synth(eng.fonts, RATE)
        s.program(v.channel, v.program)
        x = np.zeros((n, 2), dtype=np.float32)
        j = 0
        for f in range(0, n - n % STEP, STEP):
            while j < len(ev) and ev[j][0] <= f:
                fr, kind, key, vel = ev[j]
                s.noteon(v.channel, key, vel) if kind else s.noteoff(v.channel, key)
                j += 1
            s.render(STEP, x[f:f + STEP])
        s.close()
        m = n - n % STEP
        log_check[part] = float(np.abs(x[:m].mean(axis=1) - stems[part][:m]).max())
    return {"capture_vs_stems_max": float(np.abs(cap[:n] - np.clip(mixed, -1, 1)).max()), "log_vs_stems_max": log_check,
            "frames": n, "capture": cap}


def loudness_lufs(path: Path) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    lines = [ln for ln in r.stderr.splitlines() if ln.strip().startswith("I:")]
    return float(lines[-1].split()[1])


def write_clip(x: np.ndarray, path: Path, target: float = -20.0) -> float:
    import soundfile as sf
    tmp = path.with_suffix(".tmp.flac")
    sf.write(str(tmp), x, RATE, subtype="PCM_24")
    gain = target - loudness_lufs(tmp)
    y = x * 10 ** (gain / 20)
    peak = float(np.abs(y).max())
    if peak > 0.99:  # never clip: both clips of a pair get the same target, so say so if one had to be lower
        y *= 0.99 / peak
    sf.write(str(path.with_suffix(".flac")), y, RATE, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(path.with_suffix(".flac")), "-b:a", "192k",
                    str(path.with_suffix(".mp3"))], check=True)
    tmp.unlink()
    return loudness_lufs(path.with_suffix(".flac"))


def stats(x) -> dict:
    x = np.asarray(x, dtype=float)
    if not len(x):
        return {"n": 0}
    return {"n": int(len(x)), "median_ms": 1000 * float(np.median(x)), "p5_ms": 1000 * float(np.percentile(x, 5)),
            "p95_ms": 1000 * float(np.percentile(x, 95)), "min_ms": 1000 * float(x.min()),
            "max_ms": 1000 * float(x.max())}


def compare(pj: Project, r: dict, off: dict, out_dir: Path | None, clip_s: float) -> dict:
    eng, clock = r["engine"], r["clock"]
    live = live_notes(r)
    pairs = match(off["notes"], live, pj.voicing)
    res = {"case": r["case"].name, "block": r["block"], "buffer_ms": r["buffer_ms"], "in_block": r["in_block"],
           "lead_s": r["lead_s"], "engine_in": "a process of its own" if r["process"] else "a thread",
           "underruns": eng.underruns, "underrun_frames": eng.underrun_frames,
           "underruns_at_s": [round(clock.stream_time(f / RATE), 3) for f, n in eng.gaps],
           "skipped_frames": eng.skipped, "cli_check": off["cli_check"], "parts": {}}
    for part, ps in pairs.items():
        offs = [p for p in ps if p[0] is not None]
        both = [(o, lv) for o, lv in ps if o is not None and lv is not None and lv["start"] is not None]
        # onsets as heard: live from the engine's log, offline as the program places them
        d = [lv["start"] - cli_frame(o[0]) / RATE for o, lv in both]
        d_nominal = [lv["start"] - o[0] for o, lv in both]
        asked = [lv["want"] - o[0] for o, lv in both]
        delivered = [lv["start"] - lv["want"] for o, lv in both]
        firsts = [(o, lv) for o, lv in both]
        worst = sorted(both, key=lambda p: -abs(p[1]["start"] - cli_frame(p[0][0]) / RATE))[:3]
        res["parts"][part] = {
            "offline_notes": len(offs), "live_notes": sum(1 for p in ps if p[1] is not None),
            "matched_and_played": len(both),
            "offline_only": sum(1 for o, lv in ps if lv is None), "live_only": sum(1 for o, lv in ps if o is None),
            "dropped_notes": sum(1 for o, lv in ps if lv is not None and lv["start"] is None),
            "onset_vs_offline": stats(d), "onset_vs_offline_nominal": stats(d_nominal),
            "asked_vs_offline_nominal": stats(asked), "heard_vs_asked": stats(delivered),
            "cues": dict(eng.counts.get(part, {})), "late_played_ms": [round(1000 * x, 2) for x in eng.late_s[part]],
            "worst": [{"offline_s": round(o[0], 4), "live_s": round(lv["start"], 4),
                       "ms": round(1000 * (lv["start"] - cli_frame(o[0]) / RATE), 2), "beat": lv["tag"][0]}
                      for o, lv in worst],
        }
        del firsts
    cl = r["player"].log
    res["margin"] = {part: stats([c.margin for c in cl if c.cue.part == part]) for part in pj.voicing.VOICE}
    res["lead_given"] = {part: stats([c.cue.t - c.cue.decided_at for c in cl if c.cue.part == part])
                         for part in pj.voicing.VOICE}
    res["engine_delay"] = stats([c.delay for c in cl if c.delay is not None])
    # from the moment everything a cue was decided from had been captured, to its reaching the player: the
    # capture's block and the band's compute
    res["to_player"] = stats([c.arrived - (r["zero"] + c.cue.decided_at) for c in cl])
    comp = r["compute"]
    res["band_compute"] = {"ms_per_s": 1000 * float(comp.sum()) / (len(r["tk"].y) / RATE),
                           "worst_block_ms": 1000 * float(comp.max()), "p99_block_ms": 1000 * float(np.percentile(comp, 99))}
    ec = np.asarray(eng.compute_s)
    res["engine_worst_blocks_at_s"] = [round(clock.stream_time(int(k) * r["block"] / RATE), 3)
                                       for k in np.argsort(ec)[::-1][:3]]
    res["engine_compute"] = {"ms_per_s": 1000 * float(ec.sum()) / (len(ec) * r["block"] / RATE),
                             "cpu_ms_per_s": 1000 * eng.cpu_s / (len(ec) * r["block"] / RATE),
                             "worst_block_ms": 1000 * float(ec.max()), "p99_block_ms": 1000 * float(np.percentile(ec, 99))}
    res["output"] = getattr(eng, "granted", None) or {}
    if r["capture"] is None:  # a real device: what it granted, and how steady its clock looked
        return res
    chk = capture_check(r)
    res["capture_vs_engine_stems_max"] = chk["capture_vs_stems_max"]
    res["log_vs_engine_stems_max"] = chk["log_vs_stems_max"]
    if out_dir is None:
        return res
    # the clips: the take with the band, offline and live, the same seconds
    y = off["y"]
    cap = chk["capture"]
    shift = int(round(clock.offset * RATE))  # capture frame of the stream's sample 0
    live_band = np.zeros((len(y), 2))
    seg = cap[shift: shift + len(y)]
    live_band[: len(seg)] = seg
    # the band's level against the take: the offline band's, as one gain on the whole capture
    br = pj.br
    gains = br.part_gains(y, off["stems"], -4.0)
    off_band = np.zeros((len(y), 2))
    for part, g in gains.items():
        x, pan = off["stems"][part][: len(y)], pj.voicing.VOICE[part][2]
        off_band[: len(x), 0] += g * x * np.sqrt((1 - pan) / 2) * np.sqrt(2)
        off_band[: len(x), 1] += g * x * np.sqrt((1 + pan) / 2) * np.sqrt(2)
    g_live = 10 ** ((br.loudness(off_band.mean(axis=1)) - br.loudness(live_band.mean(axis=1))) / 20)
    # the capture placed on the take by the clock: the band's sound, live against offline, lines up within a few ms
    lo, hi = int(r["tk"].start * RATE), int(min(len(y) / RATE, r["tk"].end) * RATE)
    m_off, m_live = off_band[lo:hi].mean(axis=1), live_band[lo:hi].mean(axis=1)
    lags = np.arange(-480, 481)
    xc = [float(np.dot(m_off[480 + k: len(m_off) - 480 + k], m_live[480: len(m_live) - 480])) for k in lags]
    res["band_audio_lag_ms"] = -1000 * float(lags[int(np.argmax(xc))]) / RATE  # + : the live band later
    res["band_audio_corr"] = max(xc) / float(np.sqrt(np.dot(m_off, m_off) * np.dot(m_live, m_live)))
    res["clock_offset_s"] = clock.offset
    live_mix = y[:, None] + g_live * live_band
    off_mix = br.mix(y, off["stems"], -4.0)[: len(y)]
    first_comp = min((lg.t for lg in off["logs"] if "comp" in lg.plays), default=r["tk"].start)
    a = max(0, int((first_comp - 1.0) * RATE))
    b = min(len(y), a + int(clip_s * RATE))
    out_dir.mkdir(parents=True, exist_ok=True)
    name = r["case"].name
    lo = write_clip(off_mix[a:b], out_dir / f"{name}-offline")
    ll = write_clip(live_mix[a:b], out_dir / f"{name}-live")
    res["clips"] = {"from_s": a / RATE, "to_s": b / RATE, "offline": str(out_dir / f"{name}-offline.mp3"),
                    "live": str(out_dir / f"{name}-live.mp3"), "lufs": [lo, ll],
                    "band_vs_take_live_gain_db": 20 * np.log10(g_live)}
    import soundfile as sf
    sf.write(str(out_dir / f"{name}-live-full.flac"), live_mix / max(1e-9, np.abs(live_mix).max()) * 0.89, RATE,
             subtype="PCM_24")
    return res


# ---------------------------------------------------------------------------------------------- the commands


def fonts_of(cfg, pj: Project) -> list[Path]:
    return [cfg.sounds_dir / f for f in pj.voicing.FONTS]


def print_result(res: dict) -> None:
    print(f"\n{res['case']}: the engine in {res['engine_in']}, its block {res['block']} ({1000 * res['block'] / RATE:.1f} ms), buffer "
          f"{res['buffer_ms']} ms, capture blocks of {res['in_block']}, lead {res['lead_s']} s; underruns "
          f"{res['underruns']} ({res['underrun_frames']} frames, at {res['underruns_at_s']} s of the take); the "
          f"engine's slowest blocks at {res['engine_worst_blocks_at_s']} s")
    print(f"  the offline render placed as `cli_frame` says (max difference, 16-bit steps are 3.1e-5): "
          + ", ".join(f"{k} {v:.1e}" for k, v in res["cli_check"].items()))
    if "capture_vs_engine_stems_max" in res:
        print(f"  the capture against the engine's own parts (max difference): {res['capture_vs_engine_stems_max']:.1e}; "
              f"the parts against their logged notes: " + ", ".join(f"{k} {v:.1e}" for k, v in res["log_vs_engine_stems_max"].items()))
    else:
        print(f"  the device: {res['output']}")
    resp = res.get("output", {}).get("response_ms")
    if resp:
        print(f"  the engine's response (one block's room to the next block, {resp['n']} blocks): median "
              f"{resp['median']:.2f} ms, p99 {resp['p99']:.2f}, p99.9 {resp['p99.9']:.2f}, max {resp['max']:.2f}: "
              f"the smallest buffer this run kept fed")
    print(f"  engine delay (a cue's arrival to the first frame still open being heard): "
          f"median {res['engine_delay'].get('median_ms', float('nan')):.1f} ms, max {res['engine_delay'].get('max_ms', float('nan')):.1f}")
    tp = res["to_player"]
    print(f"  from all heard to the player (capture block and compute): median {tp['median_ms']:.1f} ms, "
          f"p95 {tp['p95_ms']:.1f}, max {tp['max_ms']:.1f}")
    print(f"  band compute {res['band_compute']['ms_per_s']:.0f} ms/s, worst block {res['band_compute']['worst_block_ms']:.1f} ms; "
          f"engine compute {res['engine_compute']['ms_per_s']:.1f} ms/s (its CPU {res['engine_compute']['cpu_ms_per_s']:.1f}), "
          f"worst block {res['engine_compute']['worst_block_ms']:.2f} ms, p99 {res['engine_compute']['p99_block_ms']:.2f}")
    for part, p in res["parts"].items():
        s, m, lg = p["onset_vs_offline"], res["margin"][part], res["lead_given"][part]
        if not s.get("n"):
            continue
        print(f"  {part:4s}: notes offline {p['offline_notes']}, live {p['live_notes']}, both and played "
              f"{p['matched_and_played']}; only offline {p['offline_only']}, only live {p['live_only']}, dropped "
              f"{p['dropped_notes']}; cues {p['cues']}")
        h, ask = p["heard_vs_asked"], p["asked_vs_offline_nominal"]
        print(f"        heard - asked (the player and engine): median {h['median_ms']:+.2f} ms, {h['min_ms']:+.2f} to "
              f"{h['max_ms']:+.2f}; asked - offline's times (the decision): median {ask['median_ms']:+.2f}, "
              f"{ask['min_ms']:+.2f} to {ask['max_ms']:+.2f}")
        print(f"        heard live - heard offline: median {s['median_ms']:+.2f} ms, {s['min_ms']:+.2f} to "
              f"{s['max_ms']:+.2f}")
        print(f"        lead the band gave: median {lg['median_ms']:.1f} ms, min {lg['min_ms']:.1f}; margin at the "
              f"player: median {m['median_ms']:.1f} ms, min {m['min_ms']:.1f}")
    if "band_audio_lag_ms" in res:
        print(f"  the live band's sound against the offline's, over the take: best lag {res['band_audio_lag_ms']:+.2f} ms "
              f"(+: live later), correlation {res['band_audio_corr']:.2f}")
    if "clips" in res:
        c = res["clips"]
        print(f"  clips {c['from_s']:.1f}-{c['to_s']:.1f} s at {c['lufs'][0]:.1f} / {c['lufs'][1]:.1f} LUFS:\n"
              f"    {c['offline']}\n    {c['live']}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cases", nargs="*")
    p.add_argument("--config", default=str(HERE / "config" / "desktop.toml"))
    p.add_argument("--transcribe", help="the transcription project's checkout")
    p.add_argument("--block", type=int, default=None, help="the engine's block (frames)")
    p.add_argument("--buffer-ms", type=float, default=None, help="the output's buffer (ms)")
    p.add_argument("--in-block", type=int, default=256, help="the capture's block (samples at 48 kHz)")
    p.add_argument("--lead", type=float, default=None, help="lead_s (default the band's, 0.05)")
    p.add_argument("--out", type=Path, default=None, help="where the clips and the JSON go")
    p.add_argument("--clip-s", type=float, default=25.0)
    p.add_argument("--blocks", default="64,128,256")
    p.add_argument("--buffers-ms", default="2.7,5.3,8,10.7")
    p.add_argument("--mults", default=None, help="sweep: buffers as these multiples of the block, not --buffers-ms")
    p.add_argument("--switch-ms", type=float, default=None, help="Python's thread switch interval (ms)")
    p.add_argument("--thread", action="store_true", help="the engine in a thread of this process, not its own")
    p.add_argument("--output", default="paced", choices=("paced", "alsa"),
                   help="alsa: the band on the config's [band] device, ALOUD (the practice device: the player's go-ahead)")
    p.add_argument("--device", default=None, help="with --output alsa: the device (default the config's [band] device)")
    a = p.parse_args()
    if a.switch_ms is not None:
        sys.setswitchinterval(a.switch_ms / 1000)
    cfg = load_config(Path(a.config))
    pj = Project(project_root(a, cfg))
    fonts = fonts_of(cfg, pj)
    block = a.block or cfg.band.block
    buffer_ms = a.buffer_ms or cfg.band.buffer_ms
    cmd = a.cases[0] if a.cases and a.cases[0] in ("levels", "sweep") else None
    cases = [c for c in a.cases if c not in ("levels", "sweep")] or ["red-wing", "bass-dy"]
    late = {k: v / 1000 for k, v in cfg.band.late_ms.items()}
    if cmd == "levels":
        levels(pj, fonts)
        return
    if cmd == "sweep":
        rows = []
        for blk in [int(x) for x in a.blocks.split(",")]:
            bufs = ([m * blk * 1000 / RATE for m in map(float, a.mults.split(","))] if a.mults
                    else [float(x) for x in a.buffers_ms.split(",")])
            for buf in bufs:
                if buf * RATE / 1000 < blk:
                    continue
                for name in cases:
                    r = replay(pj, name, fonts, blk, buf, a.in_block, a.lead, None, late, cfg.band.gain_db,
                               process=not a.thread, keep_stems=False)
                    eng = r["engine"]
                    margins = [c.margin for c in r["player"].log]
                    late_n = sum(v["late"] for v in eng.counts.values())
                    drop_n = sum(v["dropped"] for v in eng.counts.values())
                    resp = eng.granted.get("response_ms", {})
                    row = {"case": name, "block": blk, "buffer_ms": buf, "thread": a.thread, "response_ms": resp,
                           "underruns": eng.underruns,
                           "underrun_ms": 1000 * eng.underrun_frames / RATE, "late": late_n, "dropped": drop_n,
                           "cues": len(r["player"].log), "min_margin_ms": 1000 * min(margins),
                           "engine_worst_ms": 1000 * max(eng.compute_s)}
                    rows.append(row)
                    print(f"{'thread ' if a.thread else ''}block {blk:4d} ({1000 * blk / RATE:4.1f} ms) buffer {buf:5.1f} ms {name:9s}: underruns "
                          f"{row['underruns']:3d} ({row['underrun_ms']:.1f} ms of silence), cues {row['cues']}, late "
                          f"{late_n}, dropped {drop_n}, least margin {row['min_margin_ms']:.1f} ms, engine's worst block "
                          f"{row['engine_worst_ms']:.2f} ms; response median {resp.get('median', 0):.2f} ms, p99.9 "
                          f"{resp.get('p99.9', 0):.2f}, max {resp.get('max', 0):.2f}", flush=True)
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / f"sweep{'-thread' if a.thread else ''}.json").write_text(json.dumps(rows, indent=1))
        return
    results = []
    for name in cases:
        cap = (a.out / f"{name}-capture.wav") if a.out else Path("/dev/null")
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
        r = replay(pj, name, fonts, block, buffer_ms, a.in_block, a.lead, cap if a.out else None, late,
                   cfg.band.gain_db, process=not a.thread, output=a.output, device=a.device or cfg.band.device,
                   period_ms=cfg.band.period_ms, rt_priority=cfg.band.rt_priority)
        off = offline(pj, r, fonts)
        if not a.out and a.output == "paced":
            raise SystemExit("give --out: the comparison reads the capture")
        res = compare(pj, r, off, a.out if a.output == "paced" else None, a.clip_s)
        print_result(res)
        results.append(res)
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / f"replay{'-' + a.output if a.output != 'paced' else ''}.json").write_text(
            json.dumps(results, indent=1, default=str))


def levels(pj: Project, fonts: list[Path]) -> None:
    """Each part's loudness on its own FluidSynth (unit gain) over the development takes' offline renders at 48 kHz,
    and the gains that set the parts as the offline render does (the bass at 0 dB)."""
    rows = {p: [] for p in pj.voicing.VOICE}
    for c in pj.rcs.CASES:
        if c.split != "dev":
            continue
        tk = pj.bst.take_at(c, RATE)
        logs = pj.B.run(tk.y, RATE, pj.bh.beats_for(tk, "live", RATE), pj.bh.chart_of(c), None, tk.bpb, tk.notch, 0)
        stems = pj.br.stems_for(pj.br.notes_for(logs, tk.spb), fonts[0].parent)
        line = []
        for part, x in stems.items():
            rows[part].append(pj.br.loudness(x))
            line.append(f"{part} {rows[part][-1]:.1f}")
        print(f"{c.name:14s} " + ", ".join(line) + " dBFS", flush=True)
    med = {p: float(np.median(v)) for p, v in rows.items() if v}
    gains = {p: pj.voicing.VOICE[p][3] - (med[p] - med["bass"]) for p in med}
    print("median: " + ", ".join(f"{p} {v:.1f}" for p, v in med.items()))
    print("PART_GAIN_DB = {" + ", ".join(f'"{p}": {v:.1f}' for p, v in gains.items()) + "}")


if __name__ == "__main__":
    main()
