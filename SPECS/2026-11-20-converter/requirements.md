# Requirements — Phase 4: The Converter

**Date:** 2026-11-20
**Branch:** `feature/2026-11-20-converter`
**Roadmap:** Phase 4 (Converter)

## Context

The Interviewer (Phase 3) has just completed the 5-question interview, producing a behavioural profile and a suggested animal for the user. The Converter now fuses the user's original portrait photo with the interviewed animal archetype into a hybrid animal portrait, delivered directly as an image to the user's Telegram chat.

## Scope

### Converter — multimodal image fusion

- **Input 1:** The user's original portrait photo bytes (retrieved from the shared `SessionStore` keyed by `chat_id`, set when the photo was first received and the Bouncer accepted).
- **Input 2:** The Interviewer's behavioural profile and `suggested_animal` (also keyed by `chat_id` in the shared store).
- **Model:** Gemini 3.1 Flash Image (multimodal model that accepts both an image and text prompt).
- **Output:** A hybrid animal portrait image (PNG bytes) that blends the user's likeness with the suggested animal archetype reflecting their quirks.

### Prompt instructions for the Converter model

The Converter instructs the model to:

1. See both the user's original portrait and the behavioural profile.
2. Fuse the user's likeness with the suggested animal archetype — e.g., if the user is described as "always drinking coffee and fidgety," the animal could be a "caffeinated badger"; if "meticulous organizer," a "meticulous beaver."
3. Produce a hybrid portrait that is recognizably the user but with animal features that embody their personality quirks.
4. Output the result as a PNG image in base64 format, accompanied by a short caption.

### Delivery

- The generated image bytes are sent back to the user's Telegram chat via the Telegram Bot API `sendPhoto` method.
- No intermediate text hop — the image flows directly from the Converter to Telegram.

### State management

- The Converter reads the photo bytes and interview dossier from the shared `SessionStore`; it does not persist its own state.
- After the Converter completes, the session state is left as-is (no purge, no reset), so the user can start a new run via `/start` or `/restart`.

### Out of scope

- Video or GIF output.
- Persistent session storage (Redis, database, or disk).
- Webhooks, or any public endpoint or tunnel.
- Group chats and admin features.
- Accounts, galleries, or saved history of past results.
- The Scripter or Narrator stages (those are separate pipeline stages).

## Testing strategy

- **Unit (always run):** mocked Gemini/ADK boundary covering both the acceptance path (human photo + profile → hybrid image) and the rejection path (missing photo or missing profile → graceful error). The model boundary is mocked; no network access required.
- **Integration (skipped without `GEMINI_API_KEY`):** live test sending a real photo + real profile to Gemini 3.1 Flash Image and asserting the returned image is valid PNG; auto-skipped when `GEMINI_API_KEY` is absent.
- Red/Green TDD: tests written before feature code.

## Scope verification

- Does the implementation stay true to `SPECS/MISSION.md`? Yes — the Converter fuses photo + dossier into a hybrid animal portrait delivered directly to Telegram, exactly as step 5 describes.
- Does it respect `SPECS/TECH.md`? Yes — uses Gemini 3.1 Flash Image as specified; structured output at boundaries; session state keyed by `chat_id`.
- Does it respect `SPECS/ROADMAP.md`? Yes — this is Phase 4, following the Interviewer (Phase 3) and preceding the Scripter (Phase 5).
- Are there any out-of-scope features creeping in? No — no video, no webhooks, no persistent storage, no galleries.