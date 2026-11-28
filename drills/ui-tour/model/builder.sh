#!/bin/bash
# The scripted agents of the ui-tour drill (story D5): what api, web and docs do in their tabs. The Claude Code
# stand-in (drills/golden/fakes/claude) runs this in each session it starts with a prompt ("tour agent <name>"). It
# waits for the drill's cue ($DRILL_TOUR/<name>.do), does that, prints what an agent would, and marks the session's
# state the way the hub does (bin/lib.sh session_mark), which is what the tab's icon shows.
set -u
name="${DRILL_PROMPT##* }"; cue="${DRILL_TOUR:?}/$name.do"
hub="$PWD"; while [ "$hub" != / ] && [ ! -f "$hub/bin/lib.sh" ]; do hub="$(dirname "$hub")"; done
[ -f "$hub/bin/lib.sh" ] || { echo "tour agent: no hub above $PWD"; exit 1; }
folder="$hub/projects/$name"
mark() { (cd "$hub" && bash -c '. bin/lib.sh >/dev/null 2>&1; session_mark "$1" "$2"' _ "projects/$name" "$1"); }
say() { printf '%s\n' "$*"; }
say "Claude Code (stand-in) in projects/$name: ready."
while :; do
  if [ -f "$cue" ]; then
    what="$(cat "$cue")"; rm -f "$cue"
    case "$what" in
      busy) mark busy; say ""; say "Working on the invoice export: api/export.py, 3 files" ;;
      waiting) mark waiting; say "Needs you: may I add the invoices table to the database? (y/n)" ;;
      write-prd) cat >> "$folder/_bmad-output/prd.md" <<'MD'

## Billing rules

- An invoice is issued on the first day of the month, for the month before.
- A team pays for the seats it had on the last day of that month.
MD
        say "Wrote the billing rules into the PRD." ;;
      tests) mark busy; say ""; say "\$ bash tests/run.sh"; (cd "$folder" && bash tests/run.sh); say "Done. Tests pass."; mark idle ;;
    esac
  fi
  sleep 0.2
done
