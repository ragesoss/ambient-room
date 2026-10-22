"""Presets for one part of the sound at a time, and combinations of them.

A sound has four parts. Each setting belongs to one:

- Harmony: the scale, the progression, the harmonic rhythm, the chord color.
- Melody: the line's style and shape, how busy it is, its register.
- Beat: the tempo and feel, and the pattern each part in time plays.
- Sound: who plays each part (the voices) and how loud, the atmosphere,
  and the room (space, echo, brightness, motion, drive).

The key, the tuning and the volume belong to none: no preset changes them.
A part preset sets every setting of its part (a setting it does not name
takes the default), so it sounds the same whatever was there before.
A song is a harmony and a melody; a style is a beat and a sound; a mood is
all four, in a key.
"""

from .harmony import parse_chart
from .music import preset_slots
from .sounds import OFF

PARTS = {
    "harmony": ("Harmony", ["tones", "harmony.style", "harmony.loop", "harmony.length", "harmony.resolve",
                            "harmony.rhythm", "harmony.size", "harmony.plain", "harmony.borrow"]),
    "melody": ("Melody", ["melody.style", "melody.phrase", "melody.variation", "melody.range", "melody.leaps",
                          "melody.syncopation", "melody.pickups", "melody.pull", "melody.density", "shape.notes",
                          "shape.height"]),
    "beat": ("Beat", ["shape.tempo", "shape.swing", "shape.pump", "beat.drums", "beat.bass", "beat.chords",
                      "beat.pulse"]),
    "sound": ("Sound", ["layers.pad", "layers.bass", "layers.melody", "layers.pulse", "layers.drums",
                        "layers.texture", "shape.space", "shape.echo", "shape.bright", "shape.motion",
                        "shape.drive"]),
}
OUTSIDE = ["key", "adaptive", "volume"]  # in no part


def part_of(path: str) -> str | None:
    for part, (_, paths) in PARTS.items():
        if path in paths:
            return part
    return None


def _h(scale, style="Wander", rhythm=0.25, color=0.7, loop=None, length=0.5, resolve=0.5, plain=False, borrow=0.0):
    """color: 0 triads, 0.5 sevenths, 1 ninths, or a mix (Chord size 3 to 5)"""
    h = {"style": style, "rhythm": rhythm, "size": round((3 + 2 * color) / 5, 3), "length": length,
         "resolve": resolve, "plain": plain, "borrow": borrow}
    if loop:
        h["loop"] = loop
    return {"scale": scale, "harmony": h}


def _m(style="Scattered", notes=0.3, height=0.5, **line):
    return {"melody": {"style": style, **line}, "shape": {"notes": notes, "height": height}}


def _b(tempo, drums=OFF, bass="Held", chords="Held", pulse=OFF, swing=0.0, pump=0.3):
    return {"shape": {"tempo": tempo, "swing": swing, "pump": pump},
            "beat": {"drums": drums, "bass": bass, "chords": chords, "pulse": pulse}}


def _s(pad, bass, melody, texture=(OFF, 0.3), pulse=("Pluck", 0.4), drums=("Electronic", 0.6),
       space=0.6, echo=0.2, bright=0.4, motion=0.3, drive=0.1):
    lay = lambda v: {"voice": v[0], "level": v[1]}
    return {"layers": {"pad": lay(pad), "bass": lay(bass), "melody": lay(melody), "texture": lay(texture),
                       "pulse": lay(pulse), "drums": lay(drums)},
            "shape": {"space": space, "echo": echo, "bright": bright, "motion": motion, "drive": drive}}


# The player's own fiddle tune (2026-10-11, from its Strum Machine chart): an
# A part of 8 bars, a B part of 10. Read in C; kept as degrees, so it plays
# in any key. The bass notes after slashes (G/D, F/C, E/B, Em/B) are left out.
FIDDLE_TUNE = parse_chart("""
| C / | F G | C / | F G/D |
| C / | F G | C / | F/C E/B |
| Am / | Em / | F / | C Em/B |
| Am / | Em / | F / | / / |
| E / | E7 / |
""", "C", preset_slots("major"))

