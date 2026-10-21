"""The Ugly Duckling String Band's config: the device (both ways), the inputs, the tunes, the port, the peers.

Read from $UGLY_DUCKLING_CONFIG, else /etc/ugly-duckling.toml (and $UD_TRANSCRIBE, if set, for `[band] transcribe`:
a worktree of the transcription project) (installed once by `setup/install-ud.sh` from
`config/ud-pi.toml`). Devices, channels and controls come from here only: no code names a card.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ambient import pocket as pockets

from .record import RecordConfig

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PATH = Path("/etc/ugly-duckling.toml")


@dataclass
class Device:
    """Where the band plays and the player is heard (`ugly_duckling/duplex.py`)."""
    kind: str = "alsa"  # alsa: the device both ways; file: no device (a recorded take as the input, nothing heard)
    playback: str = "plughw:CARD=USB,DEV=0"
    capture: str = "hw:CARD=USB,DEV=0"
    card: str = "USB"  # for its controls (amixer -c)
    channels: int = 20  # the capture's channels
    loopback: list[int] = field(default_factory=lambda: [10, 11])  # capture channels that return the playback
    # the room mic, captured whichever input the band follows: its echo path's delay is the room's (the speakers to
    # a mic across the room), and it is recorded (empty: none)
    room: list[int] = field(default_factory=list)
    block: int = 128  # frames the engine computes at a time
    buffer_ms: float = 16.0
    period_ms: float = 2.67
    # the converters' delay, out and in (ms): not seen by the loopback (it is digital); an estimate
    converter_ms: float = 1.0
    # controls set before the capture opens (amixer -c card cset): phantom power for a condenser
    controls: list[dict] = field(default_factory=list)
    # kind "file": the take (a tune's id and its file in that tune's folder), its channel, the simulated round trip
    file_tune: str = ""
    file_take: str = ""
    file_path: str = ""  # or any recording (its bar 1 at file_bar1_s), in place of a tune's take
    file_bar1_s: float = 0.0
    file_channel: int | None = None
    file_latency: int = 300
    # the room, simulated: the band's own sound as the input hears it from the speakers (the band's mix, `file_latency`
    # frames after it played, through the impulse response in `file_room_ir`, a .npy or .wav at 48 kHz, at
    # `file_room_gain_db`); the take at `file_take_gain` (0: the player silent, the band alone in the room) and cut
    # after `file_take_seconds` from its bar 1 (0: the whole take; for a player who stops)
    file_room_ir: str = ""
    file_room_gain_db: float = 0.0
    file_take_gain: float = 1.0
    file_take_seconds: float = 0.0


@dataclass
class Input:
    id: str
    name: str
    channels: list[int]  # capture channels (from 0), mixed
    instrument: str = "guitar"  # the beat follower's and band's preset (transcribe: bass, guitar, dobro)
    note: str = ""
    echo: bool = True  # take the band's own sound out of this input (`transcribe.echo`)


@dataclass
class Config:
    path: Path
    web_host: str = "127.0.0.1"
    web_port: int = 8004
    peers: list[str] = field(default_factory=list)
    transcribe: str = "~/play/dobro-transcription/pipeline/src"
    tunes_root: str = "~/play/dobro-transcription/tunes"
    sounds_dir: Path = REPO / "sounds"
    tunes: list[dict] = field(default_factory=list)
    inputs: list[Input] = field(default_factory=list)
    device: Device = field(default_factory=Device)
    # the band
    lead_s: float = 0.05  # how far ahead the band decides (transcribe.band.BandParams.lead_s)
    in_block: int = 256  # capture frames given to the listening at a time
    volume_db: float = 0.0  # the page's default
    min_volume_db: float = -24.0
    # the cap: the band's level over its own (-33 dBFS gated rms at 0 dB, ambient-room PLAN.md, "The band
    # player") at most this: +12 dB puts it at -21 dBFS, the level takes play at (piano-recorder)
    max_volume_db: float = 12.0
    ceiling_db: float = -1.0  # every sample clipped here, whatever the volume
    click_db: float = -18.0  # the count-in's clicks (first sample), before the volume
    idle_minutes: float = 10.0  # a band started and not playing this long lets the device go
    voice_model: str = ""  # Vosk's model directory: "I count it in" and "stop"; empty: not offered
    rt_priority: int = 0
    # the band's count-in: two bars at or above this tempo (a reel at 170 is not counted in half time), one below
    two_bar_bpm: float = 150.0
    # the band's own sound taken out of the input (`transcribe.echo`): on, and how much of the room it learns (s)
    echo: bool = True
    echo_taps_s: float = 0.3
    echo_state_dir: str = "~/.cache/ugly-duckling"  # the room each input's canceller learnt, kept between sessions
    # the band stops when the player has not attacked for this many beats (after the band's own sound is taken out;
    # 8 before the player's first attack), and a rise counts as an attack only this far over the room's noise
    # (`transcribe.livebeat` `stop_beats`, `noise_gate_db`; the transcription project's `tools/stop_study.py`)
    stop_beats: int = 5
    noise_gate_db: float = 6.0
    # the band's pocket (`ambient/pocket.py`): the preset a start gets unless it names another (the page's "Pocket"),
    # per-part overrides of that preset ({part: {"beat" | "and" | "scatter": ms}}), and the scatter's seed
    pocket: str = pockets.DEFAULT
    pocket_parts: dict = field(default_factory=dict)
    pocket_seed: int = pockets.SEED
    # the steady band clock (the transcription project's `livebeat` `steady_bars`): the width in bars a start gets
    # unless it names another (the start request's `steady`); None: the band's clock as before. And the band's beats
    # on the player's attacks rather than on their onset function's peaks (`livebeat.ONSET_LEAD_S`, the bass's 20 ms;
    # the start request's `onset_lead`). Both off until the player has chosen them by ear
    steady_bars: float | None = None
    onset_lead: bool = False
    record: RecordConfig = field(default_factory=RecordConfig)

    def pocket_for(self, name: str | None = None) -> pockets.Pocket:
        """The pocket named (the config's own by default): the config's overrides apply to its own preset only."""
        name = self.pocket if name is None else name
        return pockets.make(name, self.pocket_parts if name == self.pocket else None, self.pocket_seed)


def pocket_entry(path: Path, raw) -> tuple[str, dict, int]:
    """`[band] pocket`: a preset's name (`pocket = "pushed"`), or a table: `preset`, `seed`, and per part its
    overrides (`[band.pocket] preset = "pushed"`, `bass = { beat = -5 }`). Checked here (ValueError)."""
    if isinstance(raw, str):
        raw = {"preset": raw}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: [band] pocket: a preset's name ({', '.join(pockets.PRESETS)}) or a table")
    unknown = set(raw) - {"preset", "seed", *pockets.PARTS}
    if unknown:
        raise ValueError(f"{path}: [band] pocket has no {', '.join(sorted(unknown))}")
    name = str(raw.get("preset", pockets.DEFAULT))
    parts = {k: v for k, v in raw.items() if k in pockets.PARTS}
    seed = int(raw.get("seed", pockets.SEED))
    try:
        pockets.make(name, parts, seed)
    except ValueError as e:
        raise ValueError(f"{path}: [band] pocket: {e}")
    return name, parts, seed


STEADY_RANGE = (0.25, 16.0)  # bars


def steady_entry(where, raw) -> float | None:
    """`[band] steady_bars` (or the start request's `steady`): a width in bars within `STEADY_RANGE`, or none (absent,
    "off", false): the band's clock as before. Checked here (ValueError)."""
    if raw is None or raw is False or raw == "off":
        return None
    try:
        bars = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{where}: steady: a width in bars ({STEADY_RANGE[0]:g}-{STEADY_RANGE[1]:g}) or off")
    if not STEADY_RANGE[0] <= bars <= STEADY_RANGE[1]:
        raise ValueError(f"{where}: steady: a width in bars ({STEADY_RANGE[0]:g}-{STEADY_RANGE[1]:g}) or off")
    return bars


def load_config(path: Path | None = None) -> Config:
    path = Path(path or os.environ.get("UGLY_DUCKLING_CONFIG") or DEFAULT_PATH)
    raw = tomllib.loads(path.read_text())
    web, band, dev, voice = raw.get("web", {}), raw.get("band", {}), dict(raw.get("device", {})), raw.get("voice", {})
    unknown = set(dev) - set(Device.__dataclass_fields__)
    if unknown:
        raise ValueError(f"{path}: [device] has no {', '.join(sorted(unknown))}")
    pocket, pocket_parts, pocket_seed = pocket_entry(path, band.get("pocket", pockets.DEFAULT))
    sounds = Path(os.path.expanduser(band.get("sounds", "sounds")))
    if not sounds.is_absolute():
        sounds = REPO / sounds
    return Config(
        path=path,
        web_host=web.get("host", "127.0.0.1"),
        web_port=int(web.get("port", 8004)),
        peers=[str(u) for u in raw.get("peers", [])],
        transcribe=os.environ.get("UD_TRANSCRIBE") or band.get("transcribe", Config.transcribe),
        tunes_root=band.get("tunes", Config.tunes_root),
        sounds_dir=sounds,
        tunes=list(raw.get("tunes", [])),
        inputs=[Input(i["id"], i.get("name", i["id"]), [int(c) for c in i["channels"]], i.get("instrument", "guitar"),
                      i.get("note", ""), bool(i.get("echo", True))) for i in raw.get("inputs", [])],
        device=Device(**dev),
        lead_s=float(band.get("lead_s", 0.05)),
        in_block=int(band.get("in_block", 256)),
        volume_db=float(band.get("volume_db", 0.0)),
        min_volume_db=float(band.get("min_volume_db", -24.0)),
        max_volume_db=float(band.get("max_volume_db", 12.0)),
        ceiling_db=float(band.get("ceiling_db", -1.0)),
        click_db=float(band.get("click_db", -18.0)),
        idle_minutes=float(band.get("idle_minutes", 10.0)),
        voice_model=os.path.expanduser(voice.get("model", "")),
        rt_priority=int(band.get("rt_priority", 0)),
        two_bar_bpm=float(band.get("two_bar_bpm", 150.0)),
        echo=bool(band.get("echo", True)),
        echo_taps_s=float(band.get("echo_taps_s", 0.3)),
        echo_state_dir=band.get("echo_state_dir", Config.echo_state_dir),
        stop_beats=int(band.get("stop_beats", 5)),
        noise_gate_db=float(band.get("noise_gate_db", 6.0)),
        pocket=pocket, pocket_parts=pocket_parts, pocket_seed=pocket_seed,
        steady_bars=steady_entry(path, band.get("steady_bars")),
        onset_lead=bool(band.get("onset_lead", False)),
        record=RecordConfig(**{k: v for k, v in raw.get("record", {}).items()}),
    )
