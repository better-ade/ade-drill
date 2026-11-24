"""Tests of the raw-Ubuntu drill's own parts (story D4). No network, no Docker: the drill itself runs in CI."""
import json, os, shutil, subprocess, sys, tempfile, time, unittest, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "drills", "raw")
G = os.path.join(ROOT, "drills", "golden")
sys.path.insert(0, R)
import flow  # noqa: E402

README = """# ade

## Install

**Today** (needs `git` and Bash):

```bash
git clone https://github.com/better-ade/ade-cli && cd ade-cli && ./install.sh
```

Or in one line:

```bash
curl -fsSL https://raw.githubusercontent.com/better-ade/ade-cli/main/install.sh | bash
```

## Quick start

```bash
ade help                         # every command, one line each
ade version                      # ade 0.2.8
ade project add ~/Project/api ~/Project/web    # each becomes projects/<name>
```

`ade setup` is the guide, one step at a time. `ade hub new my-hub` creates the hub.

## How ade fits
"""


class Readme(unittest.TestCase):
    def test_readme_steps_are_read_from_the_readme(self):
        s = flow.readme_steps(README)
        self.assertEqual(s["install"], "curl -fsSL https://raw.githubusercontent.com/better-ade/ade-cli/main/install.sh | bash")
        self.assertEqual(s["quick"], ["ade help", "ade version"])
        self.assertEqual(s["setup"], "ade setup")
        self.assertEqual(s["project_add"], "ade project add")
        self.assertEqual(s["hub_new"], "ade hub new")
        # ade main is installed the README's other way: its checkout's install.sh
        self.assertEqual(s["clone"], "git clone https://github.com/better-ade/ade-cli && cd ade-cli && ./install.sh")

    def test_readme_without_the_install_line_fails(self):
        with self.assertRaises(ValueError) as e: flow.readme_steps(README.replace("| bash", "| sh"))
        self.assertIn("Install", str(e.exception))
        with self.assertRaises(ValueError): flow.readme_steps(README.replace("`ade setup`", "`ade guide`"))
        with self.assertRaises(ValueError): flow.readme_steps(README.replace("ade version ", "ade --version "))


class Missing(unittest.TestCase):
    def test_missing_tools_are_found_on_the_screen(self):
        text = ("bash: line 1: curl: command not found\n"
                "Command 'git' not found, but can be installed with:\nsudo apt install git\n"
                "install: needs python3\n"
                "Install git python3 tmux gh gitleaks now? This runs: sudo apt-get install -y git python3 tmux gh gitleaks [y/N] y\n"
                "E: Unable to locate package gitleaks\n"
                "/home/you/hubs/h/bin/work: line 148: ps: command not found\n")
        got = flow.missing_tools("install", text)
        self.assertEqual([(t, h) for t, h, _ in got], [
            ("curl", "command not found"), ("git", "command not found (command-not-found)"), ("python3", "the installer needs it"),
            ("git", "the guide offered to install it"), ("python3", "the guide offered to install it"), ("tmux", "the guide offered to install it"),
            ("gh", "the guide offered to install it"), ("gitleaks", "the guide offered to install it"),
            ("gitleaks", "apt cannot find the package"), ("ps", "command not found")])
        self.assertEqual(got[0][2], "bash: line 1: curl: command not found")

    def test_fix_follows_the_screen_advice_only(self):
        # command-not-found's advice: the apt line, not the snap one
        f = flow.fix_for("Command 'curl' not found, but can be installed with:\nsudo snap install curl  # version 8\nsudo apt  install curl\n", set())
        self.assertEqual(f, ("the screen says: sudo apt  install curl", ["sudo apt-get install -y curl"], "advised"))
        # command-not-found for a person outside the sudo group: a bare apt line; "Please ask..." is not a command
        f = flow.fix_for("Command 'git' not found, but can be installed with:\napt install git\nPlease ask your administrator.\nbash: line 1: Please: command not found\n", set())
        self.assertEqual(f, ("the screen says: apt install git", ["sudo apt-get install -y git"], "advised"))
        # ade's own line: apt-get update first
        f = flow.fix_for("sudo apt-get install -y git failed (exit 100); when apt cannot find a package, run apt-get update first\n", set())
        self.assertEqual(f[1], ["sudo apt-get update"])
        # git identity, as ade names it
        f = flow.fix_for("git has no name and email yet: git config --global user.name and user.email\n", set())
        self.assertEqual(f[1][0], 'git config --global user.name "Drill Owner"')
        # no advice: the package a person would guess, marked unadvised
        f = flow.fix_for("bash: line 1: curl: command not found\n", set())
        self.assertEqual(f, ("no advice on the screen: curl: command not found", ["sudo apt-get install -y curl"], "unadvised"))
        self.assertEqual(flow.fix_for("bin/work: line 3: pgrep: command not found\n", set())[1], ["sudo apt-get install -y procps"])
        # ade's own prompt is not advice, a fix is never repeated, and nothing to fix is None
        self.assertIsNone(flow.fix_for("Install tmux now? This runs: sudo apt-get install -y tmux [y/N] n\n", set()))
        self.assertIsNone(flow.fix_for("bash: curl: command not found\n", {"sudo apt-get install -y curl"}))
        self.assertIsNone(flow.fix_for("all good\n", set()))


