# Reverse-engineering an AC IR protocol

Unit: Arçelik 09325 A (cool-only split)
Hardware: M5Dial (ESP32-S3) + M5Stack Unit IR U002 on PORT.B (TX = G2, RX = G1)
Result: a fully synthesised encoder with no learning and no stored codes, which survives reboot/OTA.

This is the record of how the protocol was identified, captured, decoded and
verified. It is written so the same method can be repeated for another remote.

---

## 1. Why the original approach failed

The firmware originally shipped a raw learn/replay design: you pressed a
button on the Dial, pointed the remote at the Unit IR, and the captured pulse
train was stored in a `std::vector<int32_t>` global and replayed later.

That design had four problems, in rough order of pain:

| Problem | Consequence |
|---|---|
| Codes lived in RAM globals (`ir_cool_temps`, …) | Every reboot and every OTA wiped all 18 learned codes |
| TEMP+/− are absolute-state frames, not increments | You had to teach each degree separately, 13 times |
| `ac_dial_adjust` transmitted on every encoder detent | Spinning 18→24 fired six blocking sends; UI stalled, AC beeped six times |
| Empty chips auto-armed learn mode on tap | Tapping a button you hadn't taught silently entered a capture state |

Replay also can only ever reproduce combinations you physically pressed. The
fix was to generate frames instead, which meant understanding the protocol.

---

## 2. First hypothesis: Coolix (wrong, but cheap to test)

A same-family unit had an entry in
[Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) (`ACs/Beko/Beko.ir`),
which looked like a shortcut. Demodulating its raw timings gave:

```
Off      -> B2 4D 7B 84 E0 1F   ->  data bytes 0xB27BE0
Led      -> B5 4A F5 0A A5 5A   ->  data bytes 0xB5F5A5
Temp_17  -> 0xB25F00   Temp_22 -> 0xB25F70   temp_30 -> 0xB25FB0
```

Every byte is followed by its own complement (`B2 4D`, `5F A0`), the signature
framing of Coolix, and those constants match ESPHome's
`components/coolix/coolix.cpp` exactly (`COOLIX_OFF = 0xB27BE0`,
`COOLIX_LED = 0xB5F5A5`, and a temperature map where 22 °C → `0x70`, 30 °C → `0xB0`).

So that unit is Coolix, and the obvious conclusion was to drop `ac.yaml`
and use ESPHome's built-in `coolix` climate platform.

That conclusion was wrong here. A model line can ship several different IR
platforms, so a database match for a *neighbouring model* is a hypothesis, not
evidence. Confirming it on the actual hardware cost one flash and saved a
rewrite around a protocol this unit does not speak.

---

## 3. Getting the receiver to tell the truth

Two configuration details had been hiding the answer.

### 3.1 `dump: raw` can never name a protocol

`ac.yaml` had `dump: raw`, but the README instructed you to look for a decoded
protocol name in the log. Those are mutually exclusive: `raw` only prints pulse
timings. Switching to `dump: all` runs every registered decoder, so a
protocol match would announce itself.

### 3.2 `raw` is a *secondary* dumper and gets masked

With `dump: all` the log filled with `remote.pronto` lines and zero
`remote.raw` lines. From `remote_base.cpp`:

```cpp
void RemoteReceiverBase::call_dumpers_() {
  bool success = false;
  for (auto *dumper : this->dumpers_)          // primary
    if (dumper->dump(...)) success = true;
  if (!success)                                // only if nothing matched
    for (auto *dumper : this->secondary_dumpers_)
      dumper->dump(...);
}
```

Only `raw` sets `is_secondary() { return true; }`. Pronto is a *primary* dumper
that always returns `true`, so it permanently suppresses `raw`.

The practical rule: use `dump: all` to identify a protocol, and `dump: raw`
alone to read exact timings.

This also settled the Coolix question definitively: the Coolix dumper is a
primary dumper logging at `ESP_LOGI`, it ran on every frame, and it never
matched.

### 3.3 Other receiver settings that were wrong

```yaml
tolerance: 55%      # -> 25% (default). Irrelevant for raw, but 55% causes
                    #    false decodes as soon as real decoders run.
buffer_size: 1024   # -> removed (ESP32 default 10000b).
```

`buffer_size: 1024` was worse than it looks. In `remote_receiver_rmt.cpp`:

```cpp
this->store_.buffer_size = std::max((event_size + this->store_.receive_size) * 2,
                                    this->buffer_size_);
```

With `receive_symbols` at its 192 default, `receive_size` is 768 bytes, so the
buffer was forced up to ~1560 bytes, two receive events deep. Any burst
logs `Buffer overflow` and drops captures.

