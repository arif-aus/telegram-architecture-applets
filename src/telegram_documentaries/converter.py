"""The Converter: the image-specialist component at the heart of the pipeline.

The Converter fuses the user's original portrait photo with the Interviewer's
behavioural profile and suggested animal archetype into a hybrid animal portrait,
delivered directly as an image to the user's Telegram chat.

Model: Gemini 3.1 Flash Image (multimodal).
"""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

#: The image-generation model for the Converter (per SPECS/TECH.md).
MODEL = "gemini-3.1-flash-image"

#: ADK application name shared by the runner and its session service.
APP_NAME = "telegram_documentaries"


# ---------------------------------------------------------------------------
# Output contract for the Converter agent.
# ---------------------------------------------------------------------------


class ConverterOutput(BaseModel):
    """Typed answer from the Converter agent — the contract across the boundary."""

    image_data: bytes = Field(
        description="Base64-encoded PNG data of the hybrid animal portrait.",
    )
    caption: str = Field(
        description="Short caption describing the result, e.g. 'Behold the caffeinated badger'.",
    )


# ---------------------------------------------------------------------------
# Agent instruction — guides the model to fuse likeness with animal archetype.
# ---------------------------------------------------------------------------

CONVERTER_INSTRUCTION = """\
You are The Converter, the image-specialist of The Telegram Documentaries.
Your role is to take the user's original portrait photo and the behavioural
profile + suggested animal from the Interviewer, and fuse them into a single
hybrid animal portrait.

Instructions:

1. Examine the user's portrait photo (the original likeness) and the behavioural
   profile and suggested animal from the Interviewer stage.

2. Determine an animal archetype that reflects the user's quirks from their
   responses. Some examples:
   - If the user is always drinking coffee and fidgety → "caffeinated badger"
   - If the user is a meticulous organizer → "meticulous beaver"
   - If the user is nocturnal and imaginative → "owl with a poet's soul"
   - If the user is social and outgoing → "peacock"
   Use your creativity to match the animal to the user's specific quirks.

3. Fuse the user's likeness with the chosen animal archetype. The result should
   be recognizably the user's face/appearance, but with animal features (ears,
   fur, markings, etc.) that embody their personality. The fusion should be
   artistic and playful, not a literal overlay.

4. Output a PNG image of the hybrid portrait, encoded as base64, accompanied by a
   short, dramatic caption (max ~15 words) that introduces the animal archetype.
   The caption format: "Behold the <animal_archetype>" or similar.

Your output must follow the ConverterOutput schema:

- image_data: Base64-encoded PNG data of the hybrid animal portrait.
- caption: A short dramatic caption introducing the animal archetype.

Rules:
- Always produce both image_data and caption — never return one without the other.
- The image should be a genuine hybrid — the user's likeness merged with the
  animal, not just a caption-less image.
- The caption should be vivid and theatrical, fitting a documentary tone.
- Never return raw text without the structured output schema.
"""


# ---------------------------------------------------------------------------
# Helper: build the Content the agent receives each turn.
# ---------------------------------------------------------------------------


def _build_content(
    image_bytes: bytes,
    mime_type: str,
    profile: str | None,
    suggested_animal: str | None,
) -> types.Content:
    """Build a Content object the converter agent can read.

    The model sees the user's original portrait photo, the behavioural profile,
    and the suggested animal so it can fuse the likeness with the animal
    archetype.
    """
    parts: list[types.Part] = []

    # Add the original portrait photo.
    parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

    # Add the behavioural profile and suggested animal if available.
    text_parts: list[str] = []
    if profile:
        text_parts.append(f"Behavioural profile: {profile}")
    if suggested_animal:
        text_parts.append(f"Suggested animal: {suggested_animal}")

    if text_parts:
        parts.append(types.Part.from_text(text="\n".join(text_parts)))

    return types.Content(role="user", parts=parts)


# ---------------------------------------------------------------------------
# ConverterService — wraps the ADK LlmAgent + InMemoryRunner.
# ---------------------------------------------------------------------------


class ConverterService:
    """State-less converter: takes photo bytes + dossier, returns hybrid portrait."""

    def __init__(self, api_key: str, model: str = MODEL) -> None:
        from google.genai import Client

        self._client = Client(api_key=api_key)
        self._model = Gemini(model=model, client=self._client)

        self._agent = LlmAgent(
            name="converter",
            model=self._model,
            description="Fuses the user's portrait with an animal archetype "
            "to produce a hybrid animal portrait",
            instruction=CONVERTER_INSTRUCTION,
            output_schema=ConverterOutput,
        )
        self._runner = InMemoryRunner(agent=self._agent, app_name=APP_NAME)

    # -------------------------------------------------------------------
    # Public API — convert one user's photo + dossier into a hybrid portrait.
    # -------------------------------------------------------------------

    async def convert(
        self,
        image_bytes: bytes,
        *,
        mime_type: str = "image/jpeg",
        profile: str | None = None,
        suggested_animal: str | None = None,
    ) -> ConverterOutput:
        """Fuse the user's likeness with an animal archetype and return the result.

        Args:
            image_bytes: The user's original portrait photo bytes.
            mime_type: MIME type of the image (default "image/jpeg").
            profile: The Interviewer's behavioural profile, or None.
            suggested_animal: The Interviewer's suggested animal, or None.

        Returns:
            ConverterOutput — the hybrid portrait image (base64-encoded PNG) and
            a short caption.
        """
        # Build the content the agent will read.
        content = _build_content(image_bytes, mime_type, profile, suggested_animal)

        # One fresh, disposable session per conversion so image history
        # never accumulates in the in-memory session service.
        user_id = "converter"
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
                raise RuntimeError("ADK runner produced no final response for converter")

            # Parse the structured output.
            parts = final_output.parts or []
            raw_text = "\n".join(part.text for part in parts if part.text)
            try:
                result = ConverterOutput.model_validate_json(raw_text)
            except ValidationError as exc:
                raise RuntimeError(f"unparsable converter output: {exc}") from exc

            return result

        finally:
            await self._runner.session_service.delete_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