class Prompts(unittest.TestCase):
    RULES = flow.parse_rules("Install .*now\\? This runs: sudo apt-get install -y bat\tn\n"
                             "Install .*now\\?\ty\n"
                             "Geographic area:\t@pick:Etc\n"
                             "Press Enter when done\t~open a second terminal\t@second-terminal\t@enter\n"
                             "Press Enter when done\t~send your bot any message\t@message-the-bot\t@enter\n"
                             "What now\\?\t@stop\n")

    def test_answers_pick_by_screen_and_context(self):
        a = lambda line, ctx="": flow.answer_for(line, ctx, self.RULES)
        self.assertEqual(a("Install bat chafa now? This runs: sudo apt-get install -y bat chafa [y/N]"), ["n"])
        self.assertEqual(a("Install git tmux now? This runs: sudo apt-get install -y git tmux [y/N]"), ["y"])
        self.assertEqual(a("Geographic area:", "  1. Africa  2. America\n 11. Etc  12. Legacy\n"), ["11"])
        self.assertEqual(a("Press Enter when done (or type later):", "Your turn: open a second terminal window"), ["@second-terminal", "@enter"])
        self.assertEqual(a("Press Enter when done (or type later):", "in Telegram, send your bot any message."), ["@message-the-bot", "@enter"])
        self.assertIsNone(a("Press Enter when done (or type later):", "something new"))
        self.assertIsNone(a("Favourite colour:"))
        self.assertEqual(a("What now? [retry]:"), ["@stop"])

    def test_prompts_after_the_bot_token_are_findings(self):
        p = [{"question": "Install git now?"}, {"question": "Bot token (hidden; Enter skips):"},
             {"question": "Press Enter when done (or type later):"}, {"question": "/telegram:access pair <code> (typed in the second terminal)"}]
        flow.mark_phases(p)
        self.assertEqual([x["after_telegram"] for x in p], [False, False, True, True])


class Spawn(unittest.TestCase):
    def test_spawn_summary_checks_folders_reports_and_overlap(self):
        home = "/home/you"; names = ["svc-%d" % i for i in range(1, 6)]
        ups = {n: {"t": 100.0 + i, "cwd": "%s/Project/%s" % (home, n), "saw": 5} for i, n in enumerate(names)}
        reports = [(110.0 + i, "[%s] note: \"up in ~/Project/%s; 5 of 5 running together\"" % (n, n)) for i, n in enumerate(names)]
        s = flow.spawn_summary(names, ups, reports, home, 99.0)
        self.assertTrue(s["ok"], s["problems"]); self.assertEqual(s["all_up"], 5.0)
        ups["svc-2"]["cwd"] = home + "/hubs/h"; ups["svc-3"]["saw"] = 1; del ups["svc-5"]
        s = flow.spawn_summary(names, ups, reports[:3], home, 99.0)
        self.assertFalse(s["ok"]); self.assertIsNone(s["all_up"])
        text = " | ".join(s["problems"])
        for want in ("svc-2 runs in /home/you/hubs/h, not its own checkout", "svc-3 saw 1 of 5", "svc-5 never started", "svc-4: no report reached the chat"):
            self.assertIn(want, text)
        self.assertEqual(flow.peak([(1, 1000, 10), (2, 5000, 31), (3, 3000, 40)]), (5000, 40))


