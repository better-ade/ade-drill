"""The raw-Ubuntu drill's recording mode (story D4, RAW_RECORD=1): the run's own screens and the phone's chat, as one
asciinema cast of at most BUDGET seconds, with the times the stand-in caption shows. No I/O here: run.py writes the cast
and drills/raw/record.sh renders it (agg, then ffmpeg) into the MP4 and its poster.

What is shown is what the run showed: each terminal window's output at its own pace (idle gaps shortened, the whole
scaled to fit), the command the person typed above it, and the phone's messages in the order the phone got them. Every
text goes through redact() first, and the cast is refused when leaks() still finds a token, a chat id, a home path with a
user name or an email address.
"""
import json, re

TITLE = "ADE on a fresh Ubuntu 24.04 desktop: recorded in CI"
CAPTION = "Claude sign-in and the focus agents' work are stand-ins in this recording"
COLS, ROWS = 80, 24          # the drill's terminals are 80 x 24 (golden/run.py: Term); the cast has a 25th row, the caption's
BUDGET = 82.0                # seconds of cast; agg's last frame and ffmpeg keep the MP4 under 90 s
MIN_PART = 1.5               # no part of the video is shorter than this
GAP = 0.6                    # an idle gap on a screen is shown as at most this long
HOLD = 1.5                   # the last state of a screen stays this long
PER_MESSAGE = 1.2            # a chat message every this many seconds
CHAPTERS = [
    ("1/3", "Install ade from the README"),
    ("2/3", "ade setup: Claude Code installed, the Telegram bot connected"),
    ("3/3", '"build a website" from Telegram: the architect, then frontend and backend together, then the reviewer'),
]

ANSI = re.compile(r"\x1b(\[[0-9;?<=>]*[ -/]*[@-~]|\][^\x07\x1b]*(\x07|\x1b\\)|[()][0-9A-Za-z]|[=>c78DEHM])")
TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}")
CHAT_RE = re.compile(r"(?i)(chat[_ ]?id\W{0,3})-?\d{5,}|-100\d{6,}")
HOME_RE = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
PAIR_RE = re.compile(r"(pair )[0-9a-f]{6}\b")
CLEAR = "\x1b[0m\x1b[r\x1b[?1049l\x1b[2J\x1b[3J\x1b[1;%dr\x1b[H\x1b[?25h" % ROWS   # the screen's rows only: the caption's row never scrolls


def caption_row(on):
    """drawn after every output: the caption on the 25th row (saved and restored cursor), or that row empty"""
    text = (" " + CAPTION + " ").center(COLS) if on else ""
    return "\x1b7\x1b[%d;1H\x1b[0m\x1b[2K%s\x1b[0m\x1b8" % (ROWS + 1, "\x1b[1;97;48;5;130m" + text if on else "")


def plain(text):
    """the text of a screen: no escape sequences, carriage returns as line ends"""
    return ANSI.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


def redact(text, known=()):
    """the text with every bot token, chat id, home path with a user name, email address and pairing code replaced"""
    text = TOKEN_RE.sub("<token>", text)
    for k in known:
        if k: text = re.sub(r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(k), "<chat>", text)
    text = CHAT_RE.sub(lambda m: (m.group(1) or "") + "<chat>", text)
    text = HOME_RE.sub("~", text)
    text = EMAIL_RE.sub("<email>", text)
    return PAIR_RE.sub(r"\1<code>", text)


def leaks(text, known=()):
    """what redact() should have hidden and is still there, by kind (escape sequences in between hide nothing)"""
    t = plain(text); found = []
    if TOKEN_RE.search(t): found.append("a bot token")
    if CHAT_RE.search(t) or any(k and re.search(r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(k), t) for k in known): found.append("a chat id")
    if HOME_RE.search(t): found.append("a home path with a user name")
    if EMAIL_RE.search(t): found.append("an email address")
    return found


def line_events(raw, marks):
    """[(seconds since the window opened, text)]: the output as it came, cut only at line ends (so a token or a path is
    never split between two events and redacted in neither); the last event takes what is left"""
    if not raw: return []
    t0 = marks[0][0]; out = []; prev = 0
    for i, (t, n) in enumerate(marks[1:], 1):
        cut = n if i == len(marks) - 1 else raw.rfind(b"\n", prev, n) + 1
        if cut > prev: out.append((t - t0, raw[prev:cut].decode("utf-8", "replace"))); prev = cut
    if prev < len(raw): out.append((marks[-1][0] - t0, raw[prev:].decode("utf-8", "replace")))
    return out


def plan(segs, budget):
    """[(start, duration)] per part: cards keep their length; the rest keep theirs when the whole fits, or else share
    what is left by the square root of their length (a long screen still gets more, a short one at least MIN_PART),
    never longer than they were"""
    fixed = sum(s["length"] for s in segs if s["kind"] == "card")
    flex = [max(MIN_PART, s["length"]) for s in segs if s["kind"] != "card"]
    avail = budget - fixed
    def size(k): return [min(l, max(MIN_PART, k * l ** 0.5)) for l in flex]
    if sum(flex) > avail:
        lo, hi = 0.0, max(flex)
        for _ in range(60):
            mid = (lo + hi) / 2
            if sum(size(mid)) > avail: hi = mid
            else: lo = mid
        flex = size(lo)
    out = []; at = 0.0; it = iter(flex)
    for s in segs:
        d = s["length"] if s["kind"] == "card" else next(it)
        out.append((at, d)); at += d
    return out


def is_standin(kind, text):
    """the caption shows on the team's chat (the focus agents' work) and on every screen that says it is a stand-in
    (the Claude sign-in, Claude Code's window)"""
    if kind == "team": return True
    return kind != "card" and "stand-in" in text


