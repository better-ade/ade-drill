#!/bin/bash
# The verification command for this repo: scripts parse, the matrix is valid, every listed drill exists.
cd "$(dirname "$0")/.."; rc=0
for f in drills/*.sh tests/*.sh drills/golden/*.sh drills/golden/model/*.sh drills/golden/fakes/*; do
  case "$f" in *.py|*/claude) python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' "$f" ;; *) bash -n "$f" ;; esac || { echo "FAIL syntax $f"; rc=1; }
  case "$f" in drills/golden/fakes/*) [ -x "$f" ] || { echo "FAIL not executable $f"; rc=1; } ;; esac
done
# the golden-path drill's own parts (story D3); the drill itself needs the network and runs in CI's golden job
python3 tests/test_golden.py 2>&1 | tail -4 | grep -q '^OK' || { echo "FAIL tests/test_golden.py"; python3 tests/test_golden.py 2>&1 | tail -20; rc=1; }
grep -q 'drills/golden.sh' .github/workflows/ci.yml && grep -q 'upload-artifact@' .github/workflows/ci.yml && grep -q 'ade-cli-release' .github/workflows/nightly.yml ||
  { echo "FAIL CI does not run the golden drill, upload its report, or take the release dispatch"; rc=1; }
python3 - <<'PY' || rc=1
import json, os, sys
m = json.load(open("drills/matrix.json")); bad = []
for s in m["suites"]:
    for k in ("repo", "os", "command"):
        if not s.get(k): bad.append(f"suite missing {k}: {s}")
    if s.get("os") not in ("ubuntu-latest", "macos-latest"): bad.append(f"unknown os: {s}")
for d in m["drills"]:
    if not os.path.isfile(f"drills/{d['name']}.sh"): bad.append(f"no drills/{d['name']}.sh")
    if d.get("os") not in ("ubuntu-latest", "macos-latest"): bad.append(f"unknown os: {d}")
print("\n".join("FAIL " + b for b in bad)) if bad else None
sys.exit(1 if bad else 0)
PY
[ $rc = 0 ] && echo ok; exit $rc
