"""Write a tiny SoundFont for the sfplay pan-endpoint test.

One constant, looped sample (0x1000, 256 frames at 1024 Hz, root key 60) and
four presets, each one instrument with one zone:
  0: instrument zone pan -500 (hard left)
  1: instrument zone pan +500 (hard right)
  2: preset zone -400 + instrument zone -400 (past hard left: clamped)
  3: preset zone +400 + instrument zone +400 (past hard right: clamped)

Usage: python3 make_pan_sf2.py OUT.sf2
"""

import struct
import sys

PAN, INSTRUMENT, SAMPLE_ID, SAMPLE_MODES = 17, 41, 53, 54
FRAMES, RATE, ROOT = 256, 1024, 60

PRESETS = [("Left", None, -500), ("Right", None, 500),
           ("Left, summed", -400, -400), ("Right, summed", 400, 400)]


def chunk(cid: bytes, data: bytes) -> bytes:
    return cid + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")


def lst(kind: bytes, *chunks: bytes) -> bytes:
    return chunk(b"LIST", kind + b"".join(chunks))


def name(s: str) -> bytes:
    return s.encode("ascii")[:19].ljust(20, b"\0")


def gen(oper: int, amount: int) -> bytes:
    return struct.pack("<Hh", oper, amount)


def build() -> bytes:
    info = lst(b"INFO",
               chunk(b"ifil", struct.pack("<HH", 2, 1)),
               chunk(b"isng", b"EMU8000\0"),
               chunk(b"INAM", b"Pan endpoints\0"))
    smpl = struct.pack(f"<{FRAMES + 46}h", *([0x1000] * FRAMES + [0] * 46))
    sdta = lst(b"sdta", chunk(b"smpl", smpl))

    phdr, pbag, pgen = b"", b"", b""
    inst, ibag, igen = b"", b"", b""
    npgen = nigen = 0
    for i, (label, preset_pan, inst_pan) in enumerate(PRESETS):
        phdr += name(label) + struct.pack("<HHHIII", i, 0, i, 0, 0, 0)
        pbag += struct.pack("<HH", npgen, 0)
        gens = ([gen(PAN, preset_pan)] if preset_pan is not None else []) + [gen(INSTRUMENT, i)]
        pgen += b"".join(gens)
        npgen += len(gens)
        inst += name(label) + struct.pack("<H", i)
        ibag += struct.pack("<HH", nigen, 0)
        gens = [gen(PAN, inst_pan), gen(SAMPLE_MODES, 1), gen(SAMPLE_ID, 0)]
        igen += b"".join(gens)
        nigen += len(gens)
    n = len(PRESETS)
    phdr += name("EOP") + struct.pack("<HHHIII", 0, 0, n, 0, 0, 0)
    pbag += struct.pack("<HH", npgen, 0)
    pgen += gen(0, 0)
    inst += name("EOI") + struct.pack("<H", n)
    ibag += struct.pack("<HH", nigen, 0)
    igen += gen(0, 0)
    shdr = (name("Constant") + struct.pack("<IIIIIBbHH", 0, FRAMES, 8, FRAMES - 8, RATE, ROOT, 0, 0, 1)
            + name("EOS") + struct.pack("<IIIIIBbHH", 0, 0, 0, 0, 0, 0, 0, 0, 0))
    pdta = lst(b"pdta",
               chunk(b"phdr", phdr), chunk(b"pbag", pbag), chunk(b"pmod", bytes(10)), chunk(b"pgen", pgen),
               chunk(b"inst", inst), chunk(b"ibag", ibag), chunk(b"imod", bytes(10)), chunk(b"igen", igen),
               chunk(b"shdr", shdr))
    return chunk(b"RIFF", b"sfbk" + info + sdta + pdta)


if __name__ == "__main__":
    data = build()
    with open(sys.argv[1], "wb") as f:
        f.write(data)
    print(f"{sys.argv[1]}: {len(data)} bytes")
