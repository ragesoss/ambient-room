"""The Ugly Duckling String Band's members taking breaks in turn (2026-10-22; the transcription project's
`transcribe.bandbreaks`, card `ud-member-breaks`): the tunes with a melody, a member's voice on its own fonts, the
option offered and taken at Start, and off the band as before."""

from pathlib import Path

import numpy as np
import pytest

from ambient.bandengine import BandEngine, Voice
from ambient.output import PacedOutput
from ugly_duckling import duplex

from test_ud import (DESKTOP, FONTS, RATE, VOICES, _keep_out_of_home, fluidsynth_here, load_config,  # noqa: F401
                     run_engine, transcription_here)

MEMBER_FONTS = ("dobro.sf2", "acoustic.sf2", "generaluser.sf2", "mandolin.sf2")


def breaks_here() -> bool:
    """A transcription project here with the members' breaks."""
    if not transcription_here():
        return False
    cfg = load_config(DESKTOP)
    return (Path(cfg.transcribe).expanduser() / "transcribe" / "bandbreaks.py").is_file()


def members_here() -> bool:
    """FluidSynth, the members' fonts (mandolin.sf2: `tools/soundfonts --band`) and the members' breaks."""
    if not (fluidsynth_here() and breaks_here()):
        return False
    cfg = load_config(DESKTOP)
    return all((cfg.sounds_dir / f).is_file() for f in MEMBER_FONTS)


needs_members = pytest.mark.skipif(not members_here(), reason="needs the members' fonts and the transcription "
                                   "project's bandbreaks")


@pytest.mark.skipif(not breaks_here(), reason="needs the transcription project with the members' breaks")
def test_a_tunes_melody_is_its_dobro_key_when_it_is_one_pass_of_the_chart():
    """The ambient synth's four tunes have a melody, one pass of the band's chart; the others none."""
    from ugly_duckling.tunes import load_tunes, melody_for
    cfg = load_config(DESKTOP)
    tunes, _ = load_tunes(Path(cfg.tunes_root), cfg.tunes, cfg.transcribe)
    have = {tid for tid, t in tunes.items() if melody_for(t) is not None}
    assert have == {"red-wing", "down-yonder", "big-sciota", "cherokee-shuffle"} & set(tunes)
    mel = melody_for(tunes["red-wing"])
    assert mel.bars == 16 and mel.beats == len(tunes["red-wing"].chart) and mel.key == 7


@needs_members
def test_a_members_break_plays_on_its_own_fonts():
    """The dobro's program 25 on its own synth with the dobro's font: the player's dobro, not the chords' steel guitar
    (program 25 too), which the parts' synths load."""
    from ambient.fluid import Synth
    cfg = load_config(DESKTOP)
    dobro = Voice(3, 25, 0.0, 0.0, (str(cfg.sounds_dir / "dobro.sf2"),))
    eng = BandEngine(FONTS, VOICES | {"dobro": dobro}, PacedOutput(RATE, 512, realtime=False), 128, RATE, 0.0)
    eng.play([(0.01, 0.4, "dobro", 67, 96)], 0.03, tag=(0, "dobro"))
    y = run_engine(eng, int(0.6 * RATE) // 128).mean(axis=1)
    on = next(lg.start for lg in eng.log if lg.part == "dobro")
    assert on is not None and eng.counts["dobro"]["on time"] == 1
    heard = {}
    for name, fonts in (("dobro", [cfg.sounds_dir / "dobro.sf2"]), ("steel", FONTS)):
        s = Synth(fonts, RATE)
        s.program(3, 25)
        s.render(on)
        s.noteon(3, 67, 96)
        heard[name] = s.render(int(0.3 * RATE)).mean(axis=1)
        s.close()
    x = y[on: on + int(0.3 * RATE)]
    assert np.corrcoef(x, heard["dobro"])[0, 1] > 0.99
    assert abs(np.corrcoef(x, heard["steel"])[0, 1]) < 0.5


@needs_members
def test_the_members_breaks_are_offered_and_taken_at_start():
    """Off by default (the engine the band's three parts, as before); offered with the five members and the tunes
    with a melody; on at Start with who rotates (in the rotation's order), anything else refused; the session's band
    given the breaks, its engine a voice a member on its own fonts; the status says the breaks are on."""
    from fastapi.testclient import TestClient
    from ugly_duckling.server import Band, create_app
    cfg = load_config(DESKTOP)
    with TestClient(create_app(cfg)) as c:
        o = c.get("/api/options").json()["breaks"]
        assert o["available"] and o["why"] is None
        assert [m["id"] for m in o["members"]] == ["dobro", "fiddle", "guitar", "mandolin", "banjo"]
        assert "red-wing" in o["tunes"] and "g-c-g-d" not in o["tunes"]
        for bad in ({"breaks": "yes"}, {"breaks": True, "break_members": ["piano"]},
                    {"breaks": True, "break_members": "dobro"}):
            r = c.post("/api/start", json={"tune": "red-wing"} | bad)
            assert r.status_code == 400 and "break" in r.json()["detail"], bad
    band = Band(cfg)
    band.start({"tune": "red-wing", "listen_stop": False})
    s = band.session
    try:
        assert s.breaks is None and set(s.engine.voices) == {"bass", "comp", "chop"}
        assert band.status()["breaks"] == {"on": False}
    finally:
        band.stop()
    band.start({"tune": "red-wing", "listen_stop": False, "breaks": True, "break_members": ["banjo", "fiddle"]})
    s = band.session
    try:
        assert s.s.breaks and s.s.break_members == ["fiddle", "banjo"]
        assert s.breaks.members == ("fiddle", "banjo") and s.breaks.melody.name == "red-wing"
        assert set(s.engine.voices) == {"bass", "comp", "chop", "fiddle", "banjo"}
        assert s.engine.voices["fiddle"].fonts == (str(cfg.sounds_dir / "acoustic.sf2"),)
        assert duplex.wait_for(lambda: s.state == "playing", 6.0, 0.05)
        st = band.status()["breaks"]
        assert st["on"] and st["members"] == ["Fiddle", "Banjo"]
    finally:
        band.stop()
    assert s.error is None