# Three dobro tunes the player plays (~/play/dobro-transcription, tunes/dobro), from the player's
# Strum Machine charts (2026-10-14), read in G and kept as degrees. The dominants are written as
# sevenths where the melodies lean on them (Red Wing's C over D, Down Yonder's G over A, its F
# over G going to C): a written seventh sounds even with plain triads, and the melody counts it
# a chord tone. Red Wing and Down Yonder are laid in two: two bars of the tune to a bar here, at
# half its tempo, so the melody's running sixteenths are the tune's eighths (tools/tune_fit.py).
# A chord lasts a beat here at least (half a bar of the tune): Red Wing's turnaround A D G in its
# 8th bar is D7 G.
RED_WING = parse_chart("""
| G / C G | D7 G A7 D7 | G / C G | D7 G D7 G |
| C G | D7 G | C G | D7 G |
""", "G", preset_slots("major"))
DOWN_YONDER = parse_chart("""
| G G7 | C | G | G | A7 | D7 | G G7 | C | G | A7 D7 G / |
""", "G", preset_slots("major"))
# Bar for bar; both parts twice, the second time with the second ending, as played
BIG_SCIOTA = parse_chart("""
| G / | G / | G C | D7 G | G / | G / | G C | D7 G |
| G D7 | D7 C | C Em | D7 G | G D7 | D7 C | C Em | D7 G |
""", "G", preset_slots("major"))
# Cherokee Shuffle (tunes/dobro/cherokee-shuffle/chords.txt there): the player's Strum Machine chart (2026-10-16), in
# A, read in A and kept as degrees. An A part of 8 bars and a B part of 10 (its last two the A part's ending), each
# twice as played (both endings A), laid in two as Red Wing (recorded at 170: 85 here). B's 9th bar, D for two beats
# and E for two, is a beat of each here. A chord that goes on over a bar line is carried with "/": 31 chords, a loop
# holds 32 (harmony.MAX_LOOP).
CHEROKEE_SHUFFLE = parse_chart("""
| A / | / F#m | D A | E A |
| / / | / F#m | D A | E A |
| D A | D A | D A | / F#m | D E A / |
| D A | D A | D A | / F#m | D E A / |
""", "A", preset_slots("major"))

# The tunes' own melodies, for the Tune line (ambient/breaks.py): each chart above whose tune has an answer key in
# the transcription project (tunes/dobro/<folder>/<folder>.musicxml): its folder, its key, how many of its bars to a
# bar here (2: laid in two), the bars of one pass (Red Wing's key is played through twice: its first 16), and the
# bars of each part where a part is not a whole number of phrases (Cherokee's B, 10 bars: its phrases 4 and 6).
TUNE_MELODIES = {
    "Red Wing": {"folder": "red-wing", "key": "G", "k": 2, "bars": 16},
    "Down Yonder": {"folder": "down-yonder", "key": "G", "k": 2, "bars": 20},
    "Big Sciota": {"folder": "big-sciota", "key": "G", "k": 1, "bars": 16},
    "Cherokee Shuffle": {"folder": "cherokee-shuffle", "key": "A", "k": 2, "bars": 36, "parts": (8, 8, 10, 10)},
}

