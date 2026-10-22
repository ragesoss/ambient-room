"""Evolution: the music changes itself, one unlocked setting at a time.

Each step picks one setting that is not locked and moves it a little (or,
with larger steps, a lot): a slider up or down, a part's voice or level, the
key up or down a fifth, a scale tone moved a half step, added, removed or
retuned. step() returns the new settings and a plain description of the
change.
"""

import random

from . import music
from .presets import PARTS
from .sounds import LABELS, LAYERS, OFF, PATTERN_OFF, PATTERNS

SHAPE_NAMES = {"bright": "Brightness", "motion": "Motion", "space": "Space", "echo": "Echo", "notes": "Notes",
               "tempo": "Tempo", "height": "Height", "swing": "Swing", "pump": "Pump", "drive": "Drive"}
VOICE_NAMES = {"pad": "Chords voice", "bass": "Bass voice", "melody": "Melody voice", "texture": "Atmosphere",
               "pulse": "Rhythm part voice", "drums": "Drum kit"}
BEAT_NAMES = {"drums": "Drum pattern", "bass": "Bass line", "chords": "Chord rhythm", "pulse": "Rhythm part"}
# Where evolution keeps each slider: wide, but short of the extremes.
SHAPE_RANGE = {"bright": (0.1, 0.9), "motion": (0.05, 0.85), "space": (0.2, 0.95), "echo": (0, 0.75),
               "notes": (0.05, 0.9), "tempo": (0.05, 0.95), "height": (0.2, 0.8),
               "swing": (0, 0.6), "pump": (0, 0.85), "drive": (0, 0.7)}


def name_of(path: str) -> str:
    group, _, k = path.partition(".")
    return {"volume": "Volume", "key": "Key", "tones": "Scale tones", "adaptive": "Retune each chord pure"}.get(path) or {
        "layers": VOICE_NAMES, "beat": BEAT_NAMES, "shape": SHAPE_NAMES, "harmony": HARMONY_NAMES,
        "melody": MELODY_NAMES}[group][k]


def lockable() -> dict[str, str]:
    """Every setting that can be locked, part by part, with its name on the page."""
    paths = [p for _, ps in PARTS.values() for p in ps] + ["key", "adaptive", "volume"]
    return {p: name_of(p) for p in paths}


def weights() -> dict[str, float]:
    """How often each setting is the one that changes."""
    w = {"volume": 0.3, "key": 0.6, "tones": 2.0, "adaptive": 0.15}
    w.update({f"layers.{k}": 1.2 for k in LAYERS})
    w.update({f"beat.{k}": 0.9 for k in PATTERNS})
    w.update({f"shape.{k}": 1.0 for k in SHAPE_NAMES})
    w["shape.tempo"] = 0.6
    w.update({"melody.style": 0.4, "melody.phrase": 0.5, "melody.variation": 0.5, "melody.range": 0.5, "melody.leaps": 0.5,
              "melody.syncopation": 0.5, "melody.pickups": 0.4})
    w.update({"harmony.style": 0.3, "harmony.loop": 0.6, "harmony.length": 0.3, "harmony.resolve": 0.4,
              "harmony.rhythm": 0.8, "harmony.size": 0.5, "harmony.plain": 0.15, "harmony.borrow": 0.4})
    return w


def get(state: dict, path: str):
    """The value at a setting's path: "key", "shape.bright", "layers.pad" ..."""
    v = state
    for k in path.split("."):
        v = v[k]
    return v


def describe(path: str, a, b, state: dict) -> str:
    """A change to one setting, in words, as evolution's changes are shown."""
    name = name_of(path)
    if path == "tones":
        slots_a, slots_b = sorted(int(k) for k in a), sorted(int(k) for k in b)
        deg = music.degree_names(slots_b)
        added = [music.pretty(deg[x]) for x in slots_b if x not in slots_a]
        gone = [music.pretty(music.degree_names(slots_a)[x]) for x in slots_a if x not in slots_b]
        preset = music.matching_preset(slots_b)
        parts = ([f"added {', '.join(added)}"] if added else []) + ([f"removed {', '.join(gone)}"] if gone else [])
        if not parts:
            parts = ["retuned"]
        return "Scale: " + ("; ".join(parts) if not preset or not (added or gone) else f"now {music.SCALES[preset][0]}")
    if path == "harmony.loop":
        from . import harmony
        slots = music.slots_of(state["tones"])
        nums = lambda loop: "–".join(harmony.numeral(state["key"], slots, d) for d in loop)
        return f"Loop: {nums(a)} → {nums(b)}"
    if path == "key":
        return f"Key: {music.pretty(a)} → {music.pretty(b)}"
    if isinstance(a, bool):
        return f"{name}: {'on' if b else 'off'}"
    if isinstance(a, dict) and "voice" in a:
        if a["voice"] != b["voice"]:
            return f"{name}: {a['voice']} → {b['voice']}"
        return f"{name} level {a['level']:.2f} → {b['level']:.2f}"
    if isinstance(a, (int, float)):
        return f"{name} {a:.2f} → {b:.2f}"
    return f"{name}: {a} → {b}"


