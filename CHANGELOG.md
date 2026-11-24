# Changelog

## Unreleased

- The `raw-ubuntu` drill's recording mode (story D4, `RAW_RECORD=1`, desktop only, never with the real bot): the run's
  own screens and the phone's chat as an MP4 under 90 s and 10 MB plus a poster, redacted (no token, chat id, home path
  or email), titled "recorded in CI" and captioned where the stand-ins are. CI's desktop job on ade main uploads it as
  `ade-d4-video`.
- The `golden` drill (story D3): the golden path end to end with a stand-in for every account, on macOS, Linux and in a
  fresh ADE Computer container; golden transcripts of every screen, and the first-run report. CI runs it on every pull
  request and nightly, and on an `ade-cli-release` dispatch. `docs/golden-path-manual.md`: the same path by hand.

## 0.1.0

- Nightly workflow: every repo's suite at main, the `pins` and `project` drills, an issue on failure.
