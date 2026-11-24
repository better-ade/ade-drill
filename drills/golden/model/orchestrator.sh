#!/bin/bash
# The scripted model as the hub's main agent, run by the Claude Code stand-in at the hub root when a message from the
# paired owner arrives: orchestrator.sh <file holding the message>. Lines that start with "REPLY: " go back to the chat
# through the plugin's reply tool; every other line is only logged.
#   1. the work goes to a focus agent in the project's folder: ade work --prompt <the message> projects/<name>
#   2. it waits until the focus agent's reviewer has run the verification command ($DRILL_STATE/focus-done)
#   3. "Done" (or "Not done") goes to the chat, and, when ade has `ade shot`, a picture of the focus agent's tab
set -u
msg="$(head -1 "$1")"; folder=""
# the project the message names (a word of it that is a folder under projects/)
for w in $(printf '%s' "$msg" | tr -c 'a-z0-9-' ' '); do [ -d "projects/$w" ] && { folder="projects/$w"; break; }; done
[ -n "$folder" ] || { echo "REPLY: Not done: the message names no project of this hub"; exit 1; }
name="${folder#projects/}"
echo "dispatch: ade work --prompt <the message> $folder"
ade work --prompt "$msg" "$folder" 2>&1 || { echo "REPLY: Not done: the focus agent for $name did not start"; exit 1; }
i=0; while [ ! -s "$DRILL_STATE/focus-done" ] && [ "$i" -lt 120 ]; do sleep 0.5; i=$((i + 1)); done
res="$(cat "$DRILL_STATE/focus-done" 2>/dev/null)"
case "$res" in
  pass:*) echo "REPLY: Done: $msg ($name). The reviewer ran${res#pass:} and it passes." ;;
  *) echo "REPLY: Not done: $msg ($name). ${res:-the focus agent did not finish}"; exit 1 ;;
esac
if ade shot --help >/dev/null 2>&1; then
  echo "proof: ade shot agent $name --tg"
  ade shot agent "$name" --tg "Done: $name, the tests pass" 2>&1 | sed 's/^/shot: /'
else echo "proof: this ade has no ade shot"; fi
