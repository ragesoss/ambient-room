"""What the room hears: the shared settings, presets, moods, and "surprise me".

The settings fall into four parts (ambient/presets.py): harmony, melody,
beat and sound. A preset for a part sets that part's settings and nothing
else, so a song (harmony and melody) can be played in any style (beat and
sound).
"""

import copy
import functools
import random

from .harmony import MAX_LOOP, PRESETS as LOOPS, RHYTHM_BARS, STYLES as HARMONY_STYLES, parse_chart, valid_chord
from .melody import STYLES as MELODY_STYLES
from .music import ET, FAMILIES, KEYS, SCALES, check_tones, default_tones, preset_slots
from .presets import BY_PART, PARTS, WHOLE
from .sounds import LAYERS, OFF, PATTERN_OFF, PATTERNS

SHAPE = ["bright", "motion", "space", "echo", "notes", "tempo", "height", "swing", "pump", "drive"]
NO_OFF = {"pulse", "drums"}  # these parts go quiet by their pattern, not their voice

DEFAULT = {
    "key": "D",
    # the scale: semitones above the key note, each with its pitches: just
    # ratios, or "ET" (equal-tempered)
    "tones": default_tones(preset_slots("major_pentatonic")),
    "adaptive": False,  # retune each chord pure around its root
    "volume": 0.6,
    # the band: who plays each part, and how loud (the Sound part)
    "layers": {
        "pad": {"voice": "Warm", "level": 0.7},
        "bass": {"voice": "Sub", "level": 0.5},
        "melody": {"voice": "Bell", "level": 0.5},
        "texture": {"voice": "Wind", "level": 0.3},
        "pulse": {"voice": "Pluck", "level": 0.4},
        "drums": {"voice": "Electronic", "level": 0.6},
    },
    # what the parts in time play (the Beat part, with tempo, swing and pump)
    "beat": {"drums": OFF, "bass": "Held", "chords": "Held", "pulse": OFF},
    # evolution: how often a setting changes by itself (0: never), and how far
    "evolve": {"rate": 0.0, "size": 0.3, "count": 0.0,
               # a direction: [energy, brightness] to head toward (None: wander), and how strongly
               "target": None, "pull": 0.5},
    # settings that only change by hand: never by evolution, a mood or a preset
    "locks": ["volume"],
    # the chords' form: wandering, functional cycles ending in cadences, or
    # a loop of scale degrees (or borrowed chords: "♭VII"); chords per cycle,
    # how often a cycle comes home, the harmonic rhythm (0: 16 bars a chord
    # ... 1: one bar), how many notes the chords play (0 to 1: none to five),
    # major and minor triads only, and how often a chord comes from outside
    # the scale
    "harmony": {"style": "Wander", "loop": [1, 5, 6, 4], "length": 0.5, "resolve": 0.5, "rhythm": 0.25,
                "size": 0.88, "plain": False, "borrow": 0.0},
    # how the melody is shaped
    "melody": {"style": "Scattered", "phrase": 0.55, "variation": 0.35, "range": 0.5, "leaps": 0.35,
               "syncopation": 0.25, "pickups": 0.4,
               # the Tune line's pull (ambient/breaks.py): 1 the tune as written, 0 free over the chords; and its note
               # density, the break's notes against the tune's (breaks.density_of: 0 a quarter of them, 0.5 as the
               # pull plays it, 1 twice them)
               "pull": 0.5, "density": 0.5},
    "shape": {"bright": 0.4, "motion": 0.3, "space": 0.6, "echo": 0.2,
              "notes": 0.3, "tempo": 0.21, "height": 0.5,
              "swing": 0.0, "pump": 0.4, "drive": 0.1},
}


def get_path(state: dict, path: str):
    v = state
    for k in path.split("."):
        v = v[k]
    return v


def set_path(state: dict, path: str, value) -> None:
    keys = path.split(".")
    d = state
    for k in keys[:-1]:
        d = d[k]
    d[keys[-1]] = copy.deepcopy(value)


def family_of(tones: dict) -> str:
    """How a scale is tuned: "equal" if every tone but the home note is equal-tempered."""
    return "equal" if all(p == ET for k, ps in tones.items() if k != "0" for p in ps) else "just"


def preset_values(part: str, name: str, family: str = "just") -> dict:
    """A part preset's settings, path by path: every setting of the part.
    Shared: copy before changing."""
    return _preset_values(part, name, family)


