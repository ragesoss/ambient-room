from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from ambient.config import REPO, load_config
from ambient.server import create_app


@pytest.fixture
def client(tmp_path):
    cfg = replace(load_config(REPO / "config" / "dev.toml"), state_file=tmp_path / "state.json")
    with TestClient(create_app(cfg)) as c:
        yield c


def test_page_options_and_status(client):
    assert "Ambient room" in client.get("/").text
    o = client.get("/api/options").json()
    assert [x["id"] for x in o["families"]] == ["equal", "just"]
    assert [x["pitch"] for x in o["palette"]["2"]] == ["ET", "9/8", "10/9"]
    assert o["layers"]["melody"]["voices"][0]["id"] == "Off" and o["patterns"]["drums"][0]["id"] == "Off"
    assert {"harmony", "melody", "beat", "sound"} == set(o["parts"]) and len(o["presets"]) > 20
    assert [a["id"] for a in o["aspects"]] == ["key", "harmony", "melody", "beat", "sound"]
    assert any(x["name"] == "Lydian" for x in o["scales"])
    s = client.get("/api/status").json()
    assert s["playing"] is False and s["state"]["key"]


def test_change_play_mood_surprise_stop(client):
    s = client.patch("/api/state", json={"key": "A", "shape": {"bright": 0.9}}).json()
    assert s["state"]["key"] == "A" and s["state"]["shape"]["bright"] == 0.9
    assert client.patch("/api/state", json={"scale": "grumpy"}).status_code == 400
    assert client.post("/api/play").json()["playing"] is True
    vol = s["state"]["volume"]
    m = client.post("/api/preset/Deep").json()
    assert sorted(map(int, m["state"]["tones"])) == [0, 2, 3, 5, 7, 8, 10] and m["state"]["volume"] == vol
    assert m["explain"]["scale"]["name"] == "Natural minor (Aeolian)"
    assert client.post("/api/preset/Nope").status_code == 404
    v0 = m["version"]
    assert client.post("/api/surprise").json()["version"] > v0
    s = client.post("/api/stop").json()
    assert s["playing"] is False and s["fading"] is True


def test_settings_survive_a_restart(tmp_path):
    cfg = replace(load_config(REPO / "config" / "dev.toml"), state_file=tmp_path / "state.json")
    with TestClient(create_app(cfg)) as c:
        c.patch("/api/state", json={"key": "Bb"})
    with TestClient(create_app(cfg)) as c:
        assert c.get("/api/status").json()["state"]["key"] == "Bb"


def test_tones_can_be_edited_one_by_one(client):
    s = client.patch("/api/state", json={"scale": "major"}).json()
    assert s["explain"]["scale"]["name"] == "Major (Ionian)"
    tones = dict(s["state"]["tones"])
    del tones["11"]
    tones["10"] = ["9/5", "16/9"]
    s = client.patch("/api/state", json={"tones": tones}).json()
    assert s["explain"]["scale"]["name"] == "Mixolydian"
    assert s["explain"]["scale"]["tuning"] == "just intonation, your ratios"
    s = client.patch("/api/state", json={"scale": "dorian", "family": "equal"}).json()
    assert s["state"]["tones"]["3"] == ["ET"] and s["explain"]["scale"]["tuning"] == "equal temperament"
    assert client.patch("/api/state", json={"tones": {"4": ["6/5"]}}).status_code == 400


def test_events_follow_the_music(client):
    client.patch("/api/state", json={"beat": {"drums": "House"}, "shape": {"tempo": 0.7}})
    client.post("/api/play")
    import time
    time.sleep(0.5)
    e = client.get("/api/events?since=0").json()
    kinds = {x["kind"] for x in e["events"]}
    assert {"step", "drum"} <= kinds and e["audible"] is not None
    later = client.get(f"/api/events?since={e['seq']}").json()
    assert all(x["seq"] > e["seq"] for x in later["events"])


def test_your_changes_are_in_the_history_and_undo_covers_them(client):
    before = client.get("/api/status").json()["state"]
    for x in (0.5, 0.6, 0.7):  # a slider dragged: one change
        s = client.patch("/api/state", json={"shape": {"bright": x}}).json()
    h = s["evolving"]["history"]
    assert len(h) == 1 and h[0]["by"] == "you" and h[0]["items"][0]["path"] == "shape.bright"
    assert h[0]["what"] == f"Brightness {before['shape']['bright']:.2f} → 0.70"
    s = client.patch("/api/state", json={"key": "F#"}).json()
    assert s["evolving"]["history"][0]["what"].startswith("Key:")
    s = client.post("/api/preset/Deep").json()
    assert s["evolving"]["history"][0]["what"] == "Preset: Deep" and len(s["evolving"]["history"]) == 3
    s = client.post("/api/evolve/undo").json()
    assert s["state"]["key"] == "F#"
    s = client.post("/api/evolve/undo").json()
    s = client.post("/api/evolve/undo").json()
    assert s["state"]["shape"]["bright"] == before["shape"]["bright"] and not s["evolving"]["history"]
    # settings that are not music (locks, evolution) are not changes
    s = client.patch("/api/state", json={"evolve": {"rate": 0.2}, "locks": {"key": True}}).json()
    assert not s["evolving"]["history"]


def test_presets_whole_or_only_some_aspects_and_your_own(client):
    s = client.patch("/api/state", json={"key": "F#"}).json()
    before = s["state"]
    s = client.post("/api/preset/Rock band", json={"aspects": ["beat"]}).json()
    assert s["state"]["beat"]["drums"] == "Rock" and s["state"]["key"] == "F#"
    assert s["state"]["layers"] == before["layers"] and s["state"]["harmony"] == before["harmony"]
    assert s["evolving"]["history"][0]["what"] == "Preset: Rock band (beat)"
    s = client.post("/api/preset/Rock band", json={"aspects": ["harmony", "sound"]}).json()
    assert s["state"]["harmony"]["loop"] == [1, 4, "V", 4] and s["state"]["layers"]["bass"]["voice"] == "Electric"
    assert s["state"]["key"] == "F#" and s["explain"]["preset_match"]["Rock band"] == ["harmony", "beat", "sound"]
    s = client.post("/api/preset/Rock band").json()  # all of it: the key too
    assert s["state"]["key"] == "G" and len(s["explain"]["preset_match"]["Rock band"]) == 5
    assert client.post("/api/preset/Rock band", json={"aspects": ["tempo"]}).status_code == 400
    s = client.post("/api/saved", json={"name": "My rock"}).json()
    assert [y["name"] for y in s["saved"]] == ["My rock"]
    client.post("/api/preset/Dawn")
    s = client.post("/api/saved/My rock", json={"aspects": ["beat"]}).json()
    assert s["state"]["beat"]["drums"] == "Rock" and s["state"]["key"] == "E"  # Dawn's key stays
    v = s["state"]
    s = client.post("/api/surprise", json={"aspects": ["melody"]}).json()
    assert s["state"]["beat"] == v["beat"] and s["state"]["key"] == v["key"] and s["state"]["layers"] == v["layers"]
    assert client.delete("/api/saved/My rock").json()["saved"] == []



def test_stop_is_quick(client):
    import time
    client.post("/api/play")
    s = client.post("/api/stop").json()
    assert s["playing"] is False and s["fading"] is True
    t0 = time.monotonic()
    while client.get("/api/status").json()["fading"] and time.monotonic() - t0 < 3:
        time.sleep(0.05)
    assert time.monotonic() - t0 < 1.5  # 0.3 s fade, then the speakers are let go
