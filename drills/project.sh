#!/bin/bash
# Drill: install ade from main and set up a real project against the real ade-method and registry. No fakes.
. "$(dirname "$0")/lib.sh"
cli="$(clone ade-cli)"; pre="$WORK/prefix"
bash "$cli/install.sh" "$pre" >/dev/null || fail "install.sh failed"
export PATH="$pre/bin:$PATH" HOME="$WORK/home" ADE_NO_UPDATE_CHECK=1 ADE_NO_CLAUDE_UPDATE=1; mkdir -p "$HOME"
v="$(ade version)" || fail "ade version failed"
[ "${v#ade }" = "$(tr -d ' \n' < "$cli/VERSION")" ] || fail "ade version says [$v], VERSION says $(cat "$cli/VERSION")"
ade help >/dev/null || fail "ade help failed"
p="$WORK/proj"; mkdir -p "$p" && cd "$p" && git init -q . && git config user.email drill@example.invalid && git config user.name drill
ade init >"$WORK/init.out" 2>&1 || fail "ade init failed: $(tail -3 "$WORK/init.out")"
for f in .ade/rules.md .ade/agents/developer.md .ade/agents/reviewer.md _bmad/custom/bmad-build.toml .ade/method-version; do
  [ -s "$f" ] || fail "ade init did not write $f"
done
grep -q "verification command" .ade/rules.md || fail ".ade/rules.md is not the method's rules"
ade agent list >"$WORK/agents.out" 2>&1 || fail "ade agent list failed: $(tail -2 "$WORK/agents.out")"
grep -q "^frontend" "$WORK/agents.out" || fail "ade agent list does not show frontend"
ade agent add frontend >/dev/null 2>&1 || fail "ade agent add frontend failed"
[ -s .ade/agents/frontend.md ] || fail "frontend was not installed"
echo mine > .ade/rules.md; ade init >/dev/null 2>&1 || fail "a second ade init failed"
[ "$(cat .ade/rules.md)" = mine ] || fail "ade init overwrote an existing file"
echo "project: $v, method $(head -1 .ade/method-version)"
echo ok
