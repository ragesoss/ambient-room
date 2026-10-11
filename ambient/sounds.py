"""The parts, the voices that can play them, and the patterns they play.

A part (chords, bass, melody, rhythm, drums, atmosphere) has a voice (who
plays it: its sound, in the Sound tab) and, for the parts in time, a
pattern (what rhythm it plays, in the Beat tab). Any voice can play any of
its part's patterns: an upright bass can walk or play a house offbeat.

Each voice: (Csound instrument, loudness trim in dB, how it is made). Trims
bring a part's voices to about the same loudness at the same level: pad -27,
bass -24, melody -37, texture -36 and pulse -34 dBFS gated rms alone at
level 1 and volume 1 (tools/calibrate). Pattern gains (dB) make up for how
much of the time a pattern sounds, measured with one voice.

Measured on the Pi, 2026-10-11 (the first pads, basses, melodies, textures,
pulses); on the desktop, 2026-10-11 (the beat voices, the melody voices from
E. piano on, and everything added with the voice/pattern split: 16 s each at
110 BPM; bass voices with Eighths, against Sub's level there; bass lines
with Synth, 0.5 dB under Held; chord rhythms with Warm and Keys, about 1 dB
under Held; struck chord voices with Held, which strikes once a bar; pulse
voices with Arp, against Pluck; the acoustic kit with Rock, against the
electronic one). Rms is a rough guide for sparse parts: Glints and Swing
are set by ear-free reckoning, louder than rms alone would make them.
"""

LABELS = {
    "pad": ("Chords", "the chord's notes: held as a pad, or played in a rhythm"),
    "bass": ("Bass", "the low part: the chord's root and the notes around it"),
    "melody": ("Melody", "the line: single notes from the scale, some from the chord"),
    "texture": ("Atmosphere", "a continuous noise texture, not tuned to the key"),
    "pulse": ("Rhythm part", "a pitched part in time: an arpeggio, glints, a heartbeat"),
    "drums": ("Drums", "a drum kit on the beat grid: kick, snare, clap, hats, rim"),
}

# Chord voices: "held" voices take an attack, a release and a chord number
# (to fade when the chord is replaced); "struck" ones sound and die away.
HELD, STRUCK = "held", "struck"

