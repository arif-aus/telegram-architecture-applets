"""Tests for `.env` secret loading (task group 1)."""

from pathlib import Path

import pytest

from telegram_documentaries.config import ConfigError, load_settings

# Obviously fake values: never the real secrets.
FAKE_TOKEN = "111111111:AAFakeTelegramToken0123456789abcdefghi"
FAKE_KEY = "AIzaFakeGeminiKey0123456789abcdefghijklmnopqrst"


def _write_env(tmp_path: Path, content: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    return env_file


def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_load_settings_reads_both_secrets_from_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scrub_env(monkeypatch)
    env_file = _write_env(
        tmp_path,
        f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nGEMINI_API_KEY={FAKE_KEY}\n",
    )

    settings = load_settings(env_file)

    assert settings.telegram_bot_token == FAKE_TOKEN
    assert settings.gemini_api_key == FAKE_KEY


def test_values_already_in_the_environment_win_over_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaFromEnvironment")
    env_file = _write_env(tmp_path, "GEMINI_API_KEY=AIzaFromFile\n")

    settings = load_settings(env_file)

    assert settings.gemini_api_key == "AIzaFromEnvironment"


def test_missing_secret_raises_loudly_naming_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scrub_env(monkeypatch)
    env_file = _write_env(tmp_path, f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\n")

    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file)

    assert "GEMINI_API_KEY" in str(excinfo.value)


def test_every_missing_secret_is_named_in_the_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scrub_env(monkeypatch)
    env_file = _write_env(tmp_path, "")

    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file)

    message = str(excinfo.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "GEMINI_API_KEY" in message


def test_blank_secret_value_counts_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scrub_env(monkeypatch)
    env_file = _write_env(tmp_path, "TELEGRAM_BOT_TOKEN=   \nGEMINI_API_KEY=x\n")

    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file)

    assert "TELEGRAM_BOT_TOKEN" in str(excinfo.value)


def test_absent_env_file_raises_loudly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _scrub_env(monkeypatch)

    with pytest.raises(ConfigError) as excinfo:
        load_settings(tmp_path / "nope.env")

    message = str(excinfo.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "GEMINI_API_KEY" in message


def test_secrets_never_appear_in_repr_or_str(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scrub_env(monkeypatch)
    env_file = _write_env(
        tmp_path,
        f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nGEMINI_API_KEY={FAKE_KEY}\n",
    )

    settings = load_settings(env_file)

    for rendered in (repr(settings), str(settings)):
        assert FAKE_TOKEN not in rendered
        assert FAKE_KEY not in rendered
