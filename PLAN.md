# ambient-room: plan

## Goal

A phone page that lets anyone in the room play ambient music through the
room's speakers. An existing synthesis engine makes the sound, on the
practice recorder's control unit (the Pi 3). The page hides the engine. It
offers start and stop, a few moods, and a few controls with plain names.

- Every setting should sound fine. No control can make it blast or screech.
- Changes glide over seconds. Nothing clicks or jumps.
- Several phones can control it at once, and all see the same state.

## What it shares with piano-recorder

The synth uses the hardware of `~/play/piano-recorder`. The facts about
those parts live in that project's `docs/components.md`. This project
points to them and does not copy them.

- **Control unit (its slot 5):** the Pi 3, host `practice`, at
  `practice.local`. It also runs the recorder service.
- **Playback output (slot 3):** the BMG-04F's USB playback. It enters the
  mixer on channel 3/4 when the MP3/USB button is down.
  - So the synth, like takes, needs the button on MP3/USB.
  - A record and the synth cannot play at the same time.
- **Speakers (slot 4), the one mixer setting, and the loudness
  calibration.** Takes are brought to -21 dBFS gated rms, which plays about
  level with records. The synth's top volume should land there too.
- **No mixer input is free.** So the synth must run on the computer that is
  on the mixer's USB.
- **The mixer is to be replaced** by a Focusrite Scarlett (piano-recorder's
  `docs/replacing-the-mixer.md`). The synth's output moves with it: a
  config change here.

## Design

Four parts. Each can be swapped without touching the others.

1. **Engine:** makes the sound from instruments and parameters. First
   choice: Csound (below).
2. **Output:** the playback device, taken in turns with the recorder.
   - **Only one of them plays at a time** (decided 2026-10-11). Before
     playing, each asks the other to let go (`POST /api/yield`,
     `ambient/peers.py`). The synth fades out in 1.5 s for a recording or a
     take. It refuses to start while a recording runs.
   - So no device sharing (`dmix`, PipeWire) is needed.
   - Csound computes the audio, and `aplay` plays it (`ambient/engine.py`).
     Csound's own ALSA output ignores the buffer size on the Pi: it always
     took 1024 frames (21 ms). Through `aplay` it gets 400 ms.
3. **Conductor:** a small Python service.
   - It holds the state: on or off, the mood, the controls.
   - It turns that state into engine parameters and ramps every change.
   - It runs the generative rules: which chord comes next, when a bell
     rings.
   - It serves the page and its API. FastAPI, like the recorder.
4. **Page:** the phone UI.

### Engine choice

All of these are packaged for the Pi's OS (Raspberry Pi OS Trixie, checked
2026-10-11).

| Engine | Version | For | Against |
|---|---|---|---|
| **Csound** | 6.18.1, `python3-csound` | ALSA output, no server; light; a Python API that runs in the same process; decades of instruments; `reverbsc`, a lush reverb that costs little | an older language; a smaller community than SuperCollider's |
| SuperCollider | 3.13.0, `sc3-plugins` | the most common engine for generative and ambient work; Sonic Pi's synths are SuperCollider synth definitions | on Linux its server needs JACK, which takes the playback device for itself, so the recorder's playback would have to go through JACK too |
| pyo | 1.0.6, `python3-pyo` | a Python module with a C engine: the simplest to drive from Python | one maintainer; a small community |
| Pure Data | 0.55.2 | runs well on a Pi | patches are drawn with a mouse, not written. Hard to review or keep in a repo. |
| Sonic Pi, TidalCycles, Strudel | | live coding: the "techno from the command line" kind | they are made for typing code while the music plays, not for a page of controls. Sonic Pi on Debian needs a desktop. Tidal needs Haskell, which is heavy on a Pi 3. Strudel runs in the browser, so the sound would come out of the phone. |
| FluidSynth | 2.4.4 | plays SoundFonts | later, maybe: a sampled voice for the bells, such as the dobro SoundFont |

- **Csound first:** it plays straight to ALSA, which makes sharing the
  device with the recorder simplest, and it is light enough for a Pi 3.
- **SuperCollider is the swap** if Csound's sound disappoints. Moving to it
  means JACK or PipeWire on the Pi, and re-testing the recorder.

### The sound

Layers in one key. The conductor decides what plays. The engine only plays
it.

- **Pad:** a chord that changes slowly. Voices fade in and out.
- **Bass:** a low drone on the root.
- **Texture:** filtered noise, like wind or surf.
- **Bells:** sparse notes from the scale, bell-like or plucked.
- **Space:** reverb and a soft echo over everything.

### The page

The player, 2026-10-11: "diverse, and controllable, so that someone can
play with the ui to find something they like".

