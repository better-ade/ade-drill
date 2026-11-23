"""Tests of the golden-path drill's own parts (story D3). No network, no account: the drill itself is the end-to-end run."""
import json, os, shutil, subprocess, sys, tempfile, time, unittest, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = os.path.join(ROOT, "drills", "golden")
sys.path.insert(0, G)
import screens  # noqa: E402

TOKEN = "123456789:test-stand-in-token"


class Screens(unittest.TestCase):
    def test_clean_replaces_what_differs_between_runs(self):
        raw = b"\x1b[1mok\x1b[0m  ade 0.2.7\r\nsynced: db20b70 sync 2026-11-23 14:06\r\nanthropic: ready (3s)\r\n/tmp/w/home/hubs/x pid 4711 \r\n"
        t = screens.clean(screens.plain(raw), [("/tmp/w/home", "/Users/you")])
        self.assertEqual(t, "ok  ade <version>\nsynced: <commit> sync <date> <time>\nanthropic: ready (Ns)\n/Users/you/hubs/x pid <pid>\n")

    def test_split_guide_names_each_step_and_the_end(self):
        text = "header\n  [ ] 1. Claude Code\nStep 1 of 6: Claude Code\na\nStep 6 of 6: Telegram (optional)\nb\n\nAll set: your hub\nnext: type ade\n"
        self.assertEqual([n for n, _ in screens.split_guide(text)], ["guide-0-start", "guide-1-claude-code", "guide-6-telegram-optional", "guide-9-end"])
        self.assertIn("All set", screens.split_guide(text)[-1][1])

    def test_questions_with_their_defaults(self):
        q = screens.questions_of("Install it now? [y/N] y\nSet up now? [Y/n] \nKind of teammate (1-13): 1\nHow do you use Claude? [account]: \nBot token (hidden; Enter skips): \nPress Enter when done (or type later): \n")
        self.assertEqual([(d, k) for _, d, k in q], [("no", "yes/no"), ("yes", "yes/no"), ("", "pick one of 13"), ("account", "choice"), ("", "hidden text"), ("", "Enter")])

    def test_compare_fails_on_a_change_of_wording_until_updated(self):
        d = tempfile.mkdtemp(); out, gold = os.path.join(d, "out"), os.path.join(d, "gold"); os.makedirs(out)
        try:
            with open(os.path.join(out, "01-a.txt"), "w") as f: f.write("Your hub is ready\n")
            self.assertEqual(screens.compare(out, gold, True), [])            # written on purpose
            self.assertEqual(screens.compare(out, gold, False), [])           # the same wording
            with open(os.path.join(out, "01-a.txt"), "w") as f: f.write("Your hub is set\n")
            bad = screens.compare(out, gold, False)
            self.assertEqual(len(bad), 1); self.assertIn("01-a.txt", bad[0]); self.assertTrue(os.path.isfile(os.path.join(out, "01-a.diff")))
            with open(os.path.join(out, "02-b.txt"), "w") as f: f.write("new\n")
            self.assertEqual(len(screens.compare(out, gold, False)), 2)       # a screen the golden files do not have
        finally: shutil.rmtree(d)

    def test_report_lists_what_to_polish(self):
        scr = [("01-guide", "Welcome to your hub\nYour turn: open a second terminal window and type:\n  /telegram:access policy allowlist\n" + "x" * 81 + "\nTraceback (most recent call last)\nInstall it now? [y/N] y\n", 2.0),
               ("02-phone", "your bot: " + "y" * 200 + "\n", None)]
        r = screens.report("macos", "ade 0.0.0", [("ok", "install", "", 1.0), ("pending", "pairing", "G4: not built", None)], scr, ["hub", "allowlist"], [])
        for want in ("| Questions asked | 1 |", "open a second terminal", "type a slash command", "| hub | 01-guide |", "| allowlist | 01-guide |",
                     "| 01-guide | 81 |", "Traceback", "- **pairing**: G4: not built", "| Install it now? | no | yes/no |"):
            self.assertIn(want, r)
        self.assertNotIn("| 02-phone | 2", r)   # what the phone shows is not held to 80 columns


