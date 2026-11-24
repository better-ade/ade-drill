#!/usr/bin/env python3
"""The raw-Ubuntu drill (story D4): the ade-cli README's user flow on a fresh ubuntu:24.04, as a person types it.

  the README's install line -> ade help, ade version -> ade setup until Claude Code is installed and signed in ->
  the guide connects the Telegram bot -> from Telegram: "start 5 focus agents" -> five agents, each in its own
  checkout, each reporting to the chat

Runs inside the drill's container as the person (`you`, password-less sudo), started by drills/raw-ubuntu.sh, with the
drill's own Python (/opt/drill/python, never on the person's PATH). It reuses the golden drill (D3): its terminal, its
stand-ins (Claude Code and its model, GitHub, the Bot API and the phone, systemd) and its checks. What the person does
not have is never installed by the drill: a missing tool is a finding. When a step fails, the person follows what the
screen says once (or installs the missing command the way a person would) and tries again; everything else stops.

  RAW_TARGET       server | desktop (the image drills/raw-ubuntu.sh built)
  GOLDEN_ADE_REF   empty: the release, by the README's one-line install; a branch (main): the README's git clone line
  GOLDEN_OUT       where report.md and transcripts/ go (default /out)
  RAW_DATA         the drill's prepared data, read-only: ade-brain/ (the hub template) and repos/svc-1..5
  ADE_DRILL_TELEGRAM_TOKEN, ADE_DRILL_TELEGRAM_CHAT   the real-bot mode: what the bot sends also goes to that chat
                   (only the Bot API stand-in ever holds the token; it is in no file, screen or report)

The last line is "ok" only when every step passed; the frictions are in the report either way.
"""
import importlib.util, json, os, re, shlex, shutil, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(os.path.dirname(HERE), "golden")
os.environ["GOLDEN_TARGET"] = "linux"; os.environ.setdefault("GOLDEN_OUT", "/out")
REAL_TOKEN = os.environ.pop("ADE_DRILL_TELEGRAM_TOKEN", "").strip()   # out of the environment before anything starts
REAL_CHAT = os.environ.pop("ADE_DRILL_TELEGRAM_CHAT", "").strip()
_spec = importlib.util.spec_from_file_location("golden_run", os.path.join(GOLDEN, "run.py"))
g = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(g)
sys.path.insert(0, HERE)
import flow  # noqa: E402

screens, Failed, need, line = g.screens, g.Failed, g.need, g.line
TARGET = os.environ.get("RAW_TARGET", "server")
ADE_REF = os.environ.get("GOLDEN_ADE_REF", "")
DATA = os.environ.get("RAW_DATA", "/drill-data")
OUT = g.OUT
NAMES = ["svc-%d" % i for i in range(1, 6)]
ASK = "start 5 focus agents, one per repo: " + " ".join(NAMES)
SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROMPT_END = re.compile(r"(\?|:|\]|\)|\.\.\.)$")


