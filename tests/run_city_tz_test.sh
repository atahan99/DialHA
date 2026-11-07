#!/usr/bin/env bash
# Builds tests/city_tz_test.cpp against the installed ESPHome's posix_tz.cpp and
# runs it on every city_N_tz line in packages/entities.yaml ("POSIX"  # Area/City).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
ESPHOME_DIR="$("$PY" -c 'import esphome, os; print(os.path.dirname(os.path.dirname(esphome.__file__)))')"
OUT="$(mktemp -d)/city_tz_test"
c++ -std=c++17 -DUSE_HOST -I"$ESPHOME_DIR" -I"$ROOT/include" \
  "$ROOT/tests/city_tz_test.cpp" "$ESPHOME_DIR/esphome/components/time/posix_tz.cpp" -o "$OUT"
ZONES=()
while IFS= read -r z; do ZONES+=("$z"); done < <(
  sed -nE 's/^ *city_[0-9]+_tz: *"([^"]+)" *# *([A-Za-z_]+\/[A-Za-z_\/]+).*/\2=\1/p' "$ROOT/packages/entities.yaml")
[[ ${#ZONES[@]} -gt 0 ]] || { echo "no city_N_tz lines found" >&2; exit 1; }
"$OUT" "${ZONES[@]}"
