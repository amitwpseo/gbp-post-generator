import io
import os
import tempfile
import unittest
from unittest import mock

import app as app_module
import db
import gemini_client
import scraper
from tests.samples import POST_A, POST_B, make_output
from tests.test_app import PAGE, FakeGemini, png_bytes


class PostApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"GBP_DATA_DIR": self.tmp.name})
        self.env.start()
        self.http = app_module.app.test_client()
        self.client_id = self.http.post("/api/clients", json={"name": "Sample Plumbing"}).get_json()["id"]
        self.scrape = mock.patch.object(scraper, "fetch_page_text", return_value=(PAGE, None))
        self.scrape.start()
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN")])
        with mock.patch.object(gemini_client, "generate", fake):
            r = self.http.post("/api/generate", data={
                "client_id": str(self.client_id), "cta_url": "https://example.com/drain-cleaning",
                "image": (io.BytesIO(png_bytes()), "photo.png")}, content_type="multipart/form-data")
        self.post = r.get_json()["post"]

    def tearDown(self):
        self.scrape.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_post_reports_that_it_has_an_image(self):
        self.assertTrue(self.post["has_image"])
        self.assertEqual(self.post["file_name"], "drain-cleaning-knoxville-tn.jpg")

    def test_image_inline_and_download_with_generated_filename(self):
        inline = self.http.get(f"/api/posts/{self.post['id']}/image")
        self.assertEqual(inline.status_code, 200)
        self.assertEqual(inline.mimetype, "image/jpeg")
        self.assertTrue(inline.data.startswith(b"\xff\xd8"))
        self.assertNotIn("attachment", inline.headers.get("Content-Disposition", ""))
        dl = self.http.get(f"/api/posts/{self.post['id']}/image?download=1")
        disposition = dl.headers["Content-Disposition"]
        self.assertIn("attachment", disposition)
        self.assertIn("drain-cleaning-knoxville-tn.jpg", disposition)

    def test_image_missing_is_404(self):
        db.update_post(self.post["id"], image_path="")
        self.assertEqual(self.http.get(f"/api/posts/{self.post['id']}/image").status_code, 404)

    def test_image_path_cannot_escape_the_upload_folder(self):
        db.update_post(self.post["id"], image_path="../history.db")
        self.assertEqual(self.http.get(f"/api/posts/{self.post['id']}/image").status_code, 404)

    def test_manual_text_edit_is_saved_and_rechecked(self):
        new_text = POST_B
        r = self.http.patch(f"/api/posts/{self.post['id']}/text", json={"text": new_text}).get_json()
        self.assertEqual(r["post"]["text"], new_text)
        self.assertEqual(r["validation"]["errors"], [])
        row = db.get_post(self.post["id"])
        self.assertEqual(row["opener"], new_text.splitlines()[0])
        self.assertEqual(row["closer"], "Take a look at the service page for the full list of drain services.")
        self.assertEqual(row["length"], len(new_text))
        self.assertIn(new_text, row["raw_output"])
        self.assertNotIn(POST_A, row["raw_output"])

    def test_manual_edit_that_breaks_a_rule_is_reported_not_blocked(self):
        r = self.http.patch(f"/api/posts/{self.post['id']}/text",
                            json={"text": POST_A + "\nCall 865-555-1234 — now"}).get_json()
        self.assertTrue(any("phone" in e for e in r["validation"]["errors"]))
        self.assertTrue(any("dash" in e for e in r["validation"]["errors"]))
        self.assertIn("865-555-1234", db.get_post(self.post["id"])["post_text"])

    def test_empty_text_is_rejected(self):
        r = self.http.patch(f"/api/posts/{self.post['id']}/text", json={"text": "   "})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(db.get_post(self.post["id"])["post_text"], POST_A)


if __name__ == "__main__":
    unittest.main()
