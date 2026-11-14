#!/usr/bin/env bash
# Läser av TV:n via ADB och sparar rådata i data/probe/<datum>/.
# Skriver ingenting till TV:n – bara getprop, settings list, dumpsys och pm.
#
# Användning: scripts/detect_tv.sh <tv-ip>[:port]
set -euo pipefail

[ $# -eq 1 ] || { echo "Användning: $0 <tv-ip>[:port]" >&2; exit 2; }
command -v adb >/dev/null || { echo "adb saknas: sudo pacman -S android-tools" >&2; exit 1; }

target="$1"
[[ "$target" == *:* ]] || target="$target:5555"

adb connect "$target" >/dev/null
state="$(adb -s "$target" get-state 2>&1 || true)"
if [ "$state" != "device" ]; then
  echo "TV:n svarar inte som 'device' (läge: $state)." >&2
  echo "Godkänn datorn i dialogrutan på TV:n och kör igen." >&2
  exit 1
fi

out="$(cd "$(dirname "$0")/.." && pwd)/data/probe/$(date +%F)"
mkdir -p "$out"
sh() { adb -s "$target" shell "$@"; }

sh getprop                       > "$out/getprop.txt"
sh settings list global          > "$out/settings_global.txt"
sh settings list system          > "$out/settings_system.txt"
sh settings list secure          > "$out/settings_secure.txt"
sh dumpsys display               > "$out/display.txt"
sh pm list packages -f           > "$out/packages.txt"
sh service list                  > "$out/services.txt"
sh dumpsys package providers     > "$out/providers.txt"

prop() { sed -n "s/^\[$1\]: \[\(.*\)\]$/\1/p" "$out/getprop.txt"; }

echo "Modell:        $(prop ro.product.brand) $(prop ro.product.model) ($(prop ro.product.device))"
echo "Android:       $(prop ro.build.version.release) (SDK $(prop ro.build.version.sdk))"
echo "Firmware:      $(prop ro.build.version.incremental)"
echo "SoC:           $(prop ro.soc.manufacturer) $(prop ro.soc.model), $(prop ro.product.cpu.abi)"
echo "Panel:         $(sh wm size | head -1 | sed 's/.*: //')"
# HDR-typer enligt android.view.Display.HdrCapabilities: 1=Dolby Vision 2=HDR10 3=HLG 4=HDR10+
echo "HDR-typer:     $(grep -o 'supportedHdrTypes=\[[^]]*\]' "$out/display.txt" | head -1)"
echo "Bildläge:      $(grep -E '^picture_(mode|backlight|gamma)=' "$out/settings_global.txt" | tr '\n' ' ')"
echo "MediaTek PQ:   $(grep -c 'com.mediatek.tv.settingspqdb' "$out/providers.txt" || true) träff(ar) på settingspqdb"
echo "Calman-app:    $(grep -c 'com.mediatek.calman' "$out/packages.txt" || true) träff(ar)"
echo "Rådata:        $out"
