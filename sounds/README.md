# Sounds

The SoundFonts behind the sampled voices (`ambient/samples.py`). The `.sf2`
files are not in git: `tools/soundfonts` builds them here, and
`tools/deploy` copies them to the Pi.

- `acoustic.sf2` (9.1 MB): six presets copied out of FluidR3_GM (Debian's
  `fluid-soundfont-gm`, 141 MB): fiddle (110), banjo (105), steel-string
  guitar (25), nylon-string guitar (24), acoustic bass (32), harmonica (22).
  - Copyright © 2000-2002, 2008 Frank Wen; © 2008 Toby Smithe. Released
    under the MIT licence: "Permission is hereby granted, free of charge,
    to any person obtaining a copy of this software and associated
    documentation files ..., to deal in the Software without restriction
    ..., subject to the following conditions: The above copyright notice
    and this permission notice shall be included in all copies or
    substantial portions of the Software." (The full text is in
    `/usr/share/doc/fluid-soundfont-gm/copyright` on Debian.)
- `dobro.sf2` (3.9 MB): the player's own Beard squareneck resonator guitar,
  17 sampled pitches, from `~/play/dobro-transcription/dobro-soundfont`
  (`build/BeardDobroPrototype.sf2`). A prototype, not for publication.

Measured, 2026-10-11:

- **Cost:** a busy band of these voices (488 notes in 20 s) took 5% of
  one core on the Pi, against 25% for the synthesized Bluegrass mood.
  Loading all of FluidR3 took the process to about 180 MB; the subset
  loads in a few MB.
- **How they behave** (no font envelope; Csound's would silence the looped
  presets): fiddle and harmonica sustain as long as the note; the guitars,
  banjo and bass die away and then hold a quiet loop 14-30 dB down, so each
  has a fade (`decay` in `ambient/samples.py`); the dobro dies away to
  silence by itself.
- **Loudness:** trimmed to the synthesized voices' levels in two passes of
  `tools/calibrate` (scattered melody -37 dBFS, phrases -30, chords -27,
  rhythm part -33, bass with Eighths -24.5).
- **Cost with the band, on the Pi** (20 s offline renders, after the
  deploy): Bluegrass 17% of one core (25% when it was synthesized), Folk
  song 14%, Country 28%, Bluegrass with the dobro 25%. No NaN.

## The Pi's Csound and SoundFonts

Debian's Csound 6.18.1 on the Pi (aarch64) has two SoundFont bugs that
the desktop (x86_64) does not show. Found and worked around 2026-10-11:

- **Stereo players give NaN** (`sfplay`, `sfplay3`, `sflooper`) on the
  right channel for zones panned hard left, as FluidR3's stereo samples
  are. gcc's fast-math turns the pan law into a fused multiply-add that
  comes out a hair below zero. Reported as csound/csound#3403; the fix is
  PR #3404. Workaround: the voices play through the mono `sfplay3m`, and
  we place them in the stereo field ourselves.
- **Tuning fields read as unsigned chars.** A negative fine tune plays up
  to 2.56 semitones sharp. A zone with no root key reads past a table:
  NaN, or an endless loop that froze the synthesis (with the upright bass
  on the Acid line). Fixed upstream (commit ceaad747), but not in any 6.x
  release. Workaround: `tools/soundfonts` normalises every font (explicit
  root keys, no negative tuning). It sounds the same in any player.

So a new font must go through `tools/soundfonts`, and the sampled voices
stay on `sfplay3m`, until the Pi runs a Csound with both fixes.
`../upstream/` holds the reports and patches.
