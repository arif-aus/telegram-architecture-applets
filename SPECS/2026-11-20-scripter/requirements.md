# Requirements — Phase 5: The Scripter

**Date:** 2026-11-20
**Branch:** `feature/2026-11-20-scripter`
**Roadmap:** Phase 5 (Scripter)

## Context

The Converter (Phase 4) has just produced the hybrid animal portrait and delivered it to the user's Telegram chat. The session is still in `AWAITING_INTERVIEW` phase, but the dossier (behavioural profile + suggested animal) is available in the shared session state. The Scripter now writes one paragraph of dramatic British documentary narration built from the dossier, which will be sent to the user's Telegram chat and then passed to the Narrator (Phase 6) for TTS synthesis.

## Scope

### Input

- Behavioural profile from the Interviewer stage (concise ~50 word profile of user quirks and habits)
- Suggested animal from the Interviewer stage (e.g. "red panda", "octopus", "peacock")
- These are stored in the session state from the Interviewer output

### Output

- Exactly one paragraph (maximum 90 words)
- No markdown formatting
- Dramatic British wildlife documentary narrator persona
- The subject's quirks, bedtime habits, and snacking patterns framed as funny animal behaviours
- Ready for voice synthesis

### Model

- **Gemini 3.1 Flash Lite** — used for structured text generation
- Structured output via Pydantic output schema at the boundary
- The agent is an ADK `LlmAgent` wired through an `InMemoryRunner`

### Out of Scope

- Persistent session storage (Redis, database, disk)
- Video or GIF output
- TTS synthesis (handled by the Narrator phase)
- The Converter or Bouncer stages

### Testing Strategy

- **Unit (always run):** mocked Gemini/ADK boundary covering script generation from dossier
- **Integration (skipped without `GEMINI_API_KEY`):** end-to-end flow with real Gemini, verifying the script output word count and tone
- Red/Green TDD: tests written before feature code