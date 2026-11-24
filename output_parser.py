"""Turns Gemini's fixed-format output (sections A to D plus Notes) into a dict."""
import re

from layouts import normalize_layout

_CODE_RE = re.compile(r"```[^\n`]*\n?(.*?)```", re.S)
_LABEL_PREFIX = r"^[ \t>*_#\-]*"


def _clean(s: str) -> str:
    return re.sub(r"[*`]+", "", s or "").strip()


def _field(text: str, label: str) -> str:
    m = re.search(_LABEL_PREFIX + re.escape(label) + r"[ \t*_]*:[ \t*_]*(.*)$", text, re.I | re.M)
    return _clean(m.group(1)) if m else ""


def _block(text: str, label: str, stop_labels=()) -> str:
    m = re.search(_LABEL_PREFIX + re.escape(label) + r"[ \t*_]*:[ \t*_]*", text, re.I | re.M)
    if not m:
        return ""
    rest = text[m.end():]
    if stop_labels:
        stop = re.search(r"^[ \t>*_#]*(?:" + "|".join(stop_labels) + r")", rest, re.I | re.M)
        if stop:
            rest = rest[:stop.start()]
    return _clean(rest)


def _normalize_status(value: str) -> str:
    v = (value or "").lower()
    if "mismatch" in v or "mis-match" in v or "no match" in v:
        return "Mismatch"
    if "partial" in v:
        return "Partial Match"
    if "match" in v:
        return "Match"
    return ""


def _first_code_block_after(text: str, heading_regex: str) -> str:
    m = re.search(heading_regex, text, re.I | re.M)
    sub = text[m.start():] if m else text
    cb = _CODE_RE.search(sub)
    return cb.group(1).strip("\n").strip() if cb else ""


def parse_output(raw: str) -> dict:
    raw = raw or ""
    outside = _CODE_RE.sub("", raw)

    status = _normalize_status(_field(outside, "Match Status"))
    pct_text = _field(outside, "Match Percentage")
    pct_m = re.search(r"\d{1,3}", pct_text)
    pct = min(100, int(pct_m.group(0))) if pct_m else None
    reason = _block(outside, "Reason", [r"B\.\s", r"GBP Post Details", r"Post Type"])

    post_text = _first_code_block_after(raw, _LABEL_PREFIX + r"Post Text")
    if not post_text:
        m = re.search(_LABEL_PREFIX + r"Post Text[ \t*_]*:[ \t*_]*(.*?)(?=^[ \t>*_#]*CTA URL)", raw, re.I | re.M | re.S)
        if m:
            post_text = _clean(m.group(1))
    post_text = post_text.strip()

    filename = _first_code_block_after(raw, _LABEL_PREFIX + r"(?:C\.\s*)?Image Filename")
    if not filename:
        m = re.search(_LABEL_PREFIX + r"(?:C\.\s*)?Image Filename[^\n]*\n+\s*([^\n]+)", raw, re.I | re.M)
        if m:
            filename = _clean(m.group(1))
    filename = filename.strip().strip("`").strip()

    cta_val = _field(outside, "CTA URL")
    url_m = re.search(r"https?://[^\s)>\]]+", cta_val)
    cta_url = url_m.group(0) if url_m else cta_val

    layout_raw = _field(outside, "Layout")
    notes_text = _block(outside, "Notes")
    notes = [re.sub(r"^[\-•*\s]+", "", ln).strip() for ln in notes_text.splitlines()]
    notes = [n for n in notes if n]

    return {
        "match_status": status,
        "match_pct": pct,
        "reason": reason,
        "post_type": _field(outside, "Post Type"),
        "post_text": post_text,
        "cta_url": cta_url,
        "filename": filename,
        "layout_raw": layout_raw,
        "layout": normalize_layout(layout_raw),
        "last_used": _block(outside, "Last used", [r"Approx", r"Notes", r"Do not"]),
        "notes": notes,
        "raw": raw,
    }


def first_line(text: str) -> str:
    for ln in (text or "").splitlines():
        if ln.strip():
            return ln.strip()
    return ""


def last_line(text: str) -> str:
    for ln in reversed((text or "").splitlines()):
        if ln.strip():
            return ln.strip()
    return ""
