"""FSM state groups for multi-step admin operations."""

from aiogram.fsm.state import State, StatesGroup


class AddMovie(StatesGroup):
    waiting_for_file = State()
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_description = State()


class EditMovie(StatesGroup):
    waiting_for_code = State()
    waiting_for_choice = State()
    waiting_for_new_value = State()
    waiting_for_new_file = State()


class DeleteMovie(StatesGroup):
    waiting_for_code = State()
    waiting_for_confirmation = State()


class Broadcast(StatesGroup):
    waiting_for_content = State()
    waiting_for_confirmation = State()


class ManageAdmins(StatesGroup):
    waiting_for_user_id = State()


class SearchByName(StatesGroup):
    waiting_for_query = State()
