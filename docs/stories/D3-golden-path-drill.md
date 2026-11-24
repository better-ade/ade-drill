# D3: the golden-path drill, and the first-run report

Status: In review (2026-11-23). Risk: medium (tests and docs; a stand-in for every account, nothing of the machine's is
touched). Depends on D1 (this repo's suites and drills). Owner's intent (2026-11-23): "stabilise before adding
features", one golden path made flawless, then "we really need to clean the user experience of setting this up. let's
setup e2e test to really polish this". The path, in the owner's words: "Fresh Mac or fresh ADE Computer → curl … | bash
→ ade guide → hub created and saved to GitHub → Telegram locked, auto mode → ade project add your repo → ask on
Telegram "fix X" → focus agent fixes it → reviewer runs the tests → "Done" plus a screenshot arrives on your phone."
The path's own story, with each step's state and the stories that close its gaps: ade-cli `docs/stories/G1-golden-path.md`.
Verification command: `bash tests/run.sh`. The drill itself: `bash drills/golden.sh` (it needs the network: the release
of `ade` and the hub template are read from GitHub, as anyone can).

## Goal
- **One drill runs the whole path** with the real `ade` (its release, as `curl … | bash` installs it; `GOLDEN_ADE_REF`
  picks a branch), the real hub template (ade-brain `main`) and every script in both, on a terminal of 80 columns and
  24 lines, the person's answers read from files (`drills/golden/answers/`).
- **A stand-in for every account and service** (`drills/golden/fakes/`): Claude Code with its sign-in, its Telegram
  plugin and the model (scripted: `drills/golden/model/`); the GitHub CLI and GitHub (a bare repository in the drill's
  folder); Telegram's Bot API and the owner's phone; systemd's user manager; bun. `security`, `launchctl`, `pass`,
  `gpg` and the clipboard tools are guards: a call fails the drill.
- **Three targets**: `macos` and `linux` (this machine, in a home folder of the drill's own, with only the tools the
  path needs on `PATH`), and `computer` (inside a fresh container of the ADE Computer image, in its own home; local
  Docker only, the image is not public). On a Mac the hub runs its Linux layer (file key store, systemd units inside
  the drill's home): the Mac layer is the login Keychain and launchd, which a drill must never touch; the manual
  checklist covers them.
- **A gap is `pending`, never green**: a step the stand-ins cannot reach because something is not built prints
  `pending <story>` and counts as neither ok nor failed.
- **The drill records what the person sees**: every screen as `transcripts/<screen>.ansi` and `.txt`; with the
  released `ade` the `.txt` files must equal the golden ones (`drills/golden/transcripts/<target>/`), so a change of
  wording fails the drill until the golden file is updated on purpose (`GOLDEN_UPDATE=1`).
- **The first-run report** (`report.md`, each run): steps and their time, every question with its default, every
  place the person must leave the guide, every word from `drills/golden/jargon.txt` used before it is explained,
  every line over 80 columns, every error on the screen, every pending step. It is what set-up is polished against.

## Acceptance criteria (`tests/test_golden.py` for the drill's own parts; the drill run is the end-to-end proof)
| AC | Criterion | Test |
|---|---|---|
| 1 | `bash drills/golden.sh` runs the path on macOS and Linux and prints `ok` last only when no step failed; each step is one `ok`, `pending <story>` or `FAIL` line | the drill, in CI on `ubuntu-latest` and `macos-latest` |
| 2 | Stand-ins only: the Bot API stand-in refuses another token, hands updates over as Telegram does and records what the bot sends (a photo as its bytes); the Claude Code stand-in is signed in only after `auth login`; the `gh` stand-in refuses a call it does not know | `test_bot_api_and_phone`, `test_claude_stand_in_signs_in_only_after_auth_login`, `test_gh_stand_in_refuses_a_call_it_does_not_know` |
| 3 | Nothing of the machine's: a call to `security`, `launchctl`, `pass`, `gpg` or a clipboard tool fails the drill and is recorded; the bot token is on no screen, in no log and in no commit | `test_guard_fails_and_records_a_call`; the drill's `safety` step |
| 4 | The fixture project's test fails before the fix; the scripted builder fixes it and the scripted reviewer runs the verification command from `docs/architecture.md` and records its real output | `test_fails_before_the_fix_and_passes_after_it`; the drill's `fix` and `review` steps |
| 5 | A "Done" reply and a picture reach the Bot API stand-in (the picture when `ade` has `ade shot`; else `pending`), and a message from another account is dropped unanswered | the drill's `phone` and `telegram` steps |
| 6 | Every step that is `pending` names a story listed below | `test_pending_steps_name_a_story_the_drill_story_lists` |
| 7 | Transcripts: escape sequences stripped, what differs between runs replaced, the guide split into its steps | `test_clean_replaces_what_differs_between_runs`, `test_split_guide_names_each_step_and_the_end` |
| 8 | A change of wording fails until the golden file is updated on purpose; each target has golden transcripts with no path of a run and no token | `test_compare_fails_on_a_change_of_wording_until_updated`, `test_every_target_has_its_transcripts_and_they_are_clean` |
| 9 | The report lists the questions with their defaults, the places the person leaves the guide, unexplained words, long lines, errors and pending steps | `test_questions_with_their_defaults`, `test_report_lists_what_to_polish` |
| 10 | CI runs the drill on every pull request, nightly and on an `ade-cli-release` dispatch, and uploads the transcripts and the report | `.github/workflows/ci.yml`, `nightly.yml`, `drills/matrix.json` (checked by `tests/run.sh`) |

## Pending steps and the stories that close them (details: ade-cli `docs/stories/G1-golden-path.md`)
| Story | Repo | The gap |
|---|---|---|
| A21 | ade-cli (PR #60) | `ade project add` is not in a release |
| A20 | ade-cli (merged, #59) | `ade shot` is not in a release, so no picture comes with Done |
| G2 | ade-cli | `ade guide` is an unknown command; the guide is `ade setup` |
| G4 | ade-brain, ade-cli | pairing needs a second terminal and two typed `/telegram:access` commands |
| G5 | ade-brain | a focus agent's permission prompt does not reach the phone |
| G6 | ade-brain | nothing fixes the main agent's route from a chat message to a focus agent and back |
| G7 | ade-brain, ade-skills | nothing tells the main agent to send proof with Done |
| G8 | ade-brain, ade-cli | an existing hub never gets the template's fixes |
| G9 | ade-cli | on macOS `ade work`, called by the main agent, starts a second main session |

## Out of scope
- Real accounts: the manual checklist (`docs/golden-path-manual.md`), once per release.
- The ADE Computer target in CI (the image is not public).
- The macOS Keychain and launchd.
- Building any of the stories above.