@functools.lru_cache(maxsize=None)
def _preset_values(part: str, name: str, family: str) -> dict:
    change = dict(BY_PART[part][name][1])
    if "scale" in change:
        change["family"] = family
    s = merge(DEFAULT, change)
    return {path: copy.deepcopy(get_path(s, path)) for path in PARTS[part][1]}


def matching(state: dict) -> dict:
    """For each part, the preset its settings match now (None: none)."""
    family = family_of(state["tones"])
    out = {}
    for part, presets in BY_PART.items():
        here = {p: get_path(state, p) for p in PARTS[part][1]}
        out[part] = next((n for n in presets if preset_values(part, n, family) == here), None)
    return out


def apply_values(state: dict, values: dict) -> dict:
    """`state` with these settings, except the locked ones."""
    s = copy.deepcopy(state)
    for path, v in values.items():
        if path not in state["locks"]:
            set_path(s, path, v)
    return s


def _compose(key, harmony, melody, beat, sound, extra) -> dict:
    s = copy.deepcopy(DEFAULT)
    s["key"] = key
    for part, name in (("harmony", harmony), ("melody", melody), ("beat", beat), ("sound", sound)):
        for path, v in preset_values(part, name).items():
            set_path(s, path, v)
    return merge(s, extra)


class Invalid(ValueError):
    pass


# Names used before 2026-10-11's relabelling, in saved settings.
OLD_SCALES = {"Bright": "lydian", "Happy": "major", "Calm": "major_pentatonic", "Wistful": "dorian",
              "Sad": "minor", "Dark": "phrygian", "Dreamy": "whole_tone", "Eastern": "hirajoshi"}
OLD_TUNINGS = {"Pure": "just", "Standard": "equal"}
# A part's voice used to name its pattern too (until the split of 2026-10-11)
OLD_BASS = {"Sub": ("Sub", "Held"), "Soft": ("Soft", "Held"), "Fifths": ("Fifths", "Held"),
            "Offbeat": ("Synth", "Offbeat"), "Rolling": ("Synth", "Rolling"), "Acid": ("Acid", "Acid line")}
OLD_PULSE = {"Heartbeat": ("Thump", "Heartbeat"), "Arp": ("Pluck", "Arp"), "Arp 16ths": ("Pluck", "Arp 16ths"),
             "Glints": ("Glint", "Glints"), OFF: ("Pluck", OFF)}


def _old_chord_bars(pace: float, tempo: float) -> int:
    """Bars a chord lasted when the pace was a time (before 2026-10-11)."""
    import math
    n = 30 * 15 ** -pace / (240 / (50 + 100 * tempo))
    return int(min(16, max(1, 2 ** round(math.log2(max(n, 0.5))))))


def upgrade(saved: dict) -> dict:
    """Saved settings in today's form: a scale was a name, now it is tones."""
    s = dict(saved)
    if "feel" in s:
        s["scale"] = OLD_SCALES.get(s.pop("feel"), "major_pentatonic")
    if "scale" in s and "tones" not in s:
        s["tones"] = default_tones(preset_slots(s["scale"]) if s["scale"] in SCALES else [0, 2, 4, 7, 9])
    s.pop("scale", None)
    # a tuning mode became pitches per tone (2026-10-11): equal temperament
    # means every tone equal-tempered; adaptive became a switch
    tuning = OLD_TUNINGS.get(s.get("tuning"), s.get("tuning"))
    s.pop("tuning", None)
    if tuning == "equal" and isinstance(s.get("tones"), dict):
        s["tones"] = {k: (v if k == "0" else [ET]) for k, v in s["tones"].items()}
    if tuning == "adaptive":
        s["adaptive"] = True
    # a part's voice and its pattern became two settings; the pace became bars (2026-10-11)
    L = s.get("layers")
    if isinstance(L, dict) and "beat" not in s:
        L = s["layers"] = copy.deepcopy(L)
        beat = {}
        voice = lambda layer: (L.get(layer) or {}).get("voice")
        if voice("bass") in OLD_BASS:
            L["bass"]["voice"], beat["bass"] = OLD_BASS[voice("bass")]
        if voice("pad") == "Stabs":
            L["pad"]["voice"], beat["chords"] = "Synth stab", "Stabs"
        if voice("pulse") is not None:
            L["pulse"]["voice"], beat["pulse"] = OLD_PULSE.get(voice("pulse"), ("Pluck", OFF))
        if voice("drums") is not None:
            beat["drums"] = voice("drums") if voice("drums") in PATTERNS["drums"] else OFF
            L["drums"]["voice"] = "Electronic"
        s["beat"] = beat
    sh = s.get("shape")
    if isinstance(sh, dict) and "pace" in sh:
        sh = s["shape"] = dict(sh)
        bars = _old_chord_bars(float(sh.pop("pace")), float(sh.get("tempo", DEFAULT["shape"]["tempo"])))
        s["harmony"] = {**s.get("harmony", {}), "rhythm": RHYTHM_BARS.index(bars) / 4}
    h = s.get("harmony")
    if isinstance(h, dict) and "color" in h:  # Chord color (3 to 5 notes) became Chord size (0 to 5)
        h = s["harmony"] = dict(h)
        h["size"] = round((3 + 2 * float(h.pop("color"))) / 5, 3)
    if isinstance(s.get("locks"), list):
        s["locks"] = ["harmony.size" if p == "harmony.color" else p for p in s["locks"]]
        from .evolve import lockable
        locks = set()
        for path in s["locks"]:
            locks.add("harmony.rhythm" if path == "shape.pace" else path)
            if path in ("layers.bass", "layers.drums", "layers.pulse"):
                locks.add("beat." + path.split(".")[1])
            if path == "layers.pad":
                locks.add("beat.chords")
        s["locks"] = sorted(p for p in locks if p in lockable())
    return s


