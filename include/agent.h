#pragma once
#include <fcntl.h>
#include <lwip/sockets.h>

#include "esphome/components/lvgl/lvgl_esphome.h"

// Screenshot bridge: push the current LVGL screen to a host over plain TCP.
//
// The Dial has no framebuffer to copy — ili9xxx only allocates one for its own
// drawing API, and LVGL bypasses that and streams tiles straight to the SPI
// panel. A snapshot buffer would be 240*240*2 = 112 KB of internal RAM (there
// is no PSRAM on this module), so instead we borrow the tiles on their way out:
// swap in a flush callback, invalidate the screen, and mirror every tile to the
// socket before handing it to ESPHome's real flush. Costs no extra RAM.
//
// Wire format: repeated tiles until EOF. Each is 4 x int16 LE (x1, y1, x2, y2)
// followed by (x2-x1+1)*(y2-y1+1) big-endian RGB565 pixels (LV_COLOR_16_SWAP).
// scripts/dial.py reassembles them into a PNG.

namespace m5dial {

inline int shot_fd = -1;

inline bool shot_write(const void *data, size_t len) {
  auto *p = static_cast<const uint8_t *>(data);
  while (len != 0) {
    int n = ::send(shot_fd, p, len, 0);
    if (n <= 0)
      return false;
    p += n;
    len -= n;
  }
  return true;
}

inline void shot_flush(lv_display_t *disp, const lv_area_t *area, uint8_t *px) {
  if (shot_fd >= 0) {
    const int16_t hdr[4] = {(int16_t) area->x1, (int16_t) area->y1, (int16_t) area->x2, (int16_t) area->y2};
    const size_t bytes = (size_t) (area->x2 - area->x1 + 1) * (area->y2 - area->y1 + 1) * 2;
    if (!shot_write(hdr, sizeof(hdr)) || !shot_write(px, bytes)) {
      ::close(shot_fd);
      shot_fd = -1;
    }
  }
  esphome::lvgl::LvglComponent::static_flush_cb(disp, area, px);
}

inline void screenshot(const std::string &host, int port) {
  static const char *const TAG = "agent";
  int fd = ::socket(AF_INET, SOCK_STREAM, 0);
  if (fd < 0)
    return;
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(port);
  if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) != 1) {
    ESP_LOGW(TAG, "screenshot: '%s' is not an IPv4 address", host.c_str());
    ::close(fd);
    return;
  }
  // Non-blocking connect with a 2s cap. A wrong address on a blocking socket
  // parks the main loop for the kernel's full SYN retry (~75s), which the task
  // watchdog turns into a reboot.
  int flags = ::fcntl(fd, F_GETFL, 0);
  ::fcntl(fd, F_SETFL, flags | O_NONBLOCK);
  ::connect(fd, (sockaddr *) &addr, sizeof(addr));
  fd_set writable;
  FD_ZERO(&writable);
  FD_SET(fd, &writable);
  timeval timeout{2, 0};
  int err = 0;
  socklen_t err_len = sizeof(err);
  if (::select(fd + 1, nullptr, &writable, nullptr, &timeout) <= 0 ||
      ::getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &err_len) != 0 || err != 0) {
    ESP_LOGW(TAG, "screenshot: cannot reach %s:%d", host.c_str(), port);
    ::close(fd);
    return;
  }
  ::fcntl(fd, F_SETFL, flags);
  timeval send_timeout{5, 0};
  ::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &send_timeout, sizeof(send_timeout));

  shot_fd = fd;
  lv_display_t *disp = lv_display_get_default();
  lv_display_set_flush_cb(disp, shot_flush);
  lv_obj_invalidate(lv_screen_active());
  lv_refr_now(disp);
  lv_display_set_flush_cb(disp, esphome::lvgl::LvglComponent::static_flush_cb);
  if (shot_fd >= 0)
    ::close(shot_fd);
  shot_fd = -1;
  ESP_LOGI(TAG, "screenshot sent to %s:%d", host.c_str(), port);
}

}  // namespace m5dial
