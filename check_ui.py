#!/usr/bin/env python3
"""Assert Volos industrial UI invariants in YAML (no device needed)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ui = (ROOT / "packages" / "ui.yaml").read_text()
hw = (ROOT / "packages" / "hardware.yaml").read_text()
ent_path = ROOT / "packages" / "entities.yaml"
if not ent_path.exists():
    print("FAIL:\n  packages/entities.yaml missing")
    sys.exit(1)
ent = ent_path.read_text()
ex = (ROOT / "secrets.yaml.example").read_text()
main = (ROOT / "m5dial.yaml").read_text()

fails: list[str] = []

if "theme.yaml" in main or "packages/theme" in main:
    fails.append("theme package should be removed from m5dial.yaml")
if (ROOT / "packages" / "theme.yaml").exists():
    fails.append("packages/theme.yaml should be deleted")

if "ui_sound_enabled" not in ui or 'initial_value: "false"' not in ui:
    fails.append("ui_sound_enabled missing or not default false")
if "id: ui_beep" not in ui:
    fails.append("ui_beep script missing")
if re.search(r"^\s+- rtttl\.play:", ui, re.M):
    fails.append("ui.yaml still has direct rtttl.play")
if re.search(r"^\s+- rtttl\.play:", hw, re.M):
    fails.append("hardware.yaml still has direct rtttl.play")

for bid in (
    "btn_seg_settings",
    "btn_seg_ac",
    "btn_seg_plugs",
    "btn_seg_lights",
    "btn_seg_time",
    "btn_seg_scenes",
    "btn_home_center",
):
    if bid not in ui:
        fails.append(f"pie launcher missing {bid}")

if "page_scenes" not in ui:
    fails.append("page_scenes missing")
if "lbl_clock_brand" in ui or 'text: "DIAL"' in ui or 'text: "VOLOS"' in ui:
    fails.append("brand wordmark still present on clock")
if "id: clock_meter" not in ui:
    fails.append("clock_meter missing")
if "bg_color: 0x0B0F11" not in ui:
    fails.append("Volos background token missing")
if "0xFFD400" not in ui:
    fails.append("amber selection token missing")
if "scene_1_entity" not in ent:
    fails.append("entities.yaml missing scene substitutions")
if "light_4_entity" not in ent:
    fails.append("entities.yaml missing light_3/4")
if "timezone: !secret timezone" not in hw:
    fails.append("hardware.yaml missing timezone secret")
if "platform: sntp" not in hw:
    fails.append("SNTP time source missing")
if 'timezone:' not in ex:
    fails.append("secrets.yaml.example missing timezone")
if "theme_cyberpunk" in ui or "toggle_theme" in ui:
    fails.append("cyberpunk theme remnants still in ui.yaml")
if "lbl_launcher_sel" in ui:
    fails.append("launcher selection title should be removed")
if "display_rotation" not in ui or "row_set_rotate" not in ui:
    fails.append("Rotate setting missing")
if "id: ac_refresh" not in ui or "lbl_ac_main" not in ui:
    fails.append("AC refresh / main label missing")
if "btn_ac_focus_fan" not in ui or "ac_dial_adjust" not in ui:
    fails.append("AC fan/swing dial focus missing")
tm = (ROOT / "packages" / "time.yaml").read_text()
for s in ("cities_refresh", "pomo_refresh", "sw_refresh", "timer_refresh",
          "weather_refresh", "time_hub_focus"):
    if f"id: {s}" not in tm:
        fails.append(f"time.yaml missing {s} script")
if "id: time_mode" in tm:
    fails.append("time_mode is superseded by one-page-per-function navigation")
for pg in ("page_cities", "page_pomodoro", "page_stopwatch", "page_timer", "page_weather"):
    if f"- id: {pg}" not in ui:
        fails.append(f"{pg} missing")
if "city_1_name" not in ent or "home_utc_offset" not in ent:
    fails.append("entities missing configurable cities")
if "ha_weather" in ent:
    fails.append("HA weather entities should be gone (Open-Meteo now)")

wx = (ROOT / "packages" / "weather.yaml").read_text()
if "api.open-meteo.com" not in wx or "!secret latitude" not in wx:
    fails.append("weather.yaml missing Open-Meteo request / secret coordinates")
if "packages/weather.yaml" not in main:
    fails.append("weather package not included in m5dial.yaml")
for key in ("latitude:", "longitude:", "weather_place:"):
    if key not in ex:
        fails.append(f"secrets.yaml.example missing {key}")

ac = (ROOT / "packages" / "ac.yaml").read_text()
if "non_blocking: false" not in ac:
    fails.append("IR transmitter must send blocking (LVGL starves chunked sends)")
if "transmit_raw" not in ac or "ac_tx_code" not in ac:
    fails.append("AC frame synthesiser missing from ac.yaml")
if "0x88C0051" not in ac:
    fails.append("Arcelik OFF literal missing from ac.yaml")
if "sum & 0xF" not in ac:
    fails.append("Arcelik checksum (sum of first six nibbles) missing")
for gid in ("ac_power", "ac_temp", "ac_fan"):
    if f"id: {gid}" not in ac:
        fails.append(f"AC state global {gid} missing")
# Settings must survive an immediate power cut, so they persist through
# settings_store.h rather than restore_value (which only stages on a 1 Hz poll).
def strip_comments(text: str) -> str:
    """Drop whole-line YAML comments so prose about a setting isn't mistaken for it."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


