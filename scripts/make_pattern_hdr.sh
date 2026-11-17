#!/usr/bin/env bash
# Gör en HDR10-mönstervideo: en ruta mot svart, HEVC Main10 med PQ, BT.2020 och HDR10-metadata.
# Rutan anges som färdiga 10-bitarskoder (Y', Cb, Cr, begränsat omfång); tvcal/hdr.py räknar fram
# dem från cd/m², så att PQ-räkningen finns på ett ställe och går att testa.
#
# Användning: scripts/make_pattern_hdr.sh <ut.mp4> <Y,Cb,Cr> [ytandel i procent, standard 10] [max-cll]
#   exempel:  scripts/make_pattern_hdr.sh data/patterns/hdr_gray100.mp4 509,512,512
#   max-cll:  "1000,400" (standard), "4000,400", eller "none" för en ström utan HDR10-metadata.
# Bilden ritas direkt i yuv420p10le med geq, så kodvärdena blir exakta utan omräkning. geq är
# långsam, så en ruta ritas och upprepas till 60 s.
set -euo pipefail

[ $# -ge 2 ] || { echo "Användning: $0 <ut.mp4> <Y,Cb,Cr> [procent] [max-cll|none]" >&2; exit 2; }
out="$1"; codes="$2"; percent="${3:-10}"; cll="${4:-1000,400}"
[[ "$codes" =~ ^[0-9]{1,4},[0-9]{1,4},[0-9]{1,4}$ ]] || { echo "Koderna ska vara Y,Cb,Cr" >&2; exit 2; }
IFS=, read -r y cb cr <<<"$codes"
command -v ffmpeg >/dev/null || { echo "ffmpeg saknas" >&2; exit 1; }

# Samma proportioner som skärmen, så sidorna skalas med roten ur ytandelen.
side="$(awk -v p="$percent" 'BEGIN { printf "%.4f", sqrt(p / 100) }')"
lo="$(awk -v s="$side" 'BEGIN { printf "%.4f", (1 - s) / 2 }')"
hi="$(awk -v s="$side" 'BEGIN { printf "%.4f", (1 + s) / 2 }')"
# X/W och Y/H är relativa, så samma uttryck gäller i de halverade krominansplanen.
inside="between(X/W,$lo,$hi)*between(Y/H,$lo,$hi)"

x265="colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:range=limited:log-level=error"
if [ "$cll" != none ]; then
  # P3-primärer och D65 i enheter om 0,00002, luminans i 0,0001 cd/m² (1000 / 0,0001 cd/m²).
  x265="$x265:hdr10=1:repeat-headers=1:max-cll=$cll"
  x265="$x265:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1)"
fi

mkdir -p "$(dirname "$out")"
ffmpeg -loglevel error -y -f lavfi -i color=c=black:s=1920x1080:r=30:d=0.034 \
  -vf "format=yuv420p10le,geq=lum='if($inside,$y,64)':cb='if($inside,$cb,512)':cr='if($inside,$cr,512)',loop=loop=1799:size=1" \
  -c:v libx265 -preset ultrafast -tag:v hvc1 -x265-params "$x265" \
  -color_range tv -colorspace bt2020nc -color_primaries bt2020 -color_trc smpte2084 "$out"
echo "$out"
