#!/bin/bash
# The raw-Ubuntu drill's recording mode (story D4), on the machine that ran the drill: renders <dir>/ade-d4.cast (written
# by run.py with RAW_RECORD=1, already redacted, the stand-in caption on its last row) to <dir>/ade-d4.mp4 (H.264) and
# <dir>/ade-d4.png (the poster: the title card).
#   bash drills/raw/record.sh <dir>
# Needs ffmpeg and ffprobe, a monospace font (DejaVu Sans Mono: fonts-dejavu-core) and python3; agg is downloaded, pinned by
# its sha256 (AGG: a local agg instead). Fails when the MP4 is 90 s or longer or 10 MB or more.
set -u
dir="${1:?the folder with ade-d4.cast}"; cast="$dir/ade-d4.cast"
[ -f "$cast" ] || { echo "RECORD FAIL: no $cast (run the drill with RAW_RECORD=1)" >&2; exit 1; }
for t in ffmpeg ffprobe python3; do command -v "$t" >/dev/null 2>&1 || { echo "RECORD FAIL: needs $t" >&2; exit 1; }; done
cache="${RAW_CACHE:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ade-raw-cache}"; mkdir -p "$cache" || exit 1

AGG_URL=https://github.com/asciinema/agg/releases/download/v1.9.0/agg-x86_64-unknown-linux-gnu
AGG_SHA=f111e315cd71056b116302342553dd765b7297579ed511f111d0cedb442aeda6
agg="${AGG:-$cache/agg-1.9.0}"
if [ -z "${AGG:-}" ] && [ ! -x "$agg" ]; then
  curl -fsSL --retry 3 -o "$agg.part" "$AGG_URL" || { echo "RECORD FAIL: could not download agg" >&2; exit 1; }
  got="$( (sha256sum "$agg.part" 2>/dev/null || shasum -a 256 "$agg.part") | cut -d' ' -f1)"
  [ "$got" = "$AGG_SHA" ] || { rm -f "$agg.part"; echo "RECORD FAIL: agg has sha256 $got, not $AGG_SHA" >&2; exit 1; }
  chmod +x "$agg.part" && mv "$agg.part" "$agg" || exit 1
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/ade-record.XXXXXX")" || exit 1; trap 'rm -rf "$work"' EXIT
"$agg" --font-size 20 --line-height 1.3 --fps-cap 20 --idle-time-limit 1000 --last-frame-duration 3 --theme github-dark \
  --font-family "DejaVu Sans Mono,Menlo" "$cast" "$work/ade.gif" >/dev/null 2>"$work/agg.log" || { cat "$work/agg.log" >&2; echo "RECORD FAIL: agg" >&2; exit 1; }
ffmpeg -nostdin -loglevel error -y -i "$work/ade.gif" -vf "fps=10,pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=0x0d1117" -c:v libx264 -preset slow -crf 28 -pix_fmt yuv420p -movflags +faststart -an "$dir/ade-d4.mp4" ||
  { echo "RECORD FAIL: ffmpeg" >&2; exit 1; }
ffmpeg -nostdin -loglevel error -y -ss 2.5 -i "$dir/ade-d4.mp4" -frames:v 1 "$dir/ade-d4.png" || { echo "RECORD FAIL: the poster" >&2; exit 1; }

dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$dir/ade-d4.mp4")"
size="$(wc -c < "$dir/ade-d4.mp4" | tr -d ' ')"
codec="$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,nb_frames -of csv=p=0 "$dir/ade-d4.mp4")"
echo "recorded: $dir/ade-d4.mp4: ${dur} s, $size bytes, $codec"
python3 -I -c 'import sys; d, s = float(sys.argv[1]), int(sys.argv[2]); sys.exit(0 if d < 90 and s < 10 * 1024 * 1024 else 1)' "$dur" "$size" ||
  { echo "RECORD FAIL: the MP4 must be under 90 s and 10 MB" >&2; exit 1; }
