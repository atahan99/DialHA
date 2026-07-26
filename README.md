# M5Dial — Home Assistant Controller

ESPHome firmware for the [M5Stack Dial](https://docs.m5stack.com/en/core/M5Dial): circular LVGL UI, Home Assistant control, and local IR climate for an Arçelik 09325 A AC via [Unit IR (U002)](https://docs.m5stack.com/en/unit/ir) on PORT.B.

UI look (launcher ring, dial-value screens) takes cues from [M5Dial-UserDemo](https://github.com/m5stack/M5Dial-UserDemo) and [VolosR/M5Dial](https://github.com/VolosR/M5Dial) — ESPHome + LVGL only underneath.

## Hardware

| Piece | Notes |
|-------|--------|
| M5Dial (K130) | ESP32-S3, 240×240 GC9A01, encoder, touch, RTC, RFID, buzzer — **no built-in IR** |
| Unit IR U002 | PORT.B: **TX = G2**, **RX = G1** |
| Power | Stays plugged in (USB or 6–36 V terminal) |
| Stand | [M5Stack Dial Angled Desk Stand with Pen Holder & USB-C Cable Channel](https://www.printables.com/model/1758751-m5stack-dial-angled-desk-stand-with-pen-holder-usb) by MintPrint — 3D printed |

Do **not** enable `psram:` — the module has none.

The stand tilts the Dial toward you for desk use and routes the USB-C cable out
the back, which suits this firmware: the Dial is always powered, so `Rotate` in
Settings flips LVGL 180° to put the physical M5 logo where you want it.

## Build

<!-- Drop photos in docs/images/ using these names and they will appear here. -->

![M5Dial on the printed angled stand](docs/images/build-stand.jpg)

| | |
|---|---|
| ![Clock face](docs/images/ui-clock.jpg) | ![Launcher ring](docs/images/ui-launcher.jpg) |
| ![AC page](docs/images/ui-ac.jpg) | ![Lights page](docs/images/ui-lights.jpg) |

## Home Assistant + ESPHome setup

Current as of ESPHome 2026.7.x. HA renamed **Add-ons → Apps** in 2026.2.

### 1. Install ESPHome Device Builder on HA

1. **Settings → Apps → App store** (`/config/apps/available`)
2. Search **ESPHome** → install **ESPHome Device Builder** (stable)
3. Enable *Start on boot* and *Show in sidebar* → **Start**

### 2. Local CLI (Python venv — keep config in this repo)

```bash
cd m5dial
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Needs Python **3.12–3.14**.

### 3. Secrets

```bash
cp secrets.yaml.example secrets.yaml
```

Fill Wi‑Fi, API encryption key, OTA password, `timezone` (default example `Europe/Istanbul`) and the `latitude` / `longitude` / `weather_place` used for weather. Generate a key:

```bash
openssl rand -base64 32
```

### 4. Entity IDs

Edit [`packages/entities.yaml`](packages/entities.yaml) with your HA `light.*` / `switch.*` / `scene.*` IDs and Dial labels (from **Settings → Devices & services → Entities**). This file is committed (not secret); keep `secrets.yaml` private.

### 5. Build and flash

The HA add-on cannot see USB ports on your Mac, so build locally.

**Build only** (no device needed) — writes `firmware/m5dial.bin`, the *full
factory image* (bootloader + partition table + app, flashable at `0x0`):

```bash
esphome compile m5dial.yaml
cp .esphome/build/m5-dial/build/firmware.factory.bin firmware/m5dial.bin
```

**First flash — USB.** `scripts/flash.sh` does compile → copy → upload in one
step, auto-detecting the port:

```bash
./scripts/flash.sh
./scripts/flash.sh /dev/cu.usbmodem2101   # or name it explicitly
```

**Later flashes — OTA.** Once the Dial is on Wi‑Fi, pass its IP or hostname to
the same script (or to `esphome` directly). OTA is faster and avoids the USB
serial path entirely:

```bash
./scripts/flash.sh 192.168.1.101
esphome run m5dial.yaml --device 192.168.1.101
```

**Flashing the prebuilt image** without ESPHome — the factory bin already
contains the bootloader, so it goes at offset `0x0`:

```bash
esptool --chip esp32s3 --port /dev/cu.usbmodem2101 write_flash 0x0 firmware/m5dial.bin
```

**Logs:**

```bash
esphome logs m5dial.yaml --device 192.168.1.101   # network — preferred
```

#### Troubleshooting

| Symptom | Fix |
|---|---|
| Serial port missing | Hold **BOOT (G0)**, tap **RESET**, release **BOOT**. Port is `/dev/cu.usbmodem*` |
| `waiting for download` after opening USB logs | Opening the port toggles DTR/RTS and drops the S3 into ROM download mode. Recover: `esptool --chip esp32s3 --port /dev/cu.usbmodem2101 run` — then use **network** logs instead |
| `Successfully compiled` but no device found | The Dial must be on the same subnet; try the raw IP rather than `m5-dial.local` |

> **The built `.bin` contains your secrets.** Wi‑Fi SSID and password, OTA and AP
> passwords, the API encryption key and your latitude/longitude are all compiled
> in and recoverable with `strings`. That is why `firmware/*.bin` is gitignored —
> never commit, post or share this file. See [firmware/README.md](firmware/README.md).

### 6. Adopt in Home Assistant (required for toggles)

The Dial can **read** entity state (brightness, on/off) without this. It **cannot** turn lights/plugs/scenes on or off until you enable actions — that fails silently and looks like a firmware bug.

1. **Settings → Devices & services** — wait for mDNS discovery (up to ~5 min) → **Configure** / adopt **M5 Dial**
2. Open the device → **Configure** (gear) → enable **"Allow the device to perform Home Assistant actions"** → **Submit**
3. Tap a light or plug on the Dial once; HA should change. If not, check HA logs for denied `homeassistant.action` calls.

### 7. IR check (Arçelik 09325 A)

The protocol is decoded and **synthesised** — there is nothing to teach, and
nothing to configure. See [`docs/ac-ir-protocol.md`](docs/ac-ir-protocol.md)
for the full reverse-engineering writeup.

```bash
esphome logs m5dial.yaml --device <device-ip>
```

1. **Transmit** — change the temperature on the Dial. After the dial settles the
   log prints `AC sent 0x88089xx`, and the AC should beep. No log line means the
   transmitter never ran; a line with no reaction means the emitter isn't aimed
   at the AC's receiver window (line of sight, ≤5 m).
2. **Receive** — press a button on the physical remote near the Unit IR dome.
   The log prints `remote: ON 24C fan=0` (or `remote: OFF`) and the Dial's
   display follows. Anything rejected says why (`rx reject: 29 bits`,
   `rx reject: length 22`); raise the logger to `DEBUG` to see every capture.

### IR diagnostics

Built in, and worth knowing about before assuming the protocol is wrong:

```bash
python scripts/ac_test.py --host <ip> seq            # scripted on/temp/fan/off
python scripts/ac_test.py --host <ip> sweep-fan 24   # every fan step
python scripts/ac_test.py --host <ip> code 0x88C0051 # one exact frame
```

| Tool | Use |
|---|---|
| `ac_send_code` / `ac_set_state` | send exact frames from a host over the API |
| `ac_loopback` | decode our **own** emission — verifies the transmitted frame bit-for-bit |
| `ac_arm_capture` + `ac_replay` | store a remote frame verbatim and re-emit it, separating wrong bits from wrong timing |
| `ac_set_repeats` | change the repeat count at runtime |
| **IR Beacon** switch (HA) | re-sends state every 2s so you can walk the emitter around and hear where the AC responds |

> If the AC stops responding after a long uptime or many OTA flashes, **reboot
> the Dial**. The ESP32's RMT transmitter has been seen to degrade in that
> situation: frames still leave the device and log normally, but the AC stops
> acting on some of them. A power cycle restored it.

Nothing at all in either direction points at the Unit IR cable/port rather than
the protocol.

## UI

**Default face:** industrial Volos-style tick-ring clock (no brand wordmark). Timezone from secrets; SNTP over Wi‑Fi. Status line shows IP / `NO WIFI`. **Single tap** on the clock wakes the backlight; **double tap** (or the front button) opens the **six-wedge pie launcher** (amber selection): Settings, AC, Plugs, Lights, Time, Scenes. Center **HOME** returns to the clock. Idle dims the clock; **Night** (22:00–08:00) and Display-off sleep as before. **AP** / **Audio** off by default. Every sub-page has an on-screen back arrow.

| Wedge | Page |
|-------|------|
| Settings | Display / Rotate / Network / Audio / Night / AP Fallback |
| AC | Arçelik 09325 A — temperature arc, fan, power (synthesised IR; see below) |
| Lights | 2×2 HA light cards + brightness slider |
| Plugs | HA switches, 4 rows/page, `<`/`>` (or encoder) flips pages |
| Time | Hub ring → one dedicated page each (`packages/time.yaml`) |
| Scenes | HA `scene.*` activators |

Encoder rotates amber focus; front press opens/activates. Entity IDs live in `packages/entities.yaml`.

**Icons:** Material Design Icons, subset to only the glyphs actually used —
37 in `font_icon` (18 px) plus 9 weather glyphs in `font_icon_big` (40 px). Codepoints are verified against upstream `meta.json` — several
are not the obvious value (`clock-outline` is `F0150`, `brightness-6` is
`F00DF`), so don't hand-edit them from memory.

**Round-safe layout:** the panel is a 240 px circle, so a widget whose *corner*
sits beyond r=120 is physically clipped by the glass. `check_ui.py` enforces
r≤114 for every button/slider on every page, plus a 24 px minimum touch height.
This caught 23 real violations — Settings rows were being cut off at r=126.
Outer Settings rows are deliberately narrower than inner ones so the list
follows the circle.

**AC page (09325 A):** cool-only, and **nothing needs teaching**. The protocol was
reverse-engineered from 50 captured frames, so every command is computed on the
fly — see [`docs/ac-ir-protocol.md`](docs/ac-ir-protocol.md).

- Arc shows the target temperature, **18–30°C**
- `ON`/`OFF` chip toggles power; `TEMP` / `FAN` pick what the encoder adjusts
- Fan has six steps: `AUTO`, then 1–5 bars (matching the remote)
- Turning the dial sends **one** frame 400 ms after it settles, not one per detent
- `ac_power` / `ac_temp` / `ac_fan` persist, so state survives reboot and OTA
- Pressing the **physical remote** updates the Dial — the receiver decodes the
  same format and adopts temp/fan/power
- Each command is sent **3×** (`ac_tx_repeats` at the top of `ac.yaml`). Frames
  are absolute state, so repeats are idempotent; this buys range because the
  Unit IR's single LED is far weaker than a handheld remote's

Mode is fixed to COOL. A `component: ac_commit took a long time (~230 ms)`
warning on transmit is expected and harmless: one frame is ~52 ms and we send
three, with the transmitter deliberately blocking (chunked sends get starved by
LVGL). The 400 ms debounce means it fires once per adjustment.

**Aiming matters more than anything in software.** The AC's receiver window is
behind the front panel, pointing *out and slightly down into the room* — so
directly underneath the indoor unit is the worst possible spot, and the emitter
ends up firing at its blind underside. The Unit IR is on a Grove cable and does
not have to sit next to the Dial: mount it where it can see the AC's front
panel, or bounce it off a matte white ceiling. If commands still get missed at
your final position, raise `ac_tx_repeats` to `5` and rebuild.

**`ac.yaml`:** Unit IR TX/RX only — no HA climate entity. The frame format,
capture method and verification are documented in
[`docs/ac-ir-protocol.md`](docs/ac-ir-protocol.md).

**Time hub:** the Time wedge opens a launcher-style ring (Cities, Pomodoro,
Stopwatch, Timer, Weather) with the current time in the middle. Each icon opens
its **own full page** rather than sharing one crowded screen — encoder rotates
the ring, press or tap opens. Inside a page the encoder adjusts that page's
value (city, timer minutes, pomodoro focus length).

```
clock ─tap─► launcher ─Time─► page_time (ring)
                                 ├─ page_cities     ← / →, 5 cities
                                 ├─ page_pomodoro   arc + play/reset
                                 ├─ page_stopwatch  play/reset, 0.1s
                                 ├─ page_timer      − / play / + / reset
                                 └─ page_weather    hero + 3-hourly strip
```

**Cities** (edit in `packages/entities.yaml`):
- `city_1_name` … `city_5_name` + `city_*_utc_offset` + `city_*_dst`
- `city_*_utc_offset` is **standard** time; `city_*_dst` adds the summer hour:
  `0` none, `1` EU (last Sun Mar → last Sun Oct), `2` US/CA (2nd Sun Mar → 1st Sun Nov)
- `home_utc_offset` / `home_dst` must match `secrets.yaml` `timezone`
- Rules live in [`include/tz_dst.h`](include/tz_dst.h) and were checked against
  tzdata for every day of a full year. Day granularity: a city can read an hour
  off for part of the two switchover days.
- **Vancouver is `-7` with `dst: 0`** — British Columbia stopped changing clocks,
  so tzdata puts it on a fixed `-7` from Nov 2026. Don't "fix" it back to `-8`.

**Weather** (`packages/weather.yaml`): current conditions and today's high/low from [Open-Meteo](https://open-meteo.com/en/docs) — no API key, no HA weather entity. Set `latitude` / `longitude` / `weather_place` in `secrets.yaml` for the same place as `timezone`; the API's `timezone=auto` derives the local day from those coordinates. Refresh is every 15 min; the refresh button on the Weather page forces one. The page also shows a 3-hourly outlook for the rest of the day (hour, condition icon, temperature) starting at the next 3-hour boundary.

**Settings persistence:** Rotate / Night / AP fallback / UI sound are stored by
[`include/settings_store.h`](include/settings_store.h), **not** by
`restore_value: true`. ESPHome's restoring globals are a `PollingComponent(1000)`
— they stage the value on a 1 Hz poll and only reach flash on the next
preferences flush, so a setting changed just before the power is pulled is lost
(a clean reboot hides this, because `on_shutdown()` saves). `store_now()` stages
and commits in one call, so the value is in NVS before the tap returns. AC state
(`ac_power` / `ac_temp` / `ac_fan`) still uses `restore_value` and keeps the
small window — harmless, since the Dial re-syncs from the physical remote.

**Rotate** (Settings): steps LVGL through `0°` → `90°` → `180°` → `270°` so the physical M5 logo and the encoder sit where you want on a stand. LVGL rotates touch input to match, and the setting persists across reboots.

## Checks

```bash
source .venv/bin/activate
python check_themes.py
python check_ui.py
esphome config m5dial.yaml
```

## Layout

```
m5dial.yaml              # entry
secrets.yaml.example
requirements.txt
check_themes.py
scripts/
  flash.sh                # compile → firmware/m5dial.bin → upload (USB or OTA)
  decode_ir.py            # decode ESPHome raw IR dumps (used for the AC protocol)
  ac_test.py              # drive the AC over the API for bench testing
firmware/                # full factory .bin (gitignored) + README
include/
  wx_icons.h              # WMO code -> weather glyph / word
  tz_dst.h                # EU + US daylight-saving rules
  settings_store.h        # immediate-write NVS persistence for UI settings
docs/
  ac-ir-protocol.md       # how the IR protocol was decoded
  images/                 # build + UI photos shown in this README
packages/
  hardware.yaml
  entities.yaml           # HA entity IDs + cities (committed)
  ac.yaml                 # Arcelik frame synthesiser + receive-sync
  time.yaml
  weather.yaml            # Open-Meteo fetch (coords from secrets.yaml)
  ui.yaml
```