def captions(segs, times):
    """[(from, to)]: the stand-in parts, the adjacent ones merged"""
    out = []
    for s, (a, d) in zip(segs, times):
        if not s["standin"]: continue
        if out and abs(out[-1][1] - a) < 1e-6: out[-1] = (out[-1][0], a + d)
        else: out.append((a, a + d))
    return out


def wrap(text, width):
    out = []
    for para in text.split("\n"):
        line = ""
        for w in para.split(" "):
            while len(w) > width: out.append(line) if line else None; line = ""; out.append(w[:width]); w = w[width:]
            if not line: line = w
            elif len(line) + 1 + len(w) <= width: line += " " + w
            else: out.append(line); line = w
        out.append(line)
    return out


def chat_frames(rows, cols=COLS, height=ROWS, footer=None):
    """one full screen per message: the chat so far, the person on the right, the bot on the left, the newest at the
    bottom (older ones scroll off), the footer (what the drill measured) under it"""
    head = " Telegram: your bot (the drill's stand-in Bot API) "
    body_h = height - 1 - (2 if footer else 0); width = cols * 2 // 3; frames = []; lines = []
    for r in rows:
        you = r.get("who") == "you"
        if lines: lines.append("")
        for l in wrap(r.get("text", ""), width - 2):
            cell = " " + l.ljust(width - 2) + " "
            lines.append(" " * (cols - width - 1) + "\x1b[1;97;48;5;25m" + cell + "\x1b[0m" if you else " " + "\x1b[97;48;5;238m" + cell + "\x1b[0m")
        view = lines[-body_h:]; view = view + [""] * (body_h - len(view))
        screen = ["\x1b[1;30;47m" + head.center(cols)[:cols] + "\x1b[0m"] + view
        if footer: screen += ["\x1b[2m" + "-" * cols + "\x1b[0m"] + ["\x1b[1m" + footer[:cols] + "\x1b[0m"]
        frames.append(CLEAR + "\x1b[?25l" + "\r\n".join(screen))
    return frames


def card(lines, cols=COLS, height=ROWS):
    """a full screen of centred lines, the first one bold"""
    body = []
    for i, l in enumerate(lines):
        for w in wrap(l, cols - 8): body.append(("\x1b[1m" if i == 0 else "") + w.center(cols).rstrip() + "\x1b[0m")
    top = max(0, (height - len(body)) // 2)
    return CLEAR + "\x1b[?25l" + "\r\n" * top + "\r\n".join(body)


def recording(screens, phone, ask, known=(), team=None, budget=BUDGET, subs=()):
    """(the asciicast v2 text, [(from, to)] for the caption): a title card, the install and the guide (each terminal
    window with the command typed above it), the phone's chat up to the ask, then the team's chat to the end.
    screens: [{name, step, typed, raw, marks}] in the order shown; phone: [{who, text}] in the order the phone got them.
    subs: [(text, word)] put in first (the drill's own folders). ValueError when a secret is left after redact()."""
    def put(x):
        for a, b in subs: x = x.replace(a, b)
        return redact(x, known)
    segs = [{"kind": "card", "length": 4.5, "frames": [(0.0, card([TITLE, "", "the user flow, as drill D4 of ade-drill runs it",
             "", "1. install ade from the README", "2. ade setup: Claude Code and the Telegram bot",
             '3. "build a website" from Telegram: four roles, then Done']))]}]
    def chapter(i): segs.append({"kind": "card", "length": 2.0, "frames": [(0.0, card(["%s  %s" % CHAPTERS[i]]))]})
    def chat(kind, rows, footer=None):
        if not rows: return
        rows = [dict(r, text=put(r.get("text", ""))) for r in rows]
        fr = chat_frames(rows, footer=put(footer) if footer else None)
        segs.append({"kind": kind, "length": len(fr) * PER_MESSAGE + HOLD, "text": "\n".join(r["text"] for r in rows),
                     "frames": [(i * PER_MESSAGE, f) for i, f in enumerate(fr)]})
    chapter(0); ch = 0
    for s in screens:
        ev = [(t, put(x)) for t, x in line_events(s["raw"], s["marks"])]
        if not plain("".join(x for _, x in ev)).strip(): continue
        if ch == 0 and s.get("step") not in ("install", "quick"): chapter(1); ch = 1
        at = 0.4; last = 0.0; frames = [(0.0, CLEAR + "\x1b[1;32m$\x1b[0m \x1b[1m" + put(s.get("typed", "")) + "\x1b[0m\r\n")]
        for t, x in ev: at += min(GAP, max(0.0, t - last)); last = t; frames.append((at, x))
        segs.append({"kind": "term", "length": at + HOLD, "text": plain("".join(x for _, x in ev)), "frames": frames})
    if ch == 0: chapter(1)
    cut = next((i for i, r in enumerate(phone) if r.get("who") == "you" and r.get("text", "").strip() == ask), len(phone))
    chat("chat", phone[:cut]); chapter(2); chat("team", phone[cut:], team)
    for s in segs: s["standin"] = is_standin(s["kind"], s.get("text", ""))
    times = plan(segs, budget)
    out = [json.dumps({"version": 2, "width": COLS, "height": ROWS + 1, "title": TITLE, "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}})]
    shown = []
    for s, (a, d) in zip(segs, times):
        k = d / s["length"] if s["length"] else 1.0
        for t, x in s["frames"]:
            x += caption_row(s["standin"]); out.append(json.dumps([round(a + t * k, 3), "o", x], ensure_ascii=False)); shown.append(x)
    bad = leaks("".join(shown), known)
    if bad: raise ValueError("the recording would show " + ", ".join(bad))
    return "\n".join(out) + "\n", captions(segs, times)
