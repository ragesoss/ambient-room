; Step 1 test sound: a pad, a bass drone, bells, wind, and reverb.
; Python (spike.py) sets the controls through channels, each 0-1, and
; schedules the notes. Every control glides to its new value.

sr = 48000
ksmps = 128
nchnls = 2
0dbfs = 1

seed 0

giSine ftgen 0, 0, 16384, 10, 1

gaDryL init 0
gaDryR init 0
gaWetL init 0
gaWetR init 0

chn_k "volume", 1
chn_k "bright", 1
chn_k "motion", 1
chn_k "space", 1
chn_k "wind", 1
chn_k "fade", 1
chn_k "gain_db", 1

gkVol init 0
gkBright init 0
gkMotion init 0
gkSpace init 0
gkWind init 0
gkFade init 0
gkGain init 1

alwayson 1
alwayson 30
alwayson 99

instr 1 ; the controls, glided
  gkVol lineto chnget:k("volume"), 3
  gkBright lineto chnget:k("bright"), 4
  gkMotion lineto chnget:k("motion"), 4
  gkSpace lineto chnget:k("space"), 4
  gkWind lineto chnget:k("wind"), 4
  gkFade lineto chnget:k("fade"), 10
  gkGain = ampdb(chnget:k("gain_db"))
endin

instr 10 ; pad voice. p4 Hz, p5 level, p6 attack s, p7 release s
  iF = p4
  iAtt = p6
  iRel = p7
  iSus = max(p3 - iAtt - iRel, 0.01)
  kE linseg 0, iAtt, 1, iSus, 1, iRel, 0
  kE = kE * kE * (3 - 2 * kE)
  kRate = 0.05 + gkMotion * 0.4
  kD1 jspline 0.003, kRate, kRate * 2
  kD2 jspline 0.003, kRate, kRate * 2
  kD3 jspline 0.003, kRate, kRate * 2
  kDet = 0.002 + gkMotion * 0.004
  a1 vco2 1, iF * (1 + kD1)
  a2 vco2 1, iF * (1 + kDet + kD2)
  a3 vco2 1, iF * (1 - kDet + kD3), 12
  aMix = (a1 + a2 + a3 * 0.6) / 2.6
  kWob jspline 0.3, kRate * 0.5, kRate
  kCut = iF * (1.2 + 9 * gkBright * gkBright) * (1 + kWob * gkMotion)
  kCut limit kCut, 150, 9000
  aF butterlp aMix, kCut ; moogladder cost 3x the whole patch on the Pi 3
  aOut = aF * kE * p5
  iPan random 0.15, 0.85
  aL = aOut * sqrt(1 - iPan)
  aR = aOut * sqrt(iPan)
  gaDryL += aL
  gaDryR += aR
  gaWetL += aL
  gaWetR += aR
endin

instr 15 ; bass drone. p4 Hz, p5 level, p6 attack s, p7 release s
  iSus = max(p3 - p6 - p7, 0.01)
  kE linseg 0, p6, 1, iSus, 1, p7, 0
  kE = kE * kE * (3 - 2 * kE)
  a1 oscili 1, p4, giSine
  a2 oscili 0.2 + 0.2 * gkBright, p4 * 2, giSine
  aOut = (a1 + a2) * kE * p5
  gaDryL += aOut * 0.7
  gaDryR += aOut * 0.7
  gaWetL += aOut * 0.15
  gaWetR += aOut * 0.15
endin

instr 20 ; bell. p4 Hz, p5 level
  aEnv expseg 0.001, 0.006, 1, p3 - 0.006, 0.0005
  iIdx = 0.5 + 3 * i(gkBright)
  kIdx expseg iIdx, p3, 0.02
  aB foscili aEnv, p4, 1, 3.5, kIdx, giSine
  aP oscili aEnv * aEnv * 0.3, p4 * 2.76, giSine
  aOut = (aB + aP) * p5
  iPan random 0.1, 0.9
  aL = aOut * sqrt(1 - iPan)
  aR = aOut * sqrt(iPan)
  gaDryL += aL * 0.5
  gaDryR += aR * 0.5
  gaWetL += aL
  gaWetR += aR
endin

instr 30 ; wind: noise through a slowly moving band
  aNL rand 1, 0.31
  aNR rand 1, 0.77
  kC jspline 1, 0.03, 0.1
  kCen = 350 * 2 ^ (kC * 1.2 + gkBright * 2)
  aL butterbp aNL, kCen, kCen * 0.5
  aR butterbp aNR, kCen * 1.07, kCen * 0.5
  kSwell jspline 0.35, 0.05, 0.15
  kG = gkWind * gkWind * 0.12 * (0.65 + kSwell)
  gaDryL += aL * kG
  gaDryR += aR * kG
  gaWetL += aL * kG
  gaWetR += aR * kG
endin

instr 99 ; reverb, volume, and a soft ceiling under -1 dBFS
  kFb = 0.80 + 0.17 * gkSpace
  aWL, aWR reverbsc gaWetL, gaWetR, kFb, 5000 + 4000 * gkBright
  kWet = 0.2 + 0.6 * gkSpace
  kDry = 1 - 0.5 * gkSpace
  kG = gkVol * gkFade * gkGain
  aL = (gaDryL * kDry + aWL * kWet) * kG
  aR = (gaDryR * kDry + aWR * kWet) * kG
  outs 0.89 * tanh(aL / 0.89), 0.89 * tanh(aR / 0.89)
  clear gaDryL, gaDryR, gaWetL, gaWetR
endin
