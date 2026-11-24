"""User-selectable post options (post type, layout, length, opener, closer, tone, emojis) and the 'random' mode.

Every option accepts "auto" (Gemini decides, the default), "random" (the app picks, avoiding recent repeats),
or a specific choice. Random picks are resolved here, before the request, so the prompt and the server-side
checks both know exactly what was asked for.
"""
import random

import layouts as layouts_mod
from errors import UserError

LENGTHS = {
    "short": {"label": "Short (250 to 450 characters)", "range": (250, 450)},
    "standard": {"label": "Standard (500 to 800 characters)", "range": (500, 800)},
    "long": {"label": "Long (900 to 1200 characters)", "range": (900, 1200)},
}
OPENERS = {
    "statement": ("Plain statement", "Open with a plain statement. Do not open with a question."),
    "question": ("Question hook", "Open with a short question that hooks the reader."),
    "fragments": ("Three fragments", "Open with three bare fragments, then continue."),
    "scene": ("Scene from the photo", "Open by describing what the photo clearly shows."),
    "didyouknow": ("Did you know", 'Open with a "Did you know" fact that comes from the page content.'),
}
CLOSERS = {
    "pointer": ("Point to the page", "Close with a line that points readers to the page for details."),
    "invite": ("Invite details", "Close by inviting readers to send details about their situation."),
    "reassurance": ("Reassurance", "Close with a one-line reassurance."),
    "question": ("Short question", "Close with a short question."),
    "command": ("Short command", "Close with a short, friendly command."),
}
TONES = {
    "friendly": ("Friendly", "Write in a warm, conversational tone."),
    "professional": ("Professional", "Write in a calm, professional tone."),
    "educational": ("Educational", "Write in a helpful, educational tone that explains why it matters."),
    "direct": ("Direct", "Write in a direct, no-fluff tone with short sentences."),
}
EMOJI_CHOICES = (1, 2, 3, 4)
POST_TYPES = {
    "update": "Update (What's New)",
    "offer": "Offer",
    "event": "Event",
}
# Details the user can type for Offer and Event posts. They are passed to Gemini as confirmed facts
# and shown next to the result, because Google asks for them in separate fields.
DETAIL_FIELDS = {
    "offer": (("offer_title", "Offer title"), ("offer_start", "Starts"), ("offer_end", "Ends"),
              ("offer_code", "Coupon code"), ("offer_terms", "Terms")),
    "event": (("event_title", "Event title"), ("event_start", "Starts"), ("event_end", "Ends")),
}
ALL_DETAIL_KEYS = tuple(k for rows in DETAIL_FIELDS.values() for k, _ in rows)
# Layout 19 needs a real story or testimonial as source material, so "random" never picks it.
NEVER_RANDOM_LAYOUTS = {19}
FIELDS = ("post_type", "layout", "length", "opener", "closer", "tone", "emojis")


def catalog() -> dict:
    lib = layouts_mod.load_layouts()
    return {
        "post_types": [{"id": k, "name": v} for k, v in POST_TYPES.items()],
        "layouts": [{"id": str(n), "name": name} for n, name in sorted(lib.items())],
        "lengths": [{"id": k, "name": v["label"]} for k, v in LENGTHS.items()],
        "openers": [{"id": k, "name": v[0]} for k, v in OPENERS.items()],
        "closers": [{"id": k, "name": v[0]} for k, v in CLOSERS.items()],
        "tones": [{"id": k, "name": v[0]} for k, v in TONES.items()],
        "emojis": [{"id": str(n), "name": f"{n} emoji" + ("s" if n > 1 else "")} for n in EMOJI_CHOICES],
    }


def _choice(raw, table, label):
    if raw not in table:
        raise UserError(f"Unknown {label} option.")
    return raw