class StandIns(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def call(self, api, path, data=None, ctype="application/json"):
        req = urllib.request.Request(api + path, data=data, headers={"Content-Type": ctype} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r: return r.status, json.load(r)
        except urllib.error.HTTPError as e: return e.code, json.load(e)

    def test_bot_api_and_phone(self):
        p = subprocess.Popen([sys.executable, os.path.join(G, "fakes", "botapi.py"), self.d, TOKEN, "42"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            end = time.time() + 10
            while not os.path.exists(os.path.join(self.d, "port")) and time.time() < end: time.sleep(0.05)
            api = "http://127.0.0.1:" + open(os.path.join(self.d, "port")).read().strip(); bot = "/bot" + TOKEN
            self.assertEqual(self.call(api, "/botwrong/getUpdates")[0], 401)   # another token is refused, as Telegram does
            self.call(api, "/phone/say", json.dumps({"text": "fix X"}).encode())
            up = self.call(api, bot + "/getUpdates?timeout=0")[1]["result"]
            self.assertEqual((up[0]["message"]["text"], up[0]["message"]["from"]["id"]), ("fix X", 42))
            self.assertEqual(self.call(api, bot + "/getUpdates?timeout=0&offset=%d" % (up[0]["update_id"] + 1))[1]["result"], [])   # confirmed
            self.call(api, bot + "/sendMessage", json.dumps({"chat_id": "42", "text": "Done"}).encode())
            png = b"\x89PNG\r\n\x1a\n" + b"0" * 600
            body = b'--B\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n42\r\n--B\r\nContent-Disposition: form-data; name="caption"\r\n\r\nproof\r\n' \
                   b'--B\r\nContent-Disposition: form-data; name="photo"; filename="a.png"\r\nContent-Type: image/png\r\n\r\n' + png + b"\r\n--B--\r\n"
            self.assertTrue(self.call(api, bot + "/sendPhoto", body, "multipart/form-data; boundary=B")[1]["ok"])
            sent = [json.loads(l) for l in open(os.path.join(self.d, "sent.jsonl"))]
            self.assertEqual((sent[0]["method"], sent[0]["text"]), ("sendMessage", "Done"))
            self.assertEqual((sent[1]["method"], sent[1]["png"], sent[1]["bytes"], sent[1]["caption"]), ("sendPhoto", True, len(png), "proof"))
            who = [json.loads(l)["who"] for l in open(os.path.join(self.d, "phone.jsonl"))]
            self.assertEqual(who, ["you", "your bot", "your bot"])
        finally: p.terminate(); p.wait()

    def test_guard_fails_and_records_a_call(self):
        log = os.path.join(self.d, "guard.log"); link = os.path.join(self.d, "security"); os.symlink(os.path.join(G, "fakes", "guard"), link)
        p = subprocess.run([link, "find-generic-password", "-s", "x"], env={"DRILL_GUARD": log, "PATH": "/usr/bin:/bin"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 97); self.assertEqual(open(log).read().strip(), "security find-generic-password -s x")

    def test_gh_stand_in_refuses_a_call_it_does_not_know(self):
        env = {"DRILL_GH": os.path.join(self.d, "gh"), "PATH": "/usr/bin:/bin"}
        p = subprocess.run([os.path.join(G, "fakes", "gh"), "auth", "token"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 1); self.assertEqual(p.stdout, b"")
        self.assertNotEqual(subprocess.run([os.path.join(G, "fakes", "gh"), "auth", "status"], env=env).returncode, 0)   # not signed in yet

    def test_claude_stand_in_signs_in_only_after_auth_login(self):
        env = {"HOME": self.d, "PATH": os.environ["PATH"]}; c = [sys.executable, os.path.join(G, "fakes", "claude")]
        self.assertEqual(subprocess.run(c + ["auth", "status"], env=env).returncode, 1)
        self.assertEqual(subprocess.run(c + ["auth", "login"], env=env, stdout=subprocess.DEVNULL).returncode, 0)
        self.assertEqual(subprocess.run(c + ["auth", "status"], env=env).returncode, 0)
        out = subprocess.run(c + ["-p"], env=env, input=b"Reply with the word READY and nothing else.\n", stdout=subprocess.PIPE).stdout
        self.assertEqual(out.strip(), b"READY")


class Fixture(unittest.TestCase):
    def test_fails_before_the_fix_and_passes_after_it(self):
        d = tempfile.mkdtemp(); repo = os.path.join(d, "calc")
        try:
            shutil.copytree(os.path.join(G, "fixture"), repo, ignore=shutil.ignore_patterns("__pycache__")); cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
            self.assertNotEqual(subprocess.run(cmd, cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode, 0)
            env = dict(os.environ, DRILL_STATE=d, DRILL_MODEL=os.path.join(G, "model"))
            p = subprocess.run(["bash", os.path.join(G, "model", "builder.sh")], cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertEqual(open(os.path.join(d, "focus-done")).read().strip(), "pass: python3 -m unittest discover -s tests")
            self.assertIn("OK", open(os.path.join(d, "review.txt")).read())
        finally: shutil.rmtree(d)


class Golden(unittest.TestCase):
    def test_every_target_has_its_transcripts_and_they_are_clean(self):
        for target in ("macos", "linux", "computer"):
            d = os.path.join(G, "transcripts", target); names = sorted(os.listdir(d))
            self.assertTrue(any("guide-4-your-hub" in n for n in names) and any("phone" in n for n in names), target)
            for n in names:
                t = open(os.path.join(d, n)).read()
                self.assertNotIn("\x1b", t, n); self.assertNotIn("ade-golden.", t, n); self.assertNotIn("stand-in-token", t, n)

    def test_pending_steps_name_a_story_the_drill_story_lists(self):
        story = open(os.path.join(ROOT, "docs", "stories", "D3-golden-path-drill.md")).read()
        src = open(os.path.join(G, "run.py")).read()
        import re
        refs = set(re.findall(r'"((?:G\d+|A\d+)) \(', src))
        self.assertTrue(refs)
        for r in refs: self.assertIn(r, story, "%s is pending in the drill and not in the story" % r)


if __name__ == "__main__":
    unittest.main()
