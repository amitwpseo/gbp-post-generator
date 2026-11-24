import io
import os
import random
import re
import tempfile
import unittest
from unittest import mock

import app as app_module
import gemini_client
import layouts
import options
import scraper
from errors import UserError
from tests.samples import POST_A, POST_B, POST_C, POST_QA, QA_LAYOUT, make_output
from tests.test_app import PAGE, FakeGemini, png_bytes
from validators import validate


class ResolveTests(unittest.TestCase):
    def test_catalog(self):
        c = options.catalog()
        self.assertEqual(len(c["layouts"]), 20)
        self.assertEqual([x["id"] for x in c["lengths"]], ["short", "standard", "long"])
        self.assertEqual([x["id"] for x in c["emojis"]], ["1", "2", "3", "4"])

    def test_auto_and_empty_mean_gemini_decides(self):
        r = options.resolve({"layout": "auto", "length": "", "opener": None})
        self.assertTrue(all(r[k] is None for k in options.FIELDS))
        self.assertEqual(r["random_fields"], [])
        self.assertEqual(options.instruction_text(r), "")

    def test_fixed_choices(self):
        lib = layouts.load_layouts()
        r = options.resolve({"layout": "7", "length": "short", "opener": "scene", "closer": "pointer",
                             "tone": "direct", "emojis": "3"})
        self.assertEqual(r["layout"], lib[7])
        self.assertEqual((r["length"], r["opener"], r["closer"], r["tone"], r["emojis"]),
                         ("short", "scene", "pointer", "direct", 3))
        text = options.instruction_text(r)
        self.assertIn(f"use exactly this layout from the library: {lib[7]}.", text)
        self.assertIn("250 to 450", text)
        self.assertIn("exactly 3 emojis", text)

    def test_invalid_values(self):
        for bad in ({"layout": "99"}, {"layout": "abc"}, {"length": "huge"}, {"emojis": "9"}, {"emojis": "x"},
                    {"opener": "nope"}):
            with self.assertRaises(UserError):
                options.resolve(bad)

    def test_random_layout_avoids_recent_and_never_picks_19(self):
        lib = layouts.load_layouts()
        avoid = [lib[1], lib[2], lib[3], lib[4], lib[5]]
        rng = random.Random(1)
        picks = {options.resolve({"layout": "random"}, avoid_layouts=avoid, rng=rng)["layout"] for _ in range(300)}
        self.assertFalse(picks & set(avoid))
        self.assertNotIn(lib[19], picks)
        self.assertGreater(len(picks), 8)

    def test_random_layout_still_works_when_everything_is_avoided(self):
        lib = layouts.load_layouts()
        r = options.resolve({"layout": "random"}, avoid_layouts=list(lib.values()), rng=random.Random(2))
        self.assertIn(r["layout"], lib.values())
        self.assertNotEqual(r["layout"], lib[19])

    def test_random_opener_skips_question_after_recent_question(self):
        rng = random.Random(3)
        picks = {options.resolve({"opener": "random"}, avoid_question_opener=True, rng=rng)["opener"] for _ in range(200)}
        self.assertNotIn("question", picks)
        picks = {options.resolve({"opener": "random"}, avoid_question_opener=False, rng=rng)["opener"] for _ in range(200)}
        self.assertIn("question", picks)

    def test_random_all_and_describe(self):
        r = options.resolve({k: "random" for k in options.FIELDS if k != "post_type"}, rng=random.Random(4))
        self.assertEqual(sorted(r["random_fields"]), sorted(f for f in options.FIELDS if f != "post_type"))
        rows = options.describe(r)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["random"] for row in rows))
        fixed = options.describe(options.resolve({"length": "long"}))
        self.assertEqual(fixed, [{"field": "Length", "value": "Long (900 to 1200 characters)", "random": False}])


def check(post, requested, **kw):
    parsed = {"post_text": post, "filename": "Drain Cleaning Knoxville TN",
              "layout": kw.pop("layout", "Problem, then solution"), "cta_url": ""}
    return validate(parsed, history=kw.pop("history", []), all_filenames=[], requested=requested, **kw)["errors"]


