#!/usr/bin/env bash
# Mäter en rad mönster före och efter en uppsättning skrivningar till TV:ns settingspqdb.
# Visar vilka nivåer en inställning påverkar, t.ex. vilken grånivå en punkt i flerpunkts
# vitbalansen styr. SKRIVER till TV:n; alla nycklar återställs i omvänd ordning när skriptet
# slutar, också vid fel eller avbrott.
#
# Kräver provappen på TV:n och mätaren mitt på skärmen.
# Resultat: data/probe/<datum>/levels_<första nyckeln>_<tid>.csv
#
# Användning: scripts/pq_levels.sh <tv-ip>[:port] <nyckel>=<värde>... -- <mönster>...
#   exempel:  scripts/pq_levels.sh 192.168.1.50 PQ_WB_11_Point_enabled=On PQ_WB_11_Point_5_Blue=30 \
#               -- data/patterns/gray{10,20,50,80}.mp4 data/patterns/white.mp4
set -uo pipefail

usage() { echo "Användning: $0 <tv-ip>[:port] <nyckel>=<värde>... -- <mönster>..." >&2; exit 2; }
[ $# -ge 4 ] || usage
target="$1"; shift
[[ "$target" == *:* ]] || target="$target:5555"
writes=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do writes+=("$1"); shift; done
[ "${1:-}" = "--" ] && [ ${#writes[@]} -gt 0 ] || usage
shift; patterns=("$@")
[ ${#patterns[@]} -gt 0 ] || usage

source "$(dirname "$0")/lib/pq.sh"
pq_connect

keys=(); originals=()
for w in "${writes[@]}"; do
  k="${w%%=*}"
  v="$(value_of "$k")" && [[ "$v" =~ ^[A-Za-z0-9_]*$ ]] || { echo "Kunde inte läsa nuvarande $k" >&2; exit 1; }
  keys+=("$k"); originals+=("$v")
done

applied=0
restore() {
  local i reload=0
  for ((i = applied - 1; i >= 0; i--)); do
    if set_value "${keys[i]}" "${originals[i]}"; then
      echo "${keys[i]} återställt till '${originals[i]}'"
    else
      echo "VARNING: kunde inte återställa ${keys[i]} till '${originals[i]}' – kontrollera TV:n" >&2
    fi
    needs_reload "${keys[i]}" && reload=1
  done
  if [ $reload = 1 ]; then
    reload_color_temperature && echo "Färgtemperaturläget omladdat" \
      || echo "VARNING: kunde inte ladda om färgtemperaturläget – kontrollera TV:n" >&2
  fi
  sh input keyevent KEYCODE_HOME >/dev/null 2>&1
}
trap restore EXIT
trap 'exit 130' INT TERM

csv="$(probe_dir)/levels_${keys[0]}_$(date +%H%M%S).csv"
echo "# ${writes[*]}" > "$csv"
echo "pattern,state,Y1,x1,y1,Y2,x2,y2" | tee -a "$csv"

measure_all() {
  local p reading
  for p in "${patterns[@]}"; do
    show_pattern "$p" || exit 1
    reading="$(measure_twice)" || { echo "Mätningen misslyckades på $label – avbryter" >&2; exit 1; }
    echo "$label,$1,$reading" | tee -a "$csv"
  done
}

measure_all before
for i in "${!writes[@]}"; do
  set_value "${keys[i]}" "${writes[i]#*=}" || { echo "Skrivningen ${writes[i]} gick inte igenom – avbryter" >&2; exit 1; }
  applied=$((i + 1))
done
measure_all after
echo "Rådata: $csv"
