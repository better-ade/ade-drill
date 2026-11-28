"""Tests of the `ade ui` tour (story D5): the step script, the clicks, the caption timing, what is real and what is a
stand-in, the redaction scan, the size and length limits and the repeatability. No tmux run, no ffmpeg, no network and
no ade-cli release: the drill itself (drills/ui-tour.sh) runs in CI by hand (workflow_dispatch)."""
import json, os, re, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "drills", "ui-tour"))
import tour  # noqa: E402

TOKEN = "123456789:" + "drill-stand-in-token-not-a-real-one_0"
CAPTIONS = ["One terminal, all your agents.", "Start another agent with a click.",
            "Each tab shows who is working and who needs you.", "Right click for everything a tab can do.",
            "Your PRD, architecture and stories, newest first.", "Read the plan while it is written.",
            "Open it in the browser, diagrams and all.", "Done means the tests pass."]


def cup(row, col): return "\x1b[%d;%dH" % (row, col)


BAR = cup(tour.ROWS, 1) + "\x1b[48;5;24m● 0 orchestrator #[x] ⟳ 1 projects/api ○ 2 projects/web ○ 3 projects/docs " \
      "[+ agent] [tickets] [files] [approve] [dash] [? keys]\x1b[K"


class FakeDriver:
    """a screen that shows what a step waits for some time after the action that makes it"""

    def __init__(self, speed=1.0, never=()):
        self.t = 0.0; self.speed = speed; self.never = set(never); self.sent = []; self.agents = []; self.refreshed = []
        self.shown = {"[+ agent]": 0.0, "projects/docs": 0.0, "projects/api": 0.0}
        self.after = {}   # what an action makes appear, and how long it takes

    def now(self): return self.t
    def pump(self, s): self.t += s

    def appear(self, text, delay):
        if text not in self.never: self.shown.setdefault(text, self.t + delay * self.speed)

    def find(self, text, where=None):
        if text.startswith("state:"):
            text = text[len("state:"):]
        at = self.shown.get(text)
        if at is None or at > self.t: return None
        return (tour.ROWS if where == "bar" else 10, 5 + len(text) % 7)

    def send(self, data):
        self.sent.append((self.t, data))
        if data.startswith("\x1b[<"):   # a click: the menu it opens, then what the next one starts
            for t in ("projects/billing", "builder", "preview its plan"): self.appear(t, 0.3)
            self.appear("Plan: api", 0.8); self.appear("Done. Tests pass.", 1.0)
        if data == "v": self.appear("PRD: team invoices", 0.6)
        if data == "F": self.appear("## Goals", 0.5)
        if data == "q": self.appear("PRD: team invoices", 0.3)

    def refresh(self): self.refreshed.append(self.t)

    def agent(self, name, what):
        self.agents.append((name, what))
        if what == "busy": self.appear("⟳|projects/api", 0.7)
        if what == "waiting": self.appear("?|projects/api", 0.7)
        if what == "write-prd": self.appear("## Billing rules", 1.2)
        if what == "tests": self.appear("Done. Tests pass.", 1.5)

    def state(self, folder, icon):
        at = self.shown.get(icon + "|" + folder)
        return at is not None and at <= self.t

    def browser(self): self.t += 0.8 * self.speed; return True


