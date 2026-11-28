#!/usr/bin/env python3
"""One run of the `ade ui` tour (story D5): a real `ade ui` on a private tmux socket, driven with the mouse, recorded.

  python3 drills/ui-tour/run.py <out> <ade-cli checkout>

Real: ade from the checkout of the pinned release (its install.sh), the hub template (ade hub new --no-github), ade ui,
ade docs and ade web, tmux on a socket of the drill's own. The client is a %dx%d pseudo-terminal; a click is a tmux
mouse event (SGR) sent where the bar or a menu draws the label (tour.Screen finds it).
Stand-ins: Claude Code (drills/golden/fakes/claude), whose sessions run the scripted agents (model/builder.sh); the
desktop browser (fakes/browser: it keeps ade's link, and Playwright's Chromium draws the page, shot.cjs). Guards: gh,
security, launchctl, pass, gpg and the clipboard tools fail the run when anything calls them.

Writes <out>/ade-ui-tour.cast, .json and .vtt, and docs-page.png (step 7's picture). drills/ui-tour.sh renders them.
  UI_TOUR_KEEP=1   keep the run's folder and print it
  UI_TOUR_NODE_PATH  where node finds playwright (shot.cjs)
"""
import fcntl, json, os, pty, pwd, re, select, shutil, signal, socket, struct, subprocess, sys, tempfile, termios, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tour  # noqa: E402
GOLDEN = os.path.join(os.path.dirname(HERE), "golden", "fakes")
AGENTS = ("api", "web", "docs")
__doc__ = __doc__ % (tour.COLS, tour.ROWS)


def need(cond, why):
    if not cond: raise tour.TourFailed(why)


