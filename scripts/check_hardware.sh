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
if lsusb -d 0765:5020 >/dev/null 2>&1; then
  ok "i1Display Pro ansluten ($(lsusb -d 0765:5020 | cut -d' ' -f2,4 | tr -d ':'))"
  dev="/dev/bus/usb/$(lsusb -d 0765:5020 | awk '{print $2"/"substr($4,1,3)}')"
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
