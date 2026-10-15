"""Write the SoundFont for the sfload global-zone test.

One looped ramp sample (256 frames at 1024 Hz, root key 60) and four pairs
of instruments, each with a preset of the same number. Instrument 2k sets a
value in its global zone; instrument 2k+1, its twin, sets the same value in
the sample's own zone:
  0, 1: pan -500
  2, 3: pan +500
  4, 5: initialAttenuation 300 cB
  6, 7: scaleTuning 300 cents per key

Usage: python3 make_global_zones_sf2.py OUT.sf2
"""

import struct
import sys

PAN, INSTRUMENT, ATTENUATION, SAMPLE_ID, SAMPLE_MODES, SCALE_TUNING = 17, 41, 48, 53, 54, 56
FRAMES, RATE, ROOT = 256, 1024, 60
VALUES = [("pan -500", PAN, -500), ("pan +500", PAN, 500),
          ("atten 300", ATTENUATION, 300), ("scale 300", SCALE_TUNING, 300)]


def chunk(cid: bytes, data: bytes) -> bytes:
    return cid + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")


def lst(kind: bytes, *chunks: bytes) -> bytes:
    return chunk(b"LIST", kind + b"".join(chunks))


def name(s: str) -> bytes:
    return s.encode("ascii")[:19].ljust(20, b"\0")


def gen(oper: int, amount: int) -> bytes:
    return struct.pack("<Hh", oper, amount)


def build() -> bytes:
    info = lst(b"INFO", chunk(b"ifil", struct.pack("<HH", 2, 1)), chunk(b"isng", b"EMU8000\0"),
               chunk(b"INAM", b"Global zones\0"))
    ramp = [round(-0x2000 + 0x4000 * i / (FRAMES - 1)) for i in range(FRAMES)]
    sdta = lst(b"sdta", chunk(b"smpl", struct.pack(f"<{FRAMES + 46}h", *(ramp + [0] * 46))))

    instruments = []
    for label, oper, value in VALUES:
        instruments.append(("Global " + label, [(oper, value)], []))
        instruments.append(("Zone " + label, [], [(oper, value)]))
    phdr = pbag = pgen = inst = ibag = igen = b""
    npgen = nibag = nigen = 0
    for i, (label, glob, local) in enumerate(instruments):
        phdr += name(label) + struct.pack("<HHHIII", i, 0, i, 0, 0, 0)
        pbag += struct.pack("<HH", npgen, 0)
        pgen += gen(INSTRUMENT, i)
        npgen += 1
        inst += name(label) + struct.pack("<H", nibag)
        for z in ([glob] if glob else []) + [local + [(SAMPLE_MODES, 1), (SAMPLE_ID, 0)]]:
            ibag += struct.pack("<HH", nigen, 0)
            igen += b"".join(gen(o, a) for o, a in z)
            nigen += len(z)
            nibag += 1
    n = len(instruments)
    phdr += name("EOP") + struct.pack("<HHHIII", 0, 0, n, 0, 0, 0)
    pbag += struct.pack("<HH", npgen, 0)
    pgen += gen(0, 0)
    inst += name("EOI") + struct.pack("<H", nibag)
    ibag += struct.pack("<HH", nigen, 0)
    igen += gen(0, 0)
    shdr = (name("Ramp") + struct.pack("<IIIIIBbHH", 0, FRAMES, 8, FRAMES - 8, RATE, ROOT, 0, 0, 1)
            + name("EOS") + struct.pack("<IIIIIBbHH", 0, 0, 0, 0, 0, 0, 0, 0, 0))
    pdta = lst(b"pdta", chunk(b"phdr", phdr), chunk(b"pbag", pbag), chunk(b"pmod", bytes(10)),
               chunk(b"pgen", pgen), chunk(b"inst", inst), chunk(b"ibag", ibag), chunk(b"imod", bytes(10)),
               chunk(b"igen", igen), chunk(b"shdr", shdr))
    return chunk(b"RIFF", b"sfbk" + info + sdta + pdta)


if __name__ == "__main__":
    data = build()
    with open(sys.argv[1], "wb") as f:
        f.write(data)
    print(f"{sys.argv[1]}: {len(data)} bytes")
