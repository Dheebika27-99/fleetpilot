"""Settings, read from environment variables (or a local .env file)."""

import os

from dotenv import load_dotenv

load_dotenv()  # reads .env if it exists; real environment variables win

# Postgres.app default: your Mac user, no password, local server.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/fleetpilot")

# ---- LLM gateway -------------------------------------------------------------
# Secrets live ONLY in .env (git-ignored). Never hard-code a key.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")   # any model name shown in AI Studio
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Provider order = failover order. First one is tried first.
LLM_PROVIDER_ORDER = [p.strip() for p in os.getenv("LLM_PROVIDER_ORDER", "gemini,ollama").split(",") if p.strip()]

LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_DAILY_BUDGET_USD = float(os.getenv("LLM_DAILY_BUDGET_USD", "1.0"))

# Price per 1 million tokens (input, output) in USD, used for cost logging.
# Free tier / local model = 0. If you switch to a paid tier, copy the current numbers
# from the provider's pricing page into .env.
LLM_PRICES = {
    GEMINI_MODEL: (float(os.getenv("GEMINI_PRICE_IN_PER_1M", "0")),
                   float(os.getenv("GEMINI_PRICE_OUT_PER_1M", "0"))),
    OLLAMA_MODEL: (0.0, 0.0),
}
