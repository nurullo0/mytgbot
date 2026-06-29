"""
Async database layer built on aiosqlite.

Design notes for easy PostgreSQL migration:
- All SQL is written in a dialect-neutral subset (no SQLite-only functions
  except `?` placeholders, which is the only thing that differs from
  asyncpg's `$1, $2...` style).
- All access goes through the `Database` class below. If you migrate to
  Postgres, you only need to rewrite this single file (swap aiosqlite for
  asyncpg, change placeholders, and add a connection pool) - nothing in
  handlers/ has to change because they only call Database methods.
- A single shared connection protected by an asyncio.Lock is used, which
  is the recommended safe pattern for aiosqlite under heavy concurrency.
  WAL mode is enabled for much better read/write concurrency.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class Movie:
    id: int
    code: str
    title: str
    description: Optional[str]
    file_id: str
    file_type: str
    thumbnail_file_id: Optional[str]
    added_by: int
    added_at: float
    downloads_count: int


@dataclass
class User:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    joined_at: float
    last_active: float
    is_banned: int


class Database:
    """Thin async wrapper around a single SQLite connection."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.execute("PRAGMA busy_timeout=5000;")
        await self._create_tables()
        logger.info("Database connected at %s", self._db_path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            logger.info("Database connection closed")

    async def _create_tables(self) -> None:
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                joined_at   REAL NOT NULL,
                last_active REAL NOT NULL,
                is_banned   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS movies (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                code              TEXT NOT NULL UNIQUE,
                title             TEXT NOT NULL,
                description       TEXT,
                file_id           TEXT NOT NULL,
                file_type         TEXT NOT NULL DEFAULT 'video',
                thumbnail_file_id TEXT,
                added_by          INTEGER NOT NULL,
                added_at          REAL NOT NULL,
                downloads_count   INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_movies_code ON movies(code);
            CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title);
            CREATE INDEX IF NOT EXISTS idx_movies_added_at ON movies(added_at);
            CREATE INDEX IF NOT EXISTS idx_movies_downloads ON movies(downloads_count);

            CREATE TABLE IF NOT EXISTS admins (
                user_id    INTEGER PRIMARY KEY,
                role       TEXT NOT NULL DEFAULT 'admin',
                added_by   INTEGER,
                added_at   REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS broadcasts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id     INTEGER NOT NULL,
                message_text TEXT,
                total_users  INTEGER NOT NULL DEFAULT 0,
                sent_count   INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                started_at   REAL NOT NULL,
                finished_at  REAL,
                status       TEXT NOT NULL DEFAULT 'running'
            );

            CREATE TABLE IF NOT EXISTS stats_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id    INTEGER,
                movie_code TEXT,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_stats_type_time ON stats_events(event_type, created_at);
            """
        )
        await self._conn.commit()

    # ------------------------------------------------------------------ #
    # Users
    # ------------------------------------------------------------------ #
    async def upsert_user(self, user_id: int, username: Optional[str], first_name: Optional[str]) -> bool:
        """Insert user if new, otherwise refresh activity. Returns True if newly created."""
        now = time.time()
        async with self._lock:
            cursor = await self._conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            exists = await cursor.fetchone()
            if exists:
                await self._conn.execute(
                    "UPDATE users SET username = ?, first_name = ?, last_active = ? WHERE user_id = ?",
                    (username, first_name, now, user_id),
                )
                await self._conn.commit()
                return False
            await self._conn.execute(
                "INSERT INTO users (user_id, username, first_name, joined_at, last_active, is_banned) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (user_id, username, first_name, now, now),
            )
            await self._conn.commit()
            return True

    async def touch_last_active(self, user_id: int) -> None:
        async with self._lock:
            await self._conn.execute(
                "UPDATE users SET last_active = ? WHERE user_id = ?", (time.time(), user_id)
            )
            await self._conn.commit()

    async def get_user(self, user_id: int) -> Optional[User]:
        cursor = await self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return User(**dict(row)) if row else None

    async def is_banned(self, user_id: int) -> bool:
        cursor = await self._conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return bool(row and row["is_banned"])

    async def set_banned(self, user_id: int, banned: bool) -> None:
        async with self._lock:
            await self._conn.execute(
                "UPDATE users SET is_banned = ? WHERE user_id = ?", (int(banned), user_id)
            )
            await self._conn.commit()

    async def count_users(self) -> int:
        cursor = await self._conn.execute("SELECT COUNT(*) AS c FROM users")
        row = await cursor.fetchone()
        return row["c"]

    async def get_all_user_ids(self) -> List[int]:
        cursor = await self._conn.execute("SELECT user_id FROM users WHERE is_banned = 0")
        rows = await cursor.fetchall()
        return [r["user_id"] for r in rows]

    # ------------------------------------------------------------------ #
    # Movies
    # ------------------------------------------------------------------ #
    async def add_movie(
        self,
        code: str,
        title: str,
        file_id: str,
        added_by: int,
        description: Optional[str] = None,
        file_type: str = "video",
        thumbnail_file_id: Optional[str] = None,
    ) -> Optional[int]:
        async with self._lock:
            try:
                cursor = await self._conn.execute(
                    "INSERT INTO movies (code, title, description, file_id, file_type, "
                    "thumbnail_file_id, added_by, added_at, downloads_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (code, title, description, file_id, file_type, thumbnail_file_id, added_by, time.time()),
                )
                await self._conn.commit()
                return cursor.lastrowid
            except aiosqlite.IntegrityError:
                return None  # code already exists

    async def get_movie_by_code(self, code: str) -> Optional[Movie]:
        cursor = await self._conn.execute("SELECT * FROM movies WHERE code = ?", (code,))
        row = await cursor.fetchone()
        return Movie(**dict(row)) if row else None

    async def get_movie_by_id(self, movie_id: int) -> Optional[Movie]:
        cursor = await self._conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
        row = await cursor.fetchone()
        return Movie(**dict(row)) if row else None

    async def delete_movie(self, code: str) -> bool:
        async with self._lock:
            cursor = await self._conn.execute("DELETE FROM movies WHERE code = ?", (code,))
            await self._conn.commit()
            return cursor.rowcount > 0

    async def update_movie_field(self, code: str, field_name: str, value) -> bool:
        allowed = {"code", "title", "description", "file_id", "file_type", "thumbnail_file_id"}
        if field_name not in allowed:
            raise ValueError(f"Field '{field_name}' cannot be updated")
        async with self._lock:
            try:
                cursor = await self._conn.execute(
                    f"UPDATE movies SET {field_name} = ? WHERE code = ?", (value, code)
                )
                await self._conn.commit()
                return cursor.rowcount > 0
            except aiosqlite.IntegrityError:
                return False  # e.g. new code already taken

    async def increment_downloads(self, code: str) -> None:
        async with self._lock:
            await self._conn.execute(
                "UPDATE movies SET downloads_count = downloads_count + 1 WHERE code = ?", (code,)
            )
            await self._conn.commit()

    async def search_movies_by_name(self, query: str, limit: int = 20) -> List[Movie]:
        cursor = await self._conn.execute(
            "SELECT * FROM movies WHERE title LIKE ? ORDER BY downloads_count DESC LIMIT ?",
            (f"%{query}%", limit),
        )
        rows = await cursor.fetchall()
        return [Movie(**dict(r)) for r in rows]

    async def get_recent_movies(self, limit: int = 10, offset: int = 0) -> List[Movie]:
        cursor = await self._conn.execute(
            "SELECT * FROM movies ORDER BY added_at DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        rows = await cursor.fetchall()
        return [Movie(**dict(r)) for r in rows]

    async def get_popular_movies(self, limit: int = 10, offset: int = 0) -> List[Movie]:
        cursor = await self._conn.execute(
            "SELECT * FROM movies ORDER BY downloads_count DESC, added_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [Movie(**dict(r)) for r in rows]

    async def count_movies(self) -> int:
        cursor = await self._conn.execute("SELECT COUNT(*) AS c FROM movies")
        row = await cursor.fetchone()
        return row["c"]

    # ------------------------------------------------------------------ #
    # Admins
    # ------------------------------------------------------------------ #
    async def add_admin(self, user_id: int, added_by: int, role: str = "admin") -> None:
        async with self._lock:
            await self._conn.execute(
                "INSERT INTO admins (user_id, role, added_by, added_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET role = excluded.role",
                (user_id, role, added_by, time.time()),
            )
            await self._conn.commit()

    async def remove_admin(self, user_id: int) -> bool:
        async with self._lock:
            cursor = await self._conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            await self._conn.commit()
            return cursor.rowcount > 0

    async def is_admin_in_db(self, user_id: int) -> bool:
        cursor = await self._conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return bool(await cursor.fetchone())

    async def get_admin_role(self, user_id: int) -> Optional[str]:
        cursor = await self._conn.execute("SELECT role FROM admins WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row["role"] if row else None

    async def list_admins(self) -> List[aiosqlite.Row]:
        cursor = await self._conn.execute("SELECT * FROM admins ORDER BY added_at")
        return await cursor.fetchall()

    # ------------------------------------------------------------------ #
    # Broadcasts
    # ------------------------------------------------------------------ #
    async def create_broadcast(self, admin_id: int, message_text: Optional[str], total_users: int) -> int:
        async with self._lock:
            cursor = await self._conn.execute(
                "INSERT INTO broadcasts (admin_id, message_text, total_users, started_at, status) "
                "VALUES (?, ?, ?, ?, 'running')",
                (admin_id, message_text, total_users, time.time()),
            )
            await self._conn.commit()
            return cursor.lastrowid

    async def update_broadcast_progress(self, broadcast_id: int, sent: int, failed: int) -> None:
        async with self._lock:
            await self._conn.execute(
                "UPDATE broadcasts SET sent_count = ?, failed_count = ? WHERE id = ?",
                (sent, failed, broadcast_id),
            )
            await self._conn.commit()

    async def finish_broadcast(self, broadcast_id: int) -> None:
        async with self._lock:
            await self._conn.execute(
                "UPDATE broadcasts SET status = 'finished', finished_at = ? WHERE id = ?",
                (time.time(), broadcast_id),
            )
            await self._conn.commit()

    # ------------------------------------------------------------------ #
    # Statistics
    # ------------------------------------------------------------------ #
    async def log_event(self, event_type: str, user_id: Optional[int] = None, movie_code: Optional[str] = None) -> None:
        async with self._lock:
            await self._conn.execute(
                "INSERT INTO stats_events (event_type, user_id, movie_code, created_at) VALUES (?, ?, ?, ?)",
                (event_type, user_id, movie_code, time.time()),
            )
            await self._conn.commit()

    async def get_stats_summary(self) -> dict:
        day_ago = time.time() - 86400
        week_ago = time.time() - 7 * 86400
        cursor = await self._conn.execute("SELECT COUNT(*) AS c FROM users")
        total_users = (await cursor.fetchone())["c"]

        cursor = await self._conn.execute("SELECT COUNT(*) AS c FROM users WHERE joined_at >= ?", (day_ago,))
        new_users_24h = (await cursor.fetchone())["c"]

        cursor = await self._conn.execute("SELECT COUNT(*) AS c FROM movies")
        total_movies = (await cursor.fetchone())["c"]

        cursor = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM stats_events WHERE event_type = 'download' AND created_at >= ?",
            (day_ago,),
        )
        downloads_24h = (await cursor.fetchone())["c"]

        cursor = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM stats_events WHERE event_type = 'download' AND created_at >= ?",
            (week_ago,),
        )
        downloads_7d = (await cursor.fetchone())["c"]

        cursor = await self._conn.execute("SELECT COALESCE(SUM(downloads_count), 0) AS c FROM movies")
        total_downloads = (await cursor.fetchone())["c"]

        return {
            "total_users": total_users,
            "new_users_24h": new_users_24h,
            "total_movies": total_movies,
            "downloads_24h": downloads_24h,
            "downloads_7d": downloads_7d,
            "total_downloads": total_downloads,
        }


# Module-level singleton. Created eagerly (but not yet connected) so that
# every module doing `from database import db` shares the exact same
# object. main.py calls `await db.connect()` during startup, which mutates
# this same instance in place - no re-assignment needed, so the shared
# reference everywhere stays valid.
from config import config  # noqa: E402

db = Database(config.db_path)
