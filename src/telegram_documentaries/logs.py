"""Structured logging, configured once, plus the shared logging decorator.

Business logic stays free of logging statements: decorate a function with
:func:`logged` and every call emits one structured record — success or
failure — without ever swallowing the result or the exception.
"""

from __future__ import annotations

import functools
import inspect
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar, cast, overload

P = ParamSpec("P")
R = TypeVar("R")

_HANDLER_MARKER = "_telegram_documentaries_handler"

_BASE_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Attributes every LogRecord carries; anything else is a structured extra field.
_STANDARD_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class StructuredFormatter(logging.Formatter):
    """Render the message followed by every structured field as ``key=value``."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            key: value for key, value in record.__dict__.items() if key not in _STANDARD_RECORD_KEYS
        }
        if not extras:
            return base
        rendered = " ".join(f"{key}={value}" for key, value in extras.items())
        return f"{base} | {rendered}"


def setup_logging(level: int = logging.INFO) -> None:
    """Attach the structured handler to the root logger exactly once."""
    # httpx logs every request URL at INFO, and Telegram puts the bot token in
    # that URL. Keep these noisy libraries quiet unless something is wrong.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    root = logging.getLogger()
    if any(getattr(handler, _HANDLER_MARKER, False) for handler in root.handlers):
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter(_BASE_FORMAT))
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
    root.setLevel(level)


@overload
def logged(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]: ...


@overload
def logged(func: Callable[P, R]) -> Callable[P, R]: ...


def logged(func: Callable[P, Any]) -> Callable[P, Any]:
    """Emit one structured record per call: ``status=ok`` or ``status=error``.

    Failures are logged with the traceback attached and then re-raised — the
    decorator never swallows an exception and never alters the return value.
    Supports both plain and ``async`` functions.
    """
    if inspect.iscoroutinefunction(func):
        async_func = cast("Callable[P, Coroutine[Any, Any, Any]]", func)

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            logger = logging.getLogger(func.__module__)
            started = time.perf_counter()
            try:
                result = await async_func(*args, **kwargs)
            except Exception:
                logger.error(
                    "%s failed",
                    func.__qualname__,
                    exc_info=True,
                    extra=_record_fields(func, started, status="error"),
                )
                raise
            logger.info(
                "%s finished",
                func.__qualname__,
                extra=_record_fields(func, started, status="ok"),
            )
            return result

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        logger = logging.getLogger(func.__module__)
        started = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.error(
                "%s failed",
                func.__qualname__,
                exc_info=True,
                extra=_record_fields(func, started, status="error"),
            )
            raise
        logger.info(
            "%s finished",
            func.__qualname__,
            extra=_record_fields(func, started, status="ok"),
        )
        return result

    return sync_wrapper


def _record_fields(
    func: Callable[..., object], started: float, *, status: str
) -> dict[str, object]:
    return {
        "event": func.__qualname__,
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
    }
