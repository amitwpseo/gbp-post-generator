"""Generation pipeline: build prompt -> Gemini -> parse -> validate -> auto-fix -> save."""
import json
import uuid

import config
import layouts as layouts_mod
import db
import gemini_client
import options
from errors import UserError
from gemini_client import Turn
from output_parser import first_line, last_line, parse_output
from validators import emoji_matches, file_slug, length_label, opens_with_question, post_type_key, validate

FILENAME_RULE = (
    "Image filename: make it short and SEO optimized. 3 to 5 words and under 45 characters, Title Case, in this order: "
    "main service keyword, city, state abbreviation (for example \"Drain Cleaning Knoxville TN\"). Name what the photo "
    "shows or the service it supports. No filler words (the, and, in, for, your, best), no slogans, no hyphens, "
    "underscores or file extension. Never reuse a filename from the history."
)
PARAGRAPH_RULE = (
    "Paragraphs: every post must have at least 3 paragraphs, with one blank line between each paragraph. "
    "This applies to every layout. A list, steps, or Q&A block counts as a paragraph, and the opening and closing lines each stand alone."
)
LAYOUT_CHANGE_INSTRUCTION = (
    "Rewrite this post using exactly this layout from the library: {layout}. State it in section D. "
    "Keep the same facts, post type, photo, CTA URL and image filename. Change the opener and closer wording so it is not a light rewording."
)
PARAGRAPH_CHANGE_INSTRUCTION = (
    "Rewrite this post with exactly {n} paragraphs, with one blank line between each paragraph. Keep the same layout, "
    "facts, post type, photo, CTA URL and image filename, and keep the post in the same length band. Reflow the text so "
    "each paragraph reads naturally, do not just cut it apart or glue it together."
)
MIN_PARAS, MAX_PARAS = 3, 6
MISMATCH_OPTIONS = [
    "Send a different image that fits the page",
    "Send a different CTA page that fits the image",
    "Proceed anyway (not recommended)",
]
ANOTHER_INSTRUCTION = (
    "Produce a new post with a different layout, opener, closer, and filename. "
    "This must not be a light rewording of the previous post."
)
ANOTHER_FIXED_LAYOUT_INSTRUCTION = (
    "Produce a new post with a different opener, closer, filename, wording and angle than the previous post. "
    "This must not be a light rewording of the previous post."
)
FORCE_INSTRUCTION = (
    "The user reviewed the image and CTA mismatch and chose to proceed anyway. Write the post now. "
    "Keep it general, do not claim the photo shows work it does not show, and mention the mismatch in Notes."
)


# ---------- prompt building ----------
def format_nap(c: dict) -> str:
    lines = [c["name"]]
    for label, key in (("Address", "address"), ("Phone", "phone"), ("Website", "website"), ("GBP link", "gbp_link")):
        if c.get(key):
            lines.append(f"{label}: {c[key]}")
    return "\n".join(lines)


def format_history(history) -> str:
    if not history:
        return "(none yet, this is the first post for this client)"
    rows = []
    for i, h in enumerate(history, 1):
        rows.append(
            f"{i}. Layout: {h.get('layout') or 'unknown'} | Opener: {h.get('opener', '')} | "
            f"Closer: {h.get('closer', '')} | Filename: {h.get('filename', '')} | Length: {h.get('length', 0)}"
        )
    return "\n".join(rows)


def build_user_message(client, cta_url, page_text, history, filenames, global_layouts, special="") -> str:
    parts = [
        "CLIENT NAP:\n" + format_nap(client),
    ]
    if client.get("notes"):
        parts.append("BUSINESS NOTES (rules and context for this client):\n" + client["notes"])
    parts += [
        "CTA URL:\n" + cta_url,
        "CTA PAGE CONTENT:\n" + page_text[: config.MAX_PAGE_CHARS],
        "IMAGE:\n(the image is attached to this message)",
        "CLIENT POST HISTORY (most recent first):\n" + format_history(history),
        "LAST 3 LAYOUTS USED ACROSS ALL CLIENTS (most recent first):\n"
        + (", ".join(global_layouts) if global_layouts else "(none yet)"),
        "ALL IMAGE FILENAMES ALREADY USED FOR THIS CLIENT (never reuse any):\n"
        + ("\n".join(filenames[:80]) if filenames else "(none yet)"),
        "SPECIAL INSTRUCTIONS:\n" + (special.strip() or "(none)"),
    ]
    return "\n\n".join(parts)


def build_fix_message(errors, want_post=False) -> str:
    bullets = "\n".join(f"- {e}" for e in errors)
    head = "Your previous output failed these automated checks:\n" + bullets
    if want_post:
        head = "Your previous output did not include a post. " + bullets
    return (
        head
        + "\n\nFix this. Output the complete result again in the exact same format (sections A to D, and Notes "
        "only if needed), changing only what is needed to pass every check. If the problem is a repeated layout, "
        "opener, closer, or filename, choose a different one."
    )


# ---------- core loop ----------
def _history_context(client_id, exclude_id=None):
    history = db.get_posts(client_id, limit=5, exclude_id=exclude_id)
    return {
        "history": history,
        "filenames": db.all_filenames(client_id, exclude_id=exclude_id),
        "global_layouts": db.recent_layouts_global(3, exclude_id=exclude_id),
    }


