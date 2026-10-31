"""Runnable entry point: `python -m telegram_documentaries` (long polling)."""

from __future__ import annotations

import logging
from pathlib import Path

from telegram.error import InvalidToken

from telegram_documentaries.app import build_application
from telegram_documentaries.config import DEFAULT_ENV_FILE, ConfigError, load_settings
from telegram_documentaries.logs import setup_logging

logger = logging.getLogger(__name__)


def main(env_file: Path | str = DEFAULT_ENV_FILE) -> None:
    """Boot the bot: load `.env` secrets loudly, configure logging, poll."""
    settings = load_settings(env_file)
    setup_logging()
    logger.info("event=startup status=loading_secrets")
    application = build_application(settings)
    logger.info("event=startup status=polling_started")
    try:
        application.run_polling()
    except InvalidToken:
        # `python-telegram-bot` puts the rejected token in this exception's
        # message; never let it reach a log or a traceback (TECH.md: secrets are
        # never logged). `from None` drops the chained original.
        raise ConfigError(
            "Telegram rejected TELEGRAM_BOT_TOKEN. Create a fresh token with "
            "@BotFather and update .env (the token is never logged)."
        ) from None


if __name__ == "__main__":
    main()
