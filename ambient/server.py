"""The web service: the phone page and its API.

    python -m ambient.server      (config from $AMBIENT_ROOM_CONFIG or
                                   /etc/ambient-room.toml)
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .config import Config, load_config
from .engine import Engine, EngineError, FakeEngine
from . import evolve, explain, music, samples
from .room import STOP_FADE_S, Room
from .presets import ASPECTS, WHOLE
from .state import MOODS, Invalid

STATIC = Path(__file__).parent / "static"


def create_app(cfg: Config) -> FastAPI:
    holder: dict = {}

    @asynccontextmanager
    async def lifespan(app):
        samples.orchestra(cfg.sounds_dir)  # which sampled voices have their fonts: the page says so from the start
        engine = (FakeEngine() if cfg.engine == "fake"
                  else Engine(cfg.device, cfg.buffer_ms, cfg.gain_db, cfg.sounds_dir))
        holder["room"] = Room(engine, cfg.state_file, cfg.peers)
        yield
        holder["room"].close()

    app = FastAPI(title="Ambient room", lifespan=lifespan)

    def room() -> Room:
        return holder["room"]

    @app.get("/")
    def page():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/icon.svg")
    def icon():
        return FileResponse(STATIC / "icon.svg", media_type="image/svg+xml")

    @app.get("/api/options")
    def options():
        o = explain.options()
        # the presets, calm to energetic; each with where it sits on the compass
        o["presets"] = sorted(({"id": k, "about": WHOLE[k][0], "pos": evolve.position(m),
                                "summary": f"{music.pretty(m['key'])} {music.describe_scale(m['key'], m['tones'])['name']}"
                                           + ("" if m["harmony"]["style"] == "Wander" else " · " + explain.progression_name(m))}
                               for k, m in MOODS.items()), key=lambda p: p["pos"][0])
        o["aspects"] = [{"id": k, "name": n} for k, (n, _) in ASPECTS.items()]
        return o

    @app.get("/api/status")
    def status():
        return room().status()

    @app.get("/api/events")
    def events(since: int = 0):
        """Notes and drum hits as scheduled, with the score time being heard."""
        return room().events(since)

    @app.patch("/api/state")
    def change(change: dict = Body(...)):
        try:
            return room().change(change)
        except Invalid as e:
            raise HTTPException(400, str(e))

    @app.post("/api/preset/{name}")
    def preset(name: str, aspects: list[str] | None = Body(None, embed=True)):
        """A preset: all of it, or only these aspects (key, harmony, melody, beat, sound)."""
        try:
            return room().preset(name, aspects)
        except KeyError:
            raise HTTPException(404, f"no preset {name!r}")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/saved")
    def save(name: str = Body(..., embed=True)):
        name = name.strip()[:40]
        if not name:
            raise HTTPException(400, "a name")
        return room().save(name)

    @app.post("/api/saved/{name}")
    def apply_saved(name: str, aspects: list[str] | None = Body(None, embed=True)):
        """One of yours: all of it, or only these aspects."""
        try:
            return room().preset(name, aspects, saved=True)
        except KeyError:
            raise HTTPException(404, f"no preset of yours called {name!r}")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/saved/{name}")
    def delete_saved(name: str):
        return room().delete_saved(name)

    @app.post("/api/surprise")
    def surprise(aspects: list[str] | None = Body(None, embed=True)):
        """Something new: everything, or only these aspects."""
        try:
            return room().surprise(aspects)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/evolve/now")
    def evolve_now():
        return room().evolve_now()

    @app.post("/api/evolve/undo")
    def evolve_undo():
        return room().undo()

    @app.post("/api/play")
    def play():
        try:
            return room().play()
        except EngineError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/stop")
    def stop():
        return room().stop(STOP_FADE_S)

    @app.post("/api/yield")
    def yield_speakers():
        """Another program wants the speakers (ambient/peers.py)."""
        room().yield_speakers()
        return {"released": not room().engine.running}

    @app.post("/api/sleep")
    def sleep(minutes: float = Body(..., embed=True)):
        if not 0 <= minutes <= 240:
            raise HTTPException(400, "minutes must be 0-240")
        return room().sleep(minutes)

    return app


def main() -> None:
    import uvicorn
    cfg = load_config()
    # open page connections (polling) would otherwise hold a restart up
    uvicorn.run(create_app(cfg), host=cfg.web_host, port=cfg.web_port, log_level="warning",
                timeout_graceful_shutdown=2)


if __name__ == "__main__":
    main()
