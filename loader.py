"""
Initializes the single shared Bot and Dispatcher instances used across
the whole project. Importing this module anywhere guarantees you get
the exact same bot/dp objects (no duplicated polling, no duplicated sessions).
"""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config

# MemoryStorage is fine for a single-process deployment (Railway/Render/VPS).
# If you scale to multiple workers/processes, swap this for RedisStorage:
#   from aiogram.fsm.storage.redis import RedisStorage
#   storage = RedisStorage.from_url(config.redis_url)
storage = MemoryStorage()

bot = Bot(
    token=config.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher(storage=storage)
