#pragma once
#include <cstdint>
#include <ctime>

#include "esphome/core/defines.h"  // posix_tz.h is guarded by USE_TIME_TIMEZONE
#include "esphome/components/time/posix_tz.h"

// Parses a tzdata POSIX footer (`tail -1 /usr/share/zoneinfo/Europe/London`
// gives "GMT0BST,M3.5.0/1,M10.5.0") into ESPHome's ParsedTimezone, so the
// Cities page can convert with esphome::time::epoch_to_local_tm.
//
// ESPHome has its own parse_posix_tz, but it is deprecated and goes away in
// 2026.9; the struct and epoch_to_local_tm stay. Only the M (month.week.day)
// rule form is handled, which is what tzdata footers use; anything else
// returns false. tests/city_tz_test.cpp checks the result against libc.

namespace city_tz {

using esphome::time::DSTRule;
using esphome::time::DSTRuleType;
using esphome::time::ParsedTimezone;

inline bool is_digit(char c) { return c >= '0' && c <= '9'; }

// "EST" or "<+03>"; POSIX requires at least three letters.
inline bool skip_name(const char *&p) {
  if (*p == '<') {
    while (*p && *p != '>')
      p++;
    return *p++ == '>';
  }
  const char *start = p;
  while ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z'))
    p++;
  return p - start >= 3;
}

// [+-]hh[:mm[:ss]] -> signed seconds. Rule times may be negative or past 24h.
inline bool parse_hms(const char *&p, int32_t &out) {
  int32_t sign = 1;
  if (*p == '+' || *p == '-')
    sign = (*p++ == '-') ? -1 : 1;
  int32_t secs = 0;
  for (int32_t unit = 3600; unit >= 1; unit /= 60) {
    if (!is_digit(*p))
      return false;
    int32_t n = 0;
    while (is_digit(*p))
      n = n * 10 + (*p++ - '0');
    secs += n * unit;
    if (*p != ':')
      break;
    p++;
  }
  out = sign * secs;
  return true;
}

// ",Mm.w.d[/time]"
inline bool parse_rule(const char *&p, DSTRule &rule) {
  if (*p++ != ',' || *p++ != 'M')
    return false;
  int f[3];
  for (int i = 0; i < 3; i++) {
    if (!is_digit(*p))
      return false;
    f[i] = 0;
    while (is_digit(*p))
      f[i] = f[i] * 10 + (*p++ - '0');
    if (i < 2 && *p++ != '.')
      return false;
  }
  if (f[0] < 1 || f[0] > 12 || f[1] < 1 || f[1] > 5 || f[2] > 6)
    return false;
  rule = {};
  rule.type = DSTRuleType::MONTH_WEEK_DAY;
  rule.month = f[0];
  rule.week = f[1];
  rule.day_of_week = f[2];
  rule.time_seconds = 7200;  // POSIX default 02:00
  if (*p != '/')
    return true;
  p++;
  return parse_hms(p, rule.time_seconds);
}

inline bool parse(const char *p, ParsedTimezone &tz) {
  tz = {};
  if (!skip_name(p) || !parse_hms(p, tz.std_offset_seconds))
    return false;
  if (*p == '\0')
    return true;  // no DST
  if (!skip_name(p))
    return false;
  tz.dst_offset_seconds = tz.std_offset_seconds - 3600;
  if (*p != ',' && !parse_hms(p, tz.dst_offset_seconds))
    return false;
  return parse_rule(p, tz.dst_start) && parse_rule(p, tz.dst_end) && *p == '\0';
}

// Local time in `posix` right now. False before the clock is set or on a bad
// string. Parsing every call is cheap at the page's 1 Hz refresh.
inline bool local_now(const char *posix, struct tm *out) {
  ParsedTimezone tz;
  time_t now = ::time(nullptr);
  return now > 1577836800 && parse(posix, tz) && esphome::time::epoch_to_local_tm(now, tz, out);  // > 2020: clock set
}

}  // namespace city_tz
