"""Session state: one versioned, in-memory schema keyed by `chat_id` (task group 2)."""

from typing import Any, cast

import pytest
from pydantic import ValidationError

from telegram_documentaries.state import Phase, SessionState, SessionStore, normalise_chat_id

CHAT_A = 111
CHAT_B = 222


def test_phase_enum_exposes_exactly_the_two_pipeline_phases() -> None:
    assert {phase.value for phase in Phase} == {"awaiting_photo", "awaiting_interview"}


def test_new_session_starts_in_awaiting_photo_with_versioned_schema() -> None:
    state = SessionState(chat_id=CHAT_A)

    assert state.phase is Phase.AWAITING_PHOTO
    assert state.schema_version == 2


def test_session_state_carries_the_interview_dossier() -> None:
    state = SessionState(
        chat_id=CHAT_A,
        profile="A nocturnal biscuit archivist.",
        suggested_animal="red panda",
    )

    assert state.profile == "A nocturnal biscuit archivist."
    assert state.suggested_animal == "red panda"


def test_session_state_dossier_defaults_to_none() -> None:
    state = SessionState(chat_id=CHAT_A)

    assert state.profile is None
    assert state.suggested_animal is None


def test_session_state_rejects_an_unknown_phase() -> None:
    with pytest.raises(ValidationError):
        SessionState(chat_id=CHAT_A, phase=cast(Any, "awaiting_sandwich"))


def test_session_state_requires_a_chat_id() -> None:
    with pytest.raises(ValidationError):
        SessionState()  # type: ignore[call-arg]


def test_session_state_coerces_a_string_chat_id_to_the_normalised_int() -> None:
    state = SessionState(chat_id=cast(Any, "123"))

    assert state.chat_id == 123
    assert isinstance(state.chat_id, int)


def test_normalise_chat_id_maps_string_and_int_to_the_same_value() -> None:
    assert normalise_chat_id("123") == normalise_chat_id(123) == 123


def test_normalise_chat_id_rejects_nonsense() -> None:
    with pytest.raises(ValueError):
        normalise_chat_id("not-a-chat-id")


def test_store_returns_none_for_an_unknown_chat() -> None:
    store = SessionStore()

    assert store.get(CHAT_A) is None


def test_store_round_trips_a_session() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW))

    stored = store.get(CHAT_A)

    assert stored is not None
    assert stored.phase is Phase.AWAITING_INTERVIEW


def test_store_lookup_by_string_finds_the_entry_stored_under_the_int() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A))

    assert store.get(str(CHAT_A)) is not None


def test_store_reset_purges_the_entry_entirely() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW))

    store.reset(CHAT_A)

    assert store.get(CHAT_A) is None
    assert len(store) == 0


def test_store_reset_of_an_unknown_chat_is_a_quiet_no_op() -> None:
    store = SessionStore()

    store.reset(CHAT_A)

    assert store.get(CHAT_A) is None


def test_one_chats_state_is_never_visible_to_another_chat() -> None:
    store = SessionStore()
    store.set(SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW))
    store.set(SessionState(chat_id=CHAT_B, phase=Phase.AWAITING_PHOTO))

    store.reset(CHAT_A)

    remaining = store.get(CHAT_B)
    assert remaining is not None
    assert remaining.chat_id == CHAT_B
    assert remaining.phase is Phase.AWAITING_PHOTO
    assert store.get(CHAT_A) is None
