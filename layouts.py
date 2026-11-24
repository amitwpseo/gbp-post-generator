"""Layout library, read straight from system_prompt.txt so edits to the prompt stay in sync."""
import difflib
import re
from functools import lru_cache
from pathlib import Path

import config


@lru_cache(maxsize=4)
def _load(path_str: str, mtime: float) -> dict:
    text = Path(path_str).read_text(encoding="utf-8")
    m = re.search(r"Layout library[^\n]*\n(.*?)Opener rules", text, re.S)
    layouts = {}
    for line in (m.group(1) if m else "").splitlines():
        mm = re.match(r"\s*(\d+)\.\s+(.*\S)\s*$", line)
        if mm:
            layouts[int(mm.group(1))] = mm.group(2)
    return layouts


def load_layouts() -> dict:
    path = config.prompt_path()
    return _load(str(path), path.stat().st_mtime)


def normalize_layout(text: str) -> str:
    """Map whatever the model wrote after 'Layout:' to a library layout name when possible."""
    layouts = load_layouts()
    t = re.sub(r"[*`]+", "", text or "").strip()
    if not t:
        return ""
    low = t.lower()
    for name in sorted(layouts.values(), key=len, reverse=True):
        if name.lower() in low:
            return name
    for name in sorted(layouts.values(), key=len, reverse=True):
        short = re.sub(r"\s*\(.*?\)", "", name).strip().lower()
        if short and short != name.lower() and short in low:
            return name
    m = re.match(r"^\W*(?:layout\s*)?#?(\d{1,2})(?:[.):]|\s*$|\s+[-–—]\s)", t, re.I)
    if m and int(m.group(1)) in layouts:
        return layouts[int(m.group(1))]
    head = re.split(r"\s[-–—:]\s|\.\s|:\s", t, maxsplit=1)[0]
    head = re.sub(r"^\W*\d{0,2}[.)]?\s*", "", head).strip()
    names = list(layouts.values())
    close = difflib.get_close_matches(head.lower(), [n.lower() for n in names], n=1, cutoff=0.6)
    if close:
        return names[[n.lower() for n in names].index(close[0])]
    return head[:80]