class Report(unittest.TestCase):
    def test_sudo_log_is_read_per_step(self):
        log = ("Nov 24 10:00:05 2026 : you : TTY=pts/1 ; PWD=/home/you ; USER=root ; COMMAND=/usr/bin/apt-get install -y curl\n"
               "Nov 24 10:01:00 2026 : you : TTY=unknown ; PWD=/home/you ; USER=root ; COMMAND=/usr/bin/cat /var/log/sudo-drill.log\n"
               "Nov 24 10:00:40 2026 : you : TTY=pts/2 ; PWD=/home/you ; USER=root ; COMMAND=/usr/bin/apt-get install -y git tmux\n")
        e = flow.parse_sudo(log)
        self.assertEqual([c for _, c in e], ["/usr/bin/apt-get install -y curl", "/usr/bin/apt-get install -y git tmux"])
        t0 = e[0][0]
        rows = flow.sudo_per_step(e, [("install", t0 - 5, t0 + 10), ("guide", t0 + 10, t0 + 60)])
        self.assertEqual(rows, [("install", "/usr/bin/apt-get install -y curl"), ("guide", "/usr/bin/apt-get install -y git tmux")])

    def test_report_lists_every_finding(self):
        steps = [("ok", "install", "ade 0.2.8", 3.0), ("FAIL", "spawn: five focus agents", "svc-5 never started", 60.0)]
        screens = [("01-install", "bash: line 1: curl: command not found\n", 1.0)]
        prompts = [{"screen": "guide", "question": "Install git now? [y/N]", "answer": "y", "after_telegram": False},
                   {"screen": "guide", "question": "Press Enter when done", "answer": "@enter", "after_telegram": True}]
        missing = [("curl", "command not found", "bash: line 1: curl: command not found", "install", "fixed: sudo apt-get install -y curl (no advice on the screen)")]
        fixes = [("install", "no advice on the screen: curl: command not found", "sudo apt-get install -y curl", "unadvised")]
        spawn = {"ok": False, "all_up": None, "problems": ["svc-5 never started"], "rows": [("svc-1", 1.0, "/home/you/Project/svc-1", 5, "[svc-1] up")]}
        r = flow.report("server", "ade 0.2.8", steps, screens, prompts, missing, fixes, [("install", "/usr/bin/apt-get install -y curl")],
                        spawn, (204800, 77), "Telegram: stand-in both ways")
        for want in ("# User-flow report: raw Ubuntu server", "| curl | command not found | install |", "fixed: sudo apt-get install -y curl",
                     "| guide | Press Enter when done | @enter | yes: terminal-only after Telegram |", "| install | `/usr/bin/apt-get install -y curl` |",
                     "| install | 3.0 |", "svc-5 never started", "200 MB", "| 77 |", "Telegram: stand-in both ways", "01-install", "| Terminal-only prompts after Telegram | 1 |"):
            self.assertIn(want, r)


class Relay(unittest.TestCase):
    def test_relay_sends_to_the_real_chat_and_never_polls(self):
        d = tempfile.mkdtemp(); up, me = os.path.join(d, "up"), os.path.join(d, "me")
        real, standin = "999:real-token-for-the-test", "123:stand-in"
        procs = []
        try:
            def start(state, token, owner, env):
                p = subprocess.Popen([sys.executable, os.path.join(G, "fakes", "botapi.py"), state, token, owner], env=env,
                                     stdout=subprocess.DEVNULL, stderr=open(os.path.join(d, os.path.basename(state) + ".err"), "w"))
                procs.append(p); end = time.time() + 10
                while not os.path.exists(os.path.join(state, "port")) and time.time() < end: time.sleep(0.05)
                return "http://127.0.0.1:" + open(os.path.join(state, "port")).read().strip()
            upstream = start(up, real, "777", dict(os.environ))   # plays the real Bot API
            env = dict(os.environ, DRILL_TG_RELAY_TOKEN=real, DRILL_TG_RELAY_CHAT="777", DRILL_TG_RELAY_API=upstream,
                       DRILL_TG_RELAY_MATCH=r"^\[svc-\d+\] note:", DRILL_TG_RELAY_MAX="2")
            api = start(me, standin, "42", env)
            def call(path, body):
                req = urllib.request.Request(api + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                return json.load(urllib.request.urlopen(req, timeout=10))
            call("/phone/say", {"text": "start 5 focus agents"})
            self.assertEqual(call("/bot%s/getUpdates" % standin, {"timeout": 0})["result"][0]["message"]["text"], "start 5 focus agents")
            # only what matches goes to the real chat, and at most the cap (a handful of messages a run)
            for text in ("Pairing required", "[svc-1] note: up", "[svc-2] idle: waiting", "[svc-2] note: up", "[svc-3] note: up"):
                self.assertTrue(call("/bot%s/sendMessage" % standin, {"chat_id": "42", "text": text})["ok"])
            got = [json.loads(l) for l in open(os.path.join(up, "sent.jsonl"))]
            self.assertEqual([(g["method"], g["chat_id"], g["text"]) for g in got], [("sendMessage", "777", "[svc-1] note: up"), ("sendMessage", "777", "[svc-2] note: up")])
            self.assertEqual([l.split()[0] for l in open(os.path.join(up, "methods.log"))], ["sendMessage"] * 2)   # never getUpdates
            mine = open(os.path.join(me, "sent.jsonl")).read()
            self.assertEqual(mine.count('"relayed": "ok"'), 2)
            self.assertIn('"relayed": "not relayed: over the cap"', mine)
            self.assertIn('"relayed": "not relayed: not a message the run sends for real"', mine)
            for f in os.listdir(me):
                p = os.path.join(me, f)
                if os.path.isfile(p): self.assertNotIn(real, open(p, errors="replace").read(), f)
            self.assertNotIn(real, open(os.path.join(d, "me.err")).read())
        finally:
            for p in procs: p.terminate(); p.wait()
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
