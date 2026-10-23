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
- **The page** picks the tune, the tempo (default: the tune's takes' tempo, those to a metronome first), who leads
  (below), the pocket ("The pocket", below), the count-in, the input (room mic, Nadine, piezo), the instrument (the
  follower's preset), the parts (bass, chop, chords) and the band's volume. Playing, it shows the beat in the bar, the
  chord, the key and the chart's guess, each part's on/off and whether it has come in, the input's level, and the
  timing.
- **Who leads** (2026-10-18; the player: "a beginner needs the band to hold steady. an advanced picker can lead it
  like a real band"). Under the tempo, kept for each tune as its tempo is: "The band holds steady", "The band
  follows gently", "You lead" (the default: the band as before, beat for beat). The start request's `follow` (a
  step's id or 0-1, `session.FOLLOW_STEPS`: 0, 0.25, 1) goes to the beat follower as
  `livebeat.LiveBeatParams.follow` (passed only when not 1, so an older transcription project runs the default;
  a step below 1 with one that lacks it is refused at Start). Holding, the band keeps the tempo it started with:
  the band's clicks (the page's tempo), or a spoken count's tempo re-fitted to the first two bars played (a
  beginner counts at one tempo and plays at another), then no drift followed and no chase; it still stops when the
  player stops. "Gently" takes a lasting change 2-3 beats later than leading, with half the wobble. The playing
  view names the setting when it is not "You lead"; `tools/ud_run.py --follow` runs it with no device. The
  transcription project's `docs/band-that-follows.md`, "Lead or follow", has the design and the numbers. No
  device, Red Wing's take (played near 100) counted in by the band at 108: leading, the band at 100.1 bpm by beat
  45; gently 100.5; holding, 108.0 on every beat, within 0.3 ms of the count's grid for 50 beats, and with the take
  cut 15 s in it stopped with the player. At hold the band's place in the chart still follows the player's chords
  (the chart follower): its chords went where the player was in the form, at the band's own time.
- **The tunes**: Red Wing, Down Yonder, Big Sciota (with its second endings), Cherokee Shuffle and Saint Anne's
  Reel (AABB), Tennessee Waltz (3/4), and the free guitar take's form (G C G D, 2/4), from the transcription
  project's `chords.txt` and `takes.csv` (`[[tunes]]` in the config).
- **Safety.** Nothing opens the device until Start. Before opening it the band asks the other apps to let go
  (`/api/yield`, `ambient/peers.py`) and refuses to start while one records; it answers `/api/yield` itself by
  stopping. The volume is capped at +12 dB over the band's own level (-33 dBFS gated rms at 0 dB), which puts it
  at about -21 dBFS, the level takes play at; every sample is clipped at -1 dBFS whatever the volume. A stop (the
  page, a yield, an error, "stop", or 10 minutes with nothing played): nothing new starts, what sounds rings
  0.6 s, a 0.2 s fade, the device closed (about 1 s in all). The other apps list 8004 among their peers. Since
  2026-10-19 the band and the ambient synth also ask piano-recorder's transcribe app (8006), which records.
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
- **The afternoon's sessions replayed** in the transcription project as if no tune had been chosen, as the band runs
  now (a spoken count's band without the echo estimate): Cherokee on the bass (the band's count) named on bar 9, Red Wing
  on the dobro (a spoken count) on bar 23, Big Sciota on bar 17 of 24; the right tune each time, and from there the
  chords the same as the band given the tune.
- Not deployed.

### The pocket (2026-10-20)

Where each part sits against the band's beat. The player chose "pushed" by ear (the pushed backbeat, the close mics'
defaults; the transcription project's `docs/pocket-parameters.md`, "The player's choice", and its review
`2026-10-20-pocket-presets`), and rated "even" better than the band as it was too, at 100 and 125 bpm. Built as
`ambient/pocket.py`; the default "pushed". In ms against the band's beat, + late, - early:

| preset | bass | chords on the beat / on its "and" | chop | scatter (sd) |
|---|---|---|---|---|
| pushed (the default) | -6 | +2 / -5 | -4 | 4 |
| even | -8 | 0 / 0 | -3 | 4 |
| none (the band as it was) | 0 | 0 / 0 | 0 | 0 |

- **Where it acts.** In the band player (`BandPlayer.cue`): the voicing's notes for a cue
  (`transcribe.bandvoice.play_notes`) moved by the pocket in the band's own time, then mapped to the engine by the
  stream clock. So a live run, a replay and an offline render that places the voicing's notes with the same
  `Pocket.place` (`tools/band_replay.py --pocket`, `tools/pocket_check.py`) play the same notes. The band's clock,
  its beats, its decisions, `lead_s` and the stream clock are untouched. The engine judges lateness (`LATE_S`)
  against the moved time.
