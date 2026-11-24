#!/bin/bash
# The verification command for this repo: scripts parse, the matrix is valid, every listed drill exists.
cd "$(dirname "$0")/.."; rc=0
for f in drills/*.sh tests/*.sh drills/golden/*.sh drills/golden/model/*.sh drills/golden/fakes/*; do
  case "$f" in *.py|*/claude) python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' "$f" ;; *) bash -n "$f" ;; esac || { echo "FAIL syntax $f"; rc=1; }
  case "$f" in drills/golden/fakes/*) [ -x "$f" ] || { echo "FAIL not executable $f"; rc=1; } ;; esac
done
for f in drills/raw/*.sh drills/raw/model/*.sh drills/raw/fakes/* drills/raw/*.py; do
  case "$f" in *.py) python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' "$f" ;; *) bash -n "$f" ;; esac || { echo "FAIL syntax $f"; rc=1; }
  case "$f" in drills/raw/fakes/*|drills/raw/model/*|drills/raw/stand-ins.sh) [ -x "$f" ] || { echo "FAIL not executable $f"; rc=1; } ;; esac
done
# the raw-Ubuntu drill's own parts (story D4); the drill itself needs Docker and the network and runs in CI's raw-ubuntu job
python3 tests/test_raw.py 2>&1 | tail -4 | grep -q '^OK' || { echo "FAIL tests/test_raw.py"; python3 tests/test_raw.py 2>&1 | tail -20; rc=1; }
grep -q 'drills/raw-ubuntu.sh' .github/workflows/ci.yml && grep -q 'raw-${{ matrix.target }}' .github/workflows/ci.yml &&
  grep -q "matrix.name == 'raw-ubuntu'" .github/workflows/nightly.yml && grep -q 'RAW_TARGET' .github/workflows/nightly.yml ||
  { echo "FAIL CI does not run the raw-ubuntu drill on pull requests and nightly, or does not upload its report"; rc=1; }
grep -q "github.event_name != 'pull_request' && github.repository == 'better-ade/ade-drill'" .github/workflows/ci.yml &&
  grep -q '::add-mask::' .github/workflows/ci.yml || { echo "FAIL ci.yml gives the real-bot secrets to more than push in better-ade/ade-drill, or does not mask them"; rc=1; }
# the raw-Ubuntu drill's recording mode (story D4): its logic, and CI records the desktop job only, where no real bot is
python3 tests/test_video.py 2>&1 | tail -4 | grep -q '^OK' || { echo "FAIL tests/test_video.py"; python3 tests/test_video.py 2>&1 | tail -20; rc=1; }
grep -q 'target: desktop, ade: main, record: "1"' .github/workflows/ci.yml && grep -q 'RAW_RECORD: ${{ matrix.record }}' .github/workflows/ci.yml &&
  grep -q 'name: ade-d4-video' .github/workflows/ci.yml && ! grep -q 'target: server.*record' .github/workflows/ci.yml ||
  { echo "FAIL CI does not record the desktop job (and only it) or does not upload the video"; rc=1; }
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
    if d["name"] == "raw-ubuntu" and (d.get("target") not in ("server", "desktop") or d.get("os") != "ubuntu-latest"): bad.append(f"raw-ubuntu needs a target (server or desktop) on ubuntu-latest: {d}")
raw = {(d.get("target"), d.get("ade", "")) for d in m["drills"] if d["name"] == "raw-ubuntu"}
if raw != {(t, a) for t in ("server", "desktop") for a in ("", "main")}: bad.append(f"raw-ubuntu must run server and desktop, on the release and on main: {sorted(raw)}")
print("\n".join("FAIL " + b for b in bad)) if bad else None
sys.exit(1 if bad else 0)
PY
[ $rc = 0 ] && echo ok; exit $rc