class TourRuns(unittest.TestCase):
    def test_tour_runs_the_eight_steps_in_the_owners_words(self):
        self.assertEqual([s["n"] for s in tour.STEPS], list(range(1, 9)))
        self.assertEqual([s["caption"] for s in tour.STEPS], CAPTIONS)
        for s in tour.STEPS:
            self.assertTrue(s["do"], s["n"]); ats = [a[0] for a in s["do"]]
            self.assertEqual(ats, sorted(ats)); self.assertLess(ats[-1], s["slot"])
        verbs = [a[1] for s in tour.STEPS for a in s["do"]]
        self.assertIn("click", verbs); self.assertIn("rclick", verbs); self.assertIn("prefix", verbs)
        self.assertEqual([a[1:] for a in tour.STEPS[1]["do"] if a[1] == "click"][0], ("click", "[+ agent]", "bar"))
        self.assertEqual([a for a in tour.STEPS[3]["do"] if a[1] == "rclick"][0][2:], ("projects/api", "bar"))
        self.assertEqual([a[2] for a in tour.STEPS[4]["do"] if a[1] == "prefix"], ["v"])

    def test_tour_runs_clicks_as_mouse_events_at_the_cells(self):
        self.assertEqual(tour.mouse(12, 36), ["\x1b[<0;12;36M", "\x1b[<0;12;36m"])
        self.assertEqual(tour.mouse(3, 4, right=True), ["\x1b[<2;3;4M", "\x1b[<2;3;4m"])
        s = tour.Screen(); s.feed("\x1b[2J" + cup(3, 1) + "hello" + BAR)
        row, col = s.find("[+ agent]", "bar")
        self.assertEqual(row, tour.ROWS)
        self.assertEqual(s.row(row)[col - 1:col - 1 + 9], "[+ agent]")
        self.assertEqual(s.find("projects/api", "bar")[0], tour.ROWS)
        self.assertIsNone(s.find("hello", "bar")); self.assertEqual(s.find("hello"), (3, 1))

    def test_tour_runs_on_a_screen_model_of_what_tmux_draws(self):
        s = tour.Screen(cols=20, rows=5)
        s.feed("\x1b[2J" + cup(1, 1) + "abc\x1b[1mdef\x1b[0m" + cup(2, 3) + "x\x1b[3Cy" + cup(3, 1) + "line\r\nnext")
        self.assertEqual(s.row(1).rstrip(), "abcdef"); self.assertEqual(s.row(2).rstrip(), "  x   y")
        self.assertEqual(s.row(4).rstrip(), "next")
        s.feed(cup(1, 4) + "\x1b[K"); self.assertEqual(s.row(1).rstrip(), "abc")
        s.feed(cup(4, 1) + "a menu item"); self.assertEqual(s.find("menu item", "menu"), (4, 3))
        s.feed(cup(5, 1) + "the bar"); self.assertIsNone(s.find("the bar", "menu")); self.assertEqual(s.find("the bar", "bar"), (5, 1))
        # a menu drawn later over the same cells: the newest is what is found
        s.feed(cup(2, 1) + "preview its plan"); self.assertEqual(s.find("preview its plan"), (2, 1))
        s.feed("\x1b]0;a title with a host name\x07"); self.assertNotIn("title", "".join(s.row(r) for r in range(1, 6)))
        s.feed("\x1b[2J"); self.assertEqual("".join(s.row(r) for r in range(1, 6)).strip(), "")

    def test_tour_runs_the_steps_against_a_driver_in_order(self):
        d = FakeDriver(); rec = tour.Tour(d).run()
        self.assertEqual([s["n"] for s in rec["steps"]], list(range(1, 9)))
        self.assertEqual(d.agents, [("api", "busy"), ("api", "waiting"), ("docs", "write-prd"), ("api", "tests")])
        clicks = [c for s in rec["steps"] for c in s["clicks"]]
        self.assertEqual([c[3] for c in clicks][:4], ["[+ agent]", "projects/billing", "builder", "projects/api"])
        self.assertTrue(any(x.startswith("\x1b[<2;") for _, x in d.sent), "a right click")
        for s, plan in zip(rec["steps"], tour.STEPS):
            self.assertEqual([a[0] for a in s["anchors"]], [a[0] for a in plan["do"]])
            self.assertGreaterEqual(s["end"] - s["start"], plan["slot"] - 1e-6)
        self.assertEqual(len(d.refreshed), len(clicks))   # each pointer goes when the screen is redrawn

    def test_tour_runs_fails_naming_the_step_and_what_never_came(self):
        d = FakeDriver(never=("## Billing rules",))
        with self.assertRaises(tour.TourFailed) as e: tour.Tour(d, timeout=5).run()
        self.assertIn("step 6", str(e.exception)); self.assertIn("## Billing rules", str(e.exception))

    def test_tour_runs_a_released_ade_cli_pinned_in_one_place(self):
        pins = open(os.path.join(ROOT, "drills", "pins.sh")).read()
        m = re.search(r'^ADE_UI_TOUR_REF="\$\{ADE_UI_TOUR_REF:-(v[0-9.]+)\}"(.*)$', pins, re.M)
        self.assertTrue(m, "drills/pins.sh names the ade-cli release the tour drives, overridable")
        self.assertIn("PLACEHOLDER", m.group(2))   # the next release, not a tag yet: said where it is set
        sh = os.path.join(ROOT, "drills", "ui-tour.sh")
        got = subprocess.run(["bash", sh, "--pin"], capture_output=True, text=True, env=dict(os.environ, ADE_UI_TOUR_REF=""))
        self.assertEqual(got.stdout.strip(), m.group(1))
        got = subprocess.run(["bash", sh, "--pin"], capture_output=True, text=True, env=dict(os.environ, ADE_UI_TOUR_REF="v9.9.9"))
        self.assertEqual(got.stdout.strip(), "v9.9.9")
        for f in ("ui-tour.sh", "ui-tour/run.py", "ui-tour/tour.py"):
            self.assertNotRegex(open(os.path.join(ROOT, "drills", f)).read(), r"v0\.\d+\.\d+", f + " names no ade-cli version")


