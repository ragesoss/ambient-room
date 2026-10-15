"""Write a SoundFont whose instruments set pan or attenuation in a global
zone, beside instruments that set the same value in their sample's zone.

One constant, looped sample (0x1000, 256 frames at 1024 Hz, root key 60).
Preset n plays instrument n:
  0: global zone pan -500        1: sample zone pan -500
  2: global zone pan +500        3: sample zone pan +500
  4: global zone attenuation 300 cB   5: sample zone attenuation 300 cB

Usage: python3 make_global_sf2.py OUT.sf2
"""

import struct
import sys

ATTENUATION, PAN, INSTRUMENT, SAMPLE_ID, SAMPLE_MODES = 48, 17, 41, 53, 54
FRAMES, RATE, ROOT = 256, 1024, 60

# (name, global zone generators, sample zone generators)
INSTRUMENTS = [
    ("Global pan -500", [(PAN, -500)], []),
    ("Zone pan -500", [], [(PAN, -500)]),
    ("Global pan +500", [(PAN, 500)], []),
    ("Zone pan +500", [], [(PAN, 500)]),
    ("Global atten 300", [(ATTENUATION, 300)], []),
    ("Zone atten 300", [], [(ATTENUATION, 300)]),
]


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
    smpl = struct.pack(f"<{FRAMES + 46}h", *([0x1000] * FRAMES + [0] * 46))
    sdta = lst(b"sdta", chunk(b"smpl", smpl))

    phdr = pbag = pgen = inst = ibag = igen = b""
    npgen = nibag = nigen = 0
    for i, (label, glob, local) in enumerate(INSTRUMENTS):
        phdr += name(label) + struct.pack("<HHHIII", i, 0, i, 0, 0, 0)
        pbag += struct.pack("<HH", npgen, 0)
        pgen += gen(INSTRUMENT, i)
        npgen += 1
        inst += name(label) + struct.pack("<H", nibag)
        zones = ([glob] if glob else []) + [local + [(SAMPLE_MODES, 1), (SAMPLE_ID, 0)]]
        for z in zones:
            ibag += struct.pack("<HH", nigen, 0)
            igen += b"".join(gen(o, a) for o, a in z)
            nigen += len(z)
            nibag += 1
    n = len(INSTRUMENTS)
    phdr += name("EOP") + struct.pack("<HHHIII", 0, 0, n, 0, 0, 0)
    pbag += struct.pack("<HH", npgen, 0)
    pgen += gen(0, 0)
    inst += name("EOI") + struct.pack("<H", nibag)
    ibag += struct.pack("<HH", nigen, 0)
    igen += gen(0, 0)
    shdr = (name("Constant") + struct.pack("<IIIIIBbHH", 0, FRAMES, 8, FRAMES - 8, RATE, ROOT, 0, 0, 1)
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
