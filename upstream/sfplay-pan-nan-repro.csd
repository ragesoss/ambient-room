<CsoundSynthesizer>
<CsOptions>
-n -d -m0
</CsOptions>
<CsInstruments>
; sfplay/sfplay3: right channel all NaN for zones panned hard left (pan -500)
; Seen with Debian's Csound 6.18.1 on arm64 (gcc 14, -ffast-math).
; Uses Csound's own sf_GMbank.sf2 (Debian: package csound-soundfont).
; GM drum kit (bank 128, program 0): key 80 Mute Triangle, key 81 Open
; Triangle are panned -500 in that font; key 38 (snare) is centred.
sr = 48000
ksmps = 32
nchnls = 2
0dbfs = 1

giSF sfload "/usr/share/sounds/sf2/sf_GMbank.sf2"
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
