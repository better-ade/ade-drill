"""Tests of the raw-Ubuntu drill's recording mode (story D4, RAW_RECORD=1): what goes into the video and when. No Docker,
no network, no agg or ffmpeg: the rendering runs in CI's desktop job (drills/raw/record.sh)."""
import json, os, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "drills", "raw"))
import video  # noqa: E402

TOKEN = "123456789:" + "drill-stand-in-token-not-a-real-one_0"


class Redact(unittest.TestCase):
    def test_tokens_chat_ids_home_paths_and_emails_are_hidden(self):
        text = ("token %s ok\nchat 424242 and chat_id: -100987654321\n/home/alvin/hubs/x and /Users/someone/Project\n"
                "mail someone@example.invalid, git@github.com:x\n/telegram:access pair 3fa9c1\n") % TOKEN
        got = video.redact(text, known=("424242",))
        for bad in (TOKEN, "424242", "987654321", "/home/alvin", "/Users/someone", "someone@example.invalid", "git@github.com", "3fa9c1"):
            self.assertNotIn(bad, got)
        self.assertIn("~/hubs/x", got); self.assertIn("~/Project", got); self.assertIn("<token>", got)
        self.assertIn("<chat>", got); self.assertIn("<email>", got); self.assertIn("pair <code>", got)

    def test_what_is_not_secret_stays(self):
        text = "ade 0.2.8 installed in ~/.local/bin; open @BotFather; 127.0.0.1:8080; you@ubuntu\n"
        self.assertEqual(video.redact(text), text)

    def test_leaks_finds_what_redact_hides_and_nothing_in_clean_text(self):
        self.assertEqual(video.leaks("all fine: ~/hubs/drill-hub, <token>, <chat>"), [])
        found = video.leaks("x %s y /home/you z a@b.example 424242" % TOKEN, known=("424242",))
        self.assertEqual(sorted(found), ["a bot token", "a chat id", "a home path with a user name", "an email address"])
        # an escape sequence in between hides nothing
        self.assertEqual(video.leaks("\x1b[1m/home/\x1b[0myou"), ["a home path with a user name"])


class Events(unittest.TestCase):
    def test_output_is_cut_at_line_ends_so_nothing_secret_is_split(self):
        raw = b"one\r\ntw" + b"o\r\n/home/yo" + b"u/x\r\nlast"
        marks = [(10.0, 0), (10.5, 7), (11.0, 16), (12.0, len(raw))]
        got = video.line_events(raw, marks)
        self.assertEqual([round(t, 1) for t, _ in got], [0.5, 1.0, 2.0])
        self.assertEqual("".join(x for _, x in got), raw.decode())
        for _, x in got[:-1]: self.assertTrue(x.endswith("\n"))
        self.assertTrue(all("/home/yo" not in x or "/home/you" in x for _, x in got))

    def test_no_output_no_events(self):
        self.assertEqual(video.line_events(b"", [(1.0, 0)]), [])


class Plan(unittest.TestCase):
    def segs(self):
        return [{"kind": "card", "length": 4.0}, {"kind": "term", "length": 300.0}, {"kind": "term", "length": 0.2},
                {"kind": "chat", "length": 12.0}, {"kind": "term", "length": 40.0}]

    def test_the_whole_fits_the_budget_and_each_part_stays_readable(self):
        got = video.plan(self.segs(), 80.0)
        self.assertLessEqual(sum(d for _, d in got), 80.0 + 1e-6)
        self.assertEqual(got[0][0], 0.0)
        for (a, d), (b, _) in zip(got, got[1:]): self.assertAlmostEqual(a + d, b)
        for (_, d), s in zip(got, self.segs()): self.assertGreaterEqual(d, video.MIN_PART)
        self.assertEqual(got[0][1], 4.0)                # cards keep their length
        self.assertGreater(got[1][1], got[4][1])        # a longer screen still gets more time

    def test_a_short_run_is_not_stretched(self):
        got = video.plan([{"kind": "card", "length": 3.0}, {"kind": "term", "length": 5.0}], 80.0)
        self.assertEqual([d for _, d in got], [3.0, 5.0])


class Captions(unittest.TestCase):
    def test_the_caption_shows_exactly_where_the_stand_ins_are(self):
        segs = [{"standin": False}, {"standin": True}, {"standin": True}, {"standin": False}, {"standin": True}]
        times = [(0.0, 4.0), (4.0, 10.0), (14.0, 6.0), (20.0, 5.0), (25.0, 8.0)]
        self.assertEqual(video.captions(segs, times), [(4.0, 20.0), (25.0, 33.0)])

    def test_a_screen_is_a_stand_in_when_it_says_so(self):
        self.assertTrue(video.is_standin("term", "Opening your browser to sign in (stand-in: no browser, no account)..."))
        self.assertTrue(video.is_standin("term", "Claude Code (stand-in) with the Telegram plugin"))
        self.assertTrue(video.is_standin("team", ""))
        self.assertFalse(video.is_standin("term", "installed: tmux gh gitleaks"))
        self.assertFalse(video.is_standin("card", "Claude sign-in and the focus agents' work are stand-ins"))


