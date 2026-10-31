# Plan — Phase 4: The Converter

Red/Green TDD: within each task group, write the failing tests first, then
the code that makes them pass. Run checks only through the dev scripts
(`scripts/test`, `scripts/hooks`) documented in the README.

## Task group 1 — Session state extension for photo storage

1. Tests first: add `image_bytes` field to `SessionState` Pydantic model; default
   to `None`, set when the Bouncer accepts a human portrait.
2. Implement the extension in `state.py`; ensure round-trips through JSON
   serialization/deserialization work (Pydantic v2 handles `bytes` as base64).
3. Run existing state tests to confirm no regressions.

## Task group 2 — Converter ADK agent

1. Tests first: construct a `ConverterService` ADK `LlmAgent` with model
   `gemini-3.1-flash-image` and a typed output schema (`ConverterOutput`); the
   model boundary is mocked.
2. Implement `converter.py`: `ConverterService` class wrapping an ADK `LlmAgent`
   + `InMemoryRunner`. The agent instruction guides it to:
   - Read the user's original portrait bytes and the Interviewer's behavioural
     profile + suggested_animal from the shared `SessionStore` keyed by `chat_id`.
   - Fuse the likeness with the animal archetype that reflects the user's
     quirks (e.g., "caffeinated badger", "meticulous beaver").
   - Output the hybrid portrait as PNG bytes (base64-encoded) plus a short
     caption, following the `ConverterOutput` schema.
3. The agent uses structured output (Pydantic) so the handler never receives
   raw dicts.
4. Run ADK boundary tests to confirm the agent constructs correctly and the
   runner round-trips.

## Task group 3 — Telegram handler wiring for Converter

1. Tests first: in `handlers.py`, when the Interviewer completes (profile +
   suggested_animal available), the handler invokes the `ConverterService`,
   retrieves the stored photo bytes from the shared store, and passes both to
   the converter. The converter returns image bytes, which the handler sends
   to the user's chat via `message.reply_photo`.
2. Ensure that the conversation flow is:
   - Bouncer accepts photo → `AWAITING_INTERVIEW`
   - Interviewer completes 5 questions → profile + animal produced
   - Converter fuses photo + profile/animal → hybrid image sent to chat
3. Ensure that text sent when the converter is expected is handled gracefully.
4. Run photo handler and gateway tests to confirm no regressions.

## Task group 4 — app.py wiring

1. Tests first: `build_application` in `app.py` creates a `ConverterService`
   instance and wires it into `bot_data` alongside the existing
   `BouncerService` and `InterviewerService`.
2. Add the converter invocation to the handler flow after the Interviewer
   completes.
3. Ensure the entry point still boots cleanly.

## Task group 5 — fixtures and live integration tests

1. Commit any new fixture data needed for integration tests (if any).
2. Integration tests (pytest marker `integration`, auto-skipped without
   `GEMINI_API_KEY`): run the real Converter service over a simulated
   conversation (photo + profile) and assert the returned image is valid PNG
   with a caption.
3. Run `scripts/hooks` until green.

## Task group 6 — documentation and hygiene

1. Update `README.md`: document the converter flow, new `.env`
   considerations, and `scripts/test` / `scripts/hooks` behaviour.
2. Confirm no secret is committed; `.env` is gitignored; no secret appears in
   logs or code.
3. Update `ROADMAP.md`: mark Phase 4 complete (or update if implementation
   diverges).
4. Run `scripts/hooks` until green.