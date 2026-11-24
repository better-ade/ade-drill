"""The raw-Ubuntu drill's own logic (story D4): the README's steps, what the screens say is missing, the person's fixes,
the answers, the phases of the prompts, sudo per step, the team of four roles, and the report. No I/O here: run.py does that.
"""
import calendar, re, time

# ---- the README's steps, read at run time ----
def sections(md):
    """{heading text: body} for every "## " heading"""
    out = {}; cur = None
    for l in md.split("\n"):
        m = re.match(r"^## (.+?)\s*$", l)
        if m: cur = m.group(1); out[cur] = []; continue
        if cur is not None: out[cur].append(l)
    return {k: "\n".join(v) for k, v in out.items()}


def code_lines(body):
    """the lines of the fenced code blocks, each without its trailing comment"""
    out = []; on = False
    for l in body.split("\n"):
        if l.strip().startswith("```"): on = not on; continue
        if on:
            l = re.sub(r"\s{2,}#.*$", "", l).strip()
            if l and not l.startswith("#"): out.append(l)
    return out


def readme_steps(md):
    """the commands the person copies from the README: {"install", "clone", "quick", "setup", "project_add", "hub_new"};
    ValueError when one is not there (a README change that breaks the flow fails the drill)"""
    s = sections(md)
    def section(name):
        k = next((k for k in s if k == name or k.startswith(name + " ")), None)
        if k is None: raise ValueError("the README has no section %s" % name)
        return s[k]
    inst = [l for l in code_lines(section("Install")) if re.match(r"^curl .*\|\s*bash$", l)]
    if not inst: raise ValueError("the README's Install section has no one-line `curl ... | bash` install")
    clone = [l for l in code_lines(section("Install")) if re.match(r"^git clone \S+/ade-cli\b.*install\.sh$", l)]
    if not clone: raise ValueError("the README's Install section has no `git clone ... ./install.sh` line")
    qs = section("Quick start"); lines = code_lines(qs)
    quick = [c for c in ("ade help", "ade version") if c in lines]
    if len(quick) != 2: raise ValueError("the README's Quick start has no `ade help` and `ade version` lines")
    if "`ade setup`" not in qs: raise ValueError("the README's Quick start does not name the guide, `ade setup`")
    if not re.search(r"`ade hub new\b", qs): raise ValueError("the README's Quick start does not name `ade hub new`")
    if not any(l.startswith("ade project add ") for l in lines): raise ValueError("the README's Quick start has no `ade project add` line")
    return {"install": inst[0], "quick": quick, "setup": "ade setup", "project_add": "ade project add", "hub_new": "ade hub new", "clone": clone[0]}


# ---- what the screens say is missing ----
MISSING = [
    (re.compile(r"(?:^|: )([\w.+-]+): command not found$"), "command not found"),
    (re.compile(r"^Command '([\w.+-]+)' not found"), "command not found (command-not-found)"),
    (re.compile(r"^install: needs ([\w.+-]+)$"), "the installer needs it"),
    (re.compile(r"^Install (.+?) now\? This runs: (?:sudo )?apt-get install"), "the guide offered to install it"),
    (re.compile(r"Unable to locate package ([\w.+-]+)"), "apt cannot find the package"),
]


def missing_tools(screen, text):
    """[(tool, how it was found, the line)], in screen order"""
    out = []
    for l in text.split("\n"):
        s = l.strip()
        for rx, how in MISSING:
            m = rx.search(s)
            if m:
                for t in m.group(1).split(): out.append((t, how, s))
                break
    return out


# ---- the person's own fix, from what the screen says ----
PKG = {"pgrep": "procps", "ps": "procps", "pkill": "procps", "python3": "python3", "xwd": "x11-utils", "unzip": "unzip"}


