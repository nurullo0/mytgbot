"""
Central configuration module.
Loads all settings from environment variables (.env file) so the bot
never contains hard-coded secrets and can be deployed anywhere
(local, VPS, Railway, Render) without code changes.
"""

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _parse_int_list(raw: str) -> List[int]:
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip().lstrip("-").isdigit()]


def _parse_str_list(raw: str) -> List[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass
class Config:
    # --- Core ---
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: List[int] = field(default_factory=lambda: _parse_int_list(os.getenv("ADMIN_IDS", "")))

    # --- Force subscription ---
    # Comma separated channel usernames or chat ids, e.g. "@my_channel,-1001234567890"
    force_sub_channels: List[str] = field(
        default_factory=lambda: _parse_str_list(os.getenv("FORCE_SUB_CHANNELS", ""))
    )

    # --- Database ---
    # SQLite is used by default. To migrate to PostgreSQL, set DATABASE_BACKEND=postgres
    # and provide DATABASE_URL (see database.py / README for details).
    database_backend: str = os.getenv("DATABASE_BACKEND", "sqlite")
    db_path: str = os.getenv("DB_PATH", "movie_bot.db")
    database_url: str = os.getenv("DATABASE_URL", "")

    # --- Behaviour ---
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    rate_limit_seconds: float = float(os.getenv("RATE_LIMIT_SECONDS", "0.7"))
    broadcast_delay_seconds: float = float(os.getenv("BROADCAST_DELAY_SECONDS", "0.05"))
    items_per_page: int = int(os.getenv("ITEMS_PER_PAGE", "8"))
    membership_cache_seconds: int = int(os.getenv("MEMBERSHIP_CACHE_SECONDS", "300"))


config = Config()

if not config.bot_token:
    raise RuntimeError(
        "BOT_TOKEN is not set. Copy .env.example to .env and fill in your bot token."
    )

if not config.admin_ids:
    # Not fatal - bot can still run, but no one will be able to use /admin until
    # an owner id is added to ADMIN_IDS in the .env file.
    pass