def diff(old: dict, new: dict) -> list[tuple[str, str]]:
    """What changed from `old` to `new`, setting by setting: (path, words)."""
    out = []
    for path in lockable():
        a, b = get(old, path), get(new, path)
        if a != b:
            out.append((path, describe(path, a, b, new)))
    return out


def interval_s(rate: float) -> float:
    """Seconds between changes: about 3 minutes at the slowest, 5 s at the fastest."""
    return 200 * 0.025 ** rate


# ---- where the music is: calm to energetic, dark to bright ----

DRUM_ENERGY = {"Off": 0, "Pulse": 0.2, "Downtempo": 0.35, "Half-time": 0.45, "Breaks": 0.65, "House": 0.75, "Techno": 0.9,
               "Rock": 0.7, "Funk": 0.7, "One drop": 0.4, "Disco": 0.75, "Trap": 0.7, "Swing": 0.5, "Train": 0.55}
BASS_LINE_ENERGY = {"Held": 0.1, "Root–fifth": 0.3, "Half-time": 0.45, "Eighths": 0.65, "Octaves": 0.7, "Offbeat": 0.6,
                    "Rolling": 0.8, "Tresillo": 0.6, "Funk": 0.75, "Dub": 0.35, "Walking": 0.5, "Arpeggio": 0.5,
                    "Acid line": 0.9, "Walk-ups": 0.35}
BASS_ENERGY = {"Off": 0, "Sub": 0.05, "Fifths": 0.05, "Soft": 0.15, "Upright": 0.3, "Synth": 0.5, "Electric": 0.5,
               "808": 0.6, "Moog": 0.6, "Acid": 0.8, "Reese": 0.8}
PULSE_ENERGY = {"Off": 0, "Heartbeat": 0.3, "Glints": 0.3, "Arp": 0.6, "Arp 16ths": 0.85, "Roll": 0.7, "Alternating roll": 0.7}
PAD_ENERGY = {"Off": 0, "Air": 0.1, "Choir": 0.2, "Warm": 0.25, "Strings": 0.25, "Glass": 0.3, "Organ": 0.3,
              "Piano": 0.3, "Keys": 0.4, "Brass": 0.6, "Guitar": 0.7, "Supersaw": 0.8, "Synth stab": 0.8,
              "Acoustic guitar": 0.4, "Nylon guitar": 0.3, "Mandolin": 0.5, "Banjo": 0.6}
CHORDS_ENERGY = {"Held": 0.1, "Comp": 0.6, "Offbeat": 0.7, "Strum": 0.7, "Stabs": 0.8, "Eighths": 0.8, "Chop": 0.6,
                 "Boom-chick": 0.55, "Travis": 0.45}
MELODY_ENERGY = {"Off": 0.1, "Flute": 0.2, "Felt": 0.2, "Bell": 0.3, "Kalimba": 0.4, "Pluck": 0.5,
                 "Synth pluck": 0.75, "Lead": 0.8, "E. piano": 0.35, "Vibes": 0.35, "Strings": 0.3, "Chip": 0.7,
                 "Brass": 0.65, "Sync lead": 0.9, "Saw stack": 0.85, "Marimba": 0.45, "Steel drum": 0.5, "Harp": 0.3,
                 "Voice": 0.3, "Organ lead": 0.5, "Guitar": 0.55}
HARMONY_NAMES = {"style": "Progression", "loop": "Loop chords", "length": "Cycle length", "resolve": "Resolution",
                 "rhythm": "Harmonic rhythm", "size": "Chord size", "plain": "Major and minor triads only",
                 "borrow": "Borrowing"}
MELODY_NAMES = {"style": "Melody style", "phrase": "Phrase length", "variation": "Variation",
                "range": "Melodic range", "leaps": "Leaps", "syncopation": "Syncopation", "pickups": "Pickups",
                "pull": "The tune", "density": "Note density"}


