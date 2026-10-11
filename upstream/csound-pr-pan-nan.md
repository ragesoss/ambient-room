Fixes #3403.

`SfPlay_set()` and `sflooper_init()` now clamp the pan sum as an integer, then take `sqrt((500 - ipan) / 1000.0)` and `sqrt((500 + ipan) / 1000.0)`. Neither argument can be negative, however the compiler contracts the arithmetic.

I tested this on x86_64 with gcc 15.2: a Release build of develop (3d4e795) with `-mfma` added, so `-O3 -ffast-math -mavx2 -mfma`.

- **Before:** the repro in #3403 gives NaN on the right channel for keys 80 and 81, with both `sfplay` and `sfplay3`. Rendering all 61 keys of the `sf_GMbank.sf2` drum kit gives NaN on the right with both `sfplay` and `sflooper`.
- **After:** no NaN.
  - Wherever the old build gave finite output, the new one is identical, sample for sample (1.6 M frames).
  - Notes panned -500 now play hard left, with the right channel at exactly 0.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
