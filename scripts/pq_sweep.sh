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
# Vitbalans, färgtemperatur och gamma verkar bara på videoplanet, så de ska mätas med en video
# från scripts/make_pattern.sh.
set -uo pipefail

[ $# -ge 4 ] || { echo "Användning: $0 <tv-ip>[:port] <nyckel> <mönster> <värde>..." >&2; exit 2; }
target="$1"; key="$2"; pattern="$3"; shift 3
[[ "$target" == *:* ]] || target="$target:5555"
source "$(dirname "$0")/lib/pq.sh"
pq_connect

original="$(value_of "$key")" && [[ "$original" =~ ^[A-Za-z0-9_]*$ ]] \
  || { echo "Kunde inte läsa nuvarande $key" >&2; exit 1; }

restore() {
  if set_value "$key" "$original"; then
    echo "$key återställt till '$original'"
  else
    echo "VARNING: kunde inte återställa $key till '$original' – kontrollera TV:n" >&2
  fi
  if needs_reload "$key"; then
    reload_color_temperature && echo "Färgtemperaturläget omladdat" \
      || echo "VARNING: kunde inte ladda om färgtemperaturläget – kontrollera TV:n" >&2
  fi
  sh input keyevent KEYCODE_HOME >/dev/null 2>&1
}
trap restore EXIT
trap 'exit 130' INT TERM

show_pattern "$pattern" || exit 1
csv="$(probe_dir)/${key}_${label}_$(date +%H%M%S).csv"

echo "pattern,$key,Y1,x1,y1,Y2,x2,y2" | tee "$csv"
for value in "$@"; do
  set_value "$key" "$value" || { echo "Skrivningen av $key=$value gick inte igenom – avbryter" >&2; exit 1; }
  sleep 3   # låt bilden stabilisera sig
  reading="$(measure_twice)" || { echo "Mätningen misslyckades vid $value – avbryter" >&2; exit 1; }
  echo "$label,$value,$reading" | tee -a "$csv"
done
echo "Rådata: $csv"
