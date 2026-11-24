"""Settings, read at call time so tests (and .env edits) take effect without re-importing."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def data_dir() -> Path:
    path = Path(os.environ.get("GBP_DATA_DIR") or BASE_DIR / "data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "history.db"


def upload_dir() -> Path:
    path = data_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def prompt_path() -> Path:
    return BASE_DIR / "system_prompt.txt"


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def models() -> list:
    primary = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
    fallbacks = os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite")
    out = [primary] + [m.strip() for m in fallbacks.split(",") if m.strip()]
    seen, ordered = set(), []
    for m in out:
        if m and m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


def temperature() -> float:
    try:
        return float(os.environ.get("GEMINI_TEMPERATURE", "0.9"))
    except ValueError:
        return 0.9


def max_fix_attempts() -> int:
    try:
        return max(0, int(os.environ.get("MAX_FIX_ATTEMPTS", "2")))
    except ValueError:
        return 2


def auto_randomize() -> bool:
    """When on (default), options left on Auto for layout, opener, closer, length and tone are picked at random by the app,
    so the first post for every client no longer comes out in the same layout."""
    return os.environ.get("GBP_RANDOMIZE_AUTO", "1").strip().lower() not in ("0", "false", "no", "off")


MAX_PAGE_CHARS = 12000
MAX_IMAGE_BYTES = 12 * 1024 * 1024