class Chat(unittest.TestCase):
    def test_the_panel_shows_both_sides_and_the_latest_messages(self):
        rows = [{"who": "you", "text": "hello"}, {"who": "your bot", "text": "Paired! Say hi to Claude."}] + \
               [{"who": "your bot", "text": "note %d " % i + "word " * 30} for i in range(12)]
        frames = video.chat_frames(rows, 80, 24, footer="all four up 3.1 s after the message")
        self.assertEqual(len(frames), len(rows))
        for f in frames:
            lines = video.plain(f).split("\n")
            self.assertLessEqual(len(lines), 24); self.assertTrue(all(len(l) <= 80 for l in lines))
            self.assertIn("Telegram", lines[0])
            self.assertIn("all four up 3.1 s", f)
        self.assertIn("hello", video.plain(frames[0]))
        self.assertIn("note 11", video.plain(frames[-1])); self.assertNotIn("hello", video.plain(frames[-1]))  # scrolled
        first = [l for l in video.plain(frames[1]).split("\n") if "hello" in l][0]
        bot = [l for l in video.plain(frames[1]).split("\n") if "Paired" in l][0]
        self.assertGreater(first.index("hello"), bot.index("Paired"))   # the person's side is on the right


class Cast(unittest.TestCase):
    def test_a_recording_is_a_valid_cast_with_a_title_the_caption_times_and_no_secret(self):
        screens = [{"name": "install", "step": "install", "typed": "curl -fsSL https://x/install.sh | bash",
                    "raw": ("ok /tmp/ade-raw.x1/bin /home/you/.local/bin/ade\r\ntoken %s\r\n" % TOKEN).encode(), "marks": [(0.0, 0), (1.0, 30), (2.0, 200)]},
                   {"name": "guide", "step": "guide", "typed": "ade setup",
                    "raw": b"Opening your browser to sign in (stand-in: no browser, no account)...\r\nLogin successful.\r\n", "marks": [(5.0, 0), (6.0, 200)]}]
        phone = [{"who": "you", "text": "hello"}, {"who": "your bot", "text": "Paired!"}, {"who": "you", "text": "build a website"},
                 {"who": "your bot", "text": 'note: "architect: done"'}, {"who": "your bot", "text": "Done: build a website"}]
        cast, caps = video.recording(screens, phone, ask="build a website", known=("424242",), team="frontend and backend together: yes",
                                     subs=[("/tmp/ade-raw.x1", "<drill>")])
        lines = cast.strip().split("\n"); head = json.loads(lines[0])
        self.assertEqual((head["version"], head["width"], head["height"]), (2, 80, 25))   # the 25th row: the caption
        ev = [json.loads(l) for l in lines[1:]]
        self.assertTrue(all(e[1] == "o" for e in ev)); ts = [e[0] for e in ev]
        self.assertEqual(ts, sorted(ts)); self.assertLessEqual(ts[-1], video.BUDGET)
        text = video.plain("".join(e[2] for e in ev))
        self.assertIn(video.TITLE, text); self.assertIn("$ ade setup", text); self.assertIn("build a website", text)
        self.assertIn("Done: build a website", text); self.assertIn("frontend and backend together: yes", text)
        self.assertEqual(video.leaks(text, known=("424242",)), [])
        self.assertNotIn(TOKEN, cast); self.assertNotIn("ade-raw.x1", cast); self.assertIn("<drill>/bin", text)
        self.assertTrue(caps and all(b > a for a, b in caps))
        # the caption is on the guide (its sign-in is a stand-in) and on the team's chat, not on the title or the install
        first_term = next(e[0] for e in ev if "$ curl" in video.plain(e[2]))
        self.assertGreater(caps[0][0], first_term)
        done_at = next(e[0] for e in ev if "Done: build a website" in video.plain(e[2]))
        self.assertTrue(any(a <= done_at <= b for a, b in caps))
        # the caption is drawn on the 25th row exactly while it shows, and cleared elsewhere
        for t, _, x in ev:
            on = any(a <= t < b for a, b in caps)
            self.assertEqual(video.CAPTION in x, on, (t, x[:60]))
            self.assertIn("\x1b[25;1H", x)

    def test_the_title_and_the_caption_say_what_the_owner_asked(self):
        self.assertEqual(video.TITLE, "ADE on a fresh Ubuntu 24.04 desktop: recorded in CI")
        self.assertEqual(video.CAPTION, "Claude sign-in and the focus agents' work are stand-ins in this recording")


