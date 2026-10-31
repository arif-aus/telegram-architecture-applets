Validation passes only when every step passes. Run everything through the
dev scripts, never through ad-hoc commands.

## 1. Automated checks

- [ ] `scripts/hooks` exits 0: ruff clean, mypy clean, full test suite green.
- [ ] `scripts/test` runs the unit suite with no network access required and
      no `GEMINI_API_KEY` required.
- [ ] `scripts/test -m integration` runs the live scripter tests when
      `GEMINI_API_KEY` is set, and is auto-skipped when it is not.

## 2. Unit-level behaviour verification (asserted in the suite)

- [ ] `ScripterOutput` accepts the profile and suggested_animal fields;
      script is generated from the dossier.
- [ ] When profile and suggested_animal are provided, the agent returns
      exactly one paragraph (max 90 words) with `continue_interview=False`.
- [ ] The paragraph frames the subject's quirks, bedtime habits, and snacking
      patterns as funny animal behaviours in a British documentary tone.
- [ ] The agent never returns `continue_interview=True`.
- [ ] Mocked ADK runner round-trips: create_session → run_async → delete_session
      completes cleanly for each script generation.

## 3. Live model verification (requires `GEMINI_API_KEY`)

- [ ] `scripts/test -m integration` sends profile + animal through the
      Scripter and receives a valid `ScripterOutput` with a script.
- [ ] The script is exactly one paragraph (no newline characters), max 90 words.
- [ ] The script uses a British documentary narrator persona, framing human
      quirks as funny animal behaviours.
- [ ] `suggested_animal` reference is present in the script content.
- [ ] The script is ready for direct voice synthesis (no markdown, plain text).

## 4. Constitution and documentation

- [ ] `README.md` documents the scripter flow, new entries, and `scripts/test`
      / `scripts/hooks` behaviour.
- [ ] No secret is committed; `.env` is gitignored; no secret appears in logs
      or code.
- [ ] Any drift between what was implemented and
      `SPECS/MISSION.md` / `SPECS/TECH.md` / `SPECS/ROADMAP.md` or this
      feature spec is surfaced to the user and the docs are updated with
      approval.
- [ ] ROADMAP Phase 5 acceptance lines are satisfied.