"""Inline keyboards used throughout the bot."""

from typing import List, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import Movie


def force_sub_keyboard(channels: Sequence[str]) -> InlineKeyboardMarkup:
    rows = []
    for channel in channels:
        username = channel.lstrip("@")
        url = f"https://t.me/{username}" if not username.lstrip("-").isdigit() else None
        if url:
            rows.append([InlineKeyboardButton(text=f"📢 Join {channel}", url=url)])
    rows.append([InlineKeyboardButton(text="✅ I've Joined", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def movie_list_keyboard(movies: Sequence[Movie], list_type: str, page: int, has_next: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🎬 {m.title} [{m.code}]", callback_data=f"movie:{m.code}")]
        for m in movies
    ]
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"list:{list_type}:{page - 1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"list:{list_type}:{page + 1}"))
    if nav_row:
        rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="➕ Add Movie", callback_data="admin:add")],
        [InlineKeyboardButton(text="✏️ Edit Movie", callback_data="admin:edit"),
         InlineKeyboardButton(text="🗑 Delete Movie", callback_data="admin:delete")],
        [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="👮 Manage Admins", callback_data="admin:manage_admins")],
        [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_movie_fields_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Code", callback_data="edit_field:code"),
         InlineKeyboardButton(text="Title", callback_data="edit_field:title")],
        [InlineKeyboardButton(text="Description", callback_data="edit_field:description")],
        [InlineKeyboardButton(text="🎞 Replace Video File", callback_data="edit_field:file_id")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="edit_field:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard(confirm_data: str, cancel_data: str = "cancel_action") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data=confirm_data),
                InlineKeyboardButton(text="❌ Cancel", callback_data=cancel_data),
            ]
        ]
    )


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back to Admin Panel", callback_data="admin:back")]]
    )


def manage_admins_keyboard(admins: Sequence) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"❌ Remove {a['user_id']} ({a['role']})", callback_data=f"rmadmin:{a['user_id']}")]
        for a in admins
    ]
    rows.append([InlineKeyboardButton(text="➕ Add Admin", callback_data="addadmin")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
