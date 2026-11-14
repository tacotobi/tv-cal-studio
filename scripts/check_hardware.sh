#!/usr/bin/env bash
# Kontrollerar mätare, verktyg och TV-anslutning. Läser bara.
# Användning: scripts/check_hardware.sh [tv-ip]
set -uo pipefail

ok()   { echo "  OK    $*"; }
fail() { echo "  FEL   $*"; rc=1; }
rc=0

echo "Verktyg"
for cmd in spotread adb; do
  command -v "$cmd" >/dev/null && ok "$cmd" || fail "$cmd saknas"
done
[ -x "${ANDROID_SDK:-$HOME/.local/share/android-sdk}/build-tools/34.0.0/d8" ] \
  && ok "Android build-tools 34.0.0" || fail "Android build-tools saknas (scripts/install_arch.sh)"

echo "Mätare"
# i1Display Pro: X-Rite USB-id 0765:5020.
# Läser sysfs i stället för lsusb: usbutils är inte installerat överallt,
# och utan det såg en ansluten mätare ut att saknas.
dev=""
for d in /sys/bus/usb/devices/*; do
  [ "$(cat "$d/idVendor" 2>/dev/null)" = 0765 ] && [ "$(cat "$d/idProduct" 2>/dev/null)" = 5020 ] || continue
  dev="$(printf '/dev/bus/usb/%03d/%03d' "$(cat "$d/busnum")" "$(cat "$d/devnum")")"
  break
done
if [ -n "$dev" ]; then
  ok "i1Display Pro ansluten"
  [ -w "$dev" ] && ok "skrivbar USB-enhet $dev" \
    || fail "ingen behörighet till $dev – dra ur och sätt i mätaren"
else
  fail "i1Display Pro syns inte på USB"
fi

if [ $# -ge 1 ]; then
  echo "TV"
  target="$1"; [[ "$target" == *:* ]] || target="$target:5555"
  adb connect "$target" >/dev/null 2>&1
  state="$(adb -s "$target" get-state 2>&1)"
  if [ "$state" = "device" ]; then
    ok "$target: $(adb -s "$target" shell getprop ro.product.model | tr -d '\r')"
  else
    fail "$target svarar '$state' – godkänn datorn i dialogrutan på TV:n"
  fi
fi
exit $rc
