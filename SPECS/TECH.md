# TECH — The Telegram Documentaries

## Stack

- Python.
- Telegram Bot API over **long polling** — no webhooks, no public URL.
- Google Agent Development Kit (ADK).
- Models:
  - **Bouncer** — Gemini 3.1 Flash Lite. Vision classification only: no TTS,
    no video.
  - **Interviewer** — Gemini 3.1 Flash Lite.
  - **Converter** — Gemini 3.1 Flash Image.
  - **Scripter** — Gemini 3.1 Flash Lite.
  - **Narrator** — `gemini-3.1-flash-tts-preview`. Not an agent.

## Architecture

- ADK **hub-and-spoke**. The Interviewer is the orchestrator.
- Each pipeline stage is a discrete agent or module with one responsibility.
- Explicit state-machine phases. Phase transitions are the only way control
  moves between stages.
- The Narrator is a plain call to Gemini TTS, never an agent.

## Contracts at boundaries

- Parse Telegram updates, Gemini responses, and TTS output into typed
  **Pydantic** models at the edge.
- Never pass raw dicts or unvalidated payloads across module boundaries.
- Treat all external input as untrusted and arbitrary.

## Logging and error policy

- Comprehensive structured logging. Prefer decorators over mixing logging
  into business logic.
- Non-critical, user-invisible work: **fail loudly and log**.
- On a validated user's conversation path: catch the error, log it loudly,
  and degrade gracefully so the conversation continues. Never raise into the
  user's flow.
- No bare `except: pass`. No swallowed exceptions. No un-logged fallbacks.

## Session state

- Versioned schema, keyed per `chat_id`.
- One shared state driver. No stage owns private state.
- `/start` and `/restart` purge session state and temporary media without
  restarting the process.

## Testing

- Red/Green TDD: tests are written before code.
- Dev scripts live in `scripts/` — `scripts/test` and `scripts/hooks` are the
  ground truth for tests, lint, and type checks.
- These scripts are documented here and in the README.

## Repo hygiene

- `.env` is listed in `.gitignore` and never committed.
- Dependencies are pinned and reproducible.
- Secrets are read from `.env`: `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`.

## README policy

- Any change to developer-facing behaviour updates the README in the same
  change.
- The README documents every `scripts/` entry point and how to run it.