def fix_for(text, done):
    """(why, [commands], "advised" | "unadvised") the person runs after a failed step, from the screen; None when the
    screen gives nothing to do (or the fix was done already: a fix is tried once)"""
    lines = [l.strip() for l in text.split("\n")]
    cands = []
    for l in lines:
        if "This runs:" in l: continue
        if "run apt-get update first" in l: cands.append(("the screen says: " + l, ["sudo apt-get update"], "advised"))
        if "Unable to locate package" in l: cands.append(("no advice on the screen: " + l, ["sudo apt-get update"], "unadvised"))
        if "git config --global user.name" in l:
            cands.append(("the screen says: " + l, ['git config --global user.name "Drill Owner"', "git config --global user.email drill@example.invalid"], "advised"))
        m = re.match(r"^(?:.*: )?(?:sudo )?apt(?:-get)?\s+install\s+(?:-y\s+)?([\w.+ -]+?)$", l)
        if m and (l.startswith(("sudo ", "run ", "apt ", "apt-get ")) or ": sudo apt" in l):
            cands.append(("the screen says: " + l, ["sudo apt-get install -y " + " ".join(m.group(1).split())], "advised"))
    for l in lines:
        m = re.search(r"(?:^|: )([\w.+-]+): command not found$", l)
        if m:
            t = m.group(1); cands.append(("no advice on the screen: %s: command not found" % t, ["sudo apt-get install -y " + PKG.get(t, t)], "unadvised"))
    # apt-get update comes first (an install cannot work before it), then an advised fix before a guess
    cands.sort(key=lambda c: (c[1] != ["sudo apt-get update"], c[2] != "advised"))
    for c in cands:
        if not any(cmd in done for cmd in c[1]): return c
    return None


# ---- answers: the person at the terminal ----
def parse_rules(text):
    """answers file: <regex on the prompt line> TAB [~<regex on the screen since the last answer> TAB] <action>...;
    an action is text, @enter, @hub, @token, @stop, @pick:<word> or another @word the drill acts on"""
    rules = []
    for row in text.split("\n"):
        if not row.strip() or row.startswith("#"): continue
        f = row.split("\t")
        if len(f) >= 3 and f[1].startswith("~"): rules.append((re.compile(f[0]), re.compile(f[1][1:], re.I), f[2:]))
        else: rules.append((re.compile(f[0]), None, f[1:]))
    return rules


def answer_for(line, context, rules):
    """the actions for a prompt (the first rule whose line and context match), @pick resolved; None: no answer known"""
    for rx, ctx, acts in rules:
        if not rx.search(line): continue
        if ctx is not None and not ctx.search(context): continue
        out = []
        for a in acts:
            if a.startswith("@pick:"):
                m = re.search(r"(\d+)[.)]\s+%s\b" % re.escape(a[6:]), context)
                if not m: return None
                out.append(m.group(1))
            else: out.append(a)
        return out
    return None


def mark_phases(prompts):
    """after_telegram: True for every prompt after the bot token's (the person should need no terminal from there)"""
    after = False
    for p in prompts:
        p["after_telegram"] = after
        if re.search(r"Bot token", p["question"]): after = True
    return prompts


# ---- sudo ----
MON = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
SUDO = re.compile(r"^(\w{3}) +(\d+) (\d\d):(\d\d):(\d\d)(?: (\d{4}))? : \S+ : .*?COMMAND=(.*)$")


def parse_sudo(log):
    """[(epoch, command)] from sudo's log file (log_year, loglinelen=0), oldest first; the drill's own reads left out"""
    out = []
    for l in log.split("\n"):
        m = SUDO.match(l.strip())
        if not m or "/var/log/sudo-drill.log" in m.group(7): continue
        y = int(m.group(6) or time.gmtime().tm_year)
        t = calendar.timegm((y, MON.get(m.group(1), 1), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), 0, 0, 0))
        out.append((t, m.group(7).strip()))
    return sorted(out)


def sudo_per_step(entries, windows):
    """[(step, command)]: each sudo use in the step whose [start, end] holds it (a second of slack: sudo logs whole seconds)"""
    rows = []
    for t, cmd in entries:
        step = next((n for n, a, b in windows if a - 1 <= t <= b + 1), "between steps")
        rows.append((step, cmd))
    return rows


# ---- the team: "build a website", four roles ----
ROLES = ["architect", "frontend", "backend", "reviewer"]


