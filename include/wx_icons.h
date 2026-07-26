#pragma once
// WMO weather_code -> Material Design Icons glyph (UTF-8).
// Open-Meteo code groups: https://open-meteo.com/en/docs
// Kept as a free function so it can be shared by every weather lambda; it takes
// a plain int because ESPHome emits includes before the globals are declared.
inline const char *wmo_icon(int code) {
  if (code < 0)   return "\U000F0590";  // weather-cloudy       (unknown)
  if (code == 0)  return "\U000F0599";  // weather-sunny
  if (code <= 2)  return "\U000F0595";  // weather-partly-cloudy
  if (code == 3)  return "\U000F0590";  // weather-cloudy
  if (code <= 48) return "\U000F0591";  // weather-fog
  if (code <= 57) return "\U000F0597";  // weather-rainy        (drizzle)
  if (code <= 67) return "\U000F0596";  // weather-pouring      (rain)
  if (code <= 77) return "\U000F0598";  // weather-snowy
  if (code <= 82) return "\U000F0597";  // weather-rainy        (showers)
  if (code <= 86) return "\U000F0598";  // weather-snowy
  return "\U000F0593";                  // weather-lightning    (thunder)
}

// One-word sky description for the same code groups.
inline const char *wmo_word(int code) {
  if (code < 0)   return "-";
  if (code == 0)  return "CLEAR";
  if (code <= 2)  return "PARTLY";
  if (code == 3)  return "CLOUDY";
  if (code <= 48) return "FOG";
  if (code <= 57) return "DRIZZLE";
  if (code <= 67) return "RAIN";
  if (code <= 77) return "SNOW";
  if (code <= 82) return "SHOWERS";
  if (code <= 86) return "SNOW";
  return "STORM";
}
