"""Ephemeral session state: one shared, versioned store keyed by `chat_id`.

Every pipeline stage reads and writes this single store; no stage owns private
state. Entries are purged outright by :meth:`SessionStore.reset`, which is what
`/start`, `/restart`, and a Bouncer rejection use to leave no residue behind.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

#: Bumped whenever the `SessionState` shape changes (ephemeral state dies with
#: the process, so a bump simply invalidates anything written by older code).
SCHEMA_VERSION = 2


class Phase(StrEnum):
    """Where a chat sits in the pipeline. Transitions are the only hand-offs."""

    AWAITING_PHOTO = "awaiting_photo"
    AWAITING_INTERVIEW = "awaiting_interview"


class SessionState(BaseModel):
    """Versioned snapshot of one chat's position in the pipeline."""

    schema_version: int = SCHEMA_VERSION
    chat_id: int
    phase: Phase = Phase.AWAITING_PHOTO
    # Interview state — persists across each Q&A turn within AWAITING_INTERVIEW
    question_index: int = 0  # 0 = not started, 1-5 = answers received, 5 = complete
    responses: list[str] = []  # accumulated answers, one per question
    # Completed dossier — handed from the Interviewer to the Converter/Scripter.
    profile: str | None = None  # behavioural profile once the interview completes
    suggested_animal: str | None = None  # animal emblem chosen by the Interviewer
    # Original portrait photo bytes — stored so the Converter can fuse it with the animal archetype.
    image_bytes: bytes | None = None  # set when a human photo is first received


def normalise_chat_id(chat_id: int | str) -> int:
    """Collapse Telegram's chat ids (int, or digits in a string) to one `int`.

    The whole application uses this single representation, so a chat stored
    under ``"111"`` and looked up as ``111`` always lands on the same entry.
    """
    try:
        return int(chat_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"chat_id must be an integer, got {chat_id!r}") from exc


class SessionStore:
    """In-memory `chat_id` → `SessionState` map. Not persistent; by design."""

    def __init__(self) -> None:
        self._sessions: dict[int, SessionState] = {}

    def get(self, chat_id: int | str) -> SessionState | None:
        """Return the chat's state, or ``None`` when there is no session."""
        return self._sessions.get(normalise_chat_id(chat_id))

    def set(self, state: SessionState) -> None:
        """Create or replace the session for ``state.chat_id``."""
        self._sessions[state.chat_id] = state

    def reset(self, chat_id: int | str) -> None:
        """Purge the chat's entry entirely; unknown chats are a quiet no-op."""
        self._sessions.pop(normalise_chat_id(chat_id), None)

    def __len__(self) -> int:
        return len(self._sessions)
