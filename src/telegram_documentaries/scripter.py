"""The Scripter: a text-only ADK LlmAgent that turns the interview dossier
into a short nature documentary narrative.

Model: Gemini 3.1 Flash Lite.
Input: The interview dossier from the shared session state — the behavioural
profile and the Interviewer's suggested animal.
System Instruction: Adopt the persona of a revered, dramatic British wildlife
documentary narrator. Frame the subject's quirks, bedtime habits, and snacking
patterns as funny animal behaviours, intentionally making it sound like a
nature documentary about humans.
Output: Exactly one paragraph (max 90 words), no markdown formatting, ready
for voice synthesis.
Output Action: Send the text script directly to the user's Telegram chat.
"""

from __future__ import annotations

import logging
import re

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import Client, types
from pydantic import BaseModel, Field, ValidationError

from telegram_documentaries.logs import logged
from telegram_documentaries.state import SessionStore

logger = logging.getLogger(__name__)

#: The model for the Scripter (per SPECS/TECH.md).
MODEL = "gemini-3.1-flash-lite"

#: ADK application name shared by the runner and its session service.
APP_NAME = "telegram_documentaries"

#: Hard ceiling for the narration, per the feature requirements.
MAX_WORDS = 90


# ---------------------------------------------------------------------------
# Output contract for the Scripter agent.
# ---------------------------------------------------------------------------


class ScripterOutput(BaseModel):
    """Structured output from the Scripter agent.

    ``profile`` and ``suggested_animal`` echo the dossier the paragraph was
    built from, so the handler never has to re-read state to know what the
    script is about.
    """

    profile: str | None = Field(
        default=None,
        description="The behavioural profile the narration was built from.",
    )
    suggested_animal: str | None = Field(
        default=None,
        description="The Interviewer's suggested animal for the subject.",
    )
    script: str = Field(
        description="One paragraph (max 90 words) of British documentary narration, "
        "framing the subject's quirks as funny animal behaviours.",
    )
    continue_interview: bool = Field(
        default=False,
        description="Always false: the Scripter ends the conversation flow.",
    )


# ---------------------------------------------------------------------------
# Agent instruction — guides the model to produce the documentary narrative.
# ---------------------------------------------------------------------------

SCRIPTER_INSTRUCTION = """\
You are The Scripter for The Telegram Documentaries. Your role is to take the
user's behavioural profile and suggested animal from the Interviewer stage, and
write exactly one paragraph (maximum 90 words) of dramatic British wildlife
documentary narration.

Instructions:

1. Frame the subject's quirks, bedtime habits, and snacking patterns as funny
   animal behaviours — intentionally making it sound like a nature documentary
   about humans. Be playful and affectionate, not mean-spirited.

2. Use the tone of a revered, dramatic British wildlife documentary narrator.
   Think Sir David Attenborough describing human quirks in the wild.

3. Output must be exactly ONE paragraph — no line breaks, no markdown formatting.
   Aim for 60-90 words. The paragraph must never exceed 90 words (countable as
   continuous text between spaces). It must be ready for immediate voice
   synthesis.

4. The paragraph must reference the suggested animal from the Interviewer
   stage as an emblem for the user's on-camera persona.

5. Structured output only — output must follow the ScripterOutput schema with
   the ``script`` field. Never return raw text without the schema.

Example output (90 words or fewer):
 "In the quiet hour before dawn, our subject performs the mysterious ritual
 of the nocturnal snack-seeker, padding softly to the kitchen in search of
 midnight morsels — a behaviour reminiscent of the red panda's furtive
 foraging under moonlit canopies. Indeed, even in domesticity, the red
 panda's spirit endures."
"""


# ---------------------------------------------------------------------------
# Helpers: build the dossier content and validate the model's script.
# ---------------------------------------------------------------------------


def _build_content(profile: str, suggested_animal: str) -> types.Content:
    """Build the dossier content the Scripter agent reads for one run."""
    text = (
        "Here is the interview dossier for the narration.\n\n"
        f"Behavioural profile: {profile}\n"
        f"Suggested animal: {suggested_animal}\n\n"
        "Write the documentary paragraph now."
    )
    return types.Content(role="user", parts=[types.Part.from_text(text=text)])


