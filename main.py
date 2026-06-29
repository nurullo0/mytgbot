"""
Application entry point.

Run with:  python main.py
"""

import asyncio
import logging

from aiogram.types import BotCommand

from config import config
from database import db
from loader import bot, dp
from middlewares import ThrottlingMiddleware, ForceSubscriptionMiddleware, ErrorHandlingMiddleware
from utils.logger import setup_logging

from handlers import common, user, admin

logger = logging.getLogger(__name__)


async def set_bot_commands() -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="help", description="How to use this bot"),
            BotCommand(command="admin", description="Open admin panel (admins only)"),
        ]
    )


async def on_startup() -> None:
    await db.connect()
    await set_bot_commands()
    logger.info("Bot startup complete. Admin IDs: %s", config.admin_ids)


async def on_shutdown() -> None:
    await db.close()
    await bot.session.close()
    logger.info("Bot shutdown complete.")


def register_middlewares() -> None:
    # Outer middlewares run for every update before routing, regardless of
    # update type - exactly what we need for throttling/force-sub/errors.
    dp.update.outer_middleware(ErrorHandlingMiddleware())
    dp.update.outer_middleware(ThrottlingMiddleware())
    dp.update.outer_middleware(ForceSubscriptionMiddleware())


def register_routers() -> None:
    # Admin router first so /admin and its callbacks take priority,
    # then user-facing handlers, then generic/common fallback handlers.
    dp.include_router(admin.router)
    dp.include_router(user.router)
    dp.include_router(common.router)


async def main() -> None:
    setup_logging()
    register_middlewares()
    register_routers()

    await on_startup()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
