"""The room: the shared settings, playing or not, and the sleep timer.

One Room per service. The page's requests change it; a thread ticks the
conductor while it plays. Stopping fades (STOP_FADE_S from the Stop
button, FADE_S from the sleep timer), then releases the
playback device, so the recorder can use it.
"""

import copy
import json
import random
import threading
import time
from collections import deque
from pathlib import Path

from .conductor import Conductor
from . import evolve, explain, peers
from .engine import EngineError
from .presets import ASPECTS
from .state import DEFAULT, MOODS, apply_values, family_of, get_path, merge, surprise, upgrade



FADE_S = 10.0  # Play fades in, the sleep timer fades out
STOP_FADE_S = 0.3  # the Stop button: at once, without a click
QUICK_FADE_S = 1.5  # when the recorder wants the speakers


class Room:
    def __init__(self, engine, state_file: Path | None = None, peer_urls: list[str] | None = None):
        self.engine = engine
        self.state_file = state_file
        self.peers = peer_urls or []
        self.lock = threading.RLock()
        self.state = self._load()
        self.version = 0
        self.playing = False
        self.release_at: float | None = None  # monotonic: when the device is let go
        self.sleep_at: float | None = None
        self.error: str | None = None
        self.rng = random.Random()
        self.next_evolve: float | None = None  # monotonic
        self.history: deque = deque(maxlen=40)  # changes, yours and evolution's: {id, at, by, what, items, before, pos}
        self.history_id = 0
        self.evolve_period: float | None = None  # seconds between this change and the next
        self.saved = self._load_saved()  # your own presets: name -> {parts, values}
        self.conductor = Conductor(engine, self.rng)
        self.conductor.apply(self.state)
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    # Requests

    def status(self) -> dict:
        with self.lock:
            now = time.monotonic()
            return {
                "state": self.state,
                "playing": self.playing,
                "fading": not self.playing and self.release_at is not None,
                "sleep_s": None if self.sleep_at is None else max(0, round(self.sleep_at - now)),
                "version": self.version,
                "error": self.error or self.engine.error or (self.conductor.error and f"conductor: {self.conductor.error}"),
                "dropouts": self.engine.underruns,
                "evolving": {
                    "next_s": None if self.next_evolve is None else max(0, round(self.next_evolve - now)),
                    "period": None if self.evolve_period is None else round(self.evolve_period, 1),
                    "history": [{"id": h["id"], "what": h["what"], "items": h["items"], "by": h["by"],
                                 "ago": round(now - h["at"])}
                                for h in list(self.history)[-10:]][::-1],
                    "trail": [h["pos"] for h in list(self.history)[-24:]],
                },
                "saved": [{"name": k, "parts": v["parts"]} for k, v in self.saved.items()],
                "explain": explain.describe(self.state, self.conductor if self.engine.running else None,
                                            self.engine.time()),
            }

    def events(self, since: int) -> dict:
        """What has been scheduled since `since`, and the score time being
        heard now, so the page can draw each event as it sounds."""
        with self.lock:
            audible = self.engine.time() - self.engine.latency() if self.engine.running else None
            evs = [e for e in self.conductor.events if e["seq"] > since] if self.engine.running else []
            return {"audible": audible, "seq": self.conductor.seq, "events": evs}

    def change(self, change: dict) -> dict:
        with self.lock:
            new = merge(self.state, change)
            self._record(self.state, new, "you")
            self._set(new)
            return self.status()

    def preset(self, name: str, aspects: list[str] | None = None, saved: bool = False) -> dict:
        """A preset (or one of yours, `saved`), all of it or only some
        aspects of it (the key, harmony, melody, beat, sound): the rest of
        the settings, and anything locked, stay as they are. KeyError if
        there is no such preset."""
        with self.lock:
            aspects = self._aspects(aspects)
            if saved:
                values = {p: v for p, v in self.saved[name]["values"].items() if p in self._paths(aspects)}
            else:
                source = MOODS[name]
                values = {p: get_path(source, p) for p in self._paths(aspects)}
                if "tones" in values and family_of(self.state["tones"]) == "equal":  # keep the tuning: equal stays equal
                    values["tones"] = {k: (v if k == "0" else ["ET"]) for k, v in values["tones"].items()}
            new = apply_values(self.state, values)
            self._record(self.state, new, "you", f"{'Yours' if saved else 'Preset'}: {name}{self._which(aspects)}")
            self._set(new)
            return self.status()

    def save(self, name: str) -> dict:
        """The whole sound now (its key and every part) as a preset of your own."""
        with self.lock:
            paths = self._paths(list(ASPECTS))
            self.saved[name] = {"parts": list(ASPECTS),
                                "values": {p: copy.deepcopy(get_path(self.state, p)) for p in paths}}
            self._save_saved()
            self.version += 1
            return self.status()

    def delete_saved(self, name: str) -> dict:
        with self.lock:
            self.saved.pop(name, None)
            self._save_saved()
            self.version += 1
            return self.status()

    def surprise(self, aspects: list[str] | None = None) -> dict:
        """Something new for these aspects (all: everything), the rest kept."""
        with self.lock:
            aspects = self._aspects(aspects)
            fresh = surprise(self.state, self.rng)
            new = apply_values(self.state, {p: get_path(fresh, p) for p in self._paths(aspects)})
            self._record(self.state, new, "you", f"Surprise me{self._which(aspects)}")
            self._set(new)
            return self.status()

    @staticmethod
    def _aspects(aspects: list[str] | None) -> list[str]:
        if aspects is None:
            return list(ASPECTS)
        bad = [a for a in aspects if a not in ASPECTS]
        if bad or not aspects:
            raise ValueError(f"aspects are some of {', '.join(ASPECTS)}")
        return [a for a in ASPECTS if a in aspects]

    @staticmethod
    def _paths(aspects: list[str]) -> list[str]:
        return [p for a in aspects for p in ASPECTS[a][1]]

    @staticmethod
    def _which(aspects: list[str]) -> str:
        return "" if len(aspects) == len(ASPECTS) else " (" + ", ".join(ASPECTS[a][0].lower() for a in aspects) + ")"

    def evolve_now(self) -> dict:
        """One evolution step now, whatever the rate."""
        with self.lock:
            self._evolve()
            return self.status()

    def undo(self) -> dict:
        """Back to before the last change, yours or evolution's (locks and
        evolution settings stay)."""
        with self.lock:
            if self.history:
                h = self.history.pop()
                s = copy.deepcopy(h["before"])
                s["locks"], s["evolve"] = list(self.state["locks"]), dict(self.state["evolve"])
                self._set(s)
            return self.status()

    def play(self) -> dict:
        if not self.engine.running:
            try:
                peers.claim(self.peers)
            except peers.PeerBusy as e:
                raise EngineError(str(e))
        with self.lock:
            self.error = None
            if not self.engine.running:
                try:
                    self.engine.start()
                except EngineError as e:
                    self.error = str(e)
                    raise
                self.conductor.reset()
                self.conductor.apply(self.state)
            self.engine.set("fade_s", FADE_S)
            self.engine.set("fade", 1.0)
            self.playing, self.release_at = True, None
            self.version += 1
            return self.status()

    def stop(self, fade_s: float = FADE_S) -> dict:
        with self.lock:
            if self.playing or self.release_at:
                self.engine.set("fade_s", fade_s)
                self.engine.set("fade", 0.0)
                self.playing = False
                # the fade is on the output, so silence comes when it ends
                end = time.monotonic() + fade_s + 0.5
                self.release_at = min(self.release_at or end, end)
            self.sleep_at = None
            self.version += 1
            return self.status()

    def yield_speakers(self, timeout: float = 6.0) -> None:
        """The recorder wants the speakers: a quick fade, then let go."""
        self.stop(QUICK_FADE_S)
        end = time.monotonic() + timeout
        while self.engine.running and time.monotonic() < end:
            time.sleep(0.1)

    def sleep(self, minutes: float) -> dict:
        with self.lock:
            self.sleep_at = time.monotonic() + minutes * 60 if minutes > 0 else None
            self.version += 1
            return self.status()

    def close(self) -> None:
        self._stop.set()
        self.thread.join(timeout=2)
        self.engine.stop()

    # Inside

    def _set(self, state: dict) -> None:
        self.state = state
        self.conductor.apply(state)
        self.version += 1
        self._save()

    def _evolve(self) -> None:
        before = self.state
        ev = before["evolve"]
        new, items = evolve.step_detailed(before, self.rng, ev["size"], evolve.changes_at_once(ev.get("count", 0.0)),
                                          ev.get("target"), ev.get("pull", 0.5))
        if new is not None:
            self._record(before, new, "evolution", items=items)
            self._set(new)

    def _record(self, before: dict, new: dict, by: str, what: str | None = None, items=None) -> None:
        """Into the history (the strip, the list, Undo): what changed, and who
        changed it. A slider dragged by hand is one change, not dozens: a
        change to the same settings within a few seconds joins the last."""
        now = time.monotonic()
        last = self.history[-1] if self.history else None
        hid = None
        if items is None:
            items = evolve.diff(before, new)
            if not items:
                return
            if (by == "you" and what is None and last and last["by"] == "you" and last["what_given"] is None
                    and now - last["at"] < 4 and {p for p, _ in items} == {i["path"] for i in last["items"]}):
                items = evolve.diff(last["before"], new)
                before, hid = last["before"], last["id"]  # the same change, still going
                self.history.pop()
                if not items:
                    return
        if hid is None:
            self.history_id += 1
            hid = self.history_id
        self.history.append({"id": hid, "at": now, "before": before, "by": by, "what_given": what,
                             "what": what or "; ".join(text for _, text in items),
                             "items": [{"path": p, "text": text} for p, text in items],
                             "pos": evolve.position(new)})

    def _evolve_due(self, now: float) -> None:
        """Evolution, while playing: a change when due, on a bar's first beat."""
        rate = self.state["evolve"]["rate"]
        if not self.playing or rate <= 0:
            self.next_evolve = None
            return
        if self.next_evolve is None:
            self.evolve_period = evolve.interval_s(rate) * self.rng.uniform(0.7, 1.3)
            self.next_evolve = now + self.evolve_period
        # the conductor's next step to plan is a downbeat: the change lands on it
        if now >= self.next_evolve and self.conductor.step == 0:
            self._evolve()
            self.evolve_period = evolve.interval_s(rate) * self.rng.uniform(0.7, 1.3)
            self.next_evolve = now + self.evolve_period

    def _loop(self) -> None:
        while not self._stop.wait(0.2):
            with self.lock:
                now = time.monotonic()
                if self.sleep_at is not None and now >= self.sleep_at:
                    self.stop()
                if self.engine.running and (self.playing or self.release_at):
                    try:
                        self.conductor.tick()
                    except Exception as e:  # keep playing what is scheduled
                        self.error = f"conductor: {e}"
                try:
                    self._evolve_due(now)
                except Exception as e:
                    self.error = f"evolution: {e}"
                if self.release_at is not None and now >= self.release_at:
                    self.conductor.silence_texture()
                    self.engine.stop()
                    self.release_at = None
                    self.version += 1
                if self.playing and not self.engine.running:  # the engine died
                    self.playing = False
                    self.version += 1

    def _load(self) -> dict:
        try:
            saved = json.loads(self.state_file.read_text())
            return merge(DEFAULT, upgrade(saved))
        except Exception:
            return merge(DEFAULT, {})

    def _saved_file(self) -> Path | None:
        return self.state_file.with_name("saved.json") if self.state_file else None

    def _load_saved(self) -> dict:
        try:
            saved = json.loads(self._saved_file().read_text())
        except Exception:
            return {}
        out = {}
        for name, p in saved.items():  # each checked against today's settings: one that no longer fits is dropped
            try:
                new = merge(DEFAULT, upgrade(apply_values(dict(DEFAULT, locks=[]), p["values"])))
                out[name] = {"parts": p["parts"], "values": {k: get_path(new, k) for k in p["values"]}}
            except Exception:
                pass
        return out

    def _save_saved(self) -> None:
        f = self._saved_file()
        if f:
            try:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(self.saved, ensure_ascii=False, indent=1))
            except OSError:
                pass

    def _save(self) -> None:
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state))
        except OSError:
            pass
