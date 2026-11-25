#!/bin/bash
# The scripted model as a focus session on the raw targets (story D4), run by the Claude Code stand-in in the folder its
# session started in, with its first message in DRILL_PROMPT ("role: <role>. Follow .ade/agents/<role>.md. ..."). Small
# scripted work in the website repo, by role: architect: docs/architecture.md (a short note and the verification
# command, bash tests/verify.sh: index.html is there and /api/health answers); frontend: index.html; backend: server.js
# (Bun); reviewer: runs the verification command named in docs/architecture.md, green or red. Each reports through the
# hub's own path (ade notify main, which the hub's chat forwarder sends to the phone), then records
# $DRILL_STATE/done-<role>.json: up and done times, folder, the role file's first line, the result.
set -u; st="${DRILL_STATE:?}"; here="$(pwd -P)"
role="$(printf '%s' "${DRILL_PROMPT:-}" | sed -n 's/^role: \([a-z-]*\)\..*/\1/p')"
[ -n "$role" ] || { echo "builder: no role in the first message"; exit 1; }
t_up="$(date +%s.%N)"; echo "builder: $role up in $here"
persona=""; [ -f ".ade/agents/$role.md" ] && persona="$(head -1 ".ade/agents/$role.md")"
result=ok
case "$role" in
  architect) mkdir -p docs tests
    cat > docs/architecture.md <<'MD'
# Architecture

A one-page website: `index.html` (frontend) and a tiny server, `server.js` on Bun (backend), that serves it and
answers `GET /api/health` with `ok`.

## Verification command

`bash tests/verify.sh`
MD
    cat > tests/verify.sh <<'SH'
#!/bin/bash
# the website's verification command: index.html is there and /api/health answers ok
set -u; cd "$(dirname "$0")/.." || exit 1
[ -s index.html ] || { echo "red: no index.html"; exit 1; }
bun="$(command -v bun || echo "$HOME/.bun/bin/bun")"; [ -x "$bun" ] || { echo "red: no bun to run server.js"; exit 1; }
port=$((20000 + RANDOM % 20000)); PORT=$port "$bun" server.js > /dev/null 2>&1 & pid=$!
ok=1; for _ in $(seq 50); do
  if "$bun" -e "const r = await fetch('http://127.0.0.1:$port/api/health'); process.exit(r.ok && (await r.text()).trim() === 'ok' ? 0 : 1)" 2>/dev/null; then ok=0; break; fi
  sleep 0.2; done
kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
[ "$ok" = 0 ] && echo "green: index.html is there, /api/health answers ok" || echo "red: /api/health did not answer"
exit "$ok"
SH
    text="architect: note and verification command written (bash tests/verify.sh)" ;;
  frontend) sleep 2   # the scripted work takes a moment, as a session's does: frontend and backend can overlap
    printf '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Website</title></head>\n<body><h1>Hello</h1></body></html>\n' > index.html
    text="frontend: index.html written" ;;
  backend) sleep 2
    cat > server.js <<'JS'
const port = Number(process.env.PORT || 3000);
Bun.serve({ port, hostname: "127.0.0.1", fetch(req) {
  const path = new URL(req.url).pathname;
  if (path === "/api/health") return new Response("ok\n");
  if (path === "/") return new Response(Bun.file("index.html"), { headers: { "Content-Type": "text/html" } });
  return new Response("not found\n", { status: 404 });
} });
JS
    text="backend: server.js written (GET /api/health)" ;;
  reviewer) cmd="$(sed -n '/^## Verification command/,$p' docs/architecture.md 2>/dev/null | sed -n 's/^`\(.*\)`$/\1/p' | head -1)"
    if [ -z "$cmd" ]; then result=red; text="reviewer: red: docs/architecture.md names no verification command"
    elif out="$(if command -v timeout >/dev/null; then timeout 60 bash -c "$cmd"; else bash -c "$cmd"; fi 2>&1)"; then result=green; text="reviewer: green: $cmd passed"
    else result=red; text="reviewer: red: $cmd: $(printf '%s' "$out" | tail -1)"; fi
    # the run itself (the command, then its output), for the recording's Review stage
    [ -z "$cmd" ] || { printf '%s\n' "$cmd"; printf '%s\n' "$out" | tail -20; } > "$st/reviewer-run.txt" ;;
  *) result=red; text="$role: not a role this drill scripts" ;;
esac
echo "builder: $text"
if ade notify main "$text"; then echo "builder: reported (ade notify main)"
else echo "builder: ade notify failed; trying the hub's bin/notify"; for h in "$HOME"/hubs/*/; do "$h/bin/notify" main "$text" && break; done; fi
py() { sed 's/\\/\\\\/g; s/"/\\"/g'; }
printf '{"t_up": %s, "t_done": %s, "cwd": "%s", "persona": "%s", "result": "%s", "text": "%s"}\n' "$t_up" "$(date +%s.%N)" "$here" \
  "$(printf '%s' "$persona" | py)" "$result" "$(printf '%s' "$text" | py)" > "$st/done-$role.tmp" && mv "$st/done-$role.tmp" "$st/done-$role.json"