class RequestedOptionValidationTests(unittest.TestCase):
    def test_layout_must_match(self):
        self.assertEqual(check(POST_A, {"layout": "Problem, then solution"}), [])
        errs = check(POST_A, {"layout": QA_LAYOUT})
        self.assertTrue(any("requested layout" in e for e in errs))

    def test_requested_layout_same_as_last_post_is_only_a_warning(self):
        hist = [{"layout": "Problem, then solution", "opener": "x", "closer": "y", "filename": "f"}]
        parsed = {"post_text": POST_A, "filename": "Another Name Knoxville TN", "layout": "Problem, then solution"}
        v = validate(parsed, history=hist, all_filenames=[], requested={"layout": "Problem, then solution"})
        self.assertEqual(v["errors"], [])
        self.assertTrue(any("you asked for it" in w for w in v["warnings"]))

    def test_length(self):
        self.assertEqual(check(POST_A, {"length": "short"}), [])
        self.assertTrue(any("long post (900 to 1200" in e for e in check(POST_A, {"length": "long"})))
        self.assertTrue(any("standard post (500 to 800" in e for e in check(POST_A, {"length": "standard"})))
        self.assertTrue(any("long post" in e for e in check("x \U0001F6BF " + "word " * 40, {"length": "long"})))

    def test_emojis_exact(self):
        self.assertEqual(check(POST_A, {"emojis": 2}), [])
        self.assertTrue(any("exactly 3" in e for e in check(POST_A, {"emojis": 3})))

    def test_opener_and_closer_styles(self):
        self.assertEqual(check(POST_A, {"opener": "question"}), [])
        self.assertTrue(any("question opener" in e for e in check(POST_B, {"opener": "question"})))
        self.assertTrue(any("statement opener" in e for e in check(POST_A, {"opener": "statement"})))
        self.assertTrue(any("question closer" in e for e in check(POST_A, {"closer": "question"})))
        self.assertEqual(check(POST_A + " Ready to start?", {"closer": "question"}), [])

    def test_requested_question_opener_overrides_the_repeat_rule(self):
        hist = [{"layout": "Other", "opener": "Is your sink slow? Read on.", "closer": "Something else", "filename": "f"}]
        self.assertTrue(any("last 3 posts did too" in e for e in check(POST_A, {}, history=hist)))
        self.assertFalse(any("last 3 posts did too" in e for e in check(POST_A, {"opener": "question"}, history=hist)))


class OptionsAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"GBP_DATA_DIR": self.tmp.name, "MAX_FIX_ATTEMPTS": "2"})
        self.env.start()
        self.http = app_module.app.test_client()
        self.client_id = self.http.post("/api/clients", json={"name": "Sample Plumbing"}).get_json()["id"]
        self.scrape = mock.patch.object(scraper, "fetch_page_text", return_value=(PAGE, None))
        self.scrape.start()

    def tearDown(self):
        self.scrape.stop()
        self.env.stop()
        self.tmp.cleanup()

    def gen(self, fake, **extra):
        data = {"client_id": str(self.client_id), "cta_url": "https://example.com/drain-cleaning",
                "image": (io.BytesIO(png_bytes()), "photo.png")}
        data.update(extra)
        with mock.patch.object(gemini_client, "generate", fake):
            return self.http.post("/api/generate", data=data, content_type="multipart/form-data").get_json()

    def test_options_endpoint(self):
        self.assertEqual(len(self.http.get("/api/options").get_json()["layouts"]), 20)

    def test_fixed_layout_is_sent_and_reported(self):
        fake = FakeGemini([make_output(POST_QA, "Drain Questions Knoxville TN", layout=QA_LAYOUT)])
        r = self.gen(fake, layout="7", length="auto")
        self.assertEqual(r["status"], "ok")
        self.assertIn(f"use exactly this layout from the library: {QA_LAYOUT}.", fake.calls[0][0].text)
        self.assertEqual(r["applied_options"], [{"field": "Layout", "value": QA_LAYOUT, "random": False}])
        self.assertEqual(r["post"]["layout"], QA_LAYOUT)

    def test_wrong_layout_is_retried(self):
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN", layout="Problem, then solution"),
                           make_output(POST_QA, "Drain Questions Knoxville TN", layout=QA_LAYOUT)])
        r = self.gen(fake, layout="7")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["attempts"], 1)
        self.assertIn("requested layout", fake.calls[1][2].text)

    def test_random_layout_is_resolved_by_the_app(self):
        def echo(turns):
            m = re.search(r"use exactly this layout from the library: (.*?)\. State", turns[0].text)
            echo.layout = m.group(1)
            return make_output(POST_A, "Drain Cleaning Knoxville TN", layout=m.group(1))
        r = self.gen(echo, layout="random")
        self.assertEqual(r["status"], "ok", r)
        self.assertEqual(r["post"]["layout"], echo.layout)
        self.assertEqual(r["applied_options"], [{"field": "Layout", "value": echo.layout, "random": True}])
        self.assertNotEqual(echo.layout, layouts.load_layouts()[19])

    def test_another_with_fixed_layout_does_not_ask_for_a_different_layout(self):
        fake = FakeGemini([make_output(POST_QA, "Drain Questions Knoxville TN", layout=QA_LAYOUT),
                           make_output(POST_C, "Gurgling Pipes Knoxville TN", layout=QA_LAYOUT)])
        self.gen(fake, layout="7")
        r = self.gen(fake, layout="7", another="1")
        self.assertEqual(r["status"], "ok")
        second = fake.calls[1][0].text
        self.assertIn("different opener, closer, filename", second)
        self.assertNotIn("different layout", second)
        self.assertTrue(any("you asked for it" in w for w in r["validation"]["warnings"]))

    def test_invalid_option_is_a_clear_error(self):
        r = self.http.post("/api/generate", data={
            "client_id": str(self.client_id), "cta_url": "https://example.com/x", "layout": "99",
            "image": (io.BytesIO(png_bytes()), "p.png")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Unknown layout", r.get_json()["error"])

    def test_no_options_behaves_as_before(self):
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN")])
        r = self.gen(fake, layout="auto", length="auto", opener="auto", closer="auto", tone="auto", emojis="auto")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["applied_options"], [])
        self.assertNotIn("Requested for this post", fake.calls[0][0].text)


if __name__ == "__main__":
    unittest.main()
