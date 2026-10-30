"""The Bouncer: the multimodal vision gate at the front of the pipeline.

A single ADK :class:`LlmAgent` (Gemini 3.1 Flash Lite) classifies whether the
uploaded image contains a discernible human face or body. It answers through
the typed :class:`BouncerVerdict` contract and is driven through an ADK
:class:`InMemoryRunner` — never a raw Gemini client call. Every model response
is treated as untrusted and validated at this boundary.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import Client, types
from pydantic import BaseModel, ValidationError

from telegram_documentaries.logs import logged

logger = logging.getLogger(__name__)

#: The vision model for the Bouncer (per SPECS/TECH.md).
MODEL = "gemini-3.1-flash-lite"

#: ADK application name shared by the runner and its session service.
APP_NAME = "telegram_documentaries"

CLASSIFICATION_QUESTION = (
    "Is a discernible human face or body present in this image? "
    "Answer only through the structured verdict."
)

BOUNCER_INSTRUCTION = (
    "You are The Bouncer, the famously picky doorman of The Telegram "
    "Documentaries. Look very carefully at the attached image and answer one "
    "question: does it contain a discernible human face or body? Paintings, "
    "statues, mannequins, mannequin heads, robots, animals, landscapes, food "
    "and crop-top mountain goats all count as NO. A real, recognisable human "
    "being counts as YES. Fill in the structured verdict: human_present is "
    "the door policy, rationale is a short note for the doorman's ledger."
)


class BouncerVerdict(BaseModel):
    """Typed answer from the vision model — the contract across the boundary."""

    human_present: bool
    rationale: str


class BouncerDecision(StrEnum):
    """What the conversation should do with the verdict."""

    ACCEPT = "accept"
    REJECT = "reject"
    ERROR = "error"


class BouncerError(RuntimeError):
    """The model call or its output failed validation — never user-visible."""


class BouncerService:
    """Wraps the ADK agent and runner behind one typed, testable service."""

    def __init__(self, api_key: str, model: str = MODEL) -> None:
        # Pass the secret explicitly to a client owned by this service rather
        # than mutating the process environment. The key is never logged.
        client = Client(api_key=api_key)
        self._model = Gemini(model=model, client=client)

        self._agent = LlmAgent(
            name="bouncer",
            model=self._model,
            description="Vision gate: rejects submissions without a human.",
            instruction=BOUNCER_INSTRUCTION,
            output_schema=BouncerVerdict,
        )
        self._runner = InMemoryRunner(agent=self._agent, app_name=APP_NAME)

    @logged
    async def judge(self, image_bytes: bytes, *, mime_type: str = "image/jpeg") -> BouncerVerdict:
        """Classify one image and return a validated verdict."""
        content = self._build_content(image_bytes, mime_type)
        final_content = await self._run_agent(content)

        payload = _content_text(final_content)
        try:
            return BouncerVerdict.model_validate_json(payload)
        except ValidationError as exc:
            raise BouncerError(f"unparsable bouncer output: {exc}") from exc

    @logged
    async def decide(self, image_bytes: bytes, *, mime_type: str = "image/jpeg") -> BouncerDecision:
        """Map a verdict to a decision; every failure degrades to ``ERROR``.

        The underlying exception is logged loudly here and never propagated —
        the photo handler relies on a three-way decision (accept/reject/error)
        and on never seeing the classifier raise into the conversation.
        """
        try:
            verdict = await self.judge(image_bytes, mime_type=mime_type)
        except Exception:
            logger.exception("event=bouncer.classification_failed mime_type=%s", mime_type)
            return BouncerDecision.ERROR
        return BouncerDecision.ACCEPT if verdict.human_present else BouncerDecision.REJECT

    def _build_content(self, image_bytes: bytes, mime_type: str) -> types.Content:
        return types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                types.Part.from_text(text=CLASSIFICATION_QUESTION),
            ],
        )

    async def _run_agent(self, content: types.Content) -> types.Content | None:
        # One fresh, disposable session per classification so image history
        # never accumulates in the in-memory session service.
        user_id = "bouncer"
        session = await self._runner.session_service.create_session(
            app_name=APP_NAME, user_id=user_id
        )
        session_id = session.id
        try:
            final_content: types.Content | None = None
            async for event in self._runner.run_async(
                user_id=user_id, session_id=session_id, new_message=content
            ):
                if event.is_final_response():
                    final_content = event.content
            if final_content is None:
                raise BouncerError("ADK runner produced no final response")
            return final_content
        finally:
            await self._runner.session_service.delete_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )


def _content_text(content: types.Content | None) -> str:
    if content is None or content.parts is None:
        return ""
    return "\n".join(part.text for part in content.parts if part.text)