class Run:
    def __init__(self, out, cli):
        self.out, self.cli = out, cli
        self.work = os.path.realpath(tempfile.mkdtemp(prefix="adt.", dir="/tmp"))   # short: tmux's socket path has a limit
        w = self.work; self.home = os.path.join(w, "h"); self.bin = os.path.join(w, "bin"); self.state = os.path.join(w, "claude")
        self.tour = os.path.join(self.state, "tour")
        for d in (self.home, self.bin, self.tour, os.path.join(w, "tmp"), os.path.join(w, "tmux")): os.makedirs(d, exist_ok=True)
        os.symlink(os.path.join(GOLDEN, "claude"), os.path.join(self.bin, "claude"))
        for n in ("open", "xdg-open"): os.symlink(os.path.join(HERE, "fakes", "browser"), os.path.join(self.bin, n))
        for n in ("gh", "security", "launchctl", "pass", "gpg", "pbcopy", "pbpaste", "xclip", "wl-copy"):
            os.symlink(os.path.join(GOLDEN, "guard"), os.path.join(self.bin, n))
        self.sock = "ade-tour-%d" % os.getpid()
        self.env = {
            "HOME": self.home, "PATH": ":".join((self.bin, os.path.join(self.home, ".local", "bin"), os.environ.get("PATH", "/usr/bin:/bin"))),
            "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TMPDIR": os.path.join(w, "tmp"),
            "USER": "you", "LOGNAME": "you", "SHELL": "/bin/bash", "DISPLAY": ":99",   # xdg-open is used with a display
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "DRILL_GUARD": os.path.join(w, "guard.log"), "DRILL_TOUR": self.tour,
            "ADE_NO_UPDATE_CHECK": "1", "ADE_NO_CLAUDE_UPDATE": "1", "ADE_TMUX_SOCKET": self.sock, "TMUX_TMPDIR": os.path.join(w, "tmux"),
        }
        if sys.platform == "darwin": self.env.update(AGENT_PLATFORM="linux", AGENT_PLATFORM_TEST="1")   # never the Keychain or launchd
        if os.environ.get("UI_TOUR_NODE_PATH"): self.env["NODE_PATH"] = os.environ["UI_TOUR_NODE_PATH"]
        real = pwd.getpwuid(os.getuid()).pw_dir
        for c in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), os.path.join(real, ".cache", "ms-playwright"),
                  os.path.join(real, "Library", "Caches", "ms-playwright")):
            if c and os.path.isdir(c): self.env["PLAYWRIGHT_BROWSERS_PATH"] = c; break
        self.pid = self.fd = None; self.raw = b""; self.marks = []; self.screen = tour.Screen(); self.shot = None; self.tty = None

    # ---- set-up ----
    def sh(self, argv, cwd=None, check=True, timeout=300):
        p = subprocess.run(argv, cwd=cwd or self.home, env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        out = p.stdout.decode("utf-8", "replace")
        need(not check or p.returncode == 0, "%s: exit %d: %s" % (" ".join(argv[:4]), p.returncode, " | ".join(out.strip().split("\n")[-3:])))
        return out

    def tmux(self, *args, check=False):
        return self.sh(["tmux", "-L", self.sock] + list(args), check=check, timeout=20).strip()

    def answer(self, argv, cwd, reply, timeout=180):
        """a command that asks one question on its terminal, answered with reply"""
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(cwd); os.execvpe(argv[0], argv, self.env)
        end = time.time() + timeout; sent = False; out = b""
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                try: got = os.read(fd, 4096)
                except OSError: break
                if not got: break
                out += got
                if not sent and re.search(rb"\[y/N\]|\(y/n\)|y/n|\? ", out): os.write(fd, reply.encode()); sent = True
            p, st = os.waitpid(pid, os.WNOHANG)
            if p: return os.waitstatus_to_exitcode(st), out.decode("utf-8", "replace")
        try: os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
        except OSError: pass
        return 124, out.decode("utf-8", "replace")

    def prepare(self):
        self.sh(["git", "config", "--global", "user.name", "Tour Owner"]); self.sh(["git", "config", "--global", "user.email", "tour@example.invalid"])
        self.sh(["git", "config", "--global", "init.defaultBranch", "main"])
        with open(os.path.join(self.home, ".fake-claude.json"), "w") as f: json.dump({"state": self.state, "model": os.path.join(HERE, "model")}, f)
        os.makedirs(os.path.join(self.home, ".config", "ade"), exist_ok=True)
        with open(os.path.join(self.home, ".config", "ade", "hints"), "w") as f: f.write("ui-click-off\n")   # U5's first-run line: not in the tour
        self.sh(["bash", os.path.join(self.cli, "install.sh")])
        self.versions = {"ade": self.sh(["ade", "version"]).strip(), "tmux": self.sh(["tmux", "-V"]).strip()}
        need(re.fullmatch(r"ade [0-9]+\.[0-9]+\.[0-9]+", self.versions["ade"]), "ade version says [%s]" % self.versions["ade"])
        rc, out = self.answer(["ade", "setup", "--diagrams"], self.home, "y\n")   # U6: the pinned mermaid.min.js, for step 7
        self.versions["diagrams"] = "installed" if rc == 0 else "not installed (ade setup --diagrams: exit %d)" % rc
        self.sh(["ade", "hub", "new", "tour", "--dir", os.path.join(self.home, "hubs"), "--no-github", "--persona", "tech-lead",
                 "--client", "demo", "--owner", "you"])
        self.hub = os.path.join(self.home, "hubs", "tour")
        for n in AGENTS + ("billing",): self.sh(["bin/new", "projects/" + n], cwd=self.hub)
        fx = os.path.join(HERE, "fixture")
        for n in os.listdir(fx): shutil.copytree(os.path.join(fx, n), os.path.join(self.hub, "projects", n), dirs_exist_ok=True)
        # the docs, newest first: the PRD, then the architecture, then the story
        docs = os.path.join(self.hub, "projects", "docs", "_bmad-output"); t = time.time()
        for i, f in enumerate(("prd.md", "architecture.md", "stories/1-1-invoice-export.md")): os.utime(os.path.join(docs, f), (t - 60 * (i + 1),) * 2)
        for n in AGENTS: self.sh(["ade", "work", "projects/" + n, "--prompt", "tour agent " + n], cwd=self.hub)

    # ---- the client ----
    def attach(self):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", tour.ROWS, tour.COLS, 0, 0))
            os.chdir(self.hub); os.execvpe("ade", ["ade", "ui"], self.env)
        self.marks = [(time.time(), 0)]
        end = time.time() + 60
        while not all(self.find("projects/" + n, "bar") for n in AGENTS):
            need(time.time() < end, "ade ui did not show the tabs %s; the bar reads: %s" % (", ".join(AGENTS), self.screen.row(tour.ROWS).strip()))
            self.pump(0.2)
        self.tty = self.tmux("list-clients", "-F", "#{client_tty}").split("\n")[0]
        self.tmux("select-window", "-t", ":0"); self.refresh(); self.pump(1.0)

    # ---- the driver tour.Tour uses ----
    def now(self): return time.time()

    def pump(self, s):
        end = time.time() + s
        while True:
            r, _, _ = select.select([self.fd], [], [], max(0.0, end - time.time()))
            if r:
                try: got = os.read(self.fd, 65536)
                except OSError: got = b""
                need(got, "the ade ui client ended; the screen ends with: " + self.screen.text().strip()[-300:])
                self.raw += got; self.marks.append((time.time(), len(self.raw)))
                self.screen.feed(got.decode("utf-8", "replace"))
            if time.time() >= end: return

    def find(self, text, where=None): return self.screen.find(text, where)
    def send(self, data): os.write(self.fd, data.encode())
    def refresh(self): self.tmux("refresh-client", *(["-t", self.tty] if self.tty else []))

    def agent(self, name, what):
        p = os.path.join(self.tour, name + ".do")
        with open(p + ".part", "w") as f: f.write(what + "\n")
        os.replace(p + ".part", p)

    def state(self, folder, icon):
        return re.search(re.escape(icon) + r"\s*\d+\s+" + re.escape(folder) + r"(?![\w/.-])", self.screen.row(tour.ROWS))

    def browser(self):
        url = os.path.join(self.tour, "browser.url")
        if not os.path.exists(url): return False
        if not self.shot:
            m = re.search(r"code[^0-9A-Za-z\n]{1,20}([0-9]{4,8}|[A-Za-z0-9]{3,6}-[A-Za-z0-9]{3,6})", self.screen.text())
            self.shot = subprocess.Popen(["node", os.path.join(HERE, "shot.cjs"), open(url).read().strip(), os.path.join(self.out, "docs-page.png"),
                                          os.path.join(self.work, "docs-page.txt"), os.path.join(self.work, "docs-page.html")] + ([m.group(1)] if m else []),
                                         env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return True

    # ---- the result ----
    def finish(self, rec):
        need(self.shot, "the browser was never opened")
        out = self.shot.communicate(timeout=120)[0].decode("utf-8", "replace"); rc = self.shot.returncode
        need(rc == 0, "the Docs page could not be drawn (shot.cjs: exit %d): %s" % (rc, out.strip()[-300:]))
        g = os.path.join(self.work, "guard.log")
        need(not os.path.exists(g), "a guarded tool was called: " + (open(g).read().strip().split("\n")[0] if os.path.exists(g) else ""))
        subs, known = self.names()
        self.check_page(known)
        cast, facts = tour.build(rec, self.raw, self.marks, subs=subs, known=known)
        with open(os.path.join(self.out, tour.NAME + ".cast"), "w") as f: f.write(cast)
        with open(os.path.join(self.out, tour.NAME + ".vtt"), "w") as f: f.write(tour.vtt())
        with open(os.path.join(self.out, tour.NAME + ".json"), "w") as f:
            json.dump(tour.manifest(os.environ.get("ADE_UI_TOUR_REF", ""), facts, self.versions), f, indent=1, ensure_ascii=False)
        return facts

    def check_page(self, known):
        """the Docs page as Chromium drew it (its text, and its HTML: alt, title and links count) holds nothing that must
        never show: scanned raw, never redacted first, since the picture of it is not redacted. TourFailed names the kind."""
        page = "".join(open(os.path.join(self.work, f), errors="replace").read() + "\n" for f in ("docs-page.txt", "docs-page.html"))
        bad = tour.scan(page, known)
        if any(p and p in page for p in (self.home, self.work, os.path.basename(self.work))): bad.append("the drill's folder")
        need(not bad, "the Docs page picture would show %s" % ", ".join(bad))

    def names(self):
        """(subs, known): the drill's folders put away, and this machine's names, for the cast and the failure screen"""
        subs = [("/private" + self.home, "~"), (self.home, "~"), ("/private" + self.work, "<drill>"), (self.work, "<drill>"), (self.sock, "ade")]
        me = pwd.getpwuid(os.getuid()).pw_name; host = socket.gethostname().split(".")[0]
        return subs, tuple(k for k in (me, host, os.path.basename(self.work)) if k and k not in ("localhost", "you", "root"))

    def cleanup(self):
        if self.pid:
            try: os.kill(self.pid, signal.SIGTERM); os.waitpid(self.pid, 0)
            except OSError: pass
        subprocess.run(["tmux", "-L", self.sock, "kill-server"], env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.shot and self.shot.poll() is None: self.shot.kill()
        if os.environ.get("UI_TOUR_KEEP") == "1": print("kept: " + self.work); return
        shutil.rmtree(self.work, ignore_errors=True)


def main(argv):
    if len(argv) != 2: print(__doc__.strip().split("\n\n")[0], file=sys.stderr); return 2
    out = os.path.abspath(argv[0]); os.makedirs(out, exist_ok=True)
    r = Run(out, os.path.abspath(argv[1]))
    try:
        r.prepare(); r.attach()
        rec = tour.Tour(r).run()
        facts = r.finish(rec)
        print("tour: 8 steps, %d clicks; each step took %s s" % (len(facts["clicks"]), ", ".join("%.1f" % m for m in facts["measured"])))
        return 0
    except (tour.TourFailed, ValueError, subprocess.SubprocessError, OSError) as e:
        print("UI TOUR FAIL: %s" % e, file=sys.stderr)
        subs, known = r.names(); text = r.screen.text()
        for a, b in subs: text = text.replace(a, b)
        with open(os.path.join(out, "screen.txt"), "w") as f: f.write(tour.redact(text, known))
        return 1
    finally:
        r.cleanup()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