def _run(turns, ctx, cta_url, special, force=False, requested=None, strict_filename=True):
    """Calls Gemini, then re-asks (up to MAX_FIX_ATTEMPTS) while checks fail. Returns a result dict."""
    raw = gemini_client.generate(turns)
    parsed = parse_output(raw)
    attempts = 0
    max_attempts = config.max_fix_attempts()
    while True:
        no_post = not parsed["post_text"]
        if no_post and parsed["match_status"] == "Mismatch" and not force:
            return {"kind": "mismatch", "parsed": parsed, "turns": turns, "attempts": attempts}
        if no_post:
            if attempts >= max_attempts:
                return {"kind": "unparsed", "parsed": parsed, "turns": turns, "attempts": attempts}
            problems = ["No post text was found in the output."]
            fix = build_fix_message(problems, want_post=True)
            if force:
                fix += " " + FORCE_INSTRUCTION
            validation = None
        else:
            validation = validate(
                parsed, history=ctx["history"], all_filenames=ctx["filenames"],
                global_layouts=ctx["global_layouts"], special_instructions=special, cta_url=cta_url,
                requested=requested, strict_filename=strict_filename,
            )
            if not validation["errors"] or attempts >= max_attempts:
                return {"kind": "ok" if not validation["errors"] else "flagged", "parsed": parsed,
                        "validation": validation, "turns": turns, "attempts": attempts, "raw": raw}
            fix = build_fix_message(validation["errors"])
        turns = list(turns) + [Turn("model", raw), Turn("user", fix)]
        raw = gemini_client.generate(turns)
        parsed = parse_output(raw)
        attempts += 1


def _post_json(post_row, validation=None, last_used=None):
    text = post_row["post_text"]
    return {
        "id": post_row["id"],
        "status": post_row["status"],
        "created_at": post_row["created_at"],
        "post_type": post_row["post_type"],
        "text": text,
        "cta_url": post_row["cta_url"],
        "filename": post_row["filename"],
        "layout": post_row["layout"],
        "last_used": last_used if last_used is not None else post_row.get("last_used", ""),
        "notes": [n for n in (post_row.get("notes") or "").split("\n") if n],
        "chars": len(text),
        "emojis": len(emoji_matches(text)),
        "length_label": length_label(len(text)),
        "match_status": post_row["match_status"],
        "match_pct": post_row["match_pct"],
        "client_id": post_row["client_id"],
        "has_image": bool(post_row.get("image_path")),
        "post_type_key": post_type_key(post_row["post_type"]),
        "file_name": file_slug(post_row["filename"]) + ".jpg",
        "type_details": _details_json(post_row),
    }


def _details_json(post_row):
    """The Offer or Event details the user typed, as [{label, value}] for display."""
    try:
        d = json.loads(post_row.get("type_details") or "{}")
    except ValueError:
        return []
    return [{"label": label, "value": value} for label, value in options.detail_rows(d.get("type"), d.get("values") or {})]


def _analysis_json(parsed):
    return {"match_status": parsed["match_status"], "match_pct": parsed["match_pct"], "reason": parsed["reason"]}


def _finish(result, client_id, cta_url, fixed_url_note, user_message, image_path, post_id=None, type_details=None):
    """Turns a loop result into the API response, saving the post unless it was a mismatch."""
    parsed = result["parsed"]
    if result["kind"] == "mismatch":
        return {"status": "mismatch", "analysis": _analysis_json(parsed), "options": MISMATCH_OPTIONS,
                "raw": parsed["raw"]}
    if result["kind"] == "unparsed":
        return {"status": "error", "error": "Gemini did not return a post in the expected format.",
                "raw": parsed["raw"], "analysis": _analysis_json(parsed)}

    notes = list(parsed["notes"])
    if fixed_url_note:
        notes.insert(0, fixed_url_note)
    text = parsed["post_text"]
    fields = dict(
        client_id=client_id,
        status="ok" if result["kind"] == "ok" else "flagged",
        layout=parsed["layout"], last_used=parsed["last_used"],
        opener=first_line(text), closer=last_line(text), filename=parsed["filename"], length=len(text),
        post_type=parsed["post_type"], post_text=text, cta_url=cta_url,
        match_status=parsed["match_status"], match_pct=parsed["match_pct"],
        notes="\n".join(notes), user_message=user_message, raw_output=result["raw"], image_path=image_path,
    )
    if type_details is not None:
        fields["type_details"] = type_details
    if post_id:
        db.update_post(post_id, **fields)
    else:
        post_id = db.add_post(**fields)
    row = db.get_post(post_id)
    return {
        "status": "ok" if result["kind"] == "ok" else "needs_review",
        "analysis": _analysis_json(parsed),
        "post": _post_json(row),
        "validation": result["validation"],
        "attempts": result["attempts"],
    }


