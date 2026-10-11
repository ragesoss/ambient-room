; The engine's instruments. Python (ambient/engine.py) loads this, sets the
; controls through channels (0-1 each) and schedules every note.
;
; Instrument numbers, by layer (ambient/sounds.py names them):
;   11-17 pad, 21-25 bass, 31-37 and 70-82 melody, 41-45 texture (held notes),
;   51-53 pulse, 61-66 drums, 2 sidechain, 98 echo, 99 reverb and output.
; The drums have their own bus: not ducked, little reverb. Each kick ducks
; everything else (the "pump").
; Notes: p4 Hz, p5 level, p6 attack s, p7 release s (where used).
; Pad and bass notes carry p8, their chord's number: when the "gen" channel
; passes it, the note fades out in 2 s (a new key, tuning or voice).
; Every layer has a level channel; every control glides.

sr = 48000
ksmps = 128
nchnls = 2
0dbfs = 1

seed 0

giSine ftgen 0, 0, 16384, 10, 1
giOrgSoft ftgen 0, 0, 16384, 10, 1, 0.35, 0.1, 0.05
giOrgBright ftgen 0, 0, 16384, 10, 1, 0.6, 0.45, 0.3, 0.2, 0.15, 0.1, 0.08

gaDryL init 0
gaDryR init 0
gaWetL init 0
gaWetR init 0
gaEchoL init 0
gaEchoR init 0
gaDrumL init 0
gaDrumR init 0

chn_k "volume", 1
chn_k "fade", 1
chn_k "fade_s", 1
chn_k "gain_db", 1
chn_k "bright", 1
chn_k "motion", 1
chn_k "space", 1
chn_k "echo", 1
chn_k "echo_s", 1
chn_k "pad", 1
chn_k "bass", 1
chn_k "melody", 1
chn_k "texture", 1
chn_k "pulse", 1
chn_k "gen", 1
chn_k "drums", 1
chn_k "pump", 1
chn_k "drive", 1
chn_k "beat", 1

gkVol init 0
gkFade init 0
gkGain init 1
gkBright init 0
gkMotion init 0
gkSpace init 0
gkEcho init 0
gkEchoS init 0.5
gkPad init 0
gkBass init 0
gkMel init 0
gkTex init 0
gkPulse init 0
gkDrums init 0
gkPump init 0
gkDrive init 0
gkBeat init 0.75
gkDuck init 1
gkKick init 0

alwayson 1
alwayson 2
alwayson 98
alwayson 99

instr 1 ; the controls, glided
  gkVol lineto chnget:k("volume"), 3
  gkFade lineto chnget:k("fade"), chnget:k("fade_s")
  gkGain = ampdb(chnget:k("gain_db"))
  gkBright lineto chnget:k("bright"), 4
  gkMotion lineto chnget:k("motion"), 4
  gkSpace lineto chnget:k("space"), 4
  gkEcho lineto chnget:k("echo"), 4
  gkEchoS lineto chnget:k("echo_s"), 6
  gkPad lineto chnget:k("pad"), 3
  gkBass lineto chnget:k("bass"), 3
  gkMel lineto chnget:k("melody"), 3
  gkTex lineto chnget:k("texture"), 3
  gkPulse lineto chnget:k("pulse"), 3
  gkDrums lineto chnget:k("drums"), 2
  gkPump lineto chnget:k("pump"), 1
  gkDrive lineto chnget:k("drive"), 1
  gkBeat = max(chnget:k("beat"), 0.2)
endin

instr 2 ; sidechain: each kick ducks the rest, which recovers over a third of a beat
  kLast init 0
  kD init 0
  if gkKick != kLast then
    kD = gkPump * 0.8
    kLast = gkKick
  endif
  kD = kD * exp(-ksmps / (sr * gkBeat * 0.3))
  gkDuck = 1 - kD
endin

; A smooth rise, hold and fall over the note.
opcode Env, k, iii
  iAtt, iSus, iRel xin
  kE linseg 0, iAtt, 1, iSus, 1, iRel, 0
  xout kE * kE * (3 - 2 * kE)
endop

; 1 until the note's chord is replaced, then down to 0 over 2 s.
opcode Cut, k, i
  iGen xin
  kK init 1
  if chnget:k("gen") > iGen then
    kK = max:k(kK - 1 / (kr * 2), 0)
  endif
  xout kK
endop

; Into the mix: dry, reverb send, echo send.
opcode Send, 0, aakkk
  aL, aR, kDry, kWet, kEcho xin
  gaDryL += aL * kDry
  gaDryR += aR * kDry
  gaWetL += aL * kWet
  gaWetR += aR * kWet
  gaEchoL += aL * kEcho
  gaEchoR += aR * kEcho
endop

; The level a struck instrument plays at: the melody's (p6 0), the rhythm
; part's (1) or the chords' (2), so one instrument can serve each part.
opcode Lvl, k, i
  iWho xin
  if iWho == 1 then
    kL = gkPulse
  elseif iWho == 2 then
    kL = gkPad
  else
    kL = gkMel
  endif
  xout kL
endop

; Mono to a fixed place in the stereo field.
opcode Place, aa, ai
  aS, iPan xin
  xout aS * sqrt(1 - iPan), aS * sqrt(iPan)
endop

; ---- pad ----

instr 11 ; Warm: detuned saws, filtered
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kRate = 0.05 + gkMotion * 0.4
  kDet = 0.002 + gkMotion * 0.004
  a1 vco2 1, p4 * (1 + jspline:k(0.003, kRate, kRate * 2))
  a2 vco2 1, p4 * (1 + kDet + jspline:k(0.003, kRate, kRate * 2))
  a3 vco2 1, p4 * (1 - kDet + jspline:k(0.003, kRate, kRate * 2)), 12
  aM = (a1 + a2 + a3 * 0.6) / 2.6
  kCut = p4 * (1.2 + 9 * gkBright * gkBright) * (1 + jspline:k(0.3, kRate * 0.5, kRate) * gkMotion)
  aF butterlp aM, limit(kCut, 150, 9000)
  aL, aR Place aF * kE * p5 * gkPad, random:i(0.15, 0.85)
  Send aL, aR, 1, 1, 0.2
endin

