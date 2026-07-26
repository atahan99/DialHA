#!/usr/bin/env python3
"""Decode ESPHome `Received Raw:` IR dumps into bits, nibbles and a checksum.

This is the tool used to reverse-engineer the AC protocol documented in
docs/ac-ir-protocol.md. It is deliberately generic: point it at any capture and
it reports frame length, header timing and the bit stream, so it also works as
the starting point for a different remote.

Capture first (raw dumper ALONE — see docs/ac-ir-protocol.md 3.2, the Pronto
dumper masks `raw` when both are enabled):

    # packages/ac.yaml ->  dump: raw
    esphome logs m5dial.yaml --device <device-ip> | tee raw.txt

Then:

    python scripts/decode_ir.py raw.txt
    python scripts/decode_ir.py raw.txt --since 04:16:00
    python scripts/decode_ir.py raw.txt --one 1530     # custom 1-bit threshold

Positive values are marks (carrier on), negative are spaces.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TS = re.compile(r"\[(\d\d:\d\d:\d\d\.\d+)\]")
NUM = re.compile(r"-?\d+")


def frames(path: Path, since: str | None = None):
    """Yield (timestamp, [signed microseconds]) per captured frame."""
    out: list[tuple[str | None, list[int]]] = []
    cur: list[str] | None = None
    ts: str | None = None
    for line in path.read_text(errors="replace").splitlines():
        stamp = (m := TS.search(line)) and m.group(1)
        if "Received Raw:" in line:
            if cur:
                out.append((ts, cur))
            ts, cur = stamp, NUM.findall(line.split("Received Raw:")[1])
        elif cur is not None and "remote.raw" in line:
            cur += NUM.findall(line.split("]:")[-1])  # continuation line
        elif cur is not None:
            out.append((ts, cur))
            cur = None
    if cur:
        out.append((ts, cur))
    for t, vals in out:
        if since and (t is None or t < since):
            continue
        yield t, [int(v) for v in vals]


def decode(v: list[int], one_us: int) -> tuple[list[int], str]:
    """Split into (header, bitstring). A space longer than one_us is a 1."""
    bits = []
    for i in range(2, len(v) - 1, 2):
        if v[i] <= 0 or v[i + 1] >= 0:
            break  # not a mark/space pair any more
        bits.append("1" if -v[i + 1] > one_us else "0")
    return v[:2], "".join(bits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logfile", type=Path)
    ap.add_argument("--since", help="only frames at/after this HH:MM:SS timestamp")
    ap.add_argument("--one", type=int, default=1000,
                    help="space longer than this (us) is a 1 bit (default 1000)")
    args = ap.parse_args()

    if not args.logfile.exists():
        print(f"no such file: {args.logfile}", file=sys.stderr)
        return 1

    total = good = 0
    for i, (ts, v) in enumerate(frames(args.logfile, args.since)):
        hdr, bits = decode(v, args.one)
        total += 1
        nib = [int(bits[j:j + 4], 2) for j in range(0, len(bits) // 4 * 4, 4)]
        # Generic guess: last nibble is a checksum over the preceding ones
        ck = ""
        if len(nib) >= 2:
            ok = (sum(nib[:-1]) & 0xF) == nib[-1]
            good += ok
            ck = "sum&0xF OK" if ok else "sum&0xF --"
        val = f"0x{int(bits, 2):0{max(1, len(bits) // 4)}X}" if bits else "-"
        print(f"[{i:3}] {ts} pulses={len(v):3} hdr={hdr} bits={len(bits):3} "
              f"{val:>10} nib={''.join(f'{x:X}' for x in nib)} {ck}")

    if total:
        print(f"\n{total} frames; {good} match a (sum of leading nibbles)&0xF checksum")
    else:
        print("no frames found — is the raw dumper enabled *alone*?", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