LAYERS: dict[str, dict[str, tuple]] = {
    "pad": {
        "Warm": (11, +0.7, "Subtractive: three detuned oscillators (two sawtooth, one triangle) through a low-pass filter.", HELD),
        "Glass": (12, -2.0, "FM synthesis: sine waves modulated at 2× and 3× their pitch. Brightness raises the FM index.", HELD),
        "Choir": (13, +7.5, "Two sawtooth waves through three vowel formant filters, moving between “ah” and “oo”, with a delayed vibrato.", HELD),
        "Organ": (14, -2.3, "Additive: organ-drawbar harmonics (1st to 8th), soft to bright, with a tremolo from Motion.", HELD),
        "Air": (15, +6.1, "Noise through narrow band-pass filters at the pitch and its octave, over a soft triangle wave.", HELD),
        "Supersaw": (17, +0.0, "Five detuned sawtooth waves per note: the big trance chord.", HELD),
        "Strings": (18, +2.4, "A string section: four detuned saws per note, a slow swell, vibrato, a bowed body resonance.", HELD),
        "Synth stab": (16, +10.5, "A short, bright hit: two detuned saws and a square, the filter closing fast.", STRUCK),
        "Keys": (70, +10.0, "FM electric piano: a bell-like attack that mellows as it decays.", STRUCK),
        "Piano": (35, +6.8, "Felt piano: harmonics 1-3 decaying at different rates, a soft hammer.", STRUCK),
        "Guitar": (82, +12.5, "Plucked strings through a body resonance, overdriven: strummed, the notes a little apart.", STRUCK),
        "Brass": (74, +2.9, "A brass section: saws through a filter that swells open.", STRUCK),
        "Acoustic guitar": (86, +12.6, "A clean acoustic guitar: plucked strings through the body's resonances, strummed or picked.", STRUCK),
        "Nylon guitar": (86, +12.6, "A classical guitar (without its recording: the acoustic guitar model).", STRUCK),
        "Mandolin": (84, +15.6, "A mandolin: paired strings, bright and short; good for the chop on 2 and 4.", STRUCK),
        "Banjo": (85, +16.1, "A banjo: bright plucks that die fast, with the drum head's twang.", STRUCK),
    },
    "bass": {
        "Sub": (21, -2.6, "A sine wave on the note, plus its octave: felt more than heard.", HELD),
        "Soft": (22, +0.4, "A sawtooth through a low-pass filter at 2-6× its pitch.", HELD),
        "Fifths": (23, +1.3, "Sine waves on the note and the 5th above, plus a detuned copy that beats slowly.", HELD),
        "Synth": (24, -2.4, "A sine and a filtered saw; the filter opens on accents.", HELD),
        "Acid": (25, +9.1, "A saw through a resonant, distorting low-pass swept on each note: a 303.", HELD),
        "Electric": (26, -4.6, "A fingered electric bass: saw and square through a filter that closes as the string decays.", HELD),
        "Upright": (27, -0.2, "A plucked double bass: a woody thump, a round tone, a quick decay.", HELD),
        "808": (28, +1.9, "A drum machine's bass: a sine that drops into pitch, long, saturated by Drive.", HELD),
        "Reese": (29, -6.1, "Two detuned saws beating against each other over a sine: drum and bass.", HELD),
        "Moog": (30, +9.6, "A saw and a square an octave down through a resonant ladder filter: a fat synth bass.", HELD),
    },
    "melody": {
        "Bell": (31, +1.7, "FM at an inharmonic 1 : 3.5 ratio plus a partial at 2.76×; the FM index decays like a struck bell."),
        "Pluck": (32, +15.2, "Karplus-Strong plucked string: a burst of noise in a delay loop tuned to the note."),
        "Kalimba": (33, +3.5, "A sine wave with a fast-decaying partial at 5.4× its pitch: the tine's click."),
        "Flute": (34, -5.4, "A sine wave and its octave with breath noise; vibrato starts after 0.4 s."),
        "Felt": (35, +1.5, "Harmonics 1-3 decaying at different rates, a soft hammer noise, through a low-pass filter."),
        "Lead": (36, +1.0, "A detuned saw and square with a delayed vibrato, in rhythm on the grid."),
        "Synth pluck": (37, +11.0, "A sawtooth with a fast-closing filter: short, percussive notes on the grid."),
        "E. piano": (70, +4.7, "FM electric piano: a bell-like attack that mellows as it decays, a little tremolo."),
        "Vibes": (71, +1.9, "Vibraphone: a struck bar (its 1st and 4th partials) with the motor's tremolo."),
        "Strings": (72, -1.1, "A bowed line: two detuned saws, a swell into each note, a delayed vibrato."),
        "Chip": (73, -0.5, "A square wave with a quick vibrato: 8-bit game music."),
        "Brass": (74, +3.8, "Saws with a filter that swells open: a synth horn."),
        "Sync lead": (75, +1.2, "A saw hard-synced to the note, its timbre sweeping down: an aggressive lead."),
        "Saw stack": (76, +0.1, "Three detuned saws, bright and wide: a trance lead."),
        "Marimba": (77, +5.6, "A wooden bar: partials at 1, 3.9 and 9.2 times the pitch, the upper ones dying fast."),
        "Steel drum": (78, +3.7, "A hammered pan: partials 1, 2 and 3 fading at different rates, with a shimmer."),
        "Harp": (79, +8.0, "A bright plucked string with a long ring."),
        "Voice": (80, -4.6, "A sung 'oo' opening to 'ah', through vowel formants, with vibrato."),
        "Organ lead": (81, -2.3, "Organ drawbars with a percussive click and a fast tremolo."),
        "Guitar": (82, +16.1, "A plucked string through a body resonance, a little overdriven."),
        "Fiddle": (83, +2.4, "A bowed string (a waveguide model) through a fiddle's body resonances; vibrato comes in on long notes."),
        "Mandolin": (84, +17.8, "Paired strings, picked; a long note played tremolo, the pick going back and forth."),
        "Banjo": (85, +16.5, "A bright pluck, quickly gone, with the drum head's twang."),
        "Acoustic guitar": (86, +16.5, "A clean flat-picked guitar string through the body's resonances."),
        "Nylon guitar": (86, +16.5, "A classical guitar (without its recording: the acoustic guitar model)."),
        "Dobro": (87, +12.9, "A slide guitar: each note slides up into its pitch, through a metal resonator."),
        "Harmonica": (88, -6.2, "Free reeds: a scoop into each note, breath, a hand vibrato on long notes."),
    },
    "texture": {
        "Wind": (41, +3.0, "Noise through a band-pass filter whose centre drifts, about 350 Hz to 2.4 kHz."),
        "Rain": (42, +1.0, "Random clicks, 500-1000 a second, through a high band-pass filter, over low noise."),
        "Waves": (43, -10.2, "Noise through a low-pass filter that opens and closes about every 10 s, like surf."),
        "Vinyl": (44, +0.0, "Sparse crackle (6-16 clicks a second) and a little hiss."),
        "Stream": (45, -13.9, "Noise through narrow band-pass filters whose centres jump 20-45 times a second."),
    },
    # the rhythm part's voices: struck sounds, short notes
    "pulse": {
        "Pluck": (52, +10.6, "A short plucked string (Karplus-Strong)."),
        "Glint": (53, +5.0, "A tiny sine blip."),
        "Thump": (51, +3.6, "A soft low thump: a sine falling to its pitch."),
        "Synth pluck": (37, +8.9, "A sawtooth with a fast-closing filter."),
        "Marimba": (77, +6.1, "A wooden bar."),
        "Kalimba": (33, +5.7, "A thumb piano's tine."),
        "Vibes": (71, +6.5, "A vibraphone bar."),
        "Chip": (73, -5.6, "An 8-bit square wave."),
        "Banjo": (85, +13.4, "A banjo: bright, quick plucks."),
        "Mandolin": (84, +24.8, "A mandolin: paired strings, picked."),
        "Acoustic guitar": (86, +10.6, "A clean picked guitar string."),
    },
    # drum kits: the instrument for each part is in ambient/conductor.py KITS
    "drums": {
        "Electronic": (0, +0.0, "A drum machine: a sine kick dropping in pitch, noise snare and claps, metallic hats."),
        "Acoustic": (0, +1.0, "A drum kit in a room: a deeper kick with a beater, a snare with wires, cymbal-like hats, a cross-stick."),
    },
}