instr 12 ; Glass: soft FM
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kRate = 0.05 + gkMotion * 0.4
  kIdx = 0.2 + 1.8 * gkBright * gkBright + jspline:k(0.4, kRate, kRate * 2) * gkMotion
  kIdx limit kIdx, 0.05, 3
  a1 foscili 1, p4, 1, 2, kIdx, giSine
  a2 foscili 1, p4 * 1.003, 1, 3, kIdx * 0.5, giSine
  aS = (a1 * 0.6 + a2 * 0.4) * (1 + 0.2 * gkMotion * oscili:k(1, 0.2 + gkMotion, giSine))
  aL, aR Place aS * kE * p5 * gkPad, random:i(0.15, 0.85)
  Send aL, aR, 1, 1, 0.2
endin

instr 13 ; Choir: saws through vowel formants, drifting between "ah" and "oo"
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kVib oscili 0.004, random:i(4, 5.5), giSine
  kVib = kVib * linseg:k(0, 1.5, 0, 1.5, 1)
  kRate = 0.05 + gkMotion * 0.3
  a1 vco2 1, p4 * (1 + kVib + jspline:k(0.002, kRate, kRate * 2))
  a2 vco2 1, p4 * (1.004 - kVib * 0.5 + jspline:k(0.002, kRate, kRate * 2))
  aS = (a1 + a2) * 0.5
  kM limit 0.5 + jspline:k(0.5, kRate, kRate * 2), 0, 1
  aF1 butterbp aS, 700 - 400 * kM, 90
  aF2 butterbp aS, 1220 - 350 * kM, 110
  aF3 butterbp aS, 2600 - 360 * kM, 140
  aV = aF1 + aF2 * 0.6 + aF3 * 0.3 * (0.3 + gkBright)
  aL, aR Place aV * kE * p5 * gkPad, random:i(0.15, 0.85)
  Send aL, aR, 1, 1, 0.2
endin

instr 14 ; Organ: drawbar tones, soft to bright, with a slow tremolo
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kTrem = 1 + 0.15 * gkMotion * oscili:k(1, 0.7 + gkMotion * 4, giSine)
  a1 oscili 1, p4, giOrgSoft
  a2 oscili 1, p4 * 1.002, giOrgBright
  aO = (a1 * (1 - gkBright) + a2 * gkBright) * kTrem
  aL, aR Place aO * kE * p5 * gkPad, random:i(0.15, 0.85)
  Send aL, aR, 1, 1, 0.2
endin

instr 15 ; Air: breath tuned to the note, over a soft triangle
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  aN rand 1, random:i(0, 1)
  aB1 butterbp aN, p4, p4 * 0.015
  aB2 butterbp aN, p4 * 2, p4 * 0.03
  aT vco2 1, p4, 12
  aT butterlp aT, p4 * 2
  aS = (aB1 * 6 + aB2 * 3) * (0.4 + gkBright) + aT * 0.3
  aL, aR Place aS * kE * p5 * gkPad, random:i(0.15, 0.85)
  Send aL, aR, 1, 1, 0.2
endin

instr 16 ; Synth stab: a short, bright chord hit. p4 Hz, p5 level, p6 (unused), p7 decay s
  aEnv expseg 0.001, 0.004, 1, p7, 0.06, max(p3 - p7 - 0.004, 0.01), 0.001
  a1 vco2 1, p4 * 1.004
  a2 vco2 1, p4 * 0.996
  a3 vco2 0.6, p4, 10
  kCut expseg p4 * (3 + 12 * i(gkBright)), p7, p4 * 1.5, max(p3 - p7, 0.01), p4 * 1.2
  aF butterlp (a1 + a2 + a3) / 2.6, limit(kCut, 150, 14000)
  aL, aR Place aF * aEnv * p5 * gkPad, random:i(0.25, 0.75)
  Send aL, aR, 0.9, 0.45, 0.4
endin

instr 17 ; Supersaw: five detuned saws, held. p4 Hz, p5 level, p6 attack, p7 release, p8 chord
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kDet = 0.005 + 0.008 * gkMotion
  a1 vco2 1, p4
  a2 vco2 1, p4 * (1 + kDet)
  a3 vco2 1, p4 * (1 - kDet)
  a4 vco2 1, p4 * (1 + kDet * 2.1)
  a5 vco2 1, p4 * (1 - kDet * 1.9)
  aF butterlp (a1 + a2 + a3 + a4 + a5) / 4, limit(p4 * (2 + 14 * gkBright * gkBright), 200, 12000)
  aF butterhp aF, 110
  aL, aR Place aF * kE * p5 * gkPad, random:i(0.2, 0.8)
  Send aL, aR, 1, 0.8, 0.2
endin

