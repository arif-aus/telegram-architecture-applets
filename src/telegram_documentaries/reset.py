"""Explicit per-chat reset: cancel active work, purge temp assets, re-init state.

The reset routine is deliberately small and in-memory. It is the one place that
knows how to return a chat to the greeting stage without restarting the process;
``/start``, ``/restart``, and the Bouncer rejection path reuse these primitives.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from telegram_documentaries.state import (
    Phase,
    SessionState,
    SessionStore,
    normalise_chat_id,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionToken:
    """A handle to one chat's active pipeline session.

    Tokens are invalidated as soon as the session is finished or the chat is
    reset, so stale work can cheaply check whether it may still commit state or
    send output.
    """

    chat_id: int
    epoch: int


class ActiveSessionRegistry:
    """Per-process registry of in-flight pipeline sessions, keyed by ``chat_id``."""

    def __init__(self) -> None:
        self._next_epoch: dict[int, int] = {}
        self._tasks: dict[int, dict[int, asyncio.Task[Any] | None]] = {}

    def begin(
        self,
        chat_id: int | str,
        task: asyncio.Task[Any] | None = None,
    ) -> SessionToken:
        """Start a session for ``chat_id`` and return its typed token."""
        cid = normalise_chat_id(chat_id)
        epoch = self._next_epoch.get(cid, 0) + 1
        self._next_epoch[cid] = epoch
        self._tasks.setdefault(cid, {})[epoch] = task
        return SessionToken(chat_id=cid, epoch=epoch)

    def is_active(self, token: SessionToken) -> bool:
        """True while ``token`` has not been finished or reset away."""
        return token.epoch in self._tasks.get(token.chat_id, {})

    def finish(self, token: SessionToken) -> None:
        """End a session normally; a stale or already-reset token is a no-op."""
        tasks = self._tasks.get(token.chat_id)
        if tasks is None:
            return
        tasks.pop(token.epoch, None)
        if not tasks:
            self._tasks.pop(token.chat_id, None)

    async def cancel(self, chat_id: int | str) -> int:
        """Invalidate every session for ``chat_id`` and cancel its tasks.

        Tokens are invalidated *before* tasks are cancelled so a cancelled
        handler cannot race a still-active token check. Tasks are awaited with
        ``return_exceptions=True``; cancellation is never re-raised to callers.
        """
        cid = normalise_chat_id(chat_id)
        sessions = self._tasks.pop(cid, {})

        tasks = [task for task in sessions.values() if task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return len(sessions)


class EphemeralAssetRegistry:
    """Per-process registry of temporary files created for each chat."""

    def __init__(self) -> None:
        self._paths: dict[int, set[Path]] = {}

    def add(self, chat_id: int | str, path: str | Path) -> None:
        """Record one explicitly-created temporary file for ``chat_id``."""
        cid = normalise_chat_id(chat_id)
        self._paths.setdefault(cid, set()).add(Path(path))

    def paths(self, chat_id: int | str) -> tuple[Path, ...]:
        """Return the chat's registered paths, for observability and tests."""
        cid = normalise_chat_id(chat_id)
        return tuple(sorted(self._paths.get(cid, set()), key=str))

    def purge(self, chat_id: int | str) -> int:
        """Delete every registered file for ``chat_id`` and clear the entry.

        Missing files are ignored. A file that cannot be deleted is logged
        loudly and the purge continues; this method never raises from a failed
        deletion. Only explicitly registered paths are touched.
        """
        cid = normalise_chat_id(chat_id)
        paths = self._paths.pop(cid, set())
        deleted = 0

        for path in paths:
            try:
                existed = path.exists()
                path.unlink(missing_ok=True)
            except OSError:
                logger.error(
                    "event=reset.asset_delete_failed chat_id=%s path=%s",
                    cid,
                    path,
                    exc_info=True,
                )
                continue
            if existed:
                deleted += 1

        return deleted


class ResetOutcome(BaseModel):
    """Typed result of one explicit reset, returned across the module boundary."""

    chat_id: int
    cancelled_sessions: int
    deleted_assets: int
    phase: Phase


async def reset_chat(
    chat_id: int | str,
    *,
    store: SessionStore,
    sessions: ActiveSessionRegistry,
    assets: EphemeralAssetRegistry,
) -> ResetOutcome:
    """Return one chat to the greeting stage: cancel, purge, then re-initialise."""
    cid = normalise_chat_id(chat_id)
    logger.info("event=reset.start chat_id=%s", cid)

    cancelled_sessions = await sessions.cancel(cid)
    deleted_assets = assets.purge(cid)

    store.reset(cid)
    store.set(SessionState(chat_id=cid, phase=Phase.AWAITING_PHOTO))
    phase = Phase.AWAITING_PHOTO

    logger.info(
        "event=reset.complete chat_id=%s cancelled_sessions=%s deleted_assets=%s phase=%s",
        cid,
        cancelled_sessions,
        deleted_assets,
        phase.value,
    )
    return ResetOutcome(
        chat_id=cid,
        cancelled_sessions=cancelled_sessions,
        deleted_assets=deleted_assets,
        phase=phase,
    )
