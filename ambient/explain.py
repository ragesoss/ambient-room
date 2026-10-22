"""What each control means in musical terms, and what is playing now.

The page shows these next to the controls. The numbers come from the same
formulas the music uses: the conductor's functions, and the orchestra's
expressions (ambient/orc/ambient.orc), which are noted where copied.
"""

import math
import random

from . import harmony, music
from .conductor import bar_seconds, bpm, center, melody_gap, melody_range, swing_delay
from .harmony import chord_bars
from .evolve import changes_at_once, interval_s, lockable, position
from .melody import STYLES as MELODY_STYLES, phrase_bars
from . import presets
from .state import MOODS, get_path
from .sounds import BASS_GROUPS, LABELS, LAYERS, MELODY_GROUPS, OFF, PATTERN_OFF, PATTERNS, about

SHAPE = {
    # id: (label, what it is, low end, high end)
    "bright": ("Brightness", "low-pass filter cutoff, FM index, reverb damping", "dark", "bright"),
    "motion": ("Motion", "modulation: detuning, pitch drift, filter wobble", "still", "drifting"),
    "space": ("Space", "reverb: feedback (tail length) and wet/dry mix", "close", "vast"),
    "echo": ("Echo", "delay: time set by the tempo, feedback, level", "none", "lots"),
    "notes": ("Notes", "melody density, and how full the rhythm part is; for phrases and motifs, past 0.75 the line runs on, and near 1 goes frenetic", "sparse", "frenetic"),
    "tempo": ("Tempo", "beats per minute: the grid everything plays on, 50 to 150", "slow", "fast"),
    "height": ("Height", "register: the octave the chords and melody sit in", "low", "high"),
    "swing": ("Swing", "how late the off sixteenths come, up to a triplet feel", "straight", "swung"),
    "pump": ("Pump", "sidechain: each kick ducks everything else, which swells back", "none", "deep"),
    "drive": ("Drive", "saturation: loud parts squashed, quiet ones lifted; grit and density", "clean", "driven"),
}


def db(x: float) -> str:
    return "off" if x <= 0.001 else f"{20 * math.log10(x):+.1f} dB"


