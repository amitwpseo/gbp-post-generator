import io
import os
import tempfile
import unittest
from unittest import mock

import app as app_module
import db
import gemini_client
import layouts
import scraper
from tests.samples import POST_A, POST_B, POST_C, QA_LAYOUT, POST_QA, make_output
from tests.test_app import PAGE, FakeGemini, png_bytes
from validators import count_paragraphs, validate


def check(text):
    parsed = {"post_text": text, "filename": "Drain Cleaning Knoxville TN", "layout": "Problem, then solution", "cta_url": ""}
    return validate(parsed, history=[], all_filenames=[])["errors"]


class ParagraphTests(unittest.TestCase):
    def test_counting(self):
        self.assertEqual(count_paragraphs("One \U0001F6BF\n\nTwo\n\n\nThree"), 3)
        self.assertEqual(count_paragraphs("One line\nstill one paragraph"), 1)
        self.assertEqual(count_paragraphs("A\n  \nB"), 2)

    def test_two_paragraphs_fail_and_three_pass(self):
        two = "Slow drains happen. \U0001F6BF\n\nSend us a note."
        self.assertTrue(any("2 paragraphs" in e and "at least 3" in e for e in check(two)))
        self.assertFalse(any("paragraph" in e for e in check(two + "\n\nWe serve Knox County.")))

    def test_one_paragraph_message_is_singular(self):
        self.assertTrue(any("1 paragraph." in e for e in check("Just one block of text \U0001F6BF")))


class Base(unittest.TestCase):
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

    def gen(self, fake):
        with mock.patch.object(gemini_client, "generate", fake):
            return self.http.post("/api/generate", data={
                "client_id": str(self.client_id), "cta_url": "https://example.com/drain-cleaning",
                "image": (io.BytesIO(png_bytes()), "photo.png")}, content_type="multipart/form-data")


class GenerateRulesTests(Base):
    def test_every_request_carries_the_paragraph_rule(self):
        fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN")])
        self.gen(fake)
        self.assertIn("at least 3 paragraphs", fake.calls[0][0].text)

    def test_two_paragraph_answer_is_sent_back_for_a_fix(self):
        short = "Slow drains happen. \U0001F6BF\n\nSend us a note. ✅"
        fake = FakeGemini([make_output(short, "Drain Cleaning Knoxville TN"), make_output(POST_A, "Drain Cleaning Knoxville TN")])
        body = self.gen(fake).get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["post"]["text"], POST_A)
        self.assertIn("at least 3 paragraphs", fake.calls[1][-1].text)


class LayoutChangeTests(Base):
    def setUp(self):
        super().setUp()
        self.fake = FakeGemini([make_output(POST_A, "Drain Cleaning Knoxville TN")])
        self.post = self.gen(self.fake).get_json()["post"]
        self.qa_id = next(n for n, name in layouts.load_layouts().items() if name == QA_LAYOUT)

    def edit(self, outputs, **body):
        fake = FakeGemini(outputs)
        with mock.patch.object(gemini_client, "generate", fake):
            r = self.http.post(f"/api/posts/{self.post['id']}/edit", json=body)
        return r, fake

    def test_layout_change_asks_for_that_layout_and_saves_it(self):
        r, fake = self.edit([make_output(POST_QA, "Drain Cleaning Knoxville TN", layout=QA_LAYOUT)], layout=str(self.qa_id))
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["post"]["id"], self.post["id"])
        self.assertEqual(body["post"]["layout"], QA_LAYOUT)
        self.assertEqual(body["post"]["text"], POST_QA)
        sent = fake.calls[0][-1].text
        self.assertIn(QA_LAYOUT, sent)
        self.assertIn("at least 3 paragraphs", sent)
        self.assertEqual(len(db.get_posts(self.client_id)), 1)

    def test_wrong_layout_is_sent_back_for_a_fix(self):
        r, fake = self.edit([make_output(POST_B, "Drain Cleaning Knoxville TN", layout="Problem, then solution"),
                             make_output(POST_QA, "Drain Cleaning Knoxville TN", layout=QA_LAYOUT)], layout=str(self.qa_id))
        self.assertEqual(r.get_json()["post"]["layout"], QA_LAYOUT)
        self.assertIn("requested layout", fake.calls[1][-1].text)

    def test_unknown_layout_and_empty_request_are_rejected(self):
        self.assertEqual(self.edit([], layout="99")[0].status_code, 400)
        self.assertEqual(self.edit([], instruction="")[0].status_code, 400)


FOUR = POST_B + "\n\nWe also check the water heater while we are there. \u2705"


class ParagraphCountAndRandomTests(LayoutChangeTests):
    def test_paragraph_count_change(self):
        self.assertEqual(count_paragraphs(POST_A), 3)
        r, fake = self.edit([make_output(FOUR, "Drain Cleaning Knoxville TN")], paragraphs=4)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(count_paragraphs(body["post"]["text"]), 4)
        sent = fake.calls[0][-1].text
        self.assertIn("exactly 4 paragraphs", sent)
        self.assertIn("at least 3 paragraphs", sent)

    def test_wrong_paragraph_count_is_sent_back_for_a_fix(self):
        r, fake = self.edit([make_output(POST_B, "Drain Cleaning Knoxville TN"),
                             make_output(FOUR, "Drain Cleaning Knoxville TN")], paragraphs=4)
        self.assertEqual(count_paragraphs(r.get_json()["post"]["text"]), 4)
        self.assertIn("exactly 4 were requested", fake.calls[1][-1].text)

    def test_paragraph_count_must_be_3_to_6(self):
        for bad in (2, 7, "x"):
            self.assertEqual(self.edit([], paragraphs=bad)[0].status_code, 400)

    def test_random_layout_picks_a_new_layout_and_never_the_story_one(self):
        import re
        lib = layouts.load_layouts()
        seen = set()
        for _ in range(12):
            current = db.get_post(self.post["id"])["layout"]
            fake = FakeGemini([make_output(POST_QA, "Drain Cleaning Knoxville TN", layout=QA_LAYOUT)] * 3)
            with mock.patch.object(gemini_client, "generate", fake):
                self.http.post(f"/api/posts/{self.post['id']}/edit", json={"layout": "random"})
            name = re.search(r"exactly this layout from the library: (.+?)\. State", fake.calls[0][-1].text).group(1)
            self.assertNotEqual(name, current)
            seen.add(name)
        self.assertNotIn(lib[19], seen)
        self.assertGreater(len(seen), 3)


if __name__ == "__main__":
    unittest.main()