def team_summary(assigns, dones, reports, t_msg, done):
    """assigns: {role: {"t", "hub_role", "persona", "source"}} (the main agent's record of each assignment); dones: {role:
    {"t_up", "t_done", "cwd", "persona" (the role file's first line, "" when missing), "result", "text"}} (each session's
    own record); reports: [(t, text)] sent to the chat; done: (t, text) of the main agent's Done line, or None.
    {"ok", "all_up", "done_after", "parallel", "problems", "findings", "rows"}"""
    problems, findings, rows = [], [], []
    for r in ROLES:
        a, d = assigns.get(r) or {}, dones.get(r) or {}
        rep = next((txt for t, txt in reports if re.search(r'note: "?%s: ' % r, txt)), None)
        if not a: problems.append("%s was never assigned" % r)
        elif a.get("hub_role") and a["hub_role"] != r:
            findings.append("the hub has no %s role (bin/roles): assigned as %s with %s" % (r, a["hub_role"], a.get("persona")))
        if a and not d.get("persona") and "t_up" in d:
            problems.append("%s: no role file %s (%s)" % (r, a.get("persona"), a.get("source")))
        if "t_up" not in d: problems.append("%s never started" % r)
        elif "t_done" not in d: problems.append("%s never finished" % r)
        if rep is None: problems.append("%s: no report reached the chat" % r)
        rows.append((r, a.get("source", ""), a.get("hub_role", ""), d.get("persona", ""), d["t_up"] - t_msg if "t_up" in d else None,
                     d["t_done"] - t_msg if "t_done" in d else None, d.get("cwd", ""), d.get("result", ""), rep or ""))
    t = lambda r, k: (dones.get(r) or {}).get(k)
    for r in ("frontend", "backend"):
        if t(r, "t_up") is not None and (t("architect", "t_done") is None or t(r, "t_up") < t("architect", "t_done")):
            problems.append("%s started before the architect's handoff" % r)
    built = [t(r, "t_done") for r in ("frontend", "backend")]
    if t("reviewer", "t_up") is not None and (None in built or t("reviewer", "t_up") < max(built)):
        problems.append("the reviewer started before frontend and backend were done")
    green = t("reviewer", "result") == "green"
    if "t_done" in (dones.get("reviewer") or {}) and not green: problems.append("the reviewer's run is %s" % (t("reviewer", "result") or "unknown"))
    if done and (not green or done[0] < (t("reviewer", "t_done") or float("inf"))): problems.append("Done was sent without the reviewer's green run")
    if green and not done: problems.append("no Done reached the chat after the reviewer's green run")
    ups = [t(r, "t_up") for r in ROLES]
    parallel = None not in (t("frontend", "t_up"), t("backend", "t_up"), t("frontend", "t_done"), t("backend", "t_done")) and \
        t("frontend", "t_up") < t("backend", "t_done") and t("backend", "t_up") < t("frontend", "t_done")
    return {"ok": not problems, "all_up": max(ups) - t_msg if None not in ups else None,
            "done_after": done[0] - t_msg if done and not problems else None, "parallel": parallel,
            "problems": problems, "findings": findings, "rows": rows}


def peak(samples):
    """(peak RSS in kB, peak process count) of [(t, rss_kb, count)]"""
    return (max((s[1] for s in samples), default=0), max((s[2] for s in samples), default=0))


# ---- the report ----
def cell(s, n=120):
    s = str(s).replace("|", "/").replace("\n", " ")
    return s[:n] + ("..." if len(s) > n else "")


