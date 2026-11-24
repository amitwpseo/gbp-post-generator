"""Fetches the CTA page and reduces it to readable text for the prompt."""
import ipaddress
import os
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GBPPostGenerator/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}
MAX_BYTES = 3 * 1024 * 1024


def normalize_url(url: str):
    """Fix common typos ('hhttps://', missing scheme). Returns (url, was_fixed)."""
    original = (url or "").strip()
    u = original
    u = re.sub(r"^h{2,}(ttps?://)", r"h\1", u, flags=re.I)
    u = re.sub(r"^https?:/+(?=[^/])", lambda m: m.group(0).split(":")[0] + "://", u, flags=re.I)
    if u and not re.match(r"^https?://", u, re.I):
        u = "https://" + u.lstrip("/")
    return u, u != original


def _is_public_host(host: str) -> bool:
    if os.environ.get("GBP_ALLOW_PRIVATE_URLS") == "1":
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = (meta.get("content") or "").strip() if meta else ""
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "aside", "template"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    if len(root.get_text(" ", strip=True)) < 300 and soup.body:
        root = soup.body
    lines, prev = [], None
    for raw in root.get_text("\n").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line and line != prev:
            lines.append(line)
        prev = line
    out = []
    if title:
        out.append(f"Page title: {title}")
    if description:
        out.append(f"Meta description: {description}")
    out.append("\n".join(lines))
    return "\n".join(out).strip()[: config.MAX_PAGE_CHARS]


def fetch_page_text(url: str):
    """Returns (text, error). error is a short human-readable string or None."""
    current = url
    try:
        for _ in range(5):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return "", "that is not a valid web address"
            if not _is_public_host(parsed.hostname):
                return "", "that address is not a public website"
            resp = requests.get(current, headers=HEADERS, timeout=(5, 15), allow_redirects=False, stream=True)
            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                current = urljoin(current, resp.headers.get("Location", ""))
                resp.close()
                continue
            if resp.status_code >= 400:
                return "", f"the site returned HTTP {resp.status_code}"
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype.lower() and "text" not in ctype.lower():
                return "", f"the page is not HTML ({ctype or 'unknown type'})"
            body = b""
            for chunk in resp.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            resp.close()
            text = html_to_text(body.decode(resp.encoding or "utf-8", errors="replace"))
            if len(text) < 200:
                return text, "the page has almost no readable text (it may load its content with JavaScript)"
            return text, None
        return "", "too many redirects"
    except requests.RequestException as e:
        return "", f"the request failed ({e.__class__.__name__})"
