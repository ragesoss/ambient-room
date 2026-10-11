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
    )