def report(target, version, steps, screens, prompts, missing, fixes, sudo, spawn, peaks, telegram_note):
    missing = [m for i, m in enumerate(missing) if tuple(m) not in {tuple(x) for x in missing[:i]}]   # one row per finding
    after = [p for p in prompts if p.get("after_telegram")]
    L = ["# User-flow report: raw Ubuntu %s (%s)" % (target, version), "",
         "Generated by `drills/raw/run.py` (story D4): the ade-cli README's steps, copied from it at run time, on a fresh",
         "`ubuntu:24.04` container, with a stand-in for every account. A friction is a finding: each row below is a",
         "candidate fix in ade-cli or ade-brain. Screens: `transcripts/<screen>.txt` (and `.ansi`).", "",
         "%s" % telegram_note, "", "## Summary", "", "| | |", "|---|---|",
         "| Steps | %d ok, %d failed or not run |" % (sum(1 for s in steps if s[0] == "ok"), sum(1 for s in steps if s[0] in ("FAIL", "not run"))),
         "| Missing tools found | %d (%d distinct) |" % (len(missing), len({m[0] for m in missing})),
         "| Times the person left the guide to fix something | %d |" % len(fixes),
         "| Prompts answered at a terminal | %d |" % len(prompts),
         "| Terminal-only prompts after Telegram | %d |" % len(after),
         "| sudo uses | %d |" % len(sudo),
         "| Build a website, four roles | %s |" % ("all four up in %.1f s, Done %.1f s after the message, on the reviewer's green run" % (spawn["all_up"], spawn["done_after"]) if spawn and spawn.get("ok") else "no: " + cell("; ".join((spawn or {}).get("problems") or ["not reached"]), 200)),
         "| Peak memory of the person's processes | %.0f MB |" % (peaks[0] / 1024.0),
         "| Peak process count | %d |" % peaks[1], ""]
    L += ["## Steps and their time", "", "| Step | Seconds | State | Detail |", "|---|---|---|---|"]
    for st, name, detail, sec in steps:
        L.append("| %s | %s | %s | %s |" % (cell(name), "" if sec is None else "%.1f" % sec, st, cell(detail, 300)))
    L += ["", "## Missing tools", "", "| Tool | How it was found | Step | The line | What happened |", "|---|---|---|---|---|"]
    for tool, how, line, step, what in missing: L.append("| %s | %s | %s | `%s` | %s |" % (tool, how, step, cell(line), cell(what)))
    if not missing: L.append("| none | | | | |")
    L += ["", "## Where the person left the guide to fix something", ""]
    if fixes:
        L += ["| Step | Why | What the person ran | Advice on the screen |", "|---|---|---|---|"]
        for step, why, cmd, kind in fixes: L.append("| %s | %s | `%s` | %s |" % (step, cell(why), cell(cmd), "yes" if kind == "advised" else "no: a person had to know"))
    else: L.append("None.")
    L += ["", "## Every prompt the person answered", "",
          "Owner rule (2026-11-23): a user controls everything through Telegram; every terminal-only prompt is removed or",
          "relayed. Before the bot exists a terminal is the only way; after the bot token every terminal prompt is a finding.", "",
          "| Screen | Prompt | Answer | Telegram-first finding |", "|---|---|---|---|"]
    for p in prompts:
        L.append("| %s | %s | %s | %s |" % (p["screen"], cell(p["question"]), cell(p["answer"], 40), "yes: terminal-only after Telegram" if p.get("after_telegram") else "no (before Telegram)"))
    L += ["", "## sudo", "", "| Step | Command |", "|---|---|"]
    for step, cmd in sudo: L.append("| %s | `%s` |" % (step, cell(cmd, 200)))
    if not sudo: L.append("| none | |")
    L += ["", "## Build a website: four roles from one Telegram message", "",
          "The main agent (the hub's Telegram session, the coordinator, counted apart from the four) assigns each role with",
          "the hub's own start (`ade work --role`), in order: architect; then frontend and backend; then the reviewer, whose",
          "green run of the architect's verification command is the only way to Done. Role files: `ade init` (ade-method) and",
          "`ade agent add` (ade-agent-registry).", ""]
    if spawn:
        L += ["| Role | From | Hub role | Role file | Up after (s) | Done after (s) | Folder | Result | Its report on the phone |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r, src, hub, persona, up, dn, cwd, res, rep in spawn["rows"]:
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (r, src, hub, cell(persona or "missing", 40), "" if up is None else "%.1f" % up,
                                                              "" if dn is None else "%.1f" % dn, cwd, res, cell(rep)))
        L += ["", "Frontend and backend ran at the same time: %s." % ("yes" if spawn.get("parallel") else "no"), ""]
        L += ["- finding: " + f for f in spawn.get("findings", [])] + ["- " + p for p in spawn["problems"]]
    else: L.append("Not reached.")
    L += ["", "## Screens", "", "| Screen | Seconds | Lines |", "|---|---|---|"]
    for n, t, sec in screens: L.append("| %s | %s | %d |" % (n, "" if sec is None else "%.1f" % sec, len(t.strip("\n").split("\n"))))
    return "\n".join(L) + "\n"