# Harmonic rhythm: 0 16 bars a chord, 0.25 8, 0.5 4, 0.75 2, 1 one bar.
HARMONY = {
    "Drift": ("Major pentatonic, wandering, a chord every 8 bars", _h("major_pentatonic")),
    "Lydian glow": ("Lydian, wandering slowly: bright and floating", _h("lydian", color=0.6)),
    "Deep": ("Natural minor, wandering very slowly", _h("minor", rhythm=0.0, color=0.75)),
    "Modal": ("Dorian, wandering: minor with a bright sixth", _h("dorian", color=0.75)),
    "Whole tone": ("Whole tone, wandering: dreamy, no home", _h("whole_tone", color=0.6)),
    "Phrygian": ("Phrygian, wandering every 4 bars: dark", _h("phrygian", rhythm=0.5, color=0.6)),
    "Hirajoshi": ("A Japanese pentatonic, very slow", _h("hirajoshi", rhythm=0.0, color=0.5)),
    "Pop": ("Major, I–V–vi–IV, two bars a chord, plain triads", _h("major", "Loop", 0.75, 0.15, [1, 5, 6, 4], plain=True)),
    "Doo-wop": ("Major, I–vi–IV–V, two bars a chord", _h("major", "Loop", 0.75, 0.1, [1, 6, 4, 5], plain=True)),
    "Ballad": ("Major, functional cycles of four that mostly come home", _h("major", "Functional", 0.75, 0.4, resolve=0.6, borrow=0.3)),
    "Minor ballad": ("Natural minor, functional cycles, sevenths", _h("minor", "Functional", 0.75, 0.75, borrow=0.5)),
    "Elegy": ("Natural minor, long cycles of eight that come home", _h("minor", "Functional", 0.75, 0.6, length=0.9, resolve=0.7, borrow=0.5)),
    "Canon": ("Major, Pachelbel's Canon, a chord a bar", _h("major", "Loop", 1.0, 0.25, [1, 5, 6, 3, 4, 1, 4, 5], plain=True)),
    "ii–v–i": ("Dorian, ii–v–i–i with ninths: lo-fi", _h("dorian", "Loop", 0.75, 0.9, [2, 5, 1, 1])),
    "Jazz": ("Major, the turnaround I–VI7–ii–V with ninths (VI7 borrowed: the V of ii)",
             _h("major", "Loop", 0.75, 0.95, [1, "V/ii", 2, 5], borrow=0.4)),
    "Epic minor": ("Natural minor, i–VI–III–VII, four bars a chord", _h("minor", "Loop", 0.5, 0.3, [1, 6, 3, 7], plain=True)),
    "Aeolian rock": ("Natural minor, i–VII–VI–VII", _h("minor", "Loop", 0.5, 0.45, [1, 7, 6, 7], plain=True)),
    "Dorian vamp": ("Dorian, i–IV back and forth, two bars each", _h("dorian", "Loop", 0.75, 0.8, [1, 4])),
    "Blues-rock": ("Mixolydian, I–IV–V–IV, two bars each; the V borrowed, major", _h("mixolydian", "Loop", 0.75, 0.5, [1, 4, "V", 4], plain=True)),
    "Fiddle tune chart": ("Major, the player's fiddle tune: an A part of 8 bars, a B part of 10; plain triads, E and E7 borrowed",
                          _h("major", "Loop", 1.0, 0.0, FIDDLE_TUNE, plain=True)),
    "Bluegrass": ("Major, I–IV–I–V | I–IV–V–I, a chord a bar, plain triads: a half cadence, then home",
                  _h("major", "Loop", 1.0, 0.0, [1, 4, 1, 5, 1, 4, 5, 1], plain=True)),
    "Phrygian drone": ("Phrygian, i and ♭II, eight bars each: techno", _h("phrygian", "Loop", 0.25, 0.3, [1, 2])),
    "Red Wing": ("Major, Red Wing's chart in two (two of its bars to a bar): a verse and a chorus; the dominants as sevenths",
                 _h("major", "Loop", 1.0, 0.0, RED_WING, plain=True)),
    "Down Yonder": ("Major, Down Yonder's chart in two (two of its bars to a bar): G7 into C, A7 to D7",
                    _h("major", "Loop", 1.0, 0.0, DOWN_YONDER, plain=True)),
    "Big Sciota": ("Major, Big Sciota's chart: two parts of 4 bars, each twice; plain triads, the dominants as sevenths",
                   _h("major", "Loop", 1.0, 0.0, BIG_SCIOTA, plain=True)),
    "Cherokee Shuffle": ("Major, Cherokee Shuffle's chart in two (two of its bars to a bar): an A part of 8 bars and a B "
                         "part of 10, each twice; plain triads",
                         _h("major", "Loop", 1.0, 0.0, CHEROKEE_SHUFFLE, plain=True)),
}

