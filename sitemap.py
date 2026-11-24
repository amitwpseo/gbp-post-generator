"""Sitemap support: when the CTA field holds a sitemap link, read it and let Gemini pick the page that best fits the photo."""
import re
import time
from urllib.parse import urlparse

import requests

import gemini_client
import scraper
from errors import UserError
from gemini_client import Turn

MAX_URLS = 400
MAX_CHILD_SITEMAPS = 8
_SKIP_EXT = re.compile(r"\.(jpe?g|png|gif|webp|svg|pdf|zip|mp4|mov|css|js)(\?.*)?$", re.I)
_LOC_RE = re.compile(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", re.I | re.S)
_CACHE = {}  # sitemap url -> (timestamp, [page urls])
CACHE_SECONDS = 600

SYSTEM = (
    "You match a photo to the best page of a business website. You get the photo and a numbered list of page URLs "
    "from the site's sitemap. Pick the page whose topic the photo fits best, for example a photo of a windshield "
    "being replaced fits the windshield replacement page, a photo of the building fits the home or about page. "
    "Prefer service, product and location pages. Avoid pages the business already used recently, privacy, terms, "
    "thank-you, cart, login and tag pages. Reply with only the numbers of your best 3 matches, best first, "
    "separated by commas (for example: 14, 3, 27). No words."
)


def looks_like_sitemap(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".xml") or "sitemap" in path


def _get(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UserError("That sitemap link is not a valid web address.")
    if not scraper._is_public_host(parsed.hostname):
        raise UserError("That sitemap address is not a public website.")
    try:
        resp = requests.get(url, headers=scraper.HEADERS, timeout=(5, 20), stream=True)
        if resp.status_code >= 400:
            raise UserError(f"I could not read the sitemap (the site returned HTTP {resp.status_code}). "
                            "Enter the page link yourself instead.", 422)
        body = b""
        for chunk in resp.iter_content(65536):
            body += chunk
            if len(body) > 5 * 1024 * 1024:
                break
        resp.close()
        return body.decode(resp.encoding or "utf-8", errors="replace")
    except requests.RequestException as e:
        raise UserError(f"I could not read the sitemap ({e.__class__.__name__}). Enter the page link yourself instead.", 422)


def _locs(xml: str) -> list:
    return [m.strip() for m in _LOC_RE.findall(xml)]


def page_urls(sitemap_url: str) -> list:
    """All page URLs in a sitemap or sitemap index (up to MAX_URLS), without images and files."""
    hit = _CACHE.get(sitemap_url)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    locs = _locs(_get(sitemap_url))
    pages = []
    children = [u for u in locs if u.lower().split("?")[0].endswith(".xml")]
    if children:
        # prefer page and service sitemaps over posts, categories and tags
        children.sort(key=lambda u: (0 if re.search(r"page|service|location|area", u, re.I) else
                                     2 if re.search(r"tag|categor|author|attachment", u, re.I) else 1))
        for child in children[:MAX_CHILD_SITEMAPS]:
            try:
                pages += [u for u in _locs(_get(child)) if not u.lower().split("?")[0].endswith(".xml")]
            except UserError:
                continue
            if len(pages) >= MAX_URLS:
                break
    else:
        pages = locs
    seen, out = set(), []
    for u in pages:
        if u not in seen and not _SKIP_EXT.search(u):
            seen.add(u)
            out.append(u)
    if not out:
        raise UserError("I found no page links in that sitemap. Enter the page link yourself instead.", 422)
    out = out[:MAX_URLS]
    _CACHE[sitemap_url] = (time.time(), out)
    return out


def parse_choices(raw: str, count: int) -> list:
    picks = []
    for n in re.findall(r"\d+", raw or ""):
        i = int(n)
        if 1 <= i <= count and i not in picks:
            picks.append(i)
    return picks[:3]


def pick_pages(sitemap_url: str, image, recent_urls=(), business="") -> list:
    """Returns up to 3 page URLs from the sitemap, best match for the photo first."""
    urls = page_urls(sitemap_url)
    lines = "\n".join(f"{i}. {u}" for i, u in enumerate(urls, 1))
    prompt = f"Business: {business or 'unknown'}\n\nPage URLs:\n{lines}"
    recent = [u for u in recent_urls if u]
    if recent:
        prompt += "\n\nPages already used for recent posts (avoid unless nothing else fits):\n" + "\n".join(recent[:15])
    raw = gemini_client.generate([Turn("user", prompt, image)], system=SYSTEM, temperature=0.2)
    picks = parse_choices(raw, len(urls))
    if not picks:
        raise UserError("Gemini could not pick a page from the sitemap. Enter the page link yourself instead.", 422)
    return [urls[i - 1] for i in picks]
