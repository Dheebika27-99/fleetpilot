"""
Which Gemini models actually work with MY key?

Asks each candidate model a tiny question and prints OK or the error.
Reads the key from .env and never prints it.

Run:  python scripts/check_gemini_models.py
"""

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import GEMINI_API_KEY  # noqa: E402
from app.llm.providers import GeminiProvider, ProviderError  # noqa: E402

SKIP_WORDS = ("preview", "image", "tts", "omni", "latest", "embedding", "live", "native-audio")


def candidate_models():
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                  headers={"x-goog-api-key": GEMINI_API_KEY}, params={"pageSize": 200}, timeout=20)
    r.raise_for_status()
    names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    return [n for n in names if "flash" in n and not any(w in n for w in SKIP_WORDS)]


def main():
    if not GEMINI_API_KEY:
        sys.exit("GEMINI_API_KEY is empty. Put it in .env first.")
    for model in candidate_models():
        try:
            result = GeminiProvider(GEMINI_API_KEY, model).generate(
                [{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=10, timeout=20)
            print(f"OK    {model:<30} -> {result.text.strip()[:30]!r}")
        except ProviderError as exc:
            print(f"FAIL  {model:<30} -> {exc}")


if __name__ == "__main__":
    main()
