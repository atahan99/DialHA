#!/usr/bin/env python3
"""Assert the UI invariants that cost real debugging time. No device needed.

Each check below exists because breaking it produced a bug that was not
obvious from the YAML — not to police style. `python check_ui.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "packages" / "ui"
# base.yaml first: it holds style_definitions, which later checks refer to
ui = "\n".join(p.read_text() for p in sorted(UI_DIR.glob("*.yaml"), key=lambda p: p.name != "base.yaml"))
hw = (ROOT / "packages" / "hardware.yaml").read_text()
ac = (ROOT / "packages" / "ac.yaml").read_text()
tm = (ROOT / "packages" / "time.yaml").read_text()
wx = (ROOT / "packages" / "weather.yaml").read_text()
ent = (ROOT / "packages" / "entities.yaml").read_text()
ex = (ROOT / "secrets.yaml.example").read_text()
main = (ROOT / "m5dial.yaml").read_text()
debug = (ROOT / "packages" / "debug.yaml").read_text()

fails: list[str] = []


def strip_comments(text: str) -> str:
    """Drop whole-line YAML comments so prose about a rule isn't read as the rule."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


# —— Styles ————————————————————————————————————————————————————————
# Every `styles: st_x` must name a real style_definitions entry; a typo is
# silently ignored by LVGL and the widget just renders unstyled.
defined = set()
in_defs = False
defs_indent = 0
for line in ui.splitlines():
    if re.match(r"^(\s*)style_definitions:\s*$", line):
        in_defs, defs_indent = True, len(line) - len(line.lstrip())
        continue
    if in_defs:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= defs_indent and re.match(r"^\s*[A-Za-z_][\w-]*:", line):
            break
        if m := re.match(r"^\s+-\s+id:\s+(st_\S+)\s*$", line):
            defined.add(m.group(1).strip("\"'"))
if not defined:
    fails.append("no style_definitions in packages/ui/base.yaml")
for ref in set(re.findall(r"^\s+styles:\s+([A-Za-z0-9_]+)\s*$", ui, re.M)) - defined:
    fails.append(f"styles: {ref} is referenced but never defined")

# —— Input model ———————————————————————————————————————————————————
# The encoder and buttons drive scripts directly. An `encoders:` indev adds a
# second, invisible selection (LVGL group focus) on top of the *_index globals
# that actually paint the amber border — and ESPHome puts every widget of every
# page in one flat group, so focus wanders onto other pages' widgets and the
# front button clicks them.
if re.search(r"^\s+encoders:", ui, re.M):
    fails.append("lvgl encoders: reintroduces a second selection model — see the note in packages/ui/base.yaml")
if "dial_group" in ui:
    fails.append("group: dial_group reintroduces LVGL group focus")

# front_action must dispatch on a snapshot of the page. Its handlers navigate,
# so a live `lvgl.page.is_showing` chain fires the *new* page's handler in the
# same press (one click on the launcher used to land on Cities).
front = strip_comments(ui.split("- id: front_action", 1)[1].split("\n  - id: ", 1)[0])
if "lvgl.page.is_showing" in front:
    fails.append("front_action must test id(front_page), not lvgl.page.is_showing")
if "front_page) = lv_screen_active()" not in front:
    fails.append("front_action must snapshot the active page first")

# The encoder must be able to reach every settings row.
n_rows = len(re.findall(r"id: row_set_\w+", strip_comments(ui))) // 2
if n_rows and f"% {n_rows};" not in ui:
    fails.append(f"settings has {n_rows} rows but the encoder does not wrap at {n_rows}")

# Lights: the dial sets brightness, and a card tap selects before it toggles
# (see README "Lights"). Wiring a card straight to light_toggle skips the
# select-first step.
if "light_bri_step" not in ui:
    fails.append("the Lights page dial should drive brightness via light_bri_step")
lights_page = ui.split("- id: page_lights", 1)[1].split("\n    - id: page_", 1)[0]
if "light_toggle" in lights_page or lights_page.count("light_card_tap") != 4:
    fails.append("each light card should go through light_card_tap, not light_toggle")
if re.search(r"page_lights\n\s+then:\n\s+- lambda: \"id\(light_index\)", ui):
    fails.append("the encoder should no longer move the Lights selection")

# —— Agent bridge ——————————————————————————————————————————————————
for action in ("ui_key", "ui_screenshot", "ac_send_code", "ac_set_state"):
    if f"action: {action}" not in debug:
        fails.append(f"api action {action} missing from debug.yaml; scripts/ need it")
if "include/agent.h" not in debug or "debug.yaml" not in main:
    fails.append("the personal build must include packages/debug.yaml (agent.h)")

# —— Public build ——————————————————————————————————————————————————
# dialha.factory.yaml is published, so nothing it pulls in may read secrets.yaml.
factory = (ROOT / "dialha.factory.yaml").read_text()
for path in [ROOT / "dialha.factory.yaml", *sorted((ROOT / "packages").rglob("*.yaml"))]:
    if path.name != "debug.yaml" and "!secret" in strip_comments(path.read_text()):
        fails.append(f"{path.relative_to(ROOT)} uses !secret; the public build would need secrets.yaml")
if "debug.yaml" in factory:
    fails.append("dialha.factory.yaml must not include the debug package")