def energy(s: dict) -> float:
    """Calm (0) to energetic (1): tempo, drums, how rhythmic the parts are."""
    sh, L, B = s["shape"], s["layers"], s["beat"]
    drums = DRUM_ENERGY[B["drums"]] * (0.5 + 0.5 * L["drums"]["level"])
    return (0.25 * sh["tempo"] + 0.25 * drums + 0.07 * BASS_LINE_ENERGY[B["bass"]] + 0.03 * BASS_ENERGY[L["bass"]["voice"]]
            + 0.06 * PULSE_ENERGY[B["pulse"]] + 0.03 * PAD_ENERGY[L["pad"]["voice"]] + 0.03 * CHORDS_ENERGY[B["chords"]]
            + 0.03 * MELODY_ENERGY.get(L["melody"]["voice"], 0.4) + 0.1 * sh["notes"] + 0.07 * s["harmony"]["rhythm"]
            + 0.04 * sh["drive"] + 0.04 * sh["pump"])


# each slot's place on the circle of fifths from the key note (the tritone
# counts as sharp unless the scale has a 4th and no 5th, as in Locrian)
FIFTHS = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 5: -1, 10: -2, 3: -3, 8: -4, 1: -5}


def scale_brightness(slots) -> float:
    """Dark (0) to bright (1): the mean place of the scale's tones on the circle
    of fifths. Lydian 1, Ionian 0.83, Dorian 0.5, Aeolian 0.33, Locrian 0."""
    ss = [x for x in slots if x]
    if not ss:
        return 0.5
    f = [(-6 if x == 6 and 5 in slots and 7 not in slots else FIFTHS[x]) for x in ss]
    return min(1.0, max(0.0, (sum(f) / len(f) + 3.5) / 7))


def brightness(s: dict) -> float:
    """Dark (0) to bright (1): the scale, the Brightness slider, the register."""
    return (0.5 * scale_brightness(music.slots_of(s["tones"])) + 0.3 * s["shape"]["bright"]
            + 0.2 * s["shape"]["height"])


def position(s: dict) -> tuple[float, float]:
    return round(energy(s), 3), round(brightness(s), 3)


def _distance(s: dict, target) -> float:
    e, b = position(s)
    return ((e - target[0]) ** 2 + (b - target[1]) ** 2) ** 0.5


def changes_at_once(count: float) -> int:
    """How many settings one step changes: 1 to 8."""
    return 1 + round(7 * count)


def step(state: dict, rng: random.Random, size: float, n: int = 1,
         target=None, pull: float = 0.0) -> tuple[dict, str] | tuple[None, None]:
    """Changes to `n` different unlocked settings, as (new state, what changed)."""
    new, items = step_detailed(state, rng, size, n, target, pull)
    return (new, "; ".join(text for _, text in items)) if new is not None else (None, None)


def step_detailed(state: dict, rng: random.Random, size: float, n: int = 1,
                  target=None, pull: float = 0.0) -> tuple[dict | None, list[tuple[str, str]]]:
    """As step(), with each change as (setting's path, what changed), for the page.

    With a target (energy, brightness), each change is the best of several
    random candidates: the one that brings the music nearest the target. More
    pull, more candidates: from 1 (a free wander) to 8 (a fairly straight walk).
    """
    from .state import merge  # state imports this module's lockable()
    locks = set(state.get("locks", []))
    w = {k: v for k, v in weights().items() if k not in locks}
    tries = 1 + round(7 * pull) if target is not None else 1
    items = []
    for _ in range(n):
        best = None
        for _ in range(tries):
            cand = _candidate(state, w, rng, size, merge)
            if cand is None:
                break
            path, new, text = cand
            d = _distance(new, target) if target is not None else 0.0
            if best is None or d < best[0]:
                best = (d, path, new, text)
        if best is None:
            break
        _, path, state, text = best
        items.append((path, text))
        del w[path]  # each setting changes once per step
    if not items:
        return None, []
    return state, items


def _candidate(state, w, rng, size, merge):
    """One random change to one setting still free to change: (path, new state, text)."""
    tried = set()
    for _ in range(8):  # a move can find nothing to do (a scale already at its smallest)
        free = {k: v for k, v in w.items() if k not in tried}
        if not free:
            return None
        path = rng.choices(list(free), weights=list(free.values()))[0]
        change, text = _move(path, state, rng, size)
        if change:
            return path, merge(state, change), text
        tried.add(path)
    return None


