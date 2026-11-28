"""The `ade ui` tour (story D5): eight steps of a real `ade ui`, driven with the mouse, recorded as one video.

The logic lives here, with no I/O, so tests/test_ui_tour.py can run it without tmux, ffmpeg or a release:
  STEPS       the eight steps: the owner's caption, its slot in the video and what is done (clicks at the cells where
              the bar and the menus draw their labels, keys, what the scripted agents do, what must show before going on)
  Tour        runs the steps against a driver (run.py: a real `ade ui` on a private tmux socket; the tests: a fake)
  Screen      a model of the terminal tmux draws on, to find where a label is and to scan every frame
  build()     the asciinema cast: the client's output, timed to the plan, with a pointer where each click landed; it is
              redacted as D4's (drills/raw/video.py) and refused when a frame still shows a token, a home path with a
              user name, an email address or this machine's host or user name
  vtt(), manifest(), limits(), same()   the captions, ade-ui-tour.json, the video's limits and the two-run check

Timing: each step runs at the real pace of the programs, held back to its plan (an action never runs before its planned
second); then every real time is mapped onto the plan (warp()), anchored at each action. So two runs give the same
video timings, and how long each step really took is kept in the json ("measured").

  python3 tour.py check <dir>        the video, poster, captions and json in <dir> keep the story's limits
  python3 tour.py same <a> <b>       two runs' json files give the same steps, captions and timings (within 0.5 s)
"""
import codecs, json, os, re, subprocess, sys, unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw"))
import video  # noqa: E402  (D4's redaction: the same patterns, the same rules)

COLS, ROWS = 140, 36          # the client: wide enough for U5's full button row (100 columns or more)
WIDTH, HEIGHT = 1280, 720     # the video
LAST_FRAME = 3.0              # agg keeps the last frame this long (drills/raw/record.sh: --last-frame-duration 3)
POINTER_HOLD = 0.8            # the pointer stays this long after a click; then the client is redrawn without it
PREFIX = "\x02"               # tmux's prefix, C-b
TOLERANCE = 0.5
MEASURED_TOLERANCE = 2.0   # how long each step really took ("measured"): a slower machine changes it               # two runs' timings may differ this much
NAME = "ade-ui-tour"
CAPTION = "Claude, its sign-in and the agents' work are stand-ins in this tour; ade ui, tmux and every click are real"

