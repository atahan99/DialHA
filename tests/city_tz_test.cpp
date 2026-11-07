// Host test for include/city_tz.h. Each argument is "Area/City=POSIX". The
// POSIX string is parsed and converted with ESPHome's epoch_to_local_tm, then
// compared half-hourly over 2027-2030 against libc using the full IANA zone
// from the system's tzdata. A country changing its rules fails this test.
// Run via tests/run_city_tz_test.sh.
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <string>

#include "city_tz.h"

int main(int argc, char **argv) {
  int fails = 0;
  for (int a = 1; a < argc; a++) {
    std::string arg = argv[a];
    size_t eq = arg.find('=');
    if (eq == std::string::npos) {
      std::printf("FAIL bad argument %s (want Area/City=POSIX)\n", arg.c_str());
      fails++;
      continue;
    }
    std::string iana = arg.substr(0, eq);
    const char *posix = arg.c_str() + eq + 1;
    esphome::time::ParsedTimezone tz;
    if (!city_tz::parse(posix, tz)) {
      std::printf("FAIL parse %s\n", posix);
      fails++;
      continue;
    }
    setenv("TZ", iana.c_str(), 1);
    tzset();
    int bad = 0;
    for (time_t t = 1798761600; t < 1924992000; t += 1800) {  // 2027-01-01 .. 2031-01-01
      struct tm want, got;
      ::localtime_r(&t, &want);
      esphome::time::epoch_to_local_tm(t, tz, &got);
      if (want.tm_hour != got.tm_hour || want.tm_min != got.tm_min || want.tm_mday != got.tm_mday) {
        if (bad++ < 3)
          std::printf("FAIL %s (%s) at %ld: tzdata %02d:%02d d%d, ours %02d:%02d d%d\n", iana.c_str(), posix, (long) t, want.tm_hour,
                      want.tm_min, want.tm_mday, got.tm_hour, got.tm_min, got.tm_mday);
      }
    }
    std::printf("%s %-20s %s\n", bad ? "FAIL" : "ok  ", iana.c_str(), posix);
    fails += bad != 0;
  }
  // Malformed input must be rejected, not half-parsed.
  for (const char *badtz : {"", "E5", "EST", "EST5EDT,J60,J300", "EST5EDT,M3.2.0", "EST5EDT,M13.1.0,M11.1.0"}) {
    esphome::time::ParsedTimezone tz;
    if (city_tz::parse(badtz, tz)) {
      std::printf("FAIL accepted '%s'\n", badtz);
      fails++;
    }
  }
  return fails ? 1 : 0;
}
