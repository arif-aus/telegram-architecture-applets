"""The Converter: typed base64 output and ADK runner boundary (Phase 4)."""

import base64
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.runners import InMemoryRunner

from telegram_documentaries.converter import (
    APP_NAME,
    MODEL,
    ConverterOutput,
    ConverterService,
    _build_content,
    _decode_image_data,
)

FAKE_KEY = "AIzaFakeGeminiKey0123456789abcdefghijklmnopqrst"

PHOTO = b"\x89PNG\r\n\x1a\nhybrid-portrait"
PHOTO_B64 = base64.b64encode(PHOTO).decode("ascii")
CAPTION = "Behold the midnight red panda"


# ---------------------------------------------------------------------------
# Output contract: the model returns base64 text, Telegram needs raw bytes.
# ---------------------------------------------------------------------------


def test_converter_output_keeps_the_base64_text_and_decodes_to_bytes() -> None:
    output = ConverterOutput(image_data=PHOTO_B64, caption=CAPTION)

    assert output.image_data == PHOTO_B64
    assert output.image_bytes == PHOTO
    assert isinstance(output.image_data, str)


def test_converter_output_accepts_raw_bytes_for_in_process_callers() -> None:
    output = ConverterOutput.model_validate({"image_data": PHOTO, "caption": CAPTION})

    assert output.image_data == PHOTO_B64
    assert output.image_bytes == PHOTO


def test_decode_image_data_strips_a_data_uri_prefix_and_whitespace() -> None:
    wrapped = f"data:image/png;base64,\n  {PHOTO_B64}  \n"

    assert _decode_image_data(wrapped) == PHOTO


def test_decode_image_data_rejects_malformed_base64() -> None:
    with pytest.raises(ValueError, match="base64"):
        _decode_image_data("not base64!")


# ---------------------------------------------------------------------------
# Agent construction and content building
# ---------------------------------------------------------------------------


def test_converter_service_constructs_the_image_agent_with_typed_schema() -> None:
    service = ConverterService(api_key=FAKE_KEY)

    assert service._agent.name == "converter"
    assert service._agent.output_schema is ConverterOutput
    assert getattr(service._agent.model, "model", None) == MODEL == "gemini-3.1-flash-image"
    assert isinstance(service._runner, InMemoryRunner)


def test_build_content_carries_the_portrait_and_the_dossier() -> None:
    content = _build_content(PHOTO, "image/jpeg", "A biscuit archivist.", "red panda")

    assert content.role == "user"
    assert content.parts is not None
    assert content.parts[0].inline_data is not None
    text = "\n".join(part.text or "" for part in content.parts)
    assert "biscuit archivist" in text
    assert "red panda" in text


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

    async def run_async(
        self, *, user_id: str, session_id: str, new_message: Any
    ) -> AsyncIterator[Any]:
        self.new_messages.append(new_message)
        event = MagicMock()
        event.is_final_response.return_value = True
        event.content = MagicMock(parts=[MagicMock(text=self.final_text)])
        yield event


@pytest.fixture
def mock_runner() -> _MockRunner:
    return _MockRunner()


async def test_convert_decodes_the_model_base64_into_the_original_png(
    mock_runner: _MockRunner,
) -> None:
    service = ConverterService(api_key=FAKE_KEY)
    mock_runner.final_text = json.dumps({"image_data": PHOTO_B64, "caption": CAPTION})

    with patch.object(service, "_runner", mock_runner):
        output = await service.convert(
            PHOTO,
            profile="A biscuit archivist.",
            suggested_animal="red panda",
        )

    assert output.image_data == PHOTO_B64
    assert output.image_bytes == PHOTO
    assert output.caption == CAPTION
    mock_runner.session_service.create_session.assert_awaited_once_with(
        app_name=APP_NAME, user_id="converter"
    )
    mock_runner.session_service.delete_session.assert_awaited_once_with(
        app_name=APP_NAME, user_id="converter", session_id="session-1"
    )


async def test_convert_rejects_model_output_that_is_not_valid_base64(
    mock_runner: _MockRunner,
) -> None:
    service = ConverterService(api_key=FAKE_KEY)
    mock_runner.final_text = json.dumps({"image_data": "not base64!", "caption": CAPTION})

    with patch.object(service, "_runner", mock_runner):
        with pytest.raises(RuntimeError, match="base64"):
            await service.convert(PHOTO)

    mock_runner.session_service.delete_session.assert_awaited_once()
