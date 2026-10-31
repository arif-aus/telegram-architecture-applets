"""Handler wiring: after the Converter, the Scripter replies with the script (Phase 5)."""

import base64
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import telegram_documentaries.handlers as handlers
from telegram_documentaries.config import Settings
from telegram_documentaries.converter import ConverterOutput
from telegram_documentaries.handlers import ACKNOWLEDGEMENT, acknowledge_text
from telegram_documentaries.interviewer import InterviewerService, InterviewOutput
from telegram_documentaries.scripter import ScripterOutput
from telegram_documentaries.state import Phase, SessionState, SessionStore

FAKE_TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALdsaw"
FAKE_KEY = "AIzaFakeGeminiKey0123456789abcdefghijklmnopqrst"

CHAT_A = 111

PROFILE = "A nocturnal biscuit archivist who sorts spoons by moonlight."
ANIMAL = "red panda"
SCRIPT = "In the hush before dawn, our red panda subject raids the biscuit tin. Remarkable."
PHOTO = b"\x89PNG\r\n\x1a\nhybrid-portrait"
PHOTO_B64 = base64.b64encode(PHOTO).decode("ascii")
CAPTION = "Behold the midnight red panda"


def make_update(text: str = "the final answer") -> MagicMock:
    message = MagicMock()
    message.text = text
    message.reply_text = AsyncMock(return_value=None)
    message.reply_photo = AsyncMock(return_value=None)
    chat = MagicMock()
    chat.id = CHAT_A
    update = MagicMock()
    update.effective_message = message
    update.effective_chat = chat
    return update


def make_context(store: SessionStore) -> MagicMock:
    context = MagicMock()
    context.bot_data = {"store": store}
    return context


def _active_interview_store(*, with_photo: bool = True) -> SessionStore:
    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_A,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=4,
            responses=["answer1", "answer2", "answer3", "answer4"],
            image_bytes=b"original-portrait" if with_photo else None,
        )
    )
    return store


def _patch_services(
    monkeypatch: pytest.MonkeyPatch,
    *,
    interviewer: Any,
    converter: MagicMock,
    scripter: MagicMock,
) -> None:
    monkeypatch.setattr(
        handlers,
        "load_settings",
        MagicMock(
            return_value=Settings(
                telegram_bot_token=FAKE_TOKEN,
                gemini_api_key=FAKE_KEY,
            )
        ),
    )
    monkeypatch.setattr(handlers, "InterviewerService", MagicMock(return_value=interviewer))
    monkeypatch.setattr(handlers, "ConverterService", MagicMock(return_value=converter))
    monkeypatch.setattr(handlers, "ScripterService", MagicMock(return_value=scripter))


def _completed_interviewer() -> MagicMock:
    interviewer = MagicMock()
    interviewer.run = AsyncMock(
        return_value=InterviewOutput(profile=PROFILE, suggested_animal=ANIMAL)
    )
    return interviewer


def _successful_converter() -> MagicMock:
    converter = MagicMock()
    converter.convert = AsyncMock(
        return_value=ConverterOutput(image_data=PHOTO_B64, caption=CAPTION)
    )
    return converter


def _successful_scripter() -> MagicMock:
    scripter = MagicMock()
    scripter.generate = AsyncMock(
        return_value=ScripterOutput(
            script=SCRIPT,
            profile=PROFILE,
            suggested_animal=ANIMAL,
            continue_interview=False,
        )
    )
    return scripter


async def test_completed_interview_runs_converter_then_scripter_and_replies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _active_interview_store()
    update = make_update()
    context = make_context(store)
    interviewer = _completed_interviewer()
    converter = _successful_converter()
    scripter = _successful_scripter()
    _patch_services(monkeypatch, interviewer=interviewer, converter=converter, scripter=scripter)

    await acknowledge_text(update, context)

    interviewer.run.assert_awaited_once_with(
        user_text="the final answer",
        chat_id=CHAT_A,
        store=store,
    )
    converter.convert.assert_awaited_once_with(
        image_bytes=b"original-portrait",
        profile=PROFILE,
        suggested_animal=ANIMAL,
    )
    # Telegram receives raw PNG bytes, never the model's base64 text.
    update.effective_message.reply_photo.assert_awaited_once_with(photo=PHOTO, caption=CAPTION)
    scripter.generate.assert_awaited_once_with(
        chat_id=CHAT_A,
        store=store,
        profile=PROFILE,
        suggested_animal=ANIMAL,
    )
    update.effective_message.reply_text.assert_any_await(SCRIPT)


async def test_completed_interview_persists_the_dossier_for_later_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _active_interview_store()
    update = make_update()
    context = make_context(store)
    _patch_services(
        monkeypatch,
        interviewer=_completed_interviewer(),
        converter=_successful_converter(),
        scripter=_successful_scripter(),
    )

    await acknowledge_text(update, context)

    stored = store.get(CHAT_A)
    assert stored is not None
    assert stored.profile == PROFILE
    assert stored.suggested_animal == ANIMAL


async def test_script_reply_arrives_after_the_hybrid_photo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _active_interview_store()
    update = make_update()
    context = make_context(store)
    sequence: list[str] = []
    update.effective_message.reply_photo.side_effect = lambda **_: sequence.append("photo")
    update.effective_message.reply_text.side_effect = sequence.append
    _patch_services(
        monkeypatch,
        interviewer=_completed_interviewer(),
        converter=_successful_converter(),
        scripter=_successful_scripter(),
    )

    await acknowledge_text(update, context)

    assert "photo" in sequence
    assert SCRIPT in sequence
    assert sequence.index("photo") < sequence.index(SCRIPT)


