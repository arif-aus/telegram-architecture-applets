# Validation — Phase 7: Explicit Session Reset

Validation passes only when every step passes. Run everything through the dev
scripts, never through ad-hoc commands.

## 1. Automated checks

- [ ] `scripts/hooks` exits 0: ruff clean, mypy clean, full test suite green.
- [ ] `scripts/test` runs the unit suite with no network access and no
      `GEMINI_API_KEY` required.
- [ ] The new reset tests are in the default suite (not integration-only).

## 2. Action 1 — cancel active sessions

- [ ] Starting a session for a chat makes it active.
- [ ] Resetting that chat invalidates its active token(s).
- [ ] A registered `asyncio` task for the chat is cancelled and awaited.
- [ ] Resetting one chat does not cancel another chat's active session.
- [ ] Resetting a chat with no active session is a quiet no-op.
- [ ] Work that is reset mid-flight does not commit state or send further
      pipeline output.

## 3. Action 2 — purge ephemeral assets

- [ ] Files registered for the chat are deleted from disk.
- [ ] Missing files are ignored; a second purge succeeds.
- [ ] A deletion failure is logged loudly and does not abort the remaining
      deletions or raise into the handler.
- [ ] Purging one chat leaves another chat's files untouched.
- [ ] Purging an unknown chat is a quiet no-op.
- [ ] Only explicitly registered paths are deleted; no directory is scanned.

## 4. Action 3 — re-initialise agent memory

- [ ] After reset the chat has a fresh `SessionState` in `Phase.AWAITING_PHOTO`.
- [ ] Interview responses, `question_index`, `profile`, `suggested_animal`, and
      `image_bytes` are cleared.
- [ ] No long-lived ADK session or per-chat memory buffer survives the reset.
- [ ] `/start` and `/restart` both greet after the reset and do not restart the
      Python process.
- [ ] The Bouncer rejection path still purges state without greeting and
      leaves no residue.

## 5. Contract, isolation, and logging

- [ ] `ResetOutcome` is a typed Pydantic model with `chat_id`,
      `cancelled_sessions`, `deleted_assets`, and `phase`.
- [ ] Reset is idempotent and strictly per-chat.
- [ ] Structured log records exist for reset start/completion and for
      asset-deletion failures.
- [ ] No secret is committed; `.env` is gitignored; no secret appears in logs
      or code.

## 6. Constitution and documentation

- [ ] `ROADMAP.md` Phase 7 lists the three explicit reset actions and the
      acceptance criteria.
- [ ] `SPECS/TECH.md`, `SPECS/MISSION.md`, and `README.md` describe the reset
      routine accurately.
- [ ] Any drift between what was implemented and the spec is surfaced to the
      user and the docs are updated with approval.