MELODY = {
    # Found by scoring settings against generic traits of a bluegrass break
    # (any instrument) over the Bluegrass mood's chart (2026-10-11): running
    # notes, chord tones on beats 1 and 3, mostly steps with skips through the
    # chord, few repeated notes, about half the phrases led into, a new line
    # each pass. Measured: 12.8 notes a bar, 90% chord tones on the strong
    # beats, 55% steps, 30% skips, 6% leaps, 9% repeats, no bar the same as
    # the pass before. Notes 0.87: past busy, running; 1 is frenetic.
    "Bluegrass break": ("Running two-bar phrases, new each time round: runs and chord outlines, chord tones on the beat",
                        _m("Phrases", 0.87, 0.45, phrase=0.3, variation=0.8, range=0.45, leaps=0.42, syncopation=0.35,
                           pickups=0.2)),
    # Found by scoring settings against three dobro tunes (Red Wing, Down Yonder, Big Sciota), each
    # over its own chart (2026-10-14, tools/tune_fit.py --search 150 --joint --style Phrases): notes a
    # bar, where in the bar they fall and how far apart, steps against skips and leaps, the span,
    # chord tones on beats 1 and 3; distance over 8 seeds (0: the tunes' own traits). Bar for bar:
    # Red Wing 6.1, Down Yonder 7.0, Big Sciota 3.8 in its mood (Bluegrass break 13.3, 13.2, 7.9).
    "Fiddle tune": ("A tune's melody at the tune's tempo: about six notes a bar, new each time, led into",
                    _m("Phrases", 0.49, 0.2, phrase=0.32, variation=0.97, range=0.43, leaps=0.44, syncopation=0.09,
                       pickups=1.0)),
    # In two, two bars of a tune to a bar at half its tempo (--half): its eighths are the line's
    # running sixteenths. In their moods Red Wing 4.1, Down Yonder 4.2 (Bluegrass break in two: 5.1 and 3.8).
    "Fiddle tune in two": ("A tune's melody in two: running notes in phrases of eight of its bars, led into",
                           _m("Phrases", 0.83, 0.26, phrase=0.65, variation=0.87, range=0.46, leaps=0.46,
                              syncopation=0.33, pickups=0.8)),
    "Sparse": ("Scattered notes, few", _m(notes=0.2)),
    "Scattered": ("Scattered notes, wandering", _m(notes=0.35)),
    "Song": ("Phrases that ask and answer, mid-range",
             _m("Phrases", 0.45, phrase=0.55, variation=0.3, range=0.5, leaps=0.3, syncopation=0.2, pickups=0.5)),
    "Lyrical": ("Long phrases, wide, leaning into the bar",
                _m("Phrases", 0.35, 0.45, phrase=0.8, variation=0.35, range=0.6, leaps=0.4, syncopation=0.1, pickups=0.6)),
    "Questions": ("Short phrases, two bars each, with pickups",
                  _m("Phrases", 0.4, phrase=0.3, variation=0.4, range=0.5, leaps=0.35, syncopation=0.25, pickups=0.7)),
    "Riff": ("A one-bar riff, syncopated, changing slowly",
             _m("Motif", 0.55, 0.55, phrase=0.55, variation=0.35, range=0.5, leaps=0.45, syncopation=0.6, pickups=0.4)),
    "Hook": ("A simple figure, close, repeating",
             _m("Motif", 0.55, 0.65, phrase=0.55, variation=0.25, range=0.35, leaps=0.3, syncopation=0.15, pickups=0.3)),
    "Busy": ("A busy line that keeps changing",
             _m("Motif", 0.65, 0.6, phrase=0.55, variation=0.45, range=0.6, leaps=0.5, syncopation=0.5, pickups=0.3)),
}

