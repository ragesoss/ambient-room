"""The conductor: turns the settings into notes, a second ahead, on a grid.

Time runs on a grid of sixteenth notes at the tempo, 16 to the bar. tick()
is called a few times a second; it plays every step that starts within
LOOKAHEAD seconds of the engine's clock, so the engine places each note
exactly. Chords change on the first beat of a bar. apply() pushes the
settings to the engine's channels, which glide.

Each part in time has a voice (state["layers"]) and a pattern
(state["beat"]): the patterns' notes are here, the voices' sounds in the
orchestra.
"""

import math
import random
from collections import deque

from . import music
from .harmony import (Harmonist, at_step, chord_bars, chord_scale, item_slot, loop_chord, numeral as degree_numeral,
                      played, timeline)
from .melody import Melodist
from .sounds import HELD, LEVEL, OFF, gain, instr, kind, phrase_trim, trim

LOOKAHEAD = 1.0
STEPS = 16  # sixteenth notes to the bar

# Scattered melody: how long each voice's notes last, in seconds
MELODY_DUR = {"Bell": (4, 7), "Pluck": (2.5, 4), "Kalimba": (2, 3.5), "Flute": (1.2, 3.5), "Felt": (3, 5),
              "E. piano": (2, 4), "Vibes": (3, 5), "Strings": (1.5, 4), "Marimba": (1, 1.6), "Steel drum": (1.2, 2),
              "Harp": (2, 4), "Voice": (1.5, 3.5), "Organ lead": (1, 3), "Guitar": (1.5, 3),
              "Fiddle": (1, 3), "Mandolin": (0.8, 2), "Banjo": (0.6, 1.5), "Acoustic guitar": (1.5, 3),
              "Dobro": (1.5, 3.5), "Harmonica": (1, 3), "Nylon guitar": (1.5, 3)}
MELODY_STEPS = {"Lead": (2, 6), "Synth pluck": (2, 4), "Chip": (1, 4), "Brass": (2, 6), "Sync lead": (2, 6),
                "Saw stack": (2, 6)}  # rhythmic voices: lengths in steps
# Shaped melody: struck and plucked voices ring at least this long, whatever the note's length
MELODY_RING = {"Bell": 2.5, "Pluck": 1.5, "Kalimba": 1.5, "Felt": 1.8, "E. piano": 1.6, "Vibes": 2.5,
               "Marimba": 1.0, "Steel drum": 1.4, "Harp": 2.0, "Guitar": 1.6, "Synth pluck": 0.5,
               "Mandolin": 0.6, "Banjo": 0.5, "Acoustic guitar": 1.2, "Dobro": 1.4, "Nylon guitar": 1.2}

# Drum patterns, one bar of sixteenths each: a digit is a hit's strength
# (1-9), "." a rest.
DRUMS = {
    "Pulse": {"kick": "8.......6.......", "hat": "....3.......3...", "rim": ".......3.......2"},
    "Downtempo": {"kick": "8.....6...8.....", "snare": "....8.......8...", "hat": "4.3.4.3.4.3.4.3.",
                  "rim": "...3.......3...."},
    "Breaks": {"kick": "9.....7...7.....", "snare": "....9.......9..4", "hat": "5.4.5.4.5.4.5.4."},
    "Half-time": {"kick": "9.........7.....", "snare": "........9.......", "hat": "4.4.4.4.4.4.4.4."},
    "House": {"kick": "9...9...9...9...", "clap": "....8.......8...", "ohat": "..6...6...6...6.",
              "hat": ".3.3.3.3.3.3.3.3"},
    "Techno": {"kick": "9...9...9...9...", "clap": "....5.......5...", "ohat": "..6...6...6...6.",
               "hat": "4545454545454545", "rim": "...4..4....4..4."},
    "Rock": {"kick": "9.......9.7.....", "snare": "....9.......9...", "hat": "6.4.6.4.6.4.6.4."},
    "Funk": {"kick": "9.....6...9..6..", "snare": "....9..3.3..9..3", "hat": "5353535353535353"},
    "One drop": {"kick": "........9.......", "rim": "........8.......", "hat": "..4...4...4...4."},
    "Disco": {"kick": "9...9...9...9...", "snare": "....8.......8...", "ohat": "..6...6...6...6.",
              "hat": "4...4...4...4..."},
    "Trap": {"kick": "9......7..9.....", "snare": "........9.......", "hat": "4.4.4.4.4.4.4444"},
    "Swing": {"ohat": "6...4.5.6...4.5.", "kick": "3...............", "snare": ".......3.......3",
              "hat": "....5.......5..."},
    "Train": {"kick": "8.......6.......", "snare": "2242224222422242"},
}
# Drum kits: part -> (instrument, level, length s, decay s, kick pitch Hz)
KITS = {
    "Electronic": {"kick": (61, 0.9, 0.6, 0.35, 50), "snare": (62, 0.6, 0.4, 0.18, 0), "clap": (63, 0.7, 0.35, 0, 0),
                   "hat": (64, 0.35, 0.12, 0.045, 0), "ohat": (64, 0.3, 0.5, 0.32, 0), "rim": (66, 0.4, 0.15, 0, 0)},
    "Acoustic": {"kick": (91, 0.9, 0.5, 0.28, 58), "snare": (92, 0.6, 0.45, 0.2, 0), "clap": (92, 0.5, 0.4, 0.15, 0),
                 "hat": (94, 0.3, 0.15, 0.05, 0), "ohat": (94, 0.28, 0.7, 0.45, 0), "rim": (96, 0.45, 0.15, 0, 0)},
}

