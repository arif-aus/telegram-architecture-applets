# The Telegram Documentaries

A Telegram bot that turns your portrait into a short, narrated, comedy
wildlife documentary about you. Send a photo, answer a few questions, and
receive back a hybrid animal portrait and a dramatic British-documentary
voice note starring you.

## Pipeline

1. **Bouncer** — vision gate; confirms a human is present, cheekily rejects
   everything else.
2. **Interviewer** — the orchestrator. Asks 5–7 questions one at a time and
   builds a behavioural dossier tied to your `chat_id`.
3. **Converter** — fuses the original photo and the dossier into a hybrid
   animal portrait.
4. **Scripter** — writes one 60–90 word paragraph of British documentary
   narration.
5. **Narrator** — not an agent. Sends the script to Gemini TTS and delivers
   it as a voice note.

Transport is Telegram **long polling** — no webhooks, no public URL.

## Constitution

The project contract lives in `SPECS/` and every later spec and change is
judged against it:

- [`SPECS/MISSION.md`](SPECS/MISSION.md) — what the project does and does not do
- [`SPECS/TECH.md`](SPECS/TECH.md) — stack, architecture, and engineering policies
- [`SPECS/ROADMAP.md`](SPECS/ROADMAP.md) — the ordered build plan

## Configuration

Copy `.env.example` to `.env` and fill it in. `.env` is gitignored and must
never be committed.

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `GEMINI_API_KEY` | Google Gemini API key |

## Development scripts

`scripts/` is the ground truth for tests, lint, and type checks. It lands in
Phase 1 of the roadmap; this section will be updated when it does.

## License

Unlicensed placeholder — add a license before publishing further.
