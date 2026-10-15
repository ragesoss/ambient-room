sfload: global-zone pan, initialAttenuation and scaleTuning are cut to 8 bits

I started looking at the regression test @hlolli suggested on #3404, and Claude turned up a related bug that can surface with specific SoundFonts and how they use the pan and other settings. PR that includes a fix for this one, and a regression test for this and #3403 will be incoming shortly.

-ragesoss

## AI bug report (Claude Opus 5.5)

When an instrument's global zone sets `pan`, `initialAttenuation` or `scaleTuning`, `sfload` stores the value through a `(BYTE)` cast, so only the low 8 bits are kept. The same generators in a sample's own zone are stored unchanged, and the fields are `SHORT` (`Opcodes/sf.h`). Both loaders in `Opcodes/sfont.c` do this: the preset one (`sfplay`, `sflooper` and the rest) and the instrument one (`sfinstr` and the rest).

```c
if (GscaleTuning != UNUSE)
  split->scaleTuning = (BYTE) GscaleTuning;
if (Gpan != UNUSE)
  split->pan = (BYTE) Gpan;
...
if (GinitialAttenuation != UNUSE)
  split->initialAttenuation = (BYTE) GinitialAttenuation;
```

So a global pan of -500 (hard left) becomes 12, just right of centre, and +500 becomes 244. An attenuation of 300 cB becomes 44 cB, 26 dB too loud. A scale tuning above 255 cents per key wraps around (1200 becomes 176).

Common fonts hit it:

- **FluidR3_GM:** Dulcimer, Jazz Guitar and Recorder each pair a sample panned in its own zone with one that inherits a global pan of ±500. The inherited half plays at 12 or 244 instead of hard left or right.
- **`sf_GMbank.sf2`:** Snare Verb has a global attenuation of 358 cB. Two of its five zones inherit it and play 26 dB too loud.

Develop (759ff03) and Debian's 6.18.1, both on x86_64, give the same numbers.

<details>
<summary>Repro and results</summary>

The embedded SoundFont has one constant, looped sample and six instruments, each with a preset of the same number. Each global-zone instrument has a twin that sets the same value in the sample's own zone, which shows the expected result.

```csound
<CsoundSynthesizer>
<CsOptions>
-n -d -m0
</CsOptions>
<CsFileB filename="global.sf2">
UklGRsYFAABzZmJrTElTVDYAAABJTkZPaWZpbAQAAAACAAEAaXNuZwgAAABFTVU4MDAwAElOQU0N
AAAAR2xvYmFsIHpvbmVzAABMSVNUaAIAAHNkdGFzbXBsXAIAAAAQABAAEAAQABAAEAAQABAAEAAQ
ABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAA
EAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQ
ABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAA
EAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQ
ABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAA
EAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQ
ABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAA
EAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQ
ABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAABMSVNUDAMAAHBkdGFwaGRyCgEAAEdsb2JhbCBwYW4gLTUwMAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAWm9uZSBwYW4gLTUwMAAAAAAAAAABAAAAAQAAAAAAAAAAAAAAAABHbG9i
YWwgcGFuICs1MDAAAAAAAAIAAAACAAAAAAAAAAAAAAAAAFpvbmUgcGFuICs1MDAAAAAAAAAAAwAA
AAMAAAAAAAAAAAAAAAAAR2xvYmFsIGF0dGVuIDMwMAAAAAAEAAAABAAAAAAAAAAAAAAAAABab25l
IGF0dGVuIDMwMAAAAAAAAAUAAAAFAAAAAAAAAAAAAAAAAEVPUAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAYAAAAAAAAAAAAAAAAAcGJhZxwAAAAAAAAAAQAAAAIAAAADAAAABAAAAAUAAAAGAAAAcG1vZAoA
AAAAAAAAAAAAAAAAcGdlbhwAAAApAAAAKQABACkAAgApAAMAKQAEACkABQAAAAAAaW5zdJoAAABH
bG9iYWwgcGFuIC01MDAAAAAAAAAAWm9uZSBwYW4gLTUwMAAAAAAAAAACAEdsb2JhbCBwYW4gKzUw
MAAAAAAAAwBab25lIHBhbiArNTAwAAAAAAAAAAUAR2xvYmFsIGF0dGVuIDMwMAAAAAAGAFpvbmUg
YXR0ZW4gMzAwAAAAAAAACABFT0kAAAAAAAAAAAAAAAAAAAAAAAkAaWJhZygAAAAAAAAAAQAAAAMA
AAAGAAAABwAAAAkAAAAMAAAADQAAAA8AAAASAAAAaW1vZAoAAAAAAAAAAAAAAAAAaWdlbkwAAAAR
AAz+NgABADUAAAARAAz+NgABADUAAAARAPQBNgABADUAAAARAPQBNgABADUAAAAwACwBNgABADUA
AAAwACwBNgABADUAAAAAAAAAc2hkclwAAABDb25zdGFudAAAAAAAAAAAAAAAAAAAAAAAAQAACAAA
APgAAAAABAAAPAAAAAEARU9TAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAA==
</CsFileB>
<CsInstruments>
sr = 1024
ksmps = 1
nchnls = 2
0dbfs = 1
; One constant, looped sample. Preset and instrument n are the same:
;   0: global zone pan -500           1: sample zone pan -500
;   2: global zone pan +500           3: sample zone pan +500
;   4: global zone attenuation 300 cB 5: sample zone attenuation 300 cB
giSF sfload "global.sf2"
sfpassign 0, giSF, 0
instr 1 ; p4: preset and instrument
  aL, aR sfplay 100, 60, 1, 0, p4, 0, 16
  aM sfplaym 100, 60, 1, 0, p4, 0, 16
  aIL, aIR sfinstr 100, 60, 1, 0, p4, giSF, 0, 16
  printks "%d: sfplay L %7.1f R %7.1f, sfplaym %7.1f, sfinstr L %7.1f R %7.1f\n", 1, p4, k(aL), k(aR), k(aM), k(aIL), k(aIR)
  turnoff
endin
</CsInstruments>
<CsScore>
i 1 0 .01 0
i 1 + . 1
i 1 + . 2
i 1 + . 3
i 1 + . 4
i 1 + . 5
</CsScore>
</CsoundSynthesizer>
```

Output, the same on develop and 6.18.1:

```
0: sfplay L   858.4 R   879.3, sfplaym  1228.8, sfinstr L   599.7 R   629.1
1: sfplay L  1228.8 R     0.0, sfplaym  1228.8, sfinstr L  1228.8 R     0.0
2: sfplay L   621.7 R  1059.9, sfplaym  1228.8, sfinstr L   314.6 R   914.2
3: sfplay L     0.0 R  1228.8, sfplaym  1228.8, sfinstr L     0.0 R  1228.8
4: sfplay L   522.6 R   522.6, sfplaym   739.1, sfinstr L   369.6 R   369.6
5: sfplay L    27.2 R    27.2, sfplaym    38.4, sfinstr L    19.2 R    19.2
```

Rows 0, 2 and 4 should match rows 1, 3 and 5.

</details>
