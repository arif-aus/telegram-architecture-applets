"""The Scripter: unit tests for the ADK LlmAgent wrapper (Phase 5)."""

import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.runners import InMemoryRunner

from telegram_documentaries.scripter import (
    APP_NAME,
    MODEL,
    SCRIPTER_INSTRUCTION,
    ScripterOutput,
    ScripterService,
    _build_content,
    _validate_script,
)
from telegram_documentaries.state import Phase, SessionState, SessionStore

FAKE_KEY = "AIzaFakeGeminiKey0123456789abcdefghijklmnopqrst"

CHAT_A = 111
CHAT_B = 222

PROFILE = (
    "A nocturnal biscuit archivist who rearranges the cutlery drawer at midnight "
    "and considers crisps a food group."
)
ANIMAL = "red panda"
SCRIPT = (
    "In the hush before dawn, our subject emerges from the duvet, a red panda of "
    "the suburban wild, padding toward the kitchen with the quiet determination of "
    "a creature born to forage. Observe the ritual midnight biscuit raid, the "
    "meticulous stacking of discarded wrappers, and that curious habit of sorting "
    "spoons by moonlight. Remarkable."
)


# ---------------------------------------------------------------------------
# ScripterOutput contract tests
# ---------------------------------------------------------------------------


def test_scripter_output_accepts_the_dossier_and_script_fields() -> None:
    """The output contract carries the script plus the dossier it was built from."""
    payload = json.dumps(
        {
            "profile": PROFILE,
            "suggested_animal": ANIMAL,
            "script": SCRIPT,
            "continue_interview": False,
        }
    )

    output = ScripterOutput.model_validate_json(payload)

    assert output.profile == PROFILE
    assert output.suggested_animal == ANIMAL
    assert output.script == SCRIPT
    assert output.continue_interview is False


def test_scripter_output_defaults_continue_interview_to_false() -> None:
    """A minimal model payload still yields a complete, non-interview response."""
    output = ScripterOutput.model_validate_json(json.dumps({"script": SCRIPT}))

    assert output.script == SCRIPT
    assert output.continue_interview is False
    assert output.profile is None
    assert output.suggested_animal is None


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------


def test_scripter_service_constructs_the_flash_lite_agent_with_typed_schema() -> None:
    """Service builds an ADK LlmAgent named 'scripter' with the output schema."""
    service = ScripterService(api_key=FAKE_KEY)

    assert service._agent.name == "scripter"
    assert service._agent.output_schema is ScripterOutput
    assert getattr(service._agent.model, "model", None) == MODEL == "gemini-3.1-flash-lite"
    assert isinstance(service._runner, InMemoryRunner)


def test_instruction_pins_the_british_documentary_persona_and_limits() -> None:
    """The persona, source dossier, and one-paragraph limit are all specified."""
    assert "British" in SCRIPTER_INSTRUCTION
    assert "bedtime" in SCRIPTER_INSTRUCTION
    assert "snacking" in SCRIPTER_INSTRUCTION
    assert "90" in SCRIPTER_INSTRUCTION
    assert "one paragraph" in SCRIPTER_INSTRUCTION.lower()


# ---------------------------------------------------------------------------
# _build_content / _validate_script helper tests
# ---------------------------------------------------------------------------


def test_build_content_includes_the_profile_and_suggested_animal() -> None:
    content = _build_content(PROFILE, ANIMAL)

    assert content.role == "user"
    assert content.parts is not None
    text = "\n".join(part.text or "" for part in content.parts)
    assert PROFILE in text
    assert ANIMAL in text


def test_validate_script_collapses_newlines_into_one_paragraph() -> None:
    assert _validate_script("First line.\n\n  Second line.  ") == "First line. Second line."


def test_validate_script_removes_markdown_and_wrapping_quotes() -> None:
    assert _validate_script('**"A remarkable specimen."**') == "A remarkable specimen."


def test_validate_script_trims_to_ninety_words() -> None:
    script = " ".join(f"word{i}" for i in range(120))

    validated = _validate_script(script)

    assert len(validated.split()) == 90


def test_validate_script_rejects_an_empty_script() -> None:
    with pytest.raises(ValueError, match="empty"):
        _validate_script("   \n  ")


# ---------------------------------------------------------------------------
# Mocked ADK runner round-trips
# ---------------------------------------------------------------------------


class _MockRunner:
    """Minimal runner double that records the boundary calls and returns JSON."""

    def __init__(self) -> None:
        self.session_service: MagicMock = MagicMock()
        self.session_service.create_session = AsyncMock(return_value=MagicMock(id="session-1"))
        self.session_service.delete_session = AsyncMock()
        self.new_messages: list[Any] = []
        self.final_text: str | None = None
        self.run_error: Exception | None = None

    async def run_async(
        self, *, user_id: str, session_id: str, new_message: Any
    ) -> AsyncIterator[Any]:
        self.new_messages.append(new_message)
        if self.run_error is not None:
            raise self.run_error
        event = MagicMock()
        event.is_final_response.return_value = True
        event.content = MagicMock(parts=[MagicMock(text=self.final_text)])
        yield event


@pytest.fixture
def mock_runner() -> _MockRunner:
    """Provide a fresh runner double per test."""
    return _MockRunner()


