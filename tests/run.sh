#!/bin/bash
# The verification command for this repo: scripts parse, the matrix is valid, every listed drill exists.
cd "$(dirname "$0")/.."; rc=0
for f in drills/*.sh tests/*.sh; do bash -n "$f" || { echo "FAIL syntax $f"; rc=1; }; done
python3 - <<'PY' || rc=1
import json, os, sys
m = json.load(open("drills/matrix.json")); bad = []
for s in m["suites"]:
    for k in ("repo", "os", "command"):
        if not s.get(k): bad.append(f"suite missing {k}: {s}")
    if s.get("os") not in ("ubuntu-latest", "macos-latest"): bad.append(f"unknown os: {s}")
for d in m["drills"]:
    if not os.path.isfile(f"drills/{d['name']}.sh"): bad.append(f"no drills/{d['name']}.sh")
print("\n".join("FAIL " + b for b in bad)) if bad else None
sys.exit(1 if bad else 0)
PY
[ $rc = 0 ] && echo ok; exit $rc
