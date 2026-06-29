"""User-facing handlers: instant code lookup, name search, recent & popular lists."""

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import config
from database import db, Movie
from keyboards.inline import movie_list_keyboard
from keyboards.reply import main_menu_keyboard, cancel_keyboard
from states.admin_states import SearchByName
from utils.helpers import is_valid_code, escape_html

logger = logging.getLogger(__name__)
router = Router(name="user")

PAGE_SIZE = config.items_per_page


async def _send_movie(message: Message, movie: Movie) -> None:
    caption = f"🎬 <b>{escape_html(movie.title)}</b>\n🔢 Code: <code>{movie.code}</code>"
    if movie.description:
        caption += f"\n\n{escape_html(movie.description)}"

    if movie.file_type == "video":
        await message.answer_video(movie.file_id, caption=caption)
    elif movie.file_type == "document":
        await message.answer_document(movie.file_id, caption=caption)
    else:
        await message.answer_animation(movie.file_id, caption=caption)

    await db.increment_downloads(movie.code)
    await db.log_event("download", message.from_user.id, movie.code)


@router.message(F.text.regexp(r"^[A-Za-z0-9_-]{1,32}$") & ~F.text.startswith("/"))
async def handle_code_lookup(message: Message, state: FSMContext) -> None:
    """Treat any short alphanumeric text (not a command) as a movie-code lookup,
    unless we are currently mid-conversation in another FSM flow."""
    current_state = await state.get_state()
    if current_state is not None:
        return  # let the active FSM flow's own handler deal with this message

    code = message.text.strip()
    if not is_valid_code(code):
        return

    await db.touch_last_active(message.from_user.id)
    movie = await db.get_movie_by_code(code)
    await db.log_event("search_code", message.from_user.id, code)

    if movie is None:
        await message.answer("❌ <b>Movie not found.</b>\n\nPlease check the code and try again.")
        return

    await _send_movie(message, movie)


@router.message(F.text == "🔍 Search by Name")
async def search_by_name_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchByName.waiting_for_query)
    await message.answer(
        "🔎 Send me the <b>movie name</b> (or part of it) you want to search for.",
        reply_markup=cancel_keyboard(),
    )


@router.message(SearchByName.waiting_for_query, F.text == "❌ Cancel")
async def cancel_search(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu_keyboard())


@router.message(SearchByName.waiting_for_query)
async def search_by_name_run(message: Message, state: FSMContext) -> None:
    await state.clear()
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Please enter at least 2 characters to search.", reply_markup=main_menu_keyboard())
        return

    results = await db.search_movies_by_name(query, limit=PAGE_SIZE)
    await db.log_event("search_name", message.from_user.id)

    if not results:
        await message.answer(
            f"❌ No movies found matching <b>{escape_html(query)}</b>.", reply_markup=main_menu_keyboard()
        )
        return

    await message.answer(
        f"🔎 Found <b>{len(results)}</b> result(s) for <b>{escape_html(query)}</b>:",
        reply_markup=main_menu_keyboard(),
    )
    await message.answer(
        "Tap a movie to get it:",
        reply_markup=movie_list_keyboard(results, "search", 0, has_next=False),
    )


@router.message(F.text == "🆕 Recent Movies")
async def recent_movies(message: Message) -> None:
    movies = await db.get_recent_movies(limit=PAGE_SIZE, offset=0)
    if not movies:
        await message.answer("No movies have been added yet.")
        return
    extra = await db.get_recent_movies(limit=1, offset=PAGE_SIZE)
    await message.answer(
        "🆕 <b>Recently Added Movies</b>",
        reply_markup=movie_list_keyboard(movies, "recent", 0, has_next=bool(extra)),
    )


@router.message(F.text == "🔥 Popular Movies")
async def popular_movies(message: Message) -> None:
    movies = await db.get_popular_movies(limit=PAGE_SIZE, offset=0)
    if not movies:
        await message.answer("No movies have been added yet.")
        return
    extra = await db.get_popular_movies(limit=1, offset=PAGE_SIZE)
    await message.answer(
        "🔥 <b>Most Popular Movies</b>",
        reply_markup=movie_list_keyboard(movies, "popular", 0, has_next=bool(extra)),
    )


@router.callback_query(F.data.startswith("list:"))
async def paginate_list(callback: CallbackQuery) -> None:
    _, list_type, page_str = callback.data.split(":")
    page = int(page_str)
    offset = page * PAGE_SIZE

    if list_type == "recent":
        movies = await db.get_recent_movies(limit=PAGE_SIZE, offset=offset)
        extra = await db.get_recent_movies(limit=1, offset=offset + PAGE_SIZE)
        title = "🆕 <b>Recently Added Movies</b>"
    elif list_type == "popular":
        movies = await db.get_popular_movies(limit=PAGE_SIZE, offset=offset)
        extra = await db.get_popular_movies(limit=1, offset=offset + PAGE_SIZE)
        title = "🔥 <b>Most Popular Movies</b>"
    else:
        await callback.answer()
        return

    if not movies:
        await callback.answer("No more movies.", show_alert=True)
        return

    await callback.message.edit_text(
        title, reply_markup=movie_list_keyboard(movies, list_type, page, has_next=bool(extra))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("movie:"))
async def send_movie_from_list(callback: CallbackQuery) -> None:
    code = callback.data.split(":", 1)[1]
    movie = await db.get_movie_by_code(code)
    if movie is None:
        await callback.answer("Movie not found.", show_alert=True)
        return
    await callback.answer()
    await _send_movie(callback.message, movie)
