"""Samples from takes: one extraction for every instrument, the instrument a parameter (2026-10-20).

    python3 tools/samples.py collect INSTRUMENT [--fresh] [--only FOLDER ...]
    python3 tools/samples.py report INSTRUMENT [--markdown]
    python3 tools/samples.py choose INSTRUMENT [--map PATH] [--all] [--notes E1 ...] [--chain "18i8, Nadine"]
    python3 tools/samples.py build INSTRUMENT [--map PATH] [--out PATH]
    tools/soundfonts                              # then: the fonts normalised for the Pi's Csound

INSTRUMENT is a profile (`PROFILES`): `upright` (the player's upright bass, every bass take: exercises/bass and
tunes/bass of the transcription project, the bowed ones as "arco") or `guitar` (the player's Martin D-1: guitar
exercises 001-003, single notes, and the three guitar tunes, strokes). Run with the Python that has the
transcription project's pipeline and librosa (this desktop's Miniconda `python3`); `--transcription DIR` (default
`~/play/dobro-transcription`). OPENBLAS_NUM_THREADS=2 when other jobs run.

The stages are the sound plan's (`docs/sound-plan.md`, "Extraction: from takes to samples"), each writing what it
found, so a sample's history is in a file:

1. **Find the notes** (`found`): a take with an answer key is transcribed as the transcription project's bench does
   it (`bench.transcribe_take`, the instrument's own path) and matched to its key (`evaluate`), each key note found
   at its pitch a candidate; a take with only a chord chart (the guitar's tunes) gives its strokes
   (`transcribe.strokes`), each labelled boom or chuck and by the chart's chord where it falls. The detector's
   onsets are kept as the take's onsets (where each note's ring ends). Cached per take (`--fresh` to redo).
2. **Label and check** (`measure`): the label is the key's (pitch, string, fret) or the chart's (the chord); then
   the detectors check it on the cut sample: the pitch by pYIN within 4 semitones of the label, refined from the
   partials (`partial_cents`), and the octave by the partials (`octave_doubt`); the string by its harmonic
   fingerprint (`transcribe.timbre`, against the same pitch on each string in the other takes); a boom's bass note
   a tone of the chart's chord, a chuck's chroma its chord's root (`transcribe.chords`; a single guitar note's
   stroke kind is kept, `stroke_kind`, not judged: single notes often read strum-like). And the sound: a clean
   start, long enough, the note before not still ringing (`ringing_db`), the backing or a voice in the room not
   heard at a bass's 1.5-6 kHz (`hf_db`), no clipping, no burst over the ring (`tick_db`). A candidate failing any
   is flagged (`flags`), not chosen; the thresholds are this file's constants, each with its evidence.
3. **Cut** (`cut`): from 3 ms before the attack (`find_attack`: a pick's 3-8 kHz click for a guitar, as the dobro
   build's `find_pick`; a finger's pluck by the level, as the upright build's) to 40 ms before the next onset, or
   where the player damped it, at most `max_s`, faded in over 2 ms and out over 120 ms. The exercise app's click
   is taken out of the take first where its sidecar names one (`transcribe.click.remove_clicks`), then any left
   over the note's ring is gated down to the sound around it (`gate_clicks`): through the old mixer the click was
   in the capture, as loud as a note (the upright's E1 and G2 of 2026-10-15 click on every note).
4. **Loop** (`find_loop`) only what sustains: a bowed note (none of the plucked ones), at matching phase and level.
5. **Level and tune**: every sample to one loudness over its first 300 ms (`level_rms`), its level as played kept
   in the map (`level_db`) for the dynamics to come; tuned by the sample's pitch correction, never resampled.
6. **Choose** (`choose`): per pitch, through the font's mic (`font_mic`: one instrument's sound in a preset), the
   candidates with no flag, the longest first, a take through the 18i8 preferred where it rings long enough (as the
   upright build did); the rest kept, for round robins, in the candidates file
   (`sounds/samples/INSTRUMENT-candidates.json`, in git: the takes' paths and times, no audio), so a choice can be
   changed by hand in the map. `--notes` chooses only those pitches, the map's others kept.
7. **Write** the map (`sounds/samples/INSTRUMENT.json`, in git): one entry per sample, its source (take, channel,
   cut, the clicks taken out), root, key range, velocity range, string, articulation, loop, tuning. The WAVs are cut
   from it into `~/.cache/ambient-room/samples/INSTRUMENT/` (out of git; `--wavs`), and `build` writes the SF2 from
   the map and the WAVs (re-cut where one is missing), then `tools/soundfonts` normalises it for the Pi's Csound.
   An entry marked `"pinned"` is kept by `choose` as it is (without `--all`): the upright's 2026-10-15 samples
   (`tools/upright_font.py`'s, retired) are pinned so, cut as they were, and built from them alone the font is
   that build's, byte for byte (the writer, `write_sf2`, writes what dobro-soundfont's `sf2write` wrote).

`report`: per articulation and chain, each pitch (or chord) in the profile's range: the candidates found, how many
are good, the best's length, why the others were not (by flag), and what is missing.

The player's takes are not for publication: a font built from them is for the unit, not for release, until the
player says.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parents[1]
SOUNDS = HERE / "sounds"
MAPS = SOUNDS / "samples"
CACHE = Path.home() / ".cache" / "ambient-room" / "samples"
TRANSCRIPTION = Path.home() / "play" / "dobro-transcription"
NAMES = "C C# D D# E F F# G G# A A# B".split()


def note_name(m: int) -> str:
    return f"{NAMES[m % 12]}{m // 12 - 1}"


# ---------------------------------------------------------------------------------------------------- the profiles

@dataclass(frozen=True)
class Profile:
    """One instrument's extraction: where its takes are, its range, how its attack is found and cut, its font."""
    name: str
    about: str
    folders: tuple[str, ...]  # globs under the transcription project
    lowest: int  # the range wanted (MIDI), for the report's "missing"
    highest: int
    font: str  # the SF2 written under sounds/
    font_name: str
    presets: dict  # articulation -> (preset name, bank, program)
    attack_band: tuple[float, float] | None  # a pick's click band (Hz); None: a finger's pluck, by the level
    attack_before: float  # where to look for the attack around the detector's onset (s)
    attack_after: float
    attack_within_db: float
    partials: tuple[int, ...]  # the partials the pitch is read from
    font_mic: str  # the font's samples come from this mic's chains only (one instrument's sound in a preset)
    extra_channels: dict = field(default_factory=dict)  # another pickup's file of a take -> its chain name
    arco: str | None = None  # a folder whose name holds this is bowed
    capo: dict = field(default_factory=dict)  # folder -> capo fret (the tune's README)
    min_contrast_db: float = 10.0  # a clean start: the 50-300 ms after it this much over the 10-60 ms before
    min_s: float = 0.5  # the shortest sample worth keeping
    min_s_by: dict = field(default_factory=dict)  # a stroke's kind -> its shortest (a chuck is short by nature)
    prefer: str = "18i8"  # a session whose name ends so is preferred where it rings `prefer_s`
    prefer_s: float = 1.2
    max_s: float = 4.0
    end_before_next_s: float = 0.04
    fade_in_s: float = 0.002
    fade_out_s: float = 0.12
    level_rms: float = 0.12  # every sample's first 300 ms
    release_s: float = 0.25


