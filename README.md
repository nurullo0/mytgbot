# 🎬 Movie Bot — Telegram Movie Delivery Bot

A production-ready Telegram bot built with **Python 3.12** and **aiogram 3.x** that
delivers movies instantly by code, with force-subscription, search, an admin
panel, broadcasting, and statistics — backed by SQLite (easily migratable to
PostgreSQL).

## Features

**Users**
- `/start` with force-subscription to one or more channels
- Send a code (e.g. `101`) → instant movie delivery via Telegram `file_id` (no re-uploading, near-instant response)
- Search movies by name
- Browse recent movies / popular movies with pagination
- Reply keyboard + inline keyboards

**Admins**
- `/admin` panel (inline UI)
- Add / Edit / Delete movies, change code/title/description, replace video file
- Broadcast a message to all users (with flood-safe delay + retry handling)
- View user count, movie count, and detailed statistics
- Multiple admins with owner-only admin management

**Engineering**
- Clean, modular architecture (`handlers/`, `keyboards/`, `states/`, `utils/`)
- Fully asynchronous (aiogram 3.x + aiosqlite)
- Rate limiting, centralized error handling, structured logging (console + rotating file)
- Input validation everywhere user input is accepted
- Indexed SQLite queries, WAL mode, designed for 10,000+ users

---

## Project Structure

```
movie_bot/
├── config.py            # env-based configuration
├── main.py              # entry point
├── loader.py            # Bot / Dispatcher instances
├── database.py          # async SQLite data layer
├── middlewares.py       # throttling, force-sub, error handling
├── filters.py           # IsAdmin / IsOwner filters
├── handlers/
│   ├── common.py        # /start, /help, force-sub check
│   ├── user.py           # code lookup, search, recent/popular
│   └── admin.py          # admin panel + all admin flows
├── keyboards/
│   ├── reply.py
│   └── inline.py
├── states/
│   └── admin_states.py   # FSM states
├── utils/
│   ├── logger.py
│   ├── throttling.py
│   └── helpers.py
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 1. BotFather Setup

1. Open Telegram and message **@BotFather**.
2. Send `/newbot`, choose a name and a unique username ending in `bot`.
3. Copy the **token** BotFather gives you (looks like `123456789:AAExample...`).
4. (Optional) Send `/setprivacy` → choose your bot → **Disable** if you want it
   to read every group message; not required for this bot.
5. If you'll use force-subscription, create your channel(s), add your bot as
   an **administrator** of each channel (required for `getChatMember` to work).

Get your own numeric Telegram ID by messaging **@userinfobot** — you'll need
it for `ADMIN_IDS`.

---

## 2. Local Installation

```bash
git clone <your-repo-url> movie_bot
cd movie_bot

python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# now edit .env and fill in BOT_TOKEN, ADMIN_IDS, etc.
```

### Configure `.env`

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Token from @BotFather |
| `ADMIN_IDS` | Comma separated numeric Telegram IDs of owners/admins |
| `FORCE_SUB_CHANNELS` | Comma separated `@channel` usernames or numeric chat IDs; leave empty to disable |
| `DATABASE_BACKEND` | `sqlite` (default) or `postgres` |
| `DB_PATH` | SQLite file path (default `movie_bot.db`) |
| `DATABASE_URL` | Postgres connection string (only if `DATABASE_BACKEND=postgres`) |
| `LOG_LEVEL` | `INFO`, `DEBUG`, `WARNING`, etc. |
| `RATE_LIMIT_SECONDS` | Minimum seconds between actions per user |
| `BROADCAST_DELAY_SECONDS` | Delay between each broadcast message (flood control) |
| `ITEMS_PER_PAGE` | Movies shown per page in recent/popular/search lists |
| `MEMBERSHIP_CACHE_SECONDS` | How long a verified channel membership is cached |

### Run locally

```bash
python main.py
```

You should see log lines confirming the database connected and the bot
started polling. Open Telegram and send `/start` to your bot.

---

## 3. Deploying to Railway

1. Push this project to a GitHub repository.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Select your repository.
4. In the Railway project settings → **Variables**, add all the variables
   from `.env.example` (`BOT_TOKEN`, `ADMIN_IDS`, etc.).
5. Under **Settings → Deploy**, set the **Start Command** to:
   ```
   python main.py
   ```
6. Railway auto-detects Python from `requirements.txt`. Deploy.
7. SQLite data lives on Railway's ephemeral filesystem by default — for
   persistence across redeploys, attach a **Railway Volume** mounted at the
   working directory, or switch to PostgreSQL (see below) using Railway's
   built-in PostgreSQL plugin.

---

## 4. Deploying to Render

1. Push the project to GitHub.
2. On [render.com](https://render.com) → **New** → **Background Worker**
   (not a Web Service, since this bot uses long polling, not a webhook/HTTP server).
3. Connect your repo.
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `python main.py`
6. Add all environment variables from `.env.example` under **Environment**.
7. For persistent storage, add a **Render Disk** mounted at your working
   directory, or migrate to PostgreSQL using Render's managed Postgres add-on.

---

## 5. Deploying to a VPS (Ubuntu example)

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv git

git clone <your-repo-url> movie_bot
cd movie_bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # fill in your values
```

Run it permanently with **systemd**:

```ini
# /etc/systemd/system/moviebot.service
[Unit]
Description=Movie Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/movie_bot
ExecStart=/home/ubuntu/movie_bot/.venv/bin/python main.py
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/movie_bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable moviebot
sudo systemctl start moviebot
sudo systemctl status moviebot
journalctl -u moviebot -f   # live logs
```

---

## 6. Migrating from SQLite to PostgreSQL

The data-access layer is fully isolated in `database.py`. To migrate:

1. Add `asyncpg` to `requirements.txt` and `pip install asyncpg`.
2. Replace the `aiosqlite.connect(...)` call in `Database.connect()` with
   `asyncpg.create_pool(dsn=config.database_url)`.
3. Change `?` placeholders to `$1, $2, ...` in each SQL statement (asyncpg style).
4. Replace `cursor.lastrowid` usage with `RETURNING id` clauses on `INSERT`.
5. Set `DATABASE_BACKEND=postgres` and `DATABASE_URL=postgresql://user:pass@host:5432/dbname` in `.env`.

No changes are required in `handlers/`, `filters.py`, or `middlewares.py` —
they only ever call methods on the `db` object.

---

## 7. Admin Usage Guide

- `/admin` opens the inline admin panel (only works for IDs in `ADMIN_IDS`
  or added at runtime via **Manage Admins**).
- **Add Movie**: send the video file → send a unique code → send a title →
  send a description (or `/skip`).
- **Edit Movie**: send the existing code → choose what to change → send the
  new value (or new file).
- **Delete Movie**: send the code → confirm.
- **Broadcast**: send any message (text/photo/video) → confirm → sent to
  every known user with flood-safe delays and automatic retry on rate limits.
- **Statistics**: total users, new users (24h), total movies, downloads (24h/7d/total).
- **Manage Admins**: owners (from `ADMIN_IDS`) can add/remove additional admins
  at runtime, who get full panel access except managing other admins.

---

## 8. Security Notes

- All admin actions are protected by `IsAdmin` / `IsOwner` filters checked
  against both `.env` config and the database.
- All free-text input (codes, titles) is validated and HTML-escaped before
  being echoed back to users.
- Per-user rate limiting is enforced via an outer middleware.
- All exceptions are caught centrally and logged; the bot never crashes from
  a single bad update.
- `.env` is git-ignored by default — never commit real tokens or IDs.
