#!/usr/bin/env bash
# Gör en mönstervideo för pq_sweep.sh: en färgad ruta mot svart, H.264 i BT.709 med begränsat omfång.
# Vitbalans, färgtemperatur och gamma verkar bara på videoplanet, så mönstren ska vara video.
#
# Användning: scripts/make_pattern.sh <ut.mp4> <rrggbb> [ytandel i procent, standard 10]
#   exempel:  scripts/make_pattern.sh data/patterns/gray50.mp4 808080
# Rutan ritas i RGB och konverteras uttryckligen med BT.709-matris; ffmpeg väljer annars BT.601.
set -euo pipefail

[ $# -ge 2 ] || { echo "Användning: $0 <ut.mp4> <rrggbb> [procent]" >&2; exit 2; }
out="$1"; color="$2"; percent="${3:-10}"
[[ "$color" =~ ^[0-9a-fA-F]{6}$ ]] || { echo "Färgen ska vara rrggbb" >&2; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg saknas" >&2; exit 1; }

# Samma proportioner som skärmen, så sidorna skalas med roten ur ytandelen.
side="$(awk -v p="$percent" 'BEGIN { printf "%.4f", sqrt(p / 100) }')"
pos="$(awk -v s="$side" 'BEGIN { printf "%.4f", (1 - s) / 2 }')"

mkdir -p "$(dirname "$out")"
ffmpeg -loglevel error -y -f lavfi -i color=c=black:s=1920x1080:r=30:d=120 \
  -vf "format=rgb24,drawbox=x=iw*$pos:y=ih*$pos:w=iw*$side:h=ih*$side:color=0x$color:t=fill,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p" \
  -c:v libx264 -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 "$out"
echo "$out"
