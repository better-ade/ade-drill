# ade-drill

Nightly, extensive tests across the better-ade repos. Each repo's own CI checks one pull request at a time with fakes;
the drill checks **everything together, at main, every night, against the real thing**.

| Part | What runs |
|---|---|
| **Suites** | every repo's verification command at `main`, on the runners in `drills/matrix.json` (macOS and Ubuntu) |
| **Drills** | cross-repo checks with real network and no fakes: `pins` (every version one repo pins in another still exists), `project` (install `ade` from main, `ade init` and `ade agent add` against the real ade-method and registry) |
| **Golden path** | `golden`: the owner's one path end to end (install, the guide, hub saved to GitHub, Telegram locked and in auto mode, `ade project add`, "fix X" on Telegram, a focus agent's fix, the reviewer's tests, "Done" and a picture on the phone) with the real `ade` and hub template and a **stand-in for every account** (Claude, GitHub, Telegram); it records every screen and writes the first-run report |
| **Report** | a failing night opens or updates one issue labelled `nightly`; the next green night closes it |

Runs at 08:17 UTC, and on demand: Actions → nightly → Run workflow.

```
bash drills/run.sh            # every drill, locally
bash drills/run.sh pins       # one drill
bash tests/run.sh             # this repo's own check
```

## The golden path (`drills/golden.sh`, story D3)

```
bash drills/golden.sh                          # this machine (macOS or Linux), in a home folder of the drill's own
GOLDEN_TARGET=computer bash drills/golden.sh   # inside a fresh ADE Computer container (local Docker, image ade-computer:dev)
GOLDEN_ADE_REF=main bash drills/golden.sh      # ade from a branch instead of its release
GOLDEN_UPDATE=1 bash drills/golden.sh          # take this run's wording as the golden transcripts, on purpose
```

Each step prints `ok`, `pending <story>` (a gap that is not built: never green) or `FAIL`. Every screen the person sees
goes to `drills/golden/out/transcripts/` and the **first-run report** to `drills/golden/out/report.md`: time per step,
every question and its default, every place the person must leave the guide, every word used before it is explained,
every line over 80 columns. With the released `ade` the transcripts must equal `drills/golden/transcripts/<target>/`:
a change of wording fails the drill until the golden files are updated on purpose. CI runs it on every pull request
and nightly, and uploads the transcripts and the report. Once per release, with real accounts:
`docs/golden-path-manual.md`.

Add a suite or a drill: one entry in `drills/matrix.json` (and `drills/<name>.sh` printing `ok` as its last line).
Planned drills are in `docs/stories/`.
