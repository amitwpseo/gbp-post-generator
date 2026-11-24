"""Thin wrapper around the google-genai SDK: system prompt, image input, retries, model discovery."""
import re
import time
from collections import namedtuple

import config

# role is "user" or "model"; image is (bytes, mime_type) or None
Turn = namedtuple("Turn", "role text image", defaults=(None,))


class GeminiError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


_sleep = time.sleep
_working_model = None  # remembered after the first successful call, so later calls skip dead models

_SKIP_WORDS = ("tts", "image", "live", "audio", "embedding", "robotics", "computer", "exp", "learnlm",
               "gemma", "veo", "imagen", "aqa", "native")


def load_system_prompt() -> str:
    return config.prompt_path().read_text(encoding="utf-8").strip()


def working_model():
    return _working_model


def _to_contents(turns):
    from google.genai import types

    out = []
    for t in turns:
        parts = [types.Part.from_text(text=t.text)]
        if t.image:
            parts.append(types.Part.from_bytes(data=t.image[0], mime_type=t.image[1]))
        out.append(types.Content(role=t.role, parts=parts))
    return out


def _extract_text(resp) -> str:
    text = None
    try:
        text = resp.text
    except Exception:
        text = None
    if text and text.strip():
        return text
    reason = ""
    fb = getattr(resp, "prompt_feedback", None)
    if fb and getattr(fb, "block_reason", None):
        reason = f"blocked: {fb.block_reason}"
    elif getattr(resp, "candidates", None):
        reason = f"finish reason: {resp.candidates[0].finish_reason}"
    raise GeminiError(
        "Gemini returned no text" + (f" ({reason})" if reason else "") + ". Try again or use a different image.", 502
    )


def _model_rank(name: str):
    """Stable before preview, full Flash before Flash-Lite, newest version first."""
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    version = float(m.group(1)) if m else 0.0
    return ("preview" in name, "lite" in name, -version, name)


def discover_models(client) -> list:
    """Flash-class text models that this API key can call, best candidates first."""
    try:
        names = []
        for m in client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            name = (getattr(m, "name", "") or "").split("/")[-1]
            if "flash" not in name or any(w in name for w in _SKIP_WORDS):
                continue
            names.append(name)
        return sorted(set(names), key=_model_rank)
    except Exception:
        return []


def generate(turns, system=None, temperature=None) -> str:
    """Sends the turns to Gemini. system=None uses system_prompt.txt; pass a string for a different job (for example emoji search)."""
    global _working_model
    key = config.api_key()
    if not key:
        raise GeminiError("No Gemini API key found. Add GEMINI_API_KEY to the .env file and restart the app.", 500)

    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=key)
    cfg = types.GenerateContentConfig(
        system_instruction=load_system_prompt() if system is None else system,
        temperature=config.temperature() if temperature is None else temperature)
    contents = _to_contents(turns)
    failures = []  # (model, short reason)

    def attempt(model):
        """Returns text, or None after recording why this model could not be used."""
        for n in range(3):
            try:
                return _extract_text(client.models.generate_content(model=model, contents=contents, config=cfg))
            except errors.APIError as e:
                code = getattr(e, "code", None)
                msg = getattr(e, "message", None) or str(e)
                if code == 404:
                    failures.append((model, "not found"))
                    return None
                if code == 429 and re.search(r"limit:\s*0\b", msg):
                    failures.append((model, "no free-tier quota"))
                    return None
                if code in (429, 500, 503):
                    if n < 2:
                        _sleep(8 * (n + 1))
                        continue
                    failures.append((model, "rate limited" if code == 429 else f"unavailable ({code})"))
                    return None
                if code in (400, 401, 403) and "api key" in msg.lower():
                    raise GeminiError("Gemini rejected the API key. Check GEMINI_API_KEY in the .env file.", 401)
                raise GeminiError(f"Gemini request failed ({code}): {msg}", 502)
        return None

    candidates = []
    for m in ([_working_model] if _working_model else []) + config.models():
        if m and m not in candidates:
            candidates.append(m)

    for model in candidates:
        text = attempt(model)
        if text is not None:
            _working_model = model
            return text

    # Configured models are gone or unusable: ask the API which models this key can call.
    available = discover_models(client)
    for model in [m for m in available if m not in candidates][:5]:
        text = attempt(model)
        if text is not None:
            _working_model = model
            return text

    tried = ", ".join(f"{m} ({why})" for m, why in failures) or "none"
    if failures and all(why in ("rate limited", "no free-tier quota") for _, why in failures):
        raise GeminiError(
            "Gemini free-tier rate limit or daily quota reached. Wait a minute and try again, or try tomorrow. "
            f"Tried: {tried}.", 429)
    hint = (f" Models available to your key: {', '.join(available[:8])}. "
            "Set GEMINI_MODEL to one of these in the .env file and restart."
            if available else " Could not list the models for your key. Check the key at aistudio.google.com/apikey.")
    raise GeminiError(f"No usable Gemini model for this key. Tried: {tried}.{hint}", 502)
