"""The service's config: which engine, which playback device, which port.

Read from $AMBIENT_ROOM_CONFIG, else /etc/ambient-room.toml. The playback
device is piano-recorder's slot 3; its facts live in that project's
docs/components.md.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PATH = Path("/etc/ambient-room.toml")


@dataclass
class BandConfig:
    """The band player's profile (`[band]`): its own output, with a short buffer (`ambient/bandplayer.py`)."""
    # the transcription project's package, whose decisions (transcribe.liveband) and voicing (transcribe.bandvoice)
    # the band plays
    transcribe: str = "~/play/dobro-transcription/pipeline/src"
    output: str = "alsa"  # alsa, paced (no device: replays) or aplay (ambient/output.py)
    device: str = ""
    block: int = 128  # frames the engine computes at a time (a multiple of 64)
    buffer_ms: float = 10.67  # the output's buffer: 4 blocks of 128 frames
    period_ms: float | None = None  # alsa: the device's period (default a quarter of the buffer)
    gain_db: float = 0.0
    rt_priority: int = 0  # SCHED_FIFO priority for the engine's thread; 0: none
    late_ms: dict[str, float] = field(default_factory=lambda: {"bass": 30.0, "comp": 30.0, "chop": 15.0})


@dataclass
class Config:
    engine: str  # "csound" or "fake"
    device: str
    buffer_ms: int
    gain_db: float
    web_host: str
    web_port: int
    state_file: Path | None
    path: Path
    # Other programs that play through the same speakers (ambient/peers.py).
    peers: list[str] = field(default_factory=list)
    # Where the sampled voices' SoundFonts are (ambient/samples.py); None: no samples
    sounds_dir: Path | None = None
    # The engine's block (frames) and its output: aplay (the default), alsa, or csound (Csound's own ALSA output)
    block: int = 1024
    output: str = "aplay"
    period_ms: float | None = None
    # The band player's profile ([band]); the defaults if the file has none
    band: BandConfig = field(default_factory=BandConfig)


def load_config(path: Path | None = None) -> Config:
    path = Path(path or os.environ.get("AMBIENT_ROOM_CONFIG") or DEFAULT_PATH)
    raw = tomllib.loads(path.read_text())
    out, web = raw.get("output", {}), raw.get("web", {})
    state = raw.get("state", {}).get("file")
    if state:
        state = Path(os.path.expanduser(state))
        if not state.is_absolute():
            state = REPO / state
    # the SoundFonts: [sounds] dir, the repo's sounds/ unless set ("" for none)
    sounds = raw.get("sounds", {}).get("dir", "sounds")
    sounds_dir = None
    if sounds:
        sounds_dir = Path(os.path.expanduser(sounds))
        if not sounds_dir.is_absolute():
            sounds_dir = REPO / sounds_dir
    b = dict(raw.get("band", {}))
    late = {**BandConfig().late_ms, **{k: float(v) for k, v in b.pop("late_ms", {}).items()}}
    unknown = set(b) - set(BandConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(f"{path}: [band] has no {', '.join(sorted(unknown))}")
    band = BandConfig(**b, late_ms=late)
    return Config(
        engine=out.get("engine", "csound"),
        device=out.get("device", ""),
        buffer_ms=int(out.get("buffer_ms", 400)),
        gain_db=float(out.get("gain_db", 0.0)),
        web_host=web.get("host", "127.0.0.1"),
        web_port=int(web.get("port", 8001)),
        state_file=state,
        path=path,
        peers=[str(u) for u in raw.get("peers", [])],
        sounds_dir=sounds_dir,
        block=int(out.get("block", 1024)),
        output=out.get("output", "aplay"),
        period_ms=out.get("period_ms"),
        band=band,
    )
