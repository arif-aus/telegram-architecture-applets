"""Gateway behaviour: `/start`, `/restart`, text acknowledgement, no-raise policy (task group 3)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_documentaries.handlers import (
    ACKNOWLEDGEMENT,
    GRACEFUL_ERROR_TEXT,
    GREETING,
    acknowledge_text,
    restart,
    start,
)
from telegram_documentaries.state import Phase, SessionState, SessionStore

CHAT_A = 111


def make_update(chat_id: int | None = CHAT_A) -> MagicMock:
    message = MagicMock()
    message.reply_text = AsyncMock(return_value=None)
    chat = MagicMock()
    chat.id = chat_id
    update = MagicMock()
    update.effective_chat = None if chat_id is None else chat
    update.effective_message = None if chat_id is None else message
    return update


def make_context(store: SessionStore) -> MagicMock:
    context = MagicMock()
    context.bot_data = {"store": store}
    return context


async def test_start_creates_a_fresh_session_and_greets() -> None:
    store = SessionStore()
    update = make_update()
    context = make_context(store)

    await start(update, context)

    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_PHOTO
    update.effective_message.reply_text.assert_awaited_once_with(GREETING)


async def test_start_purges_any_existing_progress_before_greeting() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW))
    update = make_update()
    context = make_context(store)

    await start(update, context)

    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_PHOTO


async def test_restart_purges_and_regreets() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW))
    update = make_update()
    context = make_context(store)

    await restart(update, context)

    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_PHOTO
    update.effective_message.reply_text.assert_awaited_once_with(GREETING)


async def test_plain_text_without_a_session_gets_the_hardcoded_acknowledgement() -> None:
    store = SessionStore()
    update = make_update()
    context = make_context(store)

    await acknowledge_text(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(ACKNOWLEDGEMENT)
    assert store.get(CHAT_A) is None


async def test_plain_text_does_not_touch_an_existing_session() -> None:
    store = SessionStore()
    # Interview complete: the text handler falls back without calling a model.
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW, question_index=5))
    update = make_update()
    context = make_context(store)

    await acknowledge_text(update, context)

    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_INTERVIEW


async def test_update_without_a_chat_is_skipped_quietly() -> None:
    store = SessionStore()
    update = make_update(chat_id=None)
    context = make_context(store)

    await start(update, context)

    assert store.get(CHAT_A) is None


async def test_store_failure_never_raises_into_the_poll_loop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("ERROR")
    store = SessionStore()

    def explode(state: SessionState) -> None:
        del state
        raise RuntimeError("store is on fire")

    store.set = explode  # type: ignore[method-assign]
    update = make_update()
    context = make_context(store)

    await start(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(GRACEFUL_ERROR_TEXT)
    assert any(record.levelname == "ERROR" for record in caplog.records)


async def test_graceful_error_reply_failure_also_never_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("ERROR")
    store = SessionStore()

    def explode(state: SessionState) -> None:
        del state
        raise RuntimeError("store is on fire")

    store.set = explode  # type: ignore[method-assign]
    update = make_update()
    update.effective_message.reply_text = AsyncMock(side_effect=RuntimeError("telegram down"))
    context = make_context(store)

    await start(update, context)  # must not raise

    assert any("ERROR" == record.levelname for record in caplog.records)


async def test_successful_handler_emits_a_structured_log_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    store = SessionStore()
    update = make_update()
    context = make_context(store)

    await start(update, context)

    events = [record.__dict__["event"] for record in caplog.records if "event" in record.__dict__]
    assert start.__qualname__ in events
