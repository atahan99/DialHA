# M5Dial — Home Assistant Controller

ESPHome firmware for the [M5Stack Dial](https://docs.m5stack.com/en/core/M5Dial): circular LVGL UI, Home Assistant control, and local IR climate for an Arçelik 09325 A AC via [Unit IR (U002)](https://docs.m5stack.com/en/unit/ir) on PORT.B.

UI cues from [M5Dial-UserDemo](https://github.com/m5stack/M5Dial-UserDemo) and [VolosR/M5Dial](https://github.com/VolosR/M5Dial) — ESPHome + LVGL only underneath.

**Core:** clock face, Weather, Pomodoro, Timer, Lights

![Core UI — clock, weather, pomodoro, timer, lights](docs/images/core-ui-showcase.png)

**Controls:** launcher ring, AC, Plugs, Settings, Scenes

![Controls UI — launcher, AC, plugs, settings, scenes](docs/images/controls-ui-showcase.png)

## Hardware

| Piece | Notes |
|-------|--------|
| M5Dial (K130) | ESP32-S3, 240×240 GC9A01, encoder, touch, RTC, RFID, buzzer — **no built-in IR** |
| Unit IR U002 | PORT.B: **TX = G2**, **RX = G1** |
| Power | Stays plugged in (USB or 6–36 V terminal) |
| Stand | [Angled Desk Stand with Pen Holder & USB-C Cable Channel](https://www.printables.com/model/1758751-m5stack-dial-angled-desk-stand-with-pen-holder-usb) by MintPrint — 3D printed |
| USB-C 90° adapter | Effectively required with that stand — a straight cable does not fit the channel, and the workaround (rotating the Dial 90°) puts the cable out the side |

Do **not** enable `psram:` — the module has none. That is also why there is no
framebuffer to copy for screenshots; see [Driving it from a host](#driving-it-from-a-host).

## Setup

Needs Python **3.12–3.14**. Current as of ESPHome 2026.7.x.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -r requirements.txt
cp secrets.yaml.example secrets.yaml
```

Fill `secrets.yaml`: Wi-Fi, OTA password, `timezone`, `latitude` / `longitude` /
`weather_place`, and an API key from `openssl rand -base64 32`.

Then put your HA entity IDs and Dial labels in
[`packages/entities.yaml`](packages/entities.yaml) (from **Settings → Devices &
services → Entities**). That file is committed and is not secret; `secrets.yaml`
is neither.

```bash
./scripts/flash.sh                  # USB, auto-detects the port
./scripts/flash.sh 192.168.1.101    # OTA, once it is on Wi-Fi
esphome logs m5dial.yaml --device 192.168.1.101
```

`scripts/flash.sh` compiles, copies the factory image to `firmware/m5dial.bin`
and uploads. See [firmware/README.md](firmware/README.md) for flashing without
ESPHome, recovering a wedged USB port — and for why **the built `.bin` contains
your Wi-Fi password and API key** and must never be shared.

| Symptom | Fix |
|---|---|
| Serial port missing | Hold **BOOT (G0)**, tap **RESET**, release **BOOT**. Port is `/dev/cu.usbmodem*` |
| `waiting for download` after opening USB logs | Opening the port toggles DTR/RTS into ROM download mode. `esptool --chip esp32s3 --port <port> run`, then use network logs |
| Compiles, no device found | Same subnet? Try the raw IP rather than `m5-dial.local` |

### Adopt in Home Assistant — required for toggles

The Dial **reads** entity state without this. It **cannot** turn anything on or
off until actions are allowed, and that fails silently and looks like a firmware bug.

1. **Settings → Devices & services** — wait for mDNS discovery (up to ~5 min), adopt **M5 Dial**
2. Open the device → **Configure** (gear) → enable **"Allow the device to perform Home Assistant actions"**
3. Tap a light on the Dial; HA should change. If not, check HA logs for denied `homeassistant.action` calls.

## UI

Industrial tick-ring clock; timezone from secrets, SNTP over Wi-Fi. **Single
tap** wakes the backlight, **double tap** (or the front button) opens the
six-wedge launcher. Center **HOME** returns to the clock. Idle dims; **Night**
(22:00–08:00) and Display-off sleep. **AP** and **Audio** are off by default.
Every sub-page has a back arrow, and the side button is Back everywhere.

| Wedge | Page |
|-------|------|
| Settings | Display / Rotate / Clock / Dial nums / Network / Audio / Night / AP |
| AC | Arçelik 09325 A — temperature arc, fan, power (synthesised IR) |
| Lights | 2×2 HA light cards — tap toggles, dial sets brightness |
| Plugs | HA switches, 4 rows/page, `<`/`>` flips pages |
| Time | Hub ring → one dedicated page each (`packages/time.yaml`) |
| Scenes | HA `scene.*` activators |

**Input model.** The encoder and both buttons are wired straight to scripts
(`encoder_nav_cw` / `_ccw`, `front_or_wake`, `nav_back`), and the amber border
comes from a `*_index` global per page. There is deliberately **no LVGL
`encoders:` indev**: it adds a second, invisible selection (group focus), and
ESPHome puts every widget of every page into one flat group — so the encoder
walked focus onto *other pages'* widgets and the front button clicked them.

`front_action` snapshots the active page before dispatching, because several of
its handlers navigate; a live `lvgl.page.is_showing` chain fired the new page's
handler in the same press.

**Lights.** The first tap on a card only **selects** it; tapping the **selected**
card toggles it (as does the front button). So the dial can be aimed at a light
without switching it, and a mis-aimed tap costs nothing. The dial then changes
that light's brightness in 16/255 steps, sent to HA 250 ms after it settles (the
same debounce the AC uses). Brightness is held locally rather than read back from
HA, whose value lags a command by a refresh and would make the dial feel like it
was fighting back. The page re-reads HA once a second while it is on screen, so
changes made elsewhere show up.

**Icons:** Material Design Icons, subset to the glyphs actually used — `font_icon`
(18 px) plus 9 weather glyphs in `font_icon_big` (40 px). Codepoints are verified
against upstream `meta.json`; several are not the obvious value (`clock-outline`
is `F0150`, `brightness-6` is `F00DF`), so don't hand-edit them from memory.

**Round-safe layout:** the panel is a 240 px circle, so a widget whose *corner*
sits beyond r=120 is clipped by the glass. `check_ui.py` enforces r≤114 for every
button and slider on every page, plus a 24 px minimum touch height. Outer
Settings rows are deliberately narrower than inner ones so the list follows the
circle.

**Settings persistence:** Rotate / Clock / Dial nums / Night / AP / Audio and the
AC state are stored by [`include/settings_store.h`](include/settings_store.h),
**not** by `restore_value: true`. ESPHome's restoring globals are a
`PollingComponent(1000)`: they stage on a 1 Hz poll and only reach flash on the
next preferences flush, so a setting changed just before the power is pulled is
lost (a clean reboot hides this, because `on_shutdown()` saves). `store_now()`
stages and commits in one call.

**Time hub:** the Time wedge opens a launcher-style ring with the current time in
the middle. Each icon opens its own full page; the encoder adjusts that page's
value (city, timer minutes, pomodoro length).

```
clock ─tap─► launcher ─Time─► page_time (ring)
                                 ├─ page_cities     ← / →, 5 cities
                                 ├─ page_pomodoro   arc + play/reset
                                 ├─ page_stopwatch  play/reset, 0.1s
                                 ├─ page_timer      − / play / + / reset
                                 └─ page_weather    hero + 3-hourly strip
```

**Cities** (edit in `packages/entities.yaml`): `city_*_utc_offset` is **standard**
time; `city_*_dst` adds the summer hour — `0` none, `1` EU (last Sun Mar → last
Sun Oct), `2` US/CA (2nd Sun Mar → 1st Sun Nov). `home_utc_offset` / `home_dst`
must match `secrets.yaml`. Rules live in [`include/tz_dst.h`](include/tz_dst.h),
checked against tzdata for a full year; a city can read an hour off for part of
the two switchover days. **Vancouver is `-7` with `dst: 0`** — British Columbia
stopped changing clocks, so tzdata puts it on a fixed `-7` from Nov 2026. Don't
"fix" it back to `-8`.

**Weather** (`packages/weather.yaml`): current conditions and today's high/low
from [Open-Meteo](https://open-meteo.com/en/docs) — no API key, no HA weather
entity. `timezone=auto` derives the local day from your coordinates. Refreshes
every 15 min; the button on the page (or the front button) forces one.

## AC — Arçelik 09325 A

Cool-only, and **nothing needs teaching**. The protocol was reverse-engineered
from 50 captured frames and every command is computed on the fly, so the Dial
works straight after a reboot or OTA. Full writeup:
[`docs/ac-ir-protocol.md`](docs/ac-ir-protocol.md).

- Arc shows the target temperature, **18–30 °C**; fan is `AUTO` then 1–5 bars
- The power chip toggles; the front button (or the `TEMP`/`FAN` chips) picks what the dial adjusts
- Turning the dial sends **one** frame 400 ms after it settles, not one per detent
- Pressing the **physical remote** updates the Dial — the receiver decodes the same format
- Each command is sent **5×** (`ac_tx_repeats`, or `ac_set_repeats` at runtime). Frames are absolute state, so repeats are idempotent; this buys range, because the Unit IR's single LED is far weaker than a handheld remote's

A `component: ac_commit took a long time (~420 ms)` warning on transmit is
expected: one frame is ~52 ms, five with 40 ms gaps, and the transmitter
deliberately blocks (chunked sends get starved by LVGL).

**Aiming matters more than anything in software.** The AC's receiver window is
behind the front panel, pointing *out and slightly down into the room* — so
directly underneath the indoor unit is the worst possible spot. The Unit IR is
on a Grove cable and does not have to sit next to the Dial: put it where it can
see the front panel, or bounce it off a matte white ceiling. If commands are
still missed, raise `ac_tx_repeats`, or try `ac_carrier_hz: "36000"` / `"40000"` —
the carrier frequency was never measured (a demodulator strips it), so 38 kHz is
an assumption.

If the AC stops responding after a long uptime or many OTA flashes, **reboot the
Dial**: the ESP32's RMT transmitter has been seen to degrade, with frames still
leaving the device and logging normally.

### IR diagnostics

```bash
python scripts/ac_test.py --host <ip> seq            # scripted on/temp/fan/off
python scripts/ac_test.py --host <ip> sweep-fan 24   # every fan step
python scripts/ac_test.py --host <ip> code 0x88C0051 # one exact frame
python scripts/decode_ir.py raw.txt                  # decode a `Received Raw:` dump
```

| Tool | Use |
|---|---|
| `ac_send_code` / `ac_set_state` | send exact frames from a host over the API |
| `ac_loopback` | decode our **own** emission — verifies the transmitted frame bit-for-bit |
| `ac_arm_capture` + `ac_replay` | store a remote frame verbatim and re-emit it, separating wrong bits from wrong timing |
| `ac_set_repeats` | change the repeat count at runtime |
| **IR Beacon** switch (HA) | re-sends state every 2 s so you can walk the emitter around |

## Driving it from a host

`scripts/dial.py` works the UI over the ESPHome API and brings the screen back
as a PNG — enough to check a layout change, or to let an agent drive the device,
without photographing the glass.

```bash
python scripts/dial.py shot                  # -> shot.png
python scripts/dial.py key press cw:3 press  # cw / ccw / press / back
python scripts/dial.py key back shot         # keys and screenshots in one run
python scripts/dial.py logs -s 20            # stream the device log
```

The keys are the Dial's whole physical input surface, so anything a finger can
reach is reachable from here. **On the AC page they send real IR** — turning the
dial there changes your AC.

There is no framebuffer to snapshot: `ili9xxx` only allocates one for its own
drawing API, LVGL streams tiles straight to the panel, and a 240×240×2 = 112 KB
buffer will not fit in internal RAM (no PSRAM). So
[`include/agent.h`](include/agent.h) borrows the tiles on the way out — it swaps
in a flush callback, invalidates the screen, and mirrors each tile to a TCP
socket before handing it to ESPHome's real flush. Zero extra RAM; the host
reassembles the tiles into the PNG.

## Checks

```bash
python check_ui.py            # UI invariants, no device needed
python scripts/dial.py selftest
esphome config m5dial.yaml
```

## Layout

```
m5dial.yaml              # entry
check_ui.py              # UI invariants (styles, geometry, input model, persistence)
scripts/
  flash.sh                # compile → firmware/m5dial.bin → upload (USB or OTA)
  dial.py                 # screenshots + scripted input + logs over the API
  ac_test.py              # drive the AC over the API for bench testing
  decode_ir.py            # decode ESPHome raw IR dumps
firmware/                # full factory .bin (gitignored) + README
include/
  agent.h                 # screenshot bridge (LVGL flush tap → TCP)
  wx_icons.h              # WMO code -> weather glyph / word
  tz_dst.h                # EU + US daylight-saving rules
  settings_store.h        # immediate-write NVS persistence
  timefmt.h
docs/
  ac-ir-protocol.md       # how the IR protocol was decoded
  images/
packages/
  hardware.yaml           # pins, display, touch, encoder, RTC, NFC
  entities.yaml           # HA entity IDs + cities (committed)
  ac.yaml                 # Arçelik frame synthesiser + receive-sync
  time.yaml               # clock, cities, pomodoro, stopwatch, timer, weather logic
  weather.yaml            # Open-Meteo fetch (coords from secrets.yaml)
  ui.yaml                 # pages, styles, navigation, agent API actions
```
