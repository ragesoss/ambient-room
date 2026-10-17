"""The Ugly Duckling String Band: the band that follows the player, as a service with a phone page.

    python -m ugly_duckling.server     (config from $UGLY_DUCKLING_CONFIG or /etc/ugly-duckling.toml)

Nothing opens the device and nothing sounds until Start (`/api/start`). It takes turns with the other apps on the
control unit (piano-recorder's `docs/components.md`, "A second program on the control unit"): before opening the
device it asks each peer to let go (`ambient/peers.py`), and it refuses to start while one is recording; when a
peer asks it (`/api/yield`) it stops the band and lets the device go.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .config import Config, load_config
from .session import PARTS, PART_NAMES, Busy, Session, Settings, selfcheck
from .tunes import load_tunes

STATIC = Path(__file__).parent / "static"
INSTRUMENTS = {"guitar": "Guitar", "dobro": "Dobro", "bass": "Bass"}


class Band:
    """The service's state: the tunes, the inputs, the current run (`Session`) if any."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        src = str(Path(cfg.transcribe).expanduser())
        if src not in sys.path:
            sys.path.insert(0, src)
        from transcribe import bandvoice
        self.voicing = bandvoice
        self.tunes, self.problems = load_tunes(Path(cfg.tunes_root), cfg.tunes, src)
        self.inputs = {i.id: i for i in cfg.inputs}
        self.lock = threading.RLock()
        self.session: Session | None = None
        self.last: Session | None = None
        self.voice_why = self._voice_check()
        self._model = None
        self.checking = False

    def _voice_check(self) -> str | None:
        """Why counting in by voice is not offered here, or None."""
        if not self.cfg.voice_model:
            return "no word model in the config ([voice] model)"
        if not Path(self.cfg.voice_model).is_dir():
            return f"the word model is not at {self.cfg.voice_model}"
        try:
            import vosk  # noqa: F401
        except ImportError:
            return "the word recognizer (vosk) is not installed"
        return None

    def model(self):
        """Vosk's model, loaded once (about 140 MB, a second or two)."""
        if self.voice_why is not None:
            return None
        if self._model is None:
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            self._model = Model(self.cfg.voice_model)
        return self._model

    def options(self) -> dict:
        c = self.cfg
        return {"tunes": [t.summary() for t in self.tunes.values()], "problems": self.problems,
                "inputs": [{"id": i.id, "name": i.name, "instrument": i.instrument, "note": i.note}
                           for i in c.inputs],
                "instruments": [{"id": k, "name": v} for k, v in INSTRUMENTS.items()],
                "parts": [{"id": p, "name": PART_NAMES[p]} for p in PARTS],
                "volume": {"default": c.volume_db, "min": c.min_volume_db, "max": c.max_volume_db},
                "voice": {"available": self.voice_why is None, "why": self.voice_why},
                "device": c.device.kind}

    def start(self, body: dict) -> dict:
        with self.lock:
            if self.session is not None and self.session.running:
                raise Busy("the band is already playing: stop it first")
            if self.checking:
                raise Busy("a self-check is using the device")
            tune = self.tunes.get(body.get("tune", ""))
            if tune is None:
                raise ValueError(f"no tune {body.get('tune')!r}")
            inp = self.inputs.get(body.get("input") or (self.cfg.inputs[0].id if self.cfg.inputs else ""))
            if inp is None:
                raise ValueError(f"no input {body.get('input')!r}")
            count = body.get("count", "band")
            if count not in ("band", "voice"):
                raise ValueError("count: band or voice")
            if count == "voice" and self.voice_why:
                raise ValueError(f"counting in by voice is not available: {self.voice_why}")
            bpm = float(body.get("bpm") or tune.bpm)
            if not 40 <= bpm <= 260:
                raise ValueError("bpm: 40-260")
            instrument = body.get("instrument") or inp.instrument
            if instrument not in INSTRUMENTS:
                raise ValueError(f"no instrument {instrument!r}")
            parts = {p: bool((body.get("parts") or {}).get(p, True)) for p in PARTS}
            vol = float(body.get("volume_db", self.cfg.volume_db))
            vol = max(self.cfg.min_volume_db, min(self.cfg.max_volume_db, vol))
            listen_stop = bool(body.get("listen_stop", True)) and self.voice_why is None
            s = Settings(tune.id, bpm, inp.id, instrument, parts, vol, count, listen_stop)
            words = self.model() if (count == "voice" or listen_stop) else None
            sess = Session(self.cfg, tune, inp, s, self.voicing, words, on_end=self._ended)
            sess.start()  # raises Busy
            self.session = sess
            return self.status()

    def _ended(self, sess: Session) -> None:
        self.last = sess

    def stop(self, reason: str = "stopped") -> dict:
        with self.lock:
            s = self.session
        if s is not None and s.running:
            s.stop(reason)
        return self.status()

    def live(self, body: dict) -> dict:
        s = self.session
        if s is None or not s.running:
            raise Busy("the band is not playing")
        if "volume_db" in body:
            s.set_volume(float(body["volume_db"]))
        if "parts" in body:
            s.set_parts(body["parts"])
        return self.status()

    def status(self) -> dict:
        s = self.session
        if s is None:
            return {"state": "stopped", "playing": False}
        out = s.status()
        out["playing"] = s.running
        if not s.running:
            out["state"] = "error" if s.error else "stopped"
        return out

    def check(self, input_id: str | None = None, seconds: float = 2.0) -> dict:
        with self.lock:
            if self.session is not None and self.session.running:
                raise Busy("the band is playing")
            self.checking = True
        try:
            inp = self.inputs.get(input_id or "") or (self.cfg.inputs[0] if self.cfg.inputs else None)
            return selfcheck(self.cfg, self.voicing, inp, seconds)
        finally:
            self.checking = False

    def close(self) -> None:
        s = self.session
        if s is not None and s.running:
            s.stop("the service stopped")