instr 18 ; Strings: a section: four detuned saws, a slow swell, vibrato, a bowed body. p4 Hz, p5 level, p6 attack, p7 release, p8 chord
  kE Env max(p6, 0.25), max(p3 - max(p6, 0.25) - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kVib = oscili:k(0.0035, random:i(4.6, 5.6), giSine) * linseg:k(0, 0.6, 1)
  kDet = 0.004 + 0.004 * gkMotion
  a1 vco2 1, p4 * (1 + kVib)
  a2 vco2 1, p4 * (1 + kDet - kVib * 0.7)
  a3 vco2 1, p4 * (1 - kDet + kVib * 0.5)
  a4 vco2 1, p4 * (1 + kDet * 0.4 - kVib)
  aM = (a1 + a2 + a3 + a4) / 4
  aB1 butterbp aM, 450, 250
  aB2 butterbp aM, 1600, 900
  aF butterlp aM * 0.5 + aB1 * 0.9 + aB2 * 0.6, limit(p4 * (3 + 8 * gkBright), 400, 9000)
  aF butterhp aF, 90
  aL, aR Place aF * kE * p5 * gkPad, random:i(0.2, 0.8)
  Send aL, aR, 1, 0.9, 0.15
endin

; ---- bass: p4 Hz, p5 level, p6 attack, p7 release, p8 chord, p9 accent 0-1 ----

instr 21 ; Sub: a sine and a little octave
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  a1 oscili 1, p4, giSine
  a2 oscili 0.2 + 0.2 * gkBright, p4 * 2, giSine
  aS = (a1 + a2) * kE * p5 * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.2, 0
endin

instr 22 ; Soft: a filtered saw
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  a1 vco2 1, p4
  a1 butterlp a1, p4 * (2 + 4 * gkBright)
  aS = a1 * kE * p5 * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.2, 0
endin

instr 23 ; Fifths: root and fifth, slowly beating
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  a1 oscili 1, p4, giSine
  a2 oscili 0.6, p4 * 1.5, giSine
  a3 oscili 0.5, p4 + 0.3 + 0.5 * gkMotion, giSine
  aS = (a1 + a2 + a3) / 2 * kE * p5 * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.3, 0
endin

instr 24 ; Synth: a sine and a filtered saw; the filter opens on accents
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kD expseg 1, 0.35, 0.55, max(p3 - 0.35, 0.01), 0.5
  kFE expseg 1, 0.2, 0.1, max(p3 - 0.2, 0.01), 0.1
  a1 oscili 1, p4, giSine
  a2 vco2 0.5, p4
  a2 butterlp a2, limit(p4 * (2 + 6 * gkBright) * (1 + 3 * p9 * kFE), 60, 8000)
  aS = (a1 + a2) * kD * kE * p5 * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.1, 0.1
endin

instr 25 ; Acid: a saw through a resonant, distorting low-pass, its cutoff swept per note
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kD expseg 1, max(p3, 0.02), 0.05
  kFE expseg 1, min(p3 * 0.9, 1.5), 0.05, max(p3 * 0.1, 0.01), 0.05
  kCut = p4 * (1.5 + 6 * gkBright + 22 * p9 * kFE)
  aS vco2 1, p4
  aF lpf18 aS, limit(kCut, 60, 9000), 0.7 + 0.2 * p9, 0.35
  aOut = aF * kD * kE * p5 * gkBass
  Send aOut * 0.7, aOut * 0.7, 1, 0.15, 0.3
endin

instr 26 ; Electric: a fingered bass: saw and square through a filter closing as the string decays
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kD expseg 1, 1.6, 0.35, max(p3 - 1.6, 0.01), 0.25
  kFE expseg 1, 0.12, 0.25, max(p3 - 0.12, 0.01), 0.2
  a1 vco2 1, p4
  a2 vco2 0.6, p4, 10
  a3 oscili 0.8, p4, giSine
  aF butterlp (a1 + a2) * 0.5, limit(p4 * (2.5 + 4 * gkBright) * (1 + 3 * kFE * (0.5 + p9)), 80, 5000)
  aS = (aF + a3) * kD * kE * p5 * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.1, 0.05
endin

instr 27 ; Upright: a plucked double bass: a woody thump, a round tone, a quick decay
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kD expseg 1, 0.9, 0.15, max(p3 - 0.9, 0.01), 0.08
  a1 oscili 1, p4, giSine
  a2 oscili expseg:a(0.4, 0.2, 0.05, max(p3 - 0.2, 0.01), 0.02), p4 * 2, giSine
  a3 oscili expseg:a(0.25, 0.08, 0.01, max(p3 - 0.08, 0.01), 0.005), p4 * 3.01, giSine
  aN rand 1, random:i(0, 1)
  aN butterbp aN, 180, 140
  aT = aN * expseg:a(1, 0.04, 0.001, max(p3 - 0.04, 0.01), 0.0001) * 0.8
  aS = (a1 + a2 + a3 + aT) * kD * kE * p5 * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.25, 0
endin

instr 28 ; 808: a sine that drops into pitch, long, saturated by Drive
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kF expseg p4 * 2.2, 0.035, p4, max(p3 - 0.035, 0.01), p4
  kD expseg 1, max(p3, 0.05), 0.2
  a1 oscili 1, kF, giSine
  kSat = 1.5 + 3 * gkDrive
  aS = tanh(a1 * kSat) / tanh(kSat) * kD * kE * p5 * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.05, 0
endin

instr 29 ; Reese: two detuned saws beating over a sine
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kDet = 0.006 + 0.006 * gkMotion
  a1 vco2 1, p4 * (1 + kDet)
  a2 vco2 1, p4 * (1 - kDet)
  a3 oscili 0.8, p4, giSine
  kCut = p4 * (3 + 6 * gkBright) * (1 + 0.3 * oscili:k(1, 0.25 + gkMotion, giSine))
  aF butterlp (a1 + a2) * 0.4, limit(kCut, 100, 6000)
  aS = (aF + a3) * kE * p5 * gkBass
  aL, aR Place aS, 0.5
  Send aL * 1.4, aR * 1.4, 1, 0.1, 0.05
endin

instr 30 ; Moog: a saw and a square an octave down through a resonant ladder filter
  kE Env p6, max(p3 - p6 - p7, 0.01), p7
  kE = kE * Cut(p8)
  if kE == 0 && timeinsts() > 1 then
    turnoff
  endif
  kD expseg 1, 0.6, 0.6, max(p3 - 0.6, 0.01), 0.5
  kFE expseg 1, 0.15 + 0.25 * (1 - p9), 0.12, max(p3 - 0.4, 0.01), 0.1
  a1 vco2 1, p4
  a2 vco2 0.7, p4 * 0.5, 10
  aF moogvcf2 (a1 + a2) * 0.6, limit(p4 * (2 + 5 * gkBright + 12 * kFE * (0.4 + p9)), 60, 8000), 0.35
  aS = aF * kD * kE * p5 * gkBass
  Send aS * 0.7, aS * 0.7, 1, 0.1, 0.05
endin

; ---- melody ----

instr 31 ; Bell: FM, inharmonic
  aEnv expseg 0.001, 0.006, 1, p3 - 0.006, 0.0005
  kIdx expseg 0.5 + 3 * i(gkBright), p3, 0.02
  aB foscili aEnv, p4, 1, 3.5, kIdx, giSine
  aP oscili aEnv * aEnv * 0.3, p4 * 2.76, giSine
  aL, aR Place (aB + aP) * p5 * Lvl(p6), random:i(0.1, 0.9)
  Send aL, aR, 0.5, 1, 1
endin

instr 32 ; Pluck: a plucked string
  aP pluck 1, p4, p4, 0, 1
  aP butterlp aP, p4 * (3 + 10 * i(gkBright))
  aEnv linseg 1, p3 - 0.1, 1, 0.1, 0
  aL, aR Place aP * aEnv * p5 * Lvl(p6), random:i(0.1, 0.9)
  Send aL, aR, 0.6, 0.8, 1
endin

instr 33 ; Kalimba: a tine with a bright click
  a1 oscili expseg:a(0.001, 0.003, 1, p3 - 0.003, 0.0005), p4, giSine
  a2 oscili expseg:a(0.001, 0.002, 0.4, 0.15, 0.0005, p3 - 0.152, 0.0005), p4 * 5.4, giSine
  aL, aR Place (a1 + a2 * (0.3 + i(gkBright))) * p5 * Lvl(p6), random:i(0.1, 0.9)
  Send aL, aR, 0.6, 0.8, 1
endin

instr 34 ; Flute: a breathy sine with a slow vibrato
  kE Env 0.12, max(p3 - 0.72, 0.01), 0.6
  kVib = oscili:k(0.006, 5, giSine) * linseg:k(0, 0.4, 0, 0.6, 1)
  a1 oscili 1, p4 * (1 + kVib), giSine
  a2 oscili 0.15, p4 * 2 * (1 + kVib), giSine
  aN rand 1, random:i(0, 1)
  aN butterbp aN, p4 * 2, p4
  aS = (a1 + a2 + aN * 0.4 * (0.3 + gkBright)) * kE * p5 * Lvl(p6)
  aL, aR Place aS, random:i(0.2, 0.8)
  Send aL, aR, 0.7, 0.8, 0.7
endin

instr 35 ; Felt: a soft, muted piano-like tone
  a1 oscili expseg:a(0.001, 0.004, 1, p3 - 0.004, 0.0005), p4, giSine
  a2 oscili expseg:a(0.001, 0.004, 0.4, p3 * 0.5, 0.0005, p3 * 0.5 - 0.004, 0.0005), p4 * 2, giSine
  a3 oscili expseg:a(0.001, 0.004, 0.2, p3 * 0.25, 0.0005, p3 * 0.75 - 0.004, 0.0005), p4 * 3.01, giSine
  aH rand expseg:a(0.3, 0.02, 0.0005, p3 - 0.02, 0.0005), random:i(0, 1)
  aH butterlp aH, 1500
  aS butterlp a1 + a2 + a3 + aH, p4 * (2 + 8 * i(gkBright))
  aL, aR Place aS * p5 * Lvl(p6), random:i(0.2, 0.8)
  Send aL, aR, 0.7, 0.8, 0.5
endin

instr 36 ; Lead: detuned saw and square, a delayed vibrato. p4 Hz, p5 level
  kE Env 0.02, max(p3 - 0.32, 0.01), 0.3
  kVib = oscili:k(0.005, 5.5, giSine) * linseg:k(0, 0.25, 0, 0.3, 1)
  a1 vco2 1, p4 * (1.003 + kVib)
  a2 vco2 0.7, p4 * (0.997 + kVib), 10
  aF butterlp (a1 + a2) / 1.7, limit(p4 * (2 + 10 * gkBright), 300, 12000)
  aL, aR Place aF * kE * p5 * Lvl(p6), random:i(0.35, 0.65)
  Send aL, aR, 0.8, 0.6, 0.7
endin

instr 37 ; Synth pluck: a saw with a fast filter envelope. p4 Hz, p5 level
  aEnv expseg 0.001, 0.003, 1, max(p3 - 0.003, 0.01), 0.001
  kCut expseg p4 * (4 + 16 * i(gkBright)), 0.18, p4 * 1.2, max(p3 - 0.18, 0.01), p4
  a1 vco2 1, p4
  aF butterlp a1, limit(kCut, 150, 14000)
  aL, aR Place aF * aEnv * p5 * Lvl(p6), random:i(0.2, 0.8)
  Send aL, aR, 0.7, 0.6, 0.8
endin

; ---- more melody voices (70-82). p4 Hz, p5 level ----

instr 70 ; E. piano: FM, a bell-like attack mellowing as it decays, a tine bark, a little tremolo
  aEnv expseg 0.001, 0.004, 1, max(p3 - 0.004, 0.01), 0.001
  kIdx expseg 1.2 + 1.5 * i(gkBright), p3, 0.15
  a1 foscili aEnv, p4, 1, 1, kIdx, giSine
  aT oscili expseg:a(0.001, 0.002, 0.25, 0.05, 0.0005, max(p3 - 0.052, 0.01), 0.0005), p4 * 14, giSine
  kTrem = 1 + 0.12 * gkMotion * oscili:k(1, 4.5, giSine)
  aL, aR Place (a1 + aT) * kTrem * p5 * Lvl(p6), random:i(0.3, 0.7)
  Send aL, aR, 0.8, 0.6, 0.6
endin

instr 71 ; Vibes: a struck bar (1st and 4th partials) with the motor's tremolo
  aE1 expseg 0.001, 0.003, 1, max(p3 - 0.003, 0.01), 0.001
  aE2 expseg 0.001, 0.003, 0.35, p3 * 0.3, 0.001, max(p3 * 0.7 - 0.003, 0.01), 0.001
  a1 oscili aE1, p4, giSine
  a2 oscili aE2, p4 * 4, giSine
  kTrem = 1 - 0.35 * (0.3 + 0.7 * gkMotion) * (0.5 + 0.5 * oscili:k(1, 5.5, giSine))
  aL, aR Place (a1 + a2 * (0.4 + 0.6 * i(gkBright))) * kTrem * p5 * Lvl(p6), random:i(0.3, 0.7)
  Send aL, aR, 0.8, 0.7, 0.6
endin

instr 72 ; Strings: a bowed line: two detuned saws, a swell, a delayed vibrato
  kE linseg 0, 0.18, 1, max(p3 - 0.58, 0.01), 0.85, 0.4, 0
  kVib = oscili:k(0.005, 5.2, giSine) * linseg:k(0, 0.3, 0, 0.4, 1)
  a1 vco2 1, p4 * (1 + kVib)
  a2 vco2 1, p4 * (1.004 + kVib * 0.8)
  aF butterlp (a1 + a2) / 2, limit(p4 * (3 + 6 * gkBright), 300, 9000)
  aF butterhp aF, 150
  aL, aR Place aF * kE * p5 * Lvl(p6), random:i(0.35, 0.65)
  Send aL, aR, 0.85, 0.7, 0.4
endin

instr 73 ; Chip: a square wave, 8-bit style, with a quick vibrato
  kE linseg 0, 0.005, 1, max(p3 - 0.055, 0.01), 0.8, 0.05, 0
  kVib = oscili:k(0.008, 6.5, giSine) * linseg:k(0, 0.15, 0, 0.1, 1)
  a1 vco2 1, p4 * (1 + kVib), 10
  a1 butterlp a1, limit(p4 * (6 + 10 * gkBright), 500, 12000)
  aL, aR Place a1 * kE * p5 * Lvl(p6), 0.5
  Send aL, aR, 0.85, 0.4, 0.7
endin

instr 74 ; Brass: saws with a filter that swells open, like a synth horn
  kE linseg 0, 0.03, 1, max(p3 - 0.23, 0.01), 0.75, 0.2, 0
  kF linseg 0, 0.08, 1, max(p3 - 0.08, 0.01), 0.6
  a1 vco2 1, p4
  a2 vco2 0.6, p4 * 1.005
  aF butterlp (a1 + a2) / 1.6, limit(p4 * (1.5 + kF * (3 + 8 * gkBright)), 200, 12000)
  aL, aR Place aF * kE * p5 * Lvl(p6), random:i(0.4, 0.6)
  Send aL, aR, 0.85, 0.5, 0.5
endin

instr 75 ; Sync lead: a saw hard-synced to the note, its timbre sweeping down: aggressive
  kE linseg 0, 0.004, 1, max(p3 - 0.084, 0.01), 0.85, 0.08, 0
  kRatio expseg 3.5 + 2 * i(gkBright), p3, 1.5
  aPhM, aSync syncphasor p4, a(0)
  aPh, aOut syncphasor p4 * kRatio, aSync
  aS butterlp aPh * 2 - 1, limit(p4 * 12, 800, 14000)
  aL, aR Place aS * kE * p5 * Lvl(p6), 0.5
  Send aL, aR, 0.85, 0.45, 0.6
endin

instr 76 ; Saw stack: three detuned saws, bright and wide: a trance lead
  kE linseg 0, 0.006, 1, max(p3 - 0.066, 0.01), 0.9, 0.06, 0
  kD = 0.006 + 0.006 * gkMotion
  a1 vco2 1, p4
  a2 vco2 1, p4 * (1 + kD)
  a3 vco2 1, p4 * (1 - kD)
  kCut = limit(p4 * (4 + 12 * gkBright), 400, 14000)
  aF1 butterlp (a1 + a2) / 1.6, kCut
  aF2 butterlp (a1 + a3) / 1.6, kCut
  kG = kE * p5 * Lvl(p6)
  Send aF1 * kG * 0.8, aF2 * kG * 0.8, 0.85, 0.55, 0.6
endin

instr 77 ; Marimba: a wooden bar: partials at 1, 3.9 and 9.2 times, the upper ones dying fast
  a1 oscili expseg:a(0.001, 0.002, 1, max(p3 - 0.002, 0.01), 0.001), p4, giSine
  a2 oscili expseg:a(0.001, 0.002, 0.5, 0.12, 0.001, max(p3 - 0.122, 0.01), 0.001), p4 * 3.9, giSine
  a3 oscili expseg:a(0.001, 0.001, 0.25, 0.04, 0.001, max(p3 - 0.041, 0.01), 0.001), p4 * 9.2, giSine
  aL, aR Place (a1 + (a2 + a3) * (0.4 + 0.6 * i(gkBright))) * p5 * Lvl(p6), random:i(0.2, 0.8)
  Send aL, aR, 0.8, 0.55, 0.6
endin

instr 78 ; Steel drum: a hammered pan: partials 1, 2 and 3 fading at different rates, a shimmer
  aE expseg 0.001, 0.003, 1, max(p3 - 0.003, 0.01), 0.001
  a1 oscili aE, p4, giSine
  a2 oscili aE * aE * 0.5, p4 * 2.005, giSine
  a3 oscili aE * aE * aE * 0.35, p4 * 3.01, giSine
  aSh = 1 + 0.12 * oscili:a(1, 7, giSine)
  aL, aR Place (a1 + a2 + a3) * aSh * p5 * Lvl(p6), random:i(0.25, 0.75)
  Send aL, aR, 0.8, 0.6, 0.6
endin

instr 79 ; Harp: a bright plucked string with a long ring
  aP pluck 1, p4, p4, 0, 1
  aP butterlp aP, limit(p4 * (6 + 12 * i(gkBright)), 500, 14000)
  aB oscili expseg:a(0.001, 0.003, 0.4, max(p3 - 0.003, 0.01), 0.001), p4, giSine
  aEnv linseg 1, max(p3 - 0.15, 0.01), 1, 0.15, 0
  aL, aR Place (aP + aB) * aEnv * p5 * Lvl(p6), random:i(0.2, 0.8)
  Send aL, aR, 0.75, 0.75, 0.6
endin

instr 80 ; Voice: a sung "oo" opening to "ah", with vibrato
  kE linseg 0, 0.12, 1, max(p3 - 0.47, 0.01), 0.85, 0.35, 0
  kVib = oscili:k(0.006, 5, giSine) * linseg:k(0, 0.35, 0, 0.4, 1)
  a1 vco2 1, p4 * (1 + kVib)
  kM linseg 0, p3 * 0.6, 1, p3 * 0.4, 1  ; 0 "oo" to 1 "ah"
  aF1 butterbp a1, 300 + 400 * kM, 80
  aF2 butterbp a1, 870 + 350 * kM, 100
  aF3 butterbp a1, 2240 + 360 * kM, 140
  aV = (aF1 + aF2 * 0.6 + aF3 * 0.3 * (0.3 + gkBright)) * 3
  aL, aR Place aV * kE * p5 * Lvl(p6), random:i(0.35, 0.65)
  Send aL, aR, 0.8, 0.75, 0.5
endin

instr 81 ; Organ lead: drawbars, a percussive click on the 2nd harmonic, a fast tremolo
  kE linseg 0, 0.008, 1, max(p3 - 0.068, 0.01), 1, 0.06, 0
  a1 oscili 1, p4, giOrgBright
  aPerc oscili expseg:a(0.6, 0.15, 0.001, max(p3 - 0.15, 0.01), 0.001), p4 * 2, giSine
  kTrem = 1 + 0.18 * oscili:k(1, 6.5, giSine)
  aL, aR Place (a1 + aPerc) * kTrem * kE * p5 * Lvl(p6), random:i(0.35, 0.65)
  Send aL, aR, 0.85, 0.5, 0.5
endin

instr 82 ; Guitar: a plucked string through a body resonance, a little overdriven
  aP pluck 1, p4, p4, 0, 1
  aB1 butterbp aP, 220, 140
  aB2 butterbp aP, 2500, 1800
  aG = tanh((aP * 0.7 + aB1 * 0.8 + aB2 * 0.3 * (0.4 + i(gkBright))) * 2.5) * 0.45
  aEnv linseg 1, max(p3 - 0.1, 0.01), 1, 0.1, 0
  aL, aR Place aG * aEnv * p5 * Lvl(p6), random:i(0.25, 0.75)
  Send aL, aR, 0.85, 0.5, 0.6
endin

; ---- acoustic strings and reeds: p4 Hz, p5 level, p6 whose level (Lvl) ----

instr 83 ; Fiddle: a bowed string (waveguide), its body's resonances, vibrato that comes in late
  iRel = min(0.08, p3 * 0.3)
  kE linseg 0, 0.02, 1, max(p3 - 0.02 - iRel, 0.01), 0.92, iRel, 0
  kVibA = 0.005 * linseg:k(0, 0.2, 0, 0.3, 1)
  aB wgbow 1, p4, 3.2 + 0.8 * gkBright, 0.127, 5.6, kVibA, giSine, 60
  aN rand 0.02, random:i(0, 1)
  aN butterhp aN, 3000
  aB = aB + aN * kE
  aF1 butterbp aB, 280, 140
  aF2 butterbp aB, 470, 220
  aF3 butterbp aB, 2800, 1600
  aS butterlp aB * 0.5 + aF1 * 0.9 + aF2 * 0.7 + aF3 * 0.6, limit(p4 * (5 + 8 * gkBright), 1500, 12000)
  aL, aR Place aS * kE * p5 * Lvl(p6), random:i(0.35, 0.65)
  Send aL, aR, 0.85, 0.6, 0.3
endin

instr 84 ; Mandolin: a picked pair of strings a hair apart; a long note is played tremolo, the pick going back and forth
  iTrem = (p3 > 0.45 ? 1 : 0)
  aImp mpulse 1, iTrem / 13
  aExc butterlp aImp, 3500
  aS1 streson aExc, p4, 0.993
  aS2 streson aExc, p4 * 1.0035, 0.993
  aS = aS1 + aS2
  aB1 butterbp aS, 420, 250
  aB2 butterbp aS, 2600, 1500
  aM = aS * 0.6 + aB1 * 0.8 + aB2 * 0.7 * (0.5 + gkBright)
  aEnv linseg 1, max(p3 - 0.05, 0.01), 1, 0.05, 0
  aL, aR Place aM * aEnv * p5 * Lvl(p6), random:i(0.3, 0.7)
  Send aL, aR, 0.8, 0.5, 0.3
endin

instr 85 ; Banjo: a bright pluck, quickly gone, with the drum head's twang
  aP pluck 1, p4, p4, 0, 1
  aD expseg 1, max(p3, 0.05), 0.03
  aH butterbp aP, 1300, 900
  aK butterhp aP, 2500
  aS = (aP * 0.5 + aH * 1.4 + aK * 0.5 * (0.5 + gkBright)) * aD
  aS butterhp aS, 140
  aEnv linseg 1, max(p3 - 0.04, 0.01), 1, 0.04, 0
  aL, aR Place aS * aEnv * p5 * Lvl(p6), random:i(0.25, 0.75)
  Send aL, aR, 0.85, 0.45, 0.3
endin

instr 86 ; Acoustic guitar: a clean plucked string through the body's air and top resonances
  aP pluck 1, p4, p4, 0, 1
  aP butterlp aP, limit(p4 * (4 + 8 * gkBright), 800, 9000)
  aB1 butterbp aP, 105, 45
  aB2 butterbp aP, 220, 100
  aB3 butterbp aP, 3000, 2000
  aS = aP * 0.8 + aB1 * 0.9 + aB2 * 0.6 + aB3 * 0.3
  aEnv linseg 1, max(p3 - 0.08, 0.01), 1, 0.08, 0
  aL, aR Place aS * aEnv * p5 * Lvl(p6), random:i(0.25, 0.75)
  Send aL, aR, 0.85, 0.6, 0.4
endin

instr 87 ; Dobro: a slide guitar: each note slides up into its pitch, through a metal resonator, with a slow shimmer
  kF expseg p4 * 0.94, 0.09, p4, max(p3 - 0.09, 0.01), p4
  kF = kF * (1 + 0.004 * oscili:k(1, 5.5, giSine) * linseg:k(0, 0.3, 0, 0.3, 1))
  aP pluck 1, kF, p4 * 0.9, 0, 1
  aR1 butterbp aP, 900, 350
  aR2 butterbp aP, 2400, 900
  aS = aP * 0.5 + aR1 * 1.0 + aR2 * 0.6 * (0.5 + gkBright)
  aEnv linseg 1, max(p3 - 0.1, 0.01), 1, 0.1, 0
  aL, aR Place aS * aEnv * p5 * Lvl(p6), random:i(0.3, 0.7)
  Send aL, aR, 0.85, 0.7, 0.4
endin

instr 88 ; Harmonica: free reeds: narrow pulse waves, a scoop into each note, breath, a hand vibrato on long notes
  kE linseg 0, 0.025, 1, max(p3 - 0.095, 0.01), 0.85, 0.07, 0
  kF expseg p4 * 0.97, 0.06, p4, max(p3 - 0.06, 0.01), p4
  kTrem = 1 + 0.25 * oscili:k(1, 5, giSine) * linseg:k(0, 0.35, 0, 0.3, 1)
  a1 vco2 1, kF, 2, 0.32
  a2 vco2 0.5, kF * 1.004, 2, 0.4
  aN rand 0.08, random:i(0, 1)
  aR = a1 + a2 + butterbp(aN, p4 * 2, p4)
  aF1 butterbp aR, 1100, 600
  aF2 butterbp aR, 2700, 1200
  aS butterlp aR * 0.3 + aF1 * 0.9 + aF2 * 0.5 * (0.5 + gkBright), 7000
  aL, aR2 Place aS * kE * kTrem * p5 * Lvl(p6), 0.5
  Send aL, aR2, 0.85, 0.5, 0.2
endin

; ---- texture: held notes (p3 -1), stopped by a negative p1 ----

instr 41 ; Wind
  kE linsegr 0, 4, 1, 4, 0
  aNL rand 1, 0.31
  aNR rand 1, 0.77
  kC jspline 1, 0.03, 0.1 + gkMotion * 0.2
  kCen = 350 * 2 ^ (kC * 1.2 + gkBright * 2)
  aL butterbp aNL, kCen, kCen * 0.5
  aR butterbp aNR, kCen * 1.07, kCen * 0.5
  kG = kE * gkTex * 0.5 * (0.65 + jspline:k(0.35, 0.05, 0.15))
  Send aL * kG, aR * kG, 1, 0.6, 0
endin

instr 42 ; Rain
  kE linsegr 0, 4, 1, 4, 0
  aDL dust2 1, 500 + 500 * gkMotion
  aDR dust2 1, 500 + 500 * gkMotion
  kC = 3000 + 3000 * gkBright
  aDL butterbp aDL, kC, kC * 0.8
  aDR butterbp aDR, kC * 1.1, kC * 0.8
  aNL rand 1, 0.13
  aNR rand 1, 0.57
  aNL butterlp aNL, 1200
  aNR butterlp aNR, 1200
  kG = kE * gkTex * (0.85 + jspline:k(0.15, 0.05, 0.2))
  Send (aDL * 0.5 + aNL * 0.12) * kG, (aDR * 0.5 + aNR * 0.12) * kG, 1, 0.5, 0
endin

instr 43 ; Waves: slow swells of filtered noise
  kE linsegr 0, 4, 1, 4, 0
  kRate = 0.07 + 0.06 * gkMotion
  kSL = 0.5 + 0.5 * oscili:k(1, kRate, giSine)
  kSR = 0.5 + 0.5 * oscili:k(1, kRate * 0.93, giSine, 0.3)
  aNL rand 1, 0.21
  aNR rand 1, 0.66
  aL butterlp aNL, 200 + 2500 * kSL * kSL * (0.4 + gkBright)
  aR butterlp aNR, 200 + 2500 * kSR * kSR * (0.4 + gkBright)
  kG = kE * gkTex * 0.6
  Send aL * (0.15 + kSL) * kG, aR * (0.15 + kSR) * kG, 1, 0.5, 0
endin

instr 44 ; Vinyl: crackle and a little hiss
  kE linsegr 0, 4, 1, 4, 0
  aCL dust2 1, 6 + 10 * gkMotion
  aCR dust2 1, 6 + 10 * gkMotion
  aCL butterhp aCL, 1200
  aCR butterhp aCR, 1200
  aH rand 1, 0.44
  aH butterbp aH, 5000 + 3000 * gkBright, 4000
  kG = kE * gkTex
  Send (aCL * 1.2 + aH * 0.03) * kG, (aCR * 1.2 + aH * 0.03) * kG, 1, 0.2, 0
endin

instr 45 ; Stream: bubbling, jittered bands
  kE linsegr 0, 4, 1, 4, 0
  aN rand 1, 0.91
  aN2 rand 1, 0.37
  k1 randh 1, 25 + 15 * gkMotion
  k2 randh 1, 31 + 15 * gkMotion
  k3 randh 1, 19 + 15 * gkMotion
  a1 butterbp aN, 1200 + 700 * k1 + 600 * gkBright, 150
  a2 butterbp aN2, 1800 + 800 * k2 + 600 * gkBright, 200
  a3 butterbp aN, 800 + 300 * k3, 120
  kG = kE * gkTex * 1.5
  Send (a1 + a3 * 0.7) * kG, (a2 + a3 * 0.5) * kG, 1, 0.5, 0
endin

; ---- pulse ----

instr 51 ; Heartbeat: a soft low thump
  kF expseg p4 * 2, 0.12, p4, p3 - 0.12, p4
  aEnv expseg 0.001, 0.005, 1, p3 - 0.005, 0.001
  a1 oscili aEnv, kF, giSine
  aS = a1 * p5 * gkPulse
  Send aS * 0.7, aS * 0.7, 1, 0.3, 0.2
endin

instr 52 ; Arp: short plucks
  aP pluck 1, p4, p4, 0, 1
  aP butterlp aP, p4 * (2 + 8 * i(gkBright))
  aEnv linseg 1, p3 - 0.05, 1, 0.05, 0
  aL, aR Place aP * aEnv * p5 * gkPulse, random:i(0.25, 0.75)
  Send aL, aR, 0.8, 0.5, 1
endin

instr 53 ; Glints: tiny high blips
  aEnv expseg 0.001, 0.002, 1, p3 - 0.002, 0.0005
  a1 oscili aEnv, p4, giSine
  aL, aR Place a1 * p5 * gkPulse, random:i(0.05, 0.95)
  Send aL, aR, 0.4, 1, 1
endin

; ---- drums: their own bus. p4 level ----

instr 61 ; Kick: a sine falling to its pitch, and a click. p5 decay s, p6 pitch Hz
  kF expseg p6 * 3.2, 0.045, p6, max(p3 - 0.045, 0.01), p6 * 0.9
  aEnv expseg 1, p5, 0.001, max(p3 - p5, 0.01), 0.0001
  a1 oscili aEnv, kF, giSine
  aC rand 1, random:i(0, 1)
  aC butterhp aC, 2500
  aCE expseg 1, 0.004, 0.001, max(p3 - 0.004, 0.01), 0.0001
  aK = (a1 + aC * aCE * 0.12) * p4 * gkDrums
  gaDrumL += aK
  gaDrumR += aK
  gkKick init i(gkKick) + 1
endin

instr 62 ; Snare: two tones and a band of noise. p5 decay s
  aT1 oscili expseg:a(1, 0.11, 0.001, max(p3 - 0.11, 0.01), 0.0001), 185, giSine
  aT2 oscili expseg:a(0.6, 0.07, 0.001, max(p3 - 0.07, 0.01), 0.0001), 330, giSine
  aN rand 1, random:i(0, 1)
  aN butterbp aN, 3200, 4000
  aNE expseg 1, p5, 0.001, max(p3 - p5, 0.01), 0.0001
  aS = (aT1 * 0.5 + aT2 * 0.3 + aN * aNE * 0.9) * p4 * gkDrums
  aL, aR Place aS, 0.48
  gaDrumL += aL
  gaDrumR += aR
  gaWetL += aL * 0.15
  gaWetR += aR * 0.15
endin

instr 63 ; Clap: three quick bursts of noise and a short tail
  aN rand 1, random:i(0, 1)
  aN butterbp aN, 1150, 900
  aE linseg 0, 0.001, 1, 0.008, 0.15, 0.001, 1, 0.008, 0.15, 0.001, 1, 0.012, 0.45, max(p3 - 0.032, 0.01), 0
  aE = aE * aE
  aS = aN * aE * p4 * gkDrums * 1.6
  aL, aR Place aS, 0.52
  gaDrumL += aL
  gaDrumR += aR
  gaWetL += aL * 0.25
  gaWetR += aR * 0.25
endin

instr 64 ; Hat: metallic noise, high. p5 decay s (short: closed; long: open)
  aN rand 1, random:i(0, 1)
  a1 vco2 1, 540, 10
  a2 vco2 1, 800, 10
  aM = aN * 0.7 + a1 * a2 * 0.5
  aM butterhp aM, 7000
  aE expseg 1, p5, 0.001, max(p3 - p5, 0.01), 0.0001
  aS = aM * aE * p4 * gkDrums * 0.7
  aL, aR Place aS, 0.62
  gaDrumL += aL
  gaDrumR += aR
endin

instr 66 ; Rim: a short high knock
  a1 oscili expseg:a(1, 0.035, 0.001, max(p3 - 0.035, 0.01), 0.0001), 1650, giSine
  aC rand 1, random:i(0, 1)
  aC butterbp aC, 3000, 1500
  aCE expseg 1, 0.008, 0.001, max(p3 - 0.008, 0.01), 0.0001
  aS = (a1 * 0.6 + aC * aCE * 0.8) * p4 * gkDrums
  aL, aR Place aS, 0.38
  gaDrumL += aL
  gaDrumR += aR
  gaWetL += aL * 0.2
  gaWetR += aR * 0.2
endin

; the acoustic kit: same p-fields as the electronic one

instr 91 ; Acoustic kick: a lower, rounder body with less pitch drop, a beater click, a thud. p5 decay s, p6 pitch Hz
  kF expseg p6 * 1.7, 0.025, p6, max(p3 - 0.025, 0.01), p6 * 0.95
  aEnv expseg 1, p5, 0.001, max(p3 - p5, 0.01), 0.0001
  a1 oscili aEnv, kF, giSine
  aN rand 1, random:i(0, 1)
  aC butterbp aN, 3500, 2500
  aCE expseg 1, 0.006, 0.001, max(p3 - 0.006, 0.01), 0.0001
  aT butterlp aN, 120
  aTE expseg 1, 0.05, 0.001, max(p3 - 0.05, 0.01), 0.0001
  aK = (a1 + aC * aCE * 0.25 + aT * aTE * 0.6) * p4 * gkDrums
  gaDrumL += aK
  gaDrumR += aK
  gaWetL += aK * 0.08
  gaWetR += aK * 0.08
  gkKick init i(gkKick) + 1
endin

instr 92 ; Acoustic snare: the head (two tones), the wires (wide noise), a stick. p5 decay s
  aT1 oscili expseg:a(1, 0.07, 0.001, max(p3 - 0.07, 0.01), 0.0001), 205, giSine
  aT2 oscili expseg:a(0.5, 0.05, 0.001, max(p3 - 0.05, 0.01), 0.0001), 290, giSine
  aN rand 1, random:i(0, 1)
  aW butterhp aN, 1800
  aW butterlp aW, 9000
  aWE expseg 1, p5, 0.001, max(p3 - p5, 0.01), 0.0001
  aS1 butterbp aN, 5000, 3000
  aSE expseg 1, 0.004, 0.001, max(p3 - 0.004, 0.01), 0.0001
  aS = (aT1 * 0.5 + aT2 * 0.3 + aW * aWE * 0.75 + aS1 * aSE * 0.5) * p4 * gkDrums
  aL, aR Place aS, 0.46
  gaDrumL += aL
  gaDrumR += aR
  gaWetL += aL * 0.3
  gaWetR += aR * 0.3
endin

instr 94 ; Acoustic hat: bright noise and an inharmonic metallic ring. p5 decay s
  aN rand 1, random:i(0, 1)
  a1 vco2 1, 317, 10
  a2 vco2 1, 541, 10
  a3 vco2 1, 873, 10
  aM = aN * 0.6 + a1 * a2 * a3 * 0.6
  aM butterbp aM, 9000, 7000
  aM butterhp aM, 5500
  aE expseg 1, p5, 0.001, max(p3 - p5, 0.01), 0.0001
  aS = aM * aE * p4 * gkDrums * 0.8
  aL, aR Place aS, 0.66
  gaDrumL += aL
  gaDrumR += aR
  gaWetL += aL * 0.2
  gaWetR += aR * 0.2
endin

instr 96 ; Cross-stick: a woody click on the rim
  a1 oscili expseg:a(1, 0.025, 0.001, max(p3 - 0.025, 0.01), 0.0001), 900, giSine
  a2 oscili expseg:a(0.5, 0.015, 0.001, max(p3 - 0.015, 0.01), 0.0001), 1900, giSine
  aC rand 1, random:i(0, 1)
  aC butterbp aC, 2200, 1200
  aCE expseg 1, 0.006, 0.001, max(p3 - 0.006, 0.01), 0.0001
  aS = (a1 * 0.6 + a2 * 0.3 + aC * aCE * 0.7) * p4 * gkDrums
  aL, aR Place aS, 0.4
  gaDrumL += aL
  gaDrumR += aR
  gaWetL += aL * 0.25
  gaWetR += aR * 0.25
endin

; ---- effects and output ----

instr 98 ; echo: two darkening delays, the right one longer
  kT limit gkEchoS, 0.1, 1.3
  kFb = 0.2 + 0.5 * gkEcho
  aBufL delayr 2
  aTL deltap3 kT
  aTL butterlp aTL, 3500
  delayw gaEchoL + aTL * kFb
  aBufR delayr 2
  aTR deltap3 kT * 1.5
  aTR butterlp aTR, 3000
  delayw gaEchoR + aTR * kFb
  gaDryL += aTL * gkEcho
  gaDryR += aTR * gkEcho
  gaWetL += aTL * gkEcho * 0.5
  gaWetR += aTR * gkEcho * 0.5
  clear gaEchoL, gaEchoR
endin

instr 99 ; reverb, the pump, the drums, drive, volume, and a soft ceiling under -1 dBFS
  aWL, aWR reverbsc gaWetL, gaWetR, 0.80 + 0.17 * gkSpace, 5000 + 4000 * gkBright
  kWet = 0.2 + 0.6 * gkSpace
  kDry = 1 - 0.5 * gkSpace
  kDuck port gkDuck, 0.003
  aL = (gaDryL * kDry + aWL * kWet) * kDuck + gaDrumL
  aR = (gaDryR * kDry + aWR * kWet) * kDuck + gaDrumR
  ; drive: tanh saturation, scaled so a peak of 0.25 (-12 dBFS) keeps its level:
  ; quieter parts come up a little, louder ones are squashed
  kDrv = 1 + 5 * gkDrive
  kMake = 0.25 / tanh(0.25 * kDrv)
  aL = tanh(aL * kDrv) * kMake
  aR = tanh(aR * kDrv) * kMake
  kG = gkVol * gkFade * gkGain
  aL butterhp aL * kG, 30
  aR butterhp aR * kG, 30
  outs 0.89 * tanh(aL / 0.89), 0.89 * tanh(aR / 0.89)
  clear gaDryL, gaDryR, gaWetL, gaWetR, gaDrumL, gaDrumR
endin
