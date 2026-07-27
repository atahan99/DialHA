#!/usr/bin/env python3
"""Drive the Dial and see what it drew, over the ESPHome API.

Lets a host (or an agent) work the UI without a finger on the glass: press the
same four inputs the hardware has, grab the screen as a PNG, and read the log.

    python scripts/dial.py shot                     # -> shot.png
    python scripts/dial.py key press cw:3 press     # sequence, cw:3 = 3 detents
    python scripts/dial.py key back shot            # keys then a screenshot
    python scripts/dial.py logs -s 20               # stream the log for 20s

Keys are cw / ccw / press / back — the encoder, the front button and the side
button. Reads the API key from secrets.yaml; nothing is printed from that file.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import socket
import struct
import sys
import zlib
from pathlib import Path

from aioesphomeapi import APIClient

ROOT = Path(__file__).resolve().parent.parent
W = H = 240
KEYS = ("cw", "ccw", "press", "back")


def api_key() -> str:
    text = (ROOT / "secrets.yaml").read_text()
    m = re.search(r"^api_encryption_key:\s*[\"']?([A-Za-z0-9+/=]+)", text, re.M)
    if not m:
        sys.exit("api_encryption_key not found in secrets.yaml")
    return m.group(1)


def write_png(path: Path, pixels: bytearray) -> None:
    """Minimal RGB888 PNG. Pillow is not a dependency and one filter-0 scanline
    per row compresses fine for flat UI screenshots."""
    raw = b"".join(b"\x00" + bytes(pixels[y * W * 3:(y + 1) * W * 3]) for y in range(H))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def blit(pixels: bytearray, stream: bytes) -> int:
    """Unpack the tile stream from include/agent.h into an RGB888 image.

    Each tile is 4 x int16 LE (x1, y1, x2, y2) then big-endian RGB565 pixels
    (LVGL is built with LV_COLOR_16_SWAP=1). Returns the tile count."""
    pos = tiles = 0
    while pos + 8 <= len(stream):
        x1, y1, x2, y2 = struct.unpack_from("<4h", stream, pos)
        pos += 8
        tw, th = x2 - x1 + 1, y2 - y1 + 1
        end = pos + tw * th * 2
        if tw <= 0 or th <= 0 or end > len(stream):
            break
        for row in range(th):
            out = ((y1 + row) * W + x1) * 3
            for col in range(tw):
                v = (stream[pos] << 8) | stream[pos + 1]
                pos += 2
                pixels[out] = ((v >> 11) & 0x1F) * 255 // 31
                pixels[out + 1] = ((v >> 5) & 0x3F) * 255 // 63
                pixels[out + 2] = (v & 0x1F) * 255 // 31
                out += 3
        tiles += 1
    return tiles


async def shot(cli: APIClient, actions: dict, host: str, out: Path) -> None:
    listener = socket.socket()
    listener.bind(("", 0))
    listener.listen(1)
    listener.settimeout(10)
    port = listener.getsockname()[1]

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.connect((host, 6053))  # no packets sent; just asks the routing table
    my_ip = probe.getsockname()[0]
    probe.close()

    await cli.execute_service(actions["ui_screenshot"], {"host": my_ip, "port": port})
    try:
        conn, _ = listener.accept()
    except socket.timeout:
        sys.exit(f"device never connected back to {my_ip}:{port} — firewall?")
    conn.settimeout(10)
    parts = []
    while chunk := conn.recv(65536):
        parts.append(chunk)
    conn.close()
    listener.close()

    pixels = bytearray(W * H * 3)
    tiles = blit(pixels, b"".join(parts))
    write_png(out, pixels)
    print(f"{out}  ({tiles} tiles, {sum(map(len, parts))} bytes)")


async def run(args) -> int:
    cli = APIClient(args.host, 6053, None, noise_psk=api_key())
    await cli.connect(login=True)
    try:
        actions = {s.name: s for s in (await cli.list_entities_services())[1]}
        for want in ("ui_key", "ui_screenshot"):
            if want not in actions:
                sys.exit(f"device does not expose {want} — flash the current firmware")

        if args.cmd == "logs":
            cli.subscribe_logs(lambda m: print(m.message.decode(errors="replace")))
            await asyncio.sleep(args.seconds)
            return 0

        shots = 0
        for token in args.sequence:
            if token == "shot":
                shots += 1
                out = args.out if shots == 1 else args.out.with_stem(f"{args.out.stem}-{shots}")
                await shot(cli, actions, args.host, out)
                continue
            name, _, count = token.partition(":")
            if name not in KEYS:
                sys.exit(f"unknown key {name!r} — use {'/'.join(KEYS)} or 'shot'")
            n = int(count or 1)
            await cli.execute_service(actions["ui_key"], {"key": name, "n": n})
            print(f"{name} x{n}")
            await asyncio.sleep(0.2 + 0.06 * n)
    finally:
        await cli.disconnect()
    return 0


def selftest() -> int:
    """blit() is the only real logic here — check it against a hand-built stream."""
    tile = struct.pack("<4h", 2, 1, 3, 1)  # x 2..3, y 1, two pixels
    tile += struct.pack(">2H", 0xF800, 0x001F)  # pure red, pure blue
    pixels = bytearray(W * H * 3)
    assert blit(pixels, tile) == 1
    at = lambda x, y: tuple(pixels[(y * W + x) * 3:(y * W + x) * 3 + 3])
    assert at(2, 1) == (255, 0, 0), at(2, 1)
    assert at(3, 1) == (0, 0, 255), at(3, 1)
    assert at(1, 1) == (0, 0, 0), "wrote outside the tile"
    assert blit(bytearray(W * H * 3), tile[:-1]) == 0, "truncated tile must be dropped"
    print("OK")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="m5-dial.local")
    p.add_argument("-o", "--out", type=Path, default=Path("shot.png"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("shot")
    k = sub.add_parser("key")
    k.add_argument("sequence", nargs="+", metavar="KEY[:N]|shot")
    lg = sub.add_parser("logs")
    lg.add_argument("-s", "--seconds", type=float, default=15)
    sub.add_parser("selftest")
    args = p.parse_args()
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "shot":
        args.sequence = ["shot"]
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
