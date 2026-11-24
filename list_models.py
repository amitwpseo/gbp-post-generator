"""Prints the Gemini models your API key can use. Run: python list_models.py"""
import sys

import config
import gemini_client


def main() -> int:
    key = config.api_key()
    if not key:
        print("No GEMINI_API_KEY found. Add it to the .env file first.")
        return 1
    from google import genai

    client = genai.Client(api_key=key)
    try:
        everything = list(client.models.list())
    except Exception as e:  # noqa: BLE001
        print(f"Could not list models: {e}")
        return 1
    flash = gemini_client.discover_models(client)
    print("Flash models the app can use (best first):")
    for name in flash:
        print(f"  {name}")
    if not flash:
        print("  (none found)")
    print(f"\nConfigured in .env: {', '.join(config.models())}")
    if flash and not set(config.models()) & set(flash):
        print(f"None of those exist for your key. Set GEMINI_MODEL={flash[0]} in .env (or leave it, the app will auto-pick).")
    print(f"\nAll {len(everything)} models returned by the API:")
    for m in everything:
        print("  " + (getattr(m, "name", "") or "").split("/")[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