Also worth knowing for longer protocols: ESPHome decodes each RMT event
independently and never stitches partial frames. A frame longer than
`receive_symbols` (192 symbols = 384 pulses) arrives as two separate `on_raw`
calls, and a naive handler stores only the first fragment. This protocol is 59
pulses, so it was never affected, though only by luck. For a long
protocol (Daikin, Mitsubishi) raise `receive_symbols` to 1024.

---

## 4. Capture methodology

The goal is to make each captured frame unambiguously labelled.
Frames are recorded *after* a press, which is the source of most mistakes.

Setup:

```bash
# ac.yaml: dump: raw   (alone — see 3.2)
esphome run m5dial.yaml --device <device-ip> --no-logs
esphome logs m5dial.yaml --device <device-ip> | tee raw.txt
```

> **Use the network, not USB.** Opening `/dev/cu.usbmodem*` with `esphome logs
> --device` re-triggered DTR/RTS and dropped the ESP32-S3 into ROM download
> mode (`waiting for download`). Recover with
> `python -m esptool --chip esp32s3 --port /dev/cu.usbmodem2101 run`.

Rules that made the data trustworthy:

1. One variable per round. Sweep temperature with fan fixed, then fan with
   temperature fixed.
2. Know the starting state. Frames only show state *after* a press, so
   without the start value the entire mapping can be off by one. This cost us a
   round: the first fan attempt was unusable because the initial state wasn't
   recorded.
3. Space presses widely (4–5 s). Cheap insurance against merged or dropped
   frames.
4. Sweep monotonically end to end. 18 → 30 in single steps means the frame
   order *is* the label; no per-press narration needed.
5. Verify in both directions. The fan map was confirmed by walking up with
   FAN+ and back down with FAN− and checking the codes mirrored.

### Behaviour worth recognising

Pressing a button at the end of its range re-sends the current state rather
than doing nothing. TEMP+ at 30 °C repeats the 30 °C frame; FAN+ on AUTO repeats
the AUTO frame. Those duplicate trailing frames look like corruption but are
normal, and they are a useful signal that you have hit a limit.

---

## 5. Decoding

[`scripts/decode_ir.py`](../scripts/decode_ir.py) parses `Received Raw:` lines
into signed microseconds, where positive = mark, negative = space, and
prints length, header, bits, nibbles and a checksum guess per frame:

```bash
python scripts/decode_ir.py raw.txt
python scripts/decode_ir.py raw.txt --since 04:16:00   # one capture round
```

The core is two lines; everything else is reporting:

```python
hdr  = v[:2]
bits = ''.join('1' if -v[i+1] > 1000 else '0' for i in range(2, len(v)-1, 2))
```

Run against the session's capture it reports
`51 frames; 51 match a (sum of leading nibbles)&0xF checksum`.

### 5.1 Timing, measured over 20 frames

| Element | Value |
|---|---|
| Header mark | `+3000 µs` (measured 2938–3007) |
| Header space | `−9650 µs` (measured 9631–9704) |
| Bit mark | `+500 µs` (all bits) |
| `1` space | `−1530 µs` |
| `0` space | `−500 µs` |
| Stop | `+500 µs` mark |
| Frame | 28 bits MSB-first, 59 pulses, sent once (no repeat frame) |

> **A *received* frame is 60 entries, not 59.** ESPHome's raw dumper prints
> `src.size() - 1`, hiding the trailing idle space, so measuring the protocol
> from dumper output gives a count one short. A decoder that walks the vector
> unbounded then pairs the stop mark with that idle and invents a 29th bit and
> rejects every frame. Bound the loop at the expected bit count:
>
> ```cpp
> for (size_t i = 2; i + 1 < x.size() && bits < 28; i += 2) { ... }
> ```
>
> This cost a long debugging session: receive-sync had never worked, and
> because the rejects were silent it looked like nothing was arriving at all.

The 3.0 ms / 9.65 ms header is unusual (most AC protocols use a roughly
symmetric 4.4/4.3 ms lead-in) which is exactly why no built-in decoder matched.

### 5.2 The checksum, found before any field was identified

Every frame is 7 nibbles. Summing the first six and masking to 4 bits
reproduced the seventh, on all 51 raw-dumper frames (and on the 12 earlier
Pronto captures re-checked by hand):

```
K = (n0 + n1 + n2 + n3 + T + n5) & 0xF
```

Finding the checksum early pays off: from that point on, every later
capture is self-validating, and a bad decode is detected instead of silently
producing a wrong mapping.

### 5.3 Field map

```
   8   8   n2  n3  T   n5  K        28 bits, MSB first
   │   │   │   │   │   │   └── checksum, (sum of first six) & 0xF
   │   │   │   │   │   └────── fan
   │   │   │   │   └────────── temperature, °C − 15
   │   │   │   └────────────── 0 = power-on, 8 = adjust while running
   │   │   └────────────────── 0 normally; C only inside the OFF literal
   └───┴────────────────────── constant preamble
```

