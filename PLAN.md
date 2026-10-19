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
      `sounds/README.md`. Reported upstream: csound/csound#3403, fixed by
      PR #3404 (merged 2026-10-12; in no release yet). The sampled
      voices have been on the Pi since 2026-10-11.
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

Then the guitar and the banjo from GeneralUser GS (`sounds/README.md`):
the player heard the same parts through FluidR3 (as the app plays it, and
through FluidSynth with the font's own envelopes), MuseScore's MS Basic,
GeneralUser GS and FlameStudios' Kay 5-string banjo, and found GeneralUser
"slightly better for both", none of the guitars good: the samples are the
limit. The app plays every font through Csound's `sfplay3m` without the
font's envelopes (Debian's Csound has no FluidSynth opcodes); a sample's
fade (`decay`) stands in for them.

Next, if they help:
- **Sampling sessions of the player's own instruments,** as for the dobro
  and the bass: the bass (every semitone E1 to D3, let ring 3-4 s, through
  the 18i8; the takes so far have no D#2, F2, G#2, A#2, B2, C#3 long
  enough), and the player's guitar and banjo ("we'll get there
  eventually"). For the guitar's boom-chick, single notes let ring and
  palm-muted strums.
- **Meanwhile, other free guitars** found but not tried: MDM Acoustic Guitar
  on Pianobook (pick and finger, five dynamics, palm mutes; a free account
  to download, Pianobook's terms) and FlameStudios' two GPL acoustics
  (GigaStudio; their site needs a browser).
- **Rolls between the dobro's melody notes** (its open strings ringing under
  the tune).
- **The CPU playing live on the LIVA:** offline, the tune moods take about
  8% of one core there (2026-10-15).

### Listening to the room (2026-10-16)

The player, as dobro-transcription's band that follows was first being voiced over their takes:

> that's what I'm thinking... the ambient project can be the basis for the band... we can extend that side of it to give the band some degrees of freedom to vary their parts and evolve over time within their tracking constraints and even have ambient mode "follow" by choosing evolution that points toward harmonizing and synchronization with live input.  this would be more like just taking input when available and responding to the environment rather than following like a band that needs to not let you get lost

- **Two ways.** The band that follows (dobro-transcription, `docs/band-that-follows.md`): a chart,
  the player's beat, and it must not let them get lost. Listening, here: the music goes on by
  itself and, when someone plays, leans toward them.
- **Where it fits.** Evolution already picks each change as the best of several random candidates,
  the one nearest a target (energy, brightness), with more candidates for more pull
  (`evolve.step_detailed`). Listening adds targets from what is heard:
  - the key and chords: the scale's tones and the chord roots against the pitch classes heard;
  - the tempo and the beat's phase: the conductor's grid against the player's beats (the follower's
    `transcribe.livebeat` in dobro-transcription);
  - how busy and how loud the playing is: energy.
  With no one playing it wanders as now; the pull sets how much it listens.
- **The band's parts get the same freedom:** their patterns vary and evolve over time, inside what
  tracking needs (the chord, the beat, each part's place in the bar).
- **Open: the inputs.** The recorders hold the capture while they record; the exercise app listens
  between takes and lets go when asked (piano-recorder `docs/components.md`). A synth that listens
  while it plays needs the capture too: the same hand-over, or ALSA's `dsnoop` (several programs
  reading one capture), a decision for slot 2.
- **First, offline,** as the band was built: evolution over a recorded take, choosing by its fit to
  the take, against a free wander, as A/B renders of the same take.

### The band player (2026-10-16)

The live band (the transcription project's `transcribe.liveband`, which the player named the Ugly
Duckling String Band) decides each part's play for a beat 50 ms before the beat (`lead_s`); the chop
on the "and" is decided half a beat earlier still. The band player sounds those decisions on time:
`ambient/bandplayer.py`, `ambient/bandengine.py`, `ambient/fluid.py`, `ambient/output.py`, checked by
`tools/band_replay.py`.

- **The same notes as the offline render.** The player voices each cue with the transcription
  project's own function (`transcribe.bandvoice`, imported from the path in `[band] transcribe`): the
  notes, lengths, velocities, programs and pans of its `tools/band_render.py`.
