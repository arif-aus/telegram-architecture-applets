# Validation — Phase 1 Gateway + The Bouncer

Validation passes only when every step passes. Run everything through the
dev scripts, never through ad-hoc commands.

## 1. Automated checks

- [ ] `scripts/hooks` exits 0: ruff clean, mypy clean, full test suite green.
- [ ] `scripts/test` runs the unit suite with no network access required and
      no `GEMINI_API_KEY` required.
- [ ] Integration tests are collected but **skipped** when `GEMINI_API_KEY`
      is unset, and **run** when it is set.

## 2. Live model verification (requires `GEMINI_API_KEY`)

- [ ] `scripts/test -m integration` sends `tests/fixtures/landscape.jpg`
      (object/landscape) to Gemini 3.1 Flash Lite and the verdict is
      `human_present = False`.
- [ ] The same run sends `tests/fixtures/person.jpg` (a person) and the
      verdict is `human_present = True`.
- [ ] Both fixture images are committed and small (< 500 KB each).

## 3. Behaviour verification (unit level, asserted in the suite)

- [ ] Rejection path: no human ⇒ session state for that `chat_id` is purged
      and a humorous rejection is sent.
- [ ] Acceptance path: human ⇒ phase advances to `AWAITING_INTERVIEW` and a
      confirmation is sent.
- [ ] Classifier failure ⇒ state untouched, user asked to retry, error
      logged loudly.
- [ ] `/start` and `/restart` purge session state without restarting the
      process.
- [ ] One chat's state is never visible to another chat.

## 4. Manual smoke test

- [ ] With a valid `.env`, the bot runs via the documented entry point and
      answers in Telegram using long polling (no webhooks).
- [ ] Sending a landscape photo elicits the cheeky rejection and leaves no
      session residue (a follow-up `/start` behaves fresh).
- [ ] Sending a portrait photo elicits the confirmation.

## 5. Constitution and documentation

- [ ] `README.md` documents `.env`, the entry point, `scripts/test`, and
      `scripts/hooks`.
- [ ] No secret is committed; `.env` is gitignored; no secret appears in
      logs or code.
- [ ] Any drift between what was implemented and
      `SPECS/MISSION.md` / `SPECS/TECH.md` / `SPECS/ROADMAP.md` or this
      feature spec is surfaced to the user and the docs are updated with
      approval.
- [ ] ROADMAP Phase 1 and Phase 2 acceptance lines are satisfied (or the
      ROADMAP is updated to reflect reality).
