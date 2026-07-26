#!/usr/bin/env python3
"""Assert style_definitions exist and every styles: reference is defined."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "packages" / "ui.yaml"


def style_definition_ids(text: str) -> set[str]:
    ids: set[str] = set()
    in_defs = False
    defs_indent = None
    for line in text.splitlines():
        if re.match(r"^(\s*)style_definitions:\s*$", line):
            in_defs = True
            defs_indent = len(re.match(r"^(\s*)", line).group(1))
            continue
        if in_defs:
            if not line.strip() or line.strip().startswith("#"):
                continue
            indent = len(re.match(r"^(\s*)", line).group(1))
            if indent <= defs_indent and re.match(r"^\s*[A-Za-z_][\w-]*:", line):
                break
            m = re.match(r"^\s+-\s+id:\s+(\S+)\s*$", line)
            if m:
                sid = m.group(1).strip("\"'")
                if sid.startswith("st_"):
                    ids.add(sid)
    return ids


def style_references(text: str) -> set[str]:
    refs: set[str] = set()
    for m in re.finditer(r"^\s+styles:\s+([A-Za-z0-9_]+)\s*$", text, re.M):
        refs.add(m.group(1))
    return refs


def main() -> int:
    ui = UI.read_text()
    defined = style_definition_ids(ui)
    if not defined:
        print("FAIL: no style_definitions in ui.yaml")
        return 1
    missing = style_references(ui) - defined
    if missing:
        print(f"FAIL: styles referenced but not defined: {sorted(missing)}")
        return 1
    print(f"OK: {len(defined)} styles defined: {sorted(defined)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
