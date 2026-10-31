"""Committed Bouncer fixtures must exist, be real JPEGs, and stay small (task group 6)."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MAX_BYTES = 500 * 1024


@pytest.mark.parametrize("filename", ["landscape.jpg", "person.jpg"])
def test_bouncer_fixture_is_a_small_jpeg(filename: str) -> None:
    path = FIXTURES / filename

    assert path.is_file(), f"missing fixture: {path}"
    data = path.read_bytes()
    assert data.startswith(b"\xff\xd8\xff"), "fixture must be a JPEG"
    assert data.endswith(b"\xff\xd9"), "fixture must be a complete JPEG"
    assert len(data) < MAX_BYTES, "fixture must be smaller than 500 KB"
