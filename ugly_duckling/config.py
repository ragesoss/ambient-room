"""The Ugly Duckling String Band's config: the device (both ways), the inputs, the tunes, the port, the peers.

Read from $UGLY_DUCKLING_CONFIG, else /etc/ugly-duckling.toml (installed once by `setup/install-ud.sh` from
`config/ud-pi.toml`). Devices, channels and controls come from here only: no code names a card.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class Input:
    id: str
    name: str
    channels: list[int]  # capture channels (from 0), mixed
    instrument: str = "guitar"  # the beat follower's and band's preset (transcribe: bass, guitar, dobro)
    note: str = ""


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


def load_config(path: Path | None = None) -> Config:
    path = Path(path or os.environ.get("UGLY_DUCKLING_CONFIG") or DEFAULT_PATH)
    raw = tomllib.loads(path.read_text())
    web, band, dev, voice = raw.get("web", {}), raw.get("band", {}), dict(raw.get("device", {})), raw.get("voice", {})
    unknown = set(dev) - set(Device.__dataclass_fields__)
    if unknown:
        raise ValueError(f"{path}: [device] has no {', '.join(sorted(unknown))}")
    sounds = Path(os.path.expanduser(band.get("sounds", "sounds")))
    if not sounds.is_absolute():
        sounds = REPO / sounds
    return Config(
        path=path,
        web_host=web.get("host", "127.0.0.1"),
        web_port=int(web.get("port", 8004)),
        peers=[str(u) for u in raw.get("peers", [])],
        transcribe=band.get("transcribe", Config.transcribe),
        tunes_root=band.get("tunes", Config.tunes_root),
        sounds_dir=sounds,
        tunes=list(raw.get("tunes", [])),
        inputs=[Input(i["id"], i.get("name", i["id"]), [int(c) for c in i["channels"]], i.get("instrument", "guitar"),
                      i.get("note", "")) for i in raw.get("inputs", [])],
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
    )
