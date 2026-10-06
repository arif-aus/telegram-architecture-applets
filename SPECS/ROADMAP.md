# ROADMAP — The Telegram Documentaries

One phase per pipeline capability, in build order. A phase is marked complete
only when its acceptance criteria are verified.

## 1. Repository and gateway

Project skeleton, `.env` loading, and a long-polling loop that replies with a
hardcoded message.

- **Acceptance:** the bot answers in Telegram from a clean checkout with only
  `.env` supplied.
- **Rubric:** runnable entry point.

## 2. Bouncer

Vision gate on the uploaded portrait, with cheeky rejection and state reset
for non-human images.

- **Acceptance:** a human portrait advances to the Interviewer; anything else
  is rejected and leaves no session residue.
- **Rubric:** vision gate and rejection routing.

## 3. Interviewer

Sequential stateful Q&A — 5–7 questions, one at a time — ending in a dossier
summary and a suggested animal. Doubles as the orchestrator.

- **Acceptance:** a completed interview yields a dossier and an animal; state
  survives between questions; wrong-payload input is handled gracefully.
- **Rubric:** stateful multi-turn orchestration.

## 4. Converter

Native multimodal fusion of the original photo and the dossier into a hybrid
animal portrait, sent straight to Telegram with no intermediate text hop.

- **Acceptance:** the image reaches the chat, and no raw payload crosses the
  module boundary.
- **Rubric:** multimodal image generation.

## 5. Scripter

One paragraph of 60–90 words of dramatic British documentary narration built
from the dossier.

- **Acceptance:** word count and tone hold across multiple runs.
- **Rubric:** structured generation.

## 6. Narrator

TTS synthesis of the script, rendered to a Telegram-compatible audio format
(OGG or MP3) and delivered to the chat.

- **Acceptance:** a voice note plays in Telegram from the Scripter's output.
- **Rubric:** text-to-speech delivery.

## 7. Resilience

`/start` and `/restart` purge state and temporary files, wrong-payload-at-the-
wrong-stage guards, and API-timeout fallbacks.

- **Acceptance:** reset leaves no state or temp files behind; timeouts degrade
  gracefully on the conversation path; nothing raises into the user's chat.
- **Rubric:** reset semantics and error handling.
