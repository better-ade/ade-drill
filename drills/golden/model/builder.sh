#!/bin/bash
# The scripted model as a focus agent (the builder), run by the Claude Code stand-in in the folder the session was
# started in. It does what the message asks for in the only way this fixture needs: it puts the fixed file in place,
# then hands over to the reviewer (model/reviewer.sh), who runs the project's verification command for real.
set -u
[ -f calc.py ] && [ -f docs/architecture.md ] || { echo "builder: this is not the fixture project ($PWD)"; echo "fail: wrong folder" > "$DRILL_STATE/focus-done"; exit 1; }
echo "builder: add() subtracts; fixing calc.py"
cp "$DRILL_MODEL/fix/calc.py" calc.py || { echo "fail: could not write calc.py" > "$DRILL_STATE/focus-done"; exit 1; }
git diff --stat -- calc.py 2>/dev/null | tail -1
bash "$DRILL_MODEL/reviewer.sh"
