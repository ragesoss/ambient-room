# Band sounds: a plan (2026-10-17)

How the Ugly Duckling String Band and the ambient synth's acoustic voices
get better, one audible step at a time. Mostly by making our own sample
sets from the player's instruments and, later, other players'. A plan;
since 2026-10-20 its extraction is built (`tools/samples.py`, below,
"Extraction: from takes to samples") and has been run on the takes in hand.

The player: "sketch out a plan for incrementally improving band sounds...
which probably means making our own soundfonts and gradually improving them
for all the instruments we care about (which is part of where the website
will help)".

## Where it stands

- **The band** (`transcribe.bandvoice` in dobro-transcription, played by
  `ambient/bandengine.py` through FluidSynth, `ambient/fluid.py`) has three
  parts:
  - the bass: the player's upright (`sounds/upright.sf2`), root and fifth,
    each 0.9 of a beat;
  - the chords: GeneralUser GS's steel-string guitar (program 25), six single
    notes 12 ms apart;
  - the chop: GeneralUser GS's banjo (program 105), a close chord 4 ms a note,
    90 ms long (40 ms muted).
  Fills are not voiced.
- **The ambient synth** plays the same fonts through Csound's `sfplay3m`,
  with no font envelopes or filters (`sounds/README.md`), plus synthesized
  fiddle, mandolin and others.
- **The player's verdicts so far:**
  - the dobro "sounds very little like a dobro";
  - the old bass "isn't very much like an acoustic bass";
  - of every free guitar tried, "none of the guitars good": the samples are
    the limit;
  - GeneralUser GS was "slightly better for both" guitar and banjo.
- **Our two fonts are prototypes cut from exercise takes,** not from
  sessions recorded for sampling:
  - `upright.sf2`: 8 pitches, the rest stretched, one dynamic, notes cut
    where the next was played;
  - `dobro.sf2`: 17 pitches, one dynamic, no strings told apart.
  Both are built by scripts (`tools/samples.py` from `sounds/samples/upright.json`
  since 2026-10-20; dobro-transcription `dobro-soundfont/tools/build.py`,
  with a minimal SF2 writer, `sf2write.py`).
- **What helps:** the transcription pipeline already finds onsets, pitch
  to about a cent, the string a note is on (`fretting`, `timbre`), and a
  guitar's strokes, boom or chuck (`strokes`). The exercise app on the
  control unit records takes over a click and knows where beat 0 is. The
  18i8 records up to 20 channels at 24 bits. `dobro-soundfont/docs/session-sheet.md`
  is a written sampling session (30 takes, about 50 minutes) that has not
  been recorded yet.

## The rule for every step

**Each step ends with something the player hears,** as matched A/B renders
of the same notes (below, "Judging by ear"). No step goes on to the next
until the player has said which is better. A step that does not win is
kept as a candidate, not shipped.

## Instruments and articulations

What each part plays now, what it will play, and so what to sample. "Now"
is what `bandvoice` or the ambient patterns play today; "later" is what
the band's plans name (dobro-transcription `docs/band-that-follows.md`:
the mandolin's chop first, then bass, chords, fills).