- **FluidSynth for these voices, not Csound.** The offline render plays the fonts through FluidSynth,
  with their envelopes, filters and velocity layers, and GeneralUser's guitar and banjo use them (a
  filter cutoff per velocity layer on the banjo, filter envelopes on both). Csound's `sfplay3m` plays
  the samples without any of that, and Debian's Csound has no FluidSynth opcodes. So the band engine
  runs FluidSynth's library (Debian's `libfluidsynth3`, through ctypes), one synth per part as the
  offline render has it. With the parts sharing one synth, a voice another part had used started
  differently: the chop up to 0.015 apart after the chords had played.
- **Levels.** Fixed gains, so the parts sit as the offline render sets them by loudness (the chords
  3 dB under the bass, the chop 5 dB under): the chords -8.3 dB and the chop -9.5 dB against the bass,
  from the five development takes' renders, each part within 0.5 dB of its median
  (`tools/band_replay.py levels`). At `gain_db` 0 the band plays at -33 dBFS gated rms, peaks -15
  dBFS: 12 dB under the level takes play at. Its level against the player is the player's call.
- **The output** (`ambient/output.py`): `alsa` writes straight to the device through alsa-lib, asks
  for a period and buffer, reads back what it got, and follows the device's clock through its delay;
  `paced` keeps a sound card's pace and buffer with no device and keeps what it plays; `aplay` as
  before. Csound's own ALSA output is no option for a short buffer: it took 1024 frames (21 ms) for
  every `-B` from 256 to 4096 on the desktop's ALSA null device (Csound 6.18), as on the Pi. The Csound
  engine's block and output are the config's now too (`[output] block`, `output`, `period_ms`).
- **The engine has a process of its own.** Python runs one thread at a time. In a thread beside the
  listening, the engine's response (from the moment one block could go into the buffer to the moment
  the next came) reached 2.3 ms at the 99.9th percentile and 3.8 ms at worst; in its own process
  0.7 ms and 0.9-1.7 ms (block 128, a 21 ms buffer, the two takes).
- **Late cues.** A cue's notes go to the engine as one group. If the engine has already computed past
  its first note, the group sounds at once, shifted whole (a strum stays a strum), when it is no
  later than its part allows: the bass and the chords 30 ms, the chop 15 ms, under the 25-40 ms an
  ensemble tolerates. Later than that it is dropped. Both are counted by part. First settings.
- **The clock** (`StreamClock`): engine time = stream time + offset. In a replay the stream's clock
  is the wall clock: the offset is the wall time of the stream's sample 0 less that of the engine's
  frame 0 (when the output plays it). Live, the 18i8's capture and playback share one sample clock:
  the offset comes from when each started and from the round trip through the device, measured once.
  The input's own latency (the capture's block, the converter) comes out of the lead before a cue
  reaches the player.

**The replay** (`tools/band_replay.py`, on the desktop, 2026-10-16). Red Wing on the dobro (77 s) and
Down Yonder's bass part (43 s), as the band harness has them: the chart known and where it starts,
the beat live from a cold start. The take went through `LiveBand` at the wall clock's pace in blocks
of 256 samples (5.3 ms) at 48 kHz. The engine computed 128 frames (2.7 ms) at a time into a paced
output with a 10.67 ms buffer. Nothing was played aloud.

- Every cue on time: none late, none dropped (Red Wing 373 cues, 902 notes; Down Yonder 244, 603).
  No underruns.
- Every note heard within 0.67 ms of its time: FluidSynth starts a note on a 64-frame boundary.
- Against the offline render (`band_render.py --sr 48000`, whose decisions are the live ones): the
  same notes, all of them. The bass and chords sound 0.7-3.3 ms earlier live (median 2.0 ms), because
  the `fluidsynth` program plays a MIDI file that much after its times (whole milliseconds, ticks of
  1/960 s, and a 64-frame block late). The chop's "and" differs by decision: live it is placed by the
  beat's tempo when it is decided, offline halfway to the next beat, which is not known yet live.
  That moves it -37 to +18 ms on Red Wing, -25 to +17 ms on Down Yonder, median 0.
