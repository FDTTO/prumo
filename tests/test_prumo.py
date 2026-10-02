"""Prumo's own checks: the command line, a real browser and a fixture site.

Each guard is checked both ways: what it must stop, and what it must let
through. A tool that verifies others has to prove first that it can fail.

    python -m unittest discover -s tests -v
"""
import functools
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PRUMO = os.path.dirname(HERE)
FIXTURE = os.path.join(HERE, "fixture")


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class PrumoTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.profiles_before = set(glob.glob(os.path.join(tempfile.gettempdir(), "prumo-profile-*")))
        cls.work = tempfile.mkdtemp(prefix="prumo-test-")
        shutil.copytree(FIXTURE, cls.work, dirs_exist_ok=True)
        cls.site = os.path.join(cls.work, "site")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=cls.site))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.config = cls.write_config("prumo.json", "harness.html")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.work, ignore_errors=True)

    @classmethod
    def write_config(cls, name, harness):
        path = os.path.join(cls.work, name)
        with open(path, "w", encoding="utf-8") as target:
            json.dump({
                "base": cls.base,
                "publish": {"dir": "site", "url": "/"},
                "harness": harness,
                "mirror": "/index.html",
                "scenarios": "scenarios",
                "fidelity": {"states": "fidelity/states", "roles": "fidelity/roles.js", "viewport": [800, 600]},
            }, target)
        return path

    def prumo(self, *args, config=None):
        done = subprocess.run([sys.executable, PRUMO, "--config", config or self.config] + list(args),
                              capture_output=True, text=True, encoding="utf-8")
        return done.returncode, done.stdout + done.stderr

    def test_a_passing_suite_passes(self):
        code, out = self.prumo("suite")
        self.assertEqual(code, 0, out)
        self.assertIn("PASS saves", out)
        self.assertIn("375px", out)
        self.assertIn("PASS focus", out)
        self.assertIn("PASS allowed", out)

    def test_each_kind_of_failure_fails_and_says_why(self):
        code, out = self.prumo("suite", os.path.join(self.work, "failing"))
        self.assertEqual(code, 1, out)
        self.assertNotIn("PASS", out)
        self.assertIn("FAIL one and one make three  -> 2", out)
        self.assertIn("no done()", out)
        self.assertIn("error: something broke", out)
        self.assertIn("timed out waiting for: function () { return !!document.querySelector('#never-there'); }", out)

    def test_coverage_names_what_no_scenario_reached_and_only_that(self):
        code, out = self.prumo("suite", "--coverage", "--only", "saves")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"app\.css:3 +\.never")
        self.assertRegex(out, r"app\.js:\d+ +never")
        self.assertNotRegex(out, r"app\.css:\d+ +\.status")
        self.assertNotRegex(out, r"app\.js:\d+ +save\b")
        self.assertNotIn("prumo-", out)

    def test_mutation_kills_what_a_check_depends_on_and_spares_what_none_does(self):
        self.prumo("suite", "--coverage", "--only", "saves")
        code, out = self.prumo("mutate", "--only", "save,decorate")
        self.assertRegex(out, r"KILLED +app\.js:save")
        self.assertRegex(out, r"SURVIVED +app\.js:decorate")
        with open(os.path.join(self.site, "app.js"), encoding="utf-8") as served, \
                open(os.path.join(FIXTURE, "site", "app.js"), encoding="utf-8") as original:
            self.assertEqual(served.read(), original.read(), "the mutated script was not restored")

    def test_fidelity_reports_a_difference_and_not_a_role_neither_side_draws(self):
        code, out = self.prumo("fidelity", "plain")
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"box\n(?:.*\n)*? +padding +8px +-> +10px")
        self.assertIn("only-in-reference\n    drawn only in the reference", out)
        self.assertNotIn("in-neither", out)
        self.assertRegex(out, r"of 3 roles drawn in this state differ")

    def test_a_harness_styled_unlike_the_served_page_is_refused(self):
        with open(os.path.join(self.work, "harness.html"), encoding="utf-8") as source:
            restyled = source.read().replace("</head>", '<link rel="stylesheet" href="/extra.css">\n</head>')
        with open(os.path.join(self.work, "restyled.html"), "w", encoding="utf-8") as target:
            target.write(restyled)
        code, out = self.prumo("suite", "--only", "saves", config=self.write_config("restyled.json", "restyled.html"))
        self.assertNotEqual(code, 0, out)
        self.assertIn("styles the page differently", out)

    def test_visit_checks_a_folder_as_it_is_served(self):
        done = subprocess.run([sys.executable, PRUMO, "visit", os.path.join(self.work, "scenarios", "saves.js"),
                               "--serve", self.site, "--at", "/app/"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("PASS saves", done.stdout)

    def test_diff_tells_identical_from_changed(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        before, same, after = (os.path.join(self.work, name) for name in ("a.png", "b.png", "c.png"))
        Image.new("RGB", (20, 10), (255, 255, 255)).save(before)
        Image.new("RGB", (20, 10), (255, 255, 255)).save(same)
        changed = Image.new("RGB", (20, 10), (255, 255, 255))
        changed.putpixel((3, 4), (0, 0, 0))
        changed.save(after)
        code, out = self.prumo("diff", before, same)
        self.assertEqual((code, "identical" in out), (0, True), out)
        code, out = self.prumo("diff", before, after)
        self.assertEqual(code, 1, out)
        self.assertIn("1 of 200 pixels differ", out)

    def test_z_nothing_is_left_behind(self):
        self.assertEqual(glob.glob(os.path.join(self.site, "prumo-*")), [], "published files left in the site")
        left = set(glob.glob(os.path.join(tempfile.gettempdir(), "prumo-profile-*"))) - self.profiles_before
        self.assertEqual(left, set(), "browser profiles left behind")


if __name__ == "__main__":
    unittest.main()
