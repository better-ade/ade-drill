#!/usr/bin/env python3
"""The golden-path drill (story D3): the owner's one path, end to end, with a stand-in for every account.

  fresh machine -> curl ... | bash -> the guide -> hub created and saved to GitHub -> Telegram locked, auto mode ->
  ade project add your repo -> "fix X" on Telegram -> a focus agent fixes it -> the reviewer runs the tests ->
  "Done" plus a picture on your phone

Real: ade (installed from its release, or from GOLDEN_ADE_REF), the hub template (ade-brain at GOLDEN_BRAIN_REF,
default main) and every script in both, git, tmux, the fixture project's own test.
Stand-ins (drills/golden/fakes/): Claude Code with its sign-in, its Telegram plugin and the model (scripted,
drills/golden/model/); the GitHub CLI and GitHub (a bare repository in the drill's folder); Telegram's Bot API and the
owner's phone; systemd's user manager; bun. Guards: security, launchctl, pass, gpg and the clipboard tools fail the
drill when anything calls them. The drill's home folder is its own; nothing of this machine's is read or written.

Each step prints one line: "ok", "pending <story>: ..." (a gap that is not built yet: never counted as green) or
"FAIL". The last line is "ok" only when no step failed.

What the person sees is recorded (screens.py): every screen on an 80x24 terminal goes to <out>/transcripts/ (.ansi as it
came, .txt cleaned), and <out>/report.md is the first-run report. With the released ade the .txt files must equal the
golden ones in transcripts/<target>/: a change of wording fails the drill until they are updated on purpose.

  GOLDEN_TARGET   macos | linux (this machine, in a home folder of the drill's own; the default) | computer (inside a
                  fresh ADE Computer container, in its own home: golden.sh starts the container)
  GOLDEN_ADE_REF  a branch or tag of ade-cli instead of the release (the golden files are then not compared)
  GOLDEN_OUT      where the transcripts and the report go (default drills/golden/out)
  GOLDEN_UPDATE=1 write this run's transcripts as the golden files
  GOLDEN_KEEP=1   keep the drill's folder and print it
"""
import fcntl, json, os, pty, pwd, re, select, shutil, signal, struct, subprocess, sys, tempfile, termios, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import screens  # noqa: E402
FAKES = os.path.join(HERE, "fakes")
ORG = os.environ.get("DRILL_ORG", "https://github.com/better-ade")
ADE_REF = os.environ.get("GOLDEN_ADE_REF", "")          # empty: the release, through install.sh as a person runs it
BRAIN_REF = os.environ.get("GOLDEN_BRAIN_REF", "main")
TOKEN = "123456789:" + "drill-stand-in-token-not-a-real-one_0"   # shaped as a bot token; belongs to no bot
OWNER = "424242"
HUB = "drill-hub"
MESSAGE = "fix the failing test in calc: add() subtracts"
TARGET = os.environ.get("GOLDEN_TARGET") or ("macos" if sys.platform == "darwin" else "linux")
OUT = os.path.abspath(os.environ.get("GOLDEN_OUT") or os.path.join(HERE, "out"))
RESULTS = []


def line(state, name, detail="", seconds=None):
    RESULTS.append((state, name, detail, seconds)); print("%-8s%s%s" % (state, name, ": " + detail if detail else "")); sys.stdout.flush()


class Failed(Exception):
    pass


def need(cond, why):
    if not cond: raise Failed(why)


