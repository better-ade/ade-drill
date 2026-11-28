#!/bin/bash
# Drill: the `ade ui` tour video (story D5). A real `ade ui` from the released ade-cli pinned in drills/pins.sh
# (ADE_UI_TOUR_REF), driven with the mouse on a private tmux socket, in eight steps with the owner's captions; recorded
# with D4's recorder (drills/raw/record.sh) as <out>/ade-ui-tour.mp4 (H.264, 1280x720, 30 to 60 s, under 8 MB), its
# poster ade-ui-tour.png (step 1), the captions ade-ui-tour.vtt and ade-ui-tour.json (what is real, what is a stand-in).
#   bash drills/ui-tour.sh          the drill (UI_TOUR_OUT: where the files go, default drills/ui-tour/out)
#   bash drills/ui-tour.sh --pin    the ade-cli release it drives
# It runs the tour UI_TOUR_RUNS times (default 2) and fails unless the runs give the same steps, captions and timings
# (within 0.5 s); the first run is the one recorded. Needs tmux 3.4 or newer, python3, node with playwright
# (UI_TOUR_NODE_PATH) and its Chromium, ffmpeg, ffprobe, a monospace font and the network (ade-cli and the hub template
# are cloned). CI runs it by hand only (workflow_dispatch: the ui-tour job). The drill uses no secret.
set -u; here="$(cd "$(dirname "$0")" && pwd)"
pin="$(sed -n 's/^ADE_UI_TOUR_REF="\${ADE_UI_TOUR_REF:-\([^}]*\)}".*/\1/p' "$here/pins.sh" | head -1)"
ref="${ADE_UI_TOUR_REF:-$pin}"
[ "${1:-}" != --pin ] || { echo "$ref"; exit 0; }
. "$here/lib.sh"
[ -n "$ref" ] || fail "drills/pins.sh names no ade-cli release for the tour (ADE_UI_TOUR_REF)"
for t in tmux python3 node ffmpeg ffprobe git; do command -v "$t" >/dev/null 2>&1 || fail "the ui-tour drill needs $t"; done
v="$(tmux -V | sed -n 's/^tmux \([0-9]*\)\.\([0-9]*\).*/\1 \2/p')"; read -r maj min <<<"${v:-0 0}"
[ "$maj" -gt 3 ] || { [ "$maj" = 3 ] && [ "$min" -ge 4 ]; } || fail "the ui-tour drill needs tmux 3.4 or newer (U5's clickable bar); this is $(tmux -V)"
tag_exists ade-cli "$ref" || fail "ade-cli $ref is not released yet (drills/pins.sh: ADE_UI_TOUR_REF); the tour drives a release"
cli="$(clone ade-cli "$ref")"
out="${UI_TOUR_OUT:-$here/ui-tour/out}"; rm -rf "$out"; mkdir -p "$out" || exit 1
runs="${UI_TOUR_RUNS:-2}"; export ADE_UI_TOUR_REF="$ref"
for i in $(seq 1 "$runs"); do
  echo "tour: run $i of $runs (ade-cli $ref)"
  python3 "$here/ui-tour/run.py" "$out/run-$i" "$cli" || fail "run $i: see $out/run-$i/screen.txt"
done
for i in $(seq 2 "$runs"); do
  python3 "$here/ui-tour/tour.py" same "$out/run-1/ade-ui-tour.json" "$out/run-$i/ade-ui-tour.json" || fail "runs 1 and $i differ"
done
for f in ade-ui-tour.cast ade-ui-tour.json ade-ui-tour.vtt docs-page.png; do cp "$out/run-1/$f" "$out/" || exit 1; done
at="$(python3 -c 'import json, sys; o = json.load(open(sys.argv[1]))["overlay"]; print("%s,%s" % tuple(o))' "$out/ade-ui-tour.json")" || fail "the json has no browser time"
REC_NAME=ade-ui-tour REC_SIZE=1280x720 REC_POSTER_AT=3 REC_OVERLAY="$out/docs-page.png" REC_OVERLAY_AT="$at" \
  bash "$here/raw/record.sh" "$out" || fail "the recording"
python3 "$here/ui-tour/tour.py" check "$out" || fail "the video is not what the story asks"
echo ok