- **The classes.** A note's class is where it falls in its beat: the band's beat (the recordings' 1 and 3) or its
  "and" (their 2 and 4). The band's chords strum on every beat, so they take the recordings' guitar boom's +2; the
  -5 for a strum on the "and" waits for a boom-chuck comp (the voicing, not built: the board's `pocket-in-band` has
  it), which would take it without a change here, its boom and strum classed apart even when voiced from one play.
- **The scatter** is drawn per play and class from its own generator, seeded by the pocket's seed, the part, the
  class and the beat, and clipped at 2.5 standard deviations (10 ms at 4): the same draws in any order the cues come.
- **The lead.** An early note spends that much of the margin the band's lead leaves when its cue reaches the player.
  The earliest a pocket can put a note: "pushed" -16 ms (the bass's -6 less 2.5 scatters), "even" -18; a pocket that
  could go earlier than 20 ms is refused (the band's cues had 22-25 ms left at least on the control unit, above).
  Measured, no device: the whole loop on Red Wing (the take, 25 s), the least margin 25.6 ms with none, 14.3 ms with
  pushed (the bass's first note 13.7 ms early: a draw of -1.9), median 33-34 either way, nothing late or dropped; the
  replay of Red Wing (`tools/band_replay.py red-wing --pocket pushed`, the wall clock's pace) the bass's margin
  median 28.3 ms, least 17.3 (the chords' 36.6 and 25.4), every note the offline render's, asked within 0.01 ms of
  it, none late or dropped. `tests/test_band.py` checks the case: a cue with the unit's least margin (22 ms) and the
  note moved the most "pushed" can (16 ms) is on time.
- **The setting.** The config's `[band] pocket` names the preset (`pocket = "pushed"`, the default when it is not
  there), or is a table with per-part overrides of it (`pocket = { preset = "pushed", bass = { beat = -5, scatter =
  3 } }`, and `seed`); checked when the config is read. The page's "Pocket", under "Who leads": Pushed, Even, None,
  the numbers in words under it, one choice for every tune; the start request's `pocket` (a preset's id; the config's
  if not given). The playing view names it when it is not the default. The session's log has the pocket at the start
  (its numbers and seed) and each cue's `pocket_ms`. `tools/ud_run.py --pocket`.
- **Checked by the pocket analyzer** (`tools/pocket_check.py`; the transcription project's `transcribe.pocket` on each
  part's stem, as its `pipeline/tools/pocket_ab.py` checked the review's renders). The band alone on Red Wing's chart
  at 100 bpm (32 bars), its own three parts through the band player and engine; measured and expected each less the
  "none" render's, the expected against the notes' own consensus (the analyzer's grid moves with the pocket), ms:

  | | bass, beat | chords, beat | chop, "and" |
  |---|---|---|---|
  | pushed: set / expected / measured | -6 / -3.4 / -3.1 | +2 / +4.4 / +5.8 | -4 / -1.5 / -1.5 |
  | even | -8 / -4.3 / -4.0 | 0 / +3.6 / +4.9 | -3 / +0.2 / +0.2 |

  The chords read 1.3-1.4 ms late under scatter, as the review's guitar boom did. The review's own notes and render
  (the boom-chuck guitar, a banjo behind), placed by this code: within 0.5 ms of the review's own measurements of
  "pushed" and "even" in every cell (the bass -3.3 against -3.0, the boom +6.0 against +6.0, the strum -3.6 against
  -4.1, the chop -2.3 against -1.8).
- **Found with it: the beat follower's echo weighting.** With no device, "Any of my tunes" on the free guitar take
  (no chart: the parts come in on what the band hears) stopped the band after about 10 beats ("You stopped playing")
  in 7 runs of 10 with "pushed", and named the tune at 13-18 s in the other 3; with "none" it named it in 7 of 7 at
  10.8-15.7 s; "even" at 18.1 s in 3 of 3. With the echo canceller off, or with its estimate not given to the
  beat follower (the cleaned input kept), "pushed" named it at 10.8-13.3 s. The follower counts a rise only as far as
  the input stands over the canceller's estimate of the band there (`livebeat` `echo_margin_db`); once the band's bass
  sounds a few ms before the player's attack, a cold canceller can predict that attack from the band, and its
  estimate swallows the attack's rise. Here the estimate is all spurious (no band in this input), as it would be on
  a pickup with little of the band. With the tune's chart chosen (counted in) the same take ran alike with both (5
  runs); so did Red Wing on the dobro and Down Yonder on the bass. The test for "Any of my tunes" runs with "none";
  the follower's weighting is the transcription project's to look at before the live band leans on it. (Fixed:
  below, "The pocket and the echo estimate".)
- Not deployed. No config entry is needed on the unit: without one the band's pocket is "pushed".

### The pocket and the echo estimate (2026-10-20)

The unit runs `pocket = "none"` (`/etc/ugly-duckling.toml`) since the find above; this puts "pushed" back as the
band's default. The measurements and the reasons are the transcription project's (`docs/findings.md`, "The pocket and
the echo estimate"; `docs/band-that-follows.md`, the same title); here, the band.

- **The cause:** a cold echo canceller explains the guitar by the band's bass, which sounds the guitar's pitches
  20-60 ms before its booms ("pushed" adds 4-10 ms): with no band in the input its estimate stood 0-3 dB under the
  guitar in the low band within 60 ms of the bass's first note, and the follower's weighting (`echo_margin_db`) took
  the take's two weak booms in beats 2-5. With "none" it took attacks too, but kept those two.
- **The fix, in the session:** the beat follower is given the canceller's estimate as far as the canceller is sure of
  it (`session._band_estimate`: the transcription project's `EchoCanceller.sure_estimate`; per bin, the estimate's
  power by its share of that and the echo the Kalman filter expects it may still miss), in place of all it
  subtracted (`raw - heard`). What the band hears, the input less the whole estimate, is unchanged. A transcription
  project from before it (no `sure_estimate`) is given `raw - heard` as before.
- **The capture has five channels:** channel 4 is the band as the beat follower was given it (`ugly_duckling/record.py`;
  the start event's `capture_channels`), so a replay gives the follower what the session gave it. Channel 0 less 2
  is still all the canceller subtracted.
- **No device, every run with no learnt room** (before: this branch's base with the transcription project's
  01f1aef): "Any of my tunes", the free guitar take, "pushed": named in 20 of 20 runs at 14.4-19.2 s (before 4 of 10,
  6 stopped at 6.3 s); "none" 5 of 5 (12.1-19.2 s); "even" 5 of 5 (14.6 s). The tune chosen, 3 runs each pocket: Red
  Wing (dobro) and Down Yonder (bass) as before (Down Yonder with "pushed" one beat fewer on the chart's root of 55).
  The band alone in a cold simulated room (`tools/ud_room.py`'s defaults): it stops as before (6 beats at 170 with
  "pushed", 19 with "none", 15 at 100), and plays through with the dobro takes as before.
- **Left, as before:** with the guitar take's chart chosen and the guitar preset, "even" and "pushed" stop the band at
  6.3 s (3 runs of 3, before and after); "none" plays through, and so does "pushed" on the dobro preset (the input's
  own instrument). The canceller's subtraction itself takes the booms there, not the weighting: a cold canceller's,
  with no band in the input. On the unit each input starts from the room it learnt; with no device every run starts
  cold.
- `tests/test_ud.py`: "Any of my tunes" runs on the default pocket again ("pushed"); the recorded session's capture
  has five channels, channel 4 no louder than channel 0 less 2.
- Not deployed. For the unit: the transcription project's `pipeline/src` and this branch, then the `pocket = "none"`
  line taken out of `/etc/ugly-duckling.toml` by hand.

### The steady band clock (2026-10-20)

The player, on the band's challenge: "The band needs to keep a pretty steady tempo with all changes as gradual as
possible while still keeping aligned with the downbeats I play." The clock is the transcription project's
(`livebeat.LiveBeatParams.steady_bars`, `onset_lead_s`; its `docs/band-that-follows.md` and `docs/findings.md`, "A
steady band clock", have the design and the numbers); here, the settings that reach it. Off until the player had
chosen by ear; on by default since 2026-10-21 (below).

- **The steady clock** (`Settings.steady`, bars; None the band's clock as before): the band's phase comes to the
  player's beats over about that many bars, its tempo over one, the chase opening both for a quick lasting change.
  "Who leads" scales it as it scales the band's clock now ("gently" four times as wide, "hold" holds), for every
  instrument and either count. The config's `[band] steady_bars` (absent: off) is the default a start gets; the start
  request's `steady` (a width in bars, 0.25-16, or "off") overrides it; `/api/options` gives the default.
- **The onset lead** (`Settings.onset_lead`; `[band] onset_lead`, the start request's `onset_lead`): the band's beats
  on the player's attacks rather than on their onset function's peaks, by the transcription project's
  `livebeat.ONSET_LEAD_S` for the instrument (the bass's 20 ms; none for the dobro and the guitar, so it changes
  nothing there). Under a bass the band was a median 19 ms early on the sung take; this takes it to 1 ms late.
- Both go to the beat follower only when set (`Session._beat_params`), so an older transcription project runs the
  default; one without them refuses a start that asks for them. The session's start event has both in its settings.
  `tools/ud_run.py --steady BARS --onset-lead`.
- **No device** (`tools/ud_run.py`, Red Wing's take, the desktop config, 30 s): with `--steady 1` the band's tempo moved
  a median 0.28% a beat against 1.92% without, 46 beats each, every cue on time (45 a part, none late or dropped).
- **Not on the page yet**: the width is the player's choice from the renders of the sung take (the transcription
  project's `exercises/observations/ud-oracle-2026-10-19/live-lines/`); then a control under "Who leads", or the
  steps re-cut (hold, the steady clock at the chosen width, beat-by-beat lead). `tests/test_ud.py`: off unless asked,
  passed when asked, the onset lead only where one is measured, widths out of range refused.
- Not deployed. Needs the transcription project's matching commit.
- **On by default, 2026-10-21: steady over half a bar with the onset lead** (`config.STEADY_BARS` 0.5, `ONSET_LEAD`;
  a config's `steady_bars = "off"` or a start's `steady: "off"` turns it off). The player heard the live clock beside
  the hindsight line in two reviews (the transcription project's `2026-10-20-band-clock` and `-live`; its findings,
  "The live clock by ear") and then said to settle it from those answers: "do what you can with info you already
  have". Half a bar is the only live setting never heard as throwing them off, and the steadiest on Red Wing's entrance
  ("Pocket is better here"); a bar threw them off twice, 2 bars once ("lots of tension"). No device, Red Wing's take,
  30 s: every cue on time at the default (135, none late or dropped, margins 14-33 ms), the band's tempo moving a
  median 0.30% every 4 beats against 0.35% off (90th percentile 0.60% against 0.91%), the bass on the chart's root
  95.6% of beats against 91.1%; the listening's CPU within the run-to-run spread (157-255 ms a second against
  205-225). `tests/test_ud.py`: on by default in every config, "off" in a config or a start, a start's own width
  passed. Still not on the page: the default does it.

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

### Samples from takes, and the upright's low E (2026-10-20)

The sound plan's extraction, built: `tools/samples.py collect|report|choose|build INSTRUMENT` (`upright`, `guitar`),
one tool for every instrument (`docs/sound-plan.md`, "Extraction: from takes to samples", has the stages and what the
takes in hand give). It reads the transcription project's takes and pipeline (and its new `transcribe.click`), writes
every candidate and its checks to `sounds/samples/INSTRUMENT-candidates.json`, the chosen samples to a map in git
(`sounds/samples/INSTRUMENT.json`), the cut WAVs to `~/.cache/ambient-room/samples/`, and the SF2 from the map. It
replaces `tools/upright_font.py`: the upright's 2026-10-15 samples are the map's pinned entries, and built from them
alone the font is the same file byte for byte (`tests/test_samples.py` checks the writer against the dobro font's).

- **The upright's low E clicked** (the transcription project's board, `the-upright-s-e1-sample-clicks-65`): the
  exercise app's click, which the old mixer recorded into the take electrically, sat 64 ms and 0.81 s into the E1
  sample (E1 and F1), 46 dB over the note's ring at 2-8 kHz and about as loud as the note there; the G2 (F2-G#2,
  which only the ambient synth plays) had it on its attack and at 0.76 and 1.51 s. The tool takes the click out of a
  take before it cuts; the map now has the E1 it chose (bass exercise 008's, 14 October, 4 s, its clicks taken out)
  and the old G2 with its clicks taken out. In the band's bass on Cherokee Shuffle's A part (24 E1s in 64 notes) the
  burst is gone: nothing within 35 dB of the note.
- **Heard by the player** before it ships: the transcription project's review `2026-10-20-upright-e1` (the font as
  it is, the tool's E1, the old E1 with its clicks taken out; blind, loudness matched). Not deployed: the unit has the
  2026-10-15 font. Needs the transcription project's matching commit (`transcribe.click`).

### Breaks on a tune's melody (2026-10-22)

The player (2026-10-21): "add a representation of the actual melody to the fiddle tunes that are set, but make it
treat those as an improvising bluegrass musician would: something to vary, iterate on, decorate, and play with (to
varying degrees, from an exact replication of the melody to a completely free melody that only takes the chords into
account (like the current version), but the interesting parts are all in the middle where the melody has a strong
influence but there's also lots of variation and room for surprise). i'd like to use ambient to close in on some
approaches that we can apply to UD later on, like having members of the band take breaks." The transcription
project's card `ambient-tune-melody`; its findings, "Breaks on a tune's melody", have the numbers.

- **The Tune line** (`ambient/breaks.py`; the melody style "Tune"). Chosen, not imposed: no preset, mood or default
  changed, and evolution never picks it. Over Red Wing's, Down Yonder's or Big Sciota's chart
  (`presets.TUNE_MELODIES`) it plays that tune's melody, laid in two where the chart is. The melody is the tune's
  answer key in the transcription project, read with that project's score reader when the style is chosen (the
  server looks in the project its `[band] transcribe` names); there is no copy here, since the keys are the player's
  own arrangements. Over any other chart, or with no tunes to hand, the Tune line is the Phrases line.
- **One control, "The tune"** (`melody.pull`, 0.5 unless set; the Melody tab's slider, free to as written): 1 plays
  the tune as written, 0 the free line over the chords (the melodist's Phrases, note for note today's). Between,
  the module's docstring has the rules: what is kept (the strong beats' notes, every phrase's landing note and the
  notes into it) and what is played with (fills, passing notes, pushes, octaves, a G run at a home cadence, a run into
  a landing, a repeated phrase answered, later passes further, past the middle whole bars of the free line). Each
  surprise lands back on the tune by the phrase's end.
- **Decoration by the instrument**: the style says whether a note is decorated, the voice's idiom how (`IDIOMS`): the
  dobro slides into a note, hammers on only from an open string and pulls off only to one, double stops a third or a
  sixth under, rolls a held note; the fiddle plays from its G string up (a tune's lower notes an octave up). The
  dobro's samples slide, hammer and pull on the string (`conductor.play_strung_as`, `HAMMER_S`, `SLIDE_MAX`); a struck
  voice takes a slide into a note as a grace note (`GRACE_S`). Notes the Tune line places have none of the hand's
  random slides.
- **Its own dice**: `Conductor(melody_rng=...)` gives the melody its own random generator, and `break_seed` the
  break's. Without them nothing changes: the melodist shares the conductor's dice, as before. With them the band's
  notes are the same under every line, note for note (`tests/test_breaks.py`).
- **Measured** without sound, 20 seeds each, the first pass: the tune's notes that start on beats 1 and 3 that the
  break sounds there, and the share of the break's notes that are the tune's own.

  | The tune | Red Wing (dobro) | Down Yonder (fiddle) | Big Sciota (dobro) |
  |---|---|---|---|
  | 1, as written | 100% / 100% | 97% / 95% (its bar 12 an octave up) | 100% / 100% |
  | 0.75 | 98% / 73% | 92% / 68% | 92% / 73% |
  | 0.5 | 84% / 57% | 79% / 55% | 66% / 52% |
  | 0.25 | 53% / 41% | 49% / 39% | 39% / 36% |
  | 0, free | 2% / 1% | 3% / 1% | 5% / 3% |

  Every phrase's landing note is there at 0.25 to 1 (100%); free, 62%, 34% and 100% by chance. At 0.5 the later
  passes depart further: Red Wing's strong-beat notes 84%, 72%, 60% over three passes.
- **Breaks for the ear**: `tools/tune_breaks.py` renders a tune's breaks to files (Csound offline, nothing heard): the
  band once, each break's melody alone, then mixed; the clip a bar before the pass, the pass, and the next pass's first
  note, -20 LUFS each. The 21 clips of the transcription project's review `2026-10-22-tune-breaks` (seven a tune:
  1, 0.75, 0.5 three times, 0.25, 0) are in `~/.cache/challenge-reviews/2026-10-22-tune-breaks/`. The tool checks
  that the band's notes are the same in every version and that the engine was given every note of the break.
- **Toward the band** (the Ugly Duckling String Band): a member's break is this line at a pull, on its own dice,
  landing on the tune's phrases while the band backs it; to come, calling the breaks (card `band-form-calls`), each
  member's idiom (the banjo's rolls, the fiddle's double stops) and the band's tunes' melodies.
- `tests/test_breaks.py` (14); the suite 115 passed, 1 skipped (FluidSynth loadable; no ctcsound under Miniconda),
  and under the venv the engine's, the conductor's, the server's and the breaks' tests 76 passed. The UD self-check
  failed now and then while another agent's jobs loaded the desktop, on main as here (an underrun). Not deployed.

### Cherokee Shuffle's chart (2026-10-22)

The synth had no Cherokee Shuffle: its "Fiddle tune chart" is the player's own tune (in C), not Cherokee's. The
transcription project's card `ambient-cherokee-chart` (#213); the player (2026-10-22): "do both quick wins, and deploy
them".

- **The chart** (`presets.CHEROKEE_SHUFFLE`; the harmony and the mood "Cherokee Shuffle"): the player's Strum Machine
  chart in the tune's folder there (`tunes/dobro/cherokee-shuffle/chords.txt`, 2026-10-16), in A, laid in two as Red
  Wing (two of its bars to a bar). A, 8 bars: A, A, A, F♯m, D, A, E, A. B, 10 bars: D, A, D, A, D, A, A, F♯m, D and E
  half a bar each, A. AABB as played, both endings A: 36 of its bars, 18 here. A chord that goes on over a bar line is
  carried with "/", so the loop is 31 chords (a loop holds 32).
- **The mood**: the chart in A at 170 (the take's tempo; 85 here, tempo 0.35), the "Fiddle tune in two" line on the
  dobro, "Bluegrass in two", the Country band. The Tune line is chosen on the Melody tab, as for the other three.
- **The melody** (`presets.TUNE_MELODIES`): the tune's answer key there (`cherokee-shuffle.musicxml`, as the player
  corrected it on 2026-10-16), one pass of 36 bars: 110 notes and 6 double stops' added notes, from A3 on bar 1 to the
  E3 back to the top. `tools/deploy` already copies every dobro tune's key to the unit.
- **Phrases within a part**: an entry may give the bars of each part of the pass (`parts`; Cherokee's 8, 8, 10, 10). A
  phrase is four bars within its part, a part's remainder joined to its last phrase, as `breaks.py`'s docstring
  said; before, the pass was one part, and B's phrases ran over its end. Now B is phrases of 4 and 6 bars: it lands on
  its A3 at its end (a home cadence, where the run may go) and the second B answers the first. A tune given no parts
  is one part, as before: Red Wing's, Down Yonder's and Big Sciota's measures are the same as before this change, to
  the digit (20 seeds, three passes, five pulls each).
- **Measured** as the others (20 seeds, the first pass; the tune's notes on beats 1 and 3 that the break sounds
  there / the break's notes that are the tune's own). Cherokee Shuffle is development in the transcription
  project's split; nothing was set from it.

  | The tune | Cherokee Shuffle (dobro) | its B as four-bar phrases over the bar line |
  |---|---|---|
  | 1, as written | 100% / 100% | 100% / 100% |
  | 0.75 | 96% / 53% | 97% / 57% |
  | 0.5 | 77% / 38% | 82% / 42% |
  | 0.25 | 45% / 24% | 52% / 26% |
  | 0, free | 6% / 2% | 6% / 2% |

  Every arrival sounded at 0.25 to 1; free, 61% by chance. Notes a bar: the tune 3.1 (mostly quarters and halves);
  5.0 at 0.75, 5.4 at 0.5 (the fills), 5.5 free. At 0.5 the passes keep 77%, 65%, 51% of the strong-beat notes. The
  tune keeps less of itself than the others at the same pull (Red Wing 84% / 57% at 0.5): its notes are long, so
  more of them are filled, and the second A and B answer the first.
- **Rendered** (`tools/tune_breaks.py --tunes "Cherokee Shuffle"`; Csound offline, nothing heard): one pass, 52.9 s
  with the bar before and the tail, -20 LUFS. As written (gain +10.6 dB, peak -6.8 dBFS, the engine given all 116
  notes) and at 0.5, seed 1 (+9.1 dB, -6.6 dBFS, 216 notes; 83% of the strong-beat notes, every arrival).
- **Found in the renders**: a pick on a dobro string 3.8 to 4.0 s after that string's last pick is lost. The
  conductor counts the string's note as over (`samples.RING_S - 0.2`) and sends no stop, but Csound's note still
  sounds until 4.0 s, so the new pick is tied into it (no attack, the old sample retuned) and stopped with it a
  moment later. As written, 4 of Cherokee's 101 picks on a string (bar 6's C♯4, beat 2, among them); over the
  review's seven clips a tune, Red Wing 7, Big Sciota 8, Cherokee 10. In the Phrases line too (`play_strung`). Not
  changed here: a sound change, for the player's ear first (branch `strung-pick-window`).
- `tests/test_breaks.py` (17): parts split phrases; the chart beat by beat; with the transcription project here, the
  chart against `chords.txt`, the key read as one pass (its arrivals and repeats), and the Tune line playing it as
  written over the mood. The suite 118 passed, 1 skipped (no ctcsound under Miniconda; FluidSynth loadable); under the
  venv the engine's, the conductor's, the server's and the breaks' tests 79 passed. Not deployed.

### A pick on a string never lost (2026-10-22)

Found in Cherokee Shuffle's renders (above): a pick on a dobro string 3.8 to 4.0 s after that string's last pick was
tied by Csound into the note still sounding there, with no attack, and stopped with it at `samples.RING_S` (4 s).
Now a pick stops the string's note whenever it may still sound, up to 4.5 s after it (`conductor.stop_string`,
`STOP_MARGIN_S` 0.5 s: room for a note that started late), in the Tune line (`play_strung_as`) and the Phrases line
(`play_strung`). A stop for a note already ended does nothing; Csound says it found none.

- Over the review's seven clips a tune (pulls 1, 0.75, 0.25 and 0, and 0.5 three times), the picks lost: Red Wing
  7 to 0, Big Sciota 8 to 0, Cherokee Shuffle 10 to 0. The band and every note the same, before and after, in each
  tune at pulls 1, 0.5 and 0; only the stops added (2 or 3 a run).
- Heard: Cherokee as written, bar 6's C♯4 (beat 2, held three beats) now sounds, 2.7 dB more over those 0.4 s.
  For the player's ear before it goes on: the Cherokee clips, today's against this.
- `tests/test_breaks.py` (18): a pick 2, 3.9 and 4.2 s after the last on its string stops it, 5 s after does not, in
  both lines. The suite 119 passed, 1 skipped; under the venv 80 passed. Not deployed.

### A break's note density (2026-10-22)

The player, after the Tune line on Cherokee Shuffle at pulls 1 and 0.5: "For the ones closer to 0, I think it'll be
important to reduce note density... a player would play different notes and rhythms from the standard melody, but not
necessarily play something far busier ... with low note density, i'd want to hear it actually simplify the melody in
some cases rather than ornament it". The transcription project's card `ambient-break-density` (#232).

- **The control**: Note density, on the Melody tab beside The tune (`melody.density`, 0 to 1; 0.5, the default, is
  the tune's own; `breaks.density_of`: a quarter of the tune's notes at 0, twice them at 1, linear on each side).
  It is lockable and in a preset's Melody part, like The tune; evolution never moves it. Its words: "the tune's own
  notes, and what the pull adds", "50% of the tune's notes: simpler", "up to 150% of the tune's notes: filled".
  A new density is taken up from the break's next phrase, as a new pull is.
- **At the default the synth is as before**: the density's rules are not asked (a test stops them), and every note
  the conductor sends is the same as on main (3db72aa) over the four tunes, pulls 1, 0.75, 0.5, 0.25 and 0, and 20
  seeds each: 400 runs, 455,441 notes (the band's and the line's) and 109,212 notes of the break as heard, also with
  the density set to 0.5 by hand.
- **Below the tune's own** a phrase is held to that share of the tune's notes in it (from 0.75 down; between 0.75 and
  1 the notes it plays over the tune's own give way in proportion, so the control has no step at 1): the skeleton
  kept (its first note and its landing always; the notes on beats 1 and 3, the landing's approach, a note where the
  chord changes, one where the tune strikes a note), and first dropped a fill's or a run's notes, a grace note, a
  repeated note (held instead), a passing or neighbour note; of the rest the tune's own where the pull is high, the
  chord's tones where it is low. Each note left is held to the next, never into a bar the free line takes; where one
  would be held past its own length over a chord it is not in, a note dropped there is struck again; one held longer
  over other notes, out of its chord, moves to the chord's nearest. The free line's bars are held the same way to
  the share of the tune's notes in each bar (one note at least). It has dice of its own, so a break at a density is
  its seed's break at 1, simplified. Cherokee, pull 0.75, bars 1-4 (seed 1): as written A3 2 | A3 1.5 B3 .5 | C#4 1
  B3 1 A3 2 | A3 1.5 A3 .5 C#4 1 E4 1 | F#4 3 G#4 1 (12 notes); at the tune's own density 29 notes (eighth fills, a
  roll over the F#4); at 0.75, A3 2 | A3 2 | C#4 1 B3 1 A3 2 | A3 2 C#4 1 E4 1 | F#4 4 (9); at 0.5, A3 2 | A3 2 |
  C#4 2 A3 4 | C#4 2 | F#4 4 (6).
- **Above the tune's own** a phrase's held notes are filled as the pull fills them, in a random order (its landing
  last; not a double stop's), until it has that share of the tune's notes; a break already busier is left as it is
  (Cherokee at 0.75 plays 1.64 times its notes at 1, 1.66 at 1.25). The free line is not filled. The tune as written
  is the same at every density.
- **The departure by the tune's own density** (`BreakParams.local`, None: off). From the player's answer on Down
  Yonder at 0.25 (review `2026-10-22-tune-breaks`): "a fiddle player would usually hit most of the standard notes in
  the low density portions ... and then innovate on the density parts more freely". Set, each note's moves and each
  bar's chance of the free line go at d ** (1 / r ** g), r the tune's notes in that bar against its mean. With g 2,
  over 20 seeds at pull 0.25, Down Yonder's sparse bars (0.8 of the mean or fewer) keep their beat 1 and 3 notes 58%
  -> 74%, its busy bars (1.3 or more) 45% -> 33%; at 0.5, 82% -> 89% and 88% -> 60%. Off until the player hears it.
- **Measured** (`tools/tune_breaks.py --measure 20`, no sound; the first pass; the four tunes are development and
  validation in the transcription project's split, nothing tuned on a held-out tune): see that project's findings,
  "A break's note density". From pull 0.25 to 0.75 the break's notes against the tune's come to 0.75-0.82 at
  density 0.75 and 0.50-0.59 at 0.5 (the strikes where the chord changes add a few, most on Cherokee); free, 0.66-0.86
  and 0.49-0.62 (a bar where the free line plays fewer than the share keeps them). Every landing sounded at every
  density from pull 0.25 up; the chord changes struck 93-100% at every density from 0.25 up. New in `breaks.measure`: the tune's
  onsets the line strikes too, the chord changes it strikes, and how alike a repeated phrase is to the phrase it
  repeats. `tools/tune_breaks.py`: `--densities`, `--grid`, `--locals`, `--measure N`, `--json`.
- **Rendered** for the ear (`tools/tune_breaks.py`, Csound offline, nothing heard): Cherokee and Red Wing at pulls
  0.75 and 0.25, each at densities 1, 0.75 and 0.5 (seed 1); Down Yonder at 0.25 with `local` off and 2 (seed 14);
  Big Sciota at 0.5 at 1 and 0.75 (seed 3, the break the player said should keep "the simplified core of the
  repeated phrases"). 16 clips, 12.3 minutes, each -20 LUFS (gains +9.1 to +12.3 dB, peaks -4.2 to -7.0 dBFS), the
  band the same in every clip of a tune; the engine given every note of every break but one (Cherokee at 0.75 and
  the tune's own density, the tune's own slide from a slid note in bar 19, as today).
- `tests/test_breaks.py` 18 -> 26: the setting and its words; at 1 the density's rules never run; below 1 the same
  break simplified (every note one it played, held, or moved to its chord; no note struck again within two beats;
  none held over a chord it is not in while another note was there to strike); the tune's own kept where the pull is
  high, the chord's where low; above 1 filled, as written unchanged; the free line held; a repeat more like the
  phrase it repeats, nothing held into the free line; `local` off unless set, and what it does. The suite 119 -> 127
  passed, 1 skipped; under the venv the engine's, conductor's, server's and breaks' tests 69 -> 77. Not deployed: a
  sound change at any density but the default, for the player's ear first (review `2026-10-22-break-density`).

### Members' breaks in the band (2026-10-22)

The player: "let's take the ambient breaks work from today and build an option in UD for rotating through band member
breaks. dobro, fiddle, guitar, mando, banjo, and if that instrument takes a break, they drop out of the rhythm part (if
they were in it)". The transcription project's card `ud-member-breaks` (#212); its findings, "Members' breaks in the
band", have the measures. Needs that project's branch of the same work (its `transcribe/breaks.py`, `idioms.py`,
`bandbreaks.py`).

- **The break moved there.** `ambient/breaks.py` is now the synth's side only: finding the transcription project and
  importing its package (`$AMBIENT_TRANSCRIPTION`, then `~/play/dobro-transcription`, `~/dobro-transcription`), a
  tune's key (`load_tune`, cached), the loop's chords a beat at a time, which tune the harmony plays, the idioms by the
  synth's voice names, and the synth's `Break`: the style's, played into the conductor's grid (`plan_bar`, `at`), its
  free bars the melodist's (held to the note density by the style's `thin_free`). The rules are the transcription
  project's `transcribe.breaks` and `transcribe.idioms`, moved verbatim. The synth plays the same notes: four tunes,
  five voices (Dobro, Fiddle, Mandolin, Banjo, Acoustic guitar), pulls 1 to 0, densities 0.5 to 1.5, ten seeds and
  the local departure: 4,200 runs, 4,139,645 notes the conductor sent and 451,514 of the break as heard, every one and
  every measure the same as on main (8871704). The synth now imports that package at start (it read the tunes' keys
  through it before): `tools/deploy` copies its `pipeline/src` to the unit too, and stops if it has no breaks.
- **UD's option** (the transcription project's `bandbreaks`): Breaks in turn on the page under Who plays (on or off,
  and which of the five), off by default; at Start `breaks` and `break_members` (`Settings`); while it plays, a line
  naming whose break it is and who is next (the status's `breaks`). Only on a tune with a melody (`tunes.melody_for`:
  the dobro's answer key, for the tunes `presets.TUNE_MELODIES` lists, when one pass of it is one pass of the band's
  chart); with no tune chosen, each catalog tune's. With it off the session is as before: the band made with no
  `breaks`, the engine the three parts' synths.
- **The members' voices.** A member's notes come as cues of their own (its name the part), voiced by the transcription
  project's `bandvoice.BREAK_VOICE` on a synth of its own with its own fonts (`bandengine.Voice.fonts`: the dobro's
  program 25 is the steel guitar's too): the dobro `dobro.sf2`, the fiddle `acoustic.sf2`, the guitar and the banjo
  `generaluser.sf2`, the mandolin `mandolin.sf2`, new: GeneralUser GS's mandolin (its bank 16) moved to bank 0,
  program 25, 0.3 MB, built by `tools/soundfonts --band` (not normalised: only FluidSynth plays it). `tools/soundfonts`
  now pads a font's INFO strings to an even length (FluidSynth 2.6 refused the mandolin's odd one; the fonts built
  before were even and are the same). Their levels on the engine (`bandplayer.BREAK_GAIN_DB`: each 2 dB over the bass
  by loudness, measured on the offline render) and a beat's notes late by up to 30 ms (`BREAK_LATE_S`). Made only when
  the breaks are on: five more synths.
- **No device** (`tools/ud_run.py --breaks all`, Red Wing, 80 s, three runs each way): the dobro's break planned at
  beat 48, begun on the top at 64 and ended on the next at 128, its notes on time on every beat, none late or dropped,
  no underrun; the fiddle's pickup and top as the take ended. The cues' margins min 12.7-14.6 ms, median 31.4-32.0
  (off 14.4-15.4, 32.3-33.9). The engine's CPU 42-57 ms a second off, 70-72 on (the five members' synths, about 19);
  the session's own varies between runs (209-278 off, 260-270 on) more than the breaks add. The unit's estimate is in
  the transcription project's findings.
- **Deploy**, after the player's ear and with both merged: the transcription project's main first (its pipeline the
  synth and UD import), then `tools/soundfonts --band` here (writes `sounds/mandolin.sf2`), then `tools/deploy-ud`
  (copies the tree with the fonts, that project's `pipeline/src` and now the dobro tunes' keys), then `tools/deploy`
  (the synth: its breaks import from that `pipeline/src`), each after checking the apps are idle.
- `tests/test_ud_breaks.py` (new, 3): the four tunes have a melody, the others none; a member's break on its own
  fonts (the dobro, not the steel guitar); offered and taken at Start, refused otherwise, off the engine as before.
  The suite 127 -> 130 passed, 1 skipped (against the transcription project's branch: `AMBIENT_TRANSCRIPTION` and
  `UD_TRANSCRIBE` pointed at it). The page in muted headless Chromium at 390 px: the control off by default, on with
  the five, one taken out, Start's request carrying them; no error, no sideways scroll. Not deployed.

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

## Licence

The code is free software under the GNU General Public License, version 3
or (at your option) any later version (`LICENSE`). Copyright 2026 the
project's authors, as the git history shows. The player, 2026-10-23, in
dobro-transcription: "let's proceed with the GPL as the plan. (same with
ambient-room and piano-recorder.)" The band imports dobro-transcription's
pipeline, which is under the same licence.

Not under it:

- The fonts in `ugly_duckling/static/fonts/`: SIL Open Font License 1.1,
  its text beside each.
- The patches in `upstream/`: made for Csound, and meant for it under
  Csound's own licence (LGPL 2.1 or later).
