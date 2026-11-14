#!/usr/bin/env bash
# Sveper TV:ns bakgrundsljus och mäter vitt med i1Display Pro efter varje steg.
# SKRIVER till TV:ns bildinställning Backlight. Värdet som gällde före svepet
# återställs när skriptet slutar, också vid fel eller avbrott.
#
# Kräver provappen på TV:n (spikes/pqprobe/build.sh, adb install) och mätaren mitt på skärmen.
# Resultat: data/probe/<datum>/backlight_sweep_window<procent>_<tid>.csv
#
# Användning: scripts/backlight_sweep.sh <tv-ip>[:port] <fönster-procent> <värde>...
#   fönster-procent: vit rutas andel av ytan, 100 = helvit bild
#   exempel:         scripts/backlight_sweep.sh 192.168.1.50 10 0 25 50 75 100
set -uo pipefail

[ $# -ge 3 ] || { echo "Användning: $0 <tv-ip>[:port] <fönster-procent> <värde>..." >&2; exit 2; }
target="$1"; window="$2"; shift 2
[[ "$target" == *:* ]] || target="$target:5555"
for cmd in adb spotread; do
  command -v "$cmd" >/dev/null || { echo "$cmd saknas (scripts/install_arch.sh)" >&2; exit 1; }
done

PKG=se.tvcal.pqprobe
RESULT="/sdcard/Android/data/$PKG/files/out.txt"
sh() { adb -s "$target" shell "$@"; }

adb connect "$target" >/dev/null 2>&1
[ "$(adb -s "$target" get-state 2>&1)" = "device" ] || { echo "TV:n svarar inte på $target" >&2; exit 1; }
sh pm list packages | grep -q "$PKG" || { echo "Provappen $PKG är inte installerad på TV:n" >&2; exit 1; }

# Kör provappen och skriver ut databasens Backlight efteråt. Resultatfilen tas bort först,
# så att ett anrop som aldrig nådde fram inte kan se ut att ha lyckats med ett gammalt svar.
probe() {
  sh rm -f "$RESULT" >/dev/null 2>&1
  sh am start -W -n "$PKG/.ProbeActivity" --es paths none --es keys Backlight "$@" >/dev/null 2>&1
  sleep 1
  sh cat "$RESULT" 2>/dev/null | tr -d '\r' | sed -n 's/^Backlight=//p'
}

# Skriver ett värde och läser tillbaka det. Anslutningen kan brytas kort, därför flera försök.
set_backlight() {
  local try
  for try in 1 2 3; do
    [ "$(probe --es set "Backlight=$1")" = "$1" ] && return 0
    sleep 2
    adb connect "$target" >/dev/null 2>&1
  done
  return 1
}

measure() {
  timeout 90 spotread -e -x -O </dev/null 2>&1 \
    | sed -n 's/.*Yxy: \([0-9.]*\) \([0-9.]*\) \([0-9.]*\).*/\1,\2,\3/p'
}

original="$(probe)"
[[ "$original" =~ ^[0-9]+$ ]] || { echo "Kunde inte läsa nuvarande Backlight" >&2; exit 1; }

restore() {
  if set_backlight "$original"; then
    echo "Backlight återställt till $original"
  else
    echo "VARNING: kunde inte återställa Backlight till $original – kontrollera TV:n" >&2
  fi
  sh input keyevent KEYCODE_HOME >/dev/null 2>&1
}
trap restore EXIT
trap 'exit 130' INT TERM

out="$(cd "$(dirname "$0")/.." && pwd)/data/probe/$(date +%F)"
mkdir -p "$out"
csv="$out/backlight_sweep_window${window}_$(date +%H%M%S).csv"

sh am start -S -W -n "$PKG/.PatternActivity" --es color ffffff --ei window "$window" >/dev/null 2>&1
sleep 5

echo "window,backlight,Y1,x1,y1,Y2,x2,y2" | tee "$csv"
for value in "$@"; do
  set_backlight "$value" || { echo "Skrivningen av $value gick inte igenom – avbryter" >&2; exit 1; }
  sleep 3   # låt bakgrundsljuset stabilisera sig
  first="$(measure)"; sleep 2; second="$(measure)"
  [ -n "$first" ] && [ -n "$second" ] || { echo "Mätningen misslyckades vid $value – avbryter" >&2; exit 1; }
  echo "$window,$value,$first,$second" | tee -a "$csv"
done
echo "Rådata: $csv"