def options() -> dict:
    """Everything the page needs to build its controls."""
    return {
        "keys": [{"id": k, "name": music.pretty(k)} for k in music.KEYS],
        "scales": [{"id": s, "name": n, "formula": music.pretty(f), "about": a,
                    "slots": music.preset_slots(s), "steps": music.step_pattern(music.preset_slots(s))}
                   for s, (n, f, a) in music.SCALES.items()],
        # the pitches offered for each tone: equal-tempered, then its just
        # ratios, the usual one first. height: log2(numerator x denominator),
        # the Tenney height; lower is simpler: 3/2 is 2.6, 5/4 4.3, 45/32 10.5
        "palette": {str(s): [_pitch(s, p) for p in music.offered(s)] for s in range(12)},
        "families": [{"id": f, "name": n, "about": a} for f, (n, a) in music.FAMILIES.items()],
        "adaptive": music.ADAPTIVE,
        "lockable": lockable(),
        "melody_groups": MELODY_GROUPS,
        "bass_groups": BASS_GROUPS,
        # the four parts: their names and settings (each can be locked whole)
        "parts": {k: {"name": n, "paths": ps} for k, (n, ps) in presets.PARTS.items()},
        # what the parts in time play
        "patterns": {part: [{"id": OFF, "about": "silent"}] * (part in PATTERN_OFF) +
                           [{"id": k, "about": a} for k, (_, a) in ps.items()] for part, ps in PATTERNS.items()},
        "harmony": {"styles": [{"id": k, "about": v} for k, v in harmony.STYLES.items()],
                    "presets": [{"id": k, "degrees": d, "about": a} for k, (d, a) in harmony.PRESETS.items()],
                    "borrowed": [{"id": k, "about": a} for k, (_, _, a) in harmony.BORROWED.items()],
                    # any chord on any root: root (semitones above the key note) -> kind -> its Roman numeral
                    "any": {"kinds": [{"id": k, "name": n} for k, (n, _, _) in harmony.KINDS.items()],
                            "chords": {r: {k: harmony.any_chord(r, k) for k in harmony.KINDS} for r in range(12)}},
                    "max_loop": harmony.MAX_LOOP,
                    "params": [{"id": "rhythm", "name": "Harmonic rhythm", "what": "how often the chord changes: every 16, 8, 4, 2 or 1 bars",
                                "lo": "slow", "hi": "every bar", "step": 0.25},
                               {"id": "size", "name": "Chord size", "what": "how many notes the chords play: none, the root, root and fifth, triads, sevenths, ninths",
                                "lo": "none", "hi": "five", "step": 0.1},
                               {"id": "borrow", "name": "Borrowing", "what": "how often a chord comes from outside the scale: iv, ♭VI, ♭VII in major, V in minor, secondary dominants",
                                "lo": "the scale only", "hi": "often"},
                               {"id": "length", "name": "Cycle length", "what": "chords in a cycle: 2, 4 or 8",
                                "lo": "short", "hi": "long"},
                               {"id": "resolve", "name": "Resolution", "what": "how often a cycle comes home to the home chord",
                                "lo": "open", "hi": "always home"}]},
        "melody": {"styles": [{"id": k, "about": v} for k, v in MELODY_STYLES.items()],
                   "params": [{"id": "phrase", "name": "Phrase length", "what": "1, 2, 4 or 8 bars a phrase", "lo": "short", "hi": "long"},
                              {"id": "variation", "name": "Variation", "what": "how much the motif changes as it repeats", "lo": "repeats", "hi": "reinvents"},
                              {"id": "range", "name": "Melodic range", "what": "how far up and down the line may go", "lo": "narrow", "hi": "wide"},
                              {"id": "leaps", "name": "Leaps", "what": "steps from note to note, or jumps", "lo": "stepwise", "hi": "leaping"},
                              {"id": "syncopation", "name": "Syncopation", "what": "notes off the beat: offbeat starts, anticipations, snaps", "lo": "on the beat", "hi": "off the beat"},
                              {"id": "pickups", "name": "Pickups", "what": "how often a phrase starts with notes leading into its first bar", "lo": "never", "hi": "often"},
                              {"id": "pull", "name": "The tune", "what": "with the Tune line, over a tune's chart: how much of the tune's own melody it keeps", "lo": "free", "hi": "as written"},
                              {"id": "density", "name": "Note density", "what": "with the Tune line: how many notes the break plays against the tune's own; fewer simplifies the tune, more fills it", "lo": "simpler", "hi": "busier"}]},
        "layers": {layer: {"name": LABELS[layer][0], "about": LABELS[layer][1],
                           "voices": [{"id": OFF, "about": "silent"}] * (layer not in ("drums", "pulse")) +
                                     [{"id": v, "about": about(layer, v)} for v in voices]}
                   for layer, voices in LAYERS.items()},
        "shape": [{"id": k, "name": n, "what": w, "lo": lo, "hi": hi} for k, (n, w, lo, hi) in SHAPE.items()],
    }


def _melody(state: dict) -> dict:
    m = state["melody"]
    words = lambda x, ws: ws[min(len(ws) - 1, int(x * len(ws)))]
    return {
        "style": MELODY_STYLES[m["style"]],
        "phrase": f"{phrase_bars(m['phrase'])} bar{'s' if phrase_bars(m['phrase']) > 1 else ''} a phrase",
        "variation": words(m["variation"], ["repeats almost exactly", "small changes", "develops as it goes",
                                            "changes a lot", "keeps reinventing itself"]),
        "range": f"within about {2 * (3 + int(8 * m['range'])) + 1} scale notes",
        "leaps": words(m["leaps"], ["moves by step", "mostly steps", "steps and some leaps", "many leaps", "leaping"]),
        "syncopation": words(m.get("syncopation", 0.25), ["on the beat", "now and then off it", "often off the beat",
                                                          "mostly off the beat", "syncopated throughout"]),
        "pickups": words(m.get("pickups", 0.4), ["phrases start on the bar line", "a pickup now and then",
                                                 "pickups into about half the phrases", "most phrases led into", "every phrase led into"]),
        "density": _density(m.get("density", 0.5)),
        "pull": words(m.get("pull", 0.5), ["free over the chords", "the tune's cadences, free between", "the tune, played with",
                                           "the tune, decorated", "the tune as written"]),
    }


