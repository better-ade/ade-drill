#!/bin/bash
# The scripted model as the hub's main agent on the raw targets (story D4), run by the Claude Code stand-in at the hub
# root when the paired owner's message arrives: orchestrator.sh <file holding the message>. Lines that start with
# "REPLY: " go to the chat. For "start 5 focus agents, one per repo: svc-1 ... svc-5" it does what the hub gives a main
# agent for it: ade project add (the README's way to load repos you already have), then ade work --prompt per folder.
set -u
msg="$(head -1 "$1")"; names="$(printf '%s' "$msg" | grep -o 'svc-[0-9][0-9]*' | tr '\n' ' ')"
[ -n "$names" ] || { echo "REPLY: Not done: the message names no repo"; exit 1; }
paths=""; for n in $names; do paths="$paths $HOME/Project/$n"; done
echo "dispatch: ade project add$paths --no-init --yes"
# shellcheck disable=SC2086
out="$(ade project add $paths --no-init --yes 2>&1)"; rc=$?; printf '%s\n' "$out"
[ "$rc" = 0 ] || { echo "REPLY: Not done: ade project add ended with exit $rc: $(printf '%s' "$out" | tail -1)"; exit 1; }
started=0; total=0
for n in $names; do total=$((total + 1))
  echo "dispatch: ade work --prompt <the task> projects/$n"
  if out="$(ade work --prompt "You are the focus agent for $n. Report to main when you are up." "projects/$n" 2>&1)"; then started=$((started + 1))
  else echo "REPLY: projects/$n did not start: $(printf '%s' "$out" | tail -1)"; fi
  printf '%s\n' "$out"
done
echo "REPLY: started $started of $total focus agents; each reports here when it is up"
