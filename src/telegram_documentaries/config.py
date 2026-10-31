"""Secret configuration.

Every secret is read from the process environment first and from an env file
(`.env` by default) second. Secrets are never logged and never rendered by
``repr``/``str``. A missing or blank secret fails loudly at startup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_ENV_FILE = Path(".env")

REQUIRED_SECRETS: tuple[str, ...] = ("TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or blank."""


@dataclass(frozen=True, slots=True, repr=False)
class Settings:
    """The secrets the application needs, kept out of logs by construction."""

    telegram_bot_token: str
    gemini_api_key: str

    def __repr__(self) -> str:
        return "Settings(telegram_bot_token='***', gemini_api_key='***')"

    __str__ = __repr__


def load_settings(env_file: Path | str = DEFAULT_ENV_FILE) -> Settings:
    """Resolve the required secrets, failing loudly when any is missing.

    The process environment wins over the file, so operators can override
    ``.env`` without editing it. Blank or absent values raise
    :class:`ConfigError` naming **every** offending variable — the error
    message itself never contains a secret value.
    """
    path = Path(env_file)
    file_values = dotenv_values(path) if path.is_file() else {}

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for name in REQUIRED_SECRETS:
        value = (os.environ.get(name) or file_values.get(name) or "").strip()
        if value:
            resolved[name] = value
        else:
            missing.append(name)

    if missing:
        raise ConfigError(
            f"Missing required secret(s): {', '.join(missing)}. "
            f"Set them in {path} or in the environment before starting."
        )

    return Settings(
        telegram_bot_token=resolved["TELEGRAM_BOT_TOKEN"],
        gemini_api_key=resolved["GEMINI_API_KEY"],
    )