WORK = {"design": "# Architecture\n\nA one-page website.\n\n## Verification command\n\n`bash tests/verify.sh`\n",
        "log": ["dispatch: ade project add ~/Project/website --no-init --yes", "dispatch: bin/dispatch --list projects/website",
                "assign: architect: ade work --role architect --name website-architect projects/website",
                "assign: frontend: ade work --role builder --name website-frontend projects/website",
                "assign: backend: ade work --role builder --name website-backend projects/website",
                "assign: reviewer: ade work --role reviewer --name website-reviewer projects/website"],
        "files": [("index.html", "<!doctype html>\n<h1>Hello</h1>\n"), ("server.js", "Bun.serve({ port })\n")],
        "timing": "frontend 3.4-5.5 s, backend 3.6-5.7 s after the ask: together",
        "changes": [("git status --short", "?? docs/\n?? index.html\n?? server.js\n?? tests/"), ("git log --oneline", "1a2b3c4 website")],
        "review": {"cmd": "bash tests/verify.sh", "out": "green: index.html is there, /api/health answers ok", "result": "green"}}
PHONE = [{"who": "you", "text": "hello"}, {"who": "your bot", "text": "Paired!"}, {"who": "you", "text": "build a website"},
         {"who": "your bot", "text": 'note: "architect: done"'}, {"who": "your bot", "text": 'note: "reviewer: green"'},
         {"who": "your bot", "text": "Done: build a website"}]
SCREENS = [{"name": "install", "step": "install", "typed": "curl -fsSL https://x/install.sh | bash", "raw": b"installed\r\n", "marks": [(0.0, 0), (1.0, 11)]}]


class Stages(unittest.TestCase):
    def test_the_seven_stage_captions_are_short_plain_and_in_the_owners_order(self):
        caps = video.stage_captions("green", True)
        self.assertEqual(caps, ["Feature: asked on Telegram", "Design: the architect's note", "Tasks: dispatch, then roles assigned",
                                "Development: frontend and backend together", "Changes: new files, no PR",
                                "Review: verification run, green", "Ship: Done, last on Telegram"])
        for c in caps: self.assertTrue(2 <= len(c.split()) <= 6, c)

    def test_a_caption_says_what_happened_when_the_run_went_wrong(self):
        caps = video.stage_captions("red", False)
        self.assertEqual(caps[5], "Review: verification run, red"); self.assertEqual(caps[6], "Ship: not Done")

    def test_the_stages_come_in_order_each_with_its_caption_and_what_the_drill_made(self):
        cast, caps = video.recording(SCREENS, PHONE, ask="build a website", work=WORK)
        ev = [json.loads(l) for l in cast.strip().split("\n")[1:]]
        firsts = []
        for c in video.stage_captions("green", True):
            at = [i for i, e in enumerate(ev) if c in video.plain(e[2])]
            self.assertTrue(at, c); firsts.append(at[0])
        self.assertEqual(firsts, sorted(firsts))
        text = lambda c: video.plain("".join(e[2] for e in ev if c in video.plain(e[2])))
        self.assertIn("build a website", text("Feature:"))
        self.assertIn("## Verification command", text("Design:"))
        self.assertIn("bin/dispatch --list projects/website", text("Tasks:"))
        self.assertIn("--role builder --name website-frontend", text("Tasks:"))
        dev = text("Development:")
        both = [l for l in dev.split("\n") if "index.html" in l and "server.js" in l]
        self.assertTrue(both, "frontend and backend side by side"); self.assertIn("Bun.serve", dev); self.assertIn("together", dev)
        ch = text("Changes:")
        self.assertIn("$ git status --short", ch); self.assertIn("?? index.html", ch); self.assertIn("1a2b3c4 website", ch)
        self.assertNotRegex(ch.replace("no PR", ""), r"(?i)pull request|\bPR\b|merged")
        rv = text("Review:")
        self.assertIn("$ bash tests/verify.sh", rv); self.assertIn("green: index.html is there", rv)
        ship = [e for e in ev if "Ship:" in video.plain(e[2])]
        self.assertIn("Done: build a website", video.plain(ship[-1][2]))
        last = video.plain(ship[-1][2])
        self.assertGreater(last.index("Done: build a website"), last.index("reviewer: green"))   # Done last on the phone
        # every stage is the agents' stand-in work: the caption shows on each
        for t, _, x in ev:
            if any(c in video.plain(x) for c in video.stage_captions("green", True)): self.assertIn(video.CAPTION, x)
        self.assertLessEqual(ev[-1][0], video.BUDGET)

    def test_a_stage_with_nothing_from_the_run_is_left_out_not_made_up(self):
        work = dict(WORK, changes=[], design="")
        cast, _ = video.recording(SCREENS, PHONE, ask="build a website", work=work)
        text = video.plain(cast)
        self.assertNotIn("Changes:", text); self.assertNotIn("Design:", text)
        self.assertIn("Tasks: dispatch", text); self.assertIn("Ship: Done", text)


if __name__ == "__main__":
    unittest.main()
