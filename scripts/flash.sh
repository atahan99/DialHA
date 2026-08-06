#!/usr/bin/env bash
# Compile → copy firmware/dialha.bin → upload over USB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ESPHOME="${ESPHOME:-}"
if [[ -z "$ESPHOME" ]]; then
  if [[ -x /tmp/m5dial-venv/bin/esphome ]]; then
    ESPHOME=/tmp/m5dial-venv/bin/esphome
  elif [[ -x "$ROOT/.venv/bin/esphome" ]]; then
    ESPHOME="$ROOT/.venv/bin/esphome"
  elif command -v esphome >/dev/null 2>&1; then
    ESPHOME="$(command -v esphome)"
  else
    echo "esphome not found. Activate a venv or set ESPHOME=..." >&2
    exit 1
  fi
fi

DEVICE="${1:-}"
if [[ -z "$DEVICE" ]]; then
  for p in /dev/cu.usbmodem* /dev/tty.usbmodem*; do
    if [[ -e "$p" ]]; then
      DEVICE="$p"
      break
    fi
  done
fi
if [[ -z "$DEVICE" ]]; then
  echo "No USB serial device found. Pass one: $0 /dev/cu.usbmodemXXXX" >&2
  exit 1
fi

mkdir -p "$ROOT/firmware"
echo "Using esphome: $ESPHOME"
echo "Device: $DEVICE"

"$ESPHOME" compile "$ROOT/m5dial.yaml"

BUILD_BIN=""
for cand in \
  "$ROOT/.esphome/build/m5-dial/build/firmware.factory.bin" \
  "$ROOT/.esphome/build/m5-dial/build/m5-dial.bin" \
  "$ROOT/.esphome/build/m5-dial/build/firmware.ota.bin" \
  "$ROOT/.esphome/build/m5-dial/.pioenvs/m5-dial/firmware.bin"
do
  if [[ -f "$cand" ]]; then
    BUILD_BIN="$cand"
    break
  fi
done
if [[ -z "$BUILD_BIN" ]]; then
  BUILD_BIN="$(find "$ROOT/.esphome/build/m5-dial" \( -name 'firmware.factory.bin' -o -name 'm5-dial.bin' -o -name 'firmware.bin' \) -type f 2>/dev/null | head -n 1 || true)"
fi
if [[ -z "$BUILD_BIN" || ! -f "$BUILD_BIN" ]]; then
  echo "Could not locate built binary under .esphome/build/m5-dial" >&2
  exit 1
fi

cp -f "$BUILD_BIN" "$ROOT/firmware/dialha.bin"
echo "Copied $(basename "$BUILD_BIN") → firmware/dialha.bin ($(wc -c < "$ROOT/firmware/dialha.bin") bytes)"

"$ESPHOME" upload "$ROOT/m5dial.yaml" --device "$DEVICE"
echo "Flash OK."