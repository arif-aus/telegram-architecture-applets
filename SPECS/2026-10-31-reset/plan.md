# Plan — Phase 7: Explicit Session Reset

Red/Green TDD: within each task group, write the failing tests first, then the
code that makes them pass. Run checks only through the dev scripts
(`scripts/test`, `scripts/hooks`) documented in the README.

## Task group 1 — active-session registry

1. Tests first:
   - starting a session for a chat makes it active;
   - cancelling a chat invalidates only that chat's token(s);
   - a registered `asyncio` task for the chat is cancelled and awaited;
   - cancelling an unknown chat is a quiet no-op;
   - a token from another chat is unaffected.
2. Implement an `ActiveSessionRegistry` (in `reset.py`) with:
   - a typed `SessionToken` handle carrying `chat_id` and a monotonically
     increasing epoch;
   - `begin(chat_id, task=None) -> SessionToken`;
   - `is_active(token) -> bool`;
   - `async cancel(chat_id) -> int` that invalidates the chat's tokens, cancels
     registered tasks, awaits them with `return_exceptions=True`, and returns
     the number of invalidated sessions.
3. Keep the registry per-process and in-memory; no persistence.

## Task group 2 — ephemeral-asset registry

1. Tests first:
   - registering and purging a chat's files deletes them;
   - missing files are ignored;
   - a deletion failure is logged and the remaining files are still removed;
   - purging one chat leaves another chat's files alone;
   - purging an unknown chat is a quiet no-op;
   - paths are only deleted when explicitly registered (no directory scan).
2. Implement an `EphemeralAssetRegistry` (in `reset.py`) with:
   - `add(chat_id, path)`;
   - `purge(chat_id) -> int` using `Path.unlink(missing_ok=True)`, catching
     `OSError` per file, logging `event=reset.asset_delete_failed`, and
     returning the number of deleted files;
   - `paths(chat_id)` for observability/tests.
3. Normalise `chat_id` through `normalise_chat_id` so string and int keys agree.

## Task group 3 — explicit reset routine

1. Tests first:
   - a reset cancels the chat's active session, deletes its registered assets,
     and installs a fresh `AWAITING_PHOTO` session with empty history/dossier;
   - the returned `ResetOutcome` has the expected counts and phase;
   - reset is idempotent;
   - reset is isolated to the requesting chat;
   - a fresh reset of an unknown chat still installs the greeting state;
   - structured log records are emitted.
2. Implement in `reset.py`:
   - `ResetOutcome` Pydantic model (`chat_id`, `cancelled_sessions`,
     `deleted_assets`, `phase`);
   - `async def reset_chat(chat_id, *, store, sessions, assets) -> ResetOutcome`
     performing the three actions in order: cancel, purge assets, then
     `store.reset` + `store.set(SessionState(chat_id=..., phase=Phase.AWAITING_PHOTO))`.
3. Do not add persistent storage or a process restart.

## Task group 4 — handler and application wiring

1. Tests first:
   - `/start` and `/restart` call the reset routine, leave a fresh
     `AWAITING_PHOTO` state, and greet;
   - `/start` after an active interview clears responses, dossier, photo bytes,
     and question progress;
   - reset deletes a registered temp file for the chat and leaves another
     chat's file untouched;
   - the Bouncer rejection still purges the chat state without greeting and
     without creating residue;
   - existing no-raise/graceful-error behaviour is preserved.
2. Implement:
   - share one `ActiveSessionRegistry` and one `EphemeralAssetRegistry` through
     `application.bot_data` in `app.py`;
   - replace the duplicated `store.reset` + `store.set` blocks in `start` and
     `restart` with `await reset_chat(...)`;
   - make the Bouncer rejection reuse the asset/session primitives without
     re-initialising a greeting state;
   - have pipeline handlers begin/check an active-session token so work that is
     reset mid-flight aborts before committing state or sending further output.
3. Update existing handler tests' `bot_data` fixtures for the new registries.
4. Run the gateway, photo-handler, and state tests to confirm no regressions.

## Task group 5 — documentation and hygiene

1. Update `ROADMAP.md` Phase 7 to require the three explicit reset actions and
   mark the implementation status.
2. Update `SPECS/TECH.md` session-state policy, `SPECS/MISSION.md` reset success
   criterion, and `README.md` current behaviour to describe the reset routine.
3. Confirm no secret is committed; `.env` remains gitignored.
4. Run `scripts/hooks` until green.
