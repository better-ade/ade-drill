"""What the person saw, for the golden-path drill: transcripts, the golden files and the first-run report.

A screen is everything one step put on the terminal. Each is written twice into <out>/transcripts/: <step>.ansi (as it
came) and <step>.txt (escape sequences stripped, and what differs from run to run replaced: see clean()). The .txt files
are compared with the golden ones in drills/golden/transcripts/<target>/; a change of wording fails the drill until the
golden file is updated on purpose (GOLDEN_UPDATE=1).
"""
import difflib, os, re

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b[=>()][0-9A-Za-z]?")
STEP = re.compile(r"^Step (\d+) of (\d+): (.+)$", re.M)


def plain(raw):
    """the text of a screen: no escape sequences, no carriage returns, backspaces applied"""
    t = ANSI.sub("", raw.decode("utf-8", "replace")).replace("\r\n", "\n").replace("\r", "\n")
    while "\b" in t: t = re.sub(r"[^\n]?\x08", "", t, count=1)
    return t


def clean(text, subs):
    """a screen as a golden file holds it: the drill's own folders, and what differs from run to run, as fixed words"""
    for a, b in subs: text = text.replace(a, b)
    text = re.sub(r"\((\d+)s\)", "(Ns)", text)
    text = re.sub(r"\b20\d\d-\d\d-\d\d\b", "<date>", text)
    text = re.sub(r"(<date>) \d\d:\d\d\b", r"\1 <time>", text)
    text = re.sub(r"\b(synced|sync): [0-9a-f]{7,40}\b", r"\1: <commit>", text)
    text = re.sub(r"\bpid \d+", "pid <pid>", text)
    text = re.sub(r"\bade (\d+\.\d+\.\d+)\b", "ade <version>", text)
    text = re.sub(r"127\.0\.0\.1:\d+", "127.0.0.1:<port>", text)
    text = re.sub(r"(/telegram:access pair )[0-9a-f]{6}\b", r"\1<code>", text)
    return "\n".join(l.rstrip() for l in text.split("\n")).strip("\n") + "\n"


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def split_guide(text):
    """the guide's one long screen as its steps: [(name, text)], in the order shown"""
    parts = []; marks = list(STEP.finditer(text))
    if not marks: return [("guide", text)]
    parts.append(("guide-0-start", text[:marks[0].start()]))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end]
        if i + 1 == len(marks):   # the guide's last lines come after a blank line
            cut = max(body.rfind("\n\nAll set"), body.rfind("\n\nNot finished"))
            if cut > 0:
                parts.append(("guide-%s-%s" % (m.group(1), slug(m.group(3))), body[:cut])); parts.append(("guide-9-end", body[cut:])); continue
        parts.append(("guide-%s-%s" % (m.group(1), slug(m.group(3))), body))
    return parts


def compare(out_dir, golden_dir, update):
    """[] when every transcript equals its golden file; else one line per difference (a diff is written beside it)"""
    bad = []; mine = sorted(n for n in os.listdir(out_dir) if n.endswith(".txt"))
    theirs = sorted(n for n in os.listdir(golden_dir) if n.endswith(".txt")) if os.path.isdir(golden_dir) else []
    if update:
        os.makedirs(golden_dir, exist_ok=True)
        for n in theirs:
            if n not in mine: os.remove(os.path.join(golden_dir, n))
        for n in mine:
            with open(os.path.join(out_dir, n)) as f, open(os.path.join(golden_dir, n), "w") as g: g.write(f.read())
        return []
    for n in sorted(set(mine) | set(theirs)):
        a = open(os.path.join(golden_dir, n)).read().split("\n") if n in theirs else None
        b = open(os.path.join(out_dir, n)).read().split("\n") if n in mine else None
        if a == b: continue
        if a is None: bad.append("%s: a screen the golden files do not have" % n); continue
        if b is None: bad.append("%s: a golden screen that was not shown" % n); continue
        d = list(difflib.unified_diff(a, b, "golden/" + n, "this run/" + n, lineterm="", n=1))
        with open(os.path.join(out_dir, n[:-4] + ".diff"), "w") as f: f.write("\n".join(d) + "\n")
        first = next((l for l in d[2:] if l[:1] in "+-"), "")
        bad.append("%s: %s" % (n, first[:120]))
    return bad


# ---- the first-run report ----
LEAVE = [   # (what the person has to do away from the guide, the text that says so)
    ("open a second terminal", re.compile(r"open a second terminal", re.I)),
    ("type a slash command in a Claude Code session", re.compile(r"^\s*/[a-z]+:[a-z]+ .*$", re.M)),
    ("edit a file", re.compile(r"\b(in|edit) hub\.conf\b|\bedit (the|your) [a-z./~]+", re.I)),
    ("go to another app", re.compile(r"\bIn Telegram, (open|send)\b|github\.com/login/device", re.I)),
    ("run another command afterwards", re.compile(r"^(next|start it later|Later \(.*\)): .*$", re.M)),
]
ERRORS = re.compile(r"Traceback \(most recent call last\)|^\S*: line \d+: |command not found|No such file or directory|\bfatal: |\berror: |^Error\b|\bfailed\b", re.M | re.I)
EXPLAINS = r"\b(is|are|means|lets|keeps)\b"


