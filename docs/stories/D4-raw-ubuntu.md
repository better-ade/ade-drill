# D4: the user flow on a raw Ubuntu server and a raw Ubuntu desktop

Status: In review (2026-11-24). Risk: high (set medium by the coordinator; raised by the builder: the optional real-bot
mode reads a Telegram bot token from Actions secrets). Depends on D3 (the golden drill's stand-ins, its recorder and its
first-run report are reused, not copied). Owner's words (2026-11-24): "we need to run a UX or User flow test ... it
needs to be seamless in a raw ubuntu server ... ubuntu desktop", and "the entire ux/user flow is to establish claude
code and telegram bot and spawning 5 focus agents". The owner chose GitHub Actions as the test bed, stand-in accounts
now and a real walkthrough by the owner later. Owner rule (2026-11-23): "a user controls everything through Telegram;
remove or relay every terminal-only prompt".
Verification command: `bash tests/run.sh`. The drill itself: `RAW_TARGET=server|desktop bash drills/raw-ubuntu.sh`
(needs Docker and the network; CI runs it).

## The flow (the ade-cli README, read at run time)
1. **Claude Code**: the README's one-line install (`curl ... | bash`, copied from its "Install" section), `ade help` and
   `ade version` from "Quick start", then `ade setup` (the guide the Quick start names) until Claude Code is installed
   and signed in (stand-in sign-in, as in D3).
2. **Telegram**: the same guide connects the bot (the D3 stand-in token and Bot API). From here on the person acts only
   from Telegram: every prompt answered at a terminal after the bot token is a finding.
3. **Build a website, four roles, from Telegram** (owner's scope, 2026-11-24, replacing five generic agents): one message,
   "build a website", to the bot. The main agent (the hub's Telegram session: the coordinator, counted apart from the
   four) loads the scratch repo the person has (`~/Project/website`) with `ade project add`, the core roles with
   `ade init` (ade-method) and frontend and backend with `ade agent add` (ade-agent-registry); a role missing there is a
   finding. It shows the hub's ticket dispatch (`bin/dispatch --list`) and assigns each role with the hub's own start,
   `ade work --role <hub role>` (a role `bin/roles` does not have runs as builder with its role file: a finding), in
   order: the architect (a short note and the verification command: `index.html` is there and `/api/health` answers);
   then frontend (`index.html`) and backend (a tiny Bun server), which may run at the same time; then the reviewer, who
   runs the verification command. Each role reports through the hub's own path (`ade notify main`, which the hub's chat
   forwarder sends to the chat). Done comes only from the reviewer's green run.
`ade hub new` runs inside the guide (its step 4), so the flow needs no separate call.

