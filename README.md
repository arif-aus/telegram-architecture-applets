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

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and fill it in. `.env` is gitignored and must
never be committed.

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `GEMINI_API_KEY` | Google Gemini API key — shared by the Bouncer, Interviewer, Converter, and Scripter |

The Scripter introduces no new environment variables; it reuses
`GEMINI_API_KEY`.

## Running the bot

```bash
python -m telegram_documentaries
# or, after installing the project:
telegram-documentaries
```

The bot uses Telegram long polling, so no public URL or webhook is needed.

### Current behaviour (through the Scripter)

- `/start` and `/restart` reset the chat's session and greet.
- A photo is checked by the **Bouncer** (Gemini 3.1 Flash Lite): a human
  portrait advances the session to `AWAITING_INTERVIEW`; anything else is
  cheekily rejected and the session is purged; a model failure asks the user to
  retry without losing state.
- The **Interviewer** asks five questions one at a time and writes the finished
  dossier (behavioural profile + suggested animal) into the one shared session
  state keyed by `chat_id`.
- The **Converter** fuses the stored portrait with the suggested animal and
  sends the hybrid image straight to the chat.
- The **Scripter** (Gemini 3.1 Flash Lite) reads the dossier from shared state
  and replies with exactly one plain-text paragraph (max 90 words) of dramatic
  British documentary narration, framing the user's quirks, bedtime habits, and
  snacking as animal behaviour. The text contains no markdown and is ready for
  voice synthesis.
- Ordinary text outside an active interview gets a hardcoded acknowledgement;
  a Scripter failure is logged loudly without losing the image already sent.
- The **Narrator** (Gemini TTS) is the next phase; the Scripter's paragraph is
  its input.

The gateway itself makes no API calls on startup; Gemini calls happen only as
the pipeline runs.

## Development scripts

`scripts/` is the ground truth for tests, lint, and type checks. Run both from
the repository root; they are executable and exit non-zero on failure.

### `scripts/test`

Runs the pytest suite via `python -m pytest tests`. Any arguments are passed
straight through to pytest.

```bash
scripts/test                           # default suite: no network, no API calls
scripts/test -m "not integration"      # unit only, explicitly
RUN_LIVE_GEMINI_TESTS=1 scripts/test -m integration   # opt-in live Gemini tests
```

Live Bouncer and Scripter tests in `tests/integration/` are marked `integration`
and are **opt-in**: they run only when both `GEMINI_API_KEY` is set and
`RUN_LIVE_GEMINI_TESTS=1`. Without the opt-in they are collected but skipped, so
the default suite makes no network or API calls. `tests/conftest.py` loads the
repository `.env` without overriding variables that are already set.

### `scripts/hooks`

The pre-commit gate. It runs, in order:

1. `ruff check .` — lint
2. `ruff format --check .` — formatting
3. `mypy` — strict type checking
4. `scripts/test` — the full test suite

```bash
scripts/hooks
```

It exits non-zero on the first failure, so a green run means lint, formatting,
types, and tests all pass.

## License

Unlicensed placeholder — add a license before publishing further.
