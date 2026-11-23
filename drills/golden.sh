#!/bin/bash
# Drill: the golden path, end to end, with a stand-in for every account (story D3; drills/golden/run.py says what is
# real and what is a stand-in). It records every screen the person sees and writes the first-run report.
#   bash drills/golden.sh                         this machine (macOS or Linux), in a home folder of the drill's own
#   GOLDEN_TARGET=computer bash drills/golden.sh  inside a fresh ADE Computer container (local Docker; the image is
#                                                 GOLDEN_IMAGE, default ade-computer:dev), thrown away afterwards
#   GOLDEN_TARGET=linux GOLDEN_IN_IMAGE=1 ...     the linux target inside that image, as a plain Ubuntu machine
# Other settings (GOLDEN_ADE_REF, GOLDEN_OUT, GOLDEN_UPDATE, GOLDEN_KEEP): the top of drills/golden/run.py.
# The container is the drill's own (ade-golden-<pid>, --rm): it never touches another container.
set -u; here="$(cd "$(dirname "$0")" && pwd)"; repo="$(dirname "$here")"
if [ "${GOLDEN_TARGET:-}" != computer ] && [ "${GOLDEN_IN_IMAGE:-}" != 1 ]; then exec python3 "$here/golden/run.py"; fi
command -v docker >/dev/null 2>&1 || { echo "DRILL FAIL: the computer target needs Docker" >&2; exit 1; }
image="${GOLDEN_IMAGE:-ade-computer:dev}"
docker image inspect "$image" >/dev/null 2>&1 || { echo "DRILL FAIL: no image $image here (the ADE Computer image is not public yet: build it from ade-computer)" >&2; exit 1; }
out="${GOLDEN_OUT:-$here/golden/out}"; mkdir -p "$out" || exit 1
mode=ro; [ "${GOLDEN_UPDATE:-}" != 1 ] || mode=rw   # the golden files are written only on purpose
exec docker run --rm --name "ade-golden-$$" -v "$repo:/drill:$mode" -v "$out:/out" \
  -e GOLDEN_INSIDE=1 -e GOLDEN_OUT=/out -e "GOLDEN_TARGET=${GOLDEN_TARGET:-linux}" -e "GOLDEN_ADE_REF=${GOLDEN_ADE_REF:-}" \
  -e "GOLDEN_BRAIN_REF=${GOLDEN_BRAIN_REF:-main}" -e "GOLDEN_UPDATE=${GOLDEN_UPDATE:-}" \
  --entrypoint /bin/bash "$image" -c 'exec python3 /drill/drills/golden/run.py'
