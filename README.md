# ade-drill

Nightly, extensive tests across the better-ade repos. Each repo's own CI checks one pull request at a time with fakes;
the drill checks **everything together, at main, every night, against the real thing**.

| Part | What runs |
|---|---|
| **Suites** | every repo's verification command at `main`, on the runners in `drills/matrix.json` (macOS and Ubuntu) |
| **Drills** | cross-repo checks with real network and no fakes: `pins` (every version one repo pins in another still exists), `project` (install `ade` from main, `ade init` and `ade agent add` against the real ade-method and registry) |
| **Report** | a failing night opens or updates one issue labelled `nightly`; the next green night closes it |

Runs at 08:17 UTC, and on demand: Actions → nightly → Run workflow.

```
bash drills/run.sh            # every drill, locally
bash drills/run.sh pins       # one drill
bash tests/run.sh             # this repo's own check
```

Add a suite or a drill: one entry in `drills/matrix.json` (and `drills/<name>.sh` printing `ok` as its last line).
Planned drills are in `docs/stories/`.
