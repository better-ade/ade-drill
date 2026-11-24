#!/bin/bash
# The scripted model as a focus agent on the raw targets (story D4), run by the Claude Code stand-in in the folder its
# session started in. It records that it is up ($DRILL_STATE/up-<repo>.json: when, where), waits until all five are up
# (at most 180 s: an agent that waits on another shows as fewer running together), then reports through the hub's own
# path: ade notify main (bin/notify), which the hub's chat forwarder sends to the phone as "[<agent>] ...".
set -u; st="${DRILL_STATE:?}"; name="$(basename "$PWD")"; here="$(pwd -P)"
printf '{"t": %s, "cwd": "%s"}\n' "$(date +%s.%N)" "$here" > "$st/up-$name.tmp" && mv "$st/up-$name.tmp" "$st/up-$name.json"
echo "builder: up in $here"
i=0; while [ "$(ls "$st"/up-svc-*.json 2>/dev/null | wc -l)" -lt 5 ] && [ "$i" -lt 360 ]; do sleep 0.5; i=$((i + 1)); done
saw="$(ls "$st"/up-svc-*.json 2>/dev/null | wc -l | tr -d ' ')"
t="$(sed -n 's/.*"t": \([0-9.]*\).*/\1/p' "$st/up-$name.json")"
printf '{"t": %s, "cwd": "%s", "saw": %s}\n' "$t" "$here" "$saw" > "$st/up-$name.tmp" && mv "$st/up-$name.tmp" "$st/up-$name.json"
text="up in ~/Project/$name; $saw of 5 running together"
if ade notify main "$text"; then echo "builder: reported (ade notify main)"
else echo "builder: ade notify failed; trying the hub's bin/notify"; for h in "$HOME"/hubs/*/; do "$h/bin/notify" main "$text" && break; done; fi
