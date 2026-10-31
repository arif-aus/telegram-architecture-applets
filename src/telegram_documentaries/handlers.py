"""Telegram conversation handlers.

Phase 1 gateway: `/start`, `/restart`, and a hardcoded text acknowledgement.
The Bouncer photo gate lives here too (see :func:`handle_photo`).
The Interviewer text handler is active once the phase advances to
`AWAITING_INTERVIEW` (after the Bouncer accepts a human portrait).

Every handler is wrapped in :func:`safe_handler` so nothing ever raises into
the Telegram poll loop: failures are logged loudly and the user gets a
graceful error reply.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar, cast

from telegram import Update
from telegram.ext import ContextTypes

from telegram_documentaries.bouncer import BouncerDecision, BouncerService
from telegram_documentaries.config import load_settings
from telegram_documentaries.converter import ConverterService
from telegram_documentaries.interviewer import InterviewerService
from telegram_documentaries.logs import logged
from telegram_documentaries.reset import ActiveSessionRegistry, EphemeralAssetRegistry, reset_chat
from telegram_documentaries.scripter import ScripterService
from telegram_documentaries.state import Phase, SessionState, SessionStore

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

GREETING = (
    "Welcome to The Telegram Documentaries! I turn a portrait into a narrated "
    "wildlife documentary about you. Send me a photo of your human self and "
    "the Bouncer will show you in."
)
ACKNOWLEDGEMENT = (
    "I can't chat yet - right now I live for photos. Send one and the Bouncer "
    "will decide whether you're documentary material."
)
GRACEFUL_ERROR_TEXT = "Something went wrong on my side. No hard feelings - try /start again."
PHOTO_REJECTION = (
    "I'm sorry, but there's no human in that photo. The Bouncer only admits "
    "certified people - not landscapes, snacks, or ambitious mountain goats. "
    "Send a portrait of your actual human self and try again."
)
PHOTO_CONFIRMATION = (
    "You're in! The Bouncer spotted a human and waved you through. "
    "The Interviewer will be with you shortly."
)
PHOTO_RETRY = (
    "The Bouncer couldn't get a good look at that one. Please send the photo again in a moment."
)


def safe_handler(
    func: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, R | None]]:
    """Guard a handler so it can never raise into the poll loop."""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
        try:
            return await func(*args, **kwargs)
        except Exception:
            logger.exception("event=handler.failure_contained handler=%s", func.__qualname__)
            await _best_effort_error_reply(args[0] if args else None)
            return None

    return wrapper


async def _best_effort_error_reply(update: object | None) -> None:
    message = getattr(update, "effective_message", None) if update is not None else None
    if message is None:
        return
    try:
        await message.reply_text(GRACEFUL_ERROR_TEXT)
    except Exception:
        logger.exception("event=handler.error_reply_failed")


@safe_handler
@logged
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Begin a fresh session: purge any residue, then greet."""
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return
    store = _store(context)
    sessions = _sessions(context)
    assets = _assets(context)
    _ = await reset_chat(chat.id, store=store, sessions=sessions, assets=assets)
    await message.reply_text(GREETING)


