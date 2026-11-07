# Firmware artifacts

`dialha.bin` is the personal build's full factory image (`m5dial.yaml`):
bootloader + partition table + app,
written at offset `0x0`. It is not the OTA-only binary. Use it for a first
flash, a recovery flash, or a blank Dial.

It is gitignored and must stay that way (see the warning below).

## Build it

```bash
esphome compile m5dial.yaml
cp .esphome/build/m5-dial/build/firmware.factory.bin firmware/dialha.bin
```

Or in one step, which also uploads:

```bash
./scripts/flash.sh                        # USB, auto-detect port
./scripts/flash.sh /dev/cu.usbmodem2101   # USB, explicit port
./scripts/flash.sh 192.168.1.101          # OTA
```

## Flash it directly

```bash
esptool --chip esp32s3 --port /dev/cu.usbmodem2101 write_flash 0x0 firmware/dialha.bin
```

If the port does not appear: hold BOOT (G0), tap RESET, release BOOT.

Once the Dial is on Wi‑Fi, prefer OTA, which avoids the USB serial path entirely:

```bash
esphome run m5dial.yaml --device <device-ip>
```

Opening the USB port with `esphome logs --device /dev/cu.*` can toggle DTR/RTS
and drop the S3 into ROM download mode (`waiting for download`). Recover with:

```bash
esptool --chip esp32s3 --port /dev/cu.usbmodem2101 run
```

## This file is a credential

ESPHome compiles `secrets.yaml` into the binary. Checked against a real build
of this project, `strings` recovers all of the following:

| Secret | Embedded |
|---|---|
| `wifi_ssid` | plaintext |
| `wifi_password` | **plaintext** |
| `ota_password` | **plaintext** |
| `api_encryption_key` | the decoded 32 raw bytes |

So:

- **Never commit it.** Git does not forget; removing it in a later commit leaves
  the blob in history, and scrubbing needs `filter-repo` plus a force-push.
- **Never post or share it**, whether in an issue, a chat, or a cloud folder.
- If a build has left your machine, rotate the OTA password and
  regenerate the API key.

To share a build, use the public one instead: `dialha.factory.yaml` reads no
secrets. A fresh public Dial is flashed with ESPHome Web and takes
Wi‑Fi over USB there (Improv), and Home Assistant sets its API key when it adopts it. Tagged releases publish it; see the main README.
