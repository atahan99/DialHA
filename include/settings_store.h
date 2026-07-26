#pragma once
#include "esphome/core/preferences.h"

// Immediate-write persistence for the UI settings that survive a power cut.
//
// Why not `restore_value: true`?
//   RestoringGlobalsComponent is a PollingComponent(1000): it copies the value
//   into the pending-save queue only on its 1 Hz poll, and ESP32Preferences::
//   sync() returns early when that queue is empty. So a setting changed and
//   then immediately unplugged is lost — calling sync() straight after the
//   change flushes nothing, because nothing has been staged yet.
//
// store_now() stages AND commits, so the value is in NVS before it returns.
//
// The ESPPreferenceObject is function-static because
// ESP32Preferences::make_preference allocates a new backend on every call;
// creating it per invocation would leak.

namespace m5dial {

// Stable NVS keys. Do not renumber — these name the stored blobs.
constexpr uint32_t KEY_ROTATION = 0x4D354431;  // "M5D1"
constexpr uint32_t KEY_NIGHT = 0x4D354432;     // "M5D2"
constexpr uint32_t KEY_AP = 0x4D354433;        // "M5D3"
constexpr uint32_t KEY_SOUND = 0x4D354434;     // "M5D4"

template<uint32_t KEY, typename T> inline void store_now(T value) {
  static esphome::ESPPreferenceObject pref = esphome::global_preferences->make_preference<T>(KEY);
  pref.save(&value);
  esphome::global_preferences->sync();
}

template<uint32_t KEY, typename T> inline T load_or(T fallback) {
  static esphome::ESPPreferenceObject pref = esphome::global_preferences->make_preference<T>(KEY);
  T v{};
  return pref.load(&v) ? v : fallback;
}

}  // namespace m5dial