| instrument | now | later | to sample |
|---|---|---|---|
| **upright bass** | root and fifth on the beat (E1 to A#2); ambient walk-ups | walks into changes, two-beat and four-beat feels, pickups | every semitone E1 to G3, three dynamics, 2-3 round robins; each let ring and each stopped short (the bluegrass bass note is damped before the next); open strings and the same pitch stopped on the next string down; a few slides into a note |
| **guitar** (Martin D-1) | the strum (six notes); boom-chick and Travis in the ambient synth | boom-chuck with the bass on its string, G runs and bass runs, strums up and down, single-note fills | the boom: single bass notes on strings 6-4, E2 to D3, let ring and damped; the chuck: the band's chord shapes (G, C, D, D7, A, A7, E, Em, Am, B7, F), strummed down on the upper strings and choked, three dynamics, 4 round robins; later full strums down and up, and single notes on every string for runs |
| **banjo** | the chop (stand-in); Scruggs-style rolls in the ambient synth | rolls under the melody, chop, pinches, vamp | every string open and fretted to the 5th fret (rolls stay low), thumb and finger picks, three dynamics, round robins; the same pitch on two strings (exercise 008); chop shapes muted (closed shapes up the neck: the vamp) |
| **mandolin** | nothing (the synth's own mandolin in the ambient synth) | the muted chop first in the band, then open chop, tremolo, fills | chop shapes (G, C, D, A, E closed chop chords), muted and open, down-strokes, 4 round robins, three dynamics; single notes per string down and up strokes for tremolo built from picks; a few tremolo notes as loops to compare |
| **fiddle** | nothing in the band; FluidR3's fiddle in the ambient synth | fills, then long notes under the melody, shuffles, double stops | the hardest: sustained bowed notes with and without vibrato, looped; short shuffle strokes up and down; double stops on the open strings; slides into notes. Needs a fiddler (not the player, so far) |
| **dobro** | the ambient synth's melody, by string, with slides by re-tuning | fills in the band, rolls under the melody, chop with the bar | per string, every fret 0-17, three dynamics (the session sheet); bar noise, slides of 1, 2 and 5 frets, damped endings, harmonics; rolls and chop later |

Articulations fall into three kinds, which decide how they are built:

- **Single notes** (bass, banjo, mandolin and dobro notes, the guitar's
  boom): one sample per pitch, string, dynamic and round robin. The engine
  chooses the note; the font plays it.
- **Chord strokes** (the guitar's chuck and strums, the chop on all three):
  a whole stroke recorded as one sample, keyed by chord shape and
  direction. Built from single strings, a strum sounds like a machine: the
  strings of a real strum touch each other, the pick drags, the hand mutes.
  Strum Machine and RealTracks record whole strokes. So does this plan. The
  cost: a sample per shape, direction, dynamic and round robin (11 shapes x
  1 direction x 3 x 4 = 132 for the guitar's chuck).
- **Sustains with motion** (fiddle bowing, mandolin tremolo, dobro vibrato):
  loops or modelling. Last, because they are the hardest to make sound
  right from samples.

## Sampling sessions with the player's instruments

### What a session records

- **Notes recorded for sampling:** one at a time, from silence, let ring
  until they fade into the room (5-8 s for the dobro and bass; the session
  sheet says how long), or stopped on a count when the sheet asks for a
  short note.
- **Three dynamics** (soft, medium, hard), the player's own, not measured
  in advance. The build measures each note's level and maps the velocity
  ranges to what was played.
- **Round robins:** 2-4 takes of the same note at the same dynamic. They
  matter most for repeated notes: the chop and the chuck (on every 2 and 4),
  the bass on the root.
- **Open and stopped:** the same pitch on two strings where a player would
  use both (exercises 006 and 008 for guitar and banjo already ask for it).
- **The extras that make an instrument real:** damped endings, mutes, pick
  noise alone, bar or finger noise, slides, the release (a string let go).
  Recorded in the first session for each instrument, even if used later:
  setting up again costs more than a few extra minutes.
- **Room tone,** 10 s, at the start and end of each session, with the AC
  off (its fan adds about 10 dB, `dobro-soundfont/docs/next-steps.md`).
- **Tuned to one reference** before each string, written in the session's
  notes.

### Through the 18i8

- 24-bit, 48 kHz, the device's native format, nothing in between: no
  resampling, no gain control, no noise suppression.
- **Two channels at once where it is cheap:** a close mic and the room mic
  (the MXL 990 on input 4), and for the bass the Nadine and the piezo. The
  build chooses, or mixes, later. Both are kept.
- Input gain so the hardest stroke peaks near -12 dBFS. `check_take`
  (below) flags clipping and the noise floor.
- The dobro's 1.0 setup was decided on the FIFINE before the 18i8 arrived.
  Whether the 18i8 with a condenser now beats it is a quick blind test
  (`dobro-soundfont/tools/setup/blind_clips.py`), only if the player wants
  it (question 4).

### The exercise app as the session's guide

The exercise app already shows a score, counts in, plays a click and
records where beat 0 is. A sampling session can be a set of exercises:

- **Each take is a short score:** "E1 to A#2, one note every 4 beats at 60
  bpm, soft" with the string marked in tab. The player reads what to play;
  nothing to remember.
- **The score is the answer key.** Since the take knows its beat 0, the
  extraction knows which note is due when, on which string, at which
  dynamic and in which round robin. Labelling becomes checking.
- **After each take, a check** like `dobro-soundfont/tools/check_take.py`:
  every note heard against the sheet (pitch and tuning, level, how long it
  rang, the room tone, clipping), and what to redo, shown on the page.
- **What is still wanted:** the exercise picker's "needs a take" status
  (`exercises/status.py`) extended to the fonts: which notes, dynamics and
  round robins are missing or rejected. A session then records exactly the
  gaps.
- **Short takes,** a few minutes each, so a bad one is cheap to redo, and a
  session can stop at any take.

## Extraction: from takes to samples

One pipeline for every instrument, built from the transcription
pipeline's parts and the two font scripts that exist. Each stage writes
what it found, so a sample's history is in a file.

1. **Find the notes:** onsets (`detect`, `bass` for the bass, `strokes` for
   guitar strokes), matched to the session's score (`evaluate`), using the
   take's beat 0.
2. **Label them** from the score: pitch, string, dynamic, round robin,
   articulation, stroke direction. Then **check the labels** with the
   detectors: pitch measured to about a cent (pyin, then an interpolated
   spectral peak, as `check_take.py`); the string by its harmonic
   fingerprint (`timbre`); boom or chuck by `strokes`. A note whose
   measurement disagrees with its label goes to a list for the player, not
   into the font.
3. **Cut:** from 3 ms before the pick (the 3-8 kHz click, `find_pick` in the
   dobro build), to where it falls to the room's floor or the score's stop,
   with a short fade. No silence before the pick: the dobro prototype's
   samples spoke 19-54 ms late until this was fixed.
4. **Loop** only what sustains (fiddle, tremolo, a long dobro note if
   wanted): loop points at matching phase and level, checked by ear in a
   10 s render.
5. **Level and tune:** the dynamics keep their measured differences; the
   whole set is matched to one loudness on its medium layer. Tuning goes in
   the sample's pitch correction, not by resampling.
6. **Choose:** the best take per slot by the same rules as
   `upright_font.py` (clean start, long enough, in tune), with the
   candidates kept in a JSON beside the build, so a choice can be changed by
   hand.
7. **Write** a sample map (one entry per sample: file, root, key range,
   velocity range, round robin, string, articulation, loop), and from it
   the font. The map is the source in git; the WAVs live outside git (as the
   dobro's, `~/Dropbox/dobro-soundfont/recordings/`); the builds are
   reproducible from both.

**Built (2026-10-20): `tools/samples.py`,** the generalisation of the
upright's first build and the dobro's `build.py`: `collect`, `report`,
`choose` and `build`, the instrument a profile (`upright`, `guitar`). What
it does beyond the list above, and how:

- **The exercise app's click comes out first.** The takes over a click
  hold it, and through the old mixer (2026-10-13/14) it was recorded
  electrically, as loud as a note: the upright's E1 and G2 of 2026-10-15
  clicked on every note. The click's place comes from the take's sidecar;
  each kind is a median template over the take's clicks, fitted to each by
  a fraction of a sample and a gain (the transcription project's
  `transcribe.click`), and any left over a note's ring is gated to the
  sound around it. Then a check on every cut sample: no 5 ms of 2-8 kHz
  standing 12 dB over its neighbourhood within 35 dB of the note.
- **A take with a key** is transcribed as that project's bench does and
  matched to its key; **a take with a chart** (the guitar's tunes) gives
  its strokes, a boom labelled by its bass note and a chuck by the chart's
  chord, each checked (the boom a chord tone, the chuck's chroma the
  chord's root).
- **The other checks:** a clean start (10 dB over the 50 ms before; a
  stroke's own band's rise), long enough (0.5 s; a boom 0.17, a chuck
  0.09), the pitch (pYIN within 4 semitones of the label, refined from the
  partials, and an octave test), the note before still ringing (its own
  partials within 20 dB), the backing or a voice in the room (a bass's
  1.5-6 kHz within 40 dB of it), the string (`timbre`, one take left out),
  clipping. A sound late in the ring (the hand coming back) ends the cut
  before it. A bowed note gets loop points (a whole number of periods, the
  seam crossfaded) or is flagged.
- **The map is the source** (`sounds/samples/INSTRUMENT.json`, in git), the
  candidates beside it; the WAVs in `~/.cache/ambient-room/samples/`; an
  entry `pinned` is kept by `choose`. The upright's 2026-10-15 samples are
  pinned there, cut as they were: built from them alone, the font is the
  same file byte for byte.

**What the takes in hand give** (the transcription project's findings,
"The band's sounds", has the tables): the bass, 19 of the 28 semitones
E1-G3 through the Nadine on the 18i8 with a clean candidate (282 of 1089),
16 on the piezo, 13 through the old mixer; none on any chain for D#2, A#2,
C#3 and D#3 to G3; most 0.5-0.9 s long (cut by the next note), 4 s only on
the open strings and a few held notes; 25 bowed notes on 8 pitches with a
loop. The guitar: 29 single notes on 15 of the 37 semitones E2-E5, 0.7 s
(1.4-1.5 s on the open B and E and a G4); 99 booms on 8 pitches (G2 33, D3
25, A2 23; a median 0.35 s, rung to the chuck after); 214 chucks across 9 chords as
the tunes play them, 0.1-0.4 s each (A, with the capo at the 2nd fret, 80;
D 48; G 37). Enough for round robins of a chuck; not for a bass or guitar
font of every semitone: the sessions above are still needed.

## SF2 or SFZ, and the engine

**Stay on FluidSynth for now; write fonts from a neutral sample map so SFZ
stays open.**

- **What SF2 in FluidSynth does:** velocity layers, key ranges, envelopes,
  filters, loops. The band and the offline render are bit-identical through
  it, which is what lets A/B renders be trusted.
- **What it lacks, and the workarounds in the engine:**
  - **Round robins.** SF2 has none. The engine rotates among N presets (one
    per round robin) on its own channels. The rotation must be
    deterministic (a counter per part and note, or the voicing's own dice),
    so the live band and the offline render still play the same samples.
  - **Per string.** A preset or a channel per string, chosen by the voicing
    (the dobro already chooses strings, `play_strung`). A channel per string
    also gives each string its own pitch bend for slides.
  - **Articulations** (chop muted or open, let ring or damped, down or up):
    a preset each, chosen by program change or channel. No keyswitches
    needed: the voicing knows what it asks for.
  - **Release samples** (a string let go, a mute): the engine plays a short
    noise sample itself at note-off.
- **What SFZ would add:** round robins and random choice in the format
  (`seq_length`, `lorand`), release triggers, key switches, crossfades
  between layers, legato for the fiddle. sfizz (BSD-2, a C API usable
  through ctypes as `fluid.py` uses FluidSynth) and liquidsfz (LGPL) are
  the candidates. Neither is in this desktop's Debian archive: either would
  be built from source on the control unit too. sfizz's development is
  quiet (dobro-transcription `docs/ecosystem/2026-10-13-accompaniment.md`).
- **When to move:** only when the player hears something the workarounds
  cannot give, most likely the fiddle's legato or crossfaded dynamics. Then
  a spike: the same band part through FluidSynth and sfizz, matched;
  sfizz's CPU and block on the control unit; and whether the offline
  render and the live band stay identical.
- **The ambient synth** plays fonts through Csound's `sfplay3m`, which
  ignores envelopes and filters and needs fonts normalised for Debian's
  Csound bugs (`tools/soundfonts`). As fonts gain layers, round robins and
  envelopes, the ambient synth's sampled voices should move to the band's
  FluidSynth engine, so one font sounds the same in both (question 12).

## Judging by ear

The player's way, from the memory on sound changes: matched renders of the
same notes, before and after, and the player's ear decides.

- **The renders:** the same band part (a tune, a seed, a tempo), rendered
  with the old font and the new, loudness matched (ffmpeg `loudnorm`, the
  same LUFS), 10-25 s each. The dice that only change how notes are played
  stay on their own seed, so only the sound differs.
- **A third clip where one exists: the real instrument** playing the same
  notes. A take with an answer key (guitar exercise 003, the bass's tunes)
  is rendered from its key through each font. "Which is closer to the
  recording?" is a sharper question than "which is better?".
- **Blind where possible:** letters, not names, the order shuffled per
  question, as `dobro-soundfont/tools/setup/blind_clips.py` already does.
  Then revealed.
- **A short form per comparison:**
  - which sounds more like the instrument (or: like the recording);
  - which would you rather play with;
  - anything wrong: late, thin, harsh, clicky, too loud or soft, out of
    tune, the same sample over and over, a wrong note;
  - a line of free text.
- **Where:** the review flow being built on `practice.local` is the natural
  home, so it can be done in the music room on the speakers the band plays
  through. Until then, a page with the clips (as the by-ear question pages
  are made). The verdicts go in a ledger beside the fonts (one row per
  comparison: date, fonts, clips, choice, notes), so a later change can be
  checked against what was said.
- **Simple measurements beside the ear,** never instead of it:
  - **loudness:** each part's level in the band against the old font
    (`tools/band_replay.py levels`), within 0.5 dB, or the trim changed;
  - **attack timing:** from the note's time to its pick in the render
    (under 3 ms, as the dobro's samples now are);
  - **spectrum and decay:** the long-term spectrum and the decay per band
    of a rendered note against the same note in a recording (as
    `dobro-soundfont/tools/setup/measure.py` and the MuseScore spike did);
  - **the round trip:** the render transcribed by the pipeline, against its
    key. Strokes read as the same boom or chuck as a real take's; the
    dobro's strings come back as the strings played. A font that the
    pipeline cannot tell from the instrument is a good sign, not a verdict;
  - **repetition:** for round robins, how different consecutive chops are
    (a spectral distance), so a set does not repeat audibly.

## The steps

Each step ends with A/B renders for the player.

1. **The bass's missing notes, and the guitar's boom-chuck from the D-1.**
   - Before the session: the extraction pipeline, generalised from
     `upright_font.py`, run on the takes we have (the bass's, guitar
     exercises 001-003, the guitar tunes). Shows what is already usable.
     Done 2026-10-20 (`tools/samples.py`; above, "What the takes in hand
     give"); its first use, the upright's clicking E1, waits on the
     player's ear.
   - **The bass:** a session as exercises, every semitone E1 to G3, three
     dynamics, two round robins, let ring 4 s and stopped after one beat,
     through the Nadine and the piezo at once. Fills the stretched notes
     (today 8 sampled pitches) and gives the bass a damped note, which the
     bluegrass bass plays.
   - **The guitar:** single bass notes for the boom (strings 6-4, E2 to D3,
     let ring and damped), and the chuck as whole strokes for the band's
     chord shapes, down, choked, three dynamics, four round robins. A
     strummed chord as one sample needs a change in `bandvoice` (one note per
     chuck, keyed by shape, instead of six), in the transcription project.
   - **Heard:** Down Yonder and Red Wing with the band, old fonts against
     new; the real guitar take of Down Yonder against its key rendered
     through GeneralUser and through the D-1.
2. **The banjo's and the mandolin's chops,** and round robins in the
   engine.
   - Round robins by rotating presets (deterministic), first on the bass and
     guitar from step 1.
   - The banjo: the chop shapes muted and open; single notes for the rolls
     (the eight banjo exercises have no takes yet: they become the session).
   - The mandolin's chop, if a mandolin is at hand (question 2): muted first,
     as the band brings it in first.
   - **Heard:** the chop alone over a click, the GeneralUser banjo against
     each new chop; then the band.
3. **The dobro by string.**
   - The written session (`dobro-soundfont/docs/session-sheet.md`) through
     the 18i8: G2 to G5 on the usual string, eight pitches on a second,
     three dynamics, two each, 8 s rings, then damping, slides, bar and pick
     noise, harmonics.
   - A preset and a channel per string; slides by each string's pitch bend;
     bar noise at slides and lifts played by the engine.
   - **Heard:** the ambient synth's dobro melody and a tune key (Red Wing),
     the prototype against the new font, and against the player's take.
     This is also the dobro-soundfont project's 1.0.
4. **More of what the band will play:** guitar strums down and up, G runs
   and bass runs (single notes on every string), the bass's walks and
   slides, banjo vamp and pinches, mandolin open chop.
5. **The engine question:** a sfizz spike, only if a step above found
   something FluidSynth cannot do.
6. **Sustains:** mandolin tremolo (from repeated picks with round robins,
   against looped tremolo), dobro rolls and vibrato, and the fiddle (a
   contributor's, or a CC0 set if one is good enough; question 2).
7. **Other players' instruments** through the website (below): a second
   guitar, banjo, mandolin, fiddle, as presets of their own.
8. **Publishing 1.0** of each font the player is happy with: generic names
   (below, "Names"), a README with the instrument, the chain and the licence.

Steps 2-4 can change order with what the player has at hand and wants to
hear first.

## Contributors through the website

The website being planned can collect other players' instruments. The
same exercises that test the transcriber can be sampling sessions, so a
contributor's takes serve twice.

- **What a contributor gives:** takes of the sampling exercises (and any
  other exercises), the instrument's details (make, model, strings, tuning,
  mic, interface, room), and their consent.
- **Consent, separately for each use,** in plain words, before upload:
  - their takes used to test and train the transcription;
  - samples cut from their takes published in the project's fonts, under
    the fonts' licence, CC0 (below), which cannot be withdrawn once published;
  - whether and how they are credited (a name, a handle, or none).
  They also confirm the playing and the recording are their own, and that
  nothing comes from a sample library or a record.
- **Recording in a browser** is lossy by default and processed: browsers
  apply echo cancellation, noise suppression and automatic gain unless asked
  not to (`getUserMedia` with all three off), and record Opus. Prefer a
  WAV or FLAC upload from the contributor's own recorder; accept browser
  takes for transcription only.
- **Quality control:**
  - automatic: the format (sample rate, bit depth, no resampling, mono or
    the channels said), clipping, the room's floor against the notes, tuning
    to A440 within a few cents, the extraction's rejects;
  - by ear: the contributor's instrument against the current font, blind,
    in the same form as the player's comparisons;
  - every contributed instrument is a preset of its own, not mixed into
    another's key range: two instruments within one preset change timbre
    from note to note.
- **Names** (decided 2026-10-22): generic, never a maker's (Dobro, Beard,
  Martin and Silvertone are trademarks); the maker and model only in the
  README, as where the samples came from. A font is named by the style it is
  played in and the instrument, since the playing is in the samples: "Bluegrass
  Banjo" (a resonator banjo with fingerpicks, Scruggs style), "Bluegrass
  Guitar" (a dreadnought with a flatpick), "Bluegrass Bass" (the upright as a
  bluegrass bassist plays it), and so on; the same instrument in another style
  would be sampled differently and named for it (the player: "we might sample
  differently for, like Jazz Manouche"). The resonator guitar comes in two, a
  modern one (the Beard; a Rayco or another modern design) and a vintage one
  (the 60D), which sound "pretty different" (the player).

## Licensing

- **The project's own fonts** (from the player's and contributors'
  recordings): CC0 (question 1, decided 2026-10-22; the player: "let's go
  with CC0"; dobro-transcription's card `fonts-release-decisions`), the same
  for every instrument and every contributor's samples, stated before the
  first contributor uploads. The build scripts keep the code's own
  licence.
- **Fonts built from others keep their terms,** and stay in files of their
  own, not merged into ours:
  - GeneralUser GS (the guitar and banjo now): free use and modification,
    its notice kept;
  - FluidR3_GM (fiddle, nylon guitar, harmonica): MIT, its notice kept.
  `sounds/README.md` already records both.
- **The dobro prototype** stays unpublished, as its README says; the 1.0
  from the session replaces it.
- **Contributors' samples** go out only under the stated licence and with
  their consent; the README lists each contributor as they asked.

## Risks

- **Sessions take the player's time and patience.** The player wanted no
  more setup recording for the dobro. Short takes, the exercise app's
  guidance, and recording only the gaps keep sessions small.
- **Sample counts grow fast:** whole strokes per shape, direction, dynamic
  and round robin. Start with the shapes the tunes use (G, C, D, A, E and
  sevenths) and one direction.
- **Memory and CPU on the control unit:** more and longer samples, more
  voices. Measure a font's load size and the engine's response on the unit
  (`tools/band_replay.py`) before deploying, as for the band.
- **The live band and the offline render must stay identical.** Round
  robins, string choice and noise samples on their own seeded dice, or the
  A/B renders stop meaning anything.
- **Old strings.** The D-1 and the Beard have old strings. A font of old
  strings sounds like them for good (question 3).
- **Two repositories.** A new articulation changes `bandvoice` in the
  transcription project and the engine here: both change together, and the
  offline render with them.
- **SFZ players are not packaged in Debian here;** sfizz is quiet. Moving the
  engine is a cost to weigh against what it gives.
- **Contributors' recordings vary** in rooms, mics and tuning: the automatic
  checks reject the worst, the ear the rest.

## Open questions for the player

1. **The fonts' licence:** CC0, for every instrument and every contributor's
   samples (decided 2026-10-22; the player: "CC0 for everything contributed
   to the soundfonts project").
2. **Which instruments are at hand:** which banjo, a mandolin, a fiddle?
   Who would play the fiddle, if anyone here?
3. **Strings:** restring the D-1 and the Beard before sampling, or sample
   them as they sound now?
4. **Mics through the 18i8:** record a close mic and the room mic together
   for every session? The dobro's 1.0 was decided on the FIFINE before the
   18i8; test again, or keep it?
5. **How long a session** is comfortable, and one instrument per session?
6. **Your band or the best band:** should the band be the player's own
   instruments, or whichever sounds best, contributors' included?
7. **Where to judge:** the review flow on `practice.local` through the
   room's speakers, or pages with clips? Blind every time?
8. **Strums as whole strokes** (more samples, more real) rather than built
   from single strings: agreed?
9. **The order after step 1:** chops, then the dobro by string, as above, or
   the dobro first?
10. **The engine:** stay on FluidSynth with workarounds until something
    audibly needs SFZ?
11. **Publishing:** where (Codeberg, GitHub, musescore.org), and when: per
    font at 1.0, or all together?
12. **The ambient synth:** move its sampled voices to the band's FluidSynth
    engine, so one font sounds the same in both?
