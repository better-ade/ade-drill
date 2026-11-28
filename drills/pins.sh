#!/bin/bash
# Drill: every version one repo pins in another still exists. Real network, no fakes.
. "$(dirname "$0")/lib.sh"
# The released ade-cli the ui-tour drill (story D5, drills/ui-tour.sh) drives: its one place. Override with ADE_UI_TOUR_REF.
ADE_UI_TOUR_REF="${ADE_UI_TOUR_REF:-v0.2.16}"   # PLACEHOLDER: the next release (U5 and U6), not a tag yet; once it is, drop this word
cli="$(clone ade-cli)"; brain="$(clone ade-brain)"; method="$(clone ade-method)"
pin_of() { sed -n "s/^$1=\"\${$1:-\([^}]*\)}\"\$/\1/p" "$cli/ade" | head -1; }
m="$(pin_of ADE_METHOD_REF)"; r="$(pin_of ADE_REGISTRY_REF)"
[ -n "$m" ] && [ -n "$r" ] || fail "could not read ade-cli's pins (ADE_METHOD_REF, ADE_REGISTRY_REF)"
tag_exists ade-method "$m" || fail "ade-cli pins ade-method $m, which is not a tag"
tag_exists ade-agent-registry "$r" || fail "ade-cli pins ade-agent-registry $r, which is not a tag"
hp="$(cd "$brain" && bash -c '. bin/lib.sh >/dev/null 2>&1; method_pin')"
[ -n "$hp" ] || fail "could not read ade-brain's method_pin"
tag_exists ade-method "$hp" || fail "ade-brain pins ade-method $hp, which is not a tag"
read -r sref bref <<EOF2
$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["specialists"]["ref"], d["bmad"]["ref"])' "$method/ade.json")
EOF2
tag_exists ade-agent-registry "$sref" || fail "ade-method pins the registry at $sref, which is not a tag"
code=$(curl -s -o /dev/null -w '%{http_code}' ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} "https://api.github.com/repos/bmad-code-org/BMAD-METHOD/commits/$bref")
[ "$code" = 200 ] || fail "ade-method pins BMAD at $bref, which GitHub does not find (HTTP $code)"
if grep -q '^ADE_UI_TOUR_REF=.*PLACEHOLDER' "$0"; then echo "pins: ui-tour waits for ade-cli $ADE_UI_TOUR_REF (a placeholder until that release)"
else tag_exists ade-cli "$ADE_UI_TOUR_REF" || fail "the ui-tour drill pins ade-cli $ADE_UI_TOUR_REF, which is not a tag"; fi
echo "pins: ade-cli -> method $m, registry $r; ade-brain -> method $hp; ade-method -> registry $sref, BMAD $bref"
echo ok