def fake_record(speed=1.0):
    """a recording as the driver makes it: the client's output with the times it came, and the steps"""
    d = FakeDriver(speed=speed); rec = tour.Tour(d).run()
    raw, marks = "", [(0.0, 0)]
    def out(t, text):
        nonlocal raw; raw += text; marks.append((t, len(raw.encode())))
    out(0.05, "\x1b[2J" + BAR)
    for s in rec["steps"]:
        for t, _, _, text in s["clicks"]: out(t + 0.1, cup(5, 1) + "after " + text); out(t + tour.POINTER_HOLD + 0.05, cup(1, 1) + "redrawn")
        out(s["start"] + 0.5, cup(8, 1) + "step %d on screen" % s["n"])
    return rec, raw.encode(), marks


class TourVideo(unittest.TestCase):
    def test_tour_video_has_the_size_and_length_the_story_asks(self):
        self.assertEqual((tour.WIDTH, tour.HEIGHT), (1280, 720))
        total = sum(s["slot"] for s in tour.STEPS) + tour.LAST_FRAME
        self.assertTrue(30 <= total <= 60, total)
        self.assertGreaterEqual(tour.COLS, 100)   # U5's full button row needs 100 columns

    def test_tour_video_captions_are_timed_to_their_steps(self):
        tl = tour.timeline()
        self.assertEqual(len(tl), 8); self.assertEqual(tl[0][0], 0.0)
        for (a, b), (c, _), s in zip(tl, tl[1:] + [(None, None)], tour.STEPS):
            self.assertAlmostEqual(b - a, s["slot"])
            if c is not None: self.assertAlmostEqual(b, c)
        vtt = tour.vtt()
        self.assertTrue(vtt.startswith("WEBVTT\n\n"))
        cues = re.findall(r"(\d\d:\d\d\.\d\d\d) --> (\d\d:\d\d\.\d\d\d)\n(.+)\n", vtt)
        self.assertEqual([c[2] for c in cues], CAPTIONS)
        self.assertEqual(cues[0][0], "00:00.000"); self.assertEqual(cues[1][0], tour.stamp(tl[1][0]))
        self.assertEqual(cues[-1][1], tour.stamp(tl[-1][1] + tour.LAST_FRAME))   # the last caption stays to the end

    def test_tour_video_a_cast_of_the_client_with_the_pointer_where_each_click_lands(self):
        rec, raw, marks = fake_record()
        cast, facts = tour.build(rec, raw, marks)
        lines = cast.strip().split("\n"); head = json.loads(lines[0])
        self.assertEqual((head["version"], head["width"], head["height"]), (2, tour.COLS, tour.ROWS))
        ev = [json.loads(l) for l in lines[1:]]
        ts = [e[0] for e in ev]; self.assertEqual(ts, sorted(ts))
        self.assertLessEqual(ts[-1], sum(s["slot"] for s in tour.STEPS))
        first = [c for s in rec["steps"] for c in s["clicks"]][0]
        ptr = tour.pointer(first[1], first[2], first[3])
        at = [e[0] for e in ev if ptr in e[2]]
        self.assertTrue(at, "the pointer is drawn at the first click's cell")
        self.assertIn("\x1b[%d;%dH" % (first[1], first[2]), ptr)
        self.assertAlmostEqual(at[0], facts["clicks"][0][0], places=3)
        redrawn = [e for e in ev if "redrawn" in e[2]]
        self.assertTrue(redrawn and ptr not in redrawn[0][2], "the pointer goes once the screen is redrawn")
        self.assertEqual(len(facts["clicks"]), sum(len(s["clicks"]) for s in rec["steps"]))

    def test_tour_video_the_browser_shows_in_step_7_only(self):
        rec, raw, marks = fake_record(); _, facts = tour.build(rec, raw, marks)
        a, b = facts["overlay"]; s7 = tour.timeline()[6]
        self.assertTrue(s7[0] < a < b <= s7[1] + 1e-6, (a, b, s7))

    def test_tour_video_limits(self):
        good = {"duration": 49.0, "size": 3 * 1024 * 1024, "codec": "h264", "width": 1280, "height": 720}
        self.assertEqual(tour.limits(good), [])
        for bad, word in ((dict(good, duration=61.0), "60"), (dict(good, duration=29.0), "30"),
                          (dict(good, size=8 * 1024 * 1024), "8 MB"), (dict(good, codec="hevc"), "H.264"),
                          (dict(good, width=1920, height=1080), "1280x720")):
            got = tour.limits(bad); self.assertEqual(len(got), 1, got); self.assertIn(word, got[0])

    def test_tour_video_rendered_by_the_d4_recorder_at_1280x720_with_the_browser_on_top(self):
        with tempfile.TemporaryDirectory() as d:
            fakes = os.path.join(d, "fakes"); os.makedirs(fakes); log = os.path.join(d, "ffmpeg.log")
            def tool(name, body):
                p = os.path.join(fakes, name); open(p, "w").write("#!/bin/bash\n" + body + "\n"); os.chmod(p, 0o755)
            tool("agg", 'for a; do last="$a"; done; : > "$last"')
            tool("ffmpeg", 'echo "$*" >> %s; for a; do last="$a"; done; : > "$last"' % log)
            tool("ffprobe", 'case "$*" in *format=duration*) echo 49.0 ;; *) echo h264,1280,720,490 ;; esac')
            out = os.path.join(d, "out"); os.makedirs(out); open(os.path.join(out, "ade-ui-tour.cast"), "w").write("{}\n")
            open(os.path.join(out, "docs-page.png"), "w").write("png")
            env = dict(os.environ, PATH=fakes + ":" + os.environ["PATH"], AGG=os.path.join(fakes, "agg"), REC_NAME="ade-ui-tour",
                       REC_SIZE="1280x720", REC_POSTER_AT="3", REC_OVERLAY=os.path.join(out, "docs-page.png"), REC_OVERLAY_AT="30.4,36.5")
            got = subprocess.run(["bash", os.path.join(ROOT, "drills", "raw", "record.sh"), out], capture_output=True, text=True, env=env)
            self.assertEqual(got.returncode, 0, got.stderr)
            for f in ("ade-ui-tour.mp4", "ade-ui-tour.png"): self.assertTrue(os.path.exists(os.path.join(out, f)), f)
            calls = open(log).read()
            self.assertIn("scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720", calls)
            self.assertIn("enable='between(t,30.4,36.5)'", calls); self.assertIn("-ss 3", calls); self.assertIn("libx264", calls)
            # D4's own call is as before: its names, no size, no overlay
            open(log, "w").close(); open(os.path.join(out, "ade-d4.cast"), "w").write("{}\n")
            env = {k: v for k, v in env.items() if not k.startswith("REC_")}
            got = subprocess.run(["bash", os.path.join(ROOT, "drills", "raw", "record.sh"), out], capture_output=True, text=True, env=env)
            self.assertEqual(got.returncode, 0, got.stderr)
            calls = open(log).read()
            self.assertIn("ade-d4.mp4", calls); self.assertIn("-ss 2.5", calls)
            self.assertNotIn("1280:720", calls); self.assertNotIn("overlay", calls)

    def test_tour_video_ci_runs_it_by_hand_and_attaches_all_four(self):
        ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml")).read()
        job = ci[ci.index("\n  ui-tour:"):]
        nxt = re.search(r"\n  [a-z][a-z0-9-]*:\n", job[1:]); job = job[:nxt.start() + 1] if nxt else job
        self.assertIn("if: github.event_name == 'workflow_dispatch'", job)
        self.assertIn("bash drills/ui-tour.sh", job); self.assertIn("name: ade-ui-tour", job)
        for f in ("ade-ui-tour.mp4", "ade-ui-tour.png", "ade-ui-tour.vtt", "ade-ui-tour.json"): self.assertIn(f, job)
        self.assertNotIn("secrets.", job)
        nightly = open(os.path.join(ROOT, ".github", "workflows", "nightly.yml")).read()
        self.assertNotIn("ui-tour", nightly)
        self.assertNotIn("ui-tour", open(os.path.join(ROOT, "drills", "matrix.json")).read())