- **Play** fades in over 10 s. **Stop** fades out in 0.3 s, so it stops at once
  without a click (2026-10-11; it was 10 s). The sleep timer fades out over 10 s.
- **Four parts** (since 2026-10-11, `ambient/presets.py`). The player: "i
  might want the same 'song' preset with different voices or even
  different genre." Every setting belongs to one part, and each part is a
  tab:
  - **Harmony:** the scale, the progression, harmonic rhythm, chord size,
    triads only, borrowing.
  - **Melody:** the line's style and shape, how busy, its register.
  - **Beat:** tempo, swing, pump, and what each part in time plays: a drum
    pattern (12), a bass line (13), a chord rhythm (6), a rhythm part (4).
  - **Sound:** who plays each part (the voices) and how loud, the
    atmosphere, the room.
  - The key, the tuning and the volume belong to none.
  - Any voice plays any pattern of its part: an upright bass can walk or
    play a house offbeat. Bass voices (10): Sub, Soft, Fifths, Synth, Acid,
    Electric, Upright, 808, Reese, Moog. Drum kits: Electronic, Acoustic.
  - Acoustic strings and reeds (2026-10-11), for bluegrass, folk and
    acoustic country: Fiddle (a bowed-string waveguide), Mandolin (paired
    picked strings; tremolo on long notes), Banjo, Acoustic guitar, Dobro
    (slides into each note), Harmonica. Their rhythms: Chop (chords on 2
    and 4), Boom-chick and Travis (a guitar's own bass and chords), banjo
    Rolls (forward, alternating), Walk-ups (a bass walking into each
    chord), Train (a brushed country beat).
  - Sampled voices (2026-10-11, `ambient/samples.py`, `sounds/`): the
    fiddle, banjo, acoustic and nylon guitars, upright bass and harmonica
    play recordings from FluidR3_GM (MIT), and the dobro the player's own
    resonator recordings. A voice whose font is missing plays its
    synthesized model. On the Pi they cost far less than synthesis (5% of
    a core for a busy band).
    - The Pi's Csound (Debian 6.18.1, aarch64) has two SoundFont bugs: NaN
      from the stereo players, and tuning read as unsigned chars (notes
      sharp, or a frozen synthesis). The voices play through the mono
      `sfplay3m`, and `tools/soundfonts` normalises the fonts. Details in
      `sounds/README.md`. Reported upstream: csound/csound#3403, fix in
      PR #3404. The sampled voices have been on the Pi since 2026-10-11.
  - Melody voices are evened out twice: scattered notes at -37 dBFS, and
    phrases and motifs at -30 dBFS (3 dB under the chords: a shaped line
    is there to be followed). Before, phrased voices spread over 13 dB.
- **Presets** (unified 2026-10-11): one list of whole sounds, each in a key,
  calm to energetic. Five toggles say what a preset brings: Key, Harmony,
  Melody, Beat, Sound. All on: the whole preset (volume, the tuning switch
  and anything locked stay). Some: only those parts change. Surprise me
  follows the same toggles. Yours: save the whole sound by name; the
  toggles choose what to take from it. The player: "if all aspects are
  applied, nothing from current settings are retained ... but you can just
  apply one or several subsets while keeping the rest of the settings
  unchanged."
- **Locks:** each setting, or a whole part with one tap at the top of its
  tab.
- **Changes, yours and evolution's,** go in the same strip and history,
  with the same glow; Undo takes back the last of either.
- **Progression** (added 2026-10-11, `ambient/harmony.py`): how the chords
  move. The player: "it should be able to have more form as well, like a
  definite harmonic rhythm that resolves to the tonic... at the most locked
  down end, even a set chord progression that repeats."
  - **Wander:** chords chosen freely from the scale. The ambient end.
  - **Functional:** cycles of 2, 4 or 8 chords that move home → away →
    tension and end in a cadence: V–I, IV–I, a stop on V, or V–vi.
    Resolution sets how often a cycle comes home.
  - **Loop:** a set progression of 1 to 8 scale degrees. There are presets
    (1–5–6–4, 2–5–1, Canon ...), and each chord can be changed by hand.
  - Chords are named by scale degree, so a loop fits any key and scale.
    Where a scale lacks a degree, a chord with the same job stands in.
  - Chords fall on bar lines counted from the start, so loops and cycles
    line up with the melody's phrases. When the harmony has a form, it
    leads: a phrase ending over I ends on the home note.
  - **Harmonic rhythm:** 16, 8, 4, 2 or 1 bars a chord, whatever the
    tempo, so a song keeps its rhythm in any style.
  - **Chord size:** 0 to 5 notes (none, the root, root and fifth, triads,
    sevenths, ninths), or a mix of two. The harmony the melody and bass
    follow is always at least a triad. **Triads only:** every chord major
    or minor.
  - **Borrowing:** chords from outside the scale: iv, ♭VI, ♭VII in major;
    a major V in minor; secondary dominants (V/V, V/vi ...) leading into
    their chord. Functional and wandering harmony borrow as the slider
    allows; a loop can hold borrowed chords. While one sounds, the melody
    uses its notes.
- **A sleep timer:** fade out after 15, 30 or 60 min.
- **Shared:** every phone sees the same settings. Changes glide. A new
  key, scale, tuning, chord voice or rhythm fades the sounding chord in 2 s.
- **Volume tops out** at the calibrated room level.
- **No synth words** on the page: no "LFO", "cutoff" or "ADSR".
- **The home page,** http://practice.local/ (in piano-recorder), shows
  both programs and links to each.

### Real tunes as goals (2026-10-14)

Three dobro tunes the player plays (Red Wing, Down Yonder, Big Sciota, in
`~/play/dobro-transcription/tunes/dobro`) are the goals for three moods: each
tune's chart, a dobro making up a melody over it, a string band.
`tools/tune_fit.py` plays a chart through the conductor without sound and
compares the melody it plans with the tune's: notes a bar, where they fall
in the bar, how far apart, steps against skips and leaps, the span, chord
tones on beats 1 and 3. 0 is the tune's own traits.

- **The moods:** Red Wing and Down Yonder laid in two (two bars of the tune
  to a bar, at half its tempo: the generator's running sixteenths are the
  tune's eighths, the bass falls on its downbeats, the chop on its 2 and 4);
  Big Sciota bar for bar (it has many sixteenths). New: the melodies
  "Fiddle tune" and "Fiddle tune in two", the beat "Bluegrass in two",
  three charts, three moods.
- **The generator, changed for them** (`ambient/melody.py`,
  `ambient/harmony.py`, `ambient/conductor.py`):
  - rhythm cells a tune in two needs: three after a held note, short-long-
    short (a fifth of the tunes' beats in two), two more syncopations, the
    dotted pairs; in the running regime only;
  - a cadence's held note on beat 3 or an eighth either side (in a running
    line, anywhere in the bar's second half); pickups of two sixteenths too,
    and in a running line in sixteenths; now and then by half steps;
  - a phrase ending away from home on any chord tone but the home note (it
    was: any but the chord's root; Down Yonder ends on C over C);
  - a chord from outside the scale replaces only the note it alters (over A7
    in G, C♯ for C; D stays: before, both neighbours of C♯ went);
  - under a second chord in the bar, the bar's notes respelt as its scale
    has them (G then G7: F for F♯);
  - now and then a bar starts on a neighbour of its chord tone, resolving to
    it (3-13% of bars, with Variation), and a weak note a whole step from
    the strong note after it takes the half step between (3-13%);
  - the register widens past the middle of Range, to 26 semitones (19
    before; the tunes span 21 to 24).

  On the other moods (10 seeds of 32 bars each): notes a bar within half a
  note of before in most, up to 1.4 more in the riffs (Disco; one riff
  stands for many bars, so the seeds spread wide); chord tones on beats 1
  and 3 up to 0.07 fewer.
- **Closest, over 8 seeds, in their moods:** Red Wing 4.1, Down Yonder 4.2,
  Big Sciota 3.8. Before the generator changes, with the first presets:
  5.0, 3.3, 4.0; Bluegrass break, the Bluegrass mood's melody: 13.3, 13.2
  and 7.9 bar for bar.
- **Could it play the tune itself?** Not whole. Bars within the rules, in
  the moods: Red Wing 14 of 16 (in two; none before the changes), Down
  Yonder 6 of 10 (in two; none before), Big Sciota 12 of 16 (10 before).
  Bar for bar Red Wing 28 of 32 and Down Yonder 16 of 20. What stops the
  rest: Down Yonder's chromatic runs across a bar line (G, F♯, F into the
  next bar's E; D, E♭ into E: the generator plans a bar at a time and does
  not know the next bar's first note), a note or two beyond the register,
  and two of Red Wing's cadences.
- **By chance:** in 200 times round each chart, no bar came out as the
  tune plays it (0 of 2,000 to 3,200).

### Acoustic voices from the player's own instruments (2026-10-15)

The player: the Dobro voice "sounds very little like a dobro", and the bass
"isn't very much like an acoustic bass". First steps (`sounds/README.md`):

- **The dobro's samples speak on time:** each starts at its pick, found
  from the 3-8 kHz click (in the dobro-soundfont build); they spoke 19-54 ms
  late.
- **The dobro plays by string,** as the MuseScore dobro spike found matters
  most (`../dobro-transcription/docs/musescore-dobro-rendering-spike.md`):
  each note on a string of open G, chosen near where the bar is; it rings
  until the string is picked again, where before every note rang 1.4 s
  whatever its string; a nearby note on the same string now and then slides
  there without a new pick (0.08 s a semitone, arriving on the beat), and a
  longer note is now and then picked a fret or two below and slid up.
  Vibrato is not modelled (the player's held notes vary 1-2 cents). Its
  choices have their own dice: the notes stay what the conductor planned.
- **The Upright voice is the player's own bass** (`tools/upright_font.py`),
  from the bass exercise takes, in place of FluidR3's.

Then (2026-10-15, the player: the boom-chick guitar, the arpeggio, and a
melody that does not "resolve and breathe at the key points of form"):

- **A guitar plays guitar chords** (`music.guitar_shape`): open-position
  shapes from standard tuning (G 320033, C x32010, D7 xx0212, A7 x02020),
  where the patterns used the pad's voicing. Boom-chick: the root on its
  string, the alternate bass a fifth below on the string under it (C-G,
  D-A) or above (G-D), and the chick the strings above them strummed down
  (7 ms a string) and damped short (0.16 s); the chop and stabs the same.
  2 dB more in gain, to the old level.
- **The rolls are a banjo's:** the Country band's rhythm part is the
  sampled banjo, not the synthesized pluck, and a roll's notes are the
  chord's from G3 to A4 with the thumb's drone on the home note near G4
  (they were the pad's chord an octave up).
- **The end of a part resolves** (`Melodist.strong_cadence`): a phrase's
  last bar where the harmony goes from V to I (the end of the A part and of
  the B part in the tune charts) arrives on the home note as I comes, from a
  step away (2-1 or 7-1), and holds it; pickups there a quarter as often.
  In the three tune moods, at those bars: on the home note as I comes
  29-48% before, 99-100% after; held with nothing after it 0-8% before,
  72-80% after; from a step away 6-16% before, 99-100% after.

Next, if they help: a sampling session for the bass (every semitone E1 to
D3, let ring 3-4 s, through the 18i8), as the dobro's planned 1.0 session;
rolls between the dobro's melody notes (its open strings ringing under the
tune).

## Steps

0. **Plan.** This file. Done 2026-10-11.
1. **Engine check.** Done 2026-10-11, on the Pi (the player chose to skip
   the desktop).
   - A test pad played through the BMG-04F. The player: "working".
   - Cost: the Moog-style filter (`moogladder`) alone took more than one
     core. With a simpler filter, the test sound took 29% of one core.
   - With the hand-over (above), the T9 soak with the synth is not needed:
     the two never run together.
2. **Sound.** First version 2026-10-11: five layers, 21 voices, seven
   moods.
   - Loudness: each voice measured alone on the Pi (`tools/calibrate`) and
     trimmed to match the others in its layer (`ambient/sounds.py`). The
     moods then render within 3.5 dB of each other, at 19-30% of one
     core. A +6 dB output trim puts volume 1 near -21 dBFS, the level
     takes play at.
   - Next: the player and others listen and say what to change.
3. **Conductor and page.** First version 2026-10-11, at
   http://practice.local:8001/ (systemd service `ambient-room`).
   - The state, the ramps and the generative rules.
   - The phone page.
   - A systemd service on the Pi.
4. **Room use.** Other people try it. Then, if wanted:
   - more voices and moods;
   - favourites: save a setting someone found;
   - a hardware knob box (MIDI).

## Open questions

- Answered 2026-10-11: the synth never plays during a recording or a take
  (the hand-over). Playing along with the synth while recording could
  return with the Scarlett, which would keep the synth out of the take.
- Who is "anyone"? Assumed: whoever is on the home Wi-Fi. No login, like
  the recorder.
- Pi 3 headroom: answered for now. The synth uses 19-30% of one core and
  never runs with the recorder. More voices per mood would cost more.

## Sources

- [Benchmarking audio performance (SuperCollider on a Pi), Blokas forum](https://community.blokas.io/t/benchmarking-audio-performance/611)
- [SuperCollider on Small Computers, Goldsmiths](https://research.gold.ac.uk/id/eprint/38207)
- [Best Linux audio setup for real-time Csound, Csound forum](https://forum.csound.com/t/csnd-best-linux-audio-setup-for-real-time-csound/1352):
  Csound headless on a Pi, controlled from Python.
- [Csound on a Pi with ALSA, clap-detection project](https://github.com/iver56/clap-detection):
  larger buffers fixed crackling.
- [Supriya, a Python API for SuperCollider](https://github.com/supriya-project/supriya)