Temperature (`T`) is perfectly linear; all 13 values were observed:

| °C | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 |
|----|----|----|----|----|----|----|----|----|----|----|----|----|----|
| `T`| 3  | 4  | 5  | 6  | 7  | 8  | 9  | A  | B  | C  | D  | E  | F  |

Fan (`n5`) is arbitrary, not ordered, so a lookup table is required:

| bars | 1 | 2 | 3 | 4 | 5 | auto |
|------|---|---|---|---|---|------|
| `n5` | 0 | 9 | 2 | A | 4 | 5    |

Commands:

```
ON   8 8 0 0 T n5 K     carries current temp/fan
ADJ  8 8 0 8 T n5 K     temp/fan change while already running
OFF  8 8 C 0 0 5 1      fixed literal 0x88C0051 — does NOT carry temp/fan
```

OFF is the one frame that is not state-carrying: it always reports `T=0, n5=5`
regardless of the unit's actual settings. It was observed three separate times,
byte-identical.

Mode was never decoded: the unit is used in COOL only, so `n3 = 8` is emitted
as a constant. `n3` values `9`, `A`, `B`, `3` were seen during an early
unlabelled round and correspond to other modes if anyone wants them later.

---

## 5.4 Diagnostics that earned their keep

Four tools, all still in the firmware, that turned a week of guessing into
single measurements:

| Tool | What it answers |
|---|---|
| `scripts/ac_test.py` | Drives the AC over the ESPHome API, so frames can be sent from a host and correlated with the device log without touching the Dial |
| `ac_loopback` | Suppresses the self-reception guard so the Dial decodes its own emission; proves the transmitted frame bit-for-bit |
| `ac_arm_capture` / `ac_replay` | Stores a received frame verbatim and re-emits it, separating "wrong bits" from "wrong timing/optics" |
| `IR Beacon` switch | Re-sends state every 2s so you can walk the emitter around and hear where the AC responds |

Two lessons worth keeping:

1. Never let a receive path reject silently. The decoder discarded every
   frame for one off-by-one reason, and because the rejects were silent it was
   indistinguishable from "nothing is arriving". Logging the reason found it
   immediately.
2. Measure, do not infer. The carrier frequency was never measured: a
   demodulator strips it, and the Pronto dump showed 38kHz only because
   ESPHome hardcodes that constant. It is still an assumption.

## 6. Verification before flashing

The encoder was checked against every captured frame offline, before any
firmware was built:

```
ON   18C fan1   ours=0x8800303   captured=0x8800303   OK
ADJ  18C fan1   ours=0x880830B   captured=0x880830B   OK
ADJ  24C fan1   ours=0x8808901   captured=0x8808901   OK
ADJ  30C fan1   ours=0x8808F07   captured=0x8808F07   OK
ADJ  18C fan2   ours=0x8808394   captured=0x8808394   OK
...
temp sweep 18-30: all 13 match
```

Reproducing captured frames bit-for-bit is the strongest check available
without pointing the emitter at the AC, and it costs nothing.

---

## 7. What shipped

`packages/ac.yaml` now:

- Synthesises every frame: `ac_tx_code` expands a 28-bit value into the raw
  timing vector; `ac_tx_state` builds the value from live temp/fan and computes
  the checksum.
- Persists `ac_power` / `ac_temp` / `ac_fan` through
  [`include/settings_store.h`](../include/settings_store.h), so state survives
  reboot, OTA *and* an immediate power cut. Nothing is ever learned.
- Decodes incoming frames with the same field map, so pressing the physical
  remote updates the Dial's display (guarded by `ac_rx_guard` so the Dial
  ignores its own emission).
- Debounces the encoder via `ac_commit` (`mode: restart`, 400 ms), so a spin
  from 18 to 30 sends exactly one command instead of twelve.
- Repeats each command 5× (`ac_tx_repeats`, 40 ms apart). The handheld remote
  sends once, but its emitter is much stronger than the Unit IR's single LED, so
  a marginal aim drops frames. This is safe because every frame is absolute state; the
  remote itself re-sends an identical frame when you press TEMP+ at 30 °C.

Any temperature/fan combination now works immediately, including combinations
never pressed on the physical remote.

---

## 8. Repeating this for another remote

1. `dump: all`, press a button. If a decoder names the protocol, use the
   matching ESPHome `climate_ir` platform and stop here.
2. Otherwise `dump: raw` alone; confirm frames are a stable length.
3. Sweep one field monotonically end to end, recording the start state.
4. Look for a checksum first (try `sum & 0xF`, XOR, and sum-of-bytes).
5. Map remaining fields one round at a time, verifying in both directions.
6. Reproduce every captured frame offline before flashing.