if "restore_value" in strip_comments(ac):
    fails.append("ac.yaml should persist via settings_store.h, not restore_value")
if "id: ac_persist" not in ac or "m5dial::commit()" not in ac:
    fails.append("ac.yaml missing the ac_persist script")
store = (ROOT / "include" / "settings_store.h").read_text()
for key in ("KEY_ROTATION", "KEY_NIGHT", "KEY_AP", "KEY_SOUND",
            "KEY_AC_POWER", "KEY_AC_TEMP", "KEY_AC_FAN"):
    if key not in store:
        fails.append(f"settings_store.h missing {key}")
    if key not in ui and key not in ac:
        fails.append(f"{key} is defined but never used")
if "restore_value: true" in strip_comments(ui):
    fails.append("ui.yaml globals should persist via settings_store.h")
if "ac_learning" in ac or "ir_cool_temps" in ac:
    fails.append("raw learn/replay is superseded by the synthesiser")
if "platform: coolix" in ac:
    fails.append("Coolix is the wrong protocol for 09325 A")
# The encoder must be able to reach every settings row.
n_rows = len(re.findall(r"id: row_set_\w+", strip_comments(ui))) // 2
if n_rows and f"% {n_rows};" not in ui:
    fails.append(f"settings has {n_rows} rows but the encoder does not wrap at {n_rows}")
if "id: set_list" not in ui or "scroll_dir: VER" not in ui:
    fails.append("settings list should be a vertical scroll container")
for lbl in ("lbl_clock_mon", "lbl_clock_ampm", "id: clock_scale"):
    if lbl not in ui:
        fails.append(f"clock face missing {lbl}")
if "ac_commit" not in ui:
    fails.append("encoder must debounce through ac_commit, not send per detent")

page_ac = ui.split("- id: page_ac", 1)[1].split("\n    - id: page_", 1)[0]
if "id: arc_ac" not in page_ac:
    fails.append("AC page missing temperature arc")
if "id: bar_ac" in page_ac:
    fails.append("AC bar should be replaced by the arc gauge")
if "id: btn_ac_power" not in page_ac or "ac_power_toggle" not in page_ac:
    fails.append("AC page missing power toggle")
if "°C" not in ui:
    fails.append("AC must show °C (spec: Celsius with degree sign)")

# Round display: the panel is a 240px circle (r=120), so the *corner* of every
# widget must stay inside it or it is physically clipped by the glass. Budget
# r<=114 leaves a little margin for the bezel. Applies to every page.
# btn_clock_wake is the deliberate full-screen tap target and is exempt.
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
            fails.append(
                f"{page_name}: {name} corner at r={radius:.0f} is clipped by the round display"
            )
        if kind == "button" and geom["height"] < MIN_TOUCH_H:
            fails.append(
                f"{page_name}: {name} is only {geom['height']}px tall (min {MIN_TOUCH_H} for touch)"
            )

if fails:
    print("FAIL:")
    for f in fails:
        print(" ", f)
    sys.exit(1)
print("OK: ui invariants hold")
sys.exit(0)