class Raw(g.Drill):
    def __init__(self):
        need(TARGET in ("server", "desktop"), "RAW_TARGET is server or desktop")
        need(os.path.isfile("/etc/ade-raw-drill"), "this runs inside the drill's container: bash drills/raw-ubuntu.sh starts it")
        self.work = os.path.realpath(tempfile.mkdtemp(prefix="ade-raw."))
        w = self.work; self.home = os.path.expanduser("~")
        self.bin = os.path.join(w, "bin"); self.tools = self.bin
        self.state = os.path.join(w, "claude"); self.tg = os.path.join(w, "telegram")
        for d in (self.bin, self.state, self.tg, os.path.join(w, "gh-config")): os.makedirs(d, exist_ok=True)
        self.shown = []; self.terms = []; self.api = None; self.botapi = None; self.second = None
        self.tmux = tempfile.mkdtemp(prefix="adr.", dir="/tmp")
        # the stand-ins the person's machine needs in front: systemd's user manager (a container has none) and the
        # guards; gh and curl are put in front of the real ones by the image's apt hook once apt installs them
        for n in ("systemctl", "loginctl"): os.symlink(os.path.join(GOLDEN, "fakes", n), os.path.join(self.bin, n))
        for n in ("security", "launchctl", "pass", "gpg", "pbcopy", "pbpaste", "xclip", "wl-copy"):
            os.symlink(os.path.join(GOLDEN, "fakes", "guard"), os.path.join(self.bin, n))
        self.env = {
            "HOME": self.home, "PATH": self.bin + ":" + SYSTEM_PATH, "TERM": "xterm-256color", "LANG": "C.UTF-8",
            "USER": "you", "LOGNAME": "you", "SHELL": "/bin/bash",
            "GH_CONFIG_DIR": os.path.join(w, "gh-config"), "GIT_TERMINAL_PROMPT": "0",
            "DRILL_FAKES": self.bin, "DRILL_CLAUDE_SRC": os.path.join(HERE, "fakes", "claude"),
            "DRILL_CLAUDE_INSTALLER": os.path.join(GOLDEN, "fakes", "install-claude.sh"), "DRILL_REAL_CURL": "/usr/bin/curl.real",
            "DRILL_GH": os.path.join(w, "gh"), "DRILL_SYSTEMD": os.path.join(w, "systemd"), "DRILL_GUARD": os.path.join(w, "guard.log"),
            "DRILL_TEMPLATE": os.path.join(w, "src", "ade-brain"),
            "ADE_NO_UPDATE_CHECK": "1", "ADE_NO_CLAUDE_UPDATE": "1", "ADE_TMUX_SOCKET": "ade-raw-%d" % os.getpid(), "TMUX_TMPDIR": self.tmux,
            "AGENT_CHAT_TEST_TIMEOUT": "30", "AGENT_CHAT_FORWARD_EVERY": "2", "ADE_TG_WAIT": "30",
        }
        if TARGET == "desktop": self.env["DISPLAY"] = os.environ.get("DISPLAY", ":99")
        self.rules = flow.parse_rules(open(os.path.join(HERE, "answers.txt")).read())
        self.prompts = []; self.missing = []; self.fixes = []; self.done_fixes = set(); self.windows = []
        self.spawn = None; self.peaks = (0, 0); self.step = "prepare"

    # ---- the person ----
    def term(self, argv, cwd, name):
        """every terminal is a new window: a login shell (the golden act's own `bash -c ...` too)"""
        if argv[:3] != ["bash", "-l", "-i"]: argv = ["bash", "-l", "-i", "-c", shlex.join(argv)]
        return super().term(argv, cwd, name)

    def run(self, argv, cwd=None, check=True, stdin=None, timeout=300):
        """the drill's own checks (never the person's): with ade and Claude Code where the installers put them"""
        keep = self.env["PATH"]
        self.env["PATH"] = ":".join((self.bin, os.path.join(self.home, ".local", "bin"), os.path.join(self.home, ".bun", "bin"), SYSTEM_PATH))
        try: return super().run(argv, cwd, check, stdin, timeout)
        finally: self.env["PATH"] = keep

    def person(self, cmd, name):
        """one command typed at a new terminal window (a login shell: ~/.profile and command-not-found apply)"""
        return self.term(["bash", "-l", "-i", "-c", cmd], self.home, name)

    def shell(self, cmd):
        """(exit, output): a command the drill runs as the person would see it in a new terminal, with no prompt"""
        p = subprocess.run(["bash", "-l", "-c", cmd], cwd=self.home, env=self.env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip()

    def converse(self, t, screen, timeout=1500):
        """answers each prompt from answers.txt until the program ends; its exit code. A prompt the rules do not know,
        still waiting after 60 s, fails the step (the screen shows it)."""
        start = 0; last = time.time(); size = 0; asked = {}; end = time.time() + timeout
        while True:
            alive = t.read(0.3)
            if len(t.raw) != size: size = len(t.raw); last = time.time()
            if not alive:
                try:
                    p, st = os.waitpid(t.pid, 0); return os.waitstatus_to_exitcode(st)
                except ChildProcessError: return 0
            need(time.time() < end, "%s did not end within %d s; the screen ends with: %s" % (screen, timeout, t.tail()))
            idle = time.time() - last
            if idle < 0.8 or size <= start: continue
            text = screens.plain(t.raw[start:]); q = text.split("\n")[-1].strip()
            if not q or not PROMPT_END.search(q): continue
            acts = flow.answer_for(q, text, self.rules)
            if acts is None:
                need(idle < 60, "a question the drill has no answer for, at %s: [%s]" % (screen, q)); continue
            asked[q] = asked.get(q, 0) + 1; need(asked[q] <= 3, "asked again and again at %s: [%s]" % (screen, q))
            shown = " then ".join({"@token": "<the bot token, hidden>", "@enter": "Enter", "@hub": g.HUB}.get(a, a) for a in acts)
            self.prompts.append({"screen": screen, "question": q, "answer": shown})
            for a in acts:
                if a in ("@second-terminal", "@message-the-bot", "@lock"): self.act(a)
                else: t.send({"@token": g.TOKEN, "@hub": g.HUB, "@enter": "", "@stop": "stop"}.get(a, a))
            start = len(t.raw)

    def act(self, do):
        """what the guide sends the person away to do: a second terminal (each typed line is a terminal-only prompt)"""
        typed = {"@second-terminal": "cd ~/hubs/%s && bin/chat start" % g.HUB, "@message-the-bot": "/telegram:access pair <code>",
                 "@lock": "/telegram:access policy allowlist"}[do]
        self.prompts.append({"screen": "second terminal", "question": "the guide: type in a second terminal", "answer": typed})
        if do == "@message-the-bot": self.prompts.append({"screen": "phone", "question": "the guide: send your bot any message", "answer": "hello (on Telegram)"})
        super().act(do)

    def looked(self, name, t):
        """the missing tools a screen shows, for the report"""
        for tool, how, l in flow.missing_tools(name, screens.plain(t.raw)): self.missing.append([tool, how, l, self.step, None])

    def apply(self, fix, depth=0):
        """the person leaves the guide and runs what the screen says (or what a person would guess), once"""
        why, cmds, kind = fix
        for cmd in cmds:
            for attempt in (1, 2):
                t = self.person(cmd, "%s-fix-%d" % (self.step, len(self.fixes) + 1)); rc = self.converse(t, "fix"); self.looked("fix", t)
                self.fixes.append((self.step, why, cmd if rc == 0 else "%s (exit %d)" % (cmd, rc), kind))
                if rc == 0: self.done_fixes.add(cmd); break
                sub = flow.fix_for(screens.plain(t.raw), self.done_fixes)
                need(attempt == 1 and depth < 2 and sub, "the person's fix [%s] ended with exit %d: %s" % (cmd, rc, t.tail()))
                self.apply(sub, depth + 1)

    def until_it_works(self, cmd, name, works, tries=6):
        """runs the command, fixing from the screen between tries, until works() says yes"""
        for i in range(tries):
            t = self.person(cmd, name if i == 0 else "%s-again-%d" % (name, i)); rc = self.converse(t, name); self.looked(name, t)
            if works(rc): return t
            fix = flow.fix_for(screens.plain(t.raw), self.done_fixes)
            need(fix, "%s ended with exit %d and the screen says nothing a person could do: %s" % (cmd, rc, t.tail()))
            self.apply(fix)
            if ADE_REF and name == "install": shutil.rmtree(os.path.join(self.home, "ade-cli"), ignore_errors=True)   # to clone again
        raise Failed("%s still fails after %d tries" % (cmd, tries))

    # ---- the flow ----
    def prepare(self):
        env = dict(os.environ)
        if REAL_TOKEN and REAL_CHAT: env.update(DRILL_TG_RELAY_TOKEN=REAL_TOKEN, DRILL_TG_RELAY_CHAT=REAL_CHAT)
        self.botapi = subprocess.Popen([sys.executable, "-I", os.path.join(GOLDEN, "fakes", "botapi.py"), self.tg, g.TOKEN, g.OWNER], env=env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=open(os.path.join(self.tg, "errors.log"), "w"))
        del env
        port = self.wait_for("the stand-in Bot API", lambda: os.path.exists(os.path.join(self.tg, "port")) and open(os.path.join(self.tg, "port")).read().strip(), 15)
        self.api = "http://127.0.0.1:" + port; self.env["AGENT_TELEGRAM_API"] = self.api
        with open(os.path.join(self.home, ".fake-claude.json"), "w") as f:
            json.dump({"state": self.state, "model": os.path.join(HERE, "model"), "api": self.api}, f)
        os.makedirs(os.path.join(self.work, "src"))
        shutil.copytree(os.path.join(DATA, "ade-brain"), self.env["DRILL_TEMPLATE"], symlinks=True)
        for n in NAMES: shutil.copytree(os.path.join(DATA, "repos", n), os.path.join(self.home, "Project", n), symlinks=True)
        self.readme = flow.readme_steps(open(os.path.join(DATA, "README.md")).read())
        self.sampling = True; self.samples = []
        threading.Thread(target=self.sample, daemon=True).start()

    def sample(self):
        """the person's processes every 0.5 s: their memory (VmRSS) and how many (from /proc: the image has no ps)"""
        me = str(os.getuid()); skip = {os.getpid(), self.botapi.pid}
        while self.sampling:
            rss = n = 0
            for pid in os.listdir("/proc"):
                if not pid.isdigit() or int(pid) in skip: continue
                try: st = open("/proc/%s/status" % pid).read()
                except OSError: continue
                if re.search(r"^Uid:\s+%s\b" % me, st, re.M):
                    n += 1; m = re.search(r"^VmRSS:\s+(\d+)", st, re.M); rss += int(m.group(1)) if m else 0
            self.samples.append((time.time(), rss, n)); time.sleep(0.5)

    def install(self):
        cmd = self.readme["clone"] if ADE_REF else self.readme["install"]
        if ADE_REF and ADE_REF != "main": cmd = cmd.replace("git clone ", "git clone -b %s " % ADE_REF, 1)
        self.until_it_works(cmd, "install", lambda rc: self.shell("ade version")[0] == 0)
        rc, v = self.shell("ade version"); self.ade_version = v.split("\n")[-1]
        need(re.fullmatch(r"ade [0-9]+\.[0-9]+\.[0-9]+", self.ade_version), "ade version says [%s]" % v)
        return "%s, by the README's line: %s" % (self.ade_version, cmd)

    def quick(self):
        for cmd in self.readme["quick"]:
            t = self.person(cmd, "quick-" + cmd.replace(" ", "-")); rc = self.converse(t, cmd, 60); self.looked(cmd, t)
            need(rc == 0, "%s ended with exit %d: %s" % (cmd, rc, t.tail()))
        return "the README's Quick start: " + ", ".join(self.readme["quick"])

    def guide(self):
        self.until_it_works(self.readme["setup"], "guide", lambda rc: rc == 0, 4)
        if self.second: self.second.wait(30)
        self.hub = os.path.join(self.home, "hubs", g.HUB)
        need(os.path.isfile(os.path.join(self.hub, "hub.conf")), "there is no hub at ~/hubs/" + g.HUB)
        return "%s, %d runs, %d prompts answered" % (self.readme["setup"], sum(1 for n, _ in self.shown if n.startswith("guide")), len(self.prompts))

    def spawn(self):
        """outcome 3: one Telegram message, five focus agents, each in its own checkout, each reporting to the chat"""
        before = len(self.sent()); t_msg = time.time(); self.phone(ASK)
        self.wait_for("the message to reach the main agent", lambda: ASK in self.claude_log(), 30)
        ups = {}
        def all_up():
            for n in NAMES:
                try: ups[n] = json.load(open(os.path.join(self.state, "up-%s.json" % n)))
                except (OSError, ValueError): pass
            return all(n in ups and "saw" in ups[n] for n in NAMES)
        def replies(): return [m.get("text", "") for m in self.sent()[before:] if m.get("method") == "sendMessage"]
        try: self.wait_for("five focus agents up", all_up, 240)
        except Failed: pass
        try: self.wait_for("a report from each agent on the phone", lambda: all(any("[%s]" % n in r for r in replies()) for n in NAMES), 60)
        except Failed: pass
        self.sampling = False; self.peaks = flow.peak(self.samples)
        for l in self.claude_log().split("\n"):
            for tool, how, ln in flow.missing_tools("spawn", l): self.missing.append([tool, how, ln, "spawn", None])
        self.spawn = flow.spawn_summary(NAMES, ups, [(0, r) for r in replies()], self.home, t_msg)
        self.spawn["phone"] = replies()
        need(self.spawn["ok"], "; ".join(self.spawn["problems"]) + "; the phone shows: " + " | ".join(r[:120] for r in replies()[-4:]))
        return "all five up %.1f s after the message, each in its own checkout, each reported; peak %.0f MB, %d processes" % (
            self.spawn["all_up"], self.peaks[0] / 1024.0, self.peaks[1])

    def no_leak(self):
        got = super().no_leak()
        if REAL_TOKEN:
            for t in self.terms: need(REAL_TOKEN.encode() not in t.raw, "the real bot token was shown on a terminal")
            for root in (self.work, self.home):
                for d, _, files in os.walk(root):
                    for n in files:
                        try: need(REAL_TOKEN.encode() not in open(os.path.join(d, n), "rb").read(), "the real bot token is in a file")
                        except OSError: pass
            got += "; the real bot token is in no file and on no screen"
        return got

    def outcomes(self):
        """what became of each missing tool: fixed by the person, installed by the guide, or still missing"""
        path = ":".join((os.path.join(self.home, ".local", "bin"), os.path.join(self.home, ".bun", "bin"), SYSTEM_PATH))
        for m in self.missing:
            fix = next((f[2] for f in self.fixes if f[0] == m[3] and re.search(r"\b%s\b" % re.escape(flow.PKG.get(m[0], m[0])), f[2])), None)
            m[4] = ("fixed: " + fix) if fix else "installed by the guide" if shutil.which(m[0], path=path) and m[1] == "the guide offered to install it" \
                else "there now" if shutil.which(m[0], path=path) else "still missing"
        return [tuple(m) for m in self.missing]

    def sudo(self):
        p = subprocess.run(["sudo", "-n", "cat", "/var/log/sudo-drill.log"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return flow.sudo_per_step(flow.parse_sudo(p.stdout.decode("utf-8", "replace")), self.windows)

    def record_all(self):
        """every screen, in the order shown, to <out>/transcripts/ (.ansi as it came, .txt cleaned); the guide by its steps"""
        subs = [(self.work, "<drill>"), (self.env["ADE_TMUX_SOCKET"], "ade-raw"), (self.tmux, "<tmux>")]
        if REAL_TOKEN: subs.append((REAL_TOKEN, "<real token>"))
        tr = os.path.join(OUT, "transcripts"); shutil.rmtree(tr, ignore_errors=True); os.makedirs(tr); out = []
        got = []
        for name, t in self.shown:
            text = screens.plain(t.raw); sec = t.marks[-1][0] - t.marks[0][0]
            parts = screens.split_guide(text) if name.startswith("guide") else [(name, text)]
            for i, (n, body) in enumerate(parts): got.append((n if len(parts) > 1 else name, body, t.raw if i == 0 else b"", sec if i == 0 else None))
        try: rows = [json.loads(l) for l in open(os.path.join(self.tg, "phone.jsonl")) if l.strip()]
        except OSError: rows = []
        if rows:
            phone = "".join("%s: %s\n" % (r["who"], r["text"].replace("\n", "\n    ")) for r in rows); got.append(("phone", phone, phone.encode(), None))
        for i, (name, text, raw, sec) in enumerate(got):
            n = "%02d-%s" % (i + 1, name); text = screens.clean(text, subs)
            if raw:
                for a, b in subs: raw = raw.replace(a.encode(), b.encode())
                with open(os.path.join(tr, n + ".ansi"), "wb") as f: f.write(raw)
            with open(os.path.join(tr, n + ".txt"), "w") as f: f.write(text)
            out.append((n, text, sec))
        return out

    def mode_note(self):
        if not (REAL_TOKEN and REAL_CHAT):
            return "Telegram: the stand-in both ways (no ADE_DRILL_TELEGRAM_TOKEN and ADE_DRILL_TELEGRAM_CHAT: a pull request, or the secrets are not set)."
        rel = [m.get("relayed", "") for m in self.sent() if m.get("chat_id") == g.OWNER]
        ok = sum(1 for r in rel if r == "ok"); bad = sorted({r for r in rel if r != "ok"})
        return ("Telegram: half real. What the bot sent (%d messages) also went through the real Bot API to the real chat: %d "
                "arrived%s. What the person sent came through the stand-in update feed; the real token was never polled "
                "(no getUpdates, no setWebhook)." % (len(rel), ok, "; not relayed: " + ", ".join(bad) if bad else ""))

    def cleanup(self):
        self.sampling = False
        if getattr(self, "samples", None): self.peaks = flow.peak(self.samples)   # over the whole run
        for t in self.terms: t.close()
        hub = os.path.join(self.home, "hubs", g.HUB)
        for argv, cwd in ((["bin/chat", "stop"], hub), (["tmux", "-L", self.env["ADE_TMUX_SOCKET"], "kill-server"], self.home), (["tmux", "kill-server"], self.home)):
            try: subprocess.run(argv, cwd=cwd if os.path.isdir(cwd) else self.home, env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            except (OSError, subprocess.SubprocessError): pass
        if self.botapi: self.botapi.terminate(); self.botapi.wait()


STEPS = [
    ("install: the README's install line", "install"),
    ("install: the README's Quick start (ade help, ade version)", "quick"),
    ("guide: ade setup, from nothing to the end", "guide"),
    ("outcome 1: Claude Code installed and signed in", "check_claude"),
    ("outcome 2: Telegram connected, locked to the person, auto mode", "check_telegram"),
    ("outcome 3: five focus agents from one Telegram message", "spawn"),
    ("safety: no guarded tool, no token shown", "no_leak"),
]


def main():
    d = None; failed = False; shown = []
    try:
        d = Raw(); d.prepare()
        for name, method in STEPS:
            if failed: line("not run", name); continue
            d.step = {"check_claude": "claude", "check_telegram": "telegram", "no_leak": "safety"}.get(method, method)
            t0 = time.time()
            try: detail = getattr(d, method)(); line("ok", name, detail or "", time.time() - t0)
            except Failed as e: failed = True; line("FAIL", name, str(e), time.time() - t0)
            except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as e:
                failed = True; line("FAIL", name, "%s: %s" % (e.__class__.__name__, e), time.time() - t0)
            d.windows.append((d.step, t0, time.time()))
    except (Failed, OSError, ValueError) as e:
        failed = True; line("FAIL", "the drill's own set-up", str(e))
    finally:
        if d and failed:
            try: d.debug()
            except (OSError, KeyError, AttributeError, subprocess.SubprocessError): pass
        if d: d.cleanup()
    ver = getattr(d, "ade_version", "ade not installed") if d else "ade not installed"
    if ADE_REF: ver += " from " + ADE_REF
    try:
        shown = d.record_all() if d else []
        prompts = flow.mark_phases(d.prompts if d else [])
        rep = flow.report(TARGET, ver, g.RESULTS, shown, prompts, d.outcomes() if d else [], d.fixes if d else [], d.sudo() if d else [],
                          d.spawn if d else None, d.peaks if d else (0, 0), d.mode_note() if d else "")
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "report.md"), "w") as f: f.write(rep)
        print("report: %s" % os.path.join(OUT, "report.md"))
    except (OSError, KeyError, ValueError, TypeError) as e:
        failed = True; print("FAIL    the report: %s: %s" % (e.__class__.__name__, e))
    if REAL_TOKEN:   # the real token is in nothing the drill leaves behind
        for root, _, files in os.walk(OUT):
            for n in files:
                p = os.path.join(root, n)
                if REAL_TOKEN.encode() in open(p, "rb").read(): os.remove(p); failed = True; print("FAIL    the real bot token was in an output file; removed")
    if d and not os.environ.get("GOLDEN_KEEP"): shutil.rmtree(d.work, ignore_errors=True); shutil.rmtree(d.tmux, ignore_errors=True)
    ok = sum(1 for r in g.RESULTS if r[0] == "ok"); bad = sum(1 for r in g.RESULTS if r[0] in ("FAIL", "not run"))
    print("raw-ubuntu: %s, %s: %d ok, %d failed or not run" % (TARGET, ver, ok, bad))
    if failed: return 1
    print("ok"); return 0


if __name__ == "__main__":
    sys.exit(main())