def _validate_script(script: str) -> str:
    """Normalise the script into one plain-text paragraph of at most 90 words.

    The model boundary is untrusted: strip markdown and surrounding quotes,
    collapse all whitespace (so newlines cannot leak into the TTS input), and
    enforce the word ceiling. An empty script is a loud failure, never a silent
    empty voice note.
    """
    script = script.strip()
    script = re.sub(r"[*_`]+", "", script)
    script = re.sub(r"^#+\s*", "", script)
    script = script.strip().strip("\"'")
    script = re.sub(r"\s+", " ", script).strip()

    if not script:
        raise ValueError("scripter returned an empty script")

    words = script.split()
    if len(words) > MAX_WORDS:
        script = " ".join(words[:MAX_WORDS])
        if script and script[-1] not in ".!?":
            script = script.rstrip(",;:") + "."

    return script


# ---------------------------------------------------------------------------
# ScripterService — wraps the ADK LlmAgent + InMemoryRunner.
# ---------------------------------------------------------------------------


class ScripterService:
    """Stateless script generator: takes a dossier, returns documentary narration."""

    def __init__(self, api_key: str, model: str = MODEL) -> None:
        client = Client(api_key=api_key)
        self._model = Gemini(model=model, client=client)

        self._agent = LlmAgent(
            name="scripter",
            model=self._model,
            description="Transforms the interview dossier into a British "
            "documentary narrative paragraph",
            instruction=SCRIPTER_INSTRUCTION,
            output_schema=ScripterOutput,
        )
        self._runner = InMemoryRunner(agent=self._agent, app_name=APP_NAME)

    # -------------------------------------------------------------------
    # Public API — generate script from the dossier stored per chat.
    # -------------------------------------------------------------------

    @logged
    async def generate(
        self,
        chat_id: int,
        store: SessionStore,
        *,
        profile: str | None = None,
        suggested_animal: str | None = None,
    ) -> ScripterOutput:
        """Generate the documentary narration from the chat's dossier.

        Args:
            chat_id: The Telegram chat identifier — used to look up session
                state in the shared store and to scope the ADK session.
            store: The shared SessionStore (keyed by chat_id) holding the
                interview dossier.
            profile: An explicit behavioural profile; when omitted it is read
                from shared state.
            suggested_animal: An explicit suggested animal; when omitted it is
                read from shared state.

        Returns:
            ScripterOutput with the script, the echoed dossier, and
            ``continue_interview=False``.

        Raises:
            ValueError: when the dossier is missing from both arguments and
                shared state.
            RuntimeError: when the model boundary returns no parseable output.
        """
        state = store.get(chat_id)
        if profile is None and state is not None:
            profile = state.profile
        if suggested_animal is None and state is not None:
            suggested_animal = state.suggested_animal

        if not profile or not suggested_animal:
            missing = [
                name
                for name, value in (
                    ("profile", profile),
                    ("suggested_animal", suggested_animal),
                )
                if not value
            ]
            logger.error(
                "event=scripter.missing_dossier chat_id=%s missing=%s",
                chat_id,
                ",".join(missing),
            )
            raise ValueError(
                f"scripter requires profile and suggested_animal (missing {', '.join(missing)})"
            )

        content = _build_content(profile, suggested_animal)

        # One fresh, disposable session per script generation so history
        # never accumulates in the in-memory session service.
        user_id = f"scripter_{chat_id}"
        session = await self._runner.session_service.create_session(
            app_name=APP_NAME, user_id=user_id
        )
        session_id = session.id

        try:
            final_output: types.Content | None = None
            async for event in self._runner.run_async(
                user_id=user_id, session_id=session_id, new_message=content
            ):
                if event.is_final_response():
                    final_output = event.content
            if final_output is None:
                raise RuntimeError("ADK runner produced no final response for scripter")

            # Parse the structured output at the model boundary. Some models
            # still wrap JSON in a markdown fence despite the schema; strip it
            # rather than dropping an otherwise valid script.
            output_parts = final_output.parts or []
            raw_text = "\n".join(part.text for part in output_parts if part.text).strip()
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)
            try:
                result = ScripterOutput.model_validate_json(raw_text)
            except ValidationError as exc:
                raise RuntimeError(f"unparsable scripter output: {exc}") from exc

            script = _validate_script(result.script)
            return ScripterOutput(
                profile=profile,
                suggested_animal=suggested_animal,
                script=script,
                continue_interview=False,
            )

        finally:
            await self._runner.session_service.delete_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