def create_app(cfg: Config) -> FastAPI:
    holder: dict = {}

    @asynccontextmanager
    async def lifespan(app):
        holder["band"] = Band(cfg)
        yield
        holder["band"].close()

    app = FastAPI(title="Ugly Duckling String Band", lifespan=lifespan, docs_url=None, redoc_url=None)

    def band() -> Band:
        return holder["band"]

    @app.get("/")
    def page():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/icon.svg")
    def icon():
        return FileResponse(STATIC / "icon.svg", media_type="image/svg+xml")

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/fonts/{name}")
    def font(name: str):
        path = STATIC / "fonts" / name
        if not re.match(r"^[A-Za-z0-9-]+\.woff2$", name) or not path.is_file():
            raise HTTPException(404, "no such font")
        return FileResponse(path, media_type="font/woff2", headers={"Cache-Control": "max-age=86400"})

    @app.get("/api/options")
    def options():
        return band().options()

    @app.get("/api/status")
    def status():
        return band().status()

    @app.post("/api/start")
    def start(body: dict = Body(default={})):
        try:
            return band().start(body)
        except Busy as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/stop")
    def stop():
        return band().stop()

    @app.patch("/api/live")
    def live(body: dict = Body(...)):
        try:
            return band().live(body)
        except Busy as e:
            raise HTTPException(409, str(e))

    @app.post("/api/yield")
    def yield_device():
        """Another app wants the device (ambient/peers.py): the band stops and lets it go. Never refused: the band
        records nothing."""
        t0 = time.monotonic()
        band().stop("another app asked for the device")
        return {"released": True, "seconds": round(time.monotonic() - t0, 2)}

    @app.post("/api/selfcheck")
    def check(input: str | None = None, seconds: float = 2.0):
        """The device opened both ways and closed, nothing played (`session.selfcheck`)."""
        try:
            return band().check(input, min(10.0, max(0.5, seconds)))
        except Busy as e:
            raise HTTPException(409, str(e))

    return app


def main() -> None:
    import uvicorn
    cfg = load_config()
    uvicorn.run(create_app(cfg), host=cfg.web_host, port=cfg.web_port, log_level="warning",
                timeout_graceful_shutdown=3)


if __name__ == "__main__":
    main()
