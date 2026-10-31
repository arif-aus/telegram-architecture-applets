# Requirements — Phase 1 Gateway + The Bouncer

**Date:** 2026-10-06
**Branch:** `feature/2026-10-06-bouncer`
**Roadmap:** Phase 1 (Repository and gateway) and Phase 2 (Bouncer)

## Context

The repo currently contains only the constitution (`SPECS/MISSION.md`,
`TECH.md`, `ROADMAP.md`) and a README. There is no Python code, no Telegram
gateway, no ADK wiring, and no `scripts/` entry points. The Bouncer cannot be
wired in until the Phase 1 foundation exists, so this spec covers both:
the minimal runnable gateway and the Bouncer vision gate on top of it.

## Decisions (confirmed with user)

1. **Telegram client:** `python-telegram-bot` (long polling via its built-in
   updater, photo download, reply helpers).
2. **Verification:** unit tests with a mocked Gemini/ADK boundary that always
   run, plus live integration tests that send a real landscape photo and a
   real person photo to Gemini 3.1 Flash Lite, skipped automatically when
   `GEMINI_API_KEY` is absent. Small fixture images are committed to the repo.
3. **Human-confirmed path:** the Bouncer replies with a short confirmation and
   advances the session state machine to the next phase
   (`AWAITING_INTERVIEW`). The Interviewer itself is a later spec.
4. **Model invocation:** The Bouncer is an ADK `LlmAgent`
   (`google-adk`) that receives the image bytes as a multimodal part and
   returns a structured verdict. It is wired through an ADK `Runner`, not a
   raw Gemini client call.

## Scope

### Phase 1 — gateway foundation

- Python project with pinned, reproducible dependencies
  (`python-telegram-bot`, `google-adk`, `pydantic`, `pytest`, lint/type
  tools) described in `pyproject.toml`.
- Secrets loaded from `.env` only (`TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`);
  `.env` stays gitignored; secrets are never logged.
- A runnable long-polling entry point that answers `/start` and `/restart`
  and replies with a simple hardcoded acknowledgement to ordinary text
  (enough to satisfy ROADMAP Phase 1).
- In-memory session state keyed by `chat_id`, modelled as a versioned
  Pydantic schema with an explicit phase enum. One shared store; no stage
  owns private state.
- Structured logging configured once, with a reusable decorator so logging
  stays out of business logic.
- `scripts/test` (test runner) and `scripts/hooks` (lint, type check, tests)
  as the ground truth, documented in the README per TECH.md.

### Bouncer — vision gate

- On a photo upload: download the image bytes from Telegram, hand them to
  the ADK Bouncer agent (Gemini 3.1 Flash Lite) for multimodal
  classification of whether a discernible human face or body is present.
- The agent answers through a typed contract (Pydantic output schema) —
  never a raw dict or free-text parse across the module boundary.
- **No human detected:** purge that `chat_id`'s ephemeral session state
  (and any temp media), then reply with a humorous, cheeky rejection that
  explains the submission must contain a human.
- **Human detected:** reply with a short confirmation and advance the
  session phase to `AWAITING_INTERVIEW`; no other behaviour changes.
- All Telegram updates and Gemini responses are treated as untrusted and
  validated at the edge.
- If the classification call fails (timeout, API error): log loudly, do not
  advance the phase, do not purge state, and reply asking the user to retry.
  Never raise into the user's conversation.

## Out of scope

Everything not listed above: the Interviewer, Converter, Scripter,
Narrator, wrong-payload stage guards beyond the photo gate, persistent
storage, webhooks, group chats (see `SPECS/MISSION.md`).

## Testing strategy

- **Unit (always run):** mocked Gemini/ADK boundary covering both verdicts,
  state reset on rejection, phase advance on acceptance, and classifier
  failure degradation.
- **Integration (skipped without `GEMINI_API_KEY`):** one negative fixture
  (object/landscape) and one positive fixture (person), both committed under
  `tests/fixtures/`, sent to the real model and asserted on the verdict.
- Red/Green TDD: tests written before feature code.
