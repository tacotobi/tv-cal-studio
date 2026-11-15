#!/usr/bin/env bash
# Sveper en bildinställning i TV:ns settingspqdb och mäter vitt med i1Display Pro efter varje steg.
# SKRIVER till TV:n. Värdet som gällde före svepet återställs när skriptet slutar,
# också vid fel eller avbrott. Provappen tar bara emot nycklarna i sin WRITABLE-lista.
#
# Kräver provappen på TV:n (spikes/pqprobe/build.sh, adb install) och mätaren mitt på skärmen.
# Resultat: data/probe/<datum>/<nyckel>_<mönster>_<tid>.csv
#
# Användning: scripts/pq_sweep.sh <tv-ip>[:port] <nyckel> <mönster> <värde>...
#   mönster: vit rutas andel av ytan i procent (100 = helvit bild), ritad som vanlig vy,
#            eller en lokal .mp4 som spelas upp i videoplanet där TV:ns bildbehandling verkar
#   exempel:         scripts/pq_sweep.sh 192.168.1.50 Backlight 10 0 25 50 75 100
#                    scripts/pq_sweep.sh 192.168.1.50 Color_Temperature white10.mp4 Warm Cool Warm
#
# Vitbalans och färgtemperatur verkar bara på videoplanet, så de ska mätas med en video.
# Vit ruta på 10 % av ytan (sidor 0,316 av skärmens) i BT.709 med begränsat omfång:
#   ffmpeg -f lavfi -i color=c=black:s=1920x1080:r=30:d=120 -vf "drawbox=x=iw*0.342:y=ih*0.342:\
#     w=iw*0.316:h=ih*0.316:color=white:t=fill,format=yuv420p" -c:v libx264 -color_range tv \
#     -colorspace bt709 -color_primaries bt709 -color_trc bt709 white10.mp4
# För färgade rutor: rita i RGB och konvertera uttryckligen med BT.709, annars blir matrisen fel:
#   -vf "format=rgb24,drawbox=...:color=0x0000FF:t=fill,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"
set -uo pipefail

[ $# -ge 4 ] || { echo "Användning: $0 <tv-ip>[:port] <nyckel> <mönster> <värde>..." >&2; exit 2; }
target="$1"; key="$2"; pattern="$3"; shift 3
[[ "$target" == *:* ]] || target="$target:5555"
for cmd in adb spotread; do
  command -v "$cmd" >/dev/null || { echo "$cmd saknas (scripts/install_arch.sh)" >&2; exit 1; }
done

PKG=se.tvcal.pqprobe
FILES="/sdcard/Android/data/$PKG/files"
RESULT="$FILES/out.txt"
sh() { adb -s "$target" shell "$@"; }

adb connect "$target" >/dev/null 2>&1
[ "$(adb -s "$target" get-state 2>&1)" = "device" ] || { echo "TV:n svarar inte på $target" >&2; exit 1; }
sh pm list packages | grep -q "$PKG" || { echo "Provappen $PKG är inte installerad på TV:n" >&2; exit 1; }

# probe <nyckel> [extra]: kör provappen och skriver ut databasens värde för nyckeln efteråt.
# Resultatfilen tas bort först, så att ett anrop som aldrig nådde fram inte kan se ut att ha
# lyckats med ett gammalt svar.
probe() {
  local k="$1"; shift
  sh rm -f "$RESULT" >/dev/null 2>&1
  sh am start -W -n "$PKG/.ProbeActivity" --es paths none --es keys "$k" "$@" >/dev/null 2>&1
  sleep 1
  sh cat "$RESULT" 2>/dev/null | tr -d '\r' | sed -n "s/^$k=//p"
}

# set_value <nyckel> <värde>: skriver och läser tillbaka. Anslutningen kan brytas kort, därför flera försök.
set_value() {
  local try
  for try in 1 2 3; do
    [ "$(probe "$1" --es set "$1=$2")" = "$2" ] && return 0
    sleep 2
    adb connect "$target" >/dev/null 2>&1
  done
  return 1
}

measure() {
  timeout 90 spotread -e -x -O </dev/null 2>&1 \
    | sed -n 's/.*Yxy: \([0-9.]*\) \([0-9.]*\) \([0-9.]*\).*/\1,\2,\3/p'
}

original="$(probe "$key")"
[[ "$original" =~ ^[A-Za-z0-9_]+$ ]] || { echo "Kunde inte läsa nuvarande $key" >&2; exit 1; }

restore() {
  if set_value "$key" "$original"; then
    echo "$key återställt till $original"
  else
    echo "VARNING: kunde inte återställa $key till $original – kontrollera TV:n" >&2
  fi
  # Den aktiva gain-nyckeln ersätter förinställningens värde i HAL:en tills läget laddas om,
  # och databasens värde är inte det panelen hade. Byt läge fram och tillbaka.
  if [[ "$key" =~ ^Color_Temperature_(Red|Green|Blue)_(Gain|Offset)$ ]]; then
    local mode other
    mode="$(probe Color_Temperature)"
    [ "$mode" = Cool ] && other=Warm || other=Cool
    if set_value Color_Temperature "$other" && set_value Color_Temperature "$mode"; then
      echo "Färgtemperaturläget $mode omladdat"
    else
      echo "VARNING: kunde inte ladda om färgtemperaturläget $mode – kontrollera TV:n" >&2
    fi
  fi
  sh input keyevent KEYCODE_HOME >/dev/null 2>&1
}
trap restore EXIT
trap 'exit 130' INT TERM

out="$(cd "$(dirname "$0")/.." && pwd)/data/probe/$(date +%F)"
mkdir -p "$out"
if [[ "$pattern" == *.mp4 ]]; then
  [ -f "$pattern" ] || { echo "Videofilen $pattern finns inte" >&2; exit 1; }
  name="$(basename "$pattern")"
  adb -s "$target" push "$pattern" "$FILES/$name" >/dev/null || { echo "Kunde inte föra över $pattern" >&2; exit 1; }
  start=(--es video "$name"); label="${name%.mp4}"
else
  start=(--es color ffffff --ei window "$pattern"); label="window$pattern"
fi
csv="$out/${key}_${label}_$(date +%H%M%S).csv"

sh am start -S -W -n "$PKG/.PatternActivity" "${start[@]}" >/dev/null 2>&1
sleep 5

echo "pattern,$key,Y1,x1,y1,Y2,x2,y2" | tee "$csv"
for value in "$@"; do
  set_value "$key" "$value" || { echo "Skrivningen av $key=$value gick inte igenom – avbryter" >&2; exit 1; }
  sleep 3   # låt bilden stabilisera sig
  first="$(measure)"; sleep 2; second="$(measure)"
  [ -n "$first" ] && [ -n "$second" ] || { echo "Mätningen misslyckades vid $value – avbryter" >&2; exit 1; }
  echo "$label,$value,$first,$second" | tee -a "$csv"
done
echo "Rådata: $csv"