# Without credentials, the public build must not accept firmware from the
# network: no password-less esphome OTA, and no captive portal (it serves an
# upload form on an open hotspot).
core = (ROOT / "packages" / "core.yaml").read_text()
public = strip_comments(factory + core)
if "captive_portal" in public or re.search(r"^\s*ap:", public, re.M):
    fails.append("public build must not open a hotspot / captive portal")
if "platform: esphome" in public:
    fails.append("public build must not use password-less esphome OTA")

# —— Persistence ———————————————————————————————————————————————————
# Settings must survive an immediate power cut, so they persist through
# settings_store.h rather than restore_value (which only stages on a 1 Hz poll).
if "restore_value" in strip_comments(ac):
    fails.append("ac.yaml should persist via settings_store.h, not restore_value")
if "restore_value: true" in strip_comments(ui):
    fails.append("ui globals should persist via settings_store.h")
if "id: ac_persist" not in ac or "m5dial::commit()" not in ac:
    fails.append("ac.yaml missing the ac_persist script")
store = (ROOT / "include" / "settings_store.h").read_text()
for key in ("KEY_ROTATION", "KEY_NIGHT", "KEY_AP", "KEY_SOUND",
            "KEY_AC_POWER", "KEY_AC_TEMP", "KEY_AC_FAN"):
    if key not in store:
        fails.append(f"settings_store.h missing {key}")
    if key not in ui and key not in ac:
        fails.append(f"{key} is defined but never used")

# —— AC / IR ———————————————————————————————————————————————————————
if "non_blocking: false" not in ac:
    fails.append("IR transmitter must send blocking (LVGL starves chunked sends)")
if "transmit_raw" not in ac or "ac_tx_code" not in ac:
    fails.append("AC frame synthesiser missing from ac.yaml")
if "0x88C0051" not in ac:
    fails.append("Arcelik OFF literal missing from ac.yaml")
if "sum & 0xF" not in ac:
    fails.append("Arcelik checksum (sum of first six nibbles) missing")
if "bits < 28" not in ac:
    fails.append("the receive decoder must stop at 28 bits or it invents a 29th")
for gid in ("ac_power", "ac_temp", "ac_fan"):
    if f"id: {gid}" not in ac:
        fails.append(f"AC state global {gid} missing")
if "ac_commit" not in ui:
    fails.append("encoder must debounce through ac_commit, not send per detent")

# —— Pages and sources —————————————————————————————————————————————
for pg in ("page_clock", "page_launcher", "page_ac", "page_lights", "page_plugs",
           "page_scenes", "page_settings", "page_time", "page_cities",
           "page_pomodoro", "page_stopwatch", "page_timer", "page_weather"):
    if f"- id: {pg}" not in ui:
        fails.append(f"{pg} missing")
for s in ("cities_refresh", "pomo_refresh", "sw_refresh", "timer_refresh",
          "weather_refresh", "time_hub_focus"):
    if f"id: {s}" not in tm:
        fails.append(f"time.yaml missing {s} script")
if "platform: sntp" not in hw:
    fails.append("hardware.yaml missing SNTP")
# A timezone: on any time source pins it; without one, Home Assistant sends its
# zone on connect and the Dial follows it.
if "timezone:" in strip_comments(hw):
    fails.append("hardware.yaml should not pin a timezone (HA provides it)")
if "api.open-meteo.com" not in wx or "zone.home" not in wx:
    fails.append("weather.yaml should fetch Open-Meteo for HA's zone.home")
for key in ("wifi_ssid:", "wifi_password:", "api_encryption_key:", "ota_password:", "ap_password:"):
    if key not in ex:
        fails.append(f"secrets.yaml.example missing {key}")
for key in ("scene_1_entity", "light_4_entity", "city_1_name", "city_1_tz"):
    if key not in ent:
        fails.append(f"entities.yaml missing {key}")

# —— Round display geometry ————————————————————————————————————————
# The panel is a 240px circle (r=120), so the *corner* of every widget must stay
# inside it or the glass physically clips it. r<=114 leaves margin for the
# bezel. btn_clock_wake is the deliberate full-screen tap target.
EXEMPT = {"btn_clock_wake"}
MIN_TOUCH_H = 24  # comfortable finger target

for page_name, body in zip(*[iter(re.split(r"\n    - id: (page_\w+)", ui)[1:])] * 2):
    for block in re.split(r"\n        - (?=\w+:)", body)[1:]:
        kind = block.split(":", 1)[0]
        if kind not in ("button", "slider") or "align: CENTER" not in block:
            continue
        geom = {
            key: int(m.group(1))
            for key in ("width", "height", "x", "y")
            if (m := re.search(rf"^            {key}: (-?\d+)$", block, re.M))
        }
        if "width" not in geom or "height" not in geom:
            continue
        name = (m := re.search(r"id: (\w+)", block)) and m.group(1) or "?"
        if name in EXEMPT:
            continue
        dx = abs(geom.get("x", 0)) + geom["width"] / 2
        dy = abs(geom.get("y", 0)) + geom["height"] / 2
        radius = (dx * dx + dy * dy) ** 0.5
        if radius > 114:
            fails.append(f"{page_name}: {name} corner at r={radius:.0f} is clipped by the round display")
        if kind == "button" and geom["height"] < MIN_TOUCH_H:
            fails.append(f"{page_name}: {name} is only {geom['height']}px tall (min {MIN_TOUCH_H} for touch)")

if fails:
    print("FAIL:")
    for f in fails:
        print(" ", f)
    sys.exit(1)
print(f"OK: ui invariants hold ({len(defined)} styles defined)")
