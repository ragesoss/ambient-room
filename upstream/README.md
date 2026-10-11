# Upstream reports

Bugs found in other projects while building ambient-room, with what was
sent. Both are in Debian's Csound 6.18.1 on the Pi (aarch64); see
`../sounds/README.md` for how ambient-room works around them.

- **Pan NaN in the stereo SoundFont players.**
  - Issue: https://github.com/csound/csound/issues/3403 (filed 2026-10-11).
  - Fix: https://github.com/csound/csound/pull/3404, against develop.
    Tested on x86_64 with gcc 15 and `-mfma`: before, NaN on the right
    channel; after, none, and identical output for every other pan.
  - Files: `csound-issue-pan-nan.md` (the issue as drafted),
    `csound-pr-pan-nan.md` (the PR text),
    `0001-fix-sfont-clamp-pan-as-an-integer-so-sqrt-never-gets.patch`
    (the PR's commit), `csound-sfont-pan-nan-6.18.1.patch` (the same fix
    for 6.18.1), `sfplay-pan-nan-repro.csd`.
- **Signed tuning fields.** Already fixed upstream (ceaad747), but in no
  6.x release.

Both fixes are in Csound's source, for Csound 7. Debian (6.18.1 in every
release, 2026-10-11) gets them when it packages Csound 7. Not reported to
Debian: anyone who needs them sooner can backport the commits.
