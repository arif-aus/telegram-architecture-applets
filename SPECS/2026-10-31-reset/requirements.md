# Requirements — Phase 7: Explicit Session Reset

**Date:** 2026-10-31
**Branch:** `feature/2026-11-20-scripter` (the current feature branch; the reset
work builds on the unmerged Bouncer/Interviewer/Converter/Scripter pipeline)
**Roadmap:** Phase 7 (Resilience)

## Context

`/start` and `/restart` currently call `SessionStore.reset()` and then write a
fresh `SessionState` directly in each handler. That clears the shared store, but
it is not an explicit reset routine: it does not invalidate in-flight work, it
has no way to remove temporary media, and the same logic is duplicated.

The pipeline also has ephemeral assets that will grow beyond in-memory bytes:
the original portrait, the Converter's PNG, and (once Phase 6 lands) the
Narrator's OGG/MP3 voice files. A reset must be able to remove all of them for
the requesting chat without restarting the Python process.

This spec introduces one explicit reset routine with three required actions.

## Scope

### 1. Cancel active sessions

- Add a per-chat active-session registry. A session is "active" from the moment
  a handler starts multi-step pipeline work until it finishes or is cancelled.
- The reset routine must terminate any running interview loop or waiting state
  for the requesting `chat_id`:
  - invalidate the chat's active session token(s) so stale work cannot commit
    state or send further pipeline output, and
  - cancel any registered `asyncio` tasks for that chat.
- Work belonging to other chats must never be cancelled.
- A reset for a chat with no active session is a quiet no-op for this action.

### 2. Purge ephemeral assets

- Add a per-chat ephemeral-asset registry that records the paths of temporary
  files created for a chat (original photo, converted PNG, generated OGG/MP3
  voice files).
- The reset routine must delete every registered file for the requesting
  `chat_id`, then clear the chat's registry entry.
- Missing files are ignored (idempotent reset). A file that cannot be deleted is
  logged loudly and does not stop the rest of the reset; it must never raise
  into the user's conversation.
- Only paths explicitly registered by the pipeline are deleted. The routine
  must never scan a directory or delete an arbitrary path supplied by a user.
- In-memory media (`SessionState.image_bytes`) is discarded when the session
  state is re-initialised; it does not need a disk path.

### 3. Re-initialise agent memory

- The reset routine must clear the chat's conversation history buffers and
  state trackers:
  - accumulated interview responses,
  - completed dossier (`profile`, `suggested_animal`),
  - original photo bytes,
  - question progress.
- It must then install a fresh `SessionState` at the greeting stage
  (`Phase.AWAITING_PHOTO`) for the requesting `chat_id`.
- ADK sessions are already created per call and deleted in `finally`; no
  long-lived ADK session may survive a reset. Any future per-chat memory buffer
  must be cleared by this same routine.

## Behaviour

- `/start` and `/restart` both run the explicit reset routine and then send the
  existing greeting. They must not restart the Python process.
- The Bouncer rejection path keeps its current semantics: it purges the chat's
  state and replies with the rejection, without sending a greeting. It may reuse
  the same asset/session primitives but must not re-initialise a greeting state.
- The reset routine returns a typed `ResetOutcome` (Pydantic) with the
  `chat_id`, the number of cancelled sessions, the number of deleted assets, and
  the resulting phase. No raw dict crosses the boundary.
- A reset is idempotent: running it twice in a row succeeds, and the second run
  finds nothing to cancel or delete.
- Reset is strictly per-chat: another chat's state, assets, and active sessions
  are untouched.
- The routine emits structured log records for start/completion and for any
  asset-deletion failure.

## Out of scope

- Writing new media to disk now. The registry is the contract future stages use;
  the current Converter keeps returning in-memory bytes.
- The Narrator/TTS implementation itself.
- Persistent storage, process restart, webhooks, group chats, or changes to the
  pipeline stages' prompts/models.
- A public reset API or an admin command.

## Decisions confirmed with user

1. Create a dedicated reset spec and implement it on the current feature branch
   (which already contains the Bouncer/Interviewer/Converter/Scripter work).
2. Track ephemeral asset paths per chat and delete them on reset; do not move the
   current in-memory media to disk as part of this feature.
3. Keep `/start` and `/restart` as the only commands that run the full
   reset-and-greet flow.

## Testing strategy

- **Unit (always run):** reset routine with mocked/real registries covering all
  three actions, isolation between chats, idempotency, missing files, deletion
  failures, and handler wiring for `/start`, `/restart`, and the Bouncer
  rejection path.
- **No live model calls** are required for this feature.
- Red/Green TDD: tests are written before the code that makes them pass.
