# Validation — Phase 4: The Converter

Validation passes only when every step passes. Run everything through the
dev scripts, never through ad-hoc commands.

## 1. Automated checks

- [ ] `scripts/hooks` exits 0: ruff clean, mypy clean, full test suite green.
- [ ] `scripts/test` runs the unit suite with no network access required and
      no `GEMINI_API_KEY` required.
- [ ] `scripts/test -m integration` runs the live Converter tests when
      `GEMINI_API_KEY` is set, and is auto-skipped when it is not.

## 2. Unit-level behaviour verification (asserted in the suite)

- [ ] `ConverterService` constructs with the flash-image model and
      `ConverterOutput` schema; agent name is "converter".
- [ ] When a photo bytes + profile + animal are provided, the agent returns
      `image_data` (base64-encoded PNG) and `caption`.
- [ ] When photo bytes are missing, the agent returns an error caption,
      no `image_data`.
- [ ] When profile/animal are missing, the agent returns an error caption,
      no `image_data`.
- [ ] The agent never returns `image_data` without a corresponding `caption`.
- [ ] Mocked ADK runner round-trips: create_session → run_async → delete_session
      completes cleanly for each converter call.

## 3. Mocked unit tests (always run, no Gemini required)

- [ ] `ConverterService` constructs with the flash-image model and
      `ConverterOutput` schema; agent name is "converter".
- [ ] When image bytes + profile + suggested_animal are provided, the agent
      returns valid base64-encoded PNG data and a caption describing the
      animal archetype chosen.
- [ ] When image bytes are absent, the agent returns an error caption and
      no `image_data`.
- [ ] When profile or suggested_animal are absent, the agent returns an error
      caption and no `image_data`.
- [ ] Mocked ADK runner round-trips complete cleanly.

## 4. Live model verification (requires `GEMINI_API_KEY`)

- [ ] `scripts/test -m integration` sends a real photo + real profile to
      Gemini 3.1 Flash Image and the verdict is a valid PNG image in
      base64 with a non-empty caption.
- [ ] The caption fuses the user's likeness with an animal archetype
      reflecting their quirks (e.g., "caffeinated badger").
- [ ] The image is a valid PNG that can be decoded and sent via Telegram.
- [ ] `scripts/test -m integration` is auto-skipped when `GEMINI_API_KEY` is
      not set.

## 5. Constitution and documentation

- [ ] `README.md` documents the converter flow, new entries, and `scripts/test`
      / `scripts/hooks` behaviour.
- [ ] No secret is committed; `.env` is gitignored; no secret appears in logs
      or code.
- [ ] Any drift between what was implemented and
      `SPECS/MISSION.md` / `SPECS/TECH.md` / `SPECS/ROADMAP.md` or this
      feature spec is surfaced to the user and the docs are updated with
      approval.
- [ ] ROADMAP Phase 4 acceptance lines are satisfied.