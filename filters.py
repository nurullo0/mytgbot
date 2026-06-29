"""
Custom filters used to restrict handlers to admins/owners only.
Admin status is resolved from two sources:
  1. config.admin_ids (the "owners" hard-coded in .env, always trusted)
  2. the `admins` DB table (admins added at runtime via the bot itself)
"""

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from config import config
from database import db


async def _is_admin(user_id: int) -> bool:
    if user_id in config.admin_ids:
        return True
    return await db.is_admin_in_db(user_id)


async def _is_owner(user_id: int) -> bool:
    return user_id in config.admin_ids


class IsAdmin(BaseFilter):
    """Allows owners (from .env) and admins added via the bot."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None:
            return False
        return await _is_admin(user.id)


class IsOwner(BaseFilter):
    """Allows only owners hard-coded in ADMIN_IDS - used for sensitive actions
    like adding/removing other admins."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None:
            return False
        return await _is_owner(user.id)
