# D5: a recorded `ade ui` tour for the website, re-made each release

Status: **Approved** (owner, 2026-11-28, as written). Risk: **medium** (CI only, with stand-ins;
no secret, sign-in, data or money; the voiceover is D6). Depends on U5 and U6 being released in ade-cli, and on D4 (the
stand-ins, `drills/raw/stand-ins.sh`, and the recorder, `drills/raw/record.sh` and `video.py`, are reused, not copied).
Verification command: `bash tests/run.sh`. The drill itself: `bash drills/ui-tour.sh` (needs tmux 3.4 and ffmpeg; CI
runs it by hand, `workflow_dispatch`, not on every push).
Owner's words (2026-11-28): "can we add a video demo of this for the website", choosing the `ade ui` tour, placed in a
new section below the hero.

## The script (the owner approves these steps and words; the captions are the words, D6 speaks them)
About 45 seconds at 1280x720, in a hub with three stand-in focus agents (api, web, docs) whose work is scripted.

| # | Screen | Caption |
|---|---|---|
| 1 | `ade ui` opens: tabs main, api, web, docs; the button row | "One terminal, all your agents." |
| 2 | `[+ agent]` → the new-agent menu → `billing` starts | "Start another agent with a click." |
| 3 | A click on tab `api`; its state goes busy `⟳` → done `○` | "Each tab shows which agent is working and which is done." |
| 4 | Right click on `api` → its menu → preview its plan | "Right click for everything a tab can do." |
| 5 | `prefix v` → the docs list → the PRD | "Your PRD, architecture and stories, newest first." |
| 6 | The docs agent writes a section; the PRD redraws live | "Read the plan while it is written." |
| 7 | `w` → the Docs page in a browser, with a diagram | "Open it in the browser, diagrams and all." |
| 8 | Back to the tests: `ok`, "Done. Tests pass." | "Done means the tests pass." |

## Acceptance criteria (each named by its test, tests/test_ui_tour.py)
1. **tour_runs**: `drills/ui-tour.sh` drives a real `ade ui` (the released ade-cli named in `drills/pins.sh`) on a
   private tmux socket through the 8 steps above. Clicks are sent as tmux mouse events at the button's cells, so the
   video shows real clicks, with a pointer drawn on screen where each one lands.
2. **tour_video**: the output is `ade-ui-tour.mp4` (H.264, 1280x720, 30 to 60 seconds, under 8 MB), a PNG poster
   (step 1), and `ade-ui-tour.vtt` with the 8 captions timed to their steps. CI attaches all three as the
   `ade-ui-tour` artifact.
3. **tour_honest**: no real account, token, host name, home path or e-mail appears in any frame. This uses the D4
   recording's redaction. The agents' work and the Claude sign-in are named as stand-ins in `ade-ui-tour.json` (what is real,
   what is not), which the website's caption is taken from.
4. **tour_repeatable**: two runs of the same pins give the same steps and captions, with timings within 0.5 s, so a
   release can re-make the video and the website's test still holds.

## Out of scope
The voiceover (D6); music; other screens than `ade ui` and the Docs page; the website change (W-ui-tour).