def _density(x: float) -> str:
    """The Tune line's note density in words: its share of the tune's notes (breaks.density_of)."""
    from .breaks import density_of
    r = density_of(x)
    if abs(r - 1) < 0.02:
        return "the tune's own notes, and what the pull adds"
    if r < 1:
        return f"{round(100 * r)}% of the tune's notes: simpler"
    return f"up to {round(100 * r)}% of the tune's notes: filled"


def _words(x: float, ws: list[str]) -> str:
    return ws[min(len(ws) - 1, int(x * len(ws)))]


def _size(x: float, plain: bool) -> str:
    names = ["no chords: the bass and melody carry the harmony", "the root alone", "root and fifth (a power chord)",
             "triads", "sevenths", "ninths"]
    v = 5 * x
    lo = min(int(v), 3 if plain else 5)
    frac = 0 if lo < int(v) or v >= 5 else v - int(v)
    if frac < 0.05:
        return names[lo]
    return f"{names[lo]}; {round(100 * frac)}% with one more note"


def _notes(state: dict) -> str:
    """What the Notes control does now: for scattered notes a time between
    them; for phrases and motifs, how busy the rhythm is."""
    n = state["shape"]["notes"]
    if state["melody"]["style"] == "Scattered":
        return f"a melody note every {melody_gap(n):.1f} s on average"
    for upto, words in ((0.3, "sparse: long notes and rests"), (0.5, "quarters and eighths"),
                        (0.65, "eighths and some sixteenths"), (0.751, "busy: eighths and sixteenths"),
                        (0.85, "running: mostly unbroken sixteenths"), (0.95, "running fast, with bursts of thirty-seconds")):
        if n < upto:
            return words
    return "frenetic: runs of thirty-seconds"


def _harmony(state: dict) -> dict:
    h, key = state["harmony"], state["key"]
    slots = music.slots_of(state["tones"])
    names = music.spell(key, slots)
    have = harmony._numbers(slots)
    n, cb = harmony.cycle_length(h["length"]), chord_bars(h["rhythm"])
    bar = bar_seconds(state["shape"]["tempo"])
    nums = lambda loop: "–".join(harmony.numeral(key, slots, d) for d in loop)
    preset = next((k for k, (d, _) in harmony.PRESETS.items() if d == h["loop"]), None)
    chord = lambda item, i=0: music.chord_symbol(harmony.build(key, slots, item, 3, h["plain"], random.Random(i)), names)
    return {
        "style": harmony.STYLES[h["style"]],
        "rhythm": f"a new chord every {cb} bar{'s' if cb > 1 else ''} ({cb * bar:.0f} s at {bpm(state['shape']['tempo']):.0f} BPM)",
        "size": _size(h["size"], h["plain"]),
        "plain": "major and minor triads only: other chords made major or minor, borrowing a note" if h["plain"] else
                 "any chord the scale makes: diminished, suspended, sevenths ...",
        "borrow": "the scale only" if h["borrow"] < 0.01 else _words(h["borrow"], [
            "now and then a chord from outside the scale", "a borrowed chord or secondary dominant in some cycles",
            "borrowed chords in most cycles", "many borrowed chords", "borrowing all the time"]) +
            (" (in loops: the chords you put in)" if h["style"] == "Loop" else ""),
        "length": f"{n} chords a cycle: {n * cb} bars, {n * cb * bar_seconds(state['shape']['tempo']):.0f} s",
        "resolve": _words(h["resolve"], ["rarely home: most cycles stop on V (a half cadence)",
                                         "mostly open; home now and then",
                                         "question and answer: an open cycle, then one that comes home",
                                         "mostly home", "every cycle comes home, V–I or IV–I"]),
        # each degree's chord in this scale; sub: the scale lacks the degree, so another stands in
        "degrees": [{"d": d, "numeral": harmony.numeral(key, slots, d), "sub": d not in have,
                     "slot": harmony.degree_slot(slots, d), "chord": chord(d, d)}
                    for d in range(1, 8)],
        # the chords from outside this scale, with their names in this key
        "borrowed": [{"d": b, "numeral": b, "slot": harmony.BORROWED[b][0], "chord": chord(b),
                      "about": harmony.BORROWED[b][2]} for b in harmony.borrowable(slots)],
        "loop": [{"d": harmony.chord_of(e), "beats": harmony.beats_of(e), "numeral": harmony.numeral(key, slots, e),
                  "slot": harmony.item_slot(slots, e), "chord": music.chord_symbol(harmony.loop_chord(key, slots, h, i)[0], names)}
                 for i, e in enumerate(h["loop"])],
        "loop_bars": round(harmony.timeline(h)[1] / 16, 2),
        "loop_preset": preset,
        "presets": {k: nums(d) for k, (d, _) in harmony.PRESETS.items()},
    }


