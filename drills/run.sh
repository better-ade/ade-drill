#!/bin/bash
# drills/run.sh [name...]: run the named drills (default: all listed in matrix.json) and report each.
cd "$(dirname "$0")"; rc=0
names="$*"; [ -n "$names" ] || names="$(python3 -c 'import json; print(" ".join(sorted({d["name"] for d in json.load(open("matrix.json"))["drills"]})))')"
for n in $names; do
  if out=$(bash "./$n.sh" 2>&1) && [ "$(echo "$out" | tail -1)" = ok ]; then echo "ok    $n: $(echo "$out" | tail -2 | head -1)"; else echo "FAIL  $n"; echo "$out" | tail -5; rc=1; fi
done
exit $rc
