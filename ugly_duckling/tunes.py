"""The tunes the band knows: charts from the transcription project's tune folders (`tunes/<instrument>/<tune>/`), as its
band harness reads them (`chords.txt`: one chord per beat, bar by bar; `takes.csv`: each take's tempo).

The config lists the tunes (`[[tunes]]`): which folder, and which bars make one pass of the form when the file is
not that already: `bars` (bar numbers or labels, in order: second endings, a take's first passes) or `form` (part
letters: "A", "A", "B", "B" plays each part's bars in turn). The chart the band gets is one chord per beat over that
pass, `(root pitch class, "maj" | "min" | "7")`, as `transcribe.liveband.LiveBand` takes it.

A tune's melody, for the members' breaks (`melody_for`, 2026-10-22): its answer key in the dobro's folder, for the
tunes the ambient synth's Tune line plays, when one pass of it is one pass of the chart.
"""

from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass, field
from pathlib import Path

NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


def chord_name(chord) -> str | None:
    if chord is None:
        return None
    root, q = chord
    return NAMES[root % 12] + {"maj": "", "min": "m", "7": "7"}.get(q, "")


@dataclass
class Take:
    file: str
    bpm: float
    bar1_s: float  # the first downbeat of bar 1 in the take (s): its first beat plus its pickup
    metronome: bool


@dataclass
class Tune:
    id: str
    name: str
    folder: Path
    chart: list[tuple[int, str]]  # one chord per beat over a pass
    beats_per_bar: int
    bpm: float  # the default tempo: its takes' (those to a metronome first), median
    takes: list[Take] = field(default_factory=list)

    def summary(self) -> dict:
        bars = len(self.chart) // self.beats_per_bar
        first = [chord_name(self.chart[i]) for i in range(0, len(self.chart), self.beats_per_bar)]
        return {"id": self.id, "name": self.name, "bpm": round(self.bpm), "beats_per_bar": self.beats_per_bar,
                "bars": bars, "chords": first}


def _expand(bars: dict, entry: dict) -> list:
    keys = list(bars)
    if entry.get("bars"):
        want = entry["bars"]
        if isinstance(want, str):  # "1-16"
            a, b = (int(x) for x in want.split("-"))
            want = list(range(a, b + 1))
        missing = [k for k in want if k not in bars]
        if missing:
            raise ValueError(f"{entry['id']}: no bars {missing} in its chords.txt")
        return list(want)
    if entry.get("form"):
        out = []
        for part in entry["form"]:
            mine = [k for k in keys if isinstance(k, str) and k.rstrip("0123456789") == part]
            if not mine:
                raise ValueError(f"{entry['id']}: no part {part} in its chords.txt")
            out += mine
        return out
    return keys


def read_takes(folder: Path) -> list[Take]:
    path = folder / "takes.csv"
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for row in csv.DictReader(f):
            try:
                bpm = float(row["bpm"])
            except (KeyError, ValueError):
                continue
            pickup = float(row.get("pickup_beats") or 0)
            beat0 = float(row.get("beat0_s") or 0)
            out.append(Take(row["take"], bpm, beat0 + pickup * 60.0 / bpm, row.get("metronome", "") == "yes"))
    return out


def load_tune(root: Path, entry: dict, src: str | None = None) -> Tune:
    """One `[[tunes]]` entry, its folder under `root` (the transcription project's `tunes/`). `src`: that
    project's `pipeline/src`, for its chart reader."""
    if src:
        import sys
        s = str(Path(src).expanduser())
        if s not in sys.path:
            sys.path.insert(0, s)
    from transcribe.chords import parse_chord, read_chords
    from transcribe.livechords import majmin

    folder = Path(root).expanduser() / entry["folder"]
    bars = read_chords(folder / "chords.txt")
    order = _expand(bars, entry)
    chart = []
    for b in order:
        for sym in bars[b]:
            pc, q = parse_chord(sym)
            chart.append((pc, majmin(q)))
    bpb = int(entry.get("beats_per_bar") or len(bars[order[0]]))
    takes = read_takes(folder)
    timed = [t.bpm for t in takes if t.metronome] or [t.bpm for t in takes]
    bpm = float(entry.get("bpm") or (statistics.median(timed) if timed else 100.0))
    return Tune(entry["id"], entry.get("name", entry["id"]), folder, chart, bpb, bpm, takes)


def load_tunes(root: Path, entries: list[dict], src: str | None = None) -> tuple[dict[str, Tune], list[str]]:
    """The tunes that load, by id, and a line for each that does not."""
    tunes, problems = {}, []
    for e in entries:
        try:
            t = load_tune(root, e, src)
            tunes[t.id] = t
        except Exception as ex:  # noqa: BLE001 (a missing folder must not stop the others)
            problems.append(f"{e.get('id', '?')}: {ex}")
    return tunes, problems


def melody_for(tune: Tune):
    """The tune's melody for the members' breaks (the transcription project's `transcribe.bandbreaks`): one pass of
    its answer key, `tunes/dobro/<name>/<name>.musicxml` beside its folder, for the tunes whose melody the ambient
    synth's Tune line plays (`ambient.presets.TUNE_MELODIES`: its key, its bars and parts), when that pass is one pass
    of the band's chart (four beats a bar, as long). None: no melody here (no breaks on this tune)."""
    from ambient.music import KEYS
    from ambient.presets import TUNE_MELODIES
    name = Path(tune.folder).name
    src = next((m for m in TUNE_MELODIES.values() if m["folder"] == name), None)
    if src is None or not tune.chart:
        return None
    path = Path(tune.folder).parent.parent / "dobro" / name / f"{name}.musicxml"
    if not path.is_file():
        return None
    try:
        from transcribe.bandbreaks import fits
        from transcribe.breaks import read_tune
    except ImportError:  # a transcription project from before the breaks
        return None
    mel = read_tune(path, KEYS.index(src["key"]), src["bars"], tuple(src.get("parts", ())), tune.id)
    return mel if fits(mel, tune.chart, tune.beats_per_bar) else None