def preset_match(state: dict) -> dict:
    """For each preset, the aspects (key, harmony, melody, beat, sound) the
    settings now share with it."""
    return {name: [a for a, (_, paths) in presets.ASPECTS.items()
                   if all(get_path(m, p) == get_path(state, p) for p in paths)]
            for name, m in MOODS.items()}


def progression_name(state: dict) -> str:
    """A mood's progression, in a few words."""
    h = state["harmony"]
    if h["style"] == "Loop":
        slots = music.slots_of(state["tones"])
        return "–".join(harmony.numeral(state["key"], slots, d) for d in h["loop"])
    return "chords in cadences" if h["style"] == "Functional" else "wandering chords"


def _heading(target) -> str:
    if target is None:
        return "no direction: wandering freely"
    e, b = target
    ew = "calm" if e < 0.35 else "energetic" if e > 0.65 else "middling energy"
    bw = "dark" if b < 0.35 else "bright" if b > 0.65 else "neither dark nor bright"
    return f"toward {ew}, {bw}"


def _dur(s: float) -> str:
    return f"{s:.0f} s" if s < 90 else f"{s / 60:.1f} min"


def _pitch(slot: int, p) -> dict:
    """A pitch a tone may take, for the page: equal-tempered, or a ratio."""
    if p == music.ET:
        return {"pitch": music.ET, "family": "equal", "cents": 0.0, "at": 100.0 * slot,
                "name": "equal-tempered", "height": None}
    return {"pitch": music.frac(p), "family": "just", "cents": round(music.cents_from_equal(slot, p), 1),
            "at": round(music.cents(p), 2), "name": music.RATIO_NAMES.get(music.frac(p), ""),
            "height": round(math.log2(p.numerator * p.denominator), 2)}


