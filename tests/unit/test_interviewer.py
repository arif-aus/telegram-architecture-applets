"""The Interviewer: unit tests for the ADK LlmAgent wrapper (Phase 3)."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_documentaries.interviewer import (
    InterviewerService,
    InterviewOutput,
    _build_content,
)
from telegram_documentaries.state import Phase, SessionState, SessionStore

FAKE_KEY = "AIzaFakeGeminiKey0123456789abcdefghijklmnopqrst"

CHAT_A = 111
CHAT_B = 222


# ---------------------------------------------------------------------------
# InterviewOutput contract tests
# ---------------------------------------------------------------------------


def test_interview_output_contract_defaults() -> None:
    """Defaults: no question, no profile, no animal (interview not complete)."""
    output = InterviewOutput.model_validate_json("{}")
    assert output.next_question is None
    assert output.profile is None
    assert output.suggested_animal is None


def test_interview_output_contract_with_question() -> None:
    """With a next_question set; profile and animal are None."""
    payload = json.dumps({"next_question": "What is your greatest fear?"})
    output = InterviewOutput.model_validate_json(payload)
    assert output.next_question == "What is your greatest fear?"
    assert output.profile is None
    assert output.suggested_animal is None


def test_interview_output_contract_with_profile_and_animal() -> None:
    """When complete: profile and suggested_animal are set."""
    payload = json.dumps(
        {
            "profile": "You love collecting unusual rocks and feeding pigeons in the park.",
            "suggested_animal": "peacock",
        }
    )
    output = InterviewOutput.model_validate_json(payload)
    assert output.profile == "You love collecting unusual rocks and feeding pigeons in the park."
    assert output.suggested_animal == "peacock"
    assert output.next_question is None


# ---------------------------------------------------------------------------
# _build_content helper tests
# ---------------------------------------------------------------------------


def test_build_content_includes_user_text_and_state() -> None:
    """The helper includes the user's message and the current session state."""
    state = SessionState(
        chat_id=CHAT_A,
        phase=Phase.AWAITING_INTERVIEW,
        question_index=2,
        responses=["answer1", "answer2"],
    )
    content = _build_content("answer3", state)

    assert content.role == "user"
    assert content.parts is not None
    assert len(content.parts) == 2
    assert content.parts[0].text == "answer3"
    state_text = content.parts[1].text
    assert state_text is not None
    assert "question_index: 2" in state_text
    assert "answer1" in state_text
    assert "answer2" in state_text


# ---------------------------------------------------------------------------
# InterviewerService construction tests
# ---------------------------------------------------------------------------


def test_interviewer_service_constructs_with_fake_key() -> None:
    """Service can be constructed with a fake API key (no network required)."""
    service = InterviewerService(api_key=FAKE_KEY)
    assert service is not None


# ---------------------------------------------------------------------------
# Mocked ADK runner round-trip tests
# ---------------------------------------------------------------------------


class _MockRunner:
    """Minimal mock that tracks calls and returns a controllable final event."""

    def __init__(self) -> None:
        self.session_service: MagicMock = MagicMock()
        self.session_service.create_session = AsyncMock(return_value=MagicMock(id="session-1"))
        self.session_service.delete_session = AsyncMock()
        self._final_content: MagicMock | None = None

    async def run_async(self, **kwargs: Any) -> Any:
        if self._final_content is None:
            raise RuntimeError("no final content set on mock runner")
        ev = MagicMock()
        ev.is_final_response.return_value = True
        ev.content = self._final_content
        yield ev


@pytest.fixture
def mock_interviewer_runner() -> _MockRunner:
    """Provide a fresh _MockRunner per test."""
    return _MockRunner()


