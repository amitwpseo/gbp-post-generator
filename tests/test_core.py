import unittest

import layouts
from output_parser import first_line, last_line, parse_output
from scraper import html_to_text, normalize_url
from validators import check_filename, emoji_matches, opens_with_question, validate
from tests.samples import MISMATCH_OUTPUT, POST_A, POST_B, make_output


def run(post, **kw):
    if "\n\n" not in post:  # most checks use one-line posts, so give them the 3 paragraphs every post needs
        post = post + "\n\nWe serve homes across Knox County.\n\nSend us a note to get started."
    parsed = {"post_text": post, "filename": kw.pop("filename", "Drain Cleaning Knoxville TN"),
              "layout": kw.pop("layout", "Problem, then solution"), "cta_url": ""}
    return validate(parsed, history=kw.pop("history", []), all_filenames=kw.pop("files", []), **kw)


class LayoutTests(unittest.TestCase):
    def test_library_has_twenty_layouts(self):
        lib = layouts.load_layouts()
        self.assertEqual(sorted(lib), list(range(1, 21)))
        self.assertEqual(lib[4], "Numbered 1-2-3 process steps")

    def test_normalize(self):
        lib = layouts.load_layouts()
        self.assertEqual(layouts.normalize_layout("Problem, then solution. The post states..."), lib[2])
        self.assertEqual(layouts.normalize_layout("Numbered 1-2-3 process steps"), lib[4])
        self.assertEqual(layouts.normalize_layout("7"), lib[7])
        self.assertEqual(layouts.normalize_layout("Layout 16 - job site facts"), lib[16])
        self.assertEqual(layouts.normalize_layout("**Mini Q&A** with four lines"), lib[7])
        self.assertEqual(layouts.normalize_layout(""), "")


class ParserTests(unittest.TestCase):
    def test_standard_output(self):
        p = parse_output(make_output(POST_A, "Drain Cleaning Knoxville TN", notes=["Price left out"]))
        self.assertEqual(p["match_status"], "Match")
        self.assertEqual(p["match_pct"], 92)
        self.assertEqual(p["post_type"], "Update")
        self.assertEqual(p["post_text"], POST_A)
        self.assertEqual(p["filename"], "Drain Cleaning Knoxville TN")
        self.assertEqual(p["cta_url"], "https://example.com/drain-cleaning")
        self.assertEqual(p["layout"], "Problem, then solution")
        self.assertEqual(p["notes"], ["Price left out"])
        self.assertIn("Never used", p["last_used"])

    def test_bold_labels(self):
        raw = make_output(POST_B, "Sewer Line Roots Knoxville TN").replace("Match Status:", "**Match Status:**")
        raw = raw.replace("Post Type:", "**Post Type:**").replace("CTA URL:", "**CTA URL:**")
        p = parse_output(raw)
        self.assertEqual(p["match_status"], "Match")
        self.assertEqual(p["post_type"], "Update")
        self.assertEqual(p["cta_url"], "https://example.com/drain-cleaning")

    def test_partial_and_mismatch(self):
        self.assertEqual(parse_output(make_output(POST_A, "A B C", status="Partial Match"))["match_status"], "Partial Match")
        m = parse_output(MISMATCH_OUTPUT)
        self.assertEqual(m["match_status"], "Mismatch")
        self.assertEqual(m["post_text"], "")
        self.assertIn("kitchen remodel", m["reason"])

    def test_first_last_line(self):
        self.assertEqual(first_line("\n\nHello there\nmid\nBye now\n\n"), "Hello there")
        self.assertEqual(last_line("\n\nHello there\nmid\nBye now\n\n"), "Bye now")


