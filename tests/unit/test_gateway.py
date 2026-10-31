"""Gateway behaviour: `/start`, `/restart`, text acknowledgement, no-raise policy (task group 3)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import telegram_documentaries.handlers as handlers
from telegram_documentaries.handlers import (
    ACKNOWLEDGEMENT,
    GRACEFUL_ERROR_TEXT,
    GREETING,
    acknowledge_text,
    restart,
    start,
)
from telegram_documentaries.reset import (
    ActiveSessionRegistry,
    EphemeralAssetRegistry,
    ResetOutcome,
)
from telegram_documentaries.state import Phase, SessionState, SessionStore

CHAT_A = 111
CHAT_B = 222


def make_update(chat_id: int | None = CHAT_A) -> MagicMock:
    message = MagicMock()
    message.reply_text = AsyncMock(return_value=None)
    chat = MagicMock()
    chat.id = chat_id
    update = MagicMock()
    update.effective_chat = None if chat_id is None else chat
    update.effective_message = None if chat_id is None else message
    return update


def make_context(
    store: SessionStore,
    *,
    sessions: ActiveSessionRegistry | None = None,
    assets: EphemeralAssetRegistry | None = None,
) -> MagicMock:
    context = MagicMock()
    context.bot_data = {
        "store": store,
        "sessions": sessions or ActiveSessionRegistry(),
        "assets": assets or EphemeralAssetRegistry(),
    }
    return context


def _populated_store(chat_id: int = CHAT_A) -> SessionStore:
    store = SessionStore()
    store.set(
        SessionState(
            chat_id=chat_id,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=4,
            responses=["answer1", "answer2", "answer3", "answer4"],
            profile="A nocturnal biscuit archivist.",
            suggested_animal="red panda",
            image_bytes=b"portrait-bytes",
        )
    )
    return store


def _file(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"ephemeral")
    return path


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


@pytest.mark.parametrize("handler", [start, restart])
async def test_reset_commands_call_the_shared_reset_routine(
    handler: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore()
    sessions = ActiveSessionRegistry()
    assets = EphemeralAssetRegistry()
    context = make_context(store, sessions=sessions, assets=assets)
    update = make_update()
    reset_mock = AsyncMock(
        return_value=ResetOutcome(
            chat_id=CHAT_A,
            cancelled_sessions=0,
            deleted_assets=0,
            phase=Phase.AWAITING_PHOTO,
        )
    )
    monkeypatch.setattr(handlers, "reset_chat", reset_mock)

    await handler(update, context)  # type: ignore[operator]

    reset_mock.assert_awaited_once_with(
        CHAT_A,
        store=store,
        sessions=sessions,
        assets=assets,
    )
    update.effective_message.reply_text.assert_awaited_once_with(GREETING)


async def test_start_clears_the_full_interview_dossier_and_purges_temp_media(
    tmp_path: Path,
) -> None:
    store = _populated_store()
    sessions = ActiveSessionRegistry()
    token = sessions.begin(CHAT_A)
    assets = EphemeralAssetRegistry()
    portrait = _file(tmp_path, "portrait.jpg")
    assets.add(CHAT_A, portrait)
    update = make_update()
    context = make_context(store, sessions=sessions, assets=assets)

    await start(update, context)

    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_PHOTO
    assert state.question_index == 0
    assert state.responses == []
    assert state.profile is None
    assert state.suggested_animal is None
    assert state.image_bytes is None
    assert sessions.is_active(token) is False
    assert portrait.exists() is False
    update.effective_message.reply_text.assert_awaited_once_with(GREETING)


async def test_restart_clears_progress_and_purges_temp_media(tmp_path: Path) -> None:
    store = _populated_store()
    assets = EphemeralAssetRegistry()
    portrait = _file(tmp_path, "portrait.jpg")
    assets.add(CHAT_A, portrait)
    update = make_update()
    context = make_context(store, assets=assets)

    await restart(update, context)

    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_PHOTO
    assert state.responses == []
    assert state.profile is None
    assert state.image_bytes is None
    assert portrait.exists() is False
    update.effective_message.reply_text.assert_awaited_once_with(GREETING)


async def test_start_resets_only_the_requesting_chat(tmp_path: Path) -> None:
    store = _populated_store(CHAT_A)
    store.set(
        SessionState(
            chat_id=CHAT_B,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=2,
            responses=["answer1", "answer2"],
        )
    )
    sessions = ActiveSessionRegistry()
    token_b = sessions.begin(CHAT_B)
    assets = EphemeralAssetRegistry()
    theirs = _file(tmp_path, "theirs.png")
    assets.add(CHAT_B, theirs)
    update = make_update(chat_id=CHAT_A)
    context = make_context(store, sessions=sessions, assets=assets)

    await start(update, context)

    other = store.get(CHAT_B)
    assert other is not None
    assert other.phase is Phase.AWAITING_INTERVIEW
    assert other.question_index == 2
    assert other.responses == ["answer1", "answer2"]
    assert sessions.is_active(token_b) is True
    assert theirs.exists() is True


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
