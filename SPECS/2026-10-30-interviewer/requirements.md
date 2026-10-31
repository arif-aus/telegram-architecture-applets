# Requirements — Phase 3: The Interviewer

**Date:** 2026-10-30
**Branch:** `feature/2026-10-30-interviewer`
**Roadmap:** Phase 3 (Interviewer)

## Context

The Bouncer (Phase 2) has just advanced the session phase to `AWAITING_INTERVIEW`. The Interviewer now takes over, asking 5 investigative, playful, slightly eccentric questions — one at a time — and accumulating a behavioural dossier. After the 5th answer, it synthesizes a concise personality profile and suggests an animal for the Converter stage.

## Scope

### Interview Q&A

- **5 questions** asked sequentially, exactly one per turn
- The Interviewer waits for the user's response before asking the next question
- Questions are investigative, playful, and slightly eccentric
- Responses are accumulated per `chat_id` in the shared session store
- After the 5th answer, the Interviewer synthesizes a behavioural/personality profile
- The profile includes a **suggested animal** for the next pipeline stage (Converter)

### State Management

- State tracked per `chat_id` in the shared `SessionStore`
- `question_index` (0-5): which question the user is about to answer (0 = not started, 1-5 = in progress, 5 = all answered)
- `responses`: list of user strings, one per question
- Phase stays as `AWAITING_INTERVIEW` throughout the interview
- `/start` and `/restart` purge interview state along with the rest of the session

### Hand-off

- After the 5th answer, the interviewer produces:
  - A concise behavioural/personality profile (max ~50 words)
  - A `suggested_animal` string (e.g., "red panda", "octopus", "peacock")
- These are stored in the session state and made available to the next pipeline stage
- The interviewer does NOT reset state — the next stage (Converter) reads the profile and animal from the store

### Model

- **Gemini 3.1 Flash Lite** — used for both asking questions and synthesizing the final profile
- Structured output via Pydantic output schema at the boundary
- The agent is an ADK `LlmAgent` wired through an `InMemoryRunner`

### Out of Scope

- Persistent session storage (Redis, database, disk)
- Group chats or multi-user features
- Video or GIF output
- The Converter, Scripter, or Narrator stages

## Testing Strategy

- **Unit (always run):** mocked Gemini/ADK boundary covering both the question-asking flow and the final profile synthesis
- **Integration (skipped without `GEMINI_API_KEY`):** end-to-end flow with real Gemini, verifying the 5-question sequence and profile output
- Red/Green TDD: tests written before feature code