PROFILES = {
    "upright": Profile(
        name="upright", about="the player's upright bass (a New Standard Cleveland, Pirastro Perpetual Stark strings)",
        folders=("exercises/bass/*", "tunes/bass/*"), lowest=28, highest=55, font="upright.sf2",
        font_name="UprightBassPrototype",
        presets={"pizz": ("Upright bass (Cleveland)", 0, 32), "arco": ("Upright bass, bowed (Cleveland)", 0, 43)},
        # the 2026-10-15 build's pluck (`find_pluck`): the first 1.5 ms frame within 10 dB of the loudest in
        # [onset - 40 ms, onset + 80 ms]; a finger's pluck has little of a pick's 3-8 kHz click
        attack_band=None, attack_before=0.04, attack_after=0.08, attack_within_db=10.0,
        # through the Nadine the low strings' fundamentals are 25-35 dB under their octave (bass.py)
        partials=(2, 3, 4, 5, 6), font_mic="Nadine",
        extra_channels={"take-01-piezo.flac": "piezo"}, arco="arco"),
    "guitar": Profile(
        name="guitar", about="the player's Martin D-1, flatpicked",
        folders=("exercises/guitar/001-*", "exercises/guitar/002-*", "exercises/guitar/003-*", "tunes/guitar/*"),
        lowest=40, highest=76, font="d1.sf2", font_name="GuitarD1Prototype",
        presets={"note": ("Guitar notes (D-1)", 0, 25), "boom": ("Guitar booms (D-1)", 0, 25)},
        # the dobro build's `find_pick`: the first 1.5 ms frame where the 3-8 kHz click comes within 8 dB of its
        # loudest in [onset - 15 ms, onset + 90 ms]
        attack_band=(3000.0, 8000.0), attack_before=0.015, attack_after=0.09, attack_within_db=8.0,
        partials=(1, 2, 3, 4, 5, 6), font_mic="room mic", capo={"tunes/guitar/cherokee-shuffle": 2}, max_s=4.0,
        # a boom rings to its chuck, an eighth later (0.18 s at 170); a chuck is choked (the band's chop is 90 ms)
        min_s_by={"boom": 0.17, "chuck": 0.09}),
}

# the checks' thresholds (each from the takes in hand, 2026-10-20; findings, "The band's sounds")
TICK_DB = 12.0  # a burst over the ring: the 2-8 kHz band's 5 ms level this much over its own median nearby...
TICK_NOTE_DB = -35.0  # ...and no more than this under the note's first 300 ms (the old E1's burst: +2 dB)
BLEED_HZ = {"upright": 1000.0, "guitar": 3000.0}  # sound between the note's partials up to here: told, not a flag
# (a bass's body modes near 105 Hz ring between its low partials, 8-12 dB under them, in every take)
HF_BLEED_DB = {"upright": -40.0}  # a bass's ring at 1.5-6 kHz (after 150 ms) this near its first 300 ms: something
# else sounding (the backing in the room, a voice); the Nadine hears a bass's own top there 50-70 dB under it
RINGING_DB = -20.0  # the note before's own partials (those this note does not share) this near this note's
CLICK_LOUD_DB = 20.0  # a click on the attack this far over the 30 ms before it (the old mixer's: 22-47 dB)...
CLICK_DROP_DB = 15.0  # ...that its removal took less than this off, in its own tone band (under a pluck 17-20)
CLIP = 0.999


# ---------------------------------------------------------------------------------------------- the transcription