async def test_generate_returns_the_validated_script_for_the_dossier(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.final_text = json.dumps({"script": SCRIPT})

    with patch.object(service, "_runner", mock_runner):
        output = await service.generate(
            profile=PROFILE,
            suggested_animal=ANIMAL,
            chat_id=CHAT_A,
            store=SessionStore(),
        )

    assert isinstance(output, ScripterOutput)
    assert output.script == SCRIPT
    assert output.continue_interview is False
    assert output.profile == PROFILE
    assert output.suggested_animal == ANIMAL


async def test_generate_reads_the_dossier_from_the_shared_store(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.final_text = json.dumps({"script": SCRIPT})
    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_A,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=5,
            profile=PROFILE,
            suggested_animal=ANIMAL,
        )
    )

    with patch.object(service, "_runner", mock_runner):
        output = await service.generate(chat_id=CHAT_A, store=store)

    assert output.script == SCRIPT
    assert mock_runner.new_messages
    text = "\n".join(part.text or "" for part in mock_runner.new_messages[0].parts)
    assert PROFILE in text
    assert ANIMAL in text


async def test_generate_uses_a_chat_scoped_session_and_deletes_it(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.final_text = json.dumps({"script": SCRIPT})

    with patch.object(service, "_runner", mock_runner):
        await service.generate(
            profile=PROFILE,
            suggested_animal=ANIMAL,
            chat_id=CHAT_A,
            store=SessionStore(),
        )

    mock_runner.session_service.create_session.assert_awaited_once_with(
        app_name=APP_NAME, user_id=f"scripter_{CHAT_A}"
    )
    mock_runner.session_service.delete_session.assert_awaited_once_with(
        app_name=APP_NAME, user_id=f"scripter_{CHAT_A}", session_id="session-1"
    )


async def test_generate_deletes_the_session_when_the_model_fails(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.run_error = RuntimeError("model exploded")

    with patch.object(service, "_runner", mock_runner):
        with pytest.raises(RuntimeError, match="model exploded"):
            await service.generate(
                profile=PROFILE,
                suggested_animal=ANIMAL,
                chat_id=CHAT_A,
                store=SessionStore(),
            )

    mock_runner.session_service.delete_session.assert_awaited_once()


async def test_generate_rejects_a_missing_dossier(mock_runner: _MockRunner) -> None:
    service = ScripterService(api_key=FAKE_KEY)

    with patch.object(service, "_runner", mock_runner):
        with pytest.raises(ValueError, match="profile"):
            await service.generate(chat_id=CHAT_A, store=SessionStore())

    mock_runner.session_service.create_session.assert_not_awaited()


async def test_generate_never_returns_continue_interview_true(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.final_text = json.dumps({"script": SCRIPT, "continue_interview": True})

    with patch.object(service, "_runner", mock_runner):
        output = await service.generate(
            profile=PROFILE,
            suggested_animal=ANIMAL,
            chat_id=CHAT_A,
            store=SessionStore(),
        )

    assert output.continue_interview is False


async def test_generate_trims_an_overlong_model_script(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.final_text = json.dumps({"script": " ".join(f"word{i}" for i in range(120))})

    with patch.object(service, "_runner", mock_runner):
        output = await service.generate(
            profile=PROFILE,
            suggested_animal=ANIMAL,
            chat_id=CHAT_A,
            store=SessionStore(),
        )

    assert len(output.script.split()) == 90


async def test_generate_accepts_json_wrapped_in_a_markdown_code_fence(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.final_text = f"```json\n{json.dumps({'script': SCRIPT})}\n```"

    with patch.object(service, "_runner", mock_runner):
        output = await service.generate(
            profile=PROFILE,
            suggested_animal=ANIMAL,
            chat_id=CHAT_A,
            store=SessionStore(),
        )

    assert output.script == SCRIPT


async def test_generate_rejects_unparseable_model_output(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.final_text = "definitely not json"

    with patch.object(service, "_runner", mock_runner):
        with pytest.raises(RuntimeError, match="unparsable scripter output"):
            await service.generate(
                profile=PROFILE,
                suggested_animal=ANIMAL,
                chat_id=CHAT_A,
                store=SessionStore(),
            )

    mock_runner.session_service.delete_session.assert_awaited_once()


async def test_generate_does_not_mix_dossiers_between_chats(
    mock_runner: _MockRunner,
) -> None:
    service = ScripterService(api_key=FAKE_KEY)
    mock_runner.final_text = json.dumps({"script": SCRIPT})
    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_A,
            phase=Phase.AWAITING_INTERVIEW,
            profile=PROFILE,
            suggested_animal=ANIMAL,
        )
    )
    store.set(
        SessionState(
            chat_id=CHAT_B,
            phase=Phase.AWAITING_INTERVIEW,
            profile="A different dossier entirely.",
            suggested_animal="octopus",
        )
    )

    with patch.object(service, "_runner", mock_runner):
        await service.generate(chat_id=CHAT_A, store=store)

    text = "\n".join(part.text or "" for part in mock_runner.new_messages[0].parts)
    assert PROFILE in text
    assert ANIMAL in text
    assert "different dossier" not in text
    assert "octopus" not in text
