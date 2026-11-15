# Gemensamt för skripten som skriver till TV:ns settingspqdb via provappen och mäter med spotread.
# Läses in med `source`. Kräver att $target är satt (<ip>:<port>) innan pq_connect anropas.

PKG=se.tvcal.pqprobe
FILES="/sdcard/Android/data/$PKG/files"
RESULT="$FILES/out.txt"
sh() { adb -s "$target" shell "$@"; }

pq_connect() {
  local cmd
  for cmd in adb spotread; do
    command -v "$cmd" >/dev/null || { echo "$cmd saknas (scripts/install_arch.sh)" >&2; exit 1; }
  done
  adb connect "$target" >/dev/null 2>&1
  [ "$(adb -s "$target" get-state 2>&1)" = "device" ] || { echo "TV:n svarar inte på $target" >&2; exit 1; }
  sh pm list packages | grep -q "$PKG" || { echo "Provappen $PKG är inte installerad på TV:n" >&2; exit 1; }
}

# probe <nyckel> [extra]: kör provappen och skriver ut raden "<nyckel>=<värde>" ur databasen efteråt.
# Hela raden skrivs ut så att ett tomt värde (offset-nycklarna) skiljer sig från uteblivet svar.
# Resultatfilen tas bort först, så att ett anrop som aldrig nådde fram inte kan se ut att ha
# lyckats med ett gammalt svar.
probe() {
  local k="$1"; shift
  sh rm -f "$RESULT" >/dev/null 2>&1
  sh am start -W -n "$PKG/.ProbeActivity" --es paths none --es keys "$k" "$@" >/dev/null 2>&1
  sleep 1
  sh cat "$RESULT" 2>/dev/null | tr -d '\r' | grep -m1 "^$k="
}
value_of() { local line; line="$(probe "$1")" || return 1; printf '%s' "${line#"$1="}"; }

# set_value <nyckel> <värde>: skriver och läser tillbaka. Anslutningen kan brytas kort, därför flera försök.
set_value() {
  local try
  for try in 1 2 3; do
    [ "$(probe "$1" --es set "$1=$2")" = "$1=$2" ] && return 0
    sleep 2
    adb connect "$target" >/dev/null 2>&1
  done
  return 1
}

# Den aktiva gain-nyckeln ersätter förinställningens värde i HAL:en tills läget laddas om,
# och databasens värde är inte det panelen hade. Byt läge fram och tillbaka.
reload_color_temperature() {
  local mode other
  mode="$(value_of Color_Temperature)" || return 1
  [ "$mode" = Cool ] && other=Warm || other=Cool
  set_value Color_Temperature "$other" && set_value Color_Temperature "$mode"
}
needs_reload() { [[ "$1" =~ ^Color_Temperature_(Red|Green|Blue)_(Gain|Offset)$ ]]; }

# Två avläsningar som "Y,x,y,Y,x,y"; tomt om mätningen misslyckades.
measure_twice() {
  local first second
  first="$(timeout 90 spotread -e -x -O </dev/null 2>&1 \
    | sed -n 's/.*Yxy: \([0-9.]*\) \([0-9.]*\) \([0-9.]*\).*/\1,\2,\3/p')"
  sleep 2
  second="$(timeout 90 spotread -e -x -O </dev/null 2>&1 \
    | sed -n 's/.*Yxy: \([0-9.]*\) \([0-9.]*\) \([0-9.]*\).*/\1,\2,\3/p')"
  [ -n "$first" ] && [ -n "$second" ] && echo "$first,$second"
}

# show_pattern <fönster-procent | fil.mp4>: visar mönstret och sätter $label.
# Video spelas i videoplanet där TV:ns bildbehandling verkar; en vanlig vy hamnar i grafikplanet.
show_pattern() {
  local start
  if [[ "$1" == *.mp4 ]]; then
    [ -f "$1" ] || { echo "Videofilen $1 finns inte" >&2; return 1; }
    local name; name="$(basename "$1")"
    adb -s "$target" push "$1" "$FILES/$name" >/dev/null || { echo "Kunde inte föra över $1" >&2; return 1; }
    start=(--es video "$name"); label="${name%.mp4}"
  else
    start=(--es color ffffff --ei window "$1"); label="window$1"
  fi
  sh am start -S -W -n "$PKG/.PatternActivity" "${start[@]}" >/dev/null 2>&1
  sleep 5
}

probe_dir() {
  local out; out="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/data/probe/$(date +%F)"
  mkdir -p "$out" && echo "$out"
}
