fix(sfont): keep global-zone values at 16 bits; regression tests for #3403 and #3407

Fixes #3407, and adds the regression test @hlolli suggested on #3404 ([comment](https://github.com/csound/csound/pull/3404#discussion_r4245128343)).

Two commits:

1. **test(sfont): hard-left and hard-right zones in the stereo players.** `test_sfplay_pan_endpoints.csd` plays `sfplay`, `sfplay3` and `sflooper` from a tiny embedded SoundFont at pan -500 and +500, and with preset and instrument pans that add up past either end. Both channels must stay finite, the far channel exactly 0, and the near channel at the zone's full level.
2. **fix(sfont): keep global-zone pan, attenuation and scale tuning at 16 bits.** Both loaders now cast these to `SHORT`, the fields' type, instead of `BYTE`. `test_sfload_global_zones.csd` plays each global value against a twin instrument that sets the same value in the sample's own zone, through `sfplay` and `sfinstr`. The outputs must be identical.

I tested on x86_64 with gcc 15.2: a Release build of develop (759ff03) with `-mfma` added.

- **This branch:** both new tests pass, and so do the other SoundFont tests.
- **`test_sfplay_pan_endpoints`** fails with #3404 reverted (right channel NaN at -500), and with only its integer clamp removed (the -800 preset).
- **`test_sfload_global_zones`** fails on develop: all four pairs differ from their twins.
- **The full CSD suite:** 1114 passed and 4 failed. The same 4 fail without this change, because of my build: the three `deconv` tests need the utilities, which I didn't build, and `test_pinker_sequence` differs in the fifth digit.

Builds that don't fuse the pan arithmetic (gcc without FMA, clang) pass the pan-endpoint test with or without #3404, because -500/1000.0 + 0.5 is exactly 0 there. On those builds the test still covers the clamp.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
