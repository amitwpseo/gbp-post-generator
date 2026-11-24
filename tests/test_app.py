"""End-to-end tests of the Flask app with a fake Gemini (no API key or network needed)."""
import io
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

import app as app_module
import config
import db
import gemini_client
import scraper
from tests.samples import MISMATCH_OUTPUT, POST_A, POST_B, POST_C, make_output

PAGE = "Drain cleaning in Knoxville. " * 20


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "red").save(buf, format="PNG")
    return buf.getvalue()


class FakeGemini:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, turns):
        self.calls.append(list(turns))
        if not self.outputs:
            raise AssertionError("Fake Gemini ran out of outputs")
        return self.outputs.pop(0)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"GBP_DATA_DIR": self.tmp.name, "MAX_FIX_ATTEMPTS": "2"})
        self.env.start()
        self.http = app_module.app.test_client()
        self.client_id = self.http.post("/api/clients", json={
            "name": "Sample Plumbing", "address": "1 Main St, Knoxville, TN", "phone": "865-555-0100",
            "website": "https://example.com"}).get_json()["id"]
        self.patches = [mock.patch.object(scraper, "fetch_page_text", return_value=(PAGE, None))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.tmp.cleanup()

    def gen(self, fake, **extra):
        data = {"client_id": str(self.client_id), "cta_url": "https://example.com/drain-cleaning",
                "image": (io.BytesIO(png_bytes()), "photo.png"), "special": ""}
        data.update(extra)
        with mock.patch.object(gemini_client, "generate", fake):
            return self.http.post("/api/generate", data=data, content_type="multipart/form-data")

    def test_generate_saves_and_next_prompt_uses_history(self):
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN"),
                           make_output(POST_B, "Sewer Roots Knoxville TN", layout="Plain statement opener, then 2 or 3 short paragraphs")])
        r1 = self.gen(fake).get_json()
        self.assertEqual(r1["status"], "ok")
        self.assertEqual(r1["post"]["filename"], "Drain Cleaning Knoxville TN")
        self.assertEqual(r1["post"]["emojis"], 2)
        self.assertGreater(r1["scraped_chars"], 0)
        r2 = self.gen(fake).get_json()
        self.assertEqual(r2["status"], "ok")
        second_prompt = fake.calls[1][0].text
        self.assertIn("Layout: Problem, then solution", second_prompt)
        self.assertIn("Filename: Drain Cleaning Knoxville TN", second_prompt)
        self.assertIn("Opener: Slow drains in Knoxville?", second_prompt)
        self.assertIsNotNone(fake.calls[1][0].image)
        self.assertEqual(len(self.http.get(f"/api/clients/{self.client_id}/posts").get_json()), 2)

    def test_retry_fixes_dash(self):
        bad = make_output(POST_A.replace("Grease,", "Grease —"), "Drain Cleaning Knoxville TN")
        fake = FakeGemini([bad, make_output(POST_A, "Drain Cleaning Knoxville TN")])
        r = self.gen(fake).get_json()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["attempts"], 1)
        self.assertEqual(len(fake.calls[1]), 3)
        self.assertIn("dash", fake.calls[1][2].text)

    def test_mismatch_not_saved_and_no_extra_call(self):
        fake = FakeGemini([MISMATCH_OUTPUT])
        r = self.gen(fake).get_json()
        self.assertEqual(r["status"], "mismatch")
        self.assertEqual(len(r["options"]), 3)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(db.get_posts(self.client_id, status=None), [])

    def test_force_proceed_after_mismatch(self):
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN", status="Mismatch", pct=30)])
        r = self.gen(fake, force="1").get_json()
        self.assertEqual(r["status"], "ok")
        self.assertIn("chose to proceed anyway", fake.calls[0][0].text)

    def test_flagged_after_failed_fixes_then_accept(self):
        bad = make_output(POST_A.replace("Grease,", "Grease —"), "Drain Cleaning Knoxville TN")
        with mock.patch.dict(os.environ, {"MAX_FIX_ATTEMPTS": "1"}):
            fake = FakeGemini([bad, bad])
            r = self.gen(fake).get_json()
        self.assertEqual(r["status"], "needs_review")
        self.assertEqual(len(fake.calls), 2)
        pid = r["post"]["id"]
        self.assertEqual(db.get_posts(self.client_id), [])  # flagged posts stay out of the history sent to Gemini
        self.http.post(f"/api/posts/{pid}/accept")
        self.assertEqual(len(db.get_posts(self.client_id)), 1)

    def test_duplicate_filename_is_retried(self):
        fake = FakeGemini([
            make_output(POST_A, "Drain Cleaning Knoxville TN"),
            make_output(POST_B, "Drain Cleaning Knoxville TN", layout="Plain statement opener, then 2 or 3 short paragraphs"),
            make_output(POST_B, "Sewer Line Roots Knoxville TN", layout="Plain statement opener, then 2 or 3 short paragraphs"),
        ])
        self.gen(fake)
        r = self.gen(fake).get_json()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["attempts"], 1)
        self.assertEqual(r["post"]["filename"], "Sewer Line Roots Knoxville TN")

    def test_cta_typo_fixed_and_noted(self):
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN")])
        r = self.gen(fake, cta_url="hhttps://example.com/drain-cleaning").get_json()
        self.assertEqual(r["post"]["cta_url"], "https://example.com/drain-cleaning")
        self.assertTrue(any("typo" in n for n in r["post"]["notes"]))

    def test_scrape_failure_asks_for_pasted_text(self):
        with mock.patch.object(scraper, "fetch_page_text", return_value=("", "the site returned HTTP 403")):
            r = self.gen(FakeGemini([]))
        self.assertEqual(r.status_code, 422)
        self.assertIn("Paste the page text", r.get_json()["error"])

    def test_pasted_page_content_skips_scraping(self):
        with mock.patch.object(scraper, "fetch_page_text", side_effect=AssertionError("should not scrape")):
            fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN")])
            r = self.gen(fake, page_content="Pasted page text about drains.").get_json()
        self.assertEqual(r["status"], "ok")
        self.assertIn("Pasted page text about drains.", fake.calls[0][0].text)

    def test_validation_of_inputs(self):
        self.assertEqual(self.http.post("/api/generate", data={"client_id": str(self.client_id)}).status_code, 400)
        r = self.http.post("/api/generate", data={"client_id": str(self.client_id), "cta_url": "https://x.com",
                                                   "image": (io.BytesIO(b"not an image"), "a.png")},
                           content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("not a readable image", r.get_json()["error"])

    def test_edit_post(self):
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN"),
                           make_output(POST_C, "Drain Cleaning Knoxville TN", layout="Plain statement opener, then 2 or 3 short paragraphs")])
        pid = self.gen(fake).get_json()["post"]["id"]
        with mock.patch.object(gemini_client, "generate", fake):
            r = self.http.post(f"/api/posts/{pid}/edit", json={"instruction": "make it shorter"}).get_json()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["post"]["id"], pid)
        self.assertEqual(r["post"]["text"], POST_C)
        turns = fake.calls[1]
        self.assertEqual([t.role for t in turns], ["user", "model", "user"])
        self.assertTrue(turns[2].text.startswith("make it shorter"))
        self.assertIn("at least 3 paragraphs", turns[2].text)
        self.assertIsNotNone(turns[0].image)
        self.assertEqual(len(db.get_posts(self.client_id)), 1)

    def test_delete_post_and_client(self):
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN")])
        pid = self.gen(fake).get_json()["post"]["id"]
        post = db.get_post(pid)
        img = os.path.join(self.tmp.name, "uploads", post["image_path"])
        self.assertTrue(os.path.exists(img))
        self.assertEqual(self.http.delete(f"/api/posts/{pid}").status_code, 200)
        self.assertFalse(os.path.exists(img))
        self.assertEqual(self.http.delete(f"/api/clients/{self.client_id}").status_code, 200)
        self.assertEqual(self.http.get("/api/clients").get_json(), [])

    def test_gemini_error_is_reported(self):
        def boom(turns):
            raise gemini_client.GeminiError("Gemini free-tier rate limit or daily quota reached.", 429)
        with mock.patch.object(gemini_client, "generate", boom):
            r = self.http.post("/api/generate", data={
                "client_id": str(self.client_id), "cta_url": "https://example.com/x",
                "image": (io.BytesIO(png_bytes()), "p.png")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 429)
        self.assertIn("quota", r.get_json()["error"])

    def test_index_and_status(self):
        self.assertEqual(self.http.get("/").status_code, 200)
        s = self.http.get("/api/status").get_json()
        self.assertEqual(s["model"], config.models()[0])


class GeminiClientTests(unittest.TestCase):
    def test_missing_key(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
            with mock.patch("config.api_key", return_value=""):
                with self.assertRaises(gemini_client.GeminiError):
                    gemini_client.generate([gemini_client.Turn("user", "hi")])

    def test_turn_conversion_builds_sdk_contents(self):
        turns = [gemini_client.Turn("user", "hello", (png_bytes(), "image/png")), gemini_client.Turn("model", "ok")]
        contents = gemini_client._to_contents(turns)
        self.assertEqual([c.role for c in contents], ["user", "model"])
        self.assertEqual(len(contents[0].parts), 2)
        self.assertEqual(contents[0].parts[1].inline_data.mime_type, "image/png")


if __name__ == "__main__":
    unittest.main()
