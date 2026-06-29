"""
Admin panel: /admin entry point plus every management flow
(add/edit/delete movie, broadcast, statistics, admin management).
All handlers in this router are protected by the IsAdmin filter applied
at router level, except the "add admin" action which additionally
requires IsOwner.
"""

import asyncio
import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from config import config
from database import db
from filters import IsAdmin, IsOwner
from keyboards.inline import (
    admin_panel_keyboard,
    edit_movie_fields_keyboard,
    confirm_keyboard,
    back_to_admin_keyboard,
    manage_admins_keyboard,
)
from keyboards.reply import main_menu_keyboard, cancel_keyboard
from states.admin_states import AddMovie, EditMovie, DeleteMovie, Broadcast, ManageAdmins
from utils.helpers import is_valid_code, escape_html, format_timestamp

logger = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ---------------------------------------------------------------------- #
# Entry point
# ---------------------------------------------------------------------- #
@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    await message.answer("🛠 <b>Admin Panel</b>", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🛠 <b>Admin Panel</b>", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:close")
async def admin_close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Cancelled.", reply_markup=back_to_admin_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------- #
# Add movie
# ---------------------------------------------------------------------- #
@router.callback_query(F.data == "admin:add")
async def add_movie_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddMovie.waiting_for_file)
    await callback.message.answer(
        "🎞 Send the <b>video file</b> (or document/animation) for the new movie.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(AddMovie.waiting_for_file, F.text == "❌ Cancel")
@router.message(EditMovie.waiting_for_new_file, F.text == "❌ Cancel")
async def cancel_file_step(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu_keyboard())


@router.message(AddMovie.waiting_for_file, F.video | F.document | F.animation)
async def add_movie_get_file(message: Message, state: FSMContext) -> None:
    if message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.document:
        file_id, file_type = message.document.file_id, "document"
    else:
        file_id, file_type = message.animation.file_id, "animation"

    await state.update_data(file_id=file_id, file_type=file_type)
    await state.set_state(AddMovie.waiting_for_code)
    await message.answer("🔢 Now send the unique <b>code</b> for this movie (e.g. <code>101</code>).")


@router.message(AddMovie.waiting_for_file)
async def add_movie_wrong_file(message: Message) -> None:
    await message.answer("Please send a valid video, document or animation file, or tap ❌ Cancel.")


@router.message(AddMovie.waiting_for_code)
async def add_movie_get_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    if not is_valid_code(code):
        await message.answer("Invalid code format. Use letters/numbers, no spaces. Try again.")
        return
    if await db.get_movie_by_code(code) is not None:
        await message.answer("⚠️ This code is already used by another movie. Choose a different one.")
        return
    await state.update_data(code=code)
    await state.set_state(AddMovie.waiting_for_title)
    await message.answer("🎬 Now send the movie <b>title</b>.")


@router.message(AddMovie.waiting_for_title)
async def add_movie_get_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(AddMovie.waiting_for_description)
    await message.answer(
        "📝 Send a short <b>description</b> (or tap /skip to leave it empty)."
    )


@router.message(AddMovie.waiting_for_description, Command("skip"))
@router.message(AddMovie.waiting_for_description)
async def add_movie_get_description(message: Message, state: FSMContext) -> None:
    description = None if message.text and message.text.startswith("/skip") else message.text
    data = await state.get_data()
    await state.clear()

    movie_id = await db.add_movie(
        code=data["code"],
        title=data["title"],
        file_id=data["file_id"],
        added_by=message.from_user.id,
        description=description,
        file_type=data["file_type"],
    )

    if movie_id is None:
        await message.answer("❌ Failed to add movie - code already exists.", reply_markup=main_menu_keyboard())
        return

    logger.info("Admin %s added movie '%s' (code=%s)", message.from_user.id, data["title"], data["code"])
    await message.answer(
        f"✅ Movie added!\n\n🎬 <b>{escape_html(data['title'])}</b>\n🔢 Code: <code>{data['code']}</code>",
        reply_markup=main_menu_keyboard(),
    )


# ---------------------------------------------------------------------- #
# Delete movie
# ---------------------------------------------------------------------- #
@router.callback_query(F.data == "admin:delete")
async def delete_movie_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DeleteMovie.waiting_for_code)
    await callback.message.answer("🗑 Send the <b>code</b> of the movie to delete.", reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(DeleteMovie.waiting_for_code, F.text == "❌ Cancel")
async def cancel_delete(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu_keyboard())


@router.message(DeleteMovie.waiting_for_code)
async def delete_movie_get_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    movie = await db.get_movie_by_code(code)
    if movie is None:
        await message.answer("❌ Movie not found. Try another code or tap ❌ Cancel.")
        return
    await state.update_data(code=code, title=movie.title)
    await state.set_state(DeleteMovie.waiting_for_confirmation)
    await message.answer(
        f"⚠️ Delete <b>{escape_html(movie.title)}</b> (code <code>{code}</code>)? This cannot be undone.",
        reply_markup=confirm_keyboard("confirm_delete"),
    )


@router.callback_query(DeleteMovie.waiting_for_confirmation, F.data == "confirm_delete")
async def confirm_delete_movie(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    deleted = await db.delete_movie(data["code"])
    if deleted:
        logger.info("Admin %s deleted movie code=%s", callback.from_user.id, data["code"])
        await callback.message.edit_text(f"✅ Deleted <b>{escape_html(data['title'])}</b>.")
    else:
        await callback.message.edit_text("❌ Could not delete - movie not found.")
    await callback.answer()


# ---------------------------------------------------------------------- #
# Edit movie
# ---------------------------------------------------------------------- #
@router.callback_query(F.data == "admin:edit")
async def edit_movie_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditMovie.waiting_for_code)
    await callback.message.answer("✏️ Send the <b>code</b> of the movie you want to edit.", reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(EditMovie.waiting_for_code, F.text == "❌ Cancel")
async def cancel_edit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu_keyboard())


@router.message(EditMovie.waiting_for_code)
async def edit_movie_get_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    movie = await db.get_movie_by_code(code)
    if movie is None:
        await message.answer("❌ Movie not found. Try another code or tap ❌ Cancel.")
        return
    await state.update_data(code=code)
    await state.set_state(EditMovie.waiting_for_choice)
    await message.answer(
        f"Editing <b>{escape_html(movie.title)}</b>. What do you want to change?",
        reply_markup=edit_movie_fields_keyboard(),
    )


@router.callback_query(EditMovie.waiting_for_choice, F.data.startswith("edit_field:"))
async def edit_movie_choose_field(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":", 1)[1]
    if field == "cancel":
        await state.clear()
        await callback.message.edit_text("Cancelled.", reply_markup=back_to_admin_keyboard())
        await callback.answer()
        return

    await state.update_data(field=field)
    if field == "file_id":
        await state.set_state(EditMovie.waiting_for_new_file)
        await callback.message.answer("🎞 Send the new video/document/animation file.", reply_markup=cancel_keyboard())
    else:
        await state.set_state(EditMovie.waiting_for_new_value)
        prompts = {
            "code": "🔢 Send the new unique code.",
            "title": "🎬 Send the new title.",
            "description": "📝 Send the new description.",
        }
        await callback.message.answer(prompts[field], reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(EditMovie.waiting_for_new_file, F.video | F.document | F.animation)
async def edit_movie_set_file(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.document:
        file_id, file_type = message.document.file_id, "document"
    else:
        file_id, file_type = message.animation.file_id, "animation"

    await db.update_movie_field(data["code"], "file_id", file_id)
    await db.update_movie_field(data["code"], "file_type", file_type)
    await state.clear()
    logger.info("Admin %s replaced file for movie code=%s", message.from_user.id, data["code"])
    await message.answer("✅ Video file updated.", reply_markup=main_menu_keyboard())


@router.message(EditMovie.waiting_for_new_value, F.text == "❌ Cancel")
async def cancel_edit_value(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu_keyboard())


@router.message(EditMovie.waiting_for_new_value)
async def edit_movie_set_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field, code, new_value = data["field"], data["code"], message.text.strip()

    if field == "code" and not is_valid_code(new_value):
        await message.answer("Invalid code format. Try again.")
        return

    success = await db.update_movie_field(code, field, new_value)
    await state.clear()

    if not success:
        await message.answer("❌ Update failed (code may already be taken).", reply_markup=main_menu_keyboard())
        return

    logger.info("Admin %s updated %s for movie code=%s", message.from_user.id, field, code)
    await message.answer(f"✅ {field.capitalize()} updated successfully.", reply_markup=main_menu_keyboard())


# ---------------------------------------------------------------------- #
# Statistics
# ---------------------------------------------------------------------- #
@router.callback_query(F.data == "admin:stats")
async def show_stats(callback: CallbackQuery) -> None:
    stats = await db.get_stats_summary()
    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total users: <b>{stats['total_users']}</b>\n"
        f"🆕 New users (24h): <b>{stats['new_users_24h']}</b>\n"
        f"🎬 Total movies: <b>{stats['total_movies']}</b>\n"
        f"⬇️ Downloads (24h): <b>{stats['downloads_24h']}</b>\n"
        f"⬇️ Downloads (7d): <b>{stats['downloads_7d']}</b>\n"
        f"⬇️ Total downloads: <b>{stats['total_downloads']}</b>"
    )
    await callback.message.edit_text(text, reply_markup=back_to_admin_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------- #
# Broadcast
# ---------------------------------------------------------------------- #
@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Broadcast.waiting_for_content)
    await callback.message.answer(
        "📢 Send the message (text, photo, or video with caption) you want to broadcast to all users.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(Broadcast.waiting_for_content, F.text == "❌ Cancel")
async def cancel_broadcast(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu_keyboard())


@router.message(Broadcast.waiting_for_content)
async def broadcast_get_content(message: Message, state: FSMContext) -> None:
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(Broadcast.waiting_for_confirmation)
    total = await db.count_users()
    await message.answer(
        f"You are about to broadcast this to <b>{total}</b> users. Confirm?",
        reply_markup=confirm_keyboard("confirm_broadcast"),
    )


@router.callback_query(Broadcast.waiting_for_confirmation, F.data == "confirm_broadcast")
async def run_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_text("📢 Broadcast started... this may take a while.")
    await callback.answer()

    bot = callback.bot
    user_ids = await db.get_all_user_ids()
    broadcast_id = await db.create_broadcast(callback.from_user.id, None, len(user_ids))

    sent, failed = 0, 0
    for idx, uid in enumerate(user_ids, start=1):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=data["chat_id"], message_id=data["message_id"])
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=data["chat_id"], message_id=data["message_id"])
                sent += 1
            except Exception:  # noqa: BLE001
                failed += 1
        except TelegramForbiddenError:
            failed += 1  # user blocked the bot
        except Exception as exc:  # noqa: BLE001
            logger.warning("Broadcast failed for user %s: %s", uid, exc)
            failed += 1

        if idx % 50 == 0:
            await db.update_broadcast_progress(broadcast_id, sent, failed)
        await asyncio.sleep(config.broadcast_delay_seconds)

    await db.update_broadcast_progress(broadcast_id, sent, failed)
    await db.finish_broadcast(broadcast_id)
    logger.info("Broadcast %s finished: sent=%s failed=%s", broadcast_id, sent, failed)
    await callback.message.answer(
        f"✅ Broadcast finished.\n\nSent: <b>{sent}</b>\nFailed: <b>{failed}</b>",
        reply_markup=back_to_admin_keyboard(),
    )


# ---------------------------------------------------------------------- #
# Manage admins (owner only for mutation)
# ---------------------------------------------------------------------- #
@router.callback_query(F.data == "admin:manage_admins")
async def manage_admins_panel(callback: CallbackQuery) -> None:
    admins = await db.list_admins()
    owners_str = ", ".join(map(str, config.admin_ids)) if config.admin_ids else "None"
    text = f"👮 <b>Admins</b>\n\nOwners (from config): {owners_str}"
    await callback.message.edit_text(text, reply_markup=manage_admins_keyboard(admins))
    await callback.answer()


@router.callback_query(F.data == "addadmin", IsOwner())
async def add_admin_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManageAdmins.waiting_for_user_id)
    await callback.message.answer("Send the numeric Telegram user ID of the new admin.", reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(ManageAdmins.waiting_for_user_id, F.text == "❌ Cancel")
async def cancel_add_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu_keyboard())


@router.message(ManageAdmins.waiting_for_user_id, IsOwner())
async def add_admin_finish(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not message.text.strip().isdigit():
        await message.answer("Invalid ID. Must be numeric.", reply_markup=main_menu_keyboard())
        return
    new_admin_id = int(message.text.strip())
    await db.add_admin(new_admin_id, added_by=message.from_user.id)
    logger.info("Owner %s added new admin %s", message.from_user.id, new_admin_id)
    await message.answer(f"✅ User <code>{new_admin_id}</code> is now an admin.", reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("rmadmin:"), IsOwner())
async def remove_admin(callback: CallbackQuery) -> None:
    target_id = int(callback.data.split(":", 1)[1])
    removed = await db.remove_admin(target_id)
    if removed:
        logger.info("Owner %s removed admin %s", callback.from_user.id, target_id)
        await callback.answer("Admin removed.")
    else:
        await callback.answer("Admin not found.", show_alert=True)
    admins = await db.list_admins()
    await callback.message.edit_reply_markup(reply_markup=manage_admins_keyboard(admins))
