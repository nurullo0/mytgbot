"""
Middlewares:
  - ThrottlingMiddleware: simple per-user rate limiting.
  - ForceSubscriptionMiddleware: blocks usage until the user has joined
    all required channels.
  - ErrorHandlingMiddleware: catches unhandled exceptions so the bot never
    crashes the whole polling loop because of a single bad update.
"""

import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, Update
from aiogram.exceptions import TelegramAPIError

from config import config
from database import db
from utils.throttling import throttle_cache

logger = logging.getLogger(__name__)

# Caches successful membership checks for a short while so we don't hammer
# the Telegram API with getChatMember calls on every single message.
_membership_cache: Dict[int, float] = {}


class ThrottlingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            if throttle_cache.is_throttled(user.id, config.rate_limit_seconds):
                # Silently drop excessive requests - prevents flooding/spam.
                return
        return await handler(event, data)


class ForceSubscriptionMiddleware(BaseMiddleware):
    """Checks channel membership before letting the update reach handlers.
    Admins and the /start command's initial entry are always allowed through
    so the user can see the "join channel" prompt itself."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not config.force_sub_channels:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        # Admins bypass force-subscription entirely.
        if user.id in config.admin_ids or await db.is_admin_in_db(user.id):
            return await handler(event, data)

        # Always allow the membership-check callback itself through.
        if isinstance(event, Update) and event.callback_query and event.callback_query.data == "check_sub":
            return await handler(event, data)

        cached_at = _membership_cache.get(user.id)
        if cached_at and (time.time() - cached_at) < config.membership_cache_seconds:
            return await handler(event, data)

        bot = data["bot"]
        not_joined = []
        for channel in config.force_sub_channels:
            try:
                member = await bot.get_chat_member(chat_id=channel, user_id=user.id)
                if member.status in ("left", "kicked"):
                    not_joined.append(channel)
            except TelegramAPIError as exc:
                logger.warning("Could not check membership for %s in %s: %s", user.id, channel, exc)
                not_joined.append(channel)

        if not_joined:
            from keyboards.inline import force_sub_keyboard

            text = (
                "🔒 <b>Access restricted</b>\n\n"
                "Please join the channel(s) below to use this bot, "
                "then tap <b>I've Joined ✅</b>."
            )

            if isinstance(event, Update) and event.message:
                await event.message.answer(text, reply_markup=force_sub_keyboard(not_joined))
            elif isinstance(event, Update) and event.callback_query:
                await event.callback_query.answer("Please join the required channel(s) first.", show_alert=True)
            return  # block handler

        _membership_cache[user.id] = time.time()
        return await handler(event, data)


class ErrorHandlingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramAPIError as exc:
            logger.error("Telegram API error: %s", exc, exc_info=True)
        except Exception as exc:  # noqa: BLE001 - top level safety net
            logger.exception("Unhandled exception while processing update: %s", exc)
            user = data.get("event_from_user")
            try:
                if isinstance(event, Update) and event.message:
                    await event.message.answer("⚠️ Something went wrong. Please try again later.")
                elif isinstance(event, Update) and event.callback_query:
                    await event.callback_query.answer("⚠️ Something went wrong.", show_alert=True)
            except Exception:  # noqa: BLE001
                pass