# What the parts in time play: pattern -> (gain dB, what it is). The
# conductor has the notes (ambient/conductor.py).
PATTERNS: dict[str, dict[str, tuple[float, str]]] = {
    "drums": {
        "Pulse": (-1.8, "A soft kick on 1 and 3, a few hats and rim knocks: a heartbeat for ambient."),
        "Downtempo": (-1.3, "Kick, snare on 2 and 4, eighth-note hats, a rim: laid back, good with swing."),
        "Breaks": (-1.7, "A broken-beat kick, snare on 2 and 4, busy hats."),
        "Half-time": (-0.1, "Kick on 1, snare on 3: half the felt speed of the tempo."),
        "House": (-2.7, "Four on the floor, claps on 2 and 4, open hats between the beats."),
        "Techno": (-2.7, "Four on the floor, sixteenth hats, open hats between the beats, rim syncopations."),
        "Rock": (-2.0, "Kick on 1 and 3 (and the and of 3), snare on 2 and 4, eighth-note hats."),
        "Funk": (-2.0, "A syncopated kick, ghost notes on the snare, sixteenth hats."),
        "One drop": (-0.5, "Reggae: kick and cross-stick together on beat 3 only, hats between the beats."),
        "Disco": (-2.5, "Four on the floor, snare on 2 and 4, open hats on every off-beat."),
        "Trap": (-1.0, "A sparse kick, a snare on 3, hats in rolls of sixteenths."),
        "Swing": (5.5, "Jazz: a ride pattern (ding, ding-a ding), a feathered kick, ghost snare. Best with Swing up."),
        "Train": (0.0, "Country's train beat: brushed snare sixteenths, accented on the off-beats, a kick on 1 and 3."),
    },
    "bass": {
        "Held": (0.0, "The chord's root, held as long as the chord."),
        "Root–fifth": (0.4, "The root on beat 1, the fifth below on beat 3: country, folk, a two-beat feel."),
        "Half-time": (0.6, "A long root, then a short one: the 808 line of trap and hip-hop."),
        "Eighths": (-1.8, "Steady eighth notes on the root: rock, punk, a driving pulse."),
        "Octaves": (-1.9, "Eighth notes jumping between the root and its octave: disco."),
        "Offbeat": (1.6, "Short notes between the beats: house and trance."),
        "Rolling": (-1.9, "Sixteenth notes skipping each beat: a galloping trance line."),
        "Tresillo": (-1.1, "Three plus three plus two: the syncopation under reggaeton, dembow, much pop."),
        "Funk": (-0.1, "Sixteenth-note syncopation: the root, octave pops, ghost notes, the seventh."),
        "Dub": (-0.4, "Reggae: rests on the one, then a slow melodic line around the chord."),
        "Walking": (-0.5, "Jazz: a note on every beat, stepping through the chord and leading into the next one."),
        "Arpeggio": (-1.9, "The chord's notes, one per eighth note, up then down."),
        "Acid line": (0.0, "A busy sixteenth-note line with octave jumps and accents, new each chord: acid house."),
        "Walk-ups": (0.0, "Root on 1, fifth on 3; into each new chord, a walk up or down the scale: bluegrass and country."),
    },
    "chords": {
        "Held": (0.0, "The chord held for as long as it lasts (struck voices: once a bar)."),
        "Stabs": (-0.5, "Short hits on a syncopated rhythm, new each chord."),
        "Offbeat": (0.9, "Short hits between the beats: house organ, ska and reggae."),
        "Eighths": (-1.5, "Every eighth note, accented on the beat: pumping trance, rock."),
        "Strum": (-0.4, "Strummed down and up, the notes a few milliseconds apart: down, down-up, up-down-up."),
        "Comp": (5.5, "Jazz comping: a few short chords in the gaps, a new pattern each bar."),
        "Chop": (4.0, "Short, damped chords on beats 2 and 4: the mandolin chop of bluegrass."),
        "Boom-chick": (1.8, "A low root (and on beat 3 the fifth), then a strum on 2 and 4: country and bluegrass guitar."),
        "Travis": (1.7, "Fingerpicking: the thumb alternates root and fifth on the beats, fingers pick the chord between."),
    },
    "pulse": {
        "Arp": (0.0, "An arpeggio: the chord's notes an octave up, one per eighth note, up then down."),
        "Arp 16ths": (-0.9, "The arpeggio in sixteenth notes."),
        "Glints": (7.0, "Notes on random sixteenths, two to three octaves above the chords."),
        "Heartbeat": (0.0, "Two soft notes a beat, low, like a heartbeat."),
        "Roll": (-3.0, "A banjo forward roll: sixteenths through the chord in threes (3 + 3 + 2), the thumb on a high drone."),
        "Alternating roll": (-3.1, "A banjo roll with the thumb on every other note, a drone on top."),
    },
}

