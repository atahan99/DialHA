# Third-party code and licenses

DialHA's own files (YAML, headers in `include/`, scripts, docs) are MIT; see
[LICENSE](LICENSE). A compiled firmware also contains the components below,
which ESPHome fetches at build time. Versions are the ones the
ESPHome version pinned in `requirements.txt` resolved to.

| Component | Version | License | Upstream |
|-----------|---------|---------|----------|
| ESPHome C++ runtime | 2026.8.x | GPL-3.0 (its Python tooling is MIT) | https://github.com/esphome/esphome |
| ESP-IDF | 5.5.5 | Apache-2.0 | https://github.com/espressif/esp-idf |
| LVGL | 9.5.0 | MIT | https://github.com/lvgl/lvgl |
| ArduinoJson | 7.4.3 | MIT | https://github.com/bblanchon/ArduinoJson |
| espressif/mdns | 1.11.3 | Apache-2.0 | https://github.com/espressif/esp-protocols |
| noise-c (ESPHome fork) | as resolved | MIT | https://github.com/esphome/noise-c |
| libsodium (ESPHome fork) | as resolved | ISC | https://github.com/esphome/libsodium |
| Roboto font (subset) | Google Fonts | OFL-1.1 | https://fonts.google.com/specimen/Roboto |
| Material Design Icons webfont (subset) | master | Apache-2.0 (Pictogrammers Free License) | https://github.com/Templarian/MaterialDesign-Webfont |

## What this means for the released `.bin`

The firmware links ESPHome's GPL-3.0 runtime, so a released binary is
distributed under GPL-3.0 as a whole. That is satisfied by this repository: the
complete source and build setup for every release is the tagged commit, and
`esphome compile dialha.factory.yaml` reproduces it. The MIT license on
DialHA's own files still applies to those files on their own.