def pipeline(root: Path):
    """The transcription project's pipeline (its `pipeline/src` on the path)."""
    src = str(root / "pipeline" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import transcribe  # noqa: F401
    return transcribe


def soundfonts_module():
    """tools/soundfonts (no .py), for its SoundFont reader and writer's records."""
    loader = importlib.machinery.SourceFileLoader("soundfonts", str(HERE / "tools" / "soundfonts"))
    spec = importlib.util.spec_from_loader("soundfonts", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


@dataclass
class Take:
    """One take of a profile's folders, as its folder describes it."""
    folder: Path
    info: object  # evaluate.TakeInfo
    rel: str  # the take's path in the transcription project
    session: str
    chain: str  # what recorded it: "mixer, Nadine", "18i8, Nadine", "18i8, piezo", "18i8, room mic"
    articulation: str
    keyed: bool
    chart: Path | None
    channels: dict  # chain -> path (the take's own first)


def chain_of(session_row: dict, channel: str) -> str:
    """What recorded a channel: the interface (the session's recorder: the 18i8, or the old mixer) and the mic."""
    rec = session_row.get("recorder", "")
    via = "18i8" if "18i8" in rec else "mixer" if "mixer" in rec.lower() or "BOMGE" in rec else "recorder"
    return f"{via}, {channel}"


def takes_of(profile: Profile, root: Path, only: list[str] | None = None) -> list[Take]:
    pipeline(root)
    from transcribe.evaluate import read_sessions, read_takes
    from transcribe.score import take_key
    sessions = read_sessions(root / "exercises")  # the tunes' sessions are listed with the exercises'
    out = []
    for pattern in profile.folders:
        for d in sorted(root.glob(pattern)):
            rel_d = str(d.relative_to(root))
            if not (d / "takes.csv").exists() or (only and not any(rel_d.startswith(o.rstrip("/")) for o in only)):
                continue
            for t in read_takes(d):
                try:
                    keyed = take_key(d, t).exists()
                except (FileNotFoundError, ValueError):
                    keyed = False
                row = t.session or sessions.get(t.conditions.get("session", ""), {})
                if not row and sf.info(str(t.path)).subtype == "PCM_24":  # no session row: the 18i8's are 24-bit
                    row = {"recorder": "the exercise app through the 18i8 (a 24-bit take)"}
                own = "Nadine" if profile.name == "upright" else "room mic"
                channels = {chain_of(row, own): t.path}
                for name, chain in profile.extra_channels.items():
                    if (d / name).exists() and t.path.name == "take-01.flac":
                        channels[chain_of(row, chain)] = d / name
                art = "arco" if profile.arco and profile.arco in d.name else \
                    ("pizz" if profile.name == "upright" else "note" if keyed else "strokes")
                out.append(Take(d, t, str(t.path.relative_to(root)), t.conditions.get("session", ""),
                                next(iter(channels)), art, keyed, d / "chords.txt" if (d / "chords.txt").exists() else None,
                                channels))
    return out


def take_hash(path: Path) -> str:
    st = path.stat()
    return hashlib.sha1(f"{path}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()[:12]


def found(profile: Profile, take: Take, cache: Path, fresh: bool = False) -> dict:
    """Stage 1: the take's notes and onsets. A keyed take: the bench's transcription matched to its key, each key
    note found at its pitch ({onset, midi, string, fret, attack, technique, beats}); a chart's take (the guitar's
    tunes): every stroke ({onset, kind, bass_midi}). Cached by the take's path, size and time."""
    path = cache / "found" / (take.rel.replace("/", "__") + f".{take_hash(take.info.path)}.json")
    if path.exists() and not fresh:
        return json.loads(path.read_text())
    from transcribe.bench import transcribe_take
    from transcribe.evaluate import evaluate
    if take.keyed:
        reference, meta, tr = transcribe_take(take.folder, take.info)
        res = evaluate(reference, tr.detected, take.info.beat0_s, take.info.bpm)
        order = sorted(reference, key=lambda e: e.onset_beats)
        prev = {}
        for i, e in enumerate(order):
            before = [q for q in order[:i] if q.onset_beats < e.onset_beats]
            prev[id(e)] = before[-1].midi if before else None
        notes = [dict(onset=float(dn.onset_s), midi=int(r.midi), string=int(r.string), fret=int(r.fret),
                      attack=bool(r.attack), technique=r.technique, beats=float(r.duration_beats),
                      at_beat=float(r.onset_beats), detected=int(dn.midi), prev_midi=prev[id(r)])
                 for r, dn in res.matches]
        wrong = [dict(onset=float(dn.onset_s), midi=int(r.midi), detected=int(dn.midi), string=int(r.string),
                      fret=int(r.fret)) for r, dn in res.wrong_pitch]
        onsets = sorted(float(n.onset_s) for n in tr.detected)
        out = dict(kind="keyed", notes=notes, wrong_pitch=wrong, onsets=onsets, missed=len(res.missed),
                   extra=len(res.extra), key_notes=len(reference))
    elif profile.name == "upright":
        from transcribe.detect import load
        from transcribe.transcribe import transcribe
        tr = transcribe(load(take.info.path), take.info.bpm, instrument="bass",
                        beats_per_bar=int(take.info.conditions.get("beats_per_bar") or 4))
        notes = [dict(onset=float(n.onset_s), midi=int(n.midi), attack=bool(n.attack), detected=int(n.midi),
                      labelled_by="detector") for n in tr.detected]
        out = dict(kind="detector", notes=notes, onsets=sorted(n["onset"] for n in notes))
    else:
        from transcribe.strokes import detect_strokes
        y, sr = sf.read(take.info.path, always_2d=True)
        st = detect_strokes(y[:, 0], sr)
        notes = [dict(onset=float(s.time_s), kind=s.kind(), bass_midi=s.bass_midi, strength=float(s.strength),
                      low_only=bool(s.low_only), rise_db=float(s.rise_low_db if s.kind() == "boom" else s.rise_high_db))
                 for s in st]
        out = dict(kind="strokes", notes=notes, onsets=sorted(n["onset"] for n in notes))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


# --------------------------------------------------------------------------------------------------- the chart

def chart_at(take: Take, root: Path):
    """A function: time (s) -> (chord symbol, s to the nearest chord change) by the take's chart, or None outside it.
    The grid: the folder's beats.csv where it has one, else takes.csv's downbeat and tempo (`chords.take_grid`)."""
    if take.chart is None:
        return None
    from transcribe.chords import read_chords, take_grid
    chart = read_chords(take.chart)
    bars = [chart[k] for k in chart]  # in the file's order: bar 1 first
    beats = []
    if (take.folder / "beats.csv").exists():
        import csv
        rows = list(csv.DictReader(open(take.folder / "beats.csv")))
        beats = [(int(r["bar"]), int(r["beat"]), float(r["time_s"])) for r in rows]
    else:
        g = take_grid(take.info.path)
        if not g:
            return None
        spb = 60.0 / g["bpm"]
        bpb = g["beats_per_bar"] or len(bars[0])
        for b, syms in enumerate(bars):
            for k in range(len(syms)):
                beats.append((b + 1, k + 1, g["downbeat_s"] + (b * bpb + k) * spb))
    times = np.array([t for _, _, t in beats])
    syms = [bars[b - 1][k - 1] if b - 1 < len(bars) and k - 1 < len(bars[b - 1]) else None for b, k, _ in beats]
    changes = np.array([times[i] for i in range(1, len(syms)) if syms[i] != syms[i - 1]])
    period = float(np.median(np.diff(times))) if len(times) > 1 else 1.0

    def at(t: float):
        i = int(np.searchsorted(times, t + 0.03)) - 1  # a stroke a hair early belongs to its beat
        if i < 0 or t > times[-1] + period or syms[i] is None:
            return None
        near = float(np.min(np.abs(changes - t))) if len(changes) else 9.9
        return syms[i], near
    return at


# --------------------------------------------------------------------------------------------- measuring a note

def find_attack(y: np.ndarray, sr: int, onset: float, band, before: float, after: float, within_db: float) -> float:
    """The attack near a detected onset (s). With a band (a pick's click, 3-8 kHz): the first 1.5 ms frame where
    that band comes within `within_db` of its loudest in [onset - before, onset + after] (dobro-soundfont
    `tools/build.py`, `find_pick`: the sharpest jump is fooled by small sounds before the pick). Without (a finger's
    pluck): the first 1.5 ms frame whose level comes within `within_db` of the loudest there (the upright build's
    `find_pluck`)."""
    hop = int(round(0.0015 * sr))
    if band is None:
        a = max(0, int((onset - before) * sr))
        x = y[a:int((onset + after) * sr)]
        n = len(x) // hop
        db = 10 * np.log10(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
        k = int(np.nonzero(db >= db.max() - within_db)[0][0])
        return a / sr + k * hop / sr
    import librosa
    a = max(0, int((onset - before - 0.01) * sr))
    x = y[a:int((onset + after + 0.01) * sr)]
    Y = np.abs(librosa.stft(x, n_fft=256, hop_length=hop, center=False)) ** 2
    f = librosa.fft_frequencies(sr=sr, n_fft=256)
    env = 10 * np.log10(Y[(f > band[0]) & (f < band[1])].sum(axis=0) + 1e-12)
    t = a / sr + np.arange(len(env)) * hop / sr
    inside = (t + 128 / sr >= onset - before) & (t + 128 / sr <= onset + after)
    peak = env[inside].max()
    return float(t[np.nonzero(inside & (env >= peak - within_db))[0][0]])


def rms_db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(np.asarray(x, dtype=float) ** 2) + 1e-20))


def band(x: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt
    return sosfiltfilt(butter(4, [lo, min(hi, 0.45 * sr)], btype="band", fs=sr, output="sos"), x)


def frames_db(x: np.ndarray, sr: int, frame_s: float) -> np.ndarray:
    n = max(1, int(round(frame_s * sr)))
    k = len(x) // n
    return 10 * np.log10(np.mean(x[:k * n].reshape(k, n) ** 2, axis=1) + 1e-20) if k else np.zeros(0)


def damped_at(x: np.ndarray, sr: int, after_s: float = 0.15, drop_db: float = 15.0, within_s: float = 0.1):
    """Where the player stopped the note (s into x): the first 10 ms frame after `after_s` from which the level
    falls `drop_db` within `within_s`; a plucked string rings down by 10-20 dB a second. None: it rang on."""
    env = frames_db(x, sr, 0.01)
    w = int(round(within_s / 0.01))
    for i in range(int(after_s / 0.01), len(env) - w):
        if env[i + w] < env[i] - drop_db and env[i] > env.max() - 50:
            return i * 0.01
    return None


def partial_cents(x: np.ndarray, sr: int, m: int, partials=(2, 3, 4, 5, 6)) -> float | None:
    """The note's pitch in cents from m: the median of its partials, each found within 60 cents of where it should
    be (peak-interpolated, over its own number); None with fewer than three (the upright build's, its partials a
    parameter)."""
    import librosa
    nfft = 1 << 18
    mag = np.abs(np.fft.rfft(x * np.hanning(len(x)), nfft))
    hz, f0 = sr / nfft, librosa.midi_to_hz(m)
    est = []
    for h in partials:
        lo, hi = int(h * f0 * 2 ** (-0.6 / 12) / hz), int(h * f0 * 2 ** (0.6 / 12) / hz)
        if hi >= len(mag) - 1:
            break
        k = lo + int(np.argmax(mag[lo:hi]))
        if lo < k < hi - 1:
            a, b, c = np.log(mag[k - 1:k + 2] + 1e-12)
            p = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else 0.0
            est.append(1200 * np.log2((k + p) * hz / h / f0))
    return float(np.median(est)) if len(est) >= 3 else None


def partial_levels(x: np.ndarray, sr: int, f0: float, hs) -> np.ndarray:
    """dB of the strongest bin within 2% of each h f0 (h may be fractional)."""
    nfft = 1 << int(np.ceil(np.log2(max(len(x), 4 * sr / f0)) + 1))
    mag = np.abs(np.fft.rfft(x * np.hanning(len(x)), nfft))
    hz = sr / nfft
    out = []
    for h in hs:
        lo, hi = int(h * f0 * 0.98 / hz), int(h * f0 * 1.02 / hz) + 1
        out.append(20 * np.log10(mag[lo:hi].max() + 1e-12) if hi < len(mag) else -240.0)
    return np.array(out)


def octave_doubt(x: np.ndarray, sr: int, f0: float) -> str | None:
    """An octave the label may have wrong, from the partials: "up" when its odd partials (3rd, 5th) stand 20 dB or
    more under its even ones (2nd, 4th, 6th: the note an octave higher); "down" when the partials an octave lower
    would add (1.5, 2.5 and 3.5 f0) stand, by their median, within 10 dB of the label's own 2nd, 3rd and 4th (all
    three: an open string a fifth below, ringing on, puts its 2nd partial at 1.5 f0 alone). None: no doubt."""
    lv = partial_levels(x, sr, f0, [2, 3, 4, 5, 6, 1.5, 2.5, 3.5])
    odd, even = np.mean(lv[[1, 3]]), np.mean(lv[[0, 2, 4]])
    if odd < even - 20:
        return "up"
    if np.median(lv[[5, 6, 7]]) > np.median(lv[[0, 1, 2]]) - 10:
        return "down"
    return None


def pyin_midi(x: np.ndarray, sr: int, m: int) -> float | None:
    """pYIN's median pitch (fractional MIDI) within 4 semitones of m, over the voiced frames; None if few."""
    import librosa
    rate = 16000
    z = librosa.resample(np.asarray(x, dtype=float), orig_sr=sr, target_sr=rate)
    frame = 2048 if m < 40 else 1024  # 5 periods of E1, of E2
    hop = 256 if len(z) > frame + 8 * 256 else 64  # a boom before its chuck: 0.17-0.35 s
    if len(z) < frame + 5 * hop:
        return None
    f0, voiced, _ = librosa.pyin(z, fmin=librosa.midi_to_hz(m - 4), fmax=librosa.midi_to_hz(m + 4), sr=rate,
                                 frame_length=frame, hop_length=hop)
    if voiced.sum() < 5:
        return None
    return float(librosa.hz_to_midi(np.median(f0[voiced])))


def bleed_db(x: np.ndarray, sr: int, f0: float, top_hz: float) -> float:
    """Sound between the note's partials against the partials' own, dB (30 Hz to `top_hz`): each partial the
    strongest peak within 2.5% of h f0 and the bins within max(2 Hz, 0.6%) of it. Another note ringing, the backing
    through the room, a voice: all between. A note alone in a quiet room reads -20 dB or under."""
    nfft = 1 << int(np.ceil(np.log2(len(x))) + 1)
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)), nfft)) ** 2
    hz = sr / nfft
    f = np.arange(len(p)) * hz
    use = (f >= 30) & (f <= top_hz)
    inside = np.zeros(len(p), dtype=bool)
    h = 1
    while h * f0 * 0.975 < top_hz:
        lo, hi = int(h * f0 * 0.975 / hz), int(h * f0 * 1.025 / hz) + 1
        k = lo + int(np.argmax(p[lo:hi]))
        w = max(2.0, 0.006 * k * hz) / hz
        inside[max(0, int(k - w)):int(k + w) + 1] = True
        h += 1
    a, b = p[use & inside].sum(), p[use & ~inside].sum()
    return float(10 * np.log10((b + 1e-20) / (a + 1e-20)))


