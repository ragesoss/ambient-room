"""List instrument global zones whose scaleTuning, pan or initialAttenuation
lies outside 0-255 (what Csound's (BYTE) cast keeps).

Usage: python3 -I scan_global_zones.py FONT.sf2 ...
"""

import struct
import sys

NAMES = {21 - 4: "pan", 48: "initialAttenuation", 56: "scaleTuning"}
SAMPLE_ID = 53


def chunks(data: bytes, start: int, end: int):
    i = start
    while i + 8 <= end:
        cid, size = data[i:i + 4], struct.unpack_from("<I", data, i + 4)[0]
        yield cid, i + 8, size
        i += 8 + size + (size & 1)


def pdta(data: bytes) -> dict:
    for cid, off, size in chunks(data, 12, len(data)):
        if cid == b"LIST" and data[off:off + 4] == b"pdta":
            return {c.decode(): data[o:o + s] for c, o, s in chunks(data, off + 4, off + size)}
    raise ValueError("no pdta")


def scan(path: str) -> None:
    with open(path, "rb") as f:
        p = pdta(f.read())
    inst = [struct.unpack_from("<20sH", p["inst"], i) for i in range(0, len(p["inst"]), 22)]
    ibag = [struct.unpack_from("<HH", p["ibag"], i)[0] for i in range(0, len(p["ibag"]), 4)]
    igen = [struct.unpack_from("<Hh", p["igen"], i) for i in range(0, len(p["igen"]), 4)]
    hits, globals_ = [], 0
    for k in range(len(inst) - 1):
        name, b0 = inst[k][0].split(b"\0")[0].decode("latin-1"), inst[k][1]
        b1 = inst[k + 1][1]
        if b1 <= b0:
            continue
        gens = igen[ibag[b0]:ibag[b0 + 1]]
        if any(o == SAMPLE_ID for o, _ in gens):
            continue  # first zone has a sample: no global zone
        globals_ += 1
        bad = [(NAMES[o], a) for o, a in gens if o in NAMES and not 0 <= a <= 255]
        if bad:
            hits.append((name, bad))
    print(f"{path}: {len(inst) - 1} instruments, {globals_} with a global zone, "
          f"{len(hits)} with a value the cast changes")
    for name, bad in hits[:8]:
        print(f"    {name}: " + ", ".join(f"{n} {a}" for n, a in bad))
    if len(hits) > 8:
        print(f"    ... and {len(hits) - 8} more")


if __name__ == "__main__":
  for path in sys.argv[1:]:
    scan(path)
