# Plan — Phase 5: The Scripter

Red/Green TDD: within each task group, write the failing tests first, then
the code that makes them pass. Run checks only through the dev scripts
(`scripts.test`, `scripts/hooks`) documented in the README.

## Task group 1 — scripter agent ADK wrapper

1. Tests first: construct a `ScripterService` ADK `LlmAgent` with model
   `gemini-3.1-flash-lite` and a typed output schema (`ScripterOutput`);
   the model boundary is mocked.
2. Implement `scripter.py`: `ScripterService` class wrapping an ADK
   `LlmAgent` + `InMemoryRunner`. The agent instruction guides it to:
   - Read the current state from the shared `SessionStore` keyed by `chat_id`
     to get the behavioural profile and suggested animal
   - Produce exactly one paragraph (max 90 words) of dramatic British
     documentary narration, framing the subject's quirks, bedtime habits, and
     snacking patterns as funny animal behaviours
   - Output must follow the `ScripterOutput` schema with the script text
3. The agent uses structured output (Pydantic) so the handler never receives
   raw dicts.
4. Run ADK boundary tests to confirm the agent constructs correctly and the
   runner round-trips.

## Task group 2 — Telegram handler wiring

1. Tests first: `handle_interview_text` (or equivalent) in `handlers.py`
   reads the chat's current state from the shared store, delegates to the
   `ScripterService`, and either:
   - Receives the script text and replies to the user via `message.reply_text`
2. Implement the handler: after the Converter produces the hybrid image and
   replies to the chat, invoke the Scripter with the profile + animal from
   state, get the script text, and reply via `message.reply_text`.
3. Ensure that text sent when not in the appropriate flow is handled gracefully.
4. Run photo handler and gateway tests to confirm no regressions.

## Task group 3 — fixtures and live integration tests

1. Commit any new fixture data needed for integration tests (if any).
2. Integration tests (pytest marker `integration`, auto-skipped without
   `GEMINI_API_KEY`): run the real Scripter service over a simulated
   dossier and assert the script is exactly one paragraph, max 90 words,
   with the correct British documentary tone.
3. Run `scripts/hooks` until green.

## Task group 4 — documentation and hygiene

1. Update `README.md`: document the scripter flow and new `.env` considerations.
2. Confirm no secret is committed; `.env` is gitignored; no secret appears in
   logs or code.
3. Update `ROADMAP.md`: mark Phase 5 complete (or update if implementation
   diverges).
4. Run `scripts/hooks` until green.