BEAT = {
    "Still": ("No drums, held bass and chords, slow", _b(0.2)),
    "Heartbeat": ("Slow, a soft heartbeat", _b(0.18, pulse="Heartbeat")),
    "Glints": ("Slow, glints on random sixteenths", _b(0.26, pulse="Glints")),
    "Arp drift": ("An eighth-note arpeggio, no drums", _b(0.34, pulse="Arp")),
    "Ambient pulse": ("A soft kick and hats under held chords", _b(0.25, "Pulse")),
    "Chamber": ("No drums: the bass on 1 and 3, an arpeggio", _b(0.38, bass="Root–fifth", pulse="Arp", pump=0.0)),
    "Folk": ("No drums: fingerpicked chords, the bass on 1 and 3", _b(0.45, bass="Root–fifth", chords="Travis", pump=0.0)),
    "Bluegrass": ("No drums: a bass walking into each chord, boom-chick guitar, a banjo roll, a touch of swing",
                  _b(0.65, bass="Walk-ups", chords="Boom-chick", pulse="Roll", swing=0.1, pump=0.0)),
    "Bluegrass in two": ("No drums, for a tune laid in two (two of its bars to a bar): the bass on its downbeats, "
                         "the chop on its 2 and 4, a banjo roll in its eighths",
                         _b(0.05, bass="Walk-ups", chords="Offbeat", pulse="Roll", swing=0.1, pump=0.0)),
    "Country": ("A brushed train beat, a bass walking into each chord, boom-chick guitar",
                _b(0.55, "Train", "Walk-ups", "Boom-chick", swing=0.05, pump=0.0)),
    "Lo-fi": ("Downtempo drums, swung, laid back", _b(0.33, "Downtempo", swing=0.55, pump=0.2)),
    "Reggae": ("One drop, a dub bass, chords on the off-beats", _b(0.25, "One drop", "Dub", "Offbeat", swing=0.2, pump=0.1)),
    "Rock": ("Rock drums, eighth-note bass, strummed chords", _b(0.5, "Rock", "Eighths", "Strum", pump=0.1)),
    "Funk": ("Funk drums and bass, comping chords", _b(0.5, "Funk", "Funk", "Comp", swing=0.25, pump=0.15)),
    "Jazz": ("Swing ride, a walking bass, comping", _b(0.6, "Swing", "Walking", "Comp", swing=0.65, pump=0.0)),
    "Disco": ("Four on the floor, octave bass, off-beat chords", _b(0.68, "Disco", "Octaves", "Offbeat", pump=0.3)),
    "Breaks": ("Broken beat, rolling bass", _b(0.75, "Breaks", "Rolling", swing=0.15, pump=0.35)),
    "House": ("Four on the floor, off-beat bass, chord stabs", _b(0.72, "House", "Offbeat", "Stabs", swing=0.2, pump=0.5)),
    "Techno": ("Techno drums, an acid line, a sixteenth arpeggio", _b(0.8, "Techno", "Acid line", pulse="Arp 16ths", pump=0.6)),
    "Trance": ("Four on the floor, rolling bass, pumping", _b(0.88, "House", "Rolling", pulse="Arp 16ths", pump=0.75)),
    "Trap": ("Half-time kick and snare, hat rolls, an 808 line", _b(0.9, "Trap", "Half-time", pump=0.2)),
    "Tresillo": ("Half-time drums, a 3+3+2 bass", _b(0.45, "Half-time", "Tresillo", "Stabs", pump=0.3)),
}

SOUND = {
    "Ambient pads": ("Warm pad, sub bass, bells, wind", _s(("Warm", 0.7), ("Sub", 0.5), ("Bell", 0.5), ("Wind", 0.3))),
    "Glass": ("FM glass, kalimba, a stream, a big echo",
              _s(("Glass", 0.6), ("Sub", 0.4), ("Kalimba", 0.6), ("Stream", 0.25), ("Glint", 0.4),
                 space=0.8, echo=0.5, bright=0.7, motion=0.5, drive=0.05)),
    "Dawn": ("Glass pad, bells, wind, bright and wide",
             _s(("Glass", 0.7), ("Sub", 0.4), ("Bell", 0.5), ("Wind", 0.25), space=0.7, echo=0.3, bright=0.6)),
    "Choir": ("Voices, a fifths drone, a flute, wind",
              _s(("Choir", 0.7), ("Fifths", 0.5), ("Flute", 0.4), ("Wind", 0.3), ("Thump", 0.35),
                 space=0.7, echo=0.25, motion=0.4)),
    "Deep": ("A dark warm pad, a fifths drone, waves; no melody",
             _s(("Warm", 0.8), ("Fifths", 0.6), (OFF, 0.5), ("Waves", 0.35), space=0.8, echo=0.1, bright=0.2, motion=0.2)),
    "Rainy room": ("Organ, soft bass, felt piano, rain",
                   _s(("Organ", 0.5), ("Soft", 0.4), ("Felt", 0.6), ("Rain", 0.45), space=0.5, echo=0.15, bright=0.35)),
    "Night": ("Warm pad, plucks, vinyl, long echoes",
              _s(("Warm", 0.6), ("Soft", 0.5), ("Pluck", 0.3), ("Vinyl", 0.4), ("Pluck", 0.5),
                 space=0.5, echo=0.6, bright=0.45, motion=0.4)),
    "Temple": ("Air, a fifths drone, bells, a thump",
               _s(("Air", 0.6), ("Fifths", 0.5), ("Bell", 0.6), (OFF, 0.3), ("Thump", 0.35), space=0.8, echo=0.3, motion=0.25)),
    "Lo-fi": ("Electric piano, soft bass, felt, vinyl, an acoustic kit",
              _s(("Keys", 0.5), ("Soft", 0.45), ("Felt", 0.55), ("Vinyl", 0.4), drums=("Acoustic", 0.55),
                 space=0.45, echo=0.2, bright=0.35, drive=0.25)),
    "Synths": ("Supersaws, a synth bass, a saw lead, bright",
               _s(("Supersaw", 0.6), ("Synth", 0.55), ("Saw stack", 0.6), pulse=("Synth pluck", 0.35),
                  drums=("Electronic", 0.65), space=0.55, echo=0.4, bright=0.65, motion=0.45, drive=0.3)),
    "Acid": ("Synth stabs, a 303, synth plucks",
             _s(("Synth stab", 0.45), ("Acid", 0.6), ("Synth pluck", 0.4), pulse=("Pluck", 0.3),
                drums=("Electronic", 0.75), space=0.35, echo=0.45, bright=0.5, motion=0.5, drive=0.5)),
    "Deep house": ("Synth stabs, a Moog bass, a lead",
                   _s(("Synth stab", 0.6), ("Moog", 0.6), ("Lead", 0.5), drums=("Electronic", 0.7),
                      space=0.4, echo=0.35, bright=0.4, drive=0.25)),
    "Reese": ("A Reese bass under a dark pad: drum and bass",
              _s(("Warm", 0.45), ("Reese", 0.65), ("Sync lead", 0.45), drums=("Electronic", 0.7),
                 space=0.45, echo=0.3, bright=0.45, motion=0.5, drive=0.35)),
    "String ensemble": ("A string section, an upright bass, a violin line, pizzicato",
                        _s(("Strings", 0.7), ("Upright", 0.55), ("Strings", 0.65), pulse=("Pluck", 0.3),
                           drums=("Acoustic", 0.45), space=0.65, echo=0.1, bright=0.45, motion=0.35, drive=0.0)),
    "Rock band": ("Strummed overdriven guitar, electric bass, organ lead, a kit",
                  _s(("Guitar", 0.65), ("Electric", 0.6), ("Organ lead", 0.55), drums=("Acoustic", 0.75),
                     space=0.35, echo=0.15, bright=0.55, motion=0.2, drive=0.45)),
    "Jazz trio": ("Piano, upright bass, vibes, brushes on a kit",
                  _s(("Piano", 0.55), ("Upright", 0.65), ("Vibes", 0.6), drums=("Acoustic", 0.5),
                     space=0.4, echo=0.05, bright=0.45, drive=0.05)),
    "Funk band": ("Electric piano, electric bass, brass, a kit",
                  _s(("Keys", 0.55), ("Electric", 0.65), ("Brass", 0.6), drums=("Acoustic", 0.7),
                     space=0.35, echo=0.1, bright=0.55, motion=0.2, drive=0.3)),
    "Dub": ("Organ, a deep sub, a melodica-like organ lead, lots of echo",
            _s(("Organ", 0.5), ("Sub", 0.65), ("Organ lead", 0.5), drums=("Acoustic", 0.6),
               space=0.5, echo=0.65, bright=0.35, drive=0.2)),
    # The band sounds' rhythm guitar sits 6 dB under the lead (gated rms, each part alone in its moods:
    # Bluegrass, Red Wing; 2026-10-15). Country band's, level with the dobro (0.35), was too loud by ear.
    "String band": ("Acoustic guitar, upright bass, a fiddle out front, a banjo; a small dry room",
                    _s(("Acoustic guitar", 0.22), ("Upright", 0.4), ("Fiddle", 1.0), (OFF, 0.3), ("Banjo", 0.8),
                       drums=("Acoustic", 0.5), space=0.3, echo=0.0, bright=0.55, motion=0.15, drive=0.0)),
    "Folk": ("Fingerpicked acoustic guitar, a soft upright bass, harmonica",
             _s(("Acoustic guitar", 0.35), ("Upright", 0.35), ("Harmonica", 1.0), drums=("Acoustic", 0.5),
                space=0.4, echo=0.05, bright=0.5, drive=0.0)),
    "Country band": ("Acoustic guitar, upright bass, a dobro lead, a banjo's rolls, brushes on a kit",
                     _s(("Acoustic guitar", 0.18), ("Upright", 0.4), ("Dobro", 1.0), pulse=("Banjo", 0.4),
                        drums=("Acoustic", 0.3), space=0.35, echo=0.1, bright=0.5, motion=0.15, drive=0.0)),
    "Chip": ("8-bit: square waves, a synth bass",
             _s(("Synth stab", 0.3), ("Synth", 0.5), ("Chip", 0.7), pulse=("Chip", 0.3), drums=("Electronic", 0.6),
                space=0.25, echo=0.15, bright=0.7, motion=0.2, drive=0.2)),
    "Trap": ("An 808, dark keys, a bell lead",
             _s(("Keys", 0.45), ("808", 0.7), ("Bell", 0.5), drums=("Electronic", 0.7),
                space=0.4, echo=0.25, bright=0.4, drive=0.35)),
}

# The presets: each a whole sound, in a key, built from a part preset for each
# part (and anything set apart from them). The page applies all of one, or
# only the parts its toggles choose: just the beat of Bluegrass, say. Every
# part preset above is used by at least one, so every one can be reached.
# name: (what it is, key, harmony, melody, beat, sound, set apart)
WHOLE = {
    "Dawn": ("Lydian chords drifting under bells, wind, a wide room", "E", "Lydian glow", "Scattered", "Still", "Dawn", {}),
    "Deep": ("A dark, slow pad over a drone, and waves", "C", "Deep", "Sparse", "Still", "Deep", {"shape": {"tempo": 0.16}}),
    "Rain": ("Dorian organ, felt piano notes, rain", "A", "Modal", "Scattered", "Still", "Rainy room", {}),
    "Glass": ("Whole-tone glass and kalimba, glints, a long echo", "F#", "Whole tone", "Scattered", "Glints", "Glass", {}),
    "Drift": ("Voices over a fifths drone, a flute now and then", "D", "Drift", "Sparse", "Still", "Choir", {}),
    "Soft pulse": ("Warm pads and bells over a soft kick and hats", "D", "Drift", "Scattered", "Ambient pulse", "Ambient pads", {}),
    "Night drive": ("Phrygian chords, a running arpeggio, vinyl, long echoes", "F", "Phrygian", "Sparse", "Arp drift", "Night", {}),
    "Temple": ("A Japanese scale, very slow, bells and a heartbeat", "G", "Hirajoshi", "Sparse", "Heartbeat", "Temple", {}),
    "Lo-fi": ("Swung downtempo, ii–v–i on electric piano, vinyl", "A", "ii–v–i", "Scattered", "Lo-fi", "Lo-fi", {}),
    "Breaks": ("Broken beats, a rolling Reese bass, an Aeolian riff", "E", "Aeolian rock", "Riff", "Breaks", "Reese", {}),
    "Deep house": ("Four on the floor, Dorian chord stabs, a Moog bass", "F", "Dorian vamp", "Sparse", "House", "Deep house", {}),
    "Techno": ("Techno drums, an acid line, two Phrygian chords", "A", "Phrygian drone", "Sparse", "Techno", "Acid", {}),
    "Trance": ("Epic minor chords on supersaws, rolling bass, pumping", "C", "Epic minor", "Scattered", "Trance", "Synths", {}),
    "Epic": ("Epic minor chords, short questioning phrases, rock drums", "D", "Epic minor", "Questions", "Rock", "Synths", {}),
    "Song": ("A major ballad with a felt-piano line that asks and answers", "D", "Ballad", "Song", "Still", "Rainy room",
             {"layers": {"melody": {"voice": "Felt", "level": 0.75}, "texture": {"voice": OFF, "level": 0.3}}}),
    "Nocturne": ("Minor cycles, an electric piano line, slow", "A", "Minor ballad", "Song", "Still", "Rainy room",
                 {"shape": {"tempo": 0.18}, "layers": {"melody": {"voice": "E. piano", "level": 0.75},
                                                       "pad": {"voice": "Air", "level": 0.35},
                                                       "texture": {"voice": "Waves", "level": 0.15}}}),
    "Music box": ("Pachelbel's Canon, a simple vibes hook, glints", "F", "Canon", "Hook", "Glints", "Glass",
                  {"layers": {"melody": {"voice": "Vibes", "level": 0.75}}, "shape": {"tempo": 0.4}}),
    "Elegy": ("Long minor cycles, a string section, long phrases", "C", "Elegy", "Lyrical", "Still", "String ensemble", {}),
    "Strings": ("A string section and pizzicato, a lyrical line", "D", "Ballad", "Lyrical", "Chamber", "String ensemble", {}),
    "Anthem": ("I–V–vi–IV on supersaws, a saw lead, pumping", "G", "Pop", "Song", "Trance", "Synths", {"shape": {"tempo": 0.78}}),
    "Chiptune": ("Doo-wop chords in 8-bit, a busy square-wave line", "C", "Doo-wop", "Busy", "Breaks", "Chip", {"shape": {"tempo": 0.85}}),
    "Rock band": ("Blues-rock I–IV–V–IV, guitar, bass, kit, an organ riff", "G", "Blues-rock", "Riff", "Rock", "Rock band", {}),
    "Jazz club": ("A swing turnaround, walking bass, piano and vibes", "C", "Jazz", "Song", "Jazz", "Jazz trio", {}),
    "Funk": ("A Dorian vamp, funk drums and bass, keys and brass", "E", "Dorian vamp", "Riff", "Funk", "Funk band", {}),
    "Disco": ("Four on the floor, an octave bass, a Dorian riff", "A", "Dorian vamp", "Riff", "Disco", "Funk band", {}),
    "Reggae": ("One drop, a dub bass, organ off-beats, echo", "A", "Dorian vamp", "Sparse", "Reggae", "Dub", {}),
    "Dembow": ("A 3+3+2 bass under half-time drums, synths", "A", "Aeolian rock", "Riff", "Tresillo", "Synths", {}),
    "Trap": ("Half-time with hat rolls, an 808, dark keys", "F", "Epic minor", "Sparse", "Trap", "Trap", {}),
    "Bluegrass": ("The player's fiddle tune, improvised each time round, a string band", "C", "Fiddle tune chart",
                  "Bluegrass break", "Bluegrass", "String band", {}),
    "Folk song": ("Fingerpicked guitar, a harmonica line", "D", "Ballad", "Song", "Folk", "Folk", {}),
    "Country": ("A train beat on brushes, boom-chick guitar, a dobro", "G", "Bluegrass", "Song", "Country", "Country band", {}),
    # The dobro tunes: their charts, a dobro making up a tune over them, at their tempos
    "Red Wing": ("Red Wing's chart in two at 100, a dobro making up a tune over it, a string band", "G", "Red Wing",
                 "Fiddle tune in two", "Bluegrass in two", "Country band", {"shape": {"tempo": 0.0}}),
    "Down Yonder": ("Down Yonder's chart in two at 120, a dobro making up a tune over it, a string band", "G",
                    "Down Yonder", "Fiddle tune in two", "Bluegrass in two", "Country band", {"shape": {"tempo": 0.1}}),
    "Big Sciota": ("Big Sciota's chart at 100, a dobro making up a tune over it, a string band", "G", "Big Sciota",
                   "Fiddle tune", "Bluegrass", "Country band", {"shape": {"tempo": 0.5}}),
    "Cherokee Shuffle": ("Cherokee Shuffle's chart in two at 170, a dobro making up a tune over it, a string band", "A",
                         "Cherokee Shuffle", "Fiddle tune in two", "Bluegrass in two", "Country band",
                         {"shape": {"tempo": 0.35}}),
}
# What a preset can bring, toggle by toggle: the key, and each part's settings
ASPECTS = {"key": ("Key", ["key"]), **{part: (name, paths) for part, (name, paths) in PARTS.items()}}

BY_PART = {"harmony": HARMONY, "melody": MELODY, "beat": BEAT, "sound": SOUND}
