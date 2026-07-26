#pragma once
// Daylight-saving rules for the Cities page.
//
// Each city in packages/entities.yaml carries a *standard-time* UTC offset plus
// a rule id; the offset actually shown is std + dst_offset(...). Free functions
// taking plain ints, because ESPHome emits includes before the globals exist.
//
//   rule 0  no DST — fixed offset all year
//   rule 1  EU      — last Sunday March .. last Sunday October
//   rule 2  US/CA   — 2nd Sunday March .. 1st Sunday November
//
// Day granularity: the switch lands on the right day but ignores the 01:00/02:00
// local switchover hour, so a city can read an hour off for part of the two
// transition days a year. Verified against tzdata for every day of a full year.

// Sakamoto's method. Returns 0=Sunday .. 6=Saturday.
inline int tz_dow(int y, int m, int d) {
  static const int t[] = {0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4};
  if (m < 3)
    y -= 1;
  return (y + y / 4 - y / 100 + y / 400 + t[m - 1] + d) % 7;
}

inline int tz_days_in_month(int y, int m) {
  static const int d[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  if (m == 2 && ((y % 4 == 0 && y % 100 != 0) || y % 400 == 0))
    return 29;
  return d[m - 1];
}

// Extra hours on top of the standard offset (0 or 1).
inline int dst_offset(int rule, int year, int month, int day) {
  if (rule == 1) {  // EU
    int mar = 31;
    while (tz_dow(year, 3, mar) != 0)
      mar--;
    int oct = 31;
    while (tz_dow(year, 10, oct) != 0)
      oct--;
    if (month > 3 && month < 10)
      return 1;
    if (month == 3 && day >= mar)
      return 1;
    if (month == 10 && day < oct)
      return 1;
    return 0;
  }
  if (rule == 2) {  // US / Canada
    int mar = 1;
    while (tz_dow(year, 3, mar) != 0)
      mar++;
    mar += 7;  // second Sunday
    int nov = 1;
    while (tz_dow(year, 11, nov) != 0)
      nov++;
    if (month > 3 && month < 11)
      return 1;
    if (month == 3 && day >= mar)
      return 1;
    if (month == 11 && day < nov)
      return 1;
    return 0;
  }
  return 0;
}
