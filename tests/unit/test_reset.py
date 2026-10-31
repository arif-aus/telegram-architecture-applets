"""Explicit reset: active sessions, ephemeral assets, and the reset routine."""

import asyncio
from pathlib import Path

import pytest

from telegram_documentaries.reset import (
    ActiveSessionRegistry,
    EphemeralAssetRegistry,
    ResetOutcome,
    reset_chat,
)
from telegram_documentaries.state import Phase, SessionState, SessionStore

CHAT_A = 111
CHAT_B = 222


# ---------------------------------------------------------------------------
# ActiveSessionRegistry
# ---------------------------------------------------------------------------


async def test_begin_makes_a_session_active_for_its_chat() -> None:
    sessions = ActiveSessionRegistry()

    token = sessions.begin(CHAT_A)

    assert token.chat_id == CHAT_A
    assert sessions.is_active(token) is True


async def test_cancel_invalidates_only_the_requested_chats_tokens() -> None:
    sessions = ActiveSessionRegistry()
    token_a1 = sessions.begin(CHAT_A)
    token_a2 = sessions.begin(CHAT_A)
    token_b = sessions.begin(CHAT_B)

    cancelled = await sessions.cancel(CHAT_A)

    assert cancelled == 2
    assert sessions.is_active(token_a1) is False
    assert sessions.is_active(token_a2) is False
    assert sessions.is_active(token_b) is True


async def test_cancel_cancels_and_awaits_a_registered_task() -> None:
    sessions = ActiveSessionRegistry()
    started = asyncio.Event()

    async def wait_forever() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(wait_forever())
    await started.wait()
    sessions.begin(CHAT_A, task=task)

    cancelled = await sessions.cancel(CHAT_A)

    assert cancelled == 1
    assert task.done()
    assert task.cancelled()


async def test_cancel_of_an_unknown_chat_is_a_quiet_no_op() -> None:
    sessions = ActiveSessionRegistry()

    cancelled = await sessions.cancel(CHAT_A)

    assert cancelled == 0


async def test_finishing_a_session_removes_only_that_token() -> None:
    sessions = ActiveSessionRegistry()
    first = sessions.begin(CHAT_A)
    second = sessions.begin(CHAT_A)

    sessions.finish(first)

    assert sessions.is_active(first) is False
    assert sessions.is_active(second) is True
    assert await sessions.cancel(CHAT_A) == 1


async def test_a_new_session_after_a_reset_gets_a_fresh_token() -> None:
    sessions = ActiveSessionRegistry()
    stale = sessions.begin(CHAT_A)
    await sessions.cancel(CHAT_A)

    fresh = sessions.begin(CHAT_A)

    assert fresh != stale
    assert sessions.is_active(stale) is False
    assert sessions.is_active(fresh) is True


# ---------------------------------------------------------------------------
# EphemeralAssetRegistry
# ---------------------------------------------------------------------------


def _file(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"ephemeral")
    return path


def test_purge_deletes_every_registered_file_for_the_chat(tmp_path: Path) -> None:
    assets = EphemeralAssetRegistry()
    first = _file(tmp_path, "portrait.jpg")
    second = _file(tmp_path, "hybrid.png")
    assets.add(CHAT_A, first)
    assets.add(CHAT_A, second)

    deleted = assets.purge(CHAT_A)

    assert deleted == 2
    assert first.exists() is False
    assert second.exists() is False
    assert assets.paths(CHAT_A) == ()


def test_purge_ignores_missing_files_and_is_idempotent(tmp_path: Path) -> None:
    assets = EphemeralAssetRegistry()
    missing = tmp_path / "already-gone.png"
    assets.add(CHAT_A, missing)

    assert assets.purge(CHAT_A) == 0
    assert assets.purge(CHAT_A) == 0


def test_a_deletion_failure_is_logged_and_remaining_files_are_still_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("ERROR")
    assets = EphemeralAssetRegistry()
    blocked = _file(tmp_path, "blocked.png")
    healthy = _file(tmp_path, "healthy.png")
    assets.add(CHAT_A, blocked)
    assets.add(CHAT_A, healthy)
    original_unlink = Path.unlink

    def fake_unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self == blocked:
            raise OSError("permission denied")
        original_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    deleted = assets.purge(CHAT_A)  # must not raise

    assert deleted == 1
    assert blocked.exists() is True
    assert healthy.exists() is False
    assert any(
        "event=reset.asset_delete_failed" in record.getMessage() for record in caplog.records
    )


def test_purging_one_chat_leaves_another_chats_files_untouched(tmp_path: Path) -> None:
    assets = EphemeralAssetRegistry()
    mine = _file(tmp_path, "mine.png")
    theirs = _file(tmp_path, "theirs.png")
    assets.add(CHAT_A, mine)
    assets.add(CHAT_B, theirs)

    assets.purge(CHAT_A)

    assert mine.exists() is False
    assert theirs.exists() is True
    assert assets.paths(CHAT_B) == (theirs,)


