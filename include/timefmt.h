#pragma once
// Small helpers shared by every clock face (home clock, time hub, cities).
// Plain functions taking ints, because ESPHome emits includes before globals.

// 24h hour -> 12h hour (0 and 12 both read as 12).
inline int hour12(int hour) {
  int h = hour % 12;
  return h == 0 ? 12 : h;
}

inline const char *ampm_of(int hour) { return hour < 12 ? "AM" : "PM"; }

// Three-letter month, 1 = January. Out-of-range yields "---".
inline const char *month_abbr(int month) {
  static const char *const names[] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                      "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};
  if (month < 1 || month > 12)
    return "---";
  return names[month - 1];
}

// Writes "HH:MM" (24h) or "H:MM" (12h) into buf.
inline void fmt_hhmm(char *buf, size_t len, int hour, int minute, bool h24) {
  if (h24) {
    snprintf(buf, len, "%02d:%02d", hour, minute);
  } else {
    snprintf(buf, len, "%d:%02d", hour12(hour), minute);
  }
}