class Term:
    """a program on its own pseudo-terminal, as a person's terminal window is"""

    def __init__(self, argv, cwd, env):
        self.buf = b""; self.raw = b""; self.marks = [(time.time(), 0)]   # (when, how much was on the screen by then)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))   # 80 columns, 24 lines
            os.chdir(cwd); os.execvpe(argv[0], argv, env)

    def when(self, offset):
        """the time by which that much of the screen had been shown"""
        return next((t for t, n in self.marks if n >= offset), self.marks[-1][0])

    def read(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r: return True
        try: got = os.read(self.fd, 65536)
        except OSError: return False
        if not got: return False
        self.buf += got; self.raw += got; self.marks.append((time.time(), len(self.raw))); return True

    def expect(self, text, timeout=90, also=()):
        """waits for the text; `also` are texts that may come first: the one that came is returned, and passed"""
        end = time.time() + timeout
        while True:
            hits = [(self.buf.find(w.encode()), w) for w in (text,) + tuple(also) if w.encode() in self.buf]
            if hits:
                at, w = min(hits); self.buf = self.buf[at + len(w.encode()):]; return w
            need(time.time() < end, "waited %d s for [%s]; the screen ends with: %s" % (timeout, text, self.tail()))
            need(self.read(0.5), "the program ended before [%s]; the screen ends with: %s" % (text, self.tail()))

    def send(self, text):
        os.write(self.fd, text.encode() + b"\n")

    def tail(self):
        return " | ".join(re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", self.buf).decode("utf-8", "replace").split("\n")[-4:]).replace("\r", "")

    def wait(self, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            if not self.read(0.3): break
            p, st = os.waitpid(self.pid, os.WNOHANG)
            if p: return os.waitstatus_to_exitcode(st)
        try: p, st = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError: return 0
        if p: return os.waitstatus_to_exitcode(st)
        raise Failed("the program did not end within %d s; the screen ends with: %s" % (timeout, self.tail()))

    def close(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try: os.kill(self.pid, sig)
            except OSError: return
            end = time.time() + 3
            while time.time() < end:
                try:
                    if os.waitpid(self.pid, os.WNOHANG)[0]: return
                except ChildProcessError: return
                time.sleep(0.1)


class Drill:
    def __init__(self):
        need(TARGET in ("macos", "linux", "computer"), "GOLDEN_TARGET is macos, linux or computer")
        inside = os.path.isfile("/etc/ade-computer") and os.environ.get("GOLDEN_INSIDE") == "1"
        need(TARGET != "computer" or inside, "the computer target runs inside a fresh ADE Computer container: bash drills/golden.sh starts it")
        self.work = os.path.realpath(tempfile.mkdtemp(prefix="ade-golden."))
        w = self.work
        # the home folder: the drill's own; in a fresh ADE Computer, the computer's (the container is thrown away)
        self.home = os.path.expanduser("~") if TARGET == "computer" else os.path.join(w, "home")
        self.bin = os.path.join(w, "bin"); self.tools = os.path.join(w, "tools")
        self.state = os.path.join(w, "claude"); self.tg = os.path.join(w, "telegram")
        for d in (self.home, self.bin, self.tools, self.state, self.tg, os.path.join(w, "gh-config")):
            os.makedirs(d, exist_ok=True)
        self.shown = []   # (screen name, Term or text, from, to): what the person saw, in order
        # tmux's sockets: a short path of their own (a socket's path has a length limit the temp folder can exceed)
        self.tmux = tempfile.mkdtemp(prefix="adg.", dir="/tmp")
        for n in ("gh", "curl", "systemctl", "loginctl", "bun"): os.symlink(os.path.join(FAKES, n), os.path.join(self.bin, n))
        for n in ("security", "launchctl", "pass", "gpg", "pbcopy", "pbpaste", "xclip", "wl-copy"):
            os.symlink(os.path.join(FAKES, "guard"), os.path.join(self.bin, n))
        # the real tools the path needs, by name: nothing else of this machine's PATH is seen (a real claude or gh
        # here would be this machine's account)
        missing = []
        for n in ("git", "python3", "tmux", "gitleaks", "script", "tar"):
            p = shutil.which(n)
            if not p: missing.append(n); continue
            os.symlink(p, os.path.join(self.tools, n))
        need(not missing, "this machine lacks: %s (the drill needs the real tools; it installs nothing)" % ", ".join(missing))
        self.real_curl = shutil.which("curl"); need(self.real_curl, "this machine lacks curl")
        path = ":".join((self.bin, os.path.join(self.home, ".local", "bin"), self.tools, "/usr/bin", "/bin", "/usr/sbin", "/sbin"))
        if TARGET == "linux":
            # a fresh Ubuntu: the system's own programs, without the viewer extras and without anything that holds an
            # account (the same machine wherever the drill runs: a CI runner, or the linux target inside the image)
            leave = {"yazi", "bat", "batcat", "glow", "pdftotext", "pdftoppm", "chafa", "code", "claude", "gh", "bun", "gemini", "brew"}
            for folder in ("/usr/bin", "/bin", "/usr/sbin", "/sbin"):
                for n in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
                    if n not in leave and not os.path.lexists(os.path.join(self.tools, n)): os.symlink(os.path.join(folder, n), os.path.join(self.tools, n))
            path = ":".join((self.bin, os.path.join(self.home, ".local", "bin"), self.tools))
        if TARGET == "computer":
            # an ADE Computer comes with Claude Code and its tools: the computer's own PATH, the stand-ins first
            os.symlink(os.path.join(FAKES, "claude"), os.path.join(self.bin, "claude"))
            path = ":".join((self.bin, os.path.join(self.home, ".local", "bin"), os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")))
        self.env = {
            "HOME": self.home, "PATH": path,
            "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TMPDIR": os.path.join(w, "tmp"), "USER": os.environ.get("USER", "drill"),
            "LOGNAME": os.environ.get("USER", "drill"), "SHELL": "/bin/bash",
            "GH_CONFIG_DIR": os.path.join(w, "gh-config"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
            "DRILL_FAKES": self.bin, "DRILL_CLAUDE_SRC": os.path.join(FAKES, "claude"), "DRILL_CLAUDE_INSTALLER": os.path.join(FAKES, "install-claude.sh"),
            "DRILL_REAL_CURL": self.real_curl, "DRILL_GH": os.path.join(w, "gh"), "DRILL_SYSTEMD": os.path.join(w, "systemd"),
            "DRILL_GUARD": os.path.join(w, "guard.log"), "DRILL_TEMPLATE": os.path.join(w, "src", "ade-brain"),
            "ADE_NO_UPDATE_CHECK": "1", "ADE_NO_CLAUDE_UPDATE": "1", "ADE_TMUX_SOCKET": "ade-golden-%d" % os.getpid(),
            "TMUX_TMPDIR": self.tmux, "ADE_CODE_DIR": os.path.join(self.home, "Project"),
            "AGENT_CHAT_TEST_TIMEOUT": "30", "AGENT_CHAT_FORWARD_EVERY": "0", "ADE_TG_WAIT": "30",
        }
        os.makedirs(self.env["TMPDIR"])
        if TARGET != "computer" and os.path.isfile("/etc/ade-computer"):
            self.env["ADE_COMPUTER_MARKER"] = "/nonexistent"   # the linux target inside the image: a plain Ubuntu machine
        if sys.platform == "darwin":
            # the hub's Linux layer (its file key store and systemd units, both inside the drill's home) on a Mac too:
            # the Mac layer is the login Keychain and launchd, which a drill must never touch
            self.env.update(AGENT_PLATFORM="linux", AGENT_PLATFORM_TEST="1")
        # Playwright's Chromium, where this machine keeps it (a tool, as git and tmux are): ade shot takes its pictures with it
        real = pwd.getpwuid(os.getuid()).pw_dir
        for c in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), os.path.join(real, ".cache", "ms-playwright"), os.path.join(real, "Library", "Caches", "ms-playwright"), "/opt/ms-playwright"):
            if c and os.path.isdir(c) and any(n.startswith("chromium") for n in os.listdir(c)):
                self.env["PLAYWRIGHT_BROWSERS_PATH"] = c; break
        self.api = None; self.botapi = None; self.terms = []

    # ---- helpers ----
    def run(self, argv, cwd=None, check=True, stdin=None, timeout=300):
        p = subprocess.run(argv, cwd=cwd or self.home, env=self.env, stdin=stdin or subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        out = p.stdout.decode("utf-8", "replace")
        if check: need(p.returncode == 0, "%s: exit %d: %s" % (" ".join(argv[:4]), p.returncode, " | ".join(out.strip().split("\n")[-3:])))
        return out

    def term(self, argv, cwd, name):
        t = Term(argv, cwd, self.env); self.terms.append(t); self.shown.append((name, t)); return t

    def sent(self):
        try: return [json.loads(l) for l in open(os.path.join(self.tg, "sent.jsonl")) if l.strip()]
        except OSError: return []

    def phone(self, text, sender=None):
        body = {"text": text}
        if sender: body["from"] = sender
        req = urllib.request.Request(self.api + "/phone/say", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()

    def wait_for(self, what, fn, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            v = fn()
            if v: return v
            time.sleep(0.3)
        raise Failed("waited %d s for %s" % (timeout, what))

    def claude_log(self):
        try: return open(os.path.join(self.state, "claude.log")).read()
        except OSError: return ""

    def ade_has(self, command):
        return subprocess.run(["ade", command, "--help"], env=self.env, cwd=self.home, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

    # ---- the path ----
    def prepare(self):
        """what the drill sets up before the path starts: the stand-in services, and the machine as a person has it"""
        self.botapi = subprocess.Popen([sys.executable, os.path.join(FAKES, "botapi.py"), self.tg, TOKEN, OWNER],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=open(os.path.join(self.tg, "errors.log"), "w"))
        port = self.wait_for("the stand-in Bot API", lambda: os.path.exists(os.path.join(self.tg, "port")) and open(os.path.join(self.tg, "port")).read().strip(), 15)
        self.api = "http://127.0.0.1:" + port; self.env["AGENT_TELEGRAM_API"] = self.api
        with open(os.path.join(self.home, ".fake-claude.json"), "w") as f:
            json.dump({"state": self.state, "model": os.path.join(HERE, "model"), "api": self.api}, f)
        # the hub template, read from GitHub as anyone can (a public repository; no account)
        src = os.path.join(self.work, "src"); os.makedirs(src)
        self.run(["git", "clone", "-q", "--depth", "1", "--branch", BRAIN_REF, ORG + "/ade-brain", os.path.join(src, "ade-brain")])
        # a person's git identity (a machine without one is told how to set it; the drill is not about that)
        self.run(["git", "config", "--global", "user.name", "Drill Owner"]); self.run(["git", "config", "--global", "user.email", "drill@example.invalid"])
        self.run(["git", "config", "--global", "init.defaultBranch", "main"])
        # the person's own repo, already on the machine, with one failing test
        self.repo = os.path.join(self.home, "Project", "calc"); shutil.copytree(os.path.join(HERE, "fixture"), self.repo, ignore=shutil.ignore_patterns("__pycache__"))
        self.run(["git", "init", "-q", "."], cwd=self.repo); self.run(["git", "add", "-A"], cwd=self.repo)
        self.run(["git", "commit", "-q", "-m", "calc: add, and its test"], cwd=self.repo)
        out = self.run(["python3", "-m", "unittest", "discover", "-s", "tests"], cwd=self.repo, check=False)
        need("FAILED" in out, "the fixture's test must fail before the fix; it said: " + out.strip().split("\n")[-1])

    def install(self):
        if ADE_REF:
            cli = os.path.join(self.work, "src", "ade-cli")
            self.run(["git", "clone", "-q", "--depth", "1", "--branch", ADE_REF, ORG + "/ade-cli", cli])
            self.run(["bash", os.path.join(cli, "install.sh")]); how = "from a checkout of " + ADE_REF
        else:
            # typed as the README says, on the person's terminal
            url = ORG.replace("https://github.com", "https://raw.githubusercontent.com") + "/ade-cli/main/install.sh"
            t = self.term(["bash", "-c", "curl -fsSL %s | bash" % url], self.home, "install")
            rc = t.wait(180); need(rc == 0, "the installer ended with exit %d: %s" % (rc, t.tail()))
            how = "the release, as curl ... | bash installs it"
        v = self.run(["ade", "version"]).strip()
        need(re.fullmatch(r"ade [0-9]+\.[0-9]+\.[0-9]+", v), "ade version says [%s]" % v)
        self.ade_version = v; return "%s (%s)" % (v, how)

    def guide(self):
        """ade setup on a terminal, the person answering from answers/guide.txt. A line is "<wait for this text><TAB>
        <what to type>" (more tabs: more to do, in order; a line that starts with "?" is a question only some machines ask,
        answered whenever it comes); @enter is the Enter key, @hub and @token the hub's name and the
        stand-in bot token, and the other @ words are what the person does away from that terminal (see act)."""
        t = self.term(["ade", "setup"], self.home, "guide"); self.second = None
        rows = [r.rstrip("\n").split("\t") for r in open(os.path.join(HERE, "answers", "guide.txt")) if r.strip() and not r.startswith("#")]
        maybe = {r[0][1:]: r[1:] for r in rows if r[0].startswith("?")}   # asked on some machines only
        for want, *does in (r for r in rows if not r[0].startswith("?")):
            while True:
                got = t.expect(want, also=tuple(maybe))
                if got == want: break
                for do in maybe.pop(got): t.send({"@enter": ""}.get(do, do))
            for do in does:
                if do in ("@second-terminal", "@message-the-bot", "@lock"): self.act(do)
                else: t.send({"@token": TOKEN, "@hub": HUB, "@enter": ""}.get(do, do))
        rc = t.wait(120)
        need(rc == 0, "ade setup ended with exit %d: %s" % (rc, t.tail()))
        self.second.wait(30)   # ade closed the second terminal's session for the bot's test
        self.hub = os.path.join(self.home, "hubs", HUB)
        need(os.path.isfile(os.path.join(self.hub, "hub.conf")), "there is no hub at ~/hubs/" + HUB)

    def act(self, do):
        hub = os.path.join(self.home, "hubs", HUB)
        if do == "@second-terminal":      # "open a second terminal window and type: cd <hub> && bin/chat start"
            self.second = self.term(["bash", "-c", "bin/chat start"], hub, "guide-6b-second-terminal")
            self.second.expect("permission mode: manual", 60)
        elif do == "@message-the-bot":    # "in Telegram, send your bot any message", then the code it replies with
            self.phone("hello")
            code = self.wait_for("the bot's pairing code", lambda: [m for m in self.sent() if "/telegram:access pair " in m.get("text", "")], 30)[-1]["text"].split("pair ")[-1].strip()
            self.second.send("/telegram:access pair " + code); self.second.expect("paired", 30)
        elif do == "@lock":
            self.second.send("/telegram:access policy allowlist"); self.second.expect("policy: allowlist", 30)

    def check_claude(self):
        log = self.claude_log()
        need(":: auth login" in log, "the guide did not run Claude Code's sign-in")
        if TARGET == "computer": return "it comes with the computer (the stand-in in its place); signed in by the guide's step 2 (stand-in account)"
        need(os.access(os.path.join(self.home, ".local", "bin", "claude"), os.X_OK), "Claude Code was not installed by the guide")
        return "installed by the guide's step 1, signed in by its step 2 (stand-in account)"

    def check_github(self):
        gh = open(os.path.join(self.env["DRILL_GH"], "gh.log")).read()
        need("auth login --hostname github.com --git-protocol https --web" in gh, "the guide did not run gh's browser sign-in")
        need("token" not in gh, "a gh call names a token")
        return "gh auth login --web, on the person's terminal"

    def check_hub(self):
        bare = os.path.join(self.env["DRILL_GH"], "github", "drill-owner", HUB + ".git")
        need(os.path.isdir(bare), "no repository %s on the stand-in GitHub" % HUB)
        need(open(os.path.join(bare, "visibility")).read().strip() == "--private", "the hub's repository is not private")
        head = self.run(["git", "rev-parse", "HEAD"], cwd=self.hub).strip()
        remote = self.run(["git", "--git-dir", bare, "rev-parse", "main"]).strip()
        n = int(self.run(["git", "--git-dir", bare, "rev-list", "--count", "main"]).strip())
        need(n >= 2, "nothing was saved to GitHub after the template's first commit")
        need(head == remote, "the hub's last commit is not on GitHub")
        left = sorted(set(l[3:].split("/")[0] for l in self.run(["git", "status", "--porcelain"], cwd=self.hub).split("\n") if l.strip()))
        return "~/hubs/%s, private, %d commits on the stand-in GitHub (bin/sync); what the guide wrote after that save waits for the next sync: %s" % (HUB, n, ", ".join(left) or "nothing")

    def check_telegram(self):
        out = self.run(["ade", "setup", "--check"], cwd=self.hub)
        need("telegram: on (auto)" in out, "ade setup --check does not say telegram: on (auto): " + " | ".join(out.strip().split("\n")[-3:]))
        st = self.run(["bin/chat", "status"], cwd=self.hub)
        need("locked to you" in st and "mode: auto" in st and "running" in st.split("\n")[0], "bin/chat status: " + " | ".join(st.strip().split("\n")))
        return "locked to the one paired account, the background session runs in auto mode"

    def stranger(self):
        """an account that is not the owner's writes to the locked bot: nothing reaches the main agent, nothing is answered"""
        before = len(self.sent()); self.phone("fix everything", "999001")
        self.wait_for("the plugin to drop the stranger's message", lambda: "dropped: a message from an account that is not on the allowlist" in self.claude_log(), 30)
        need(len(self.sent()) == before, "the bot answered an account that is not the owner's")
        return "a message from another account is dropped, unanswered"

    def project(self):
        if not self.ade_has("project"):
            # what works today instead (the hub's own bin/new and the Code row a person writes by hand), so the rest runs
            self.run(["bin/new", "projects/calc"], cwd=self.hub)
            acc = os.path.join(self.hub, "projects", "calc", "ACCESS.md"); s = open(acc).read()
            row = "| calc (local) | %s | main | (owner) | none found |\n" % self.repo
            need("|---|---|---|---|---|\n" in s, "the folder's ACCESS.md has no Code table")
            with open(acc, "w") as f: f.write(s.replace("|---|---|---|---|---|\n", "|---|---|---|---|---|\n" + row, 1))
            return None
        t = self.term(["ade", "project", "add", self.repo], self.home, "project-add")
        for row in open(os.path.join(HERE, "answers", "project.txt")):
            row = row.rstrip("\n")
            if not row or row.startswith("#"): continue
            want, _, do = row.partition("\t"); t.expect(want); t.send(do)
        rc = t.wait(120); need(rc == 0, "ade project add ended with exit %d: %s" % (rc, t.tail()))
        need(os.path.isfile(os.path.join(self.hub, "projects", "calc", "ACCESS.md")), "there is no projects/calc in the hub")
        acc = open(os.path.join(self.hub, "projects", "calc", "ACCESS.md")).read()
        need("| ~/Project/calc |" in acc or self.repo in acc, "the folder's ACCESS.md does not name the checkout")
        return "projects/calc, its Code row names ~/Project/calc"

    def message(self):
        self.before = len(self.sent()); self.phone(MESSAGE)
        self.wait_for("the message to reach the main agent", lambda: ("channel message from the paired owner, mode auto: " + MESSAGE) in self.claude_log(), 30)
        return "getUpdates, the allowlist, then the model: in auto mode, nothing asked at a terminal"

    def dispatched(self):
        want = "%s :: " % os.path.realpath(self.repo)
        def started():
            return [l for l in self.claude_log().split("\n") if l.startswith(want) and MESSAGE in l]
        l = self.wait_for("a focus agent in the project's checkout with the message as its prompt", started, 90)[0]
        need("--channels" not in l, "the focus agent is the chat session itself")
        tabs = self.run(["tmux", "-L", self.env["ADE_TMUX_SOCKET"], "list-windows", "-a", "-F", "#{window_name}"], check=False)
        need("projects/calc" in tabs.split(), "no tab projects/calc in ade's workspace: " + " ".join(tabs.split()))
        return "ade work --prompt: a session in ~/Project/calc, a tab projects/calc in ade's workspace"

    def one_main(self):
        """the main agent that got the message is the only one: ade work must not start a second in tab 0"""
        hub = os.path.realpath(self.hub) + " :: "
        twins = [l for l in self.claude_log().split("\n") if l.startswith(hub) and "--remote-control %s" % HUB in l and "--channels" not in l]
        return None if twins else "ade work kept the running main agent's place in tab 0 and started no second one"

    def fixed(self):
        self.wait_for("the reviewer's result", lambda: os.path.exists(os.path.join(self.state, "focus-done")), 90)
        need(open(os.path.join(self.repo, "calc.py")).read() == open(os.path.join(HERE, "model", "fix", "calc.py")).read(), "calc.py was not fixed")
        return "calc.py changed in the checkout (the scripted model's fix)"

    def reviewed(self):
        res = open(os.path.join(self.state, "focus-done")).read().strip()
        need(res == "pass: python3 -m unittest discover -s tests", "the reviewer says: " + res)
        need(re.search(r"^OK$", open(os.path.join(self.state, "review.txt")).read(), re.M), "the recorded output has no OK line")
        out = self.run(["python3", "-m", "unittest", "discover", "-s", "tests"], cwd=self.repo, check=False)   # the drill's own run
        need(re.search(r"^OK$", out, re.M), "the drill's own run of the verification command fails")
        return "the verification command from docs/architecture.md, run by the reviewer and again by the drill: OK"

    def done(self):
        m = self.wait_for("a Done reply on the phone", lambda: [x for x in self.sent()[self.before:] if x["method"] == "sendMessage" and x.get("text", "").startswith(("Done", "Not done"))], 120)[0]
        need(m["text"].startswith("Done"), "the reply is: " + m["text"]); need(m["chat_id"] == OWNER, "the reply went to another chat")
        return "\"%s\"" % m["text"][:70]

    def picture(self):
        if not self.ade_has("shot"): return None
        need("PLAYWRIGHT_BROWSERS_PATH" in self.env, "this machine has no Playwright Chromium, which ade shot needs (npx -y playwright install chromium)")
        m = self.wait_for("a picture on the phone", lambda: [x for x in self.sent()[self.before:] if x["method"] == "sendPhoto"], 60)[0]
        need(m.get("png") and m["bytes"] > 500, "what arrived is not a PNG"); need(m["chat_id"] == OWNER, "the picture went to another chat")
        return "a PNG of the focus agent's tab, %d bytes, caption \"%s\" (ade shot agent --tg)" % (m["bytes"], m.get("caption", ""))

    def hub_send(self):
        png = os.path.join(HERE, "fixture", "docs", "proof.png"); n = len(self.sent())
        with open(os.devnull) as nothing:
            self.run(["bin/chat", "send", png], cwd=self.hub, stdin=nothing)
        m = self.sent()[n:]
        need(len(m) == 1 and m[0]["method"] == "sendPhoto" and m[0]["png"], "bin/chat send delivered: %s" % m)
        return "the hub's bin/chat send delivers an image to the paired owner"

    def no_leak(self):
        try: g = open(self.env["DRILL_GUARD"]).read().strip()
        except OSError: g = ""
        need(not g, "a guarded tool was called: " + " | ".join(g.split("\n")[:3]))
        hits = []
        for t in self.terms: need(TOKEN.encode() not in t.raw, "the bot token was shown on a terminal")
        for root in (self.state, os.path.join(self.hub, ".git"), self.env["DRILL_SYSTEMD"]):
            for d, _, files in os.walk(root):
                for n in files:
                    try:
                        if TOKEN.encode() in open(os.path.join(d, n), "rb").read(): hits.append(os.path.relpath(os.path.join(d, n), self.work))
                    except OSError: pass
        need(not hits, "the bot token is in: " + ", ".join(hits[:3]))
        log = open(os.path.join(self.tg, "sent.jsonl")).read()
        need(TOKEN not in log, "the bot token was sent to the chat")
        return "no call to security, launchctl, pass, gpg or the clipboard; the bot token is on no screen, in no log and no commit"

    def record(self):
        """what the person saw: [(screen, text, seconds)], each written to <out>/transcripts/ as .ansi and .txt"""
        you = {"macos": "/Users/you", "linux": "/home/you"}.get(TARGET)
        subs = [(os.path.realpath(self.home), you), (self.home, you)] if you else []
        subs += [("/private" + self.work, "<drill>"), (self.work, "<drill>"), (self.env["ADE_TMUX_SOCKET"], "ade-golden"), (self.tmux, "<tmux>")]
        got = []
        for name, t in self.shown:
            text = screens.plain(t.raw)
            if name != "guide":
                got.append((name, t.raw, text, t.marks[-1][0] - t.marks[0][0])); continue
            parts = screens.split_guide(text); cuts = []
            for n, body in parts:   # when each part began, from the same words in the raw screen
                m = re.match(r"guide-(\d)-", n); at = 0
                if m and m.group(1) == "9": at = max(t.raw.rfind(b"All set"), t.raw.rfind(b"Not finished"), 0)
                elif m and m.group(1) != "0": at = max(t.raw.find(("Step %s of" % m.group(1)).encode()), 0)
                cuts.append(at)
            for i, (n, body) in enumerate(parts):
                end = cuts[i + 1] if i + 1 < len(parts) else len(t.raw)
                got.append((n, t.raw[cuts[i]:end], body, t.when(end) - t.when(cuts[i])))
        # the second terminal belongs with the guide's Telegram step, before the guide's last lines
        got.sort(key=lambda g: (0 if g[0] == "install" else 2 if g[0] == "project-add" else 1, g[0] if g[0].startswith("guide") else ""))
        try: rows = [json.loads(l) for l in open(os.path.join(self.tg, "phone.jsonl")) if l.strip()]
        except OSError: rows = []
        if rows:
            phone = "".join("%s: %s%s\n" % (r["who"], r["text"].replace("\n", "\n    "), "  [Approve] [Deny]" if r.get("buttons") else "") for r in rows)
            got.append(("phone", phone.encode(), phone, None))
        tr = os.path.join(OUT, "transcripts"); shutil.rmtree(tr, ignore_errors=True); os.makedirs(tr)
        out = []
        for i, (name, raw, text, sec) in enumerate(got):
            n = "%02d-%s" % (i + 1, name); text = screens.clean(text, subs)
            with open(os.path.join(tr, n + ".ansi"), "wb") as f: f.write(raw)
            with open(os.path.join(tr, n + ".txt"), "w") as f: f.write(text)
            out.append((n, text, sec))
        return out

    def cleanup(self):
        for t in self.terms: t.close()
        if os.path.isdir(os.path.join(self.home, "hubs", HUB)):
            subprocess.run(["bin/chat", "stop"], cwd=os.path.join(self.home, "hubs", HUB), env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for sock in (["-L", self.env["ADE_TMUX_SOCKET"]], []):
            subprocess.run([os.path.join(self.tools, "tmux")] + sock + ["kill-server"], env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sd = self.env["DRILL_SYSTEMD"]
        for n in os.listdir(sd) if os.path.isdir(sd) else []:
            if n.endswith(".pid"):
                try: pid = int(open(os.path.join(sd, n)).read().strip() or 0)
                except (OSError, ValueError): pid = 0
                if pid > 1:   # never 0: that is this drill's own process group
                    try: os.kill(pid, signal.SIGTERM)
                    except OSError: pass
        if self.botapi: self.botapi.terminate(); self.botapi.wait()
        if os.environ.get("GOLDEN_KEEP") == "1": print("kept: " + self.work); return
        else: shutil.rmtree(self.work, ignore_errors=True)
        shutil.rmtree(self.tmux, ignore_errors=True)


# the path, in order: (name, method, the story that closes the gap when the method returns None)
STEPS = [
    ("install: curl ... | bash", "install", None),
    ("guide: ade setup, from nothing to the end", "guide", None),
    ("guide: Claude Code installed and signed in", "check_claude", None),
    ("guide: signed in to GitHub", "check_github", None),
    ("guide: hub created and saved to GitHub", "check_hub", None),
    ("guide: Telegram locked, auto mode", "check_telegram", None),
    ("telegram: only the owner reaches the main agent", "stranger", None),
    ("project: ade project add your repo", "project", "A21 (ade-cli PR #60, not in a release): the folder was made with the hub's bin/new and a Code row by hand"),
    ("telegram: \"fix X\" reaches the main agent", "message", None),
    ("dispatch: the main agent starts a focus agent on it", "dispatched", None),
    ("dispatch: still one main agent", "one_main", "G9 (ade-cli): ade work, called by the main agent itself, did not see it running (pgrep leaves out its own ancestors on macOS) and started a second main session in tab 0"),
    ("fix: the focus agent fixes it", "fixed", None),
    ("review: the reviewer runs the tests", "reviewed", None),
    ("phone: \"Done\" arrives", "done", None),
    ("phone: a picture arrives", "picture", "A20 (ade shot is merged, ade-cli PR #59, not in a release): no picture was sent"),
    ("hub: bin/chat send delivers an image", "hub_send", None),
    ("safety: nothing of this machine's, no token shown", "no_leak", None),
]
# gaps of the path that no stand-in can reach: listed every run, never green (docs/stories/D3 names each story)
PENDING = [
    ("guide: the command is `ade guide`", "G2 (ade-cli): today the guide is `ade setup`; `ade guide` is an unknown command"),
    ("telegram: pairing without typed commands", "G4 (ade-cli and ade-brain): the drill typed /telegram:access pair and policy allowlist in a second terminal"),
    ("telegram: a focus agent's permission prompt reaches the phone", "G5 (ade-brain): the approval relay is not built; the scripted model asked for nothing"),
    ("dispatch: the main agent's route from a chat message", "G6 (ade-brain): no rule or script fixes the route; here the scripted model chose ade work --prompt"),
    ("phone: Done always comes with proof", "G7 (ade-brain, ade-skills): nothing tells the main agent to send ade shot --tg with Done; here the scripted model did"),
    ("hub: an existing hub gets the template's fixes", "G8 (ade-cli and ade-brain): ade update pulls the hub's own repository, which has no link to the template"),
]


def main():
    d = None; failed = False; shown = []; notes = []
    try:
        d = Drill(); d.prepare()
        for name, method, story in STEPS:
            if failed: line("not run", name); continue
            t0 = time.time()
            try:
                detail = getattr(d, method)()
                if detail is None and story: line("pending", name, story, time.time() - t0)
                else: line("ok", name, detail or "", time.time() - t0)
            except Failed as e:
                failed = True; line("FAIL", name, str(e), time.time() - t0)
            except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as e:
                failed = True; line("FAIL", name, "%s: %s" % (e.__class__.__name__, e), time.time() - t0)
        for name, story in PENDING: line("pending", name, story)
        # what the person saw: the transcripts, then the golden files (the released ade only: a branch changes wording on purpose)
        shown = d.record(); golden = os.path.join(HERE, "transcripts", TARGET); name = "screens: the wording is the golden transcripts'"
        if ADE_REF: notes.append("not compared: ade is from %s, and the golden files are the release's" % ADE_REF)
        elif failed: notes.append("not compared: a step failed")
        else:
            bad = screens.compare(os.path.join(OUT, "transcripts"), golden, os.environ.get("GOLDEN_UPDATE") == "1")
            if bad:
                failed = True; notes += bad
                line("FAIL", name, "%d screen(s) changed (GOLDEN_UPDATE=1 takes the new wording on purpose): %s" % (len(bad), "; ".join(bad)[:400]))
            else:
                notes.append("%d screens equal transcripts/%s/%s" % (len(shown), TARGET, " (written by this run: GOLDEN_UPDATE=1)" if os.environ.get("GOLDEN_UPDATE") == "1" else ""))
                line("ok", name, notes[-1])
    except Failed as e:
        failed = True; line("FAIL", "the drill's own set-up", str(e))
    finally:
        if d: d.cleanup()
    ver = getattr(d, "ade_version", "ade not installed") if d else "ade not installed"
    if ADE_REF: ver += " from " + ADE_REF
    try:
        jargon = [l.strip() for l in open(os.path.join(HERE, "jargon.txt")) if l.strip() and not l.startswith("#")]
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "report.md"), "w") as f: f.write(screens.report(TARGET, ver, RESULTS, shown, jargon, notes))
        print("report: %s" % os.path.join(OUT, "report.md"))
    except OSError as e:
        failed = True; print("FAIL    the report: %s" % e)
    ok = sum(1 for r in RESULTS if r[0] == "ok"); pend = sum(1 for r in RESULTS if r[0] == "pending")
    bad = sum(1 for r in RESULTS if r[0] in ("FAIL", "not run"))
    print("golden: %s, %s: %d ok, %d pending, %d failed or not run" % (TARGET, ver, ok, pend, bad))
    if failed: return 1
    print("ok"); return 0


if __name__ == "__main__":
    sys.exit(main())
