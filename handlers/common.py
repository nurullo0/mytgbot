"""Handlers shared by everyone: /start, /help and the force-sub check button."""

import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

from config import config
from database import db
from keyboards.reply import main_menu_keyboard
from keyboards.inline import force_sub_keyboard

logger = logging.getLogger(__name__)
router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    is_new = await db.upsert_user(user.id, user.username, user.first_name)
    if is_new:
        logger.info("New user joined: %s (%s)", user.id, user.username)

    text = (
        f"👋 Hello, <b>{user.first_name or 'there'}</b>!\n\n"
        "🎬 Welcome to <b>Movie Bot</b>.\n\n"
        "Send me a <b>movie code</b> (e.g. <code>101</code>) and I'll instantly send you the movie.\n\n"
        "You can also use the menu below to search by name or browse recent/popular movies."
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Help")
async def cmd_help(message: Message) -> None:
    text = (
        "📖 <b>How to use this bot</b>\n\n"
        "• Send a movie <b>code</b> (e.g. <code>101</code>) to get that movie instantly.\n"
        "• Tap <b>🔍 Search by Name</b> to find a movie by its title.\n"
        "• Tap <b>🆕 Recent Movies</b> or <b>🔥 Popular Movies</b> to browse.\n\n"
        "If a code doesn't exist, the bot will tell you <i>Movie not found</i>."
    )
    await message.answer(text)


@router.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery) -> None:
    """This callback is allowed through ForceSubscriptionMiddleware unconditionally,
    so by the time we land here the middleware itself decides whether the user
    is now a member. We just re-trigger a friendly response."""
    user = callback.from_user
    not_joined = []
    for channel in config.force_sub_channels:
        try:
            member = await callback.bot.get_chat_member(chat_id=channel, user_id=user.id)
            if member.status in ("left", "kicked"):
                not_joined.append(channel)
        except Exception:  # noqa: BLE001
            not_joined.append(channel)

    if not_joined:
        await callback.answer("You haven't joined all required channels yet.", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=force_sub_keyboard(not_joined))
        return

    await callback.answer("✅ Access granted!")
    await db.upsert_user(user.id, user.username, user.first_name)
    await callback.message.delete()
    await callback.message.answer(
        "✅ Thanks for joining! You can now use the bot.", reply_markup=main_menu_keyboard()
    )
