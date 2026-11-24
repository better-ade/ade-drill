#!/bin/bash
# The scripted model as the reviewer: never the builder's word. It reads the verification command from the project's
# docs/architecture.md (section "Verification command", the first line in backquotes), runs it, and records its real
# output in $DRILL_STATE/review.txt. $DRILL_STATE/focus-done says "pass: <command>" or "fail: <command>": the drill's
# stand-in for the "idle" event a real session's hook sends to the main agent.
set -u
cmd="$(awk '/^## Verification command/ { on = 1; next } /^## / { on = 0 } on && /^`.*`$/ { print substr($0, 2, length($0) - 2); exit }' docs/architecture.md)"
[ -n "$cmd" ] || { echo "reviewer: no verification command in docs/architecture.md"; echo "fail: no verification command" > "$DRILL_STATE/focus-done"; exit 1; }
echo "reviewer: running the verification command: $cmd"
bash -c "$cmd" > "$DRILL_STATE/review.txt" 2>&1; rc=$?
cat "$DRILL_STATE/review.txt"
if [ "$rc" = 0 ]; then echo "reviewer: the verification command passes: Done"; echo "pass: $cmd" > "$DRILL_STATE/focus-done"
else echo "reviewer: the verification command fails (exit $rc): not Done"; echo "fail: $cmd" > "$DRILL_STATE/focus-done"; fi
exit "$rc"
