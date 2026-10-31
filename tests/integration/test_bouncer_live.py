"""Live Bouncer integration tests against Gemini (task group 6).

These make real API calls, so they are opt-in: run them only when
`GEMINI_API_KEY` is set **and** `RUN_LIVE_GEMINI_TESTS=1`. `tests/conftest.py`
loads the repository `.env`, so setting the opt-in variable is enough locally:

    RUN_LIVE_GEMINI_TESTS=1 scripts/test -m integration

Without the opt-in they are collected but skipped, and the default suite makes
no network or API calls.
"""

import os
from pathlib import Path

import pytest

from telegram_documentaries.bouncer import BouncerService, BouncerVerdict

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

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def bouncer() -> BouncerService:
    # Function-scoped on purpose: ADK's in-memory runner binds async clients to
    # the event loop that created them, and pytest-asyncio gives each test a
    # fresh loop. A module-scoped service would leak the first closed loop into
    # the next test.
    return BouncerService(api_key=os.environ["GEMINI_API_KEY"])


@pytest.mark.parametrize(
    ("filename", "expected_human_present"),
    [("landscape.jpg", False), ("person.jpg", True)],
)
async def test_real_bouncer_classifies_each_fixture(
    bouncer: BouncerService,
    filename: str,
    expected_human_present: bool,
) -> None:
    image_bytes = (FIXTURES / filename).read_bytes()

    verdict = await bouncer.judge(image_bytes, mime_type="image/jpeg")

    assert isinstance(verdict, BouncerVerdict)
    assert verdict.human_present is expected_human_present
    assert verdict.rationale