def test_purging_an_unknown_chat_is_a_quiet_no_op() -> None:
    assets = EphemeralAssetRegistry()

    assert assets.purge(CHAT_A) == 0


def test_only_explicitly_registered_paths_are_deleted(tmp_path: Path) -> None:
    assets = EphemeralAssetRegistry()
    registered = _file(tmp_path, "registered.png")
    unregistered = _file(tmp_path, "unregistered.png")
    assets.add(CHAT_A, registered)

    assets.purge(CHAT_A)

    assert registered.exists() is False
    assert unregistered.exists() is True


def test_string_and_int_chat_ids_address_the_same_asset_bucket(tmp_path: Path) -> None:
    assets = EphemeralAssetRegistry()
    path = _file(tmp_path, "portrait.jpg")
    assets.add(str(CHAT_A), path)

    assert assets.paths(CHAT_A) == (path,)
    assert assets.purge(CHAT_A) == 1


# ---------------------------------------------------------------------------
# reset_chat
# ---------------------------------------------------------------------------


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


async def test_reset_cancels_sessions_purges_assets_and_installs_greeting_state(
    tmp_path: Path,
) -> None:
    store = _populated_store()
    sessions = ActiveSessionRegistry()
    assets = EphemeralAssetRegistry()
    token = sessions.begin(CHAT_A)
    portrait = _file(tmp_path, "portrait.jpg")
    assets.add(CHAT_A, portrait)

    outcome = await reset_chat(CHAT_A, store=store, sessions=sessions, assets=assets)

    assert isinstance(outcome, ResetOutcome)
    assert outcome.chat_id == CHAT_A
    assert outcome.cancelled_sessions == 1
    assert outcome.deleted_assets == 1
    assert outcome.phase is Phase.AWAITING_PHOTO
    assert sessions.is_active(token) is False
    assert portrait.exists() is False

    fresh = store.get(CHAT_A)
    assert fresh is not None
    assert fresh.phase is Phase.AWAITING_PHOTO
    assert fresh.question_index == 0
    assert fresh.responses == []
    assert fresh.profile is None
    assert fresh.suggested_animal is None
    assert fresh.image_bytes is None


async def test_reset_is_idempotent(tmp_path: Path) -> None:
    store = _populated_store()
    sessions = ActiveSessionRegistry()
    assets = EphemeralAssetRegistry()
    sessions.begin(CHAT_A)
    assets.add(CHAT_A, _file(tmp_path, "portrait.jpg"))

    first = await reset_chat(CHAT_A, store=store, sessions=sessions, assets=assets)
    second = await reset_chat(CHAT_A, store=store, sessions=sessions, assets=assets)

    assert (first.cancelled_sessions, first.deleted_assets) == (1, 1)
    assert (second.cancelled_sessions, second.deleted_assets) == (0, 0)
    assert second.phase is Phase.AWAITING_PHOTO
    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_PHOTO


async def test_reset_is_isolated_to_the_requesting_chat(tmp_path: Path) -> None:
    store = _populated_store(CHAT_A)
    store.set(SessionState(chat_id=CHAT_B, phase=Phase.AWAITING_INTERVIEW, question_index=2))
    sessions = ActiveSessionRegistry()
    token_b = sessions.begin(CHAT_B)
    assets = EphemeralAssetRegistry()
    their_file = _file(tmp_path, "theirs.png")
    assets.add(CHAT_B, their_file)

    await reset_chat(CHAT_A, store=store, sessions=sessions, assets=assets)

    other = store.get(CHAT_B)
    assert other is not None
    assert other.phase is Phase.AWAITING_INTERVIEW
    assert other.question_index == 2
    assert sessions.is_active(token_b) is True
    assert their_file.exists() is True


async def test_reset_of_an_unknown_chat_still_installs_the_greeting_state() -> None:
    store = SessionStore()
    sessions = ActiveSessionRegistry()
    assets = EphemeralAssetRegistry()

    outcome = await reset_chat(CHAT_A, store=store, sessions=sessions, assets=assets)

    assert outcome.cancelled_sessions == 0
    assert outcome.deleted_assets == 0
    state = store.get(CHAT_A)
    assert state is not None
    assert state.phase is Phase.AWAITING_PHOTO
    assert state.responses == []


async def test_reset_emits_structured_start_and_completion_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    store = SessionStore()
    sessions = ActiveSessionRegistry()
    assets = EphemeralAssetRegistry()

    await reset_chat(CHAT_A, store=store, sessions=sessions, assets=assets)

    messages = [record.getMessage() for record in caplog.records]
    assert any("event=reset.start" in message for message in messages)
    assert any("event=reset.complete" in message for message in messages)
