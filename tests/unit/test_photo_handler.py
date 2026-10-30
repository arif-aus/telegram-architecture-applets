"""Photo handler: download the largest size, ask the Bouncer, route the verdict (task group 5)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_documentaries.bouncer import BouncerDecision
from telegram_documentaries.handlers import (
    GRACEFUL_ERROR_TEXT,
    PHOTO_CONFIRMATION,
    PHOTO_REJECTION,
    PHOTO_RETRY,
    handle_photo,
)
from telegram_documentaries.state import Phase, SessionState, SessionStore

CHAT_A = 111
CHAT_B = 222


def make_photo_size(width: int, height: int, image_bytes: bytes) -> MagicMock:
    """A Telegram `PhotoSize` whose download returns ``image_bytes``."""
    telegram_file = MagicMock()
    telegram_file.download_as_bytearray = AsyncMock(return_value=bytearray(image_bytes))
    size = MagicMock()
    size.width = width
    size.height = height
    size.file_size = len(image_bytes)
    size.get_file = AsyncMock(return_value=telegram_file)
    return size


def make_update(
    photos: list[MagicMock] | None = None,
    *,
    chat_id: int | None = CHAT_A,
) -> MagicMock:
    message = MagicMock()
    message.reply_text = AsyncMock(return_value=None)
    message.photo = photos
    chat = MagicMock()
    chat.id = chat_id
    update = MagicMock()
    update.effective_chat = None if chat_id is None else chat
    update.effective_message = None if chat_id is None else message
    return update


def make_context(
    store: SessionStore,
    decision: BouncerDecision | Exception,
) -> MagicMock:
    bouncer = MagicMock()
    if isinstance(decision, Exception):
        bouncer.decide = AsyncMock(side_effect=decision)
    else:
        bouncer.decide = AsyncMock(return_value=decision)
    context = MagicMock()
    context.bot_data = {"store": store, "bouncer": bouncer}
    return context


def _bouncer(context: MagicMock) -> MagicMock:
    bouncer = context.bot_data["bouncer"]
    assert isinstance(bouncer, MagicMock)
    return bouncer


async def test_photo_handler_downloads_the_largest_photo_size() -> None:
    small = make_photo_size(100, 100, b"small")
    medium = make_photo_size(320, 240, b"medium")
    large = make_photo_size(800, 600, b"large-bytes")
    store = SessionStore()
    update = make_update([small, medium, large])
    context = make_context(store, BouncerDecision.ACCEPT)

    await handle_photo(update, context)

    large.get_file.assert_awaited_once_with()
    small.get_file.assert_not_awaited()
    medium.get_file.assert_not_awaited()
    _bouncer(context).decide.assert_awaited_once_with(b"large-bytes", mime_type="image/jpeg")


async def test_photo_handler_accepts_a_human_and_advances_the_phase() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_PHOTO))
    update = make_update([make_photo_size(640, 480, b"portrait")])
    context = make_context(store, BouncerDecision.ACCEPT)

    await handle_photo(update, context)

    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_INTERVIEW
    update.effective_message.reply_text.assert_awaited_once_with(PHOTO_CONFIRMATION)


async def test_photo_handler_rejects_a_non_human_and_purges_the_chat_state() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_PHOTO))
    update = make_update([make_photo_size(640, 480, b"landscape")])
    context = make_context(store, BouncerDecision.REJECT)

    await handle_photo(update, context)

    assert store.get(CHAT_A) is None
    assert len(store) == 0
    update.effective_message.reply_text.assert_awaited_once_with(PHOTO_REJECTION)


async def test_photo_handler_error_leaves_state_untouched_and_asks_the_user_to_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("ERROR")
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_PHOTO))
    update = make_update([make_photo_size(640, 480, b"blurry")])
    context = make_context(store, BouncerDecision.ERROR)

    await handle_photo(update, context)

    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_PHOTO
    assert len(store) == 1
    update.effective_message.reply_text.assert_awaited_once_with(PHOTO_RETRY)
    assert any(
        record.levelname == "ERROR" and "photo" in record.getMessage() for record in caplog.records
    )


async def test_photo_handler_rejection_only_purges_the_sending_chats_state() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_PHOTO))
    store.set(SessionState(chat_id=CHAT_B, phase=Phase.AWAITING_INTERVIEW))
    update = make_update([make_photo_size(640, 480, b"landscape")], chat_id=CHAT_A)
    context = make_context(store, BouncerDecision.REJECT)

    await handle_photo(update, context)

    assert store.get(CHAT_A) is None
    other = store.get(CHAT_B)
    assert other is not None
    assert other.phase is Phase.AWAITING_INTERVIEW


async def test_photo_handler_error_never_touches_another_chats_state() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW))
    store.set(SessionState(chat_id=CHAT_B, phase=Phase.AWAITING_PHOTO))
    update = make_update([make_photo_size(640, 480, b"blurry")], chat_id=CHAT_A)
    context = make_context(store, BouncerDecision.ERROR)

    await handle_photo(update, context)

    other = store.get(CHAT_B)
    assert other is not None
    assert other.phase is Phase.AWAITING_PHOTO


async def test_photo_handler_ignores_an_update_without_a_photo() -> None:
    store = SessionStore()
    update = make_update(None)
    context = make_context(store, BouncerDecision.ACCEPT)

    await handle_photo(update, context)

    _bouncer(context).decide.assert_not_awaited()
    update.effective_message.reply_text.assert_not_awaited()


async def test_photo_handler_store_failure_is_contained_by_the_safe_guard(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("ERROR")
    store = SessionStore()

    def explode(state: SessionState) -> None:
        del state
        raise RuntimeError("store is on fire")

    store.set = explode  # type: ignore[method-assign]
    update = make_update([make_photo_size(640, 480, b"portrait")])
    context = make_context(store, BouncerDecision.ACCEPT)

    await handle_photo(update, context)  # must not raise

    update.effective_message.reply_text.assert_awaited_once_with(GRACEFUL_ERROR_TEXT)
