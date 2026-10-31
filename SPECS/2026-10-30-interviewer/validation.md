# Validation — Phase 3: The Interviewer

Validation passes only when every step passes. Run everything through the
dev scripts, never through ad-hoc commands.

## 1. Automated checks

- [ ] `scripts/hooks` exits 0: ruff clean, mypy clean, full test suite green.
- [ ] `scripts/test` runs the unit suite with no network access required and
      no `GEMINI_API_KEY` required.
- [ ] `scripts/test -m integration` runs the live interviewer tests when
      `GEMINI_API_KEY` is set, and is auto-skipped when it is not.

## 2. Unit-level behaviour verification (asserted in the suite)

- [ ] `SessionState` accepts `question_index` and `responses` fields; `question_index`
      defaults to 0, `responses` defaults to `[]`.
- [ ] Store lookup by string finds the entry stored under the int (and vice versa)
      after the state extension.
- [ ] `/start` and `/restart` purge the interview state (`question_index=0`,
      `responses=[]`) along with the rest of the session.
- [ ] One chat's interview state is never visible to another chat.

## 3. Mocked unit tests (always run, no Gemini required)

- [ ] `InterviewerService` constructs with the flash-lite model and
      `InterviewOutput` schema; agent name is "interviewer".
- [ ] When `question_index < 5`, the agent returns the next question with
      `continue_interview=True` and `profile=None`/`suggested_animal=None`.
- [ ] When `question_index == 5`, the agent returns `complete=True`,
      a behavioural profile, and a `suggested_animal`.
- [ ] The agent never returns `continue_interview=True` when
      `question_index == 5`.
- [ ] Mocked ADK runner round-trips: create_session → run_async → delete_session
      completes cleanly for each question.

## 4. Live model verification (requires `GEMINI_API_KEY`)

- [ ] `scripts/test -m integration` sends 5 text responses through the
      Interviewer and receives a valid `InterviewOutput` with a profile and
      animal.
- [ ] The profile is concise (≈ 50 words or fewer) and covers relevant quirks
      and habits derived from the 5 answers.
- [ ] `suggested_animal` is a non-empty string.
- [ ] The interview resumes correctly across Telegram messages: after the bot
      sends question N, the user replies with text, and the bot sends question
      N+1 (or the final profile if N=5).

## 5. Constitution and documentation

- [ ] `README.md` documents the interview flow, new entries, and `scripts/test`
      / `scripts/hooks` behaviour.
- [ ] No secret is committed; `.env` is gitignored; no secret appears in logs
      or code.
- [ ] Any drift between what was implemented and
      `SPECS/MISSION.md` / `SPECS/TECH.md` / `SPECS/ROADMAP.md` or this
      feature spec is surfaced to the user and the docs are updated with
      approval.
- [ ] ROADMAP Phase 3 acceptance lines are satisfied.