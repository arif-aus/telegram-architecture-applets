# Plan — Phase 1 Gateway + The Bouncer

Red/Green TDD: within each task group, write the failing tests first, then
the code that makes them pass. Run checks only through the dev scripts
(`scripts/test`, `scripts/hooks`) documented in the README.

## Task group 1 — project skeleton and dev scripts

1. Add `pyproject.toml` with pinned dependencies
   (`python-telegram-bot`, `google-adk`, `pydantic`, `pytest`, `ruff`,
   `mypy`) and project metadata.
2. Add `scripts/test` — runs the test suite via pytest; honours pytest
   markers (e.g. `-m integration` for live tests).
3. Add `scripts/hooks` — ruff lint/format check, mypy type check, then
   `scripts/test`; exit non-zero on any failure. Make both scripts
   executable.
4. Add `src/telegram_documentaries/` package layout (config, logging,
   state, telegram handlers, bouncer, app entry).
5. Tests first: config loads `TELEGRAM_BOT_TOKEN` / `GEMINI_API_KEY` from
   `.env`; missing secret raises loudly at startup; logging decorator emits
   structured records without touching business logic.

## Task group 2 — session state

1. Tests first: `SessionState` Pydantic model (versioned schema, `phase`
   enum), in-memory store keyed by `chat_id` (normalised to a single
   consistent type — decide string vs int and apply it everywhere),
   `reset(chat_id)` purges the entry entirely, no cross-chat leakage.
2. Implement `state.py`: phase enum (`AWAITING_PHOTO`, `AWAITING_INTERVIEW`),
   `SessionStore` with get/set/reset, backed by a plain dict.

## Task group 3 — Telegram gateway (Phase 1)

1. Tests first: `/start` creates a fresh session and greets; `/restart`
   purges and re-greets; plain text with no session gets the hardcoded
   acknowledgement; handlers never raise into the poll loop.
2. Implement `app.py`: `python-telegram-bot` `Application` with long
   polling, `config` wiring, structured logging setup, handlers from (1).
3. Runnable entry point (module `__main__` / `python -m
   telegram_documentaries`) that boots the app from `.env`.

## Task group 4 — The Bouncer ADK agent

1. Tests first: `BouncerVerdict` typed output contract (`human_present:
   bool`, `rationale: str` for logs); the ADK `LlmAgent` is constructed
   with model `gemini-3.1-flash-lite` and the output schema; image bytes are
   passed as a multimodal part; the service maps verdict → decision
   (`accept` | `reject`) — with the model boundary mocked.
2. Implement `bouncer.py`: ADK `LlmAgent` + `Runner` invocation helper that
   takes raw image bytes and returns a validated `BouncerVerdict`.
3. Failure path tests: Gemini exception/timeout ⇒ log loudly, return a
   distinct `error` decision — never advance, never purge.

## Task group 5 — photo handler wiring

1. Tests first: photo handler downloads largest photo size bytes, calls the
   Bouncer service, then:
   - `reject` ⇒ purge session state for that `chat_id`, reply with the
     cheeky rejection copy;
   - `accept` ⇒ set phase `AWAITING_INTERVIEW`, reply with confirmation;
   - `error` ⇒ leave state untouched, reply "try again", log loudly.
   Use the mocked service boundary; assert the Telegram calls.
2. Implement the handler and wire it into the application in `app.py`.

## Task group 6 — fixtures and live integration tests

1. Commit two small fixture images under `tests/fixtures/`:
   `landscape.jpg` (object/landscape, no human) and `person.jpg` (a
   recognisable human). Source public-domain/CC0 images; keep each small.
2. Integration tests (pytest marker `integration`, auto-skipped without
   `GEMINI_API_KEY`): run the real Bouncer service over each fixture and
   assert `human_present` is `False` for the landscape and `True` for the
   person.

## Task group 7 — documentation and hygiene

1. Update `README.md`: how to install, configure `.env`, run the bot, and
   what `scripts/test` / `scripts/hooks` do (README policy in TECH.md).
2. Confirm `.env` remains gitignored and no secret appears in code, logs,
   or committed files.
3. Run `scripts/hooks` until green.