@safe_handler
@logged
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Same reset-and-greet semantics as `/start`, bound to its own command."""
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return
    store = _store(context)
    sessions = _sessions(context)
    assets = _assets(context)
    _ = await reset_chat(chat.id, store=store, sessions=sessions, assets=assets)
    await message.reply_text(GREETING)


@safe_handler
@logged
async def acknowledge_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ordinary text messages.

    If the chat is in ``AWAITING_INTERVIEW`` phase and the interview is not
    complete (``question_index < 5``), the Interviewer agent is invoked to
    either ask the next question or synthesize the final profile + animal.

    Otherwise the Phase 1 hardcoded acknowledgement is sent.
    """
    message = update.effective_message
    if message is None:
        return

    chat = update.effective_chat
    if chat is None:
        return

    store = _store(context)
    state = store.get(chat.id)

    # If the interview is active, delegate to the Interviewer agent.
    if state is not None and state.phase is Phase.AWAITING_INTERVIEW and state.question_index < 5:
        try:
            settings = load_settings()
            interviewer = InterviewerService(api_key=settings.gemini_api_key)
            # The very first text after the photo triggers the kick-off turn;
            # only later messages are answers to an outstanding question.
            first_turn = state.question_index == 0 and not state.responses
            user_text = "start" if first_turn else (message.text or "")
            output = await interviewer.run(
                user_text=user_text,
                chat_id=chat.id,
                store=store,
            )

            if output.next_question is not None:
                await message.reply_text(output.next_question)
                return

            if output.profile is not None and output.suggested_animal is not None:
                # Persist the completed dossier in the one shared store so later
                # stages can read it without private state.
                stored_state = store.get(chat.id)
                if stored_state is not None:
                    stored_state.profile = output.profile
                    stored_state.suggested_animal = output.suggested_animal
                    store.set(stored_state)

                await message.reply_text(
                    f"{output.profile}\n\n"
                    f"Suggested animal for your documentary: {output.suggested_animal}"
                )

                # Invoke the Converter to fuse the photo with the animal archetype.
                try:
                    settings = load_settings()
                    converter = ConverterService(api_key=settings.gemini_api_key)

                    # Retrieve the stored portrait bytes from the session.
                    stored_state = store.get(chat.id)
                    image_bytes = stored_state.image_bytes if stored_state else None

                    if image_bytes is None:
                        logger.warning("event=converter_no_photo chat_id=%s", chat.id)
                    else:
                        converter_output = await converter.convert(
                            image_bytes=image_bytes,
                            profile=output.profile,
                            suggested_animal=output.suggested_animal,
                        )

                        # The model returns base64 text; Telegram needs PNG bytes.
                        await message.reply_photo(
                            photo=converter_output.image_bytes,
                            caption=converter_output.caption,
                        )

                        # Invoke the Scripter to generate the documentary narrative.
                        try:
                            settings = load_settings()
                            scripter = ScripterService(api_key=settings.gemini_api_key)

                            scripter_output = await scripter.generate(
                                chat_id=chat.id,
                                store=store,
                                profile=output.profile,
                                suggested_animal=output.suggested_animal,
                            )

                            await message.reply_text(scripter_output.script)
                        except Exception:
                            logger.exception("event=scripter_failure chat_id=%s", chat.id)

                except Exception:
                    logger.exception("event=converter_failure chat_id=%s", chat.id)

                return
        except Exception:
            logger.exception("event=interviewer_failure chat_id=%s", chat.id)
            await message.reply_text(GRACEFUL_ERROR_TEXT)
            return

    # Fallback: Phase 1 acknowledgement (or after interview complete).
    await message.reply_text(ACKNOWLEDGEMENT)


@safe_handler
@logged
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run the Bouncer over the largest uploaded photo and route its verdict."""
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    photos = message.photo
    if not photos:
        return

    # Telegram sends the same photo at several resolutions; judge the biggest.
    largest = max(photos, key=lambda photo: photo.width * photo.height)
    telegram_file = await largest.get_file()
    image_bytes = bytes(await telegram_file.download_as_bytearray())

    decision = await _bouncer(context).decide(image_bytes, mime_type="image/jpeg")

    if decision is BouncerDecision.REJECT:
        _store(context).reset(chat.id)
        _assets(context).purge(chat.id)
        _ = await _sessions(context).cancel(chat.id)
        await message.reply_text(PHOTO_REJECTION)
    elif decision is BouncerDecision.ACCEPT:
        _store(context).set(
            SessionState(
                chat_id=chat.id,
                phase=Phase.AWAITING_INTERVIEW,
                image_bytes=image_bytes,
            )
        )
        await message.reply_text(PHOTO_CONFIRMATION)
    else:
        # ERROR: state stays exactly as it was so the user can retry the same step.
        logger.error("event=bouncer.photo_classification_failed chat_id=%s", chat.id)
        await message.reply_text(PHOTO_RETRY)


def _store(context: ContextTypes.DEFAULT_TYPE) -> SessionStore:
    return cast(SessionStore, context.bot_data["store"])


def _bouncer(context: ContextTypes.DEFAULT_TYPE) -> BouncerService:
    return cast(BouncerService, context.bot_data["bouncer"])


def _sessions(context: ContextTypes.DEFAULT_TYPE) -> ActiveSessionRegistry:
    return cast(ActiveSessionRegistry, context.bot_data["sessions"])


def _assets(context: ContextTypes.DEFAULT_TYPE) -> EphemeralAssetRegistry:
    return cast(EphemeralAssetRegistry, context.bot_data["assets"])
