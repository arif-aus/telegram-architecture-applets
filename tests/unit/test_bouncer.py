"""The Bouncer: ADK vision gate over Gemini 3.1 Flash Lite (task group 4)."""

import os
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import types
from pydantic import ValidationError

import telegram_documentaries.bouncer as bouncer_mod
from telegram_documentaries.bouncer import (
    APP_NAME,
    BouncerDecision,
    BouncerError,
    BouncerService,
    BouncerVerdict,
)

FAKE_KEY = "AIzaFakeGeminiKey0123456789abcdefghijklmnopqrst"


class ModelBoundary(SimpleNamespace):
    agent_cls: MagicMock
    runner: MagicMock
    captured: dict[str, Any]


@pytest.fixture
def model_boundary(monkeypatch: pytest.MonkeyPatch) -> ModelBoundary:
    """Fake the ADK boundary: LlmAgent construction + Runner run loop."""
    agent_cls = MagicMock()
    runner = MagicMock()
    runner.session_service.create_session = AsyncMock(return_value=SimpleNamespace(id="session-1"))
    runner.session_service.delete_session = AsyncMock()
    captured: dict[str, Any] = {}

    async def fake_run(**kwargs: Any) -> AsyncGenerator[Any, None]:
        captured.update(kwargs)
        yield _final_event(json_text=_next_json.get("payload", "{}"))

    runner.run_async = fake_run
    monkeypatch.setattr(bouncer_mod, "LlmAgent", agent_cls)
    monkeypatch.setattr(bouncer_mod, "InMemoryRunner", MagicMock(return_value=runner))
    return ModelBoundary(agent_cls=agent_cls, runner=runner, captured=captured)


_next_json = {"payload": '{"human_present": false, "rationale": "no humans"}'}


def _final_event(json_text: str) -> MagicMock:
    event = MagicMock()
    event.is_final_response.return_value = True
    event.content = types.Content(parts=[types.Part.from_text(text=json_text)])
    return event


# --- the typed output contract -------------------------------------------------


def test_bouncer_verdict_contract_accepts_a_valid_payload() -> None:
    verdict = BouncerVerdict.model_validate({"human_present": True, "rationale": "clear face"})

    assert verdict.human_present is True
    assert verdict.rationale == "clear face"


def test_bouncer_verdict_contract_rejects_a_payload_without_human_present() -> None:
    with pytest.raises(ValidationError):
        BouncerVerdict.model_validate({"rationale": "missing the point"})


def test_bouncer_verdict_contract_rejects_a_payload_without_rationale() -> None:
    with pytest.raises(ValidationError):
        BouncerVerdict.model_validate({"human_present": False})


# --- agent construction -------------------------------------------------------


def test_service_constructs_llm_agent_with_the_flash_lite_model_and_output_schema(
    model_boundary: ModelBoundary,
) -> None:
    BouncerService(api_key=FAKE_KEY)

    model_boundary.agent_cls.assert_called_once()
    kwargs = model_boundary.agent_cls.call_args.kwargs
    assert getattr(kwargs["model"], "model", None) == "gemini-3.1-flash-lite"
    assert kwargs["output_schema"] is BouncerVerdict
    assert kwargs["name"] == "bouncer"


def test_service_wires_the_agent_through_an_adk_runner(model_boundary: ModelBoundary) -> None:
    service = BouncerService(api_key=FAKE_KEY)

    assert service._runner is model_boundary.runner  # noqa: SLF001


# --- multimodal input & verdict parsing ---------------------------------------


async def test_judge_sends_the_image_bytes_as_a_multimodal_part(
    model_boundary: ModelBoundary,
) -> None:
    service = BouncerService(api_key=FAKE_KEY)

    await service.judge(b"\xff\xd8image", mime_type="image/png")

    sent = model_boundary.captured["new_message"]
    assert sent.role == "user"
    image_part = sent.parts[0]
    assert image_part.inline_data.data == b"\xff\xd8image"
    assert image_part.inline_data.mime_type == "image/png"
    assert sent.parts[1].text  # the classification question accompanies the image


