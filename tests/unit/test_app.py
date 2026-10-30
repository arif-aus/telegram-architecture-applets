"""Application wiring tests: spec handlers, Bouncer wiring, loud boot failures."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from telegram.error import InvalidToken

import telegram_documentaries.app as app_module
from telegram_documentaries.__main__ import main
from telegram_documentaries.app import build_application
from telegram_documentaries.config import ConfigError, Settings
from telegram_documentaries.handlers import acknowledge_text, handle_photo, restart, start
from telegram_documentaries.state import SessionStore

FAKE_TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALdsaw"
FAKE_KEY = "AIzaFakeGeminiKey0123456789abcdefghijklmnopqrst"


@pytest.fixture
def settings() -> Settings:
    return Settings(telegram_bot_token=FAKE_TOKEN, gemini_api_key=FAKE_KEY)


def test_build_application_registers_the_gateway_handlers_and_store(
    settings: Settings,
) -> None:
    application = build_application(settings)

    callbacks = [
        getattr(handler, "callback", None)
        for group in application.handlers.values()
        for handler in group
    ]
    assert start in callbacks
    assert restart in callbacks
    assert acknowledge_text in callbacks
    assert handle_photo in callbacks
    assert isinstance(application.bot_data["store"], SessionStore)


def test_build_application_wires_the_bouncer(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    bouncer_cls = MagicMock()
    monkeypatch.setattr(app_module, "BouncerService", bouncer_cls)

    application = build_application(settings)

    bouncer_cls.assert_called_once_with(api_key=settings.gemini_api_key)
    assert application.bot_data["bouncer"] is bouncer_cls.return_value


def test_main_fails_loudly_when_secrets_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ConfigError):
        main(env_file=tmp_path / "missing.env")


def test_main_never_surfaces_a_rejected_telegram_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "bot000:super-secret-telegram-token"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret)
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)

    application = MagicMock()
    application.run_polling.side_effect = InvalidToken(f"The token `{secret}` was rejected.")

    def fake_build_application(_settings: Settings) -> MagicMock:
        return application

    monkeypatch.setattr("telegram_documentaries.__main__.build_application", fake_build_application)

    with pytest.raises(ConfigError) as exc_info:
        main(env_file=tmp_path / "missing.env")

    assert secret not in str(exc_info.value)
    assert "never logged" in str(exc_info.value)