def questions_of(text):
    """the questions a screen asks: [(the question, its default or "", the kind)]"""
    out = []
    for l in text.split("\n"):
        s = l.strip()
        m = re.search(r"^(.*\?) \[(y/N|Y/n)\]", s)
        if m: out.append((m.group(1), "no" if m.group(2) == "y/N" else "yes", "yes/no")); continue
        m = re.search(r"^(.*) \((1-\d+)\):", s)
        if m: out.append((m.group(1), "", "pick one of " + m.group(2).split("-")[1])); continue
        m = re.search(r"^(.*) \[([^\]]+)\]:", s)
        if m: out.append((m.group(1), m.group(2), "choice")); continue
        m = re.search(r"^(Pick any .*|Name for your hub .*|Who this hub works for .*|Owner \(.*|.*\(hidden[^)]*\)):", s)
        if m: out.append((m.group(1), "", "hidden text" if "hidden" in s else "text")); continue
        if s.startswith("Press Enter"): out.append((s.rstrip(": "), "", "Enter"))
    return out


def report(target, version, steps, screens, jargon, results):
    """report.md. steps: [(state, name, detail, seconds)]; screens: [(name, clean text, seconds or None)]"""
    L = ["# First-run report: the golden path (%s, %s)" % (target, version), "",
         "Generated by `drills/golden/run.py` from a real run with stand-ins for every account. This is what we polish",
         "against: each place the person leaves the guide, each word used before it is explained and each long line is a",
         "candidate fix. Transcripts: `transcripts/<screen>.txt` (and `.ansi`).", ""]
    ok = sum(1 for s in steps if s[0] == "ok"); pend = [s for s in steps if s[0] == "pending"]; bad = [s for s in steps if s[0] in ("FAIL", "not run")]
    allq = [(n, q) for n, t, _ in screens for q in questions_of(t)]
    total = sum(s or 0 for _, _, s in screens)
    L += ["## Summary", "", "| | |", "|---|---|", "| Steps checked | %d ok, %d pending, %d failed or not run |" % (ok, len(pend), len(bad)),
          "| Screens the person sees | %d |" % len(screens), "| Questions asked | %d |" % len(allq),
          "| Time on the terminal | %d s (with stand-ins that answer at once; a person's time is longer) |" % total, ""]
    L += ["## Steps", "", "| State | Step | Seconds | Detail |", "|---|---|---|---|"]
    for st, name, detail, sec in steps:
        L.append("| %s | %s | %s | %s |" % (st, name.replace("|", "/"), "" if sec is None else "%.1f" % sec, detail.replace("|", "/")))
    L += ["", "## Screens", "", "| Screen | Seconds | Lines | Questions |", "|---|---|---|---|"]
    for n, t, sec in screens:
        L.append("| %s | %s | %d | %d |" % (n, "" if sec is None else "%.1f" % sec, len(t.strip("\n").split("\n")), len(questions_of(t))))
    L += ["", "## Every question, with its default", "", "| Screen | Question | Default | Kind |", "|---|---|---|---|"]
    for n, (q, d, k) in allq: L.append("| %s | %s | %s | %s |" % (n, q.replace("|", "/")[:110], d or "none", k))
    L += ["", "## Where the person must leave the guide", ""]
    hits = []
    for n, t, _ in screens:
        for what, rx in LEAVE:
            for m in rx.finditer(t):
                line = t[t.rfind("\n", 0, m.start()) + 1:t.find("\n", m.end()) if t.find("\n", m.end()) >= 0 else len(t)].strip()
                hits.append((n, what, line))
    if hits:
        L += ["| Screen | What | The line |", "|---|---|---|"]
        for n, what, line in hits: L.append("| %s | %s | `%s` |" % (n, what, line.replace("|", "/")[:110]))
    else: L.append("None.")
    L += ["", "## Words used before they are explained", "",
          "A word from `drills/golden/jargon.txt` whose first line on the screen does not say what it is (a rough test: the",
          "line, or the one after it, has the word followed by is, are, means, lets or keeps). A person judges each.", ""]
    stream = [(n, l) for n, t, _ in screens if "phone" not in n for l in t.split("\n")]
    rows = []
    for w in jargon:
        rx = re.compile(r"(?<![A-Za-z./_-])%s(?![A-Za-z_-])" % re.escape(w), re.I if w.islower() else 0)
        for i, (n, l) in enumerate(stream):
            if not rx.search(l): continue
            near = l + " " + (stream[i + 1][1] if i + 1 < len(stream) else "")
            if not re.search(re.escape(w) + r"[^.]{0,60}" + EXPLAINS, near, re.I): rows.append((w, n, l.strip()))
            break
    if rows:
        L += ["| Word | First seen in | The line |", "|---|---|---|"]
        for w, n, l in rows: L.append("| %s | %s | `%s` |" % (w, n, l.replace("|", "/")[:110]))
    else: L.append("None.")
    L += ["", "## Lines longer than 80 columns", ""]
    longs = [(n, l) for n, t, _ in screens if "phone" not in n for l in t.split("\n") if len(l) > 80]
    if longs:
        L += ["| Screen | Columns | The line |", "|---|---|---|"]
        for n, l in longs: L.append("| %s | %d | `%s` |" % (n, len(l), l.replace("|", "/")[:110] + ("..." if len(l) > 110 else "")))
    else: L.append("None.")
    L += ["", "## Errors and stack traces on the screen", ""]
    errs = [(n, l.strip()) for n, t, _ in screens for l in t.split("\n") if ERRORS.search(l)]
    if errs:
        L += ["| Screen | The line |", "|---|---|"]
        for n, l in errs: L.append("| %s | `%s` |" % (n, l.replace("|", "/")[:120]))
    else: L.append("None.")
    L += ["", "## Pending: gaps in the path, by story", ""]
    for st, name, detail, _ in steps:
        if st == "pending": L.append("- **%s**: %s" % (name, detail))
    if not pend: L.append("None.")
    if results: L += ["", "## Golden transcripts", ""] + ["- " + r for r in results]
    return "\n".join(L) + "\n"