def ringing_db(x: np.ndarray, sr: int, f0: float, prev_f0: float) -> float:
    """The note before still sounding: its own partials 2-8 (those not within 3% of one of this note's) against this
    note's partials 2-8, the strongest of each, dB."""
    mine = partial_levels(x, sr, f0, range(2, 9))
    hs = [h for h in range(2, 9) if all(abs(h * prev_f0 / (k * f0) - 1) > 0.03 for k in range(1, 40))]
    if not hs:
        return -99.0
    return float(partial_levels(x, sr, prev_f0, hs).max() - mine.max())


def tick_db(x: np.ndarray, sr: int, start_s: float = 0.04, end_s: float | None = None,
            floor_db: float | None = None) -> tuple[float, float]:
    """The worst burst over a note's ring: the 2-8 kHz band's 5 ms level (dB) over its own median within 60 ms
    either side (the 10 ms around it left out), from `start_s` on, and where it is (s). A decaying note's top falls
    smoothly; a click, a string touched, a backing's attack stand out of it. With `floor_db`, a frame under it (dB,
    as `rms_db`) does not count: too quiet to hear against the note."""
    e = frames_db(band(x, sr, 2000, 8000), sr, 0.005)
    end = len(e) if end_s is None else min(len(e), int(end_s / 0.005))
    best, where = -99.0, 0.0
    for i in range(int(start_s / 0.005), end):
        near = np.r_[e[max(0, i - 12):max(0, i - 2)], e[i + 3:i + 13]]
        if len(near) < 6 or (floor_db is not None and e[i] < floor_db):
            continue
        d = e[i] - float(np.median(near))
        if d > best:
            best, where = d, i * 0.005
    return float(best), float(where)


# ------------------------------------------------------------------------------------------------- the cut

@dataclass(frozen=True)
class Cut:
    """How a sample is cut from its take (samples at the take's rate)."""
    start: int
    end: int
    fade_in: int
    fade_out: int
    declick: bool  # the app's clicks taken out of the take first
    gate: tuple[int, ...] = ()  # clicks (samples into the cut) left over the ring, gated to the sound around


_audio: dict = {}


def take_audio(path: Path) -> tuple[np.ndarray, int]:
    key = str(path)
    if key not in _audio:
        y, sr = sf.read(str(path), always_2d=True)
        _audio.clear()  # one take at a time
        _audio[key] = (y[:, 0].astype(float), sr)
    return _audio[key]


_declicked: dict = {}


def declicked(take: Take, path: Path, root: Path) -> tuple[np.ndarray, int, list]:
    """The take's channel with the app's clicks taken out (`transcribe.click.remove_clicks`; the template from the
    clicks before the first note), and each removal; as recorded where the sidecar names no click."""
    key = str(path)
    if key in _declicked:
        return _declicked[key]
    pipeline(root)
    from transcribe.click import click_samples, remove_clicks, sidecar
    y, sr = take_audio(path)
    side = sidecar(take.folder, take.info)
    at, acc = click_samples(side, sr, len(y)) if side else (np.zeros(0, int), np.zeros(0, bool))
    if len(at):
        out, removed = remove_clicks(y, sr, at, acc, quiet_until_s=take.info.beat0_s - 0.1)
    else:
        out, removed = y, []
    _declicked.clear()
    _declicked[key] = (out, sr, removed)
    return _declicked[key]


def gate_clicks(x: np.ndarray, sr: int, at: tuple[int, ...], lo_hz: float = 700.0, span_s: float = 0.04,
                ramp_s: float = 0.005) -> np.ndarray:
    """A click left over the ring taken down: above `lo_hz` (a bass note's ring has little there after its first
    50 ms), from 2 ms before each click to `span_s` after, the band scaled to its level over the 30 ms before, with
    `ramp_s` ramps. Below `lo_hz` the note is untouched (the split is exact: low = x less the band)."""
    if not at:
        return x
    hi = band(x, sr, lo_hz, 0.45 * sr)
    low = x - hi
    g = np.ones(len(x))
    r = max(1, int(ramp_s * sr))
    for i in at:
        a, b = i - int(0.002 * sr), i + int(span_s * sr)
        if a - int(0.03 * sr) < 0 or b + r >= len(x):
            continue
        ref = rms_db(hi[a - int(0.03 * sr):a])
        now = rms_db(hi[a:b])
        k = min(1.0, 10 ** ((ref - now) / 20))
        w = np.ones(b - a + 2 * r) * k
        w[:r] = np.linspace(1, k, r)
        w[-r:] = np.linspace(k, 1, r)
        g[a - r:b + r] = np.minimum(g[a - r:b + r], w)
    return low + hi * g


