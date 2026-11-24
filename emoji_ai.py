"""Finds emoji from a plain-English description, using the same Gemini key (one small request)."""
import gemini_client
from errors import UserError
from gemini_client import Turn
from validators import emoji_matches

SYSTEM = (
    "You are an emoji picker for social media posts. The person describes the emoji they want. "
    "Reply with only the 8 best matching emoji, best match first, separated by single spaces. No words, no numbers, "
    "no punctuation, no explanations. Never repeat an emoji. Only use emoji that exist in the Unicode standard. "
    "Prefer recent emoji (Unicode 13 to 15.1) when one fits as well as an older one."
)


def parse(raw: str, limit: int = 8) -> list:
    seen, out = set(), []
    for m in emoji_matches(raw or ""):
        e = m.group(0)
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:limit]


def suggest(query: str, context: str = "") -> list:
    query = " ".join((query or "").split())[:200]
    if not query:
        raise UserError("Describe the emoji you want, for example: clean water drop.")
    context = " ".join((context or "").split())[:600]
    prompt = f"Emoji wanted: {query}"
    if context:
        prompt += f"\nPost it will go in (for relevance only, do not quote it): {context}"
    raw = gemini_client.generate([Turn("user", prompt)], system=SYSTEM, temperature=0.4)
    found = parse(raw)
    if not found:
        raise UserError("Gemini did not return an emoji for that. Try describing it a different way.", 422)
    return found