class ValidatorTests(unittest.TestCase):
    def test_clean_post_passes(self):
        v = run(POST_A)
        self.assertEqual(v["errors"], [])
        self.assertEqual(v["stats"]["emojis"], 2)

    def test_dashes(self):
        self.assertTrue(any("dash" in e for e in run(POST_A.replace("Grease,", "Grease —"))["errors"]))
        self.assertTrue(any("dash" in e for e in run(POST_A.replace("Grease,", "Grease –"))["errors"]))

    def test_phone_email_url(self):
        for bad in ("Call 865-555-1234 today", "Reach us at (865) 555 1234", "Email hi@example.com", "Visit example.com", "See https://x.io/a"):
            errs = run(POST_A + "\n" + bad)["errors"]
            self.assertTrue(errs, bad)
        self.assertEqual(run(POST_A + "\nWe have served 2019 to 2024 and 24/7 crews.")["errors"], [])

    def test_markdown_and_banned(self):
        self.assertTrue(run(POST_A + "\n**bold**")["errors"])
        self.assertTrue(run(POST_A + "\nLearn more on our page")["errors"])
        self.assertTrue(run(POST_A + "\ncall now")["errors"])

    def test_emojis(self):
        self.assertTrue(any("no emojis" in e for e in run("Plain text only here.")["errors"]))
        self.assertTrue(any("maximum" in e for e in run("a \U0001F6BF b \U0001F527 c \U0001F333 d ✅ e \U0001F4A7")["errors"]))
        self.assertTrue(any("stacked" in e for e in run("Water \U0001F6BF\U0001F527 fixed")["errors"]))
        self.assertEqual(run("Water \U0001F6BF \U0001F527 fixed")["errors"], [])
        self.assertEqual(len(emoji_matches("ok ✅ ❤️ \U0001F468‍\U0001F527 → ✓")), 3)

    def test_length(self):
        self.assertTrue(any("1,500" in e for e in run("x \U0001F6BF " + "word " * 320)["errors"]))

    def test_filename_rules(self):
        self.assertEqual(check_filename("Septic Tank Installation Knoxville TN", []), [])
        self.assertTrue(check_filename("septic-tank-installation", []))
        self.assertTrue(check_filename("Septic Tank.jpg", []))
        self.assertTrue(check_filename("Two Words", []))
        self.assertTrue(check_filename("Septic tank installation Knoxville", []))
        self.assertTrue(check_filename("Septic Tank Installation Knoxville TN", ["septic tank installation knoxville tn"]))

    def test_layout_repeat(self):
        hist = [{"layout": "Problem, then solution", "opener": "x", "closer": "y", "filename": "f"}]
        self.assertTrue(any("most recent" in e for e in run(POST_A, history=hist)["errors"]))
        older = [{"layout": "Other", "opener": "x", "closer": "y"}, hist[0]]
        v = run(POST_A, history=older)
        self.assertEqual(v["errors"], [])
        self.assertTrue(v["warnings"])

    def test_question_opener_and_closer(self):
        self.assertTrue(opens_with_question("Slow drains in Knoxville? Here is why."))
        self.assertFalse(opens_with_question("Slow drains. Why?"))
        hist = [{"layout": "Other", "opener": "Is your sink slow? Read on.", "closer": "Something else entirely", "filename": "f"}]
        self.assertTrue(any("question" in e for e in run(POST_A, history=hist)["errors"]))
        same_closer = [{"layout": "Other", "opener": "Plain opener.", "closer": "Send us a note about your drain and we will suggest a next step!", "filename": "f"}]
        self.assertTrue(any("closing line" in e for e in run(POST_A, history=same_closer)["errors"]))

    def test_price_warning(self):
        v = run(POST_A + "\nFrom $65 today")
        self.assertTrue(any("price" in w for w in v["warnings"]))
        self.assertFalse(any("price" in w for w in run(POST_A + "\nFrom $65 today", special_instructions="add the $65 price")["warnings"]))


class ScraperTests(unittest.TestCase):
    def test_normalize_url(self):
        self.assertEqual(normalize_url("hhttps://a.com/x"), ("https://a.com/x", True))
        self.assertEqual(normalize_url("a.com/x"), ("https://a.com/x", True))
        self.assertEqual(normalize_url("https://a.com/x"), ("https://a.com/x", False))
        self.assertEqual(normalize_url("http:/a.com"), ("http://a.com", True))

    def test_html_to_text(self):
        html = ("<html><head><title>Drain Cleaning</title><meta name='description' content='Fast drain help'></head>"
                "<body><nav>Menu Home About</nav><main><h1>Drain Cleaning in Knoxville</h1>"
                "<p>We clear clogs. " + "More detail. " * 40 + "</p><script>var x=1;</script></main>"
                "<footer>Copyright</footer></body></html>")
        text = html_to_text(html)
        self.assertIn("Page title: Drain Cleaning", text)
        self.assertIn("Meta description: Fast drain help", text)
        self.assertIn("Drain Cleaning in Knoxville", text)
        self.assertNotIn("var x=1", text)
        self.assertNotIn("Menu Home", text)


if __name__ == "__main__":
    unittest.main()
