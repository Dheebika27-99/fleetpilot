"""Settings, read from environment variables (or a local .env file)."""

import os

from dotenv import load_dotenv

load_dotenv()  # reads .env if it exists; real environment variables win

# Postgres.app default: your Mac user, no password, local server.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/fleetpilot")
