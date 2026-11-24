"""Local web app: GBP post generator powered by the Gemini API."""
import os
import re
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

import config
import db
import emoji_ai
import images
import options
import scraper
import service
import sitemap
from errors import UserError
from gemini_client import GeminiError
from validators import file_slug

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


@app.errorhandler(UserError)
def _user_error(e):
    return jsonify({"status": "error", "error": str(e)}), e.status


@app.errorhandler(GeminiError)
def _gemini_error(e):
    return jsonify({"status": "error", "error": str(e)}), e.status


@app.errorhandler(413)
def _too_big(_):
    return jsonify({"status": "error", "error": "That upload is too large."}), 413


def _client_or_404(client_id):
    client = db.get_client(client_id)
    if not client:
        raise UserError("Client not found.", 404)
    return client


def _client_payload(data):
    name = (data.get("name") or "").strip()
    if not name:
        raise UserError("The business name is required.")
    return {k: (data.get(k) or "").strip() for k in db.CLIENT_COLS}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def api_status():
    return jsonify({"model": config.models()[0], "fallbacks": config.models()[1:], "has_key": bool(config.api_key())})


@app.get("/api/options")
def api_options():
    return jsonify(options.catalog())


# ---- clients ----
@app.get("/api/clients")
def api_clients():
    return jsonify(db.list_clients())


@app.post("/api/clients")
def api_client_create():
    return jsonify(db.create_client(_client_payload(request.get_json(force=True, silent=True) or {}))), 201


@app.put("/api/clients/<int:client_id>")
def api_client_update(client_id):
    _client_or_404(client_id)
    return jsonify(db.update_client(client_id, _client_payload(request.get_json(force=True, silent=True) or {})))


@app.delete("/api/clients/<int:client_id>")
def api_client_delete(client_id):
    _client_or_404(client_id)
    for p in db.get_posts(client_id, status=None):
        _remove_image(p)
    db.delete_client(client_id)
    return jsonify({"ok": True})


@app.get("/api/clients/<int:client_id>/posts")
def api_client_posts(client_id):
    _client_or_404(client_id)
    return jsonify([service._post_json(p) for p in db.get_posts(client_id, limit=30, status=None)])


# ---- posts ----
def _remove_image(post):
    if post.get("image_path"):
        try:
            (config.upload_dir() / post["image_path"]).unlink(missing_ok=True)
        except OSError:
            pass


def _post_or_404(post_id):
    post = db.get_post(post_id)
    if not post:
        raise UserError("Post not found.", 404)
    return post


@app.get("/api/posts/<int:post_id>")
def api_post(post_id):
    return jsonify(service._post_json(_post_or_404(post_id)))


@app.post("/api/posts/<int:post_id>/accept")
def api_post_accept(post_id):
    _post_or_404(post_id)
    db.update_post(post_id, status="ok")
    return jsonify(service._post_json(db.get_post(post_id)))


@app.delete("/api/posts/<int:post_id>")
def api_post_delete(post_id):
    post = _post_or_404(post_id)
    _remove_image(post)
    db.delete_post(post_id)
    return jsonify({"ok": True})


@app.post("/api/posts/<int:post_id>/edit")
def api_post_edit(post_id):
    post = _post_or_404(post_id)
    data = request.get_json(force=True, silent=True) or {}
    instruction = (data.get("instruction") or "").strip()
    layout_id = str(data.get("layout") or "").strip()
    paragraphs = data.get("paragraphs")
    if not instruction and not layout_id and not paragraphs:
        raise UserError("Tell me what to change, for example: make it shorter.")
    return jsonify(service.edit_post(post, instruction, layout_id=layout_id or None, paragraphs=paragraphs))


@app.get("/api/posts/<int:post_id>/image")
def api_post_image(post_id):
    """The post's photo. With ?download=1 it is saved under the generated filename, ready to upload to GBP."""
    post = _post_or_404(post_id)
    name = Path(post.get("image_path") or "").name
    path = config.upload_dir() / name if name else None
    if not path or not path.exists():
        raise UserError("No photo is stored for this post.", 404)
    return send_file(path, mimetype="image/jpeg", as_attachment=request.args.get("download") == "1",
                     download_name=file_slug(post["filename"]) + ".jpg", max_age=3600)


@app.patch("/api/posts/<int:post_id>/text")
def api_post_text(post_id):
    post = _post_or_404(post_id)
    text = (request.get_json(force=True, silent=True) or {}).get("text") or ""
    return jsonify(service.update_text(post, text))


@app.post("/api/emoji/suggest")
def api_emoji_suggest():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"emojis": emoji_ai.suggest(data.get("query"), data.get("context"))})


# ---- generate ----
@app.post("/api/generate")
def api_generate():
    form = request.form
    try:
        client_id = int(form.get("client_id") or 0)
    except ValueError:
        client_id = 0
    client = _client_or_404(client_id)

    cta_raw = (form.get("cta_url") or "").strip()
    if not cta_raw:
        raise UserError("Please enter the CTA URL.")
    cta_url, was_fixed = scraper.normalize_url(cta_raw)
    fixed_note = f"CTA URL typo corrected: {cta_raw} became {cta_url}." if was_fixed else None

    upload = request.files.get("image")
    if not upload or not upload.filename:
        raise UserError("Please attach an image.")
    image = images.prepare_image(upload.read())

    page_text = (form.get("page_content") or "").strip()
    scraped_chars = 0
    if sitemap.looks_like_sitemap(cta_url):
        # A sitemap link was entered: pick the page that best fits the photo, then use it as the CTA.
        recent = [p.get("cta_url") for p in db.get_posts(client["id"], limit=15, status=None)]
        candidates = sitemap.pick_pages(cta_url, image, recent_urls=recent, business=client["name"])
        sitemap_link, chosen, err = cta_url, None, None
        for cand in candidates:
            if page_text:
                chosen = cand
                break
            text, err = scraper.fetch_page_text(cand)
            if text and not err:
                chosen, page_text, scraped_chars = cand, text, len(text)
                break
        if not chosen:
            raise UserError(f"I picked {candidates[0]} from the sitemap but could not read it ({err or 'no text found'}). "
                            "Paste the page text into the page content box and try again.", 422)
        cta_url = chosen
        others = [c for c in candidates if c != chosen]
        sitemap_note = f"CTA page picked from the sitemap to fit the photo: {chosen}."
        if others:
            sitemap_note += " Other close matches: " + ", ".join(others) + "."
        fixed_note = "\n".join(x for x in (fixed_note, sitemap_note) if x)
    if not page_text:
        page_text, err = scraper.fetch_page_text(cta_url)
        if err or not page_text:
            raise UserError(
                f"I could not read the CTA page ({err or 'no text found'}). "
                "Paste the page text into the page content box and try again.", 422)
        scraped_chars = len(page_text)

    return jsonify(service.generate_post(
        client, cta_url, page_text, image,
        special=form.get("special") or "",
        force=form.get("force") == "1",
        another=form.get("another") == "1",
        fixed_url_note=fixed_note,
        scraped_chars=scraped_chars,
        options_raw={k: form.get(k) for k in options.FIELDS},
        type_details={k: form.get(k) for k in options.ALL_DETAIL_KEYS},
    ))


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    if not config.api_key():
        print("WARNING: GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
    print(f"GBP Post Generator running at http://{host}:{port}  (model: {config.models()[0]})")
    app.run(host=host, port=port, debug=False, threaded=True)