async def test_scripter_failure_does_not_raise_or_lose_the_sent_photo(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("ERROR")
    store = _active_interview_store()
    update = make_update()
    context = make_context(store)
    scripter = MagicMock()
    scripter.generate = AsyncMock(side_effect=RuntimeError("scriptwriter on strike"))
    _patch_services(
        monkeypatch,
        interviewer=_completed_interviewer(),
        converter=_successful_converter(),
        scripter=scripter,
    )

    await acknowledge_text(update, context)  # must not raise

    update.effective_message.reply_photo.assert_awaited_once()
    replies = [call.args[0] for call in update.effective_message.reply_text.await_args_list]
    assert SCRIPT not in replies
    assert handlers.GRACEFUL_ERROR_TEXT not in replies
    assert any(record.levelname == "ERROR" for record in caplog.records)


async def test_first_interview_turn_kicks_off_with_a_start_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_A,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=0,
            responses=[],
            image_bytes=b"original-portrait",
        )
    )
    update = make_update(text="hello there")
    context = make_context(store)
    interviewer = MagicMock()
    interviewer.run = AsyncMock(
        return_value=InterviewOutput(next_question="Question 1: What is your secret?")
    )
    _patch_services(
        monkeypatch,
        interviewer=interviewer,
        converter=_successful_converter(),
        scripter=_successful_scripter(),
    )

    await acknowledge_text(update, context)

    interviewer.run.assert_awaited_once_with(
        user_text="start",
        chat_id=CHAT_A,
        store=store,
    )
    update.effective_message.reply_text.assert_awaited_once_with("Question 1: What is your secret?")


async def test_converters_base64_payload_is_decoded_before_telegram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _active_interview_store()
    update = make_update()
    context = make_context(store)
    converter = MagicMock()
    converter.convert = AsyncMock(
        return_value=ConverterOutput(
            image_data=f"data:image/png;base64,{PHOTO_B64}",
            caption=CAPTION,
        )
    )
    _patch_services(
        monkeypatch,
        interviewer=_completed_interviewer(),
        converter=converter,
        scripter=_successful_scripter(),
    )

    await acknowledge_text(update, context)

    update.effective_message.reply_photo.assert_awaited_once_with(photo=PHOTO, caption=CAPTION)


class _ScriptedInterviewerRunner:
    """Runner double whose final payload changes between interview turns."""

    def __init__(self) -> None:
        self.session_service: MagicMock = MagicMock()
        self.session_service.create_session = AsyncMock(return_value=MagicMock(id="session-1"))
        self.session_service.delete_session = AsyncMock()
        self.final_text = "{}"

    async def run_async(
        self, *, user_id: str, session_id: str, new_message: Any
    ) -> AsyncIterator[Any]:
        del user_id, session_id, new_message
        event = MagicMock()
        event.is_final_response.return_value = True
        event.content = MagicMock(parts=[MagicMock(text=self.final_text)])
        yield event


async def test_scripter_is_reached_after_the_interview_state_machine_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_A,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=0,
            responses=[],
            image_bytes=b"original-portrait",
        )
    )
    context = make_context(store)
    interviewer = InterviewerService(api_key=FAKE_KEY)
    runner = _ScriptedInterviewerRunner()
    converter = _successful_converter()
    scripter = _successful_scripter()
    _patch_services(
        monkeypatch,
        interviewer=interviewer,
        converter=converter,
        scripter=scripter,
    )

    turns = [
        ("hello there", {"next_question": "Q1"}),
        ("answer1", {"next_question": "Q2"}),
        ("answer2", {"next_question": "Q3"}),
        ("answer3", {"next_question": "Q4"}),
        ("answer4", {"next_question": "Q5"}),
        ("answer5", {"profile": PROFILE, "suggested_animal": ANIMAL, "next_question": None}),
    ]

    with patch.object(interviewer, "_runner", runner):
        for text, payload in turns:
            runner.final_text = json.dumps(payload)
            await acknowledge_text(make_update(text), context)

    stored = store.get(CHAT_A)
    assert stored is not None
    assert stored.question_index == 5
    assert stored.responses == ["answer1", "answer2", "answer3", "answer4", "answer5"]
    assert stored.profile == PROFILE
    assert stored.suggested_animal == ANIMAL
    converter.convert.assert_awaited_once()
    scripter.generate.assert_awaited_once_with(
        chat_id=CHAT_A,
        store=store,
        profile=PROFILE,
        suggested_animal=ANIMAL,
    )


async def test_missing_photo_skips_converter_and_scripter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _active_interview_store(with_photo=False)
    update = make_update()
    context = make_context(store)
    converter = _successful_converter()
    scripter = _successful_scripter()
    _patch_services(
        monkeypatch,
        interviewer=_completed_interviewer(),
        converter=converter,
        scripter=scripter,
    )

    await acknowledge_text(update, context)

    converter.convert.assert_not_awaited()
    scripter.generate.assert_not_awaited()
    update.effective_message.reply_photo.assert_not_awaited()


async def test_text_outside_the_interview_flow_gets_the_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore()
    update = make_update()
    context = make_context(store)
    scripter = _successful_scripter()
    _patch_services(
        monkeypatch,
        interviewer=_completed_interviewer(),
        converter=_successful_converter(),
        scripter=scripter,
    )

    await acknowledge_text(update, context)

    update.effective_message.reply_text.assert_awaited_once_with(ACKNOWLEDGEMENT)
    scripter.generate.assert_not_awaited()
