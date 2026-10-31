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
        self.new_messages: list[Any] = []
        self.run_error: Exception | None = None

    async def run_async(self, **kwargs: Any) -> Any:
        self.new_messages.append(kwargs.get("new_message"))
        if self.run_error is not None:
            raise self.run_error
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


async def test_service_run_advances_the_state_machine_each_turn(
    mock_interviewer_runner: _MockRunner,
) -> None:
    """The service, not the caller, appends answers and advances question_index."""
    service = InterviewerService(api_key=FAKE_KEY)

    store = SessionStore()
    store.set(
        SessionState(chat_id=CHAT_A, phase=Phase.AWAITING_INTERVIEW, question_index=0, responses=[])
    )

    questions = [f"Question {i}" for i in range(1, 6)]
    answers = [f"answer{i}" for i in range(1, 6)]

    # The first turn starts the interview but is not itself an answer.
    mock_interviewer_runner._final_content = MagicMock(
        parts=[MagicMock(text=json.dumps({"next_question": questions[0]}))]
    )
    with patch.object(service, "_runner", mock_interviewer_runner):
        output = await service.run(user_text="start", chat_id=CHAT_A, store=store)

    assert output.next_question == questions[0]
    stored = store.get(CHAT_A)
    assert stored is not None
    assert stored.responses == []
    assert stored.question_index == 1

    # Each answer is recorded by the service before the next question is asked.
    for index, (answer, next_question) in enumerate(
        zip(answers[:4], questions[1:], strict=True), start=1
    ):
        mock_interviewer_runner._final_content = MagicMock(
            parts=[MagicMock(text=json.dumps({"next_question": next_question}))]
        )
        with patch.object(service, "_runner", mock_interviewer_runner):
            output = await service.run(user_text=answer, chat_id=CHAT_A, store=store)

        assert output.next_question == next_question
        stored = store.get(CHAT_A)
        assert stored is not None
        assert stored.responses == answers[:index]
        assert stored.question_index == index

    # The fifth answer is terminal: profile + animal, no further question.
    mock_interviewer_runner._final_content = MagicMock(
        parts=[
            MagicMock(
                text=json.dumps(
                    {
                        "profile": "You love animals",
                        "suggested_animal": "otter",
                        "next_question": None,
                    }
                )
            )
        ]
    )
    with patch.object(service, "_runner", mock_interviewer_runner):
        output = await service.run(user_text=answers[4], chat_id=CHAT_A, store=store)

    assert output.next_question is None
    stored = store.get(CHAT_A)
    assert stored is not None
    assert stored.responses == answers
    assert stored.question_index == 5
    assert stored.profile == "You love animals"
    assert stored.suggested_animal == "otter"


async def test_service_run_is_terminal_once_five_answers_are_received(
    mock_interviewer_runner: _MockRunner,
) -> None:
    """A completed interview never calls the model again or records late text."""
    service = InterviewerService(api_key=FAKE_KEY)

    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_A,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=5,
            responses=["answer1", "answer2", "answer3", "answer4", "answer5"],
            profile="A nocturnal biscuit archivist.",
            suggested_animal="red panda",
        )
    )

    with patch.object(service, "_runner", mock_interviewer_runner):
        output = await service.run(user_text="one answer too many", chat_id=CHAT_A, store=store)

    assert output.next_question is None
    assert output.profile == "A nocturnal biscuit archivist."
    assert output.suggested_animal == "red panda"
    mock_interviewer_runner.session_service.create_session.assert_not_awaited()
    stored = store.get(CHAT_A)
    assert stored is not None
    assert stored.question_index == 5
    assert len(stored.responses) == 5


async def test_service_run_does_not_advance_state_when_the_model_fails(
    mock_interviewer_runner: _MockRunner,
) -> None:
    """A failed model call leaves the last good question/answer state untouched."""
    service = InterviewerService(api_key=FAKE_KEY)

    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_A,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=2,
            responses=["answer1", "answer2"],
        )
    )
    mock_interviewer_runner.run_error = RuntimeError("model exploded")

    with patch.object(service, "_runner", mock_interviewer_runner):
        with pytest.raises(RuntimeError, match="model exploded"):
            await service.run(user_text="answer3", chat_id=CHAT_A, store=store)

    stored = store.get(CHAT_A)
    assert stored is not None
    assert stored.question_index == 2
    assert stored.responses == ["answer1", "answer2"]


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
