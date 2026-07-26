#!/usr/bin/env python3
"""Drive the Dial's AC over the ESPHome API, for bench-testing IR.

Lets a host send exact frames and watch the device log, so protocol behaviour
can be separated from marginal IR range without touching the Dial.

    python scripts/ac_test.py --host 192.168.1.101 code 0x88C0051
    python scripts/ac_test.py --host 192.168.1.101 state 24 0      # 24C, AUTO
    python scripts/ac_test.py --host 192.168.1.101 sweep-fan 24    # all 6 fans
    python scripts/ac_test.py --host 192.168.1.101 seq             # scripted test

Reads the API key from secrets.yaml; nothing is printed from that file.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

from aioesphomeapi import APIClient

ROOT = Path(__file__).resolve().parent.parent
FAN_NAMES = ["AUTO", "1 bar", "2 bar", "3 bar", "4 bar", "5 bar"]
FAN_CODES = [5, 0, 9, 2, 0xA, 4]


def api_key() -> str:
    text = (ROOT / "secrets.yaml").read_text()
    m = re.search(r"^api_encryption_key:\s*[\"']?([A-Za-z0-9+/=]+)", text, re.M)
    if not m:
        sys.exit("api_encryption_key not found in secrets.yaml")
    return m.group(1)


def build(n3: int, temp: int, fan: int) -> int:
    """Same frame builder as packages/ac.yaml, for predicting what we send."""
    nib = [8, 8, 0, n3, temp - 15, FAN_CODES[fan], 0]
    nib[6] = sum(nib[:6]) & 0xF
    v = 0
    for n in nib:
        v = (v << 4) | n
    return v


async def run(host: str, args) -> int:
    cli = APIClient(host, 6053, None, noise_psk=api_key())
    await cli.connect(login=True)
    try:
        actions = {s.name: s for s in (await cli.list_entities_services())[1]}
        for want in ("ac_send_code", "ac_set_state"):
            if want not in actions:
                sys.exit(f"device does not expose {want} — flash the current firmware")

        async def send_code(code: int, label: str = ""):
            print(f"  -> 0x{code:07X}  {label}")
            await cli.execute_service(actions["ac_send_code"], {"code": code})
            await asyncio.sleep(args.gap)

        async def send_state(temp: int, fan: int, n3: int = 8):
            code = build(n3, temp, fan)
            label = f"{temp}C fan={fan} ({FAN_NAMES[fan]}) n3={n3}"
            print(f"  -> 0x{code:07X}  {label}")
            await cli.execute_service(actions["ac_set_state"],
                                {"temp": temp, "fan": fan, "n3": n3})
            await asyncio.sleep(args.gap)

        if args.cmd == "code":
            await send_code(int(args.value, 0))
        elif args.cmd == "state":
            await send_state(args.temp, args.fan, args.n3)
        elif args.cmd == "sweep-fan":
            print(f"fan sweep at {args.temp}C — listen for the AC on each step")
            for f in range(6):
                await send_state(args.temp, f)
        elif args.cmd == "seq":
            print("scripted sequence — note what the AC does after each line")
            await send_code(0x88C0051, "OFF literal")
            await send_state(24, 1, n3=0)          # power on, 24C, 1 bar
            await send_state(24, 1)                # adjust, same state
            await send_state(26, 1)                # temp change only
            await send_state(26, 0)                # fan change only -> the suspect
            await send_state(26, 1)                # fan back
            await send_code(0x88C0051, "OFF literal again")
    finally:
        await cli.disconnect()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="192.168.1.101")
    p.add_argument("--gap", type=float, default=3.0, help="seconds between frames")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("code"); c.add_argument("value")
    s = sub.add_parser("state")
    s.add_argument("temp", type=int); s.add_argument("fan", type=int)
    s.add_argument("--n3", type=int, default=8)
    w = sub.add_parser("sweep-fan"); w.add_argument("temp", type=int, nargs="?", default=24)
    sub.add_parser("seq")
    args = p.parse_args()
    return asyncio.run(run(args.host, args))


if __name__ == "__main__":
    raise SystemExit(main())
