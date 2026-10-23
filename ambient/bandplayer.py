"""The band player: the live band's decisions (cues, from the transcription project's `transcribe.liveband`) sounded
on time by the band engine (`ambient/bandengine.py`).

A cue says which part plays what on which beat, when it should sound (`t`, in the input stream's seconds: its
sample 0 is 0 s) and when it was decided. The player:

- voices it as the transcription project's offline render does, with its own function (`transcribe.bandvoice`,
  imported from that project, `[band] transcribe` in the config): the same notes, lengths and velocities, on the
  same SoundFont programs, pans and levels, so a live run and an offline render compare note for note;
- places them in the band's pocket (`ambient/pocket.py`: where each part sits against the beat, the default none),
  in the band's own time, a play's notes on the beat or on its "and" each by one shift (a strum keeps its spread);
- maps the stream's clock to the engine's (`StreamClock`) and queues the notes as one group, with the lateness
  its part may sound at (`LATE_S`, against the shifted time); the engine drops a group later than that
  (`ambient/bandengine.py`).

The clock is the seam between listening and playing. A cue meant for stream time t is heard at engine time
`t + offset`:

- In a replay (`tools/band_replay.py`) the stream's clock is the wall clock: sample n of the take is given to the
  band when its last sample would have been captured, and the engine's frame m is heard at `started_at + m / rate`
  (the output's start). So `offset = (wall time of the stream's sample 0) - (wall time of the engine's frame 0)`.
- Live, capture and playback both run on the 18i8's one sample clock. The offset is then fixed by when each
  stream started and by the round trip through the converters (the 18i8 returns its own playback digitally on
  capture channels 11-12, a way to measure it), and it does not drift.
- Input latency: the capture hands the band a block only once it is full, and the converters add their own; both
  come out of the cue's lead before it reaches the player (`t - decided_at` is the most there is, `lead_s` in
  `transcribe.band.BandParams`), as do the band's compute, the engine's block and the output's buffer.
- The pocket is not latency: it moves a part around the band's beat, and a part moved early spends that much of
  what is left of the lead (each cue's `margin` is after it; `ambient/pocket.py`, "The lead an early part takes").
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .bandengine import BandEngine, Voice
from .pocket import Pocket

# How late each part may sound, past its time, before its play is dropped instead (s). A bass note a little late
# sounds laid back; a chop late on the "and" smears the off-beat, so it may be later only by less. First settings
# (2026-10-16), under the 25-40 ms an ensemble tolerates (the accompaniment survey, in the transcription project).
LATE_S = {"bass": 0.030, "comp": 0.030, "chop": 0.015}
# a member's break (2026-10-22): a beat's notes a group, late by as much as the bass (a line, not an off-beat)
BREAK_LATE_S = 0.030

# Each part's level on its own FluidSynth (dB), so the parts sit as the offline render sets them by loudness (the
# bass, the chords 3 dB under it, the chop 5 dB under), measured on the harness takes' renders
# (`tools/band_replay.py levels`, 2026-10-16). Set in `voices()`.
PART_GAIN_DB: dict[str, float] = {"bass": 0.0, "comp": -8.3, "chop": -9.5}
# The members' breaks (2026-10-22): each 2 dB over the bass by loudness (the transcription project's
# `bandvoice.BREAK_VOICE`), measured as the parts' were: each member's gain against the bass's in that project's
# offline render of the breaks over Red Wing and Cherokee Shuffle (`tools/band_breaks.py render`, `breaks.json`'s
# `member_gain_db_over_bass`: the dobro +1.8 and +2.3, the fiddle -5.4 and -4.2, the guitar +0.7 and +1.3, the mandolin
# +0.1 and +0.6, the banjo -1.1 and -1.4), the mean of the two.
BREAK_GAIN_DB: dict[str, float] = {"dobro": 2.0, "fiddle": -4.8, "guitar": 1.0, "mandolin": 0.4, "banjo": -1.2}


def load_voicing(src: str | Path):
    """The transcription project's voicing module (`transcribe.bandvoice`), from its `pipeline/src`."""
    src = str(Path(src).expanduser())
    if src not in sys.path:
        sys.path.insert(0, src)
    from transcribe import bandvoice
    return bandvoice


