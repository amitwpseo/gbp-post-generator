"""Server-side checks that back up the rules in the system prompt."""
import difflib
import re

from options import LENGTHS
from output_parser import first_line, last_line

DASH_RE = re.compile("[—–]")
PHONE_RES = [
    re.compile(r"(?<!\d)(?:\+?\d{1,2}[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}[\s.\-]\d{4}(?!\d)"),
]
EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")
URL_RE = re.compile(
    r"https?://\S+|www\.\S+|\b[a-z0-9\-]+\.(?:com|net|org|io|co|us|biz|info|app|dev|ai)\b", re.I
)
BANNED_PHRASES = ["learn more", "call now"]
PRICE_RE = re.compile(r"\$\s?\d")

_E = (
    "[\U0001F000-\U0001FAFF"
    "☀-⛿"
    "✂✅✈-✍✏✒✖✝✡✨✳✴❄❇"
    "❌❎❓-❕❗❣❤➕-➗➡➰➿"
    "⬅-⬇⬛⬜⭐⭕"
    "⌚⌛⏩-⏳⏸-⏺⤴⤵]"
)
EMOJI_RE = re.compile(
    "(?:" + _E + "|✔️)[️\U0001F3FB-\U0001F3FF]?(?:‍" + _E + "️?)*"
)


def emoji_matches(text: str):
    return list(EMOJI_RE.finditer(text or ""))


def opens_with_question(line: str) -> bool:
    m = re.match(r"[^.!?\n]*[.!?]", line or "")
    return bool(m and m.group(0).endswith("?"))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (s or "").lower()).strip()


def length_label(n: int) -> str:
    if n <= 450:
        return "short"
    if n <= 800:
        return "standard"
    return "long"


FILENAME_MAX_WORDS = 5
FILENAME_MAX_CHARS = 45
FILENAME_FILLER = {"a", "an", "the", "and", "or", "of", "in", "for", "to", "with", "at", "on", "by", "your", "our", "my", "best", "top"}


def file_slug(name: str) -> str:
    """The SEO form of an image filename: lowercase words joined with hyphens ('Drain Cleaning Knoxville TN' becomes
    'drain-cleaning-knoxville-tn')."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "gbp-photo"


def check_filename(name: str, prior_filenames, strict: bool = True) -> list:
    """strict=False only checks that there is a name and that it is not a repeat (used for older posts and manual edits)."""
    errs = []
    if not name:
        return ["The image filename is missing."]
    if strict:
        if re.search(r"[\-_.]", name):
            errs.append("The image filename must not contain hyphens, underscores, or a file extension.")
        words = name.split()
        if not 3 <= len(words) <= FILENAME_MAX_WORDS:
            errs.append(f"The image filename must be 3 to {FILENAME_MAX_WORDS} words (it has {len(words)}). "
                        "Keep it short: main service keyword, city, state abbreviation.")
        if len(name) > FILENAME_MAX_CHARS:
            errs.append(f"The image filename is {len(name)} characters. Keep it under {FILENAME_MAX_CHARS}.")
        filler = [w for w in words if w.lower() in FILENAME_FILLER]
        if filler:
            errs.append("The image filename has filler words (" + ", ".join(filler) + "). Remove them, keep only keywords.")
        if any(not (w[0].isupper() or w[0].isdigit()) for w in words):
            errs.append("The image filename must be Title Case, with every word capitalized.")
    if name.lower() in {f.lower() for f in prior_filenames if f}:
        errs.append(f'The image filename "{name}" was already used for this client. Choose a new one.')
    return errs


MIN_PARAGRAPHS = 3


def count_paragraphs(text: str) -> int:
    """Blocks of text separated by at least one blank line."""
    return len([b for b in re.split(r"\n\s*\n", (text or "").strip()) if b.strip()])


def post_type_key(value: str) -> str:
    """Maps Gemini's 'Post Type' text to update / offer / event ('' if unknown)."""
    v = (value or "").lower()
    if "offer" in v:
        return "offer"
    if "event" in v:
        return "event"
    if "update" in v or "what" in v:
        return "update"
    return ""


def validate(parsed, *, history, all_filenames, global_layouts=(), special_instructions="", cta_url=None,
             requested=None, strict_filename=True):
    """history: this client's posts, newest first (dicts with layout/opener/closer/filename).

    requested: resolved user options (layout/length/opener/closer/emojis) that the post must honor.
    """
    requested = requested or {}
    errors, warnings = [], []
    text = parsed.get("post_text", "")
    chars = len(text)
    emojis = emoji_matches(text)

    if not text:
        errors.append("No post text was found in the output.")
        return {"errors": errors, "warnings": warnings,
                "stats": {"chars": 0, "emojis": 0, "length_label": ""}}

    if DASH_RE.search(text) or DASH_RE.search(parsed.get("filename", "")):
        errors.append("The post contains an em dash or en dash. Use commas, periods, or colons instead.")
    if any(r.search(text) for r in PHONE_RES):
        errors.append("The post body contains a phone number. Phone numbers are not allowed in the post body.")
    if EMAIL_RE.search(text):
        errors.append("The post body contains an email address. Remove it.")
    if URL_RE.search(text):
        errors.append("The post body contains a URL or domain name. URLs belong only in the CTA URL field.")
    if re.search(r"\*|`|__|^\s*#", text, re.M):
        errors.append("The post text contains markdown (asterisks, backticks, underscores, or headers). GBP does not support formatting.")
    low = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            errors.append(f'The post uses the banned phrase "{phrase.title()}".')
    paragraphs = count_paragraphs(text)
    if paragraphs < MIN_PARAGRAPHS:
        errors.append(f"The post has {paragraphs} paragraph{'s' if paragraphs != 1 else ''}. Every post needs at least "
                      f"{MIN_PARAGRAPHS} paragraphs, with a blank line between each one.")
    want_paras = requested.get("paragraphs")
    if want_paras and paragraphs != want_paras:
        errors.append(f"The post has {paragraphs} paragraph{'s' if paragraphs != 1 else ''}, but exactly {want_paras} were requested. "
                      "Separate paragraphs with one blank line.")
    if chars > 1500:
        errors.append(f"The post is {chars} characters. The hard limit is 1,500.")
    elif chars > 1200:
        warnings.append(f"The post is {chars} characters, longer than the 'long' band (900 to 1200).")
    elif chars < 200:
        warnings.append(f"The post is only {chars} characters, shorter than the 'short' band (250 to 450).")
    want_len = requested.get("length")
    if want_len:
        lo, hi = LENGTHS[want_len]["range"]
        if not (lo * 0.9 <= chars <= hi * 1.1):
            errors.append(f"The post is {chars} characters, but a {want_len} post ({lo} to {hi} characters) was requested.")
    want_emojis = requested.get("emojis")
    if want_emojis:
        if len(emojis) != want_emojis:
            errors.append(f"The post has {len(emojis)} emojis, but exactly {want_emojis} were requested.")
    elif len(emojis) == 0:
        errors.append("The post has no emojis. Use 2 to 4 (1 or 2 is acceptable for some posts).")
    elif len(emojis) > 4:
        errors.append(f"The post has {len(emojis)} emojis. The maximum is 4.")
    if any(a.end() == b.start() for a, b in zip(emojis, emojis[1:])):
        errors.append("Emojis are stacked next to each other. Place them separately within the text.")
    if PRICE_RE.search(text) and "$" not in (special_instructions or ""):
        warnings.append("The post mentions a price. Confirm with the client that it is current.")

    errors.extend(check_filename(parsed.get("filename", ""), all_filenames, strict=strict_filename))

    layout = parsed.get("layout", "")
    recent_layouts = [h.get("layout", "") for h in history[:3]]
    want_layout = requested.get("layout")
    if want_layout:
        if not layout:
            errors.append("The output did not say which layout was used in section D.")
        elif layout != want_layout:
            errors.append(f'The requested layout was "{want_layout}", but the post used "{layout}".')
        elif recent_layouts and layout == recent_layouts[0]:
            warnings.append("This is the same layout as this client's most recent post (you asked for it).")
    else:
        if layout and recent_layouts and layout == recent_layouts[0]:
            errors.append(f'The layout "{layout}" is the same as this client\'s most recent post. Choose a different layout.')
        elif layout and layout in recent_layouts:
            warnings.append(f'The layout "{layout}" was used in one of this client\'s last 3 posts.')
        if layout and layout in list(global_layouts)[:3]:
            warnings.append(f'The layout "{layout}" was used recently for another client too.')

    want_type = requested.get("post_type")
    if want_type:
        got = post_type_key(parsed.get("post_type", ""))
        if got != want_type:
            wanted = {"update": "an Update", "offer": "an Offer", "event": "an Event"}[want_type]
            shown = parsed.get("post_type") or "no post type"
            if requested.get("type_details") or want_type == "update":
                errors.append(f'{wanted} post was requested, but the output says "{shown}". Write it as {wanted}.')
            else:
                warnings.append(f'You asked for {wanted}, but Gemini wrote "{shown}". The page may not have a real '
                                f'{"offer" if want_type == "offer" else "dated event"}. Check the notes, or add the details yourself.')

    opener = first_line(text)
    closer = last_line(text)
    last3 = history[:3]
    want_opener = requested.get("opener")
    if want_opener == "question" and not opens_with_question(opener):
        errors.append("A question opener was requested, but the post does not open with a question.")
    elif want_opener == "statement" and opens_with_question(opener):
        errors.append("A plain statement opener was requested, but the post opens with a question.")
    if requested.get("closer") == "question" and "?" not in closer:
        errors.append("A question closer was requested, but the last line is not a question.")
    if (want_opener != "question" and opens_with_question(opener)
            and any(opens_with_question(h.get("opener", "")) for h in last3)):
        errors.append("The post opens with a question, but one of this client's last 3 posts did too.")
    for h in last3:
        prev = _norm(h.get("closer", ""))
        if prev and difflib.SequenceMatcher(None, _norm(closer), prev).ratio() >= 0.85:
            errors.append("The closing line is too similar to the closing line of one of this client's last 3 posts.")
            break
    for h in last3:
        prev = _norm(h.get("opener", ""))
        if prev and difflib.SequenceMatcher(None, _norm(opener), prev).ratio() >= 0.85:
            errors.append("The opening line is too similar to the opening line of one of this client's last 3 posts.")
            break

    if cta_url and parsed.get("cta_url") and parsed["cta_url"].rstrip("/") != cta_url.rstrip("/"):
        warnings.append("Gemini returned a different CTA URL than the one you entered. The app uses the one you entered.")

    return {"errors": errors, "warnings": warnings,
            "stats": {"chars": chars, "emojis": len(emojis), "length_label": length_label(chars)}}