def _nudge(x: float, lo: float, hi: float, rng: random.Random, size: float, scale: float = 1.0) -> float:
    d = rng.gauss(0, 0.05 + 0.25 * size) * scale
    if abs(d) < 0.03 * scale:
        d = 0.03 * scale if d >= 0 else -0.03 * scale
    y = min(hi, max(lo, x + d))
    if abs(y - x) < 0.01:  # at a bound: go the other way
        y = min(hi, max(lo, x - d))
    return round(y, 2)


def _move(path: str, s: dict, rng: random.Random, size: float):
    if path.startswith("shape."):
        k = path[6:]
        x = s["shape"][k]
        y = _nudge(x, *SHAPE_RANGE[k], rng, size, 0.5 if k == "tempo" else 1.0)
        return {"shape": {k: y}}, f"{SHAPE_NAMES[k]} {x:.2f} → {y:.2f}"
    if path == "volume":
        x = s["volume"]
        y = _nudge(x, 0.3, 0.9, rng, size, 0.5)
        return {"volume": y}, f"Volume {x:.2f} → {y:.2f}"
    if path.startswith("layers."):
        return _layer(path[7:], s, rng, size)
    if path.startswith("beat."):
        part = path[5:]
        now = s["beat"][part]
        choices = [p for p in list(PATTERNS[part]) + ([OFF] if part in PATTERN_OFF else []) if p != now]
        v = rng.choices(choices, weights=[0.5 if p == OFF else 1.0 for p in choices])[0]
        return {"beat": {part: v}}, f"{BEAT_NAMES[part]}: {now} → {v}"
    if path == "key":
        return _key(s, rng, size)
    if path == "tones":
        return _tones(s, rng, size)
    if path.startswith("harmony."):
        return _harmony(path[8:], s, rng, size)
    if path.startswith("melody."):
        k = path[7:]
        if k == "style":
            from .melody import STYLES
            v = rng.choice([x for x in STYLES if x not in (s["melody"]["style"], "Tune")])  # the tune's: chosen only
            return {"melody": {"style": v}}, f"Melody style: {s['melody']['style']} → {v}"
        x = s["melody"][k]
        y = _nudge(x, 0.05, 0.95, rng, size)
        return {"melody": {k: y}}, f"{MELODY_NAMES[k]} {x:.2f} → {y:.2f}"
    if path == "adaptive":
        on = not s["adaptive"]
        return {"adaptive": on}, f"Retune each chord pure: {'on' if on else 'off'}"
    return None, None


def _harmony(k: str, s: dict, rng: random.Random, size: float):
    from . import harmony
    h = s["harmony"]
    slots = music.slots_of(s["tones"])
    nums = lambda loop: "–".join(harmony.numeral(s["key"], slots, d) for d in loop)
    if k == "style":
        v = rng.choice([x for x in harmony.STYLES if x != h["style"]])
        return {"harmony": {"style": v}}, f"Progression: {h['style']} → {v}"
    if k == "loop":
        if h["style"] != "Loop":
            return None, None  # unheard
        return _loop(h, slots, rng, size, nums)
    if k == "plain":
        return {"harmony": {"plain": not h["plain"]}}, f"Major and minor triads only: {'off' if h['plain'] else 'on'}"
    x = h[k]
    if k == "rhythm":  # a stop at a time: twice or half as many chords
        from .harmony import chord_bars
        y = min(1.0, max(0.0, x + rng.choice([-0.25, 0.25])))
        if y == x:
            y = x - 0.25 if x >= 1 else x + 0.25
        return {"harmony": {"rhythm": y}}, f"Harmonic rhythm: {chord_bars(x)} → {chord_bars(y)} bars a chord"
    y = _nudge(x, 0.05, 0.95, rng, size)
    return {"harmony": {k: y}}, f"{HARMONY_NAMES[k]} {x:.2f} → {y:.2f}"