def cut_audio(y: np.ndarray, sr: int, cut: Cut) -> np.ndarray:
    """The sample as cut: the span, its clicks gated, faded in and out (before any level)."""
    x = y[cut.start:cut.end].copy()
    if cut.gate:
        x = gate_clicks(x, sr, cut.gate)
    a, b = min(cut.fade_in, len(x) // 4), min(cut.fade_out, len(x) // 2)
    x[:a] *= np.linspace(0, 1, a)
    x[len(x) - b:] *= np.linspace(1, 0, b)
    return x


def leveled(x: np.ndarray, sr: int, level_rms: float) -> np.ndarray:
    """To `level_rms` over its first 300 ms, its peak kept under 0.98 (the upright build's order of operations)."""
    x = x * (level_rms / (np.sqrt(np.mean(x[:int(0.3 * sr)] ** 2)) + 1e-9))
    return x / max(1.0, np.abs(x).max() / 0.98)


# ------------------------------------------------------------------------------------------------- the loop

def find_loop(x: np.ndarray, sr: int, f0: float, start_s: float = 0.3, min_s: float = 0.3, xfade_s: float = 0.02):
    """Loop points (samples) in a sustained note: the end near the end of its sustain, the start a whole number of
    periods earlier, at least `min_s` before it and after `start_s`, where the 20 ms before each matches best
    (normalised correlation), the levels within 1.5 dB; then the 20 ms before the end crossfaded from the 20 ms
    before the start, so the seam is the same sound. Returns (x with the crossfade, start, end, match) or None when
    the note does not sustain (no pair matching 0.9 or better)."""
    period = sr / f0
    n = int(xfade_s * sr)
    le0 = len(x) - int(0.15 * sr)
    if le0 - int(min_s * sr) < int(start_s * sr) + n:
        return None
    best = None
    for le in range(le0, le0 - int(0.1 * sr), -max(1, int(period / 4))):
        tail = x[le - n:le]
        lev_t = rms_db(tail)
        k_max = int((le - int(start_s * sr) - n) / period)
        k_min = int(np.ceil(min_s * sr / period))
        for k in range(k_min, k_max + 1):
            ls = int(round(le - k * period))
            head = x[ls - n:ls]
            if abs(rms_db(head) - lev_t) > 1.5:
                continue
            c = float(np.dot(head, tail) / (np.linalg.norm(head) * np.linalg.norm(tail) + 1e-20))
            if best is None or c > best[0]:
                best = (c, ls, le)
    if best is None or best[0] < 0.9:
        return None
    c, ls, le = best
    out = x.copy()
    w = np.linspace(0, 1, n)
    out[le - n:le] = (1 - w) * x[le - n:le] + w * x[ls - n:ls]
    return out, ls, le, c


# --------------------------------------------------------------------------------------------- the candidates

def measure(profile: Profile, take: Take, chain: str, path: Path, note: dict, onsets: list[float], root: Path,
            chart=None) -> dict:
    """Stage 2-3 for one found note: its attack, cut, and every check on the cut sample."""
    import librosa
    y, sr, removed = declicked(take, path, root)
    raw, _ = take_audio(path)
    t = note["onset"]
    bowed = take.articulation == "arco"
    attack = t - 0.02 if bowed else find_attack(y, sr, t, profile.attack_band, profile.attack_before,
                                                 profile.attack_after, profile.attack_within_db)
    later = [o for o in onsets if o > t + 0.05]
    nxt = min(later) if later else len(y) / sr
    start = max(int((attack - 0.003) * sr), 0)
    end = int(min(nxt - profile.end_before_next_s, attack + profile.max_s) * sr)
    pre = y[max(0, int((t - 0.06) * sr)):max(1, int((t - 0.01) * sr))]
    post = y[int((t + 0.05) * sr):max(int((t + 0.06) * sr), int(min(t + 0.3, nxt - 0.01) * sr))]
    contrast = rms_db(post) - rms_db(pre)
    if note.get("rise_db") is not None:  # a stroke: how much its own band rose (`strokes`: a boom's low strings,
        contrast = note["rise_db"]       # a chuck's top), not the level, which the boom before still holds up
    span = y[start:max(end, start + int(0.1 * sr))]
    damp = damped_at(span, sr)
    ending = "cut by the next note" if later else "the take's end"
    if damp is not None:
        end = min(end, start + int((damp + 0.08) * sr))
        ending = "damped"
    elif nxt - attack > profile.max_s:
        ending = "rang on"
    # the clicks left over this note's ring, after the take's removal (30 ms after the attack on)
    gate, clicks = [], []
    for r in removed:
        if start - int(0.005 * sr) <= r.at < end:
            off = (r.at - start) / sr
            left = r.after_db - r.around_db
            clicks.append(dict(ms=round(1000 * off), accent=r.accent, before_db=round(r.before_db - r.around_db, 1),
                               left_db=round(left, 1), drop_db=r.drop_db))
            if off > 0.03:
                gate.append(r.at - start)
    m = int(note.get("midi") or note.get("bass_midi") or 0)
    # the fade out at most a third of a short sample (a chuck is choked within 0.1-0.2 s)
    cut = Cut(start, end, int(profile.fade_in_s * sr), min(int(profile.fade_out_s * sr), max(1, (end - start) // 3)),
              declick=bool(removed), gate=tuple(gate))
    length = (end - start) / sr
    row = dict(take=take.rel, chain=chain, channel=str(path.relative_to(root)), session=take.session,
               articulation=take.articulation, onset=round(t, 4), attack_ms=round(1000 * (attack - t), 1),
               length=round(length, 3), ring_to_next=round(nxt - attack, 3), ending=ending,
               contrast_db=round(contrast, 1), clicks=clicks,
               cut=dict(start=cut.start, end=cut.end, fade_in=cut.fade_in, fade_out=cut.fade_out,
                        declick=cut.declick, gate=list(cut.gate)), rate=sr)
    for k in ("midi", "string", "fret", "technique", "beats", "at_beat", "kind", "bass_midi"):
        if k in note and note[k] is not None:
            row[k] = note[k]
    if str(take.folder.relative_to(root)) in profile.capo:
        row["capo"] = profile.capo[str(take.folder.relative_to(root))]
    if chart is not None:
        c = chart(attack)
        if c:
            row["chord"], row["from_change_s"] = c[0], round(c[1], 3)
    flags = []
    min_s = profile.min_s_by.get(note.get("kind", ""), profile.min_s)
    if length < min(0.15, min_s):
        row["flags"] = ["short"]
        return row
    x = cut_audio(y, sr, cut)
    peak_raw = float(np.abs(raw[start:end]).max())
    row["level_db"] = round(rms_db(x[:int(0.3 * sr)]), 1)
    row["peak_db"] = round(20 * np.log10(peak_raw + 1e-12), 1)
    if peak_raw >= CLIP:
        flags.append("clipped")
    if contrast < profile.min_contrast_db and not bowed:
        flags.append("dirty start")
    if length < min_s:
        flags.append("short")
    audible = row["level_db"] + TICK_NOTE_DB
    td, tw = tick_db(x, sr, 0.04, length - profile.fade_out_s, audible)
    while td > TICK_DB and tw > 0.5 * length and tw - 0.03 >= min_s:
        # a sound late in the ring (the hand coming to the string for the next note, a thump): the cut ends before it
        end = start + int((tw - 0.03) * sr)
        cut = replace(cut, end=end, gate=tuple(g for g in cut.gate if g < end - start))
        length = (end - start) / sr
        row.update(length=round(length, 3), ending="before a sound late in the ring",
                   cut=dict(row["cut"], end=end, gate=list(cut.gate)))
        x = cut_audio(y, sr, cut)
        td, tw = tick_db(x, sr, 0.04, length - profile.fade_out_s, audible)
    row["tick_db"], row["tick_ms"] = round(td, 1), round(1000 * tw)
    if td > TICK_DB:
        flags.append("tick")
    if any(c["ms"] <= 30 and c["before_db"] > CLICK_LOUD_DB and c["drop_db"] < CLICK_DROP_DB for c in clicks):
        flags.append("click on the attack")
    if m:
        a0 = 0.1 if length > 0.5 else 0.03  # a short note (a boom before its chuck) read from 30 ms
        seg = x[int(a0 * sr):int(min(len(x), 1.2 * sr))]
        if len(seg) > int(0.1 * sr):
            pm = pyin_midi(seg, sr, m)
            cents = partial_cents(leveled(x, sr, profile.level_rms)[int(a0 * sr):int(min(len(x), 1.2 * sr))], sr, m,
                                  profile.partials)
            row["pyin_midi"] = round(pm, 2) if pm is not None else None
            row["cents"] = round(cents, 1) if cents is not None else None
            f0 = librosa.midi_to_hz(m) * 2 ** ((cents or 0.0) / 1200)
            od = octave_doubt(seg, sr, f0)
            if od == "down" and note.get("kind") == "boom":
                od = None  # in a strum the chord's fifth stands at 1.5 f0 and its octave at 2 f0: no test
            row["octave_doubt"] = od
            row["between_db"] = round(bleed_db(seg, sr, f0, BLEED_HZ.get(profile.name, 2000.0)), 1)
            if note.get("kind") == "boom":  # pYIN hears no one period in a strum's ringing strings: the partials
                wrong = (pm is not None and abs(pm - m) > 0.5) or cents is None or abs(cents) > 35 or od
            else:
                wrong = pm is None or abs(pm - m) > 0.5 or od or (cents is not None and abs(cents) > 35)
            if wrong:
                flags.append("off pitch")
            if note.get("prev_midi") and note["prev_midi"] != m:
                row["ringing_db"] = round(ringing_db(seg, sr, f0, librosa.midi_to_hz(note["prev_midi"])), 1)
                if row["ringing_db"] > RINGING_DB:
                    flags.append("another note ringing")
            if profile.name in HF_BLEED_DB and not bowed:  # a bow's own noise is up there
                tail = x[int(0.15 * sr):max(int(0.15 * sr) + 1, len(x) - cut.fade_out)]
                row["hf_db"] = round(rms_db(band(tail, sr, 1500, 6000)) - rms_db(x[:int(0.3 * sr)]), 1) \
                    if len(tail) > int(0.1 * sr) else None
                if row["hf_db"] is not None and row["hf_db"] > HF_BLEED_DB[profile.name]:
                    flags.append("bleed")
            if bowed:
                lp = find_loop(leveled(x, sr, profile.level_rms), sr, f0)
                if lp is None:
                    flags.append("no loop")
                else:
                    row["loop"] = dict(start=lp[1], end=lp[2], xfade=int(0.02 * sr), match=round(lp[3], 3))
    elif note.get("kind") == "boom":
        flags.append("no pitch")  # `strokes` read no bass note in it
    row["flags"] = flags
    return row


def label_flags(profile: Profile, rows: list[dict]) -> None:
    """The checks that need every candidate: a note's string against the same pitch on each string in the other
    takes through the same chain (`transcribe.timbre`), where the pitch was played on two strings."""
    from transcribe.timbre import StringModel
    # strings: leave one take out
    fps = [(r, np.array(r["fingerprint"])) for r in rows if r.get("fingerprint") is not None and "string" in r]
    for r, fp in fps:
        others = [(q, f) for q, f in fps if q["take"] != r["take"] and q["chain"] == r["chain"]
                  and q["articulation"] == r["articulation"]]
        groups = defaultdict(list)
        for q, f in others:
            groups[(q["midi"], q["string"])].append(f)
        means = {k: np.mean(v, axis=0) for k, v in groups.items()}
        if len({s for (mm, s) in means if mm == r["midi"]}) < 2:
            r["string_check"] = None
            continue
        dists = [np.sqrt(np.mean((f - means[(q["midi"], q["string"])]) ** 2)) for q, f in others]
        model = StringModel(means, float(np.median(dists)) if dists else 1.0)
        costs = model.costs(fp, r["midi"])
        if not costs:
            r["string_check"] = None
            continue
        best = min(costs, key=costs.get)
        r["string_check"] = int(best)
        if best != r["string"] and costs.get(r["string"], 9) > 1.0:
            r["flags"].append("string?")
    for r in rows:
        r.pop("fingerprint", None)


def strokes_near(take: Take, path: Path, root: Path, t: float):
    """The stroke (`transcribe.strokes`) within 30 ms of t on the declicked take: (kind, bass_midi), or None."""
    key = ("strokes", str(path))
    if key not in _declicked:
        from transcribe.strokes import detect_strokes
        y, sr, _ = declicked(take, path, root)
        st = detect_strokes(y, sr)
        _declicked[key] = st
    st = _declicked[key]
    near = [s for s in st if abs(s.time_s - t) <= 0.03]
    if not near:
        return None
    s = min(near, key=lambda s: abs(s.time_s - t))
    return s.kind(), s.bass_midi


def chuck_chord(y: np.ndarray, sr: int, attack: float, chord: str, root: Path) -> tuple[float, str]:
    """A chuck's chroma (its first 120 ms, explained as notes: `chords.segment_evidence`) against the chord
    templates (`chords.chord_fit`): the fit of the chart's chord, and the best chord's name."""
    import librosa
    from transcribe.chords import CHORDS, ChromaParams, chord_fit, parse_chord, segment_evidence, take_spectrum
    from transcribe.detect import SR
    a, b = int(max(0, attack - 0.05) * sr), int((attack + 0.15) * sr)
    z = librosa.resample(y[a:b], orig_sr=sr, target_sr=SR)
    p = ChromaParams(floor_pct=0.0, hop=256)
    C, times, _ = take_spectrum(z, p)
    t0 = attack - max(0, attack - 0.05)
    seg = segment_evidence(C, None, times, np.array([t0 + 0.01, t0 + 0.13]), p)
    S = chord_fit(seg, [False])[0][:-1]
    pc, rest = parse_chord(chord)
    q = "min" if rest.startswith("m") and not rest.startswith("maj") else ("7" if rest == "7" else "maj")
    want = [i for i, (r, qq) in enumerate(CHORDS) if r == pc and qq == q] or \
           [i for i, (r, qq) in enumerate(CHORDS) if r == pc]
    best = int(np.argmax(S))
    r, qq = CHORDS[best]
    return float(S[want[0]] - S[best]) if want else -1.0, f"{NAMES[r]}{'' if qq == 'maj' else qq}"


def collect(profile: Profile, root: Path, cache: Path, only=None, fresh: bool = False) -> list[dict]:
    """Stages 1-3 over every take of the profile: every candidate, its labels, cut and checks."""
    pipeline(root)
    from transcribe.detect import load
    from transcribe.timbre import Spectrum
    rows = []
    for take in takes_of(profile, root, only):
        f = found(profile, take, cache, fresh)
        chart = chart_at(take, root)
        what = {"keyed": "key notes found", "strokes": "strokes", "detector": "notes found (no key)"}[f["kind"]]
        print(f"{take.rel} ({take.session}, {take.articulation}): {len(f['notes'])} {what}", flush=True)
        for chain, path in take.channels.items():
            spec = Spectrum(load(path)) if f["kind"] == "keyed" else None
            print(f"  {chain}: {path.name}", flush=True)
            for n in f["notes"]:
                if f["kind"] != "strokes" and not n.get("attack", True):
                    continue  # a slid or hammered note: no attack of its own to sample
                if f["kind"] == "strokes":
                    n = dict(n)
                    if n["kind"] == "boom" and n.get("bass_midi"):
                        n["midi"] = n["bass_midi"]
                r = measure(profile, take, chain, path, n, f["onsets"], root, chart)
                art = take.articulation
                if f["kind"] == "strokes":
                    art = r["articulation"] = n["kind"]
                    if art == "boom" and r.get("chord") and "midi" in r:
                        from transcribe.chords import parse_chord
                        pc = parse_chord(r["chord"])[0]
                        r["chord_tone"] = {0: "root", 7: "fifth", 3: "third", 4: "third"}.get((r["midi"] - pc) % 12,
                                                                                             "other")
                        if r["chord_tone"] == "other":
                            r["flags"].append("not the chord's")
                    if art == "chuck":
                        r.pop("midi", None)
                        for k in ("pyin_midi", "cents", "octave_doubt", "bleed_db"):
                            r.pop(k, None)
                        r["flags"] = [g for g in r["flags"] if g not in ("off pitch", "bleed")]
                        if r.get("chord"):
                            y, sr, _ = declicked(take, path, root)
                            fit, heard = chuck_chord(y, sr, n["onset"] + r["attack_ms"] / 1000, r["chord"], root)
                            r["chord_fit"], r["chord_heard"] = round(fit, 3), heard
                            from transcribe.chords import parse_chord
                            if fit < -0.05 and parse_chord(heard)[0] != parse_chord(r["chord"])[0]:
                                r["flags"].append("chord?")  # another root (G read as G7: its 7th partial)
                    if r.get("from_change_s") is not None and r["from_change_s"] < 0.06:
                        r["flags"].append("at a change")
                    if not r.get("chord"):
                        r["flags"].append("no chart here")
                elif profile.name == "guitar" and r.get("midi", 99) <= 50:
                    k = strokes_near(take, path, root, n["onset"] + r["attack_ms"] / 1000)
                    r["stroke_kind"] = k[0] if k else None
                if spec is not None and "midi" in r and "string" in r:
                    r["fingerprint"] = [float(v) for v in spec.fingerprint(n["onset"], r["midi"])]
                if f["kind"] == "detector":
                    r["labelled_by"] = "detector"
                    r["flags"].append("no key")
                r["articulation"] = art
                r["id"] = f"{r['channel'].rsplit('.', 1)[0]}@{int(round(1000 * n['onset']))}"
                rows.append(r)
    label_flags(profile, rows)
    return rows


# ----------------------------------------------------------------------------------------------- choosing

def slot_of(r: dict) -> tuple:
    if r["articulation"] == "chuck":
        return (r["articulation"], r["chain"], r.get("chord") or "?", r.get("capo", 0))
    return (r["articulation"], r["chain"], r.get("midi", 0))


def rank(profile: Profile, rows: list[dict]) -> list[dict]:
    """A slot's good candidates, best first: a take through the preferred chain (`prefer`, the newest and cleanest)
    where it rings `prefer_s` or more, then by length."""
    good = [r for r in rows if not r["flags"]]
    return sorted(good, key=lambda r: (r["session"].endswith(profile.prefer) and r["length"] >= profile.prefer_s,
                                       r["length"]), reverse=True)


def key_ranges(roots: list[int]) -> list[tuple[int, int]]:
    """Each sampled pitch covers the keys halfway to its neighbours (the lowest from 0, the highest to 127)."""
    out = []
    for i, m in enumerate(roots):
        lo = 0 if i == 0 else (roots[i - 1] + m) // 2 + 1
        hi = 127 if i == len(roots) - 1 else (m + roots[i + 1]) // 2
        out.append((lo, hi))
    return out


def entry_of(profile: Profile, r: dict) -> dict:
    """A candidate as a map entry (its key range set by the map's other entries)."""
    return dict(name=f"{note_name(r['midi'])} {r.get('string', '')}-{r.get('fret', '')}".strip(" -"),
                root=int(r["midi"]), articulation=r["articulation"], chain=r["chain"], string=r.get("string"),
                fret=r.get("fret"), velocity=[0, 127], round_robin=0, take=r["take"], source=r["channel"],
                onset=r["onset"],
                session=r["session"], candidate=r["id"], cut=r["cut"], rate=r["rate"],
                tuning_cents=r.get("cents"), level_db=r.get("level_db"), length=r["length"], loop=r.get("loop"),
                clicks_taken_out_ms=[c["ms"] for c in r.get("clicks", [])] if r["cut"].get("declick") else [])


def choose(profile: Profile, rows: list[dict], old: dict | None, everything: bool, chain: str | None,
           notes: list[str] | None = None) -> dict:
    """The map: per pitch of the profile's first articulation, the best good candidate through the font's mic
    (`font_mic`, or `chain`), the pinned entries kept (all chosen again with `everything`); with `notes`, only those
    pitches chosen (the old map's other entries kept as they are)."""
    art = next(iter(profile.presets))
    keep = [e for e in (old or {}).get("samples", []) if (e.get("pinned") and not everything)
            or (notes and note_name(e["root"]) not in notes)]
    have = {(e["articulation"], e["root"]) for e in keep}
    by = defaultdict(list)
    for r in rows:
        if r["articulation"] == art and "midi" in r and \
                (r["chain"] == chain if chain else r["chain"].endswith(", " + profile.font_mic)):
            by[r["midi"]].append(r)
    samples = list(keep)
    for m in sorted(by):
        if (art, m) in have or (notes and note_name(m) not in notes):
            continue
        best = rank(profile, by[m])
        if best:
            samples.append(entry_of(profile, best[0]))
    samples.sort(key=lambda e: (e["articulation"], e["root"]))
    for a in {e["articulation"] for e in samples}:
        mine = [e for e in samples if e["articulation"] == a]
        for e, (lo, hi) in zip(mine, key_ranges([e["root"] for e in mine])):
            e["keys"] = [lo, hi]
    return dict(instrument=profile.name, about=profile.about, font=profile.font, font_name=profile.font_name,
                presets={k: list(v) for k, v in profile.presets.items()}, level_rms=profile.level_rms,
                release_s=profile.release_s, samples=samples)


# ------------------------------------------------------------------------------------------------ the font

def sample_audio(entry: dict, root: Path, wavs: Path, level_rms: float) -> tuple[np.ndarray, int]:
    """A map entry's audio: its WAV in the cache if it is there and made from this entry, else cut from its take
    (and the WAV written)."""
    tag = hashlib.sha1(json.dumps({k: entry.get(k) for k in ("source", "cut", "loop")}, sort_keys=True)
                       .encode()).hexdigest()[:10]
    wav = wavs / f"{entry['articulation']}-{note_name(entry['root'])}-{tag}.wav"
    if wav.exists():
        x, sr = sf.read(str(wav), dtype="float64")
        return x, sr
    c = entry["cut"]
    cut = Cut(c["start"], c["end"], c["fade_in"], c["fade_out"], c.get("declick", False), tuple(c.get("gate", ())))
    path = root / entry["source"]
    if cut.declick:
        pipeline(root)
        from transcribe.evaluate import read_takes
        own = Path(entry.get("take", entry["source"])).name
        info = next(t for t in read_takes(path.parent) if t.path.name == own)
        take = Take(path.parent, info, entry.get("take", entry["source"]), entry.get("session", ""), entry["chain"],
                    entry["articulation"], True, None, {})
        y, sr, _ = declicked(take, path, root)
    else:
        y, sr = take_audio(path)
    assert sr == entry["rate"], (entry["source"], sr)
    x = leveled(cut_audio(y, sr, cut), sr, level_rms)
    if entry.get("loop"):
        lp = entry["loop"]
        n = lp["xfade"]
        w = np.linspace(0, 1, n)
        x[lp["end"] - n:lp["end"]] = (1 - w) * x[lp["end"] - n:lp["end"]] + w * x[lp["start"] - n:lp["start"]]
    wavs.mkdir(parents=True, exist_ok=True)
    sf.write(str(wav), x, sr, subtype="DOUBLE")  # exact: the SF2 rounds these to 16 bits
    return x, sr


GEN = {"keyRange": 43, "velRange": 44, "releaseVolEnv": 38, "sampleModes": 54, "overridingRootKey": 58,
       "sampleID": 53, "instrument": 41}


def write_sf2(path: Path, name: str, presets: dict, zones: list[dict], rate: int, release_s: float) -> None:
    """A SoundFont from zones: dict(name, data (float -1..1), root, cents (pitch correction), keys (lo, hi),
    velocity (lo, hi), articulation, loop (start, end) or None). One instrument and one preset per articulation
    (`presets`: articulation -> (preset name, bank, program)); 16-bit mono samples, each followed by 46 zero
    points; each zone's release `release_s`. A one-preset font of unlooped full-velocity zones has the same
    generators, in the same order, as dobro-soundfont's `sf2write.write_sf2` (the upright's 2026-10-15 build)."""
    sfm = soundfonts_module()
    smpl, shdr = bytearray(), []
    at = 0
    for z in zones:
        pcm = np.clip(np.round(z["data"] * 32767), -32768, 32767).astype("<i2")
        smpl += pcm.tobytes() + b"\0\0" * 46
        ls, le = (at + z["loop"][0], at + z["loop"][1]) if z.get("loop") else (at, at + len(pcm))
        nm = z["name"].encode("ascii", "replace")[:19]
        shdr.append((nm + b"\0" * (20 - len(nm)), at, at + len(pcm), ls, le, rate, z["root"],
                     int(round(z["cents"])), 0, 1))
        at += len(pcm) + 46
    shdr.append((b"EOS" + b"\0" * 17, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    release_tc = int(round(1200 * np.log2(release_s)))
    p = {k: [] for k in sfm.REC}
    arts = [a for a in presets if any(z["articulation"] == a for z in zones)]
    for ii, a in enumerate(arts):
        nm = (name if len(arts) == 1 else f"{name} {a}").encode()[:19]
        p["inst"].append((nm + b"\0" * (20 - len(nm)), len(p["ibag"])))
        for zi, z in enumerate(zones):
            if z["articulation"] != a:
                continue
            p["ibag"].append((len(p["igen"]), 0))
            p["igen"].append((GEN["keyRange"], z["keys"][0] | (z["keys"][1] << 8)))
            if tuple(z.get("velocity", (0, 127))) != (0, 127):
                p["igen"].append((GEN["velRange"], z["velocity"][0] | (z["velocity"][1] << 8)))
            p["igen"].append((GEN["releaseVolEnv"], release_tc & 0xFFFF))
            p["igen"].append((GEN["sampleModes"], 1 if z.get("loop") else 0))
            p["igen"].append((GEN["overridingRootKey"], z["root"]))
            p["igen"].append((GEN["sampleID"], zi))
    p["inst"].append((b"EOI" + b"\0" * 17, len(p["ibag"])))
    p["ibag"].append((len(p["igen"]), 0))
    p["igen"].append((0, 0))
    p["imod"].append((0, 0, 0, 0, 0))
    for ii, a in enumerate(arts):
        pname, bank, prog = presets[a]
        nm = pname.encode("ascii", "replace")[:19]
        p["phdr"].append((nm + b"\0" * (20 - len(nm)), prog, bank, len(p["pbag"]), 0, 0, 0))
        p["pbag"].append((len(p["pgen"]), 0))
        p["pgen"].append((GEN["instrument"], ii))
    p["phdr"].append((b"EOP" + b"\0" * 17, 0, 0, len(p["pbag"]), 0, 0, 0))
    p["pbag"].append((len(p["pgen"]), 0))
    p["pgen"].append((0, 0))
    p["pmod"].append((0, 0, 0, 0, 0))
    p["shdr"] = shdr
    zstr = lambda s: s.encode("ascii", "replace") + b"\0" + (b"\0" if len(s.encode()) % 2 == 0 else b"")
    info = sfm.lst("INFO", sfm.chunk("ifil", struct.pack("<HH", 2, 1)) + sfm.chunk("isng", zstr("EMU8000")) +
                   sfm.chunk("INAM", zstr(name)))
    body = b"sfbk" + info + sfm.lst("sdta", sfm.chunk("smpl", bytes(smpl))) + sfm.pdta(p)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def build(m: dict, root: Path, wavs: Path, out: Path) -> list[dict]:
    """The SF2 from a map and its WAVs (cut from the takes where one is missing)."""
    zones, rate = [], None
    for e in m["samples"]:
        x, sr = sample_audio(e, root, wavs, m["level_rms"])
        rate = rate or sr
        assert sr == rate, "all samples must share a rate"
        zones.append(dict(name=e["name"], data=x, root=e["root"], cents=-(e.get("tuning_cents") or 0.0),
                          keys=e["keys"], velocity=e.get("velocity", [0, 127]), articulation=e["articulation"],
                          loop=(e["loop"]["start"], e["loop"]["end"]) if e.get("loop") else None))
    presets = {k: tuple(v) for k, v in m["presets"].items()}
    write_sf2(out, m["font_name"], presets, zones, rate, m["release_s"])
    return zones


# ----------------------------------------------------------------------------------------------- the report

def report(profile: Profile, rows: list[dict], markdown: bool = False) -> str:
    lines = []
    arts = sorted({r["articulation"] for r in rows}, key=lambda a: (a != next(iter(profile.presets)), a))
    for art in arts:
        mine = [r for r in rows if r["articulation"] == art]
        for chain in sorted({r["chain"] for r in mine}):
            here = [r for r in mine if r["chain"] == chain]
            slots = defaultdict(list)
            for r in here:
                slots[slot_of(r)[2:]].append(r)
            good_n = sum(1 for r in here if not r["flags"])
            lines.append(f"\n{profile.name}, {art}, {chain}: {len(here)} candidates, {good_n} good")
            if markdown:
                lines.append("\n| | found | good | best (s) | best from | not good, why |\n|---|---|---|---|---|---|")
            keys = sorted(slots, key=lambda k: (str(k[0]), k[1:]) if art == "chuck" else k)
            for k in keys:
                rs = slots.get(k, [])
                best = rank(profile, rs)
                why = Counter(f for r in rs if r["flags"] for f in r["flags"])
                label = (f"{k[0]}" + (f" (capo {k[1]})" if len(k) > 1 and k[1] else "")) if art == "chuck" \
                    else note_name(k[0]) if k[0] else "no note"
                b = best[0] if best else None
                src = f"{b['take'].split('/')[-2]} {b['onset']:.2f}" if b else ""
                ws = ", ".join(f"{f} {n}" for f, n in why.most_common())
                if markdown:
                    lines.append(f"| {label} | {len(rs)} | {len(best)} | {b['length']:.2f} | {src} | {ws} |" if b else
                                 f"| {label} | {len(rs)} | 0 | | | {ws or 'none played'} |")
                else:
                    lines.append(f"  {label:10s} {len(rs):3d} found {len(best):3d} good"
                                 + (f"  best {b['length']:4.2f} s ({src})" if b else "  " + " " * 22)
                                 + (f"  [{ws}]" if ws else ""))
            if art != "chuck":
                want = range(profile.lowest, profile.highest + 1)
                missing = [note_name(m) for m in want if not rank(profile, slots.get((m,), []))]
                lines.append(f"  {len(want) - len(missing)} of the {len(want)} pitches {note_name(want[0])}-"
                             f"{note_name(want[-1])} with a good candidate; none for {', '.join(missing) or '-'}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=("collect", "report", "choose", "build"))
    ap.add_argument("instrument", choices=sorted(PROFILES))
    ap.add_argument("--transcription", type=Path, default=TRANSCRIPTION)
    ap.add_argument("--wavs", type=Path, default=None, help=f"the WAV cache (default {CACHE}/INSTRUMENT)")
    ap.add_argument("--map", type=Path, default=None, help="the sample map (default sounds/samples/INSTRUMENT.json)")
    ap.add_argument("--out", type=Path, default=None, help="the SF2 (default the profile's, under sounds/)")
    ap.add_argument("--only", nargs="*", help="collect: only these folders (paths under the transcription project)")
    ap.add_argument("--fresh", action="store_true", help="collect: find the notes again (not from the cache)")
    ap.add_argument("--all", action="store_true", help="choose: choose the pinned entries again too")
    ap.add_argument("--chain", help="choose: only this chain's candidates (\"18i8, Nadine\"; default: the font's mic's)")
    ap.add_argument("--notes", nargs="*", help="choose: only these pitches (E1 ...), the map's others kept")
    ap.add_argument("--markdown", action="store_true")
    a = ap.parse_args()
    profile = PROFILES[a.instrument]
    root = a.transcription.resolve()
    wavs = a.wavs or CACHE / profile.name
    cand_path = MAPS / f"{profile.name}-candidates.json"
    map_path = a.map or MAPS / f"{profile.name}.json"
    if a.stage == "collect":
        rows = collect(profile, root, wavs, a.only, a.fresh)
        MAPS.mkdir(parents=True, exist_ok=True)
        cand_path.write_text("[\n" + ",\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n]\n")
        print(f"{len(rows)} candidates -> {cand_path}")
        print(report(profile, rows))
    elif a.stage == "report":
        print(report(profile, json.loads(cand_path.read_text()), a.markdown))
    elif a.stage == "choose":
        rows = json.loads(cand_path.read_text())
        old = json.loads(map_path.read_text()) if map_path.exists() else None
        m = choose(profile, rows, old, a.all, a.chain, a.notes)
        map_path.write_text(json.dumps(m, indent=1) + "\n")
        for e in m["samples"]:
            print(f"{e['name']:10s} {e['chain']:16s} {e['length']:4.2f} s  keys {note_name(e['keys'][0])}-"
                  f"{note_name(e['keys'][1])}  {'pinned' if e.get('pinned') else 'chosen'}  ({e['source']} "
                  f"{e['onset']:.2f})")
        print(f"-> {map_path}")
    elif a.stage == "build":
        m = json.loads(map_path.read_text())
        out = a.out or SOUNDS / m["font"]
        zones = build(m, root, wavs, out)
        print(f"{out}: {len(zones)} samples ({', '.join(z['name'] for z in zones)}); "
              f"then tools/soundfonts to normalise it for the Pi's Csound")


if __name__ == "__main__":
    main()
