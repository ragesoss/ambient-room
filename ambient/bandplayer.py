"""The band player: the live band's decisions (cues, from the transcription project's `transcribe.liveband`) sounded
on time by the band engine (`ambient/bandengine.py`).

A cue says which part plays what on which beat, when it should sound (`t`, in the input stream's seconds: its
sample 0 is 0 s) and when it was decided. The player:

- voices it as the transcription project's offline render does, with its own function (`transcribe.bandvoice`,
  imported from that project, `[band] transcribe` in the config): the same notes, lengths and velocities, on the
  same SoundFont programs, pans and levels, so a live run and an offline render compare note for note;
- maps the stream's clock to the engine's (`StreamClock`) and queues the notes as one group, with the lateness
  its part may sound at (`LATE_S`); the engine drops a group later than that (`ambient/bandengine.py`).

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
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .bandengine import BandEngine, Voice

# How late each part may sound, past its time, before its play is dropped instead (s). A bass note a little late
# sounds laid back; a chop late on the "and" smears the off-beat, so it may be later only by less. First settings
# (2026-10-16), under the 25-40 ms an ensemble tolerates (the accompaniment survey, in the transcription project).
LATE_S = {"bass": 0.030, "comp": 0.030, "chop": 0.015}

# Each part's level on its own FluidSynth (dB), so the parts sit as the offline render sets them by loudness (the
# bass, the chords 3 dB under it, the chop 5 dB under), measured on the harness takes' renders
# (`tools/band_replay.py levels`, 2026-10-16). Set in `voices()`.
PART_GAIN_DB: dict[str, float] = {"bass": 0.0, "comp": -8.3, "chop": -9.5}


def load_voicing(src: str | Path):
    """The transcription project's voicing module (`transcribe.bandvoice`), from its `pipeline/src`."""
    src = str(Path(src).expanduser())
    if src not in sys.path:
        sys.path.insert(0, src)
    from transcribe import bandvoice
    return bandvoice


def voices(bandvoice, gain_db: dict[str, float] | None = None) -> dict[str, Voice]:
    """The engine's voices from the voicing's (channel, program, pan, loudness offset) and the parts' gains."""
    g = PART_GAIN_DB if gain_db is None else gain_db
    return {part: Voice(ch, prog, pan, g.get(part, 0.0)) for part, (ch, prog, pan, _) in bandvoice.VOICE.items()}


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


@dataclass
class BandPlayer:
    """Cues in (`cue`), notes out to the engine. `spb`: the tune's beat (s), which sets the notes' lengths, as in
    the offline render (the tempo the band counts in at)."""
    engine: BandEngine
    clock: StreamClock
    spb: float
    voicing: object  # transcribe.bandvoice
    late_s: dict[str, float] = field(default_factory=lambda: dict(LATE_S))
    log: list[CueLog] = field(default_factory=list)

    def cue(self, c) -> None:
        notes = self.voicing.play_notes(c.part, c.play, c.t, self.spb, getattr(c, "bar", None))
        if not notes:
            return
        group = [(self.clock.engine_time(t), length, c.part, key, vel) for t, length, _, key, vel in notes]
        now = time.monotonic()
        committed = self.engine.committed / self.engine.rate
        started = self.engine.started_at()
        delay = None if started is None else started + committed - now
        self.log.append(CueLog(c, now, min(g[0] for g in group) - committed, delay))
        self.engine.play(group, self.late_s.get(c.part, 0.0), tag=(c.i, c.part))
