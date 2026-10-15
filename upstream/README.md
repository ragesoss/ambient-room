# Upstream reports

Bugs found in other projects while building ambient-room, with what was
sent. All three are in Debian's Csound 6.18.1; see
`../sounds/README.md` for how ambient-room works around them.

- **Pan NaN in the stereo SoundFont players.**
  - Issue: https://github.com/csound/csound/issues/3403 (filed 2026-10-11).
  - Fix: https://github.com/csound/csound/pull/3404, against develop.
    Tested on x86_64 with gcc 15 and `-mfma`: before, NaN on the right
    channel; after, none, and identical output for every other pan.
    Merged 2026-10-12.
  - Test: a reviewer (hlolli) asked for a regression test on #3404. It
    covers `sfplay`, `sfplay3` and `sflooper` at both ends, and pans that
    add up past them, from a 1.3 KB embedded SoundFont. It fails with
    #3404 reverted (gcc 15, `-mfma`) and passes with it. It went in
    #3408 (below). Files:
    `0001-test-sfont-hard-left-and-hard-right-zones-in-the-ste.patch`,
    `make_pan_sf2.py` (writes the SoundFont).
  - Files: `csound-issue-pan-nan.md` (the issue as drafted),
    `csound-pr-pan-nan.md` (the PR text),
    `0001-fix-sfont-clamp-pan-as-an-integer-so-sqrt-never-gets.patch`
    (the PR's commit), `csound-sfont-pan-nan-6.18.1.patch` (the same fix
    for 6.18.1), `sfplay-pan-nan-repro.csd`.
- **Signed tuning fields.** Already fixed upstream (ceaad747), but in no
  6.x release. On develop, coarse tune, fine tune and the root key are
  signed bytes, so an unset root key (-1) falls back to the sample's own
  (checked 2026-10-15).
- **Global-zone values cut to 8 bits** (found 2026-10-12, while writing
  the test above). `sfload` stores an instrument global zone's pan,
  initialAttenuation and scaleTuning through `(BYTE)`: pan -500 becomes
  12, 300 cB becomes 44. Measured the same on develop (759ff03) and
  Debian's 6.18.1, x86_64. Hits FluidR3_GM's Dulcimer, Jazz Guitar and
  Recorder (half of each stereo pair), and Snare Verb in `sf_GMbank.sf2`
  (2 of 5 zones, 26 dB too loud). Not ambient-room's fonts:
  `tools/soundfonts` leaves no such global zone (`scan_global_zones.py`;
  rechecked 2026-10-15 on the current four fonts).
  - Issue: https://github.com/csound/csound/issues/3407 (filed
    2026-10-12, closed by #3408). Scale tuning is cut the same way
    (measured with the PR's test).
  - Fix: https://github.com/csound/csound/pull/3408 (opened and merged
    2026-10-12), with the pan-endpoint test above, the fix (cast to
    `SHORT`), and a test that each global value plays as the same value
    in the sample's own zone. Both tests fail without their fix and pass
    with it.
  - Files: `csound-issue-global-zone-cast.md` (the issue as filed),
    `csound-pr-pan-global-zones.md` (the PR text, title on the first
    line), `0002-fix-sfont-keep-global-zone-pan-attenuation-and-scale.patch`,
    `make_global_sf2.py` (the issue's repro SoundFont),
    `make_global_zones_sf2.py` (the test's SoundFont),
    `scan_global_zones.py` (lists affected instruments in a font).

All three fixes are on Csound's develop branch, for Csound 7. No release
has #3404 or #3408 yet: the latest, 7.0.0-beta.18, is from 2026-10-01
(checked 2026-10-15). Debian (6.18.1 in every release, 2026-10-11) gets
them when it packages Csound 7. Not reported to Debian: anyone who needs
them sooner can backport the commits.
