# D2: the extensive drills

Status: Ready for development (2026-11-21). Risk: medium. Depends on D1 (this repo's first slice: suites, pins, project).

## Goal
More drills, each `drills/<name>.sh`, real tools and no fakes unless stated:
| Drill | What it proves |
|---|---|
| `hub` | a hub made from ade-brain main with `ade hub new --no-github` passes `bin/doctor`, `bin/method check`, and one `bin/work` dry run |
| `setup` | `ade setup` driven through a pty with fake sign-ins reaches the guided-session step; no key on screen, in argv or in a file |
| `upgrade` | install the previous ade-cli release, make a hub and a project, upgrade to main: nothing lost, `ade doctor` green |
| `recover` | kill a fake orchestrator and a fake focus agent mid-task; `bin/recover` brings the hub back and marks the ticket blocked |
| `ui` | `ade ui` under real tmux at 120x36 and 80x24 matches the golden screens |
| `server` | `bin/server install --dry-run` in an `ubuntu:24.04` container prints a complete plan and changes nothing; safety rows fail on an open firewall |
| `secrets` | ade-secrets round-trips a throwaway key on each backend available on the runner and refuses inside a fake agent context |
| `site` | ade.ardata.tech serves `/`, `/guide/`, `/install.sh` (200) and the installer's version matches the latest ade-terminal release |
| `live` (later, owner decision) | one tiny real Claude Code session replies READY, with an API key secret and a monthly spending cap |

## Acceptance criteria
| AC | Criterion |
|---|---|
| 1 | Each drill above (except `live`) exists, is listed in `drills/matrix.json`, runs locally and nightly, and prints `ok` |
| 2 | Each drill cleans up everything it created (temp folders, containers, tmux servers, processes) |
| 3 | A drill that needs a tool the runner lacks says so and fails, never silently passes |
| 4 | The nightly report names each failed suite and drill in the issue body |