def describe(state: dict, conductor=None, now_s: float | None = None) -> dict:
    key, sh = state["key"], state["shape"]
    slots = music.slots_of(state["tones"])
    names = music.spell(key, slots)
    tempo = bpm(sh["tempo"])
    wide = state["melody"]["range"] if state["melody"]["style"] != "Scattered" else 0.5
    mel = music.scale_notes(key, slots, *melody_range(sh["height"], wide)) or [60]
    b, m, s, e = sh["bright"], sh["motion"], sh["space"], sh["echo"]
    detune = 0.002 + 0.004 * m  # orc instr 11: kDet
    echo_t = 0.75 * 60 / tempo
    shape = {
        "bright": f"chord filter at {1.2 + 9 * b * b:.1f}× each note's pitch · reverb cut above {5000 + 4000 * b:.0f} Hz",
        "motion": f"voices detuned ±{1200 * math.log2(1 + detune):.1f} ¢, drifting at {0.05 + 0.4 * m:.2f} Hz"
                  f" · filter wobble ±{30 * m:.0f}%",
        "space": f"feedback {0.80 + 0.17 * s:.2f} · wet {100 * (0.2 + 0.6 * s):.0f}% · dry {100 * (1 - 0.5 * s):.0f}%",
        "echo": "off" if e < 0.01 else
                f"{echo_t:.2f} s left, {1.5 * echo_t:.2f} s right (a dotted eighth at {tempo:.0f} BPM)"
                f" · feedback {100 * (0.2 + 0.5 * e):.0f}% · level {100 * e:.0f}%",
        "notes": _notes(state) +
                 f" · the arpeggio plays {100 * (0.5 + 0.5 * sh['notes']):.0f}% of its eighths",
        "tempo": f"{tempo:.0f} BPM: a beat every {60 / tempo:.2f} s",
        "height": f"chords around {music.note_name(round(center(sh['height'])), names)} (±10 semitones)"
                  f" · melody {music.note_name(mel[0], names)} to {music.note_name(mel[-1], names)}",
        "swing": "straight" if sh["swing"] < 0.01 else
                 f"off sixteenths {1000 * swing_delay(sh['swing'], 15 / tempo):.0f} ms late",
        "pump": "off" if sh["pump"] < 0.01 else
                f"each kick ducks the rest by {-20 * math.log10(1 - 0.8 * sh['pump']):.0f} dB; back in ~{0.3 * 60 / tempo * 3:.2f} s",
        "drive": f"saturation ×{1 + 5 * sh['drive']:.1f}" + (" (clean)" if sh["drive"] < 0.05 else ""),
    }
    out = {
        "key": f"{music.pretty(key)}: the home note (1). Chords are built from the scale on {music.pretty(key)}.",
        "scale": music.describe_scale(key, state["tones"]),
        "adaptive": music.ADAPTIVE,
        "volume": db(state["volume"]) + " · full is about the level takes play at",
        "layers": {layer: {"level": db(lc["level"]) if lc["voice"] != OFF else "off",
                           "voice": "silent" if lc["voice"] == OFF else about(layer, lc["voice"])}
                   for layer, lc in state["layers"].items()},
        "beat": {part: "silent" if v == OFF else PATTERNS[part][v][1] for part, v in state["beat"].items()},
        "shape": shape,
        "melody": _melody(state),
        "harmony": _harmony(state),
        "preset_match": preset_match(state),
        "evolve": {
            "rate": "off: settings change only by hand" if state["evolve"]["rate"] <= 0 else
                    f"a change about every {_dur(interval_s(state['evolve']['rate']))}, on a bar's first beat",
            "size": ["small nudges", "small steps", "medium steps", "large steps", "leaps"][
                min(4, int(state["evolve"]["size"] * 5))],
            "count": (lambda n: f"{n} setting{'s' if n > 1 else ''} at a time")(
                changes_at_once(state["evolve"].get("count", 0.0))),
            "position": position(state),
            "heading": _heading(state["evolve"].get("target")),
            "pull": "" if state["evolve"].get("target") is None else
                    ["mostly wandering", "wandering, leaning that way", "heading there, with detours",
                     "heading there", "walking straight there"][min(4, int(state["evolve"].get("pull", 0.5) * 5))],
        },
        "now": None,
    }
    if conductor is not None and conductor.now:
        out["now"] = _now(state, conductor, names, now_s)
    return out


def _now(state: dict, c, names: dict[int, str], now_s: float | None) -> dict:
    key = state["key"]
    slots = music.slots_of(state["tones"])
    n = c.now
    root = music.KEYS.index(key)
    notes = []
    for midi in n["voicing"]:
        rel = (midi - root) % 12
        label, c_above = c.pitches.get(rel, (music.ET, 100.0 * rel))
        notes.append({
            "name": music.note_name(midi, names),
            "slot": rel,
            "at": round(c_above, 2),  # cents above the home note, for placing it on the wheel
            "pitch": label,
            "interval": music.RATIO_NAMES.get(label, ""),
            # how far the note sits from the piano's (equal-tempered) pitch
            "cents": round(c_above - 100 * rel, 1),
        })
    left = None if now_s is None else max(0, round(n["t"] + n["hold"] - now_s))
    degs, pos = c.harmonist.view(state, c.slot)
    return {
        "t": round(n["t"], 4),  # its score time, so the page can show it when it is heard
        "prog": {"style": state["harmony"]["style"], "degs": degs, "pos": pos, "slot": c.slot,
                 "prog": [harmony.numeral(key, slots, d) for d in degs],
                 "roots": [harmony.item_slot(slots, d) for d in degs]},
        "numeral": music.numeral(key, slots, n["pcs"]),
        "root": (n["pcs"][0] - root) % 12,  # the chord's lowest stacked note, as a slot
        "chord": music.chord_symbol(n["pcs"], names),
        "notes": notes,
        "bass": music.note_name(n["bass"], names) if n["bass"] is not None else None,
        "next_s": left,
    }