OFF = "Off"

# The melody voices and bass lines in groups, for the page.
MELODY_GROUPS = {
    "Soft": ["Bell", "Kalimba", "Felt", "Flute", "Vibes", "Marimba", "Harp", "E. piano"],
    "Expressive": ["Strings", "Voice", "Organ lead", "Guitar", "Steel drum", "Pluck"],
    "Synth": ["Lead", "Synth pluck", "Chip", "Brass", "Sync lead", "Saw stack"],
    "Acoustic": ["Fiddle", "Mandolin", "Banjo", "Acoustic guitar", "Nylon guitar", "Dobro", "Harmonica"],
}
BASS_GROUPS = {
    "Held": ["Held", "Root–fifth", "Walk-ups", "Half-time"],
    "Driving": ["Eighths", "Octaves", "Offbeat", "Rolling"],
    "Syncopated": ["Tresillo", "Funk", "Dub"],
    "Melodic": ["Walking", "Arpeggio", "Acid line"],
}
# Which parts' patterns can be Off (no drums, no rhythm part); the others
# go quiet by their voice
PATTERN_OFF = {"drums", "pulse"}
# The level channel a struck instrument reads (p6), when it plays another part
LEVEL = {"melody": 0, "pulse": 1, "pad": 2}


def instr(layer: str, voice: str) -> int:
    """The voice's Csound instrument: its recording (ambient/samples.py) if
    it has one and the font loaded, else its synthesized model."""
    from . import samples
    return samples.instrument(layer, voice) or LAYERS[layer][voice][0]


def about(layer: str, voice: str) -> str:
    from . import samples
    s = samples.sampled(layer, voice)
    return samples.SAMPLES[s].about if s else LAYERS[layer][voice][2]


def kind(layer: str, voice: str) -> str:
    v = LAYERS[layer][voice]
    return v[3] if len(v) > 3 else STRUCK


def trim(layer: str, voice: str) -> float:
    """The voice's trim as an amplitude factor (a recording has its own)."""
    from . import samples
    if samples.sampled(layer, voice):
        return 10 ** (samples.trim_db(layer, voice) / 20)
    return 10 ** (LAYERS[layer][voice][1] / 20)


# Melody voices in phrases and motifs (short notes on the grid): each brought
# to -30 dBFS gated rms alone at level 1 (notes 0.5, 110 BPM; desktop,
# 2026-10-11), 3 dB under the chords, where scattered notes sit at -37:
# a shaped line is there to be followed. Without this they spread 13 dB:
# plucked voices ring past their notes, slow swells (Strings) never open.
PHRASE = {"Bell": +1.4, "Pluck": -1.9, "Kalimba": +2.1, "Flute": +7.9, "Felt": +2.7,
          "Lead": +4.2, "Synth pluck": +2.0, "E. piano": +3.4, "Vibes": +2.1, "Strings": +11.4,
          "Chip": +0.4, "Brass": +5.3, "Sync lead": +3.8, "Saw stack": +3.6, "Marimba": +1.9,
          "Steel drum": +1.3, "Harp": +0.7, "Voice": +8.4, "Organ lead": +6.2, "Guitar": -1.8,
          "Fiddle": +7.7, "Mandolin": +3.3, "Banjo": +1.5, "Acoustic guitar": -2.7, "Dobro": -1.2,
          "Harmonica": +7.6}


def phrase_trim(voice: str) -> float:
    from . import samples
    if samples.sampled("melody", voice):
        return 10 ** (samples.PHRASE.get(voice, 0.0) / 20)
    return 10 ** (PHRASE.get(voice, 0.0) / 20)


def gain(part: str, pattern: str) -> float:
    """The pattern's gain as an amplitude factor."""
    return 10 ** (PATTERNS[part][pattern][0] / 20)
