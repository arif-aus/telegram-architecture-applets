# MISSION — The Telegram Documentaries

## Vision

A Telegram bot that turns a stranger's portrait into a short, narrated,
comedy wildlife documentary about them. The user sends a photo, answers a
few questions about themselves, and gets back a hybrid animal portrait plus a
dramatic British-documentary voice note starring them.

## End-to-end experience

1. `/start` — the bot greets the user and begins a fresh session.
2. The user sends a portrait photo.
3. **The Bouncer** confirms a human is present. Non-human images are
   cheekily rejected and the session resets.
4. **The Interviewer** asks 5–7 questions, one at a time, accumulating a
   behavioural dossier keyed to `chat_id`, and outputs a suggested animal.
5. **The Converter** fuses the original photo and the dossier into a hybrid
   animal portrait and returns it directly to the chat.
6. **The Scripter** writes one paragraph (60–90 words) of dramatic British
   documentary narration built from the dossier.
7. **The Narrator** — not an agent — renders that paragraph with Gemini TTS
   and sends it to the chat as a Telegram-compatible audio note.
8. The run ends. The user begins again only via `/start` or `/restart`.

## In scope

The pipeline above, exactly: five stages, Telegram long polling, in-memory
session state keyed by `chat_id`, secrets loaded from `.env`.

## Out of scope

Hard exclusions. No phase, spec, or implementation may add these:

- Video or GIF output.
- Webhooks, or any public endpoint or tunnel.
- Persistent session storage (Redis, database, or disk).
- Group chats and admin features.
- Accounts, galleries, or saved history of past results.

## Success criteria

- **Happy path:** one portrait produces a hybrid image, a narration, and a
  voice note, end to end, with no manual intervention.
- **Reset:** `/start` and `/restart` run one explicit reset routine that cancels
  that user's active session, purges their temporary media, clears their agent
  memory, and returns them to the greeting stage — without restarting the
  process.
- **Out-of-order input:** text sent when media is expected, or media sent
  when text is expected, is handled gracefully and the conversation
  continues.

## Non-negotiables

- One user's session state is never visible to, or mixed with, another's.
- Secrets are never hardcoded, never committed, never logged.
