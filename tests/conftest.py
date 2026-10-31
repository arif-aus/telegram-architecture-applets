"""Shared test setup.

Loads the repository `.env` (never overriding variables that are already set)
the same way the bot does in production, so the live `integration` tests can
find `GEMINI_API_KEY`. No test asserts on the real secret values.
"""

from dotenv import load_dotenv

load_dotenv(override=False)