class TourHonest(unittest.TestCase):
    def test_tour_honest_says_what_is_real_and_what_is_a_stand_in(self):
        m = tour.manifest(pin="v9.9.9", facts={"overlay": [30.0, 36.0], "clicks": []}, versions={"ade": "ade 9.9.9", "tmux": "tmux 3.4"})
        json.dumps(m)
        self.assertEqual(m["ade_cli"]["ref"], "v9.9.9")
        self.assertEqual([s["caption"] for s in m["steps"]], CAPTIONS)
        real = " ".join(m["real"]); fake = " ".join(s["what"] for s in m["standins"])
        for w in ("ade ui", "tmux", "clicks", "ade web"): self.assertIn(w, real)
        for w in ("Claude", "sign-in", "agents' work"): self.assertIn(w, fake)
        self.assertTrue(all(s.get("why") for s in m["standins"]))
        self.assertIn("stand-in", m["caption"]); self.assertIn("agents' work", m["caption"]); self.assertIn("sign-in", m["caption"])

    def test_tour_honest_the_scan_finds_what_must_never_show(self):
        known = ("build-host-7", "someone")
        self.assertEqual(tour.scan("ade ui: ~/hubs/tour, <token>, projects/api", known), [])
        got = tour.scan("x %s /home/someone/hubs a@b.example build-host-7 \x1b[1mbuild-host\x1b[0m-7" % TOKEN, known)
        self.assertEqual(sorted(got), ["a bot token", "a home path with a user name", "a host or user name", "an email address"])
        self.assertEqual(tour.scan("someones and build-host-77", known), [])    # whole names only
        self.assertEqual(tour.scan("\x1b]0;build-host-7\x07ok", known), [])      # a terminal title is never in a frame

    def test_tour_honest_a_cast_that_would_show_a_secret_is_refused(self):
        rec, raw, marks = fake_record()
        # the redaction works on what tmux wrote, chunk by chunk: an address drawn in two writes is only seen on the screen
        raw += (cup(9, 1) + "mail owner@exa").encode(); marks.append((marks[-1][0] + 0.1, len(raw)))
        raw += (cup(9, 15) + "mple.invalid").encode(); marks.append((marks[-1][0] + 0.1, len(raw)))
        with self.assertRaises(ValueError) as e: tour.build(rec, raw, marks)
        self.assertIn("email", str(e.exception))
        # in one write, the D4 redaction hides it
        rec, raw, marks = fake_record()
        raw += (cup(9, 1) + "mail owner@example.invalid").encode(); marks.append((marks[-1][0] + 0.1, len(raw)))
        cast, _ = tour.build(rec, raw, marks); self.assertNotIn("owner@", cast); self.assertIn("<email>", cast)

    def test_tour_honest_the_drills_folders_are_put_away_before_the_scan(self):
        rec, raw, marks = fake_record()
        raw += (cup(9, 1) + "Claude Code (stand-in): a session in /tmp/adt.x1/h/hubs/tour/projects/api").encode(); marks.append((marks[-1][0] + 0.1, len(raw)))
        cast, _ = tour.build(rec, raw, marks, subs=[("/tmp/adt.x1/h", "~")], known=("adt",))
        self.assertNotIn("adt.x1", cast); self.assertIn("~/hubs/tour/projects/api", cast)


