"""Application assembly: the long-polling gateway wired with handlers and deps.

``build_application`` shares one :class:`SessionStore` and one
:class:`BouncerService` with every handler through ``bot_data`` — the single
source of session truth for all pipeline stages.
"""

from __future__ import annotations

from typing import Any

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from telegram_documentaries.bouncer import BouncerService
from telegram_documentaries.config import Settings
from telegram_documentaries.converter import ConverterService
from telegram_documentaries.handlers import acknowledge_text, handle_photo, restart, start
from telegram_documentaries.interviewer import InterviewerService
from telegram_documentaries.scripter import ScripterService
from telegram_documentaries.state import SessionStore

# The concrete generic parameters of `Application` are configuration plumbing;
# the container itself is the dependency-injection point, so `Any` is fine here.
ApplicationT = Application[Any, Any, Any, Any, Any, Any]


def build_application(settings: Settings) -> ApplicationT:
    """Assemble the `python-telegram-bot` application for long polling."""
    application = Application.builder().token(settings.telegram_bot_token).build()

    application.bot_data["store"] = SessionStore()
    application.bot_data["bouncer"] = BouncerService(api_key=settings.gemini_api_key)
    application.bot_data["interviewer"] = InterviewerService(api_key=settings.gemini_api_key)
    application.bot_data["converter"] = ConverterService(api_key=settings.gemini_api_key)
    application.bot_data["scripter"] = ScripterService(api_key=settings.gemini_api_key)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("restart", restart))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, acknowledge_text))

    return application
