import os
import tempfile
import unittest
from unittest import mock

import app as app_module
import emoji_ai
import gemini_client
from errors import UserError
from validators import check_filename, file_slug


class SlugTests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(file_slug("Drain Cleaning Knoxville TN"), "drain-cleaning-knoxville-tn")
        self.assertEqual(file_slug("  Water Heater: Repair, Dallas TX! "), "water-heater-repair-dallas-tx")
        self.assertEqual(file_slug(""), "gbp-photo")


class SeoFilenameTests(unittest.TestCase):
    def test_short_keyword_names_pass(self):
        for name in ("Drain Cleaning Knoxville TN", "Windshield Replacement San Diego CA", "Junk Car Buyer St Louis"):
            self.assertEqual(check_filename(name, []), [], name)

    def test_too_long_names_fail(self):
        long_name = "Emergency Drain Cleaning Service Repair Knoxville Tennessee"
        errs = check_filename(long_name, [])
        self.assertTrue(any("3 to 5 words" in e for e in errs))
        self.assertTrue(any("under 45" in e for e in errs))

    def test_six_words_under_the_limit_still_fail(self):
        self.assertTrue(any("3 to 5 words" in e for e in check_filename("Sewer Line Root Removal Knoxville TN", [])))

    def test_filler_words_fail(self):
        self.assertTrue(any("filler" in e for e in check_filename("Best Drain Cleaning In Knoxville", [])))

    def test_relaxed_mode_only_checks_missing_and_repeats(self):
        old = "Septic Tank Installation And Repair For Homes In Knoxville"
        self.assertEqual(check_filename(old, [], strict=False), [])
        self.assertTrue(check_filename(old, [old.lower()], strict=False))
        self.assertTrue(check_filename("", [], strict=False))


class EmojiAiTests(unittest.TestCase):
    def test_parse_keeps_only_emoji_without_repeats(self):
        raw = "Sure! \U0001F6BF \U0001F527 \U0001F6BF 12 \u2705\n\U0001F9D1\u200D\U0001F527 text"
        self.assertEqual(emoji_ai.parse(raw), ["\U0001F6BF", "\U0001F527", "\u2705", "\U0001F9D1\u200D\U0001F527"])

    def test_suggest_calls_gemini_without_the_post_prompt(self):
        seen = {}

        def fake(turns, system=None, temperature=None):
            seen.update(turns=turns, system=system, temperature=temperature)
            return "\U0001FAE7 \U0001F4A7"
        with mock.patch.object(gemini_client, "generate", fake):
            out = emoji_ai.suggest("soap bubbles", "Drain cleaning post")
        self.assertEqual(out, ["\U0001FAE7", "\U0001F4A7"])
        self.assertIs(seen["system"], emoji_ai.SYSTEM)
        self.assertIn("soap bubbles", seen["turns"][0].text)
        self.assertIn("Drain cleaning post", seen["turns"][0].text)

    def test_empty_query_and_no_emoji_answer_are_errors(self):
        with self.assertRaises(UserError):
            emoji_ai.suggest("   ")
        with mock.patch.object(gemini_client, "generate", lambda *a, **k: "I could not find one"):
            with self.assertRaises(UserError):
                emoji_ai.suggest("something odd")


class EmojiApiTests(unittest.TestCase):
    def test_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"GBP_DATA_DIR": tmp}):
            http = app_module.app.test_client()
            with mock.patch.object(gemini_client, "generate", lambda *a, **k: "\U0001F4A7 \U0001F6BF"):
                r = http.post("/api/emoji/suggest", json={"query": "water", "context": "plumber"})
            self.assertEqual(r.get_json()["emojis"], ["\U0001F4A7", "\U0001F6BF"])
            self.assertEqual(http.post("/api/emoji/suggest", json={"query": ""}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