- Checked to the bit: the capture is the engine's parts mixed (to 16 bits); each part is its logged
  notes rendered again; the offline render is its notes at the frames the `fluidsynth` program uses.
  So the onsets in the engine's log are the ones heard.
- Clips for the player (the take with the band, 25 s from the first chords, both at -20 LUFS, the
  band's overall loudness against the take matched): offline against live, in the transcription
  project's `outputs/band-player-2026-10-17/` (not in git).

**The delay budget** (the bass and chords; the chop has half a beat more), the two takes:

| | median | worst |
|---|---|---|
| lead: decided this long before its time | 50 ms | 50 ms |
| to the player: the capture's block (5.3 ms) and the band's compute | 7.4 ms | 10.6 ms |
| the engine: from the first frame still open to its being heard (a block of 2.7 ms and the buffer of 10.67 ms at most) | 9.3 ms | 10.5 ms |
| left over when the cue reached the player | 33.4 ms | 29.4 ms |

On a sound card the device's own latency (USB, converters) comes on top: not measurable here.

**What the desktop sustains** (no device; i7-12700K under the powersave governor, no real-time
priority: the user's `rtprio` limit is 0):

- The engine's response at block 128, in its own process: median 0.2-0.35 ms, 99.9th percentile
  under 1 ms, worst 4.4 ms in 6 minutes of replays. The buffer must hold more than the worst: 10.67 ms
  (4 blocks) stayed fed through 9 replays (8.7 minutes). Smaller ran dry now and then: block 64 with a
  4.0 ms buffer 3 times (1.8 ms of silence in all) and with 5.3 ms once (3.4 ms), 43 s each; block 128
  with 8 ms once (1.7 ms) in 5 minutes. So the engine stalls now and then for up to about 9 ms.
- Its cost: FluidSynth 4.7 ms a second of audio running flat out, the whole engine 8.3 (block 64), 5.9
  (128) and 4.7 ms (256). At the wall clock's pace 38-66 ms a second, as the CPU slows between blocks.
- The listening (`LiveBand`) beside it: 92-158 ms a second, its worst block 6.6-7.5 ms.
- The desktop's own sound goes through PipeWire, whose graph runs in quanta of 1024 frames (21 ms) by
  default (`clock.quantum`, minimum 32). Not measured: nothing plays aloud here.
- So the band's profile: block 128, buffer 10.67 ms (`[band]`), and the engine in its own process.

**The replay's underruns on `practice` were its capture file (2026-10-17).** About one a take at a 16 ms
buffer, the engine's response up to 37-72 ms: every one (14 in 6 replays of the two takes) was the engine
writing a block of the capture WAV and waiting 33-72 ms while the kernel wrote that file's dirty pages back
(the last 30 s of it, so they came about 30 s apart: 28-35 and 59-71 s into Red Wing, 27-33 s into Down
Yonder). The listening's worst block was 13-20 ms throughout, and live there is no capture file. Now
`PacedOutput` hands the capture to a thread of its own. On `practice`, both takes: before, 1-2 underruns a
take at 16 ms (5 replays) and at 10.7 ms (2), the response max 37-72 ms; after (2 replays at each), none at
16 ms or 10.7 ms, the response at most 1.4-3.8 ms, the listening's worst block 13.0-14.5 ms, no cue late or dropped,
every note the offline render's. The transcription project's findings, "The band as the audio comes", has
the measurements.

**On the practice device (the LIVA), not touched yet.** Celeron N2807, 2 cores; about 11 times slower
than the desktop on the piano detector. Its USB audio driver runs with `lowlatency=0` (piano-recorder,
for fewer playback dropouts in T9), which may not grant a short period. Only with the player's
go-ahead, with the recorders idle:

1. Copy the branch beside the service, not over it (`tools/deploy` restarts the service):
   `rsync -aL --exclude .venv --exclude .git ./ practice:band-player/` from this tree (the fonts
   with it), and
   `rsync -a --relative ~/play/dobro-transcription/./pipeline ~/play/dobro-transcription/./tunes/dobro/red-wing ~/play/dobro-transcription/./tunes/bass/down-yonder practice:dobro-transcription/`.
2. There: `sudo apt install libfluidsynth3 fluidsynth`, then at once `systemctl --user mask --now
   fluidsynth`: Debian's fluidsynth package enables a user service that starts with the next login and
   holds the playback device (found 2026-10-17 on the LIVA, holding the 18i8's playback until masked); `cd ~/band-player && /usr/bin/python3 -m venv
   --system-site-packages .venv && .venv/bin/pip install -r requirements-band.txt`.
3. CPU and margins, no sound: `.venv/bin/python tools/band_replay.py red-wing bass-dy --config
   config/pi.toml --transcribe ~/dobro-transcription --out ~/band-replay`. It reports the listening's
   compute, the engine's CPU and response, each cue's margin, and late and dropped cues. If cues come
   late, again with `--lead 0.1`. The listening alone: `cd ~/dobro-transcription/pipeline &&
   PYTHONPATH=src ~/band-player/.venv/bin/python tools/band_stream_timing.py --block 256`.
4. The real output, aloud through the speakers (the monitor knob as the player likes):
   `.venv/bin/python tools/band_replay.py bass-dy --config config/pi.toml --transcribe
   ~/dobro-transcription --output alsa --out ~/band-alsa`, then with `--buffer-ms 21.3`. It reports
   the period and buffer the 18i8 granted, underruns, and how steady its clock looked.
5. The round trip through the 18i8 (for the clock's offset): `sudo apt install zita-alsa-pcmi-utils`,
   then `alsa_delay hw:CARD=USB hw:CARD=USB 48000 128 3 <input> <output>` with the input the loopback's
   capture channel 11 and the output PCM 1 (run it without arguments first: it prints its usage). Its
   test tones play through the speakers. The loopback leaves out the converters; a cable from an
   output to an input puts them in.

**Left for a first live run** (also in the transcription project's `docs/band-that-follows.md`):
capture on the 18i8 with the band's output on the same clock, and the offset from the round trip; the
count-in (the band plays a bar of clicks at times it schedules and gives them to `LiveBand`); the
hand-over of the 18i8 with the recorders; the LIVA's numbers above; the band's level against the
player; the player's ear on the clips, the chop's "and" above all.

### The Ugly Duckling String Band (2026-10-17)

The live band as a program of its own (the player: not part of the practice app): `ugly_duckling/`, the service
`ugly-duckling` on port 8004 of the control unit, with a phone page, listed on the home page
(http://practice.local/). It uses the band player above for its sound and the transcription project's
`transcribe.liveband` (and `voicecount`) for its listening and deciding, from the path in `[band] transcribe`.

- **The parts.** `server.py` (the page and the API), `session.py` (one run, Start to Stop), `duplex.py` (the
  device both ways), `tunes.py` (the charts), `config.py`. The engine and the player are `ambient/bandengine.py`
  and `ambient/bandplayer.py`. Config: `/etc/ugly-duckling.toml` from `config/ud-pi.toml`; the desktop's,
  `config/ud-desktop.toml`.
- **One device, one clock.** The engine's process plays a block and then reads whatever the capture has, never
  waiting for it, so the capture is read every 2.7 ms by the process that keeps the device fed. The input (the
  chosen channels, mixed to mono) and the device's return of its own playback (capture channels 10-11, PCM
  11-12) go into a ring in shared memory, which the listening reads in blocks of 256. Playback and capture take
  the same period and buffer: on `practice` both were granted 128 frames and 768 (16 ms).
- **The clock.** The two sample counts differ by a constant `L` (the capture frame that holds the return of
  playback frame m is m + L). It is estimated after every block from the two streams' delays as the driver
  reports them (median of 256), and measured exactly from the count-in's first click, found in the loopback.
  A cue for stream time t plays at engine frame `t * 48000 - L - converters` (`converter_ms`, 1.0: an estimate;
  the loopback is digital and does not see the converters). An xrun moves the estimate, and `L` with it.
- **The count-in.** "Band clicks a bar" (the default): a bar of clicks (two bars in 2/4), 0.6 s after Start is
  ready, on the engine's clock; their times in the stream go to `LiveBand` as `count_in`, and the chart starts
  on the next 1. "I count it in": `voicecount.VoiceBand` with Vosk's words (the model in `[voice] model`); the
  band starts on a spoken count, stops on "stop", and starts again on the next count. Without Vosk or its model
  the page does not offer it, nor the spoken "stop".
- **The page** picks the tune, the tempo (default: the tune's takes' tempo, those to a metronome first), the
  count-in, the input (room mic, Nadine, piezo), the instrument (the follower's preset), the parts (bass, chop,
  chords) and the band's volume. Playing, it shows the beat in the bar, the chord, the key and the chart's
  guess, each part's on/off and whether it has come in, the input's level, and the timing.
- **The tunes**: Red Wing, Down Yonder, Big Sciota (with its second endings), Cherokee Shuffle and Saint Anne's
  Reel (AABB), Tennessee Waltz (3/4), and the free guitar take's form (G C G D, 2/4), from the transcription
  project's `chords.txt` and `takes.csv` (`[[tunes]]` in the config).
- **Safety.** Nothing opens the device until Start. Before opening it the band asks the other apps to let go
  (`/api/yield`, `ambient/peers.py`) and refuses to start while one records; it answers `/api/yield` itself by
  stopping. The volume is capped at +12 dB over the band's own level (-33 dBFS gated rms at 0 dB), which puts it
  at about -21 dBFS, the level takes play at; every sample is clipped at -1 dBFS whatever the volume. A stop (the
  page, a yield, an error, "stop", or 10 minutes with nothing played): nothing new starts, what sounds rings
  0.6 s, a 0.2 s fade, the device closed (about 1 s in all). The other apps list 8004 among their peers.
- **No device** (`[device] kind = "file"`, `tools/ud-desktop`, `tools/ud_run.py`): the band paced as a sound
  card plays it, nothing heard, and a take given as the capture, its bar 1 on the beat after the count-in; the
  loopback is the band's mix 300 frames later, and the estimate is 37 frames off on purpose. The whole loop runs:
  the click found at exactly 300 frames, the band, the stop. `tests/test_ud.py`.

**Measured on `practice` (the Chromebox), 2026-10-17, no sound:**

- The self-check (`POST /api/selfcheck?input=room&seconds=10`: the device opened both ways, the engine's
  silence played, closed): passes for each input. 128-frame periods and a 16 ms buffer on both sides; no
  underrun or overrun; the loopback exactly 0 (nothing played); `L` estimated 3.0 ms (144 frames), steady to
  the frame; opened in 0.7 s. Room tone: room mic -46.5 dBFS rms, Nadine -64.9, piezo -101 (nothing on it).
- The whole loop with no device (Red Wing on the dobro, 60 s; Down Yonder's bass part, 45 s): the click found
  at exactly the simulated round trip; no note late or dropped, no underrun. The listening 102-134 ms of CPU a
  second (210 with Vosk listening for "stop"), its worst block 8-11 ms (21 with Vosk); the engine 44-61 ms a
  second. In all about 35% of one core, 356 MB. Each cue's margin when it reached the engine (its first note's
  frame less the first frame still open; the 16 ms buffer comes after): min 22-25 ms, median 33 ms. The roots
  played against the chart: 0.95 (Red Wing), 1.00 (Down Yonder).
- The band player's replay there (`tools/band_replay.py red-wing bass-dy`, the take at the wall clock's pace,
  paced output): every note the offline render's, none late or dropped, no underrun; margin at the player median
  22-24 ms, min 18.5; the engine's response max 1.7-6.1 ms against a 16 ms buffer.
- So the budget, bass and chords: the 50 ms lead; the capture's block and the listening, median 12-13 ms;
  the 16 ms buffer and `L` (3 ms) and the converters (about 1 ms) after the margin; left over at least 18 ms.
- The chords' entry is sensitive to the beat's first bars: on Red Wing one run's count-in, 0.8 ms different from
  another's, kept the beat's confidence under the chords' 0.8 for 30 beats instead of 3. Offline with the same
  times it does the same: the band's thresholds, not the service.

**Untested until the first live run** (only with the player): the click's return found on the real loopback,
and `L` measured against the estimate; the band heard at all, and its level; the converters' delay; the room
mic hearing the band from the speakers (no echo cancellation yet: the band can follow itself; the page says
to keep it low or use a pickup); Vosk on the room's real voice and the band behind it; a long session.
How to try it: open http://practice.local/ and "Ugly Duckling String Band" (or port 8004); pick the tune,
the input and the count-in, the volume low, Start; Stop, or say "stop".

**Deploy:** `tools/deploy-ud` (after checking the other apps are idle): this tree to `~/ugly-duckling` on the
unit (its own venv, so ambient-room is not restarted), the transcription project's `pipeline/src` and the tunes'
`chords.txt` and `takes.csv` to `~/dobro-transcription`, then `setup/install-ud.sh`. The Vosk model at
`~/models/vosk-model-small-en-us-0.15` there.

### The first live runs, and what changed (2026-10-17)

The player played with the band twice: the dobro on the room mic (Cherokee Shuffle at 170), then the bass on its
piezo (Down Yonder at 120: "impressive. i was able to lead the band to speed up smoothly"). From the first: the band
"cues heavily on itself from the speakers", "gradually slows, rather than quickly stopping, if i stop playing", and
comes in late after the count-in; with the chart it plays on with nobody playing, "just on a delay relative to the
count-in". The transcription project's `docs/band-that-follows.md` ("The first live runs") has the causes and the
listening's numbers; here, the service.

- **The cause was the band following itself**, reproduced with no device: `[device] file_room_ir` (`tools/ud_run.py
  --room-ir`, a room from `tools/ud_room.py`) puts the band's own output, through a room's response, into the input.
  With nobody playing the band drifted 236 ms late by beat 12 and slowed from 170 to 136 bpm. The clock was right:
  every click in the loopback at its engine frame plus `L`.
- **The band's own sound taken out** of the input it follows (`[band] echo`, per input `echo`): the transcription
  project's `transcribe.echo` in the capture path, block by block (256 frames, no delay), the loopback as the
  reference, from the count-in on; what it subtracted goes to the beat follower beside the input less it. Each input's
  learnt room is kept in `~/.cache/ugly-duckling/echo-<input>.npz` and the next session starts from it. Removed:
  18-22 dB once the room is known, 2-7 dB in a cold room's first 5 s, 19.5 dB after 20 s (the player as loud as the
  band). With the player's take and the band as loud in the mic, the band now stays within -70 to +60 ms of the
  player's grid at 168-173 bpm, as with no band in the mic at all; without it, 6 s behind by beat 86.
- **The room mic always captured** (`[device] room`, input 4: capture channel 3), whichever input the band follows:
  its own echo canceller (0.1 s of room) gives the room's delay, the output to the speakers to the mic, logged every
  2 s (`reliable` false when the response's peak is under 8 times its median or under 1 dB was removed lately); the
  page shows "room delay: N ms". The installer adds `room = [3]` to an `/etc/ugly-duckling.toml` from before.
- **The entrance**: every part's first note within 0.24 ms of beat 1 (the chop of its "and"), at 170 and 100 bpm, no
  device. The parts no longer come in over `hold` beats after the band's own count-in, and beat 1 is placed by the
  clicks alone (`docs/band-that-follows.md`).
- **The count-in**: two bars at or above `[band] two_bar_bpm` (150), one below (in 2/4 each counted bar is two of the
  tune's); the page's count-in card shows which before Start ("Count-in: 2 bars (8 clicks; at 170 bpm: two bars from
  150 bpm up)"), with Auto, 1 bar and 2 bars to choose; the playing view repeats it under the input meter. All the
  clicks go to the band. "I count it in" shows the expectation (one bar, or "one ... two ..." and a bar).
- **Stopping**: no attack from the player for `[band] stop_beats` (5) beats (8 before the first) and the band stops
  ("You stopped playing"): what sounds rings 0.6 s and fades. A rise counts as an attack only `noise_gate_db` (6) over
  the room's noise. No device, the take cut 20 s in: the last note 2.6 s after the cut at 170, 4.1-5.4 s at 100.
- **Every session recorded** (`ugly_duckling/record.py`, `[record]`): `~/ud-sessions/<start time>/capture.flac`
  (48 kHz, 24-bit: the input, the loopback, the input less the band, the room mic) and `session.jsonl` (the
  settings, the tune and chart, the count-in, the clock, every beat, cue and decision, the levels every half second,
  the room's delay, the stop, and at the end every note's frame). Written by a thread of its own; the oldest deleted
  beyond 40 sessions or 2 GB; nothing recorded under 2 GB free; at most 30 minutes a session. On the desktop:
  `tools/pull-ud-session [NAME|latest|list]` copies one to the transcription project's `outputs/ud-sessions/`, and
  `tools/ud_session_timing.py` reads it: each click and the band's first notes in the loopback against the count's
  grid, the band's beats against it as the session went, the room's delay.
- Fixed on the way: two races at a stop (the status read the ring as it closed; the engine's last report read it
  after). `UD_TRANSCRIBE` points a run at a worktree of the transcription project.

### Any of my tunes: the band finds the tune (2026-10-18)

A start with no tune chosen. The listening and the deciding are the transcription project's (`transcribe.band.TuneFinder`;
its `docs/band-that-follows.md`, "No tune chosen", and `docs/findings.md`, "The band with no tune chosen", have the
design and the numbers); here, the service and the page.

- **The page**: "Any of my tunes" after the tunes ("it listens, then follows the chart"), with "In 4" and "In 3 (a
  waltz)" under it when a tune in 3 is loaded. The tempo is where the count starts (100 bpm by default); the count works
  as for a tune: the band's clicks at that tempo, or the player's spoken count. Playing, a line under the title says
  "Listening for which tune" (with "maybe Red Wing (55%)" once the matcher names one at 30% or more), then "Found by ear:
  following its chart, in G", and the title line becomes the tune's name. Picking a tune works as before.
- **The service**: the tune ids `any` (counted in 4) and `any-3` (in 3) give the session a stand-in tune with no chart,
  and the config's tunes whose meter fits as its `catalog` (a tune in 2/4 fits a count of 4). The band
  (`LiveBand`, or `VoiceBand` for a spoken count) gets them as `tunes`: it plays the chords it hears (the chop and the
  bass), and once it has named one tune at 0.7 or more at two bar ends running it takes that tune's chart at the place
  heard: the chop, bass and chords from the next bar. If the chart's chords stop fitting those heard, it lets the chart
  go and listens again. With a count, beat 1 is the tune's downbeat. The status has `find` (the tune followed, its key,
  and the tune named with its confidence); each decision in the session log has `tune`, `named`, `named_conf` and
  `held`; the start event lists the catalog.
- **No device** (the free guitar take, G C G D, counted in 4 at 103 bpm): the tune named on beat 16 of the playing, 10.0
  s after the last click; every cue on time, none late or dropped (`tests/test_ud.py`).
- **The afternoon's sessions replayed** in the transcription project as if no tune had been chosen: Cherokee on the bass
  (the band's count) named on bar 9, Red Wing on the dobro (a spoken count) on bar 17, Big Sciota on bar 22 of 24; the
  right tune each time, and from there the chords the same as the band given the tune.
- Not deployed.

### Band sounds: a plan (2026-10-17)

The player: "sketch out a plan for incrementally improving band sounds... which probably means making our own
soundfonts and gradually improving them for all the instruments we care about (which is part of where the website
will help)". The plan is `docs/sound-plan.md`. In short:

- **Our own sample sets,** instrument by instrument, from sessions recorded for sampling through the 18i8, guided by
  the exercise app (each take a short score that is also its answer key), and cut, labelled and checked by the
  transcription pipeline's detectors.
- **Each step ends with matched A/B renders** of the same notes, blind where possible, with a short form, and the
  player decides. Loudness, attack timing, spectrum and the pipeline's round trip are measured beside the ear.
- **The first steps:** the bass's missing notes and the guitar's boom-chuck from the D-1; then the banjo's and the
  mandolin's chops, with round robins in the engine; then the dobro by string (the dobro-soundfont session).
- **Stay on FluidSynth,** with round robins, strings and articulations chosen by the engine, and fonts written from a
  neutral sample map, so SFZ (sfizz) stays open if the ear asks for it.
- **Other players' instruments** through the website, under one stated open licence for the project's fonts;
  GeneralUser GS and FluidR3 keep their own terms. Twelve open questions for the player at its end.

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
