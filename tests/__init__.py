import os

# The fake Gemini in these tests returns fixed posts, so the app must not pick random options on its own.
os.environ.setdefault("GBP_RANDOMIZE_AUTO", "0")