async def test_judge_returns_a_validated_verdict(model_boundary: ModelBoundary) -> None:
    _next_json["payload"] = '{"human_present": true, "rationale": "a person, plainly"}'
    service = BouncerService(api_key=FAKE_KEY)

    verdict = await service.judge(b"photo")

    assert verdict == BouncerVerdict(human_present=True, rationale="a person, plainly")


async def test_judge_creates_and_cleans_up_one_session_per_call(
    model_boundary: ModelBoundary,
) -> None:
    service = BouncerService(api_key=FAKE_KEY)

    await service.judge(b"photo")

    model_boundary.runner.session_service.create_session.assert_awaited_once_with(
        app_name=APP_NAME, user_id="bouncer"
    )
    model_boundary.runner.session_service.delete_session.assert_awaited_once_with(
        app_name=APP_NAME, user_id="bouncer", session_id="session-1"
    )


async def test_judge_raises_bouncer_error_when_the_model_output_is_unparsable(
    model_boundary: ModelBoundary,
) -> None:
    _next_json["payload"] = "definitely not json"
    service = BouncerService(api_key=FAKE_KEY)

    with pytest.raises(BouncerError):
        await service.judge(b"photo")


# --- decision mapping ---------------------------------------------------------


@pytest.mark.parametrize(
    ("human_present", "expected_decision"),
    [(True, BouncerDecision.ACCEPT), (False, BouncerDecision.REJECT)],
)
async def test_decide_maps_the_verdict_to_a_decision(
    model_boundary: ModelBoundary,
    human_present: bool,
    expected_decision: BouncerDecision,
) -> None:
    _next_json["payload"] = (
        f'{{"human_present": {str(human_present).lower()}, "rationale": "seen it"}}'
    )
    service = BouncerService(api_key=FAKE_KEY)

    decision = await service.decide(b"photo", mime_type="image/jpeg")

    assert decision is expected_decision


# --- failure path -------------------------------------------------------------


async def test_decide_returns_error_and_logs_loudly_when_the_model_call_fails(
    model_boundary: ModelBoundary, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("ERROR")

    async def boom(**kwargs: Any) -> AsyncGenerator[Any, None]:
        del kwargs
        for _ in range(1):
            raise TimeoutError("gemini went to lunch")
        yield  # pragma: no cover - keeps this an async generator for the runner contract

    model_boundary.runner.run_async = boom
    service = BouncerService(api_key=FAKE_KEY)

    decision = await service.decide(b"photo", mime_type="image/png")

    assert decision is BouncerDecision.ERROR
    assert any("event=bouncer.classification_failed" in record.msg for record in caplog.records)
    error_records = [r for r in caplog.records if r.levelno >= 40]
    assert error_records, "expected at least one ERROR record"


async def test_decide_returns_error_when_the_model_output_is_garbage(
    model_boundary: ModelBoundary, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("ERROR")
    _next_json["payload"] = "not json at all"
    service = BouncerService(api_key=FAKE_KEY)

    decision = await service.decide(b"photo")

    assert decision is BouncerDecision.ERROR
    assert any("event=bouncer.classification_failed" in record.msg for record in caplog.records)


# --- API key propagation to the ADK runtime -----------------------------------


def test_service_does_not_mutate_the_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(bouncer_mod, "Client", MagicMock())
    monkeypatch.setattr(bouncer_mod, "Gemini", MagicMock())
    monkeypatch.setattr(bouncer_mod, "LlmAgent", MagicMock())
    monkeypatch.setattr(bouncer_mod, "InMemoryRunner", MagicMock())

    BouncerService(api_key=FAKE_KEY)

    assert "GEMINI_API_KEY" not in os.environ


def test_service_passes_the_api_key_to_an_explicit_genai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_cls = MagicMock()
    gemini_cls = MagicMock()
    monkeypatch.setattr(bouncer_mod, "Client", client_cls)
    monkeypatch.setattr(bouncer_mod, "Gemini", gemini_cls)
    monkeypatch.setattr(bouncer_mod, "LlmAgent", MagicMock())
    monkeypatch.setattr(bouncer_mod, "InMemoryRunner", MagicMock())

    BouncerService(api_key=FAKE_KEY)

    client_cls.assert_called_once_with(api_key=FAKE_KEY)
    gemini_cls.assert_called_once_with(
        model="gemini-3.1-flash-lite", client=client_cls.return_value
    )