def merge(state: dict, change: dict) -> dict:
    """A copy of `state` with `change` applied, checked. Raises Invalid."""
    s = copy.deepcopy(state)
    family = change.get("family", "just")  # for a preset: how to tune its tones
    if family not in FAMILIES:
        raise Invalid(f"unknown tuning {family!r}")
    for k, v in change.items():
        if k == "family":
            continue
        if k == "key":
            if v not in KEYS:
                raise Invalid(f"unknown key {v!r}")
            s["key"] = v
        elif k == "scale":  # a preset: sets the tones, at their usual just ratios or equal-tempered
            if v not in SCALES:
                raise Invalid(f"unknown scale {v!r}")
            s["tones"] = default_tones(preset_slots(v), family)
        elif k == "tones":
            try:
                s["tones"] = check_tones(v)
            except ValueError as e:
                raise Invalid(str(e))
        elif k == "harmony":
            for name, x in _dict(v, k).items():
                if name == "style":
                    if x not in HARMONY_STYLES:
                        raise Invalid(f"unknown progression style {x!r}")
                    s["harmony"]["style"] = x
                elif name == "loop":
                    if isinstance(x, str) and x in LOOPS:  # a preset's name
                        x = LOOPS[x][0]
                    if not isinstance(x, list) or not 1 <= len(x) <= MAX_LOOP or not all(_entry_ok(e) for e in x):
                        raise Invalid(f"a loop is 1 to {MAX_LOOP} chords: scale degrees 1 to 7, borrowed chords or "
                                      "Roman numerals, each alone or as {chord, beats}")
                    s["harmony"]["loop"] = [dict(e) if isinstance(e, dict) else e for e in x]
                elif name == "chart":  # a chart in letter names, read in the key: the loop
                    try:
                        loop = parse_chart(str(x), s["key"], [int(t) for t in s["tones"]])
                    except ValueError as e:
                        raise Invalid(str(e))
                    if len(loop) > MAX_LOOP:
                        raise Invalid(f"a chart has {MAX_LOOP} chords at most; this one has {len(loop)}")
                    s["harmony"]["loop"], s["harmony"]["style"] = loop, "Loop"
                elif name in ("length", "resolve", "rhythm", "size", "borrow"):
                    s["harmony"][name] = _unit(x, name)
                elif name == "plain":
                    if not isinstance(x, bool):
                        raise Invalid("plain must be true or false")
                    s["harmony"]["plain"] = x
                else:
                    raise Invalid(f"unknown harmony setting {name!r}")
        elif k == "beat":
            for name, x in _dict(v, k).items():
                if name not in PATTERNS:
                    raise Invalid(f"unknown part {name!r}")
                if x not in PATTERNS[name] and not (x == OFF and name in PATTERN_OFF):
                    raise Invalid(f"unknown {name} pattern {x!r}")
                s["beat"][name] = x
        elif k == "melody":
            for name, x in _dict(v, k).items():
                if name == "style":
                    if x not in MELODY_STYLES:
                        raise Invalid(f"unknown melody style {x!r}")
                    s["melody"]["style"] = x
                elif name in ("phrase", "variation", "range", "leaps", "syncopation", "pickups", "pull",
                              "density"):
                    s["melody"][name] = _unit(x, name)
                else:
                    raise Invalid(f"unknown melody setting {name!r}")
        elif k == "evolve":
            for name, x in _dict(v, k).items():
                if name == "target":
                    if x is not None and (not isinstance(x, list) or len(x) != 2):
                        raise Invalid("target must be [energy, brightness] or null")
                    s["evolve"]["target"] = None if x is None else [_unit(x[0], "energy"), _unit(x[1], "brightness")]
                    continue
                if name not in ("rate", "size", "count", "pull"):
                    raise Invalid(f"unknown evolution setting {name!r}")
                s["evolve"][name] = _unit(x, name)
        elif k == "locks":
            from .evolve import lockable
            names = lockable()
            if isinstance(v, list):  # the whole set (saved settings, moods)
                v = {path: True for path in v}
                locks = set()
            else:  # {path: on or off} from the page
                locks = set(s["locks"])
            for path, on in _dict(v, k).items():
                if path not in names:
                    raise Invalid(f"cannot lock {path!r}")
                (locks.add if on else locks.discard)(path)
            s["locks"] = sorted(locks)
        elif k == "adaptive":
            if not isinstance(v, bool):
                raise Invalid("adaptive must be true or false")
            s["adaptive"] = v
        elif k == "volume":
            s["volume"] = _unit(v, k)
        elif k == "shape":
            for name, x in _dict(v, k).items():
                if name not in SHAPE:
                    raise Invalid(f"unknown control {name!r}")
                s["shape"][name] = _unit(x, name)
        elif k == "layers":
            for layer, lc in _dict(v, k).items():
                if layer not in LAYERS:
                    raise Invalid(f"unknown layer {layer!r}")
                for f, x in _dict(lc, layer).items():
                    if f == "voice":
                        if x not in LAYERS[layer] and not (x == OFF and layer not in NO_OFF):
                            raise Invalid(f"unknown {layer} voice {x!r}")
                        s["layers"][layer]["voice"] = x
                    elif f == "level":
                        s["layers"][layer]["level"] = _unit(x, f"{layer} level")
                    else:
                        raise Invalid(f"unknown setting {f!r}")
        else:
            raise Invalid(f"unknown setting {k!r}")
    return s


