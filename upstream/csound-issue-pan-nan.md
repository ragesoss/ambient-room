sfplay, sfplay3, sflooper: right channel NaN at pan -500 in gcc -ffast-math builds (arm64)

On Debian's Csound 6.18.1 for arm64 (Raspberry Pi 3, gcc 14, `-O3 -ffast-math`), `sfplay`, `sfplay3` and `sflooper` give NaN on the right channel for the whole note when a zone's pan is exactly -500 (hard left). The mono opcodes are fine, and so is x86_64. In FluidR3_GM this affects every preset built from stereo samples (112 of 189).

The cause is in `SfPlay_set()` and `sflooper_init()` in `Opcodes/sfont.c`. The code is unchanged on develop:

```c
pan = (cs_double)(split->pan + layer->pan) / 1000.0 + 0.5;
if (pan > 1.0) pan = 1.0;
else if (pan < 0.0) pan = 0.0;
...
p->rightlevel[spltNum] = (cs_float) sqrt(pan) * attenuation;
```

With `-ffast-math`, gcc makes two changes here:

- It fuses `/ 1000.0 + 0.5` into one multiply-add with 0.001.
- It turns the clamp into an integer test (`sum < -500`).

For a sum of -500, the fused result is -1.04e-17. The clamp misses it, and `sqrt()` gives NaN.

gcc 15 on x86_64 with `-mfma` does the same. Building with `-O2`, or adding `-ffp-contract=off`, avoids it; clang does not show it. `cmake/CompilerOptimizations.cmake` adds `-ffast-math` by default, so other gcc builds on FMA hardware may be affected too.

<details>
<summary>Repro and results</summary>

This uses Csound's `sf_GMbank.sf2`. In its GM drum kit, keys 80 and 81 are panned -500 and key 38 is centred.

```csound
<CsoundSynthesizer>
<CsOptions>
-n -d -m0
</CsOptions>
<CsInstruments>
sr = 48000
ksmps = 32
nchnls = 2
0dbfs = 1
giSF sfload "sf_GMbank.sf2"
giKit sfpreset 0, 128, giSF, 0
instr 1 ; p4 key, p5 0: sfplay, 1: sfplay3, 2: sfplaym
  kNaNL init 0
  kNaNR init 0
  kN init 0
  if p5 == 0 then
    aL, aR sfplay 100, p4, 0.5/32768, 1, giKit
  elseif p5 == 1 then
    aL, aR sfplay3 100, p4, 0.5/32768, 1, giKit
  else
    aL sfplaym 100, p4, 0.5/32768, 1, giKit
    aR = aL
  endif
  kL = k(aL)
  kR = k(aR)
  kN += 1
  kNaNL += (kL != kL ? 1 : 0)
  kNaNR += (kR != kR ? 1 : 0)
  if lastcycle() == 1 then
    printks "key %d opcode %d: k-cycles %d, NaN in left %d, NaN in right %d\n", 0, p4, p5, kN, kNaNL, kNaNR
  endif
endin
</CsInstruments>
<CsScore>
i1 0.0 0.3 38 0
i1 0.5 0.3 80 0
i1 1.0 0.3 81 0
i1 1.5 0.3 80 1
i1 2.0 0.3 81 1
i1 2.5 0.3 80 2
e 3
</CsScore>
</CsoundSynthesizer>
```

These are the k-cycles with NaN on the right channel, out of 451. The left channel has none in any case.

| key | opcode | x86_64 | arm64 |
|---|---|---|---|
| 38 (centre) | sfplay | 0 | 0 |
| 80 (pan -500) | sfplay | 0 | 122 (all of the sample) |
| 81 (pan -500, looped) | sfplay | 0 | 451 |
| 80 | sfplay3 | 0 | 122 |
| 81 | sfplay3 | 0 | 451 |
| 80 | sfplaym | 0 | 0 |

</details>

I'll follow up with a PR.

I found this while debugging a Raspberry Pi project. I used Claude (Anthropic's AI assistant) for the investigation and this write-up, and I checked it before posting.
