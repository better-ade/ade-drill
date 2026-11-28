# D5b: the tour's step 3 shows busy → done, so the video can be recorded without U4

Status: **Approved** (owner, 2026-11-28: "yes" to changing step 3 from waiting to busy → done, and the caption
"Each tab shows which agent is working and which is done."). Risk: **low** (the drill's script, its fakes and tests; CI only, stand-ins; no secret, sign-in, data
or money). Verification command: `bash tests/run.sh`.

## Why
Step 3 shows a tab going busy → `?` waiting. The `?` state comes with ade-cli's U4, which is not built, so the video
could not be recorded against a release. ade today shows busy `⟳` and idle `○` (ade's `ICON` table).

## The change
| # | Screen | Caption |
|---|---|---|
| 3 (was) | A click on tab `api`; its state goes busy → `?` waiting | "Each tab shows who is working and who needs you." |
| 3 (now) | A click on tab `api`; its state goes busy `⟳` → done `○` | "Each tab shows which agent is working and which is done." |

## Acceptance criteria (tests/test_ui_tour.py)
1. **step3_done**: step 3 marks `api` busy, then idle, and waits for `⟳`, then `○` on its tab; no step needs `?`.
2. **step3_caption**: the captions file, the `.vtt` and D5's story carry the new caption; the other steps are unchanged.
3. The tour's other tests and the verification command pass.

## Out of scope
Recording the video (after the ade-cli release with U5 and U6 and the pin bump), and step 3's waiting state once U4 ships.