def keep_locked(new: dict, old: dict) -> dict:
    """`new`, with every locked setting (and the locks and evolution
    settings themselves) as in `old`. For moods and surprises."""
    s = copy.deepcopy(new)
    for path in old["locks"]:
        if "." in path:
            group, name = path.split(".", 1)
            s[group][name] = copy.deepcopy(old[group][name])
        else:
            s[path] = copy.deepcopy(old[path])
    s["locks"] = list(old["locks"])
    s["evolve"] = dict(old["evolve"])
    return s


def surprise(state: dict, rng: random.Random) -> dict:
    """Something new that still sounds fine: a preset for each part, at
    random, in a random key; now and then a part's voice swapped."""
    s = copy.deepcopy(state)
    s["key"] = rng.choice(KEYS)
    family = family_of(state["tones"])
    for part, presets in BY_PART.items():
        for path, v in preset_values(part, rng.choice(list(presets)), family).items():
            set_path(s, path, v)
    for layer in ("pad", "bass", "melody"):
        if rng.random() < 0.3:
            s["layers"][layer]["voice"] = rng.choice(list(LAYERS[layer]))
    return s


def _entry_ok(e) -> bool:
    if isinstance(e, dict):
        b = e.get("beats")
        return (set(e) <= {"chord", "beats"} and valid_chord(e.get("chord"))
                and (b is None or (isinstance(b, (int, float)) and not isinstance(b, bool) and 0.25 <= b <= 64)))
    return valid_chord(e)


def _unit(x, name) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        raise Invalid(f"{name} must be a number")
    return min(1.0, max(0.0, x))


def _dict(v, name) -> dict:
    if not isinstance(v, dict):
        raise Invalid(f"{name} must be an object")
    return v


# The presets, each a whole state (ambient/presets.py WHOLE)
MOODS = {name: _compose(*parts[1:]) for name, parts in WHOLE.items()}