async def test_service_run_asks_first_question(
    mock_interviewer_runner: _MockRunner,
) -> None:
    """When question_index=0, the agent returns the first question."""
    service = InterviewerService(api_key=FAKE_KEY)

    store = SessionStore()
    store.set(
        SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW, question_index=0, responses=[])
    )

    mock_interviewer_runner._final_content = MagicMock(
        parts=[
            MagicMock(
                text=json.dumps({"next_question": "Question 1: What's your secret superpower?"})
            )
        ]
    )

    with patch.object(service, "_runner", mock_interviewer_runner):
        output = await service.run(
            user_text="start",
            chat_id=CHAT_A,
            store=store,
        )

    assert output.next_question == "Question 1: What's your secret superpower?"
    assert output.profile is None
    assert output.suggested_animal is None


async def test_service_run_advances_through_questions(
    mock_interviewer_runner: _MockRunner,
) -> None:
    """After each answer, the next question is returned, incrementing question_index."""
    service = InterviewerService(api_key=FAKE_KEY)

    store = SessionStore()
    store.set(
        SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW, question_index=0, responses=[])
    )

    responses: list[dict[str, str | None]] = [
        {"next_question": "Question 1: What's your secret superpower?"},
        {"next_question": "Question 2: If you were a zoo animal, which would you be?"},
        {"next_question": "Question 3: What's the weirdest food you've ever eaten?"},
        {"next_question": "Question 4: Describe your most embarrassing moment."},
        {"profile": "You love animals", "suggested_animal": "otter", "next_question": None},
    ]

    for i, expected in enumerate(responses):
        existing = store.get(CHAT_A)
        assert existing is not None
        existing.question_index = i
        existing.responses = [f"answer{j + 1}" for j in range(i)]
        store.set(existing)

        mock_interviewer_runner._final_content = MagicMock(
            parts=[MagicMock(text=json.dumps(expected))]
        )

        with patch.object(service, "_runner", mock_interviewer_runner):
            output = await service.run(
                user_text=f"answer{i + 1}" if i < 5 else "answer5",
                chat_id=CHAT_A,
                store=store,
            )

        assert output.next_question == expected["next_question"], f"Failed at turn {i}"

    # After 5 answers, profile/animal should be set and next_question is None
    profile_val = responses[-1]["profile"]
    animal_val = responses[-1]["suggested_animal"]
    assert profile_val is not None
    assert animal_val is not None


async def test_service_run_persists_state_across_turns(
    mock_interviewer_runner: _MockRunner,
) -> None:
    """The service writes the updated state back to the shared store."""
    service = InterviewerService(api_key=FAKE_KEY)

    store = SessionStore()
    store.set(
        SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW, question_index=0, responses=[])
    )

    mock_interviewer_runner._final_content = MagicMock(
        parts=[MagicMock(text=json.dumps({"next_question": "Q1"}))]
    )

    with patch.object(service, "_runner", mock_interviewer_runner):
        await service.run(
            user_text="start",
            chat_id=CHAT_A,
            store=store,
        )

    stored = store.get(CHAT_A)
    assert stored is not None
    assert stored.chat_id == CHAT_A


async def test_service_run_persists_the_completed_dossier_to_the_shared_store(
    mock_interviewer_runner: _MockRunner,
) -> None:
    """The finished profile and animal are available to the Scripter via state."""
    service = InterviewerService(api_key=FAKE_KEY)

    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_A,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=4,
            responses=["answer1", "answer2", "answer3", "answer4"],
        )
    )

    mock_interviewer_runner._final_content = MagicMock(
        parts=[
            MagicMock(
                text=json.dumps(
                    {
                        "profile": "A nocturnal biscuit archivist.",
                        "suggested_animal": "red panda",
                        "next_question": None,
                    }
                )
            )
        ]
    )

    with patch.object(service, "_runner", mock_interviewer_runner):
        await service.run(user_text="answer5", chat_id=CHAT_A, store=store)

    stored = store.get(CHAT_A)
    assert stored is not None
    assert stored.profile == "A nocturnal biscuit archivist."
    assert stored.suggested_animal == "red panda"