def voices(bandvoice, gain_db: dict[str, float] | None = None, members=(), sounds_dir=None) -> dict[str, Voice]:
    """The engine's voices from the voicing's (channel, program, pan, loudness offset) and the parts' gains; and for
    `members` (the members' breaks, `bandvoice.BREAK_VOICE`), each member's, on its own fonts in `sounds_dir`."""
    g = PART_GAIN_DB if gain_db is None else gain_db
    out = {part: Voice(ch, prog, pan, g.get(part, 0.0)) for part, (ch, prog, pan, _) in bandvoice.VOICE.items()}
    for m in members:
        ch, prog, pan, _, fonts = bandvoice.BREAK_VOICE[m]
        out[m] = Voice(ch, prog, pan, g.get(m, BREAK_GAIN_DB.get(m, 0.0)),
                       tuple(str(Path(sounds_dir or ".") / f) for f in fonts))
    return out


def break_fonts(bandvoice, members) -> list[str]:
    """The fonts the members' breaks need (`bandvoice.BREAK_VOICE`), each once."""
    out = []
    for m in members:
        for f in bandvoice.BREAK_VOICE[m][4]:
            if f not in out:
                out.append(f)
    return out


@dataclass
class StreamClock:
    """Stream time (the input's seconds) to engine time (the band engine's seconds): `engine = stream + offset`
    (module docstring)."""
    offset: float

    @classmethod
    def replay(cls, stream_zero: float, engine_zero: float) -> "StreamClock":
        """A replay: the wall (monotonic) times of the stream's sample 0 and the engine's frame 0."""
        return cls(stream_zero - engine_zero)

    def engine_time(self, t: float) -> float:
        return t + self.offset

    def stream_time(self, e: float) -> float:
        return e - self.offset


@dataclass
class CueLog:
    cue: object
    arrived: float  # monotonic
    margin: float  # engine time of its first note less the first engine time still open when it arrived (s)
    delay: float | None  # from its arrival until the first frame still open is heard (s): the engine's delay
    shift_ms: float = 0.0  # the pocket's move of its notes (ms, + late; in `margin` already)
    at: float = 0.0  # engine time of its first note (s)


@dataclass
class BandPlayer:
    """Cues in (`cue`), notes out to the engine. `spb`: the tune's beat (s), which sets the notes' lengths, as in
    the offline render (the tempo the band counts in at). `pocket`: where each part sits against the beat
    (`ambient/pocket.py`); None, every note on it."""
    engine: BandEngine
    clock: StreamClock
    spb: float
    voicing: object  # transcribe.bandvoice
    late_s: dict[str, float] = field(default_factory=lambda: dict(LATE_S))
    log: list[CueLog] = field(default_factory=list)
    pocket: Pocket | None = None

    def cue(self, c) -> None:
        notes = self.voicing.play_notes(c.part, c.play, c.t, self.spb, getattr(c, "bar", None))
        if not notes:
            return
        shift = 0.0
        if self.pocket is not None:  # in the band's time, before the clock: the same as an offline render's
            notes, shift = self.pocket.place(notes, c.part, c.i, getattr(c, "beat_t", c.t), self.spb)
        group = [(self.clock.engine_time(t), length, c.part, key, vel) for t, length, _, key, vel in notes]
        now = time.monotonic()
        committed = self.engine.committed / self.engine.rate
        started = self.engine.started_at()
        delay = None if started is None else started + committed - now
        first = min(g[0] for g in group)
        self.log.append(CueLog(c, now, first - committed, delay, shift, first))
        late = self.late_s.get(c.part, BREAK_LATE_S if c.part in getattr(self.voicing, "BREAK_VOICE", {}) else 0.0)
        self.engine.play(group, late, tag=(c.i, c.part))
