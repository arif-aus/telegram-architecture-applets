"""Live Scripter integration tests against Gemini (Phase 5).

These make real API calls, so they are opt-in: run them only when
`GEMINI_API_KEY` is set **and** `RUN_LIVE_GEMINI_TESTS=1`. `tests/conftest.py`
loads the repository `.env`, so setting the opt-in variable is enough locally:

    RUN_LIVE_GEMINI_TESTS=1 scripts/test -m integration

Without the opt-in they are collected but skipped, and the default suite makes
no network or API calls.
"""

import os

import pytest

from telegram_documentaries.scripter import ScripterOutput, ScripterService
from telegram_documentaries.state import Phase, SessionState, SessionStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY") or os.environ.get("RUN_LIVE_GEMINI_TESTS") != "1",
        reason=(
            "live Gemini tests are opt-in: set GEMINI_API_KEY and "
            "RUN_LIVE_GEMINI_TESTS=1 to enable them"
        ),
    ),
]

CHAT_ID = 987654321

PROFILE = (
    "A nocturnal biscuit archivist who rearranges the cutlery drawer at midnight, "
    "hoards half-finished cups of tea, and considers crisps a balanced breakfast."
)
ANIMAL = "red panda"

#: Words and phrases a British wildlife documentary narrator would plausibly use.
DOCUMENTARY_MARKERS = {
    "remarkable",
    "extraordinary",
    "fascinating",
    "curious",
    "observe",
    "our subject",
    "in the wild",
    "nature",
    "indeed",
    "behold",
    "creature",
    "specimen",
}


@pytest.fixture
def scripter() -> ScripterService:
    # Function-scoped on purpose: ADK's in-memory runner binds async clients to
    # the event loop that created them, and pytest-asyncio gives each test a
    # fresh loop. A module-scoped service would leak the first closed loop into
    # the next test.
    return ScripterService(api_key=os.environ["GEMINI_API_KEY"])


async def test_real_scripter_turns_a_dossier_into_one_paragraph(scripter: ScripterService) -> None:
    store = SessionStore()
    store.set(
        SessionState(
            chat_id=CHAT_ID,
            phase=Phase.AWAITING_INTERVIEW,
            question_index=5,
            profile=PROFILE,
            suggested_animal=ANIMAL,
        )
    )

    output = await scripter.generate(chat_id=CHAT_ID, store=store)

    assert isinstance(output, ScripterOutput)
    assert output.continue_interview is False
    script = output.script

    # Ready for TTS: one plain-text paragraph, no line breaks or markdown.
    assert script.strip()
    assert "\n" not in script
    assert "\r" not in script
    assert not any(marker in script for marker in ("**", "__", "`", "#", "[", "]"))

    # One paragraph, capped at 90 words.
    assert len(script.split()) <= 90

    # The animal emblem and a documentary narrator register both survive.
    assert "panda" in script.lower()
    assert any(marker in script.lower() for marker in DOCUMENTARY_MARKERS)