# ---------- public entry points ----------
def generate_post(client, cta_url, page_text, image, special="", force=False, another=False,
                  fixed_url_note=None, scraped_chars=0, options_raw=None, type_details=None):
    ctx = _history_context(client["id"])
    recent3 = ctx["history"][:3]
    options_raw = dict(options_raw or {})
    if config.auto_randomize():
        for key in ("layout", "opener", "closer", "length", "tone"):
            if str(options_raw.get(key) or "auto").strip().lower() == "auto":
                options_raw[key] = "random"
    resolved = options.resolve(
        options_raw,
        avoid_layouts=[h.get("layout", "") for h in recent3] + list(ctx["global_layouts"]),
        avoid_question_opener=any(opens_with_question(h.get("opener", "")) for h in recent3),
        details=type_details,
    )
    another_text = ANOTHER_FIXED_LAYOUT_INSTRUCTION if resolved["layout"] else ANOTHER_INSTRUCTION
    effective = "\n".join(x for x in (
        special.strip(),
        FILENAME_RULE,
        PARAGRAPH_RULE,
        options.instruction_text(resolved),
        another_text if another else "",
        FORCE_INSTRUCTION if force else "",
    ) if x)
    user_message = build_user_message(client, cta_url, page_text, ctx["history"], ctx["filenames"],
                                      ctx["global_layouts"], effective)
    turns = [Turn("user", user_message, image)]
    result = _run(turns, ctx, cta_url, effective, force=force, requested=resolved)

    image_path = ""
    if result["kind"] in ("ok", "flagged"):
        image_path = f"{uuid.uuid4().hex}.jpg"
        (config.upload_dir() / image_path).write_bytes(image[0])
    stored = json.dumps({"type": resolved["post_type"], "values": resolved["type_details"]}) if resolved["type_details"] else ""
    resp = _finish(result, client["id"], cta_url, fixed_url_note, user_message, image_path, type_details=stored)
    resp["scraped_chars"] = scraped_chars
    resp["applied_options"] = options.describe(resolved)
    return resp


def edit_post(post, instruction, layout_id=None, paragraphs=None):
    """Rewrites an existing post per the user's instruction, keeping every rule.

    layout_id: a layout number, or "random". The post is rewritten in exactly that layout and the check requires it.
    paragraphs: rewrite with exactly this many paragraphs (3 to 6) and check it.
    """
    client_id = post["client_id"]
    ctx = _history_context(client_id, exclude_id=post["id"])
    requested = {}
    if layout_id:
        lib = layouts_mod.load_layouts()
        if str(layout_id) == "random":
            avoid = [post.get("layout", "")] + [h.get("layout", "") for h in ctx["history"][:3]] + list(ctx["global_layouts"])
            layout_name = options.resolve({"layout": "random"}, avoid_layouts=avoid)["layout"]
        else:
            try:
                layout_name = lib[int(layout_id)]
            except (ValueError, KeyError):
                raise UserError("Unknown layout.")
        instruction = LAYOUT_CHANGE_INSTRUCTION.format(layout=layout_name) + (" " + instruction.strip() if instruction.strip() else "")
        requested["layout"] = layout_name
    if paragraphs:
        try:
            paragraphs = int(paragraphs)
        except (TypeError, ValueError):
            raise UserError("Choose between 3 and 6 paragraphs.")
        if not MIN_PARAS <= paragraphs <= MAX_PARAS:
            raise UserError("Choose between 3 and 6 paragraphs.")
        instruction = (instruction.strip() + " " + PARAGRAPH_CHANGE_INSTRUCTION.format(n=paragraphs)).strip()
        requested["paragraphs"] = paragraphs
    instruction = instruction.strip() + "\n" + PARAGRAPH_RULE
    image = None
    if post.get("image_path"):
        p = config.upload_dir() / post["image_path"]
        if p.exists():
            image = (p.read_bytes(), "image/jpeg")
    turns = [
        Turn("user", post["user_message"], image),
        Turn("model", post["raw_output"]),
        Turn("user", instruction.strip()),
    ]
    # An edit keeps the photo's name, so older posts with a long filename are not forced to rename it.
    result = _run(turns, ctx, post["cta_url"], instruction, requested=requested or None, strict_filename=False)
    return _finish(result, client_id, post["cta_url"], None, post["user_message"], post["image_path"],
                   post_id=post["id"])


def update_text(post, text):
    """Saves a manual edit to the post text and re-runs the checks (the status is left to the user)."""
    text = (text or "").strip()
    if not text:
        raise UserError("The post text cannot be empty.")
    ctx = _history_context(post["client_id"], exclude_id=post["id"])
    parsed = {"post_text": text, "filename": post["filename"], "layout": post["layout"], "cta_url": post["cta_url"]}
    validation = validate(parsed, history=ctx["history"], all_filenames=ctx["filenames"],
                          global_layouts=ctx["global_layouts"], cta_url=post["cta_url"], strict_filename=False)
    old = post["post_text"]
    raw = post["raw_output"].replace(old, text, 1) if old and old in post["raw_output"] else post["raw_output"]
    db.update_post(post["id"], post_text=text, opener=first_line(text), closer=last_line(text),
                   length=len(text), raw_output=raw)
    return {"post": _post_json(db.get_post(post["id"])), "validation": validation}