def _loop(h: dict, slots, rng: random.Random, size: float, nums):
    """One change to a loop, of every kind its editor can make: another
    chord (any in the vocabulary, the scale's own most often), a seventh
    added or dropped, a chord split in two or two merged, one twice or half
    as long, one inserted or taken out, the whole loop repeated with a
    change or halved, or another loop altogether."""
    from . import harmony
    loop = list(h["loop"])
    bar = harmony.chord_bars(h["rhythm"]) * 4  # beats a chord without its own length lasts
    beats = lambda e: harmony.beats_of(e) or bar
    entry = lambda c, b: c if b is None else {"chord": c, "beats": b}
    vocab = harmony.vocabulary(slots)
    have = set(harmony._numbers(slots))  # degrees the scale has: its own chords, the likeliest
    own, named = [d for d in vocab if isinstance(d, int) and d in have], [d for d in vocab if d in harmony.BORROWED]
    others = [d for d in vocab if isinstance(d, str) and d not in harmony.BORROWED]

    def a_chord(avoid):
        w = [1.0] * len(own) + [0.05 + 0.6 * h["borrow"]] * len(named) + [0.002 + 0.03 * h["borrow"]] * len(others)
        pool = [(c, x) for c, x in zip(own + named + others, w) if harmony.item_slot(slots, c) not in avoid]
        return rng.choices([c for c, _ in pool], weights=[x for _, x in pool])[0]

    n = len(loop)
    i = rng.randrange(n)
    c, b = harmony.chord_of(loop[i]), harmony.beats_of(loop[i])
    moves = {"preset": 0.06 + 0.2 * size, "chord": 0.45, "seventh": 0.08, "split": 0.08 if beats(loop[i]) >= 2 and n < harmony.MAX_LOOP else 0,
             "merge": 0.08 if n > 1 and beats(loop[min(i, n - 2)]) + beats(loop[min(i, n - 2) + 1]) <= 32 else 0,
             "longer": 0.05 if beats(loop[i]) <= 16 else 0, "shorter": 0.05 if beats(loop[i]) >= 2 else 0,
             "insert": 0.05 if n < harmony.MAX_LOOP else 0, "remove": 0.05 if n > 1 else 0,
             "twice": 0.04 if 2 * n <= harmony.MAX_LOOP else 0, "half": 0.04 if n >= 4 and n % 2 == 0 else 0}
    m = rng.choices(list(moves), weights=list(moves.values()))[0]
    new, what = list(loop), ""
    if m == "preset":
        name, (new, _) = rng.choice([(nm, p) for nm, p in harmony.PRESETS.items() if p[0] != loop])
        what = f" ({name})"
    elif m == "chord":
        new[i] = entry(a_chord({harmony.item_slot(slots, c)}), b)
    elif m == "seventh":  # written out, so the chord keeps it whatever the chord size
        root = harmony.item_slot(slots, c)
        r = harmony.roman(c) if isinstance(c, str) and c not in harmony.BORROWED else None
        ivs = r[1] if r else [(p - harmony.build("C", slots, c, 3, True, rng)[0]) % 12
                               for p in harmony.build("C", slots, c, 3, True, rng)]
        if r and r[2]:  # drop it
            kind = "dim" if ivs[2] == 6 else "min" if ivs[1] == 3 else "maj"
        else:  # add one: minor 7 on a minor chord, dominant on V and the secondary dominants' roots, else major 7
            kind = "m7" if ivs[1] == 3 else "7" if root in (7, 2, 4, 9, 11, 10) else "maj7"
        new[i] = entry(harmony.any_chord(root, kind), b)
        what = " (a seventh " + ("dropped)" if r and r[2] else "added)")
    elif m == "split":  # two halves: the second a chord leading on
        half = beats(loop[i]) / 2
        new[i:i + 1] = [entry(c, half), entry(a_chord({harmony.item_slot(slots, c)}), half)]
        what = " (a chord split in two)"
    elif m == "merge":  # this chord and the next (the last: with the one before), at most 8 bars
        j = min(i, n - 2)
        new[j:j + 2] = [entry(harmony.chord_of(loop[j]), beats(loop[j]) + beats(loop[j + 1]))]
        what = " (two chords made one)"
    elif m in ("longer", "shorter"):
        new[i] = entry(c, beats(loop[i]) * (2 if m == "longer" else 0.5))
        what = f" (a chord {'twice' if m == 'longer' else 'half'} as long)"
    elif m == "insert":
        new.insert(i + 1, entry(a_chord({harmony.item_slot(slots, c)}), b))
        what = " (a chord added)"
    elif m == "remove":
        del new[i]
        what = " (a chord taken out)"
    elif m == "twice":  # the loop again, with a chord changed in the repeat (not its last)
        new = loop + loop
        if n > 1:
            j = rng.randrange(n, 2 * n - 1)
            new[j] = entry(a_chord({harmony.item_slot(slots, harmony.chord_of(new[j]))}), harmony.beats_of(new[j]))
        what = " (twice as long)"
    else:
        new = loop[: n // 2]
        what = " (half as long)"
    if new == loop:
        return None, None
    return {"harmony": {"loop": new}}, f"Loop: {nums(loop)} → {nums(new)}{what}"


def _layer(layer: str, s: dict, rng: random.Random, size: float):
    lc, name = s["layers"][layer], VOICE_NAMES[layer]
    voices = list(LAYERS[layer])
    if lc["voice"] == OFF or rng.random() < 0.35 + 0.3 * size:
        # a new voice; the chords never go silent, the melody, bass and atmosphere sometimes do
        # (drums and the rhythm part go quiet by their pattern)
        choices = [v for v in voices + ([OFF] if layer in ("bass", "melody", "texture") else []) if v != lc["voice"]]
        weights = [0.6 if v == OFF else 1.0 for v in choices]
        v = rng.choices(choices, weights=weights)[0]
        return {"layers": {layer: {"voice": v}}}, f"{name}: {lc['voice']} → {v}"
    x = lc["level"]
    y = _nudge(x, 0.15, 0.9, rng, size)
    return {"layers": {layer: {"level": y}}}, f"{LABELS[layer][0]} level {x:.2f} → {y:.2f}"


def _key(s: dict, rng: random.Random, size: float):
    i = music.KEYS.index(s["key"])
    if rng.random() < size * 0.5:
        d = rng.choice([1, 2, 3, 4, 5, 6, -1, -2, -3, -4, -5])
        how = f"{'up' if d > 0 else 'down'} {abs(d)} half step{'s' if abs(d) > 1 else ''}"
    else:
        d = rng.choice([7, -7])
        how = "up a fifth" if d > 0 else "down a fifth"
    k = music.KEYS[(i + d) % 12]
    return {"key": k}, f"Key: {music.pretty(s['key'])} → {music.pretty(k)} ({how})"


def _tones(s: dict, rng: random.Random, size: float):
    """Move a tone a half step, add one, remove one, or retune one."""
    tones = {int(k): list(v) for k, v in s["tones"].items()}
    slots = sorted(tones)
    et = all(p == music.ET for k, ps in tones.items() if k for p in ps)  # keep the scale's tuning family

    def fresh(slot):
        return [music.ET] if et else [music.frac(music.PALETTE[slot][0])]

    def name(slot, ss):
        names, deg = music.spell(s["key"], ss), music.degree_names(ss)
        return f"{music.pretty(deg[slot])} ({music.pretty(names[(music.KEYS.index(s['key']) + slot) % 12])})"

    moves = ["move"] * 6 + ["add"] * 2 + ["remove"] * 2 + (["retune"] if not et else [])
    for _ in range(10):
        m = rng.choice(moves)
        if m == "move":
            k = rng.choice([x for x in slots if x])
            to = k + rng.choice([1, -1])
            if to in tones or not 0 < to < 12:
                continue
            new = {x: v for x, v in tones.items() if x != k}
            new[to] = fresh(to)
            text = f"Scale: {name(k, slots)} → {name(to, sorted(new))}"
        elif m == "add" and len(slots) < 9:
            free = [x for x in range(1, 12) if x not in tones]
            # favour tones a third, fourth or fifth from one already there
            near = [x for x in free if any((x - y) % 12 in (3, 4, 5, 7, 8, 9) for y in slots)]
            to = rng.choice(near or free)
            new = dict(tones)
            new[to] = fresh(to)
            text = f"Scale: added {name(to, sorted(new))}"
        elif m == "remove" and len(slots) > 4:
            k = rng.choice([x for x in slots if x])
            new = {x: v for x, v in tones.items() if x != k}
            text = f"Scale: removed {name(k, slots)}"
        elif m == "retune":
            k = rng.choice([x for x in slots if x])
            options = [music.frac(r) for r in music.PALETTE[k] if music.frac(r) not in tones[k]]
            if not options:
                continue
            r = rng.choice(options)
            new = dict(tones)
            new[k] = [r]
            text = f"Scale: {name(k, slots)} now {r}"
        else:
            continue
        out = {str(x): v for x, v in sorted(new.items())}
        preset = music.matching_preset(sorted(new))
        if preset:
            text += f", now {music.SCALES[preset][0]}"
        return {"tones": out}, text
    return None, None