class TourRepeatable(unittest.TestCase):
    def test_tour_repeatable_real_times_are_fitted_to_the_planned_ones(self):
        anchors = [(0.6, 1.0), (4.0, 2.0)]
        self.assertAlmostEqual(tour.warp(0.0, anchors, 10.0, 6.0), 0.0)
        self.assertAlmostEqual(tour.warp(0.6, anchors, 10.0, 6.0), 1.0)
        self.assertAlmostEqual(tour.warp(2.3, anchors, 10.0, 6.0), 1.5)
        self.assertAlmostEqual(tour.warp(4.0, anchors, 10.0, 6.0), 2.0)
        self.assertAlmostEqual(tour.warp(10.0, anchors, 10.0, 6.0), 6.0)
        self.assertAlmostEqual(tour.warp(99.0, anchors, 10.0, 6.0), 6.0)
        xs = [tour.warp(x / 10, anchors, 10.0, 6.0) for x in range(0, 101)]
        self.assertEqual(xs, sorted(xs))

    def test_tour_repeatable_two_runs_at_different_speeds_give_the_same_video_timings(self):
        a = tour.manifest("v9.9.9", tour.build(*fake_record(1.0))[1], {})
        b = tour.manifest("v9.9.9", tour.build(*fake_record(2.5))[1], {})
        self.assertEqual(tour.same(a, b), [])
        for (x, _), (y, _) in zip(a["clicks"], b["clicks"]): self.assertLessEqual(abs(x - y), 0.5)

    def test_tour_repeatable_a_difference_is_named(self):
        a = tour.manifest("v9.9.9", tour.build(*fake_record())[1], {})
        self.assertEqual(tour.same(a, json.loads(json.dumps(a))), [])
        b = json.loads(json.dumps(a)); b["steps"][2]["from"] += 0.4; b["steps"][2]["to"] += 0.4
        self.assertEqual(tour.same(a, b), [])
        b["steps"][2]["from"] += 0.2; self.assertIn("step 3", " ".join(tour.same(a, b)))
        b = json.loads(json.dumps(a)); b["steps"][4]["caption"] = "something else"; self.assertIn("caption", " ".join(tour.same(a, b)))
        b = json.loads(json.dumps(a)); b["steps"].pop(); self.assertIn("8 steps", " ".join(tour.same(a, b)))
        b = json.loads(json.dumps(a)); b["clicks"][0][0] += 0.7; self.assertIn("click 1", " ".join(tour.same(a, b)))
        b = json.loads(json.dumps(a)); b["overlay"][0] += 0.7; self.assertIn("browser", " ".join(tour.same(a, b)))


if __name__ == "__main__":
    unittest.main()