# (planned second in the step, verb, ...):
#   expect <text> <where>     wait until the text is on the screen (where: "bar", "menu" or None for anywhere)
#   click/rclick <text> <where>  a left/right mouse click on the cell where the text is drawn
#   prefix <key>, key <key>   tmux's prefix then the key; a key
#   agent <name> <what>       the scripted agent in that tab does something (model/builder.sh)
#   state <folder> <icon>     wait until the folder's tab shows that state
#   browser                   wait until ade has opened its link in the (stand-in) browser
STEPS = [
    {"n": 1, "caption": "One terminal, all your agents.", "slot": 5.5,
     "screen": "ade ui opens with tabs main, api, web and docs, and the button row",
     "do": [(1.0, "expect", "[+ agent]", "bar"), (2.5, "expect", "projects/docs", "bar")]},
    {"n": 2, "caption": "Start another agent with a click.", "slot": 6.0,
     "screen": "[+ agent], the new-agent menu, billing starts",
     "do": [(0.5, "click", "[+ agent]", "bar"), (2.0, "click", "projects/billing", "menu"), (3.5, "click", "builder", "menu"),
            (5.0, "expect", "projects/billing", "bar")]},
    {"n": 3, "caption": "Each tab shows which agent is working and which is done.", "slot": 6.0,
     "screen": "a click on tab api; its state goes busy ⟳, then done ○",
     "do": [(0.5, "click", "projects/api", "bar"), (1.5, "agent", "api", "busy"), (2.5, "state", "projects/api", "⟳"),
            (3.5, "agent", "api", "done"), (4.5, "state", "projects/api", "○")]},
    {"n": 4, "caption": "Right click for everything a tab can do.", "slot": 5.5,
     "screen": "a right click on api, its menu, preview its plan",
     "do": [(0.5, "rclick", "projects/api", "bar"), (1.5, "expect", "preview its plan", "menu"),
            (2.5, "click", "preview its plan", "menu"), (4.0, "expect", "Plan: api", None)]},
    {"n": 5, "caption": "Your PRD, architecture and stories, newest first.", "slot": 5.5,
     "screen": "prefix v, the docs list, the PRD",
     "do": [(0.3, "key", "q"), (0.8, "prefix", "v"), (2.0, "expect", "PRD: team invoices", None)]},   # q: the plan's preview closes
    {"n": 6, "caption": "Read the plan while it is written.", "slot": 6.0,
     "screen": "the docs agent writes a section; the PRD redraws live",
     "do": [(0.5, "key", "F"), (1.5, "expect", "## Goals", None), (2.5, "agent", "docs", "write-prd"),
            (4.0, "expect", "## Billing rules", None)]},
    {"n": 7, "caption": "Open it in the browser, diagrams and all.", "slot": 6.0,
     "screen": "w, the Docs page in a browser, with a diagram",
     "do": [(0.5, "key", "q"), (1.0, "expect", "PRD: team invoices", None), (1.5, "key", "w"), (2.5, "browser")]},
    {"n": 8, "caption": "Done means the tests pass.", "slot": 5.5,
     "screen": "back to the tests: ok, Done. Tests pass.",
     "do": [(0.3, "key", "q"), (1.0, "click", "projects/api", "bar"), (2.0, "agent", "api", "tests"),
            (3.5, "expect", "Done. Tests pass.", None)]},
]
REAL = [
    "ade ui from the pinned ade-cli release, in tmux on a private socket, at %dx%d" % (COLS, ROWS),
    "the clicks: tmux mouse events (SGR) sent at the cells where the bar and the menus draw the labels",
    "the hub (ade hub new) and its folders, ade docs with its list and follow view",
    "ade web's Docs page, opened through ade's own link, drawn by Playwright's Chromium",
]
STANDINS = [
    {"what": "Claude Code and its sign-in (drills/golden/fakes/claude)", "why": "no account in a recording"},
    {"what": "the agents' work: what api, web, docs and billing do and print is a script (drills/ui-tour/model/builder.sh)",
     "why": "the tour shows ade, not a model; a script does the same thing every run"},
    {"what": "the desktop browser: a stand-in opener keeps ade's link and a headless Chromium takes the picture shown in step 7",
     "why": "CI has no desktop"},
    {"what": "the pointer: drawn into the recording where each click landed", "why": "a terminal recording has no mouse cursor"},
]


class TourFailed(Exception):
    pass


# ---- the clicks ----

def mouse(x, y, right=False):
    """a press and a release at column x, row y (1-based), as a terminal sends them to tmux (SGR mouse mode)"""
    b = 2 if right else 0
    return ["\x1b[<%d;%d;%dM" % (b, x, y), "\x1b[<%d;%d;%dm" % (b, x, y)]


