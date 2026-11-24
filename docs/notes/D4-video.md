# D4: the run as a video (RAW_RECORD=1)

- **What is recorded:** the terminal windows the drill opened (their pty output with the times it came) and the phone's
  chat (`phone.jsonl`), not the Xvfb display: the person's windows are ptys, so the display shows nothing of them.
- **How:** `drills/raw/video.py` builds one asciicast (80 x 24, plus a 25th row for the caption) in the container;
  `drills/raw/record.sh` renders it on the runner with agg 1.9.0 (pinned by sha256) and ffmpeg (H.264, 10 fps).
- **Time:** idle gaps shortened to 0.6 s; when the whole is longer than 82 s, each part gets time by the square root of
  its length (at least 1.5 s), so the order and the relative weight stay true. The chat shows messages in the order the
  phone got them.
- **Honesty:** a title card ("recorded in CI"), chapter cards, the caption on every part that says it is a stand-in and
  on the team's chat, and a footer with what the drill measured.
- **Secrets:** every text goes through `redact()`; the cast is refused when `leaks()` still finds a bot token, a chat
  id, a home path with a user name or an email. The recording mode refuses the real bot.