def resolve(raw, *, avoid_layouts=(), avoid_question_opener=False, rng=random, details=None) -> dict:
    """Turns form values ('auto' / 'random' / a choice) into concrete choices.

    Returns the resolved values (None = Gemini decides) plus 'random_fields', the options the app picked at random.
    """
    raw = {k: str(v).strip().lower() if v not in (None, "") else "auto" for k, v in (raw or {}).items()}
    out = {k: None for k in FIELDS}
    random_fields = []
    lib = layouts_mod.load_layouts()

    v = raw.get("post_type", "auto")
    if v == "random":
        # Offer and Event need a real offer or dated event, so a random pick could push Gemini to invent one.
        raise UserError("Post type cannot be random. Choose Auto, Update, Offer or Event.")
    if v != "auto":
        out["post_type"] = _choice(v, POST_TYPES, "post type")
    out["type_details"] = {}
    if out["post_type"] in DETAIL_FIELDS:
        for key, label in DETAIL_FIELDS[out["post_type"]]:
            value = " ".join(str((details or {}).get(key) or "").split())[:300]
            if value:
                out["type_details"][key] = value

    v = raw.get("layout", "auto")
    if v == "random":
        allowed = {n: name for n, name in lib.items() if n not in NEVER_RANDOM_LAYOUTS}
        pool = [n for n, name in allowed.items() if name not in avoid_layouts] or list(allowed)
        out["layout"] = lib[rng.choice(pool)]
        random_fields.append("layout")
    elif v != "auto":
        try:
            out["layout"] = lib[int(v)]
        except (ValueError, KeyError):
            raise UserError("Unknown layout option.")

    v = raw.get("length", "auto")
    if v == "random":
        out["length"] = rng.choices(list(LENGTHS), weights=[3, 5, 2])[0]
        random_fields.append("length")
    elif v != "auto":
        out["length"] = _choice(v, LENGTHS, "length")

    v = raw.get("opener", "auto")
    if v == "random":
        pool = [k for k in OPENERS if not (k == "question" and avoid_question_opener)]
        out["opener"] = rng.choice(pool)
        random_fields.append("opener")
    elif v != "auto":
        out["opener"] = _choice(v, OPENERS, "opener")

    v = raw.get("closer", "auto")
    if v == "random":
        out["closer"] = rng.choice(list(CLOSERS))
        random_fields.append("closer")
    elif v != "auto":
        out["closer"] = _choice(v, CLOSERS, "closer")

    v = raw.get("tone", "auto")
    if v == "random":
        out["tone"] = rng.choice(list(TONES))
        random_fields.append("tone")
    elif v != "auto":
        out["tone"] = _choice(v, TONES, "tone")

    v = raw.get("emojis", "auto")
    if v == "random":
        out["emojis"] = rng.choices(EMOJI_CHOICES, weights=[1, 4, 4, 2])[0]
        random_fields.append("emojis")
    elif v != "auto":
        try:
            n = int(v)
        except ValueError:
            raise UserError("Unknown emoji option.")
        if n not in EMOJI_CHOICES:
            raise UserError("Unknown emoji option.")
        out["emojis"] = n

    out["random_fields"] = random_fields
    return out


def detail_rows(post_type, details):
    """[(label, value)] for the details the user typed, in display order."""
    return [(label, details[key]) for key, label in DETAIL_FIELDS.get(post_type or "", ()) if details.get(key)]


def _post_type_line(r):
    t = r.get("post_type")
    if not t:
        return ""
    if t == "update":
        return "Post type: Update (What's New). Write a regular update, not an offer or an event."
    rows = detail_rows(t, r.get("type_details") or {})
    noun = "offer" if t == "offer" else "dated event"
    if rows:
        facts = "; ".join(f"{label}: {value}" for label, value in rows)
        return (f"Post type: {POST_TYPES[t]}. The user confirmed these {t} details, use them as facts and do not add "
                f"any others: {facts}. Mention the {t} clearly in the post text and write {POST_TYPES[t]} as the Post Type.")
    return (f"Post type: {POST_TYPES[t]}, but only if the CTA page content contains a real {noun} with dates. "
            f"If it does not, write an Update (What's New) instead, write Update as the Post Type, and add a note "
            f"saying no real {noun} was found on the page.")


def instruction_text(r: dict) -> str:
    lines = []
    if r.get("post_type"):
        lines.append(_post_type_line(r))
    if r.get("layout"):
        lines.append(f"Layout: use exactly this layout from the library: {r['layout']}. State it in section D.")
    if r.get("length"):
        lo, hi = LENGTHS[r["length"]]["range"]
        lines.append(f"Length: write a {r['length']} post of {lo} to {hi} characters.")
    if r.get("opener"):
        lines.append("Opener: " + OPENERS[r["opener"]][1])
    if r.get("closer"):
        lines.append("Closer: " + CLOSERS[r["closer"]][1])
    if r.get("tone"):
        lines.append("Tone: " + TONES[r["tone"]][1])
    if r.get("emojis"):
        lines.append(f"Emojis: use exactly {r['emojis']} emoji{'s' if r['emojis'] > 1 else ''}, not stacked.")
    if not lines:
        return ""
    return "Requested for this post (follow these together with every rule above):\n" + "\n".join("- " + ln for ln in lines)


def describe(r: dict) -> list:
    """What was applied, for display next to the result."""
    rand = set(r.get("random_fields", []))
    rows = []
    if r.get("post_type"):
        rows.append(("post_type", "Post type", POST_TYPES[r["post_type"]]))
    if r.get("layout"):
        rows.append(("layout", "Layout", r["layout"]))
    if r.get("length"):
        rows.append(("length", "Length", LENGTHS[r["length"]]["label"]))
    if r.get("opener"):
        rows.append(("opener", "Opener", OPENERS[r["opener"]][0]))
    if r.get("closer"):
        rows.append(("closer", "Closer", CLOSERS[r["closer"]][0]))
    if r.get("tone"):
        rows.append(("tone", "Tone", TONES[r["tone"]][0]))
    if r.get("emojis"):
        rows.append(("emojis", "Emojis", str(r["emojis"])))
    return [{"field": label, "value": value, "random": key in rand} for key, label, value in rows]
