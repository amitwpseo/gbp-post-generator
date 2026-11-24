import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import app as app_module
import config
import db
import gemini_client
import options
import scraper
from errors import UserError
from output_parser import parse_output
from tests.samples import POST_A, make_output
from tests.test_app import PAGE, FakeGemini, png_bytes
from validators import post_type_key, validate


def with_type(raw, post_type):
    """Rewrites the sample output's 'Post Type:' line."""
    lines = raw.splitlines()
    return "\n".join(f"Post Type: {post_type}" if ln.startswith("Post Type:") else ln for ln in lines)


class ResolveTests(unittest.TestCase):
    def test_post_type_choices(self):
        self.assertIsNone(options.resolve({})["post_type"])
        self.assertEqual(options.resolve({"post_type": "offer"})["post_type"], "offer")
        with self.assertRaises(UserError):
            options.resolve({"post_type": "random"})
        with self.assertRaises(UserError):
            options.resolve({"post_type": "sale"})

    def test_details_kept_only_for_the_chosen_type_and_cleaned(self):
        r = options.resolve({"post_type": "offer"},
                            details={"offer_title": "  Spring   tune up ", "offer_end": "May 31", "event_title": "Open house"})
        self.assertEqual(r["type_details"], {"offer_title": "Spring tune up", "offer_end": "May 31"})
        self.assertEqual(options.resolve({"post_type": "update"}, details={"offer_title": "x"})["type_details"], {})

    def test_instruction_with_details_states_facts(self):
        r = options.resolve({"post_type": "offer"}, details={"offer_title": "$40 off drain cleaning", "offer_end": "May 31"})
        text = options.instruction_text(r)
        self.assertIn("Offer title: $40 off drain cleaning", text)
        self.assertIn("do not add any others", text)

    def test_instruction_without_details_falls_back_to_update(self):
        text = options.instruction_text(options.resolve({"post_type": "event"}))
        self.assertIn("only if the CTA page content contains a real dated event", text)
        self.assertIn("write an Update", text)

    def test_describe_lists_post_type_first(self):
        rows = options.describe(options.resolve({"post_type": "update", "length": "short"}))
        self.assertEqual(rows[0], {"field": "Post type", "value": "Update (What's New)", "random": False})

    def test_catalog_has_post_types(self):
        self.assertEqual([t["id"] for t in options.catalog()["post_types"]], ["update", "offer", "event"])


class ValidateTests(unittest.TestCase):
    def check(self, out_type, requested):
        parsed = parse_output(with_type(make_output(POST_A, "Drain Cleaning Knoxville TN"), out_type))
        return validate(parsed, history=[], all_filenames=[], requested=requested)

    def test_key_mapping(self):
        self.assertEqual(post_type_key("Update (What's New)"), "update")
        self.assertEqual(post_type_key("What's New"), "update")
        self.assertEqual(post_type_key("Offer"), "offer")
        self.assertEqual(post_type_key("Event"), "event")
        self.assertEqual(post_type_key(""), "")

    def test_offer_without_details_that_became_update_is_a_warning(self):
        v = self.check("Update", {"post_type": "offer", "type_details": {}})
        self.assertEqual(v["errors"], [])
        self.assertTrue(any("may not have a real offer" in w for w in v["warnings"]))

    def test_offer_with_details_that_became_update_is_an_error(self):
        v = self.check("Update", {"post_type": "offer", "type_details": {"offer_title": "Spring deal"}})
        self.assertTrue(any("Offer post was requested" in e for e in v["errors"]))

    def test_update_requested_but_offer_written_is_an_error(self):
        v = self.check("Offer", {"post_type": "update", "type_details": {}})
        self.assertTrue(any("Update post was requested" in e for e in v["errors"]))

    def test_matching_type_passes(self):
        self.assertEqual(self.check("Offer", {"post_type": "offer", "type_details": {"offer_title": "x"}})["errors"], [])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"GBP_DATA_DIR": self.tmp.name})
        self.env.start()
        self.http = app_module.app.test_client()
        self.client_id = self.http.post("/api/clients", json={"name": "Sample Plumbing"}).get_json()["id"]
        self.scrape = mock.patch.object(scraper, "fetch_page_text", return_value=(PAGE, None))
        self.scrape.start()

    def tearDown(self):
        self.scrape.stop()
        self.env.stop()
        self.tmp.cleanup()

    def generate(self, out_type, **form):
        fake = FakeGemini([with_type(make_output(POST_A, "Drain Cleaning Knoxville TN"), out_type)])
        data = {"client_id": str(self.client_id), "cta_url": "https://example.com/drain-cleaning",
                "image": (io.BytesIO(png_bytes()), "photo.png"), **form}
        with mock.patch.object(gemini_client, "generate", fake):
            r = self.http.post("/api/generate", data=data, content_type="multipart/form-data")
        return r, fake

    def test_offer_details_reach_gemini_and_come_back_with_the_post(self):
        r, fake = self.generate("Offer", post_type="offer", offer_title="$40 off drain cleaning",
                                offer_end="May 31", event_title="ignored")
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        sent = fake.calls[0][0].text
        self.assertIn("Offer title: $40 off drain cleaning", sent)
        self.assertNotIn("ignored", sent)
        post = body["post"]
        self.assertEqual(post["post_type_key"], "offer")
        self.assertEqual(post["type_details"], [{"label": "Offer title", "value": "$40 off drain cleaning"},
                                                {"label": "Ends", "value": "May 31"}])
        again = self.http.get(f"/api/posts/{post['id']}").get_json()
        self.assertEqual(again["type_details"], post["type_details"])
        self.assertEqual(body["applied_options"][0]["field"], "Post type")

    def test_random_post_type_is_refused(self):
        r, _ = self.generate("Update", post_type="random")
        self.assertEqual(r.status_code, 400)

    def test_old_database_gets_the_new_column(self):
        db._ready.clear()
        path = config.db_path()
        path.unlink(missing_ok=True)
        old = sqlite3.connect(path)
        old.executescript(db.SCHEMA.replace(",\n    type_details TEXT DEFAULT ''", ""))
        old.close()
        self.assertNotIn("type_details", [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(posts)")])
        db.create_client({"name": "x"})
        self.assertIn("type_details", [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(posts)")])


if __name__ == "__main__":
    unittest.main()
