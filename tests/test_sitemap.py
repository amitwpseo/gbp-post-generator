import unittest
from unittest import mock

import config
import sitemap
from errors import UserError

INDEX = "<sitemapindex><sitemap><loc>https://x.com/page-sitemap.xml</loc></sitemap><sitemap><loc>https://x.com/post-sitemap.xml</loc></sitemap></sitemapindex>"
PAGES = "<urlset><url><loc>https://x.com/windshield-repair/</loc></url><url><loc>https://x.com/logo.png</loc></url><url><loc>https://x.com/about/</loc></url></urlset>"


class SitemapTests(unittest.TestCase):
    def setUp(self):
        sitemap._CACHE.clear()

    def test_detects_sitemap_links(self):
        for u in ("https://x.com/sitemap.xml", "https://x.com/sitemaps.xml", "https://x.com/wp-sitemap.xml", "https://x.com/page-sitemap.xml"):
            self.assertTrue(sitemap.looks_like_sitemap(u), u)
        self.assertFalse(sitemap.looks_like_sitemap("https://x.com/windshield-repair/"))

    def test_reads_index_and_skips_images(self):
        docs = {"https://x.com/sitemap.xml": INDEX, "https://x.com/page-sitemap.xml": PAGES,
                "https://x.com/post-sitemap.xml": "<urlset><url><loc>https://x.com/blog/a/</loc></url></urlset>"}
        with mock.patch.object(sitemap, "_get", side_effect=lambda u: docs[u]):
            urls = sitemap.page_urls("https://x.com/sitemap.xml")
        self.assertEqual(urls, ["https://x.com/windshield-repair/", "https://x.com/about/", "https://x.com/blog/a/"])

    def test_pick_pages_uses_gemini_numbers(self):
        with mock.patch.object(sitemap, "page_urls", return_value=["https://x.com/a/", "https://x.com/b/", "https://x.com/c/"]), \
             mock.patch.object(sitemap.gemini_client, "generate", return_value="2, 9, 1"):
            self.assertEqual(sitemap.pick_pages("https://x.com/sitemap.xml", (b"x", "image/jpeg")),
                             ["https://x.com/b/", "https://x.com/a/"])

    def test_pick_pages_errors_when_nothing_usable(self):
        with mock.patch.object(sitemap, "page_urls", return_value=["https://x.com/a/"]), \
             mock.patch.object(sitemap.gemini_client, "generate", return_value="none"):
            with self.assertRaises(UserError):
                sitemap.pick_pages("https://x.com/sitemap.xml", (b"x", "image/jpeg"))


class RandomizeTests(unittest.TestCase):
    def test_flag(self):
        with mock.patch.dict("os.environ", {"GBP_RANDOMIZE_AUTO": "1"}):
            self.assertTrue(config.auto_randomize())
        with mock.patch.dict("os.environ", {"GBP_RANDOMIZE_AUTO": "0"}):
            self.assertFalse(config.auto_randomize())
