"""The Interviewer: a stateful ADK LlmAgent that conducts a 5-question interview,
tracks responses by chat_id, and synthesizes a behavioral/personality profile
with a suggested animal for the next pipeline stage.

Model: Gemini 3.1 Flash Lite.
State is stored in the shared SessionStore keyed by chat_id (not in ADK sessions).
The agent is invoked per-user-response through an InMemoryRunner with a fresh
disposable session each time, mirroring the BouncerService pattern.
"""

from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import Client, types
from pydantic import BaseModel, Field, ValidationError

from telegram_documentaries.logs import logged
from telegram_documentaries.state import Phase, SessionState, SessionStore

logger = logging.getLogger(__name__)

#: The vision/model for the Interviewer (per SPECS/TECH.md).
MODEL = "gemini-3.1-flash-lite"

#: ADK application name shared by the runner and its session service.
APP_NAME = "telegram_documentaries"


#: The output contract for the Interviewer agent.
class InterviewOutput(BaseModel):
    """Structured output from the Interviewer agent."""

    next_question: str | None = Field(
        default=None,
        description="Next question for the user, or None if complete (5 answers received).",
    )
    profile: str | None = Field(
        default=None,
        description="Behavioural profile when complete (~50 words).",
    )
    suggested_animal: str | None = Field(
        default=None,
        description="Suggested animal for next stage when complete.",
    )


# ---------------------------------------------------------------------------
# Agent instruction — guides the model to ask playful/eccentric questions and
# synthesize a profile after the 5th answer.
# ---------------------------------------------------------------------------

INTERVIEWER_INSTRUCTION = """\
You are The Interviewer for The Telegram Documentaries. Your role is to ask 5
investigative, playful, slightly eccentric questions, one at a time, and
accumulate the user's responses into a behavioural dossier. You are the
orchestrator of the pipeline — the Bouncer has already confirmed the user is
human and advanced the session to AWAITING_INTERVIEW.

Each turn you will receive the user's previous response (or "start" if this is
the first turn) and the current state: question_index (0=not started, 1-5=answers
received, 5=complete) and the accumulated responses list.

Your output must follow the InterviewOutput schema:

- next_question: The next question to ask the user, or None if the interview
    is complete (all 5 answers have been received).
- profile: A concise behavioural/personality profile (~50 words), only set when
    the interview is complete. Cover relevant quirks and habits from the 5
    responses.
- suggested_animal: A suggested animal for the next pipeline stage (Converter),
    only set when the interview is complete. Should be a single animal name that
    reflects the user's personality quirks (e.g. "red panda", "octopus", "peacock").

Rules:
- Ask exactly one question per turn — no chatter, no multiple questions.
- If question_index < 5: produce the next investigative, playful, slightly
    eccentric question in next_question. The question should feel personal and
    revealing, not a generic survey.
- If question_index == 5: synthesise a concise behavioural/personality profile
    (max ~50 words) covering relevant quirks and habits from the 5 responses,
    and suggest a single animal for the next pipeline stage in
    suggested_animal. The profile and animal should feel connected — the animal
    is an emblem for the user's on-camera persona.
- Never return raw text without the structured output schema.
- Never set next_question and profile/suggested_animal simultaneously.
- The transition from question-asking to profile-synthesis should feel natural:
    after the 5th answer, the agent pivots to summarising and suggesting.
"""

# ---------------------------------------------------------------------------
# Helper: build the Content the agent receives each turn.
# ---------------------------------------------------------------------------


def _build_content(user_text: str, state: SessionState) -> types.Content:
    """Build a Content object the interviewer agent can read.

    The model sees the user's raw message and the current interview state
    (question_index + accumulated responses) so it can decide which question
    to ask next or when to synthesise the profile.
    """
    parts: list[types.Part] = [types.Part.from_text(text=user_text)]

    # Append state so the model always knows where we are.
    state_marker = (
        f"\n--- Current state ---\n"
        f"question_index: {state.question_index}\n"
        f"responses: {state.responses}"
    )
    parts.append(types.Part.from_text(text=state_marker))

    return types.Content(role="user", parts=parts)


# ---------------------------------------------------------------------------
# InterviewerService — wraps the ADK LlmAgent + InMemoryRunner.
# ---------------------------------------------------------------------------


class InterviewerService:
    """Stateful interview conductor, one shared instance per application."""

    def __init__(self, api_key: str, model: str = MODEL) -> None:
        client = Client(api_key=api_key)
        self._model = Gemini(model=model, client=client)

        self._agent = LlmAgent(
            name="interviewer",
            model=self._model,
            description="Conducts a 5-question investigative interview and produces"
            " a behavioural profile with a suggested animal",
            instruction=INTERVIEWER_INSTRUCTION,
            output_schema=InterviewOutput,
        )
        self._runner = InMemoryRunner(agent=self._agent, app_name=APP_NAME)

    # -------------------------------------------------------------------
    # Public API — one entry point per user response.
    # -------------------------------------------------------------------

    @logged
    async def run(self, user_text: str, chat_id: int, store: SessionStore) -> InterviewOutput:
        """Process one user response and return the interviewer's output.

        Args:
            user_text: The text the user sent (their answer, or "start").
            chat_id: The Telegram chat identifier — used to look up / update
                session state in the shared store.
            store: The shared SessionStore (keyed by chat_id) holding the
                interview state.

        Returns:
            InterviewOutput — the agent's response (next question, profile,
            or suggested animal).
        """
        # Read the current state for this chat.
        state = store.get(chat_id)
        if state is None:
            # No session exists — this can happen if the user messages before
            # the bouncer has advanced the phase. Guard gracefully.
            logger.warning("event=interviewer.no_session chat_id=%s", chat_id)
            state = SessionState(chat_id=chat_id, phase=Phase.AWAITING_INTERVIEW)

        # Build the content the agent will read — user text + current state.
        content = _build_content(user_text, state)

        # One fresh, disposable session per classification so history never
        # accumulates in the in-memory session service.
        user_id = f"interviewer_{chat_id}"
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
                raise RuntimeError("ADK runner produced no final response for interviewer")

            # Parse the structured output.
            parts = final_output.parts or []
            raw_text = "\n".join(part.text for part in parts if part.text)
            try:
                result = InterviewOutput.model_validate_json(raw_text)
            except ValidationError as exc:
                raise RuntimeError(f"unparsable interviewer output: {exc}") from exc

            # Persist the updated state back to the shared store.
            # The handler has already incremented question_index and appended
            # the user's response, so we just write the state back so the next
            # turn reads the correct values.
            state.question_index = getattr(result, "question_index", state.question_index)
            state.responses = getattr(result, "responses", state.responses)
            # Persist the completed dossier so later stages (Converter, Scripter)
            # can read it from the one shared store rather than private state.
            if result.profile is not None:
                state.profile = result.profile
            if result.suggested_animal is not None:
                state.suggested_animal = result.suggested_animal
            store.set(state)

            return result

        finally:
            await self._runner.session_service.delete_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