def width(ch):
    if unicodedata.combining(ch): return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def pointer(row, col, text):
    """drawn over the screen where a click landed: the label in reverse video and an arrow above it (below on row 1)"""
    up = row - 1 if row > 1 else row + 1
    mid = col + max(0, (sum(width(c) for c in text) - 1) // 2)
    return "\x1b7\x1b[%d;%dH\x1b[1;93m▼\x1b[0m\x1b[%d;%dH\x1b[1;7m%s\x1b[0m\x1b8" % (up, mid, row, col, text)


# ---- the screen ----

ESC_RE = re.compile(r"\x1b(?:\[([0-9;?<=>]*)([ -/]*)([@-~])|\][^\x07\x1b]*(?:\x07|\x1b\\)|[()*+][0-9A-Za-z]|([78DEHMc=>]))")


class Screen:
    """the cells a terminal shows, from what tmux writes: cursor moves, erases, scrolling and text (colours ignored)"""

    def __init__(self, cols=COLS, rows=ROWS):
        self.cols, self.rows = cols, rows
        self.cells = [[" "] * cols for _ in range(rows)]
        self.y = self.x = 0; self.top, self.bottom = 0, rows - 1; self.saved = (0, 0); self.wrap = False

    def _blank(self): return [" "] * self.cols

    def _scroll(self, n=1, up=True):
        for _ in range(n):
            if up: del self.cells[self.top]; self.cells.insert(self.bottom, self._blank())
            else: del self.cells[self.bottom]; self.cells.insert(self.top, self._blank())

    def _lf(self):
        if self.y == self.bottom: self._scroll()
        elif self.y < self.rows - 1: self.y += 1

    def _put(self, ch):
        w = width(ch)
        if w == 0:
            if self.x > 0: self.cells[self.y][self.x - 1] += ch
            return
        if self.wrap or self.x + w > self.cols:
            self.x = 0; self._lf(); self.wrap = False
        self.cells[self.y][self.x] = ch
        if w == 2 and self.x + 1 < self.cols: self.cells[self.y][self.x + 1] = ""
        self.x += w
        if self.x >= self.cols: self.x = self.cols - 1; self.wrap = True

    def _csi(self, args, final):
        if args.startswith("?") or args.startswith(">") or args.startswith("<") or args.startswith("="): return
        n = [int(a) if a.isdigit() else 0 for a in args.split(";")] if args else []
        a = n[0] if n else 0; one = a or 1
        if final in "Hf":
            self.y = min(max((n[0] if n and n[0] else 1) - 1, 0), self.rows - 1)
            self.x = min(max((n[1] if len(n) > 1 and n[1] else 1) - 1, 0), self.cols - 1)
        elif final == "A": self.y = max(self.y - one, 0)
        elif final == "B": self.y = min(self.y + one, self.rows - 1)
        elif final == "C": self.x = min(self.x + one, self.cols - 1)
        elif final == "D": self.x = max(self.x - one, 0)
        elif final == "E": self.y = min(self.y + one, self.rows - 1); self.x = 0
        elif final == "F": self.y = max(self.y - one, 0); self.x = 0
        elif final == "G": self.x = min(one - 1, self.cols - 1)
        elif final == "d": self.y = min(one - 1, self.rows - 1)
        elif final == "J":
            if a == 0:
                self.cells[self.y][self.x:] = [" "] * (self.cols - self.x)
                for r in range(self.y + 1, self.rows): self.cells[r] = self._blank()
            elif a == 1:
                self.cells[self.y][:self.x + 1] = [" "] * (self.x + 1)
                for r in range(self.y): self.cells[r] = self._blank()
            else: self.cells = [self._blank() for _ in range(self.rows)]
        elif final == "K":
            if a == 0: self.cells[self.y][self.x:] = [" "] * (self.cols - self.x)
            elif a == 1: self.cells[self.y][:self.x + 1] = [" "] * (self.x + 1)
            else: self.cells[self.y] = self._blank()
        elif final == "X":
            for c in range(self.x, min(self.x + one, self.cols)): self.cells[self.y][c] = " "
        elif final == "@":
            row = self.cells[self.y]; self.cells[self.y] = (row[:self.x] + [" "] * one + row[self.x:])[:self.cols]
        elif final == "P":
            row = self.cells[self.y]; self.cells[self.y] = row[:self.x] + row[self.x + one:] + [" "] * one
        elif final in "LM" and self.top <= self.y <= self.bottom:
            for _ in range(one):
                if final == "L": del self.cells[self.bottom]; self.cells.insert(self.y, self._blank())
                else: del self.cells[self.y]; self.cells.insert(self.bottom, self._blank())
        elif final == "S": self._scroll(one)
        elif final == "T": self._scroll(one, up=False)
        elif final == "r":
            self.top = max((n[0] if n and n[0] else 1) - 1, 0)
            self.bottom = min((n[1] if len(n) > 1 and n[1] else self.rows) - 1, self.rows - 1); self.y = self.x = 0
        elif final == "s": self.saved = (self.y, self.x)
        elif final == "u": self.y, self.x = self.saved
        if final != "m": self.wrap = False

    def feed(self, text):
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b":
                m = ESC_RE.match(text, i)
                if not m: i += 1; continue
                if m.group(3): self._csi(m.group(1), m.group(3))
                elif m.group(4) == "7": self.saved = (self.y, self.x)
                elif m.group(4) == "8": self.y, self.x = self.saved; self.wrap = False
                elif m.group(4) == "M":
                    if self.y == self.top: self._scroll(up=False)
                    else: self.y = max(self.y - 1, 0)
                elif m.group(4) in ("D", "E"):
                    self._lf()
                    if m.group(4) == "E": self.x = 0
                elif m.group(4) == "c": self.__init__(self.cols, self.rows)
                i = m.end(); continue
            if ch == "\r": self.x = 0; self.wrap = False
            elif ch in "\n\x0b\x0c": self._lf(); self.wrap = False
            elif ch == "\b": self.x = max(self.x - 1, 0); self.wrap = False
            elif ch == "\t": self.x = min((self.x // 8 + 1) * 8, self.cols - 1)
            elif ch >= " " and ch != "\x7f": self._put(ch)
            i += 1

    def row(self, r):
        """row r (1-based), as text"""
        return "".join(self.cells[r - 1])

    def text(self):
        return "\n".join(self.row(r).rstrip() for r in range(1, self.rows + 1))

    def find(self, text, where=None):
        """(row, column), 1-based, where the text starts: on the bar (the last row), off it ("menu"), or anywhere"""
        rows = [self.rows] if where == "bar" else range(1, self.rows if where == "menu" else self.rows + 1)
        for r in rows:
            cols, s = [], ""
            for c, cell in enumerate(self.cells[r - 1]):
                for ch in cell: cols.append(c); s += ch
            at = s.find(text)
            if at >= 0: return (r, cols[at] + 1)
        return None


# ---- running the steps ----

class Tour:
    """the steps against a driver: now(), pump(seconds) (lets the programs run and reads what they draw), find(text, where),
    send(data), refresh() (the client redraws the whole screen), agent(name, what), state(folder, icon), browser()"""

    def __init__(self, driver, timeout=45, steps=STEPS):
        self.d, self.timeout, self.steps = driver, timeout, steps

    def _wait(self, step, what, fn):
        end = self.d.now() + self.timeout
        while True:
            v = fn()
            if v: return v
            if self.d.now() >= end:
                raise TourFailed("step %d (%s): waited %d s for %s, which never came" % (step["n"], step["caption"], self.timeout, what))
            self.d.pump(0.05)

    def _until(self, t):
        while self.d.now() < t: self.d.pump(min(0.05, t - self.d.now()))

    def run(self):
        d = self.d; rec = {"steps": [], "browser": None}
        for s in self.steps:
            start = d.now(); anchors, clicks = [], []
            for a in s["do"]:
                at, verb = a[0], a[1]; pos = None
                if verb in ("click", "rclick", "expect"):
                    pos = self._wait(s, "[%s]%s" % (a[2], " on the bar" if a[3] == "bar" else ""), lambda: d.find(a[2], a[3]))
                elif verb == "state": self._wait(s, "%s on tab %s" % (a[3], a[2]), lambda: d.state(a[2], a[3]))
                elif verb == "browser": self._wait(s, "ade's link in the browser", d.browser)
                self._until(start + at)
                now = max(d.now(), start + (anchors[-1][1] + 1e-3 if anchors else 0.0))
                anchors.append((at, now - start))
                if verb in ("click", "rclick"):
                    row, col = d.find(a[2], a[3]) or pos
                    for ev in mouse(col, row, right=verb == "rclick"): d.send(ev)
                    clicks.append((now, row, col, a[2]))
                    self._until(now + POINTER_HOLD); d.refresh()
                elif verb == "prefix": d.send(PREFIX); d.send(a[2])
                elif verb == "key": d.send(a[2])
                elif verb == "agent": d.agent(a[2], a[3])
                elif verb == "browser": rec["browser"] = now
            self._until(start + s["slot"])
            rec["steps"].append({"n": s["n"], "start": start, "end": d.now(), "anchors": anchors, "clicks": clicks})
        return rec


# ---- timing ----

def timeline(steps=STEPS):
    """[(from, to)] of each step in the video"""
    out, t = [], 0.0
    for s in steps: out.append((t, t + s["slot"])); t += s["slot"]
    return out


def warp(x, anchors, real, planned):
    """a real time in a step (0..real) on the plan (0..planned): piecewise linear through each (real, planned) anchor"""
    pts = [(0.0, 0.0)] + list(anchors) + [(max(real, anchors[-1][0] if anchors else 0.0), planned)]
    x = min(max(x, 0.0), pts[-1][0])
    for (r0, p0), (r1, p1) in zip(pts, pts[1:]):
        if x <= r1:
            return p0 if r1 <= r0 else min(p0 + (x - r0) * (p1 - p0) / (r1 - r0), planned)
    return planned


def stamp(t):
    t = round(t, 3); m = int(t // 60)
    return "%02d:%06.3f" % (m, t - 60 * m)


def vtt(steps=STEPS):
    """the captions, one cue per step; the last stays to the end of the video"""
    tl = timeline(steps); out = ["WEBVTT", ""]
    for i, ((a, b), s) in enumerate(zip(tl, steps)):
        out += ["%s --> %s" % (stamp(a), stamp(b + (LAST_FRAME if i == len(steps) - 1 else 0))), s["caption"], ""]
    return "\n".join(out) + "\n"


# ---- what must never show ----

def redact(text, known=()):
    """D4's redaction (tokens, chat ids, home paths with a user name, email addresses), and this machine's names"""
    text = video.redact(text)
    for k in known:
        if k: text = re.sub(r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(k), "<name>", text)
    return text


def scan(text, known=()):
    """what must never be in a frame and is: by kind"""
    t = video.plain(text); found = [k for k in video.leaks(t) if k != "a chat id" or video.CHAT_RE.search(t)]
    if any(k and re.search(r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(k), t) for k in known): found.append("a host or user name")
    return list(dict.fromkeys(found))


# ---- the cast ----

def build(rec, raw, marks, subs=(), known=()):
    """(the asciicast v2 text, facts): the client's output (raw, with marks [(time, bytes so far)]) on the planned
    timeline, with the pointer drawn where each click landed. ValueError when a frame shows what must never show."""
    tl = timeline(); total = tl[-1][1]

    def at(t):
        for s, (a, b) in zip(rec["steps"], tl):
            if t < s["start"]: return a
            if t <= s["end"]:
                return a + warp(t - s["start"], [(r, p) for p, r in s["anchors"]], s["end"] - s["start"], b - a)
        return total

    clicks = [c for s in rec["steps"] for c in s["clicks"]]   # (real time, row, column, label)
    events = []   # (real time, order, text): the pointer first, then what came at that time
    dec = codecs.getincrementaldecoder("utf-8")("replace"); prev = 0
    for t, n in marks[1:]:
        if n > prev: events.append((t, 1, dec.decode(raw[prev:n]))); prev = n
    if prev < len(raw): events.append((marks[-1][0], 1, dec.decode(raw[prev:], final=True)))
    for t, row, col, text in clicks: events.append((t, 0, pointer(row, col, text)))
    events.sort(key=lambda e: (e[0], e[1]))

    screen = Screen(); out = [json.dumps({"version": 2, "width": COLS, "height": ROWS, "env": {"TERM": "xterm-256color"}})]
    last = 0.0
    for t, kind, text in events:
        if kind == 1:
            for a, b in subs: text = text.replace(a, b)
            text = redact(text, known)
            held = [c for c in clicks if c[0] < t < c[0] + POINTER_HOLD]
            if held: text += pointer(*held[-1][1:])
        screen.feed(text)
        bad = scan(text, known) or scan(screen.text(), known)
        v = max(last, round(at(t), 3)); last = v
        if bad: raise ValueError("the frame at %.1f s would show %s; nothing was recorded" % (v, ", ".join(bad)))
        out.append(json.dumps([v, "o", text], ensure_ascii=False))
    facts = {"clicks": [[round(at(t), 3), text] for t, _, _, text in clicks],
             "overlay": [round(at(rec["browser"]), 3), round(tl[6][1], 3)] if rec.get("browser") else None,
             "measured": [round(s["end"] - s["start"], 2) for s in rec["steps"]]}
    return "\n".join(out) + "\n", facts


# ---- what is real, the limits, the two runs ----

def manifest(pin, facts, versions):
    """ade-ui-tour.json: what the video shows, what is real and what is a stand-in"""
    return {"name": NAME, "ade_cli": {"ref": pin, "version": versions.get("ade", "")}, "tools": versions,
            "size": "%dx%d" % (WIDTH, HEIGHT), "terminal": "%dx%d" % (COLS, ROWS), "caption": CAPTION,
            "steps": [{"n": s["n"], "caption": s["caption"], "screen": s["screen"], "from": a, "to": b}
                      for s, (a, b) in zip(STEPS, timeline())],
            "clicks": facts.get("clicks", []), "overlay": facts.get("overlay"), "measured": facts.get("measured", []),
            "real": REAL, "standins": STANDINS}


def limits(p):
    """what breaks the story's limits: H.264, 1280x720, 30 to 60 s, under 8 MB"""
    bad = []
    if p.get("codec") != "h264": bad.append("the video is %s; it must be H.264" % p.get("codec"))
    if (p.get("width"), p.get("height")) != (WIDTH, HEIGHT): bad.append("the video is %sx%s; it must be 1280x720" % (p.get("width"), p.get("height")))
    if not 30 <= p.get("duration", 0) <= 60: bad.append("the video is %.1f s; it must be 30 to 60 s" % p.get("duration", 0))
    if p.get("size", 0) >= 8 * 1024 * 1024: bad.append("the video is %d bytes; it must be under 8 MB" % p.get("size", 0))
    return bad


def same(a, b, tol=TOLERANCE, mtol=MEASURED_TOLERANCE):
    """what differs between two runs' json (nothing: []). The video timings (each step's from/to, the clicks, the browser)
    are planned and held to tol (0.5 s); "measured", how long each step really took, is held to mtol (2 s)."""
    if len(a["steps"]) != len(b["steps"]): return ["the runs have %d steps and %d steps" % (len(a["steps"]), len(b["steps"]))]
    bad = []
    for x, y in zip(a["steps"], b["steps"]):
        if x["caption"] != y["caption"]: bad.append("step %d: the caption differs" % x["n"])
        if abs(x["from"] - y["from"]) > tol or abs(x["to"] - y["to"]) > tol:
            bad.append("step %d: %.2f-%.2f s and %.2f-%.2f s in the video" % (x["n"], x["from"], x["to"], y["from"], y["to"]))
    if len(a["clicks"]) != len(b["clicks"]): bad.append("click count: %d and %d" % (len(a["clicks"]), len(b["clicks"])))
    for i, (x, y) in enumerate(zip(a["clicks"], b["clicks"]), 1):
        if x[1] != y[1] or abs(x[0] - y[0]) > tol: bad.append("click %d: %s at %.2f s and %s at %.2f s" % (i, x[1], x[0], y[1], y[0]))
    ma, mb = a.get("measured", []), b.get("measured", [])
    if len(ma) != len(mb): bad.append("measured: %d steps and %d steps" % (len(ma), len(mb)))
    for i, (x, y) in enumerate(zip(ma, mb), 1):
        if abs(x - y) > mtol: bad.append("step %d took %.1f s and %.1f s (measured)" % (i, x, y))
    oa, ob = a.get("overlay"), b.get("overlay")
    if (oa is None) != (ob is None) or (oa and any(abs(p - q) > tol for p, q in zip(oa, ob))): bad.append("the browser: %s and %s" % (oa, ob))
    return bad


def probe(mp4):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height",
                          "-show_entries", "format=duration", "-of", "json", mp4], capture_output=True, text=True, check=True).stdout
    j = json.loads(out); s = j["streams"][0]
    return {"codec": s["codec_name"], "width": s["width"], "height": s["height"], "duration": float(j["format"]["duration"]),
            "size": os.path.getsize(mp4)}


def main(argv):
    if argv[:1] == ["same"] and len(argv) == 3:
        bad = same(json.load(open(argv[1])), json.load(open(argv[2])))
    elif argv[:1] == ["check"] and len(argv) == 2:
        d = argv[1]; bad = []
        for ext in ("mp4", "png", "vtt", "json"):
            if not os.path.isfile(os.path.join(d, "%s.%s" % (NAME, ext))): bad.append("no %s.%s" % (NAME, ext))
        if not bad:
            bad = limits(probe(os.path.join(d, NAME + ".mp4")))
            if open(os.path.join(d, NAME + ".vtt")).read() != vtt(): bad.append("the captions are not the story's")
    else:
        print(__doc__.strip().split("\n\n")[-1]); return 2
    for b in bad: print("UI TOUR FAIL: " + b, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