A friction is a finding, not something to work around. The drill installs nothing the README does not tell the person
to install. When a step fails and the screen says how to fix it (a `sudo apt install ...` line, "run apt-get update
first", a `git config --global` line), the person does that once, it is recorded as leaving the guide, and the step is
tried again. A command missing with no advice on the screen is installed the way a person would
(`sudo apt-get install -y <package>`), recorded as a finding the guide did not cover. Anything else stops the target.

## Targets (each its own container, thrown away afterwards)
- **server**: `ubuntu:24.04` as published, plus only `sudo` and a normal user `you` with password-less sudo (a stand-in
  for the person's own sudo; every use is logged), and the apt lists removed again, as the image ships.
- **desktop**: `ubuntu:24.04` plus what a stock Ubuntu Desktop 24.04 has that matters here, and a display: `python3`,
  `wget`, `xdg-utils`, `ca-certificates`, `procps`, `unzip`, `x11-utils`, `command-not-found` (which tells a person how
  to install a missing command), `sudo`; no `curl`, `git`, `tmux`, `gh` or `gitleaks`. Source: the 24.04.5 desktop
  manifest, https://releases.ubuntu.com/24.04/ubuntu-24.04.5.1-desktop-amd64.manifest (checked 2026-11-24; it lists
  python3 3.12.3, wget, xdg-utils, procps, unzip, x11-utils, command-not-found and sudo, and no curl, git, tmux, gh or
  gitleaks). Firefox is a snap there, which a container cannot run: the desktop target has no browser. The display is
  Xvfb (`DISPLAY=:99`), a stand-in for the desktop's screen. The apt lists are kept, as an installed desktop has them.

What the drill brings that the person does not have, all outside the person's PATH: its own Python
(python-build-standalone, `/opt/drill/python`, sha256 pinned) to run the harness and the stand-ins; the repos and the hub
template prepared on the runner and mounted read-only; an apt hook that puts the D3 stand-ins for `gh` and `curl` in
front of the real ones once apt has installed them (so `gh` signs in to the stand-in GitHub and Claude Code's installer is
the stand-in's); the systemd stand-in (a container has no systemd).

## The report (`report.md` per target, uploaded as an artifact with the transcripts)
Each step's screen (the D3 recorder), every missing tool and how it was found (installed by the guide, fixed by the
person from the screen's advice, or the step failed), every prompt with its answer and whether it was terminal-only
(after the bot token: a Telegram-first finding), every sudo use with its step, the time per step, and for the four
roles: where each role file came from, the hub role it ran as, time from the message to each up and done, to all four
up and to Done, whether frontend and backend overlapped, peak memory and process count of the person's processes,
each role's folder, result and report on the phone.

## Real-bot mode
With the Actions secrets `ADE_DRILL_TELEGRAM_TOKEN` and `ADE_DRILL_TELEGRAM_CHAT` (on push to main, on schedule
and on a workflow_dispatch in better-ade/ade-drill, never a pull request; one job only: server on ade main), the stand-in
Bot API relays a handful of what the bot sends to the real Bot API, to that chat: the guide's connect test, one line
per role and the Done (`DRILL_TG_RELAY_MATCH`, at most `DRILL_TG_RELAY_MAX`=6 a run). The hub and ade only ever hold the stand-in token; the real one
lives in the relay's environment, masked in the log, in no file, report or artifact. What the person sends still comes
through the stand-in update feed (a bot cannot send itself a person's message), and the relay never calls `getUpdates`
or `setWebhook` (a hub live on the same bot keeps its messages). The report says which half was real.

## Acceptance criteria (`tests/test_raw.py` for the drill's own parts; the drill run in CI is the end-to-end proof)
| AC | Criterion | Test |
|---|---|---|
| 1 | Outcome 1: the install line and the guide's commands are copied from the README at run time; a README without them fails the drill | `test_readme_steps_are_read_from_the_readme`, `test_readme_without_the_install_line_fails` |
| 2 | Outcome 1: every missing tool is found from the screen and recorded with how it was found and what the person did | `test_missing_tools_are_found_on_the_screen`, `test_fix_follows_the_screen_advice_only` |
| 3 | Outcome 2: every prompt is recorded with its answer; one answered at a terminal after the bot token is a Telegram-first finding | `test_prompts_after_the_bot_token_are_findings`, `test_answers_pick_by_screen_and_context` |
| 4 | Outcome 3: four roles from their real sources, assigned in order (architect; frontend and backend; reviewer), each reporting to the chat, Done only on the reviewer's green run; time to all up and to Done, peak memory and process count | `test_team_summary_checks_roles_order_reports_and_done`, `test_team_summary_names_each_problem` |
| 5 | The report has the screens, missing tools, prompts, sudo uses with their step, time per step and the team figures | `test_report_lists_every_finding`, `test_sudo_log_is_read_per_step` |
| 6 | Real-bot mode relays only the matching messages, up to the cap, to the real chat, never polls the real token, and the token is in no record | `test_relay_sends_to_the_real_chat_and_never_polls` |
| 7 | CI runs both targets on the ade release and on ade main, on pull requests and nightly, and uploads each report | `.github/workflows/ci.yml`, `nightly.yml`, `drills/matrix.json` (checked by `tests/run.sh`) |

## Out of scope
- Fixing ade-cli or ade-brain: the defects found go in the pull request, each with its step and the real output.
- The owner's real walkthrough on a real server and desktop (later).
- A real desktop session (GNOME, snaps, a browser).
