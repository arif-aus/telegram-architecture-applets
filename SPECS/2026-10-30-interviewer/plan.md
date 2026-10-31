# Plan — Phase 3: The Interviewer

Red/Green TDD: within each task group, write the failing tests first, then
the code that makes them pass. Run checks only through the dev scripts
(`scripts/test`, `scripts/hooks`) documented in the README.

## Task group 1 — session state extensions

1. Tests first: add `question_index` and `responses` fields to `SessionState`
   Pydantic model; `question_index` defaults to 0, `responses` defaults to `[]`.
2. Implement the extensions in `state.py`; ensure `normalise_chat_id` works
   correctly with the new fields (it doesn't need to — they're derived from
   `chat_id`).
3. Run existing state tests to confirm no regressions.

## Task group 2 — interviewer agent ADK wrapper

1. Tests first: construct an `InterviewerService` ADK `LlmAgent` with model
   `gemini-3.1-flash-lite` and a typed output schema (`InterviewResponse`);
   the model boundary is mocked.
2. Implement `interviewer.py`: `InterviewerService` class wrapping an ADK
   `LlmAgent` + `InMemoryRunner`. The agent instruction guides it to:
   - Read the current `question_index` and `responses` from the shared
     `SessionStore` keyed by `chat_id`
   - If `question_index < 5`: produce the next investigative/playful/eccentric
     question, mark `continue_interview=True`, and increment `question_index` after
     the user responds
   - If `question_index == 5`: synthesise a concise behavioural/personality
     profile and `suggested_animal`; mark `complete=True`
3. The agent uses structured output (Pydantic) so the handler never receives
   raw dicts.
4. Run ADK boundary tests to confirm the agent constructs correctly and the
   runner round-trips.

## Task group 3 — Telegram handler wiring

1. Tests first: `handle_interview_text` in `handlers.py` reads the chat's
   current state from the shared store, delegates to the `InterviewerService`,
   and either:
   - Receives a new question text and replies to the user
   - Receives the final profile + animal and replies to the user, then the
     conversation reaches a natural endpoint (next stage picks up from state)
2. Implement the handler: when user sends text during `AWAITING_INTERVIEW` phase,
   pass the message to the interviewer service, get the response (question or
   profile), and reply via `message.reply_text`.
3. Ensure that text sent when not in `AWAITING_INTERVIEW` is handled gracefully
   (the existing `acknowledge_text` handler takes care of this).
4. Run photo handler and gateway tests to confirm no regressions.

## Task group 4 — app.py wiring

1. Tests first: `build_application` in `app.py` creates an `InterviewerService`
   instance and wires it into `bot_data` alongside the existing `BouncerService`
   and `SessionStore`.
2. Add the interview text message handler to the application.
3. Ensure the entry point still boots cleanly.

## Task group 5 — fixtures and live integration tests

1. Commit any new fixture data needed for integration tests (if any).
2. Integration tests (pytest marker `integration`, auto-skipped without
   `GEMINI_API_KEY`): run the real Interviewer service over a simulated
   conversation and assert the 5-question sequence and profile output.
3. Run `scripts/hooks` until green.

## Task group 6 — documentation and hygiene

1. Update `README.md`: document the interview flow, new `.env` considerations,
   and `scripts/test` / `scripts/hooks` behaviour.
2. Confirm no secret is committed; `.env` is gitignored; no secret appears in
   logs or code.
3. Update `ROADMAP.md`: mark Phase 3 complete (or update if implementation
   diverges).
4. Run `scripts/hooks` until green.