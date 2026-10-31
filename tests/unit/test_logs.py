"""Tests for structured logging and the logging decorator (task group 1)."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import pytest

from telegram_documentaries.logs import StructuredFormatter, logged, setup_logging


def _events(caplog: pytest.LogCaptureFixture, status: str | None = None) -> list[logging.LogRecord]:
    records = [r for r in caplog.records if "event" in r.__dict__]
    if status is not None:
        records = [r for r in records if r.__dict__.get("status") == status]
    return records


def test_setup_logging_installs_one_handler_and_is_idempotent() -> None:
    root = logging.getLogger()

    setup_logging()
    handler_count = len(root.handlers)
    setup_logging()

    assert handler_count > 0
    assert len(root.handlers) == handler_count


def test_structured_formatter_renders_extra_fields() -> None:
    record = logging.LogRecord(
        name="telegram_documentaries.demo",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="bouncer judged photo",
        args=(),
        exc_info=None,
    )
    record.event = "bouncer.decide"
    record.status = "ok"
    record.chat_id = 42

    rendered = StructuredFormatter().format(record)

    assert "bouncer judged photo" in rendered
    assert "event=bouncer.decide" in rendered
    assert "status=ok" in rendered
    assert "chat_id=42" in rendered


def test_logged_decorator_returns_the_original_result_and_logs_structured_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    @logged
    def add(left: int, right: int) -> int:
        return left + right

    result = add(2, 3)

    assert result == 5
    success = _events(caplog, status="ok")
    assert [r.__dict__["event"] for r in success] == [add.__qualname__]
    assert success[0].levelno == logging.INFO


def test_logged_decorator_logs_failure_and_re_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    @logged
    def boom() -> None:
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        boom()

    failures = _events(caplog, status="error")
    assert [r.__dict__["event"] for r in failures] == [boom.__qualname__]
    assert failures[0].levelno == logging.ERROR
    assert failures[0].exc_info is not None
    assert isinstance(failures[0].exc_info[1], ValueError)


def test_logged_decorator_supports_async_functions(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    @logged
    async def judge(photo: bytes) -> str:
        await asyncio.sleep(0)
        return photo.decode()

    async def run() -> str:
        return await judge(b"photo")

    assert asyncio.run(run()) == "photo"
    assert [r.__dict__["event"] for r in _events(caplog, status="ok")] == [judge.__qualname__]


def test_logged_decorator_passes_through_kwargs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    @logged
    def greet(name: str = "world") -> str:
        return f"hello {name}"

    assert greet(name="bouncer") == "hello bouncer"
    assert len(_events(caplog)) == 1


def test_logged_decorator_does_not_swallow_or_mangle_the_business_result() -> None:
    sentinel: dict[str, Any] = {"value": 1}

    @logged
    def mutate() -> dict[str, Any]:
        sentinel["value"] = 2
        return sentinel

    returned: Callable[[], dict[str, Any]] = mutate
    assert returned() is sentinel
    assert sentinel["value"] == 2
