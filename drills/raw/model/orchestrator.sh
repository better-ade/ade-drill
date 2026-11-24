#!/bin/bash
# The scripted model as the hub's main agent on the raw targets (story D4), run by the Claude Code stand-in at the hub
# root when the paired owner's message arrives: orchestrator.sh <file holding the message>. Lines that start with
# "REPLY: " go to the chat; the final Done or Not done goes through the hub's bin/chat done. For "build a website" it is the coordinator of four roles, with what the hub and ade give it:
#   ade project add ~/Project/website (the README's way to load a repo you have), ade init (the core roles, from
#   ade-method), ade agent add frontend and backend (specialists, from ade-agent-registry), bin/dispatch --list (the hub's
#   ticket dispatch: shown, it starts BMAD tickets only), then ade work --role <hub role> per role, in order: architect;
#   frontend and backend together; the reviewer. A role the hub has no --role for (bin/roles) runs as builder with its
#   role file. Each session records $DRILL_STATE/done-<role>.json when it is done (the stand-in's handoff signal; a real
#   coordinator reads the session's note). Done only on the reviewer's green run.
set -u; st="${DRILL_STATE:?}"; hub="$PWD"; repo="$HOME/Project/website"
msg="$(head -1 "$1")"
case "$msg" in *"build a website"*) ;; *) echo "REPLY: Not done: I only know \"build a website\" here"; exit 1 ;; esac
echo "dispatch: ade project add $repo --no-init --yes"
out="$(ade project add "$repo" --no-init --yes 2>&1)"; rc=$?; printf '%s\n' "$out"
[ "$rc" = 0 ] || { echo "REPLY: Not done: ade project add ended with exit $rc: $(printf '%s' "$out" | tail -1)"; exit 1; }
echo "roles: ade init"; (cd "$repo" && ade init 2>&1); echo "roles: ade init exit $?"
for s in frontend backend; do echo "roles: ade agent add $s"; (cd "$repo" && ade agent add "$s" 2>&1); echo "roles: ade agent add $s exit $?"; done
echo "dispatch: bin/dispatch --list projects/website"; "$hub/bin/dispatch" --list projects/website 2>&1 | sed 's/^/dispatch: /'
hubroles="$(ade roles 2>/dev/null | awk '{print $1}')"
assign() {   # assign <role> <source>
  local r="$1" src="$2" hr="$1" out rc
  printf '%s\n' "$hubroles" | grep -qx "$r" || hr=builder
  echo "assign: $r: ade work --role $hr --name website-$r projects/website"
  printf '{"t": %s, "hub_role": "%s", "persona": ".ade/agents/%s.md", "source": "%s"}\n' "$(date +%s.%N)" "$hr" "$r" "$src" > "$st/assign-$r.json"
  out="$(ade work --role "$hr" --name "website-$r" --prompt "role: $r. Follow .ade/agents/$r.md. The owner's task: build a website. Report to main when done." projects/website 2>&1)"; rc=$?
  printf '%s\n' "$out"
  [ "$rc" = 0 ] || echo "REPLY: Not done: $r did not start (ade work exit $rc): $(printf '%s' "$out" | tail -1)"
  return "$rc"
}
wait_done() { local r i; for r in "$@"; do i=0; while [ ! -f "$st/done-$r.json" ] && [ "$i" -lt 360 ]; do sleep 0.5; i=$((i + 1)); done
  [ -f "$st/done-$r.json" ] || { echo "REPLY: Not done: $r did not finish in 180 s"; return 1; }; done; }
assign architect ade-method && wait_done architect || exit 1
assign frontend ade-agent-registry; f=$?; assign backend ade-agent-registry; b=$?
[ "$f$b" = 00 ] && wait_done frontend backend || exit 1
assign reviewer ade-method && wait_done reviewer || exit 1
# The final word goes through bin/chat done (ade-brain P2): the agents' queued notes first, then this, last. A hub from
# before P2 has no `done`; there it is a REPLY, as before.
final() { if grep -q '^ *"done")' "$hub/bin/chat" 2>/dev/null; then "$hub/bin/chat" done "$1"; else echo "REPLY: $1"; fi; }
if grep -q '"result": "green"' "$st/done-reviewer.json"; then final "Done: build a website; the reviewer's run of the verification command is green"
else final "Not done: build a website; the reviewer's run is red"; fi