# Bass lines, one bar: (step, chord tone, length in steps, strength). Chord
# tones: R the root, 3 5 7 the chord's next notes, 8 the octave, -5 the
# fifth below. Walking and Acid line are made as they go.
BASS_LINES = {
    "Root–fifth": [(0, "R", 8, 1.0), (8, "-5", 8, 0.85)],
    "Half-time": [(0, "R", 10, 1.0), (10, "R", 6, 0.75)],
    "Eighths": [(k, "R", 2, 1.0 if k % 4 == 0 else 0.75) for k in range(0, 16, 2)],
    "Octaves": [(k, "R" if k % 4 == 0 else "8", 2, 1.0 if k % 4 == 0 else 0.85) for k in range(0, 16, 2)],
    "Offbeat": [(k, "R", 2, 1.0) for k in (2, 6, 10, 14)],
    "Rolling": [(k, "R", 1, (6 + k % 4) / 9) for k in range(16) if k % 4],
    "Tresillo": [(0, "R", 3, 1.0), (3, "R", 3, 0.8), (6, "5", 2, 0.8), (8, "R", 3, 0.95), (11, "R", 3, 0.8),
                 (14, "8", 2, 0.75)],
    "Funk": [(0, "R", 2, 1.0), (3, "R", 1, 0.45), (4, "8", 1, 0.95), (6, "R", 1, 0.7), (7, "5", 1, 0.5),
             (10, "R", 2, 0.9), (12, "8", 1, 0.9), (13, "7", 1, 0.6), (14, "5", 2, 0.75)],
    "Dub": [(2, "R", 4, 0.95), (6, "R", 2, 0.7), (8, "5", 2, 0.8), (10, "8", 2, 0.75), (12, "3", 4, 0.85)],
    "Arpeggio": [(k, ("R", "3", "5", "8", "5", "3", "R", "5")[k // 2], 2, 1.0 if k % 4 == 0 else 0.8)
                 for k in range(0, 16, 2)],
}
BASS_SHORT = {"Offbeat": 0.75, "Funk": 0.8, "Rolling": 0.95}  # how much of its length a note sounds (else 0.92)

# Chord rhythms: a bar of hits, or (Strum) hits with a direction
STAB_PATTERNS = ["..8....8..8.....", "..8...8...8...8.", "8..8..8...8..8..", "..8..8....8..8.."]
CHORD_HITS = {"Offbeat": "..8...8...8...8.", "Eighths": "9.6.8.6.9.6.8.6.", "Chop": "....8.......8..."}
CHORD_LEN = {"Stabs": 3, "Offbeat": 1.5, "Eighths": 1.6, "Comp": 2, "Chop": 0.7}  # steps a hit sounds
# Banjo rolls, a half bar of sixteenths: T the thumb (a high drone, then a low chord note, by turns),
# I the index finger (the chord's middle note), M the middle finger (its top)
ROLLS = {"Roll": "TIMTIMTM", "Alternating roll": "TITMTITM"}
STRUM = {0: (1.0, "down"), 4: (0.8, "down"), 6: (0.6, "up"), 10: (0.6, "up"), 12: (0.85, "down"), 14: (0.6, "up")}
COMP_PATTERNS = ["......6.....5...", "...6......6.....", "6.....5...6.....", "..5.......6..5..", "...5..6........."]
ATTACK = {"Supersaw": 0.15}  # how fast a pad voice swells, against the usual


def lerp(a: float, b: float, x: float) -> float:
    return a + (b - a) * x


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# What the controls mean musically. ambient/explain.py shows these.

def bpm(tempo: float) -> float:
    """The tempo: 50 to 150 BPM."""
    return 50 + 100 * tempo


def bar_seconds(tempo: float) -> float:
    return 4 * 60 / bpm(tempo)


def melody_gap(notes: float) -> float:
    """The average time between melody notes: 12 s at 0, 0.6 s at 1."""
    return 12 * 0.05 ** notes


def swing_delay(swing: float, step_s: float) -> float:
    """How late the off sixteenths come: up to a third of a step (a triplet feel)."""
    return swing * step_s / 3


def center(height: float) -> float:
    """The MIDI note the chords are voiced around (within 10 semitones)."""
    return 50 + 18 * height


def melody_range(height: float) -> tuple[int, int]:
    c = center(height)
    return int(c + 7), int(c + 26)


def hits(pattern: str, k: int) -> float:
    c = pattern[k % len(pattern)]
    return 0.0 if c == "." else int(c) / 9


class Conductor:
    def __init__(self, engine, rng: random.Random | None = None):
        self.engine = engine
        self.rng = rng or random.Random()
        self.state: dict | None = None
        self.melodist = Melodist(self.rng)
        self.harmonist = Harmonist(self.rng)
        # what the page draws as it is heard: drum hits, notes, steps, each
        # with its score time
        self.events: deque = deque(maxlen=800)
        self.seq = 0
        self.error: str | None = None  # the last step that failed
        self.reset()

    def reset(self) -> None:
        self.next_step = self.engine.time() + 0.1
        self.step = 0  # within the bar
        self.steps = 0  # since the start
        self.bar = -1  # bars since the start: phrases and chord changes count from here
        self.melodist.reset()
        self.harmonist.reset()
        self.slot = 0  # chords since the start: each chord_bars long, on bar lines
        self.chord_end = self.next_step  # when the sounding chord gives way
        self.next_melody = self.next_step
        self.change_now = False
        self.root: int | None = None  # the chord root's slot
        self.voicing: list[int] = []  # the notes the chords part plays
        self.full: list[int] = []  # the whole chord, voiced (for the arpeggio)
        self.pitches: dict = {}  # slot -> (label, cents), for the sounding chord
        self.pcs: list[int] | None = None  # the harmony's chord: pitch classes, root first
        self.scale: list[int] = []  # the scale while this chord sounds (with a borrowed chord's notes)
        self.retune = False
        self.texture: int | None = None
        self.mel_note: int | None = None
        self.arp_i = 0
        self.acid: list = []
        self.stabs = STAB_PATTERNS[0]
        self.comp = COMP_PATTERNS[0]
        self.bass_plan: dict = {}  # step in the bar -> (MIDI note, length in steps, strength)
        self.bass_last: int | None = None
        self.now: dict | None = None  # the chord most recently started
        self.gen = 0
        self.engine.set("gen", 0)

    # Settings

    def apply(self, state: dict) -> None:
        old, self.state = self.state, state
        e, sh, L, B = self.engine, state["shape"], state["layers"], state["beat"]
        e.set("volume", state["volume"])
        for k in ("bright", "motion", "space", "echo", "pump", "drive"):
            e.set(k, sh[k])
        e.set("beat", self.beat())
        e.set("echo_s", 0.75 * self.beat())
        for layer, lc in L.items():
            silent = lc["voice"] == OFF or (layer in ("drums", "pulse") and B[layer] == OFF)
            e.set(layer, 0.0 if silent else lc["level"])
        if old is None:
            return
        # A new key, scale, tuning, chord voice or chord rhythm is heard at
        # once: the sounding chord fades in 2 s and the next one starts on
        # the next step. New pitches for the same tones, or adaptive on or
        # off, repeat the same chord, so the two can be compared.
        new_notes = old["key"] != state["key"] or music.slots_of(old["tones"]) != music.slots_of(state["tones"])
        retune = old["adaptive"] != state["adaptive"] or old["tones"] != state["tones"]
        # a new loop, or a chord in it changed, is heard at once, unless the
        # chord sounding is already the loop's (as when the chords heard are kept)
        h0, h1 = old["harmony"], state["harmony"]
        new_form = False
        if h1["style"] == "Loop" and (h0["style"] != "Loop" or h0["loop"] != h1["loop"]) and self.pcs:
            want = self.harmonist.peek(state, self.slot, self.root)
            new_form = want != self.root
        new_form = new_form or h0["plain"] != h1["plain"] or abs(h0["size"] - h1["size"]) > 0.15
        changed = (new_notes or retune or new_form
                   or any(old["layers"][x]["voice"] != L[x]["voice"] for x in ("pad", "bass"))
                   or any(old["beat"][x] != B[x] for x in ("chords", "bass")))
        if changed:
            self.gen += 1
            e.set("gen", self.gen)
            self.retune = retune and not new_notes
            self.change_now = True
        if old["melody"]["style"] != state["melody"]["style"]:
            self.melodist.reset()
        if old["shape"]["notes"] < sh["notes"]:
            self.next_melody = min(self.next_melody, self.engine.time() + 0.5)

    def beat(self) -> float:
        return 60.0 / bpm(self.state["shape"]["tempo"])

    def step_s(self) -> float:
        return self.beat() / 4

    def center(self) -> float:
        return center(self.state["shape"]["height"])

    def slots(self) -> list[int]:
        return music.slots_of(self.state["tones"])

    def hz(self, midi: int) -> float:
        return music.freq(midi, self.state["key"], self.pitches)

    def voice(self, layer: str) -> str:
        return self.state["layers"][layer]["voice"]

    def pattern(self, part: str) -> str:
        return self.state["beat"][part]

    def emit(self, t: float, kind: str, **data) -> None:
        self.seq += 1
        self.events.append({"seq": self.seq, "t": round(t, 4), "kind": kind, **data})

    def pitch_of(self, midi: int) -> dict:
        """Where a note is on the wheel: its slot, pitch label, cents."""
        slot = (midi - music.KEYS.index(self.state["key"])) % 12
        label, cents = self.pitches.get(slot, (music.ET, 100.0 * slot))
        return {"slot": slot, "pitch": label, "at": round(cents, 2)}

    def scale_notes(self, lo: int, hi: int) -> list[int]:
        """The notes of the scale as it is while this chord sounds (a borrowed chord's notes in)."""
        return music.scale_notes(self.state["key"], self.scale or self.slots(), lo, hi)

    # The grid

    def tick(self) -> None:
        now = self.engine.time()
        if self.next_step < now:  # after a pause: catch up instead of piling notes
            self.next_step = now + 0.05
        while self.next_step <= now + LOOKAHEAD:
            try:
                self.do_step(self.next_step, self.step)
            except Exception as e:  # skip the step, keep the music going, report it
                self.error = f"{type(e).__name__}: {e}"
            self.next_step += self.step_s()
            self.step = (self.step + 1) % STEPS
        self.sync_texture(now)

    def loop_step(self, k: int) -> int:
        """The sixteenths since the start, at step k of this bar: where a loop is."""
        return max(0, self.bar) * STEPS + k

    def chart_bar(self) -> tuple[int, int] | None:
        """For a loop that is a whole number of bars: (this bar's place in it, its bars)."""
        h = self.state["harmony"]
        if h["style"] != "Loop":
            return None
        total = timeline(h)[1]
        if total % STEPS:
            return None
        return (max(0, self.bar) * STEPS % total) // STEPS, total // STEPS

    def chord_due(self, k: int) -> bool:
        """A new chord starts at step k of this bar: on a bar line every so many
        bars, or where a loop's next chord starts (a chart's may be mid-bar)."""
        h = self.state["harmony"]
        if h["style"] == "Loop":
            step = self.loop_step(k)
            return step == 0 or at_step(h, step)[0] != at_step(h, step - 1)[0]
        return k == 0 and self.bar % chord_bars(h["rhythm"]) == 0

    def do_step(self, t: float, k: int) -> None:
        step = self.step_s()
        s = self.state
        shaped = s["melody"]["style"] != "Scattered"
        if k == 0:
            self.bar += 1
            # a phrase may start (with a chart, at its top): the chord can lean to its cadence
            self.melodist.begin_bar(self.bar, s, self.chart_bar())
        new_chord = self.change_now or self.pcs is None or self.chord_due(k)
        if new_chord:
            self.chord(t, k)
        if k == 0 or new_chord:
            self.plan_bass(k)
        if k == 0 and shaped:  # this bar's melody, against the chords sounding in it
            notes = self.scale_notes(*melody_range(s["shape"]["height"]))
            self.melodist.plan_bar(self.bar, self.steps, s, notes, self.chord_in_bar, self.lead_in_bar)
        tp = t + (swing_delay(s["shape"]["swing"], step) if k % 2 else 0.0)
        self.emit(t, "step", k=k)
        self.drums(tp, k)
        self.bass_line(tp, k)
        self.chords(tp, k, new_chord)
        self.pulse(t, tp, k)
        if not shaped:
            if t >= self.next_melody:
                self.melody(tp)
        else:
            self.shaped_melody(tp)
        self.steps += 1

    # Harmony

    def chord(self, t: float, k: int) -> None:
        s, rng = self.state, self.rng
        changed_now, self.change_now = self.change_now, False
        bar = bar_seconds(s["shape"]["tempo"])
        bar_start = t - k * self.step_s()
        cb = chord_bars(s["harmony"]["rhythm"])
        early = self.pcs is not None and t < self.chord_end - 0.05
        if early and not changed_now:  # the harmonic rhythm quickened: let the old chord go
            self.gen += 1
            self.engine.set("gen", self.gen)
        if s["harmony"]["style"] == "Loop":  # where the loop is: its chords have their own lengths
            self.slot, _, left = at_step(s["harmony"], self.loop_step(k))
            self.chord_end = t + left * self.step_s()
        else:  # chords fall on bar lines counted from the start, cb bars apart
            self.slot = max(0, self.bar) // cb
            self.chord_end = bar_start + (cb - max(0, self.bar) % cb) * bar
        hold = self.chord_end - t
        key = music.KEYS.index(s["key"])
        if self.retune and self.pcs:
            pcs = self.pcs  # the same chord, retuned
        else:
            # under a phrase's last bar, wandering leans to a cadence: home (I) for an answer, V or IV for a question
            wish = self.melodist.cadence_wish(self.bar, cb)
            self.root, pcs, n = self.harmonist.next(s, self.slot, self.root, wish, rng.random())
            self.voicing = music.voice(played(pcs, n), self.center(), self.voicing or None) if n else []
            self.full = music.voice(pcs, self.center(), self.full or None)
            self.acid = self.acid_line(pcs)
            self.stabs = rng.choice(STAB_PATTERNS)
        self.pcs = pcs
        self.scale = chord_scale(self.slots(), [(p - key) % 12 for p in pcs])
        self.pitches = music.resolve_pitches(s["key"], s["tones"], pcs, s["adaptive"])
        pad = self.voice("pad")
        att = clamp(hold * 0.35 * ATTACK.get(pad, 1.0), 0.03, 7)
        if self.retune:
            att = min(att, 1.5)
        rel = clamp(hold * 0.5, 0.3, 10)
        self.retune = False
        if pad != OFF and self.pattern("chords") == "Held" and kind("pad", pad) == HELD and self.voicing:
            amp = 0.11 * trim("pad", pad) * (4 / len(self.voicing)) ** 0.5
            spread = min(1.5, hold * 0.1)
            for n in self.voicing:
                self.engine.note(t + rng.uniform(0, spread), instr("pad", pad), hold + rel,
                                 self.hz(n), amp * rng.uniform(0.85, 1.1), att, rel, self.gen)
        bass = self.voice("bass")
        held_bass = bass != OFF and self.pattern("bass") == "Held"
        if held_bass:
            self.engine.note(t, instr("bass", bass), hold + rel, self.hz(music.bass_note(pcs[0])),
                             0.25 * trim("bass", bass), att, rel, self.gen, 0.5)
        self.now = {"t": t, "hold": hold, "pcs": pcs, "voicing": list(self.voicing),
                    "bass": music.bass_note(pcs[0]) if bass != OFF else None}
        # for the page: the chord as it is heard, and a held bass under it
        degs, pos = self.harmonist.view(s, self.slot)
        slots = self.slots()
        self.emit(t, "chord", dur=round(hold, 3), root=(pcs[0] - key) % 12,
                  notes=[self.pitch_of(n) for n in self.voicing],
                  # the progression it belongs to, for the page: items, numerals, roots, where this chord is
                  slot=self.slot, degs=degs, pos=pos, style=s["harmony"]["style"],
                  prog=[degree_numeral(s["key"], slots, d) for d in degs], roots=[item_slot(slots, d) for d in degs])
        if held_bass:
            self.emit(t, "bassheld", dur=round(hold, 3), voice=bass, **self.pitch_of(music.bass_note(pcs[0])))

    def acid_line(self, pcs: list[int]) -> list:
        """A bar of acid bass for this chord: (semitones above the bass note,
        accent) per step, or None for a rest."""
        rng, dens = self.rng, self.state["shape"]["notes"]
        line = []
        for k in range(STEPS):
            if k and rng.random() > 0.5 + 0.35 * dens:
                line.append(None)
                continue
            r = rng.random()
            third = (pcs[1] - pcs[0]) % 12 if len(pcs) > 1 else 12
            off = 0 if r < 0.5 or not k else 12 if r < 0.7 else 7 if r < 0.85 else third
            line.append((off, 1.0 if rng.random() < 0.3 else 0.3))
        return line

    # Bass

    def chord_in_bar(self, onset: int) -> list[int]:
        """The chord sounding at a sixteenth of this bar (a chart can change chord mid-bar)."""
        s = self.state
        h = s["harmony"]
        if h["style"] != "Loop" or onset == 0:
            return self.pcs or []
        _, i, _ = at_step(h, self.loop_step(onset))
        return loop_chord(s["key"], self.slots(), h, i)[0]

    def lead_in_bar(self, onset: int) -> str | None:
        """When the harmony has a form, it leads the melody's cadences: over the
        home chord an answer, else a question."""
        if self.state["harmony"]["style"] == "Wander":
            return None
        c = self.chord_in_bar(onset)
        return "answer" if c and (c[0] - music.KEYS.index(self.state["key"])) % 12 == 0 else "question"

    def _tone(self, name: str, root: int) -> int:
        """A chord tone above (or, -5, below) the bass root, as a MIDI note."""
        pcs = self.pcs
        rel = [(p - pcs[0]) % 12 for p in pcs]
        fifth = rel[2] if len(rel) > 2 else 7
        return root + {"R": 0, "3": rel[1] if len(rel) > 1 else fifth, "5": fifth,
                       "7": rel[3] if len(rel) > 3 else 12, "8": 12, "-5": fifth - 12}[name]

    def plan_bass(self, k0: int) -> None:
        """The bass line's notes from step k0 to the bar's end, against the chord now sounding."""
        line = self.pattern("bass")
        for k in [k for k in self.bass_plan if k >= k0]:
            del self.bass_plan[k]
        if self.pcs is None or line == "Held" or self.voice("bass") == OFF:
            return
        root = music.bass_note(self.pcs[0])
        rng, dens = self.rng, self.state["shape"]["notes"]
        if line == "Acid line":
            for k in range(k0, STEPS):
                hit = self.acid[k] if self.acid else None
                if hit:
                    self.bass_plan[k] = (root + hit[0], 1, hit[1])
            return
        if line == "Walking":
            self.walking(k0, root)
            return
        if line == "Walk-ups":
            self.walk_ups(k0, root)
            return
        for k, tone, length, v in BASS_LINES[line]:
            if k < k0:
                continue
            if line == "Funk" and v < 0.6 and rng.random() < 0.5 * (1 - dens):
                continue  # fewer ghost notes when the music is sparse
            if k == k0 and k0 > 0:
                tone = "R"  # a chord that starts mid-bar starts with its root
            self.bass_plan[k] = (self._tone(tone, root), length, v)

    def next_bar_root(self) -> int | None:
        """The pitch class of the chord on the next bar's first beat, if it is
        a new chord; None if the chord goes on (or no one knows yet)."""
        s = self.state
        h = s["harmony"]
        key = music.KEYS.index(s["key"])
        if h["style"] == "Loop":
            here, _, left = at_step(h, self.loop_step(0))
            nxt, i, _ = at_step(h, self.loop_step(STEPS))
            if nxt == here:
                return None
            return (key + item_slot(self.slots(), h["loop"][i])) % 12
        if (max(0, self.bar) + 1) % chord_bars(h["rhythm"]):
            return None
        nxt = self.harmonist.peek(s, self.slot + 1, self.root)
        return None if nxt is None else (key + nxt) % 12

    def walk_ups(self, k0: int, root: int) -> None:
        """Root on 1, the fifth below on 3; in a bar before a new chord (one
        chord the whole bar), beats 3 and 4 walk by step into the new root."""
        for k, tone, length, v in BASS_LINES["Root–fifth"]:
            if k >= k0:
                self.bass_plan[k] = (self._tone("R" if k == k0 else tone, root), length, v)
        if k0 > 0 or self.chord_in_bar(8) != self.pcs:
            return
        nxt = self.next_bar_root()
        if nxt is None or nxt == self.pcs[0] % 12 or self.rng.random() > 0.8:
            return
        scale = self.scale_notes(28, 55)
        target = min((n for n in range(28, 56) if n % 12 == nxt), key=lambda n: abs(n - root))
        below = [n for n in scale if n < target][-2:]
        above = [n for n in scale if n > target][:2][::-1]
        walk = below if target >= root else above  # up into a higher root, down into a lower one
        if len(walk) == 2:
            self.bass_plan[8] = (walk[0], 4, 0.8)
            self.bass_plan[12] = (walk[1], 4, 0.85)

    def walking(self, k0: int, root: int) -> None:
        """Jazz bass: a note each beat. Beat 1 on the chord (its root when the
        chord starts), then by step or chord tone toward a note a half or
        whole step from where the next bar begins."""
        s, rng = self.state, self.rng
        lo, hi = 28, 55
        scale = self.scale_notes(lo, hi)
        pcs = set(self.pcs)
        cb = chord_bars(s["harmony"]["rhythm"])
        prev = self.bass_last if self.bass_last is not None else root
        near = lambda pc, ref: min((n for n in range(lo, hi + 1) if n % 12 == pc), key=lambda n: abs(n - ref))
        if max(0, self.bar) % cb == 0 or k0 > 0:
            first = near(self.pcs[0], prev)
        else:
            first = near(rng.choice(sorted(pcs)), prev)
        h = s["harmony"]
        if h["style"] == "Loop":  # aim at the chord on the next bar's first beat
            nxt = item_slot(self.slots(), h["loop"][at_step(h, self.loop_step(STEPS))[1]])
            target_pc = (music.KEYS.index(s["key"]) + nxt) % 12
            nxt = None
        elif (max(0, self.bar) + 1) % cb == 0:  # the chord changes at the next bar: aim at its root
            nxt = self.harmonist.peek(s, self.slot + 1, self.root)
            target_pc = (music.KEYS.index(s["key"]) + nxt) % 12 if nxt is not None else self.pcs[0]
        else:
            target_pc = rng.choice(sorted(pcs))
        target = near(target_pc, first + rng.choice([-5, 5]))
        # beat 4 leads into the target: a half step (chromatic), or the scale note a step away
        steps = [n for n in scale if 1 <= abs(n - target) <= 2]
        approach = target + rng.choice([-1, 1]) if rng.random() < 0.6 or not steps else rng.choice(steps)
        # beats 2 and 3: on the way from the first note to the approach, chord tones preferred
        notes, a = [first], first
        for frac in (1 / 3, 2 / 3):
            goal = first + (approach - first) * frac
            choices = [n for n in scale if n not in (a, approach)] or scale
            a = min(choices, key=lambda n: abs(n - goal) + (0 if n % 12 in pcs else 0.7) + rng.random() * 0.6)
            notes.append(a)
        notes.append(approach)
        for beat, n in enumerate(notes):
            k = 4 * beat
            if k >= k0:
                self.bass_plan[k] = (n, 4, 1.0 if beat == 0 else 0.8)
        self.bass_last = approach

    def bass_line(self, t: float, k: int) -> None:
        hit = self.bass_plan.pop(k, None)
        v = self.voice("bass")
        if not hit or v == OFF:
            return
        note, length, strength = hit
        line = self.pattern("bass")
        dur = length * self.step_s() * BASS_SHORT.get(line, 0.92)
        amp = 0.27 * trim("bass", v) * gain("bass", line) * (0.55 + 0.45 * strength)
        self.engine.note(t, instr("bass", v), dur + 0.05, self.hz(note), amp, 0.004, 0.05, self.gen, strength)
        self.emit(t, "bass", dur=round(dur, 3), v=round(strength, 2), **self.pitch_of(note))

    # Chords in a rhythm

    def chords(self, t: float, k: int, new_chord: bool) -> None:
        """The chords part when it plays a rhythm, or a struck voice held:
        once when the chord starts, again each bar."""
        v, pat = self.voice("pad"), self.pattern("chords")
        if v == OFF or not self.voicing:
            return
        held = kind("pad", v) == HELD
        if pat == "Held":
            if held or not (new_chord or k == 0):
                return
            h, length = (1.0 if new_chord else 0.8), STEPS
        elif pat in ("Boom-chick", "Travis"):
            self.picked(t, k, v, held, pat)
            return
        elif pat == "Strum":
            if k not in STRUM:
                return
            h, way = STRUM[k]
            nxt = min([x for x in STRUM if x > k] or [STEPS])
            length = nxt - k
        else:
            if k == 0 and pat == "Comp":
                self.comp = self.rng.choice(COMP_PATTERNS)
            row = {"Stabs": self.stabs, "Comp": self.comp}.get(pat) or CHORD_HITS[pat]
            h = hits(row, k)
            if not h:
                return
            length = CHORD_LEN[pat]
        step = self.step_s()
        dur = length * step * 0.9
        amp = 0.11 * trim("pad", v) * (4 / len(self.voicing)) ** 0.5 * gain("chords", pat) * h
        notes = list(self.voicing)
        delay = 0.0
        if pat == "Strum":  # down: low to high; up: the top notes, high to low
            notes = notes if way == "down" else notes[::-1][:3]
            delay = 0.012 if way == "down" else 0.008
        for i, n in enumerate(notes):
            at = t + i * delay
            if held:
                self.engine.note(at, instr("pad", v), dur + 0.08, self.hz(n), amp, 0.006, 0.08, self.gen)
            else:
                self.engine.note(at, instr("pad", v), max(dur, 0.25), self.hz(n), amp, LEVEL["pad"], dur * 0.5)
        self.emit(t, "stab", v=round(h, 2))

    def picked(self, t: float, k: int, v: str, held: bool, pat: str) -> None:
        """A guitar's own bass and chord: boom-chick (a low root, a strum on
        2, the fifth on 3, a strum on 4) or Travis picking (the thumb
        alternating root and fifth on the beats, fingers between)."""
        if k % 2:
            return
        chord = sorted(self.voicing)
        rel = [(p - self.pcs[0]) % 12 for p in self.pcs]
        low = min(chord) - 12
        while low % 12 != self.pcs[0] % 12:  # the root, below the chord
            low += 1
        f = rel[2] if len(rel) > 2 else 7
        fifth = low + f - 12 if low + f - 12 >= 36 else low + f  # the fifth below the root, unless that is too low
        if pat == "Boom-chick":
            hits = {0: ([low], 1.0, 3), 4: (chord, 0.75, 1.5), 8: ([fifth], 0.9, 3), 12: (chord, 0.75, 1.5)}
        else:
            top, mid = chord[-1], chord[-2] if len(chord) > 1 else chord[-1]
            hits = {0: ([low, top], 1.0, 3), 2: ([mid], 0.6, 2), 4: ([fifth], 0.85, 3), 6: ([top], 0.6, 2),
                    8: ([low], 0.9, 3), 10: ([mid], 0.6, 2), 12: ([fifth], 0.85, 3), 14: ([top], 0.6, 2)}
        if k not in hits:
            return
        notes, h, length = hits[k]
        dur = length * self.step_s() * 0.9
        amp = 0.11 * trim("pad", v) * gain("chords", pat) * h
        for i, n in enumerate(notes):
            at = t + i * (0.01 if len(notes) > 2 else 0)
            if held:
                self.engine.note(at, instr("pad", v), dur + 0.08, self.hz(n), amp, 0.006, 0.08, self.gen)
            else:
                self.engine.note(at, instr("pad", v), max(dur, 0.25), self.hz(n), amp, LEVEL["pad"], dur * 0.5)
        self.emit(t, "stab", v=round(h, 2))

    # Parts on the grid

    def drums(self, t: float, k: int) -> None:
        style = self.pattern("drums")
        if style == OFF:
            return
        kit = KITS[self.voice("drums")]
        dens, rng = self.state["shape"]["notes"], self.rng
        g = gain("drums", style) * trim("drums", self.voice("drums"))
        for part, pattern in DRUMS[style].items():
            v = hits(pattern, k)
            if not v and part == "hat" and rng.random() < 0.25 * dens:
                v = 0.25  # ghost hats, more as Notes goes up
            if not v:
                continue
            i, level, length, decay, pitch = kit[part]
            v *= rng.uniform(0.9, 1.0)
            self.engine.note(t, i, length, level * v * g, decay, pitch)
            self.emit(t, "drum", part=part, v=round(v, 2), k=k)

    def pulse(self, t: float, tp: float, k: int) -> None:
        pat = self.pattern("pulse")
        if pat == OFF:
            return
        s, rng, v = self.state, self.rng, self.voice("pulse")
        amp = 0.1 * trim("pulse", v) * gain("pulse", pat)
        dens, beat, i = s["shape"]["notes"], self.beat(), instr("pulse", v)
        lvl = LEVEL["pulse"]
        if pat == "Heartbeat":
            if k % 4 == 0 and self.pcs:
                f = 50 if v == "Thump" else self.hz(music.bass_note(self.pcs[0]) + 12)
                self.engine.note(t, i, 0.5, f, amp, lvl)
                self.engine.note(t + 0.28 * beat, i, 0.5, f, amp * 0.7, lvl)
                self.emit(t, "drum", part="heart", v=0.8, k=k)
                self.emit(t + 0.28 * beat, "drum", part="heart", v=0.5, k=k)
        elif pat in ("Arp", "Arp 16ths"):
            every = 2 if pat == "Arp" else 1
            chord = self.full or self.voicing
            if k % every == 0 and chord and rng.random() < 0.5 + 0.5 * dens:
                up = [n + 12 for n in chord]
                seq = up + up[-2:0:-1]
                n = seq[self.arp_i % len(seq)]
                self.arp_i += 1
                self.engine.note(tp, i, max(0.15, self.step_s() * every * 1.5), self.hz(n), amp, lvl)
                self.emit(tp, "arp", dur=round(self.step_s() * every, 3), **self.pitch_of(n))
        elif pat in ROLLS:
            chord = self.full or self.voicing
            if not chord:
                return
            up = sorted({n + 12 for n in chord})
            low, mid, top = up[0], up[len(up) // 2], up[-1]
            key = music.KEYS.index(s["key"])
            drone = min((n for n in range(top - 6, top + 7) if n % 12 == key), default=top)
            finger = ROLLS[pat][k % 8]
            if finger == "T":
                thumbs = [j for j in range(k % 8 + 1) if ROLLS[pat][j] == "T"]
                n = drone if len(thumbs) % 2 else low
            else:
                n = mid if finger == "I" else top
            self.engine.note(tp, i, max(0.2, self.step_s() * 3), self.hz(n), amp * (1.0 if k % 4 == 0 else 0.75), lvl)
            self.emit(tp, "arp", dur=round(self.step_s(), 3), **self.pitch_of(n))
        elif rng.random() < 0.08 + 0.3 * dens:  # Glints
            c = self.center()
            n = rng.choice(self.scale_notes(int(c + 24), int(c + 36)) or [int(c + 24)])
            self.engine.note(tp, i, 0.4, self.hz(n), amp * 0.5, lvl)
            self.emit(tp, "glint", **self.pitch_of(n))

    def shaped_melody(self, t: float) -> None:
        """Motifs and phrases (ambient/melody.py), as planned bar by bar."""
        v = self.voice("melody")
        for note, length, vel, frac in self.melodist.at(self.steps):
            if v == OFF:
                continue
            at = t + frac * self.step_s()  # a thirty-second falls between the sixteenths
            dur = max(length * self.step_s() * 0.95, MELODY_RING.get(v, 0.06))
            self.engine.note(at, instr("melody", v), dur, self.hz(note),
                             0.09 * trim("melody", v) * phrase_trim(v) * (0.55 + 0.45 * vel), LEVEL["melody"])
            self.emit(at, "melody", dur=round(dur, 3), **self.pitch_of(note))

    def melody(self, t: float) -> None:
        s, rng = self.state, self.rng
        self.next_melody = t + max(0.15, rng.expovariate(1 / melody_gap(s["shape"]["notes"])))
        v = self.voice("melody")
        if v == OFF:
            return
        notes = self.scale_notes(*melody_range(s["shape"]["height"]))
        if not notes:
            return
        chord = self.full or self.voicing
        if chord and rng.random() < 0.3:
            tones = [n for n in notes if n % 12 in {m % 12 for m in chord}]
            ref = self.mel_note if self.mel_note is not None else notes[len(notes) // 2]
            note = min(tones or notes, key=lambda n: abs(n - ref))
        elif self.mel_note in notes:
            i = notes.index(self.mel_note) + rng.choice([-3, -2, -1, -1, 1, 1, 2, 3])
            note = notes[int(clamp(i, 0, len(notes) - 1))]
        else:
            note = rng.choice(notes)
        self.mel_note = note
        if v in MELODY_STEPS:
            dur = self.step_s() * rng.randint(*MELODY_STEPS[v])
        else:
            dur = rng.uniform(*MELODY_DUR[v])
        self.engine.note(t, instr("melody", v), dur, self.hz(note), 0.09 * trim("melody", v) * rng.uniform(0.6, 1),
                         LEVEL["melody"])
        self.emit(t, "melody", dur=round(dur, 3), **self.pitch_of(note))

    # Texture: a held note, changed when its voice changes

    def sync_texture(self, now: float) -> None:
        v = self.state["layers"]["texture"]["voice"]
        want = None if v == OFF else instr("texture", v)
        if want == self.texture:
            return
        if self.texture is not None:
            self.engine.note(now, -(self.texture + 0.1), 1)
        if want is not None:
            self.engine.note(now, want + 0.1, -1)
        self.texture = want

    def silence_texture(self) -> None:
        """Release the held texture (on stop)."""
        if self.texture is not None:
            self.engine.note(self.engine.time(), -(self.texture + 0.1), 1)
            self.texture = None
