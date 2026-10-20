# ============================================================
#           🎬 PROFESSIONAL KINO BOT - AIOGRAM 3.x
#           Bitta faylda, to'liq funksional
#           Qidiruv: faqat kino kodi orqali
#           + RENDER KEEP-ALIVE + INACTIVITY NOTIFIER
# ============================================================

import asyncio
import logging
import os
import sys
import time

import aiosqlite
from aiohttp import web
import aiohttp
from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from dotenv import load_dotenv
load_dotenv()

# ============================================================
#                    ⚙️ SOZLAMALAR
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
MOVIE_CHANNEL_ID = int(os.getenv("MOVIE_CHANNEL_ID", "0"))

DB_PATH = os.getenv("DB_PATH", "kino.db")
MOVIES_PER_PAGE = 10
PROXY_URL = os.getenv("PROXY_URL", None)

BOT_NAME = "🎬 Kino Bot"
CONTACT_ADMIN = "@admin"

BTN_MOVIES    = "🎬 Filmlar"
BTN_SEARCH    = "🔍 Qidiruv"
BTN_FAVORITES = "⭐ Sevimlilar"
BTN_HISTORY   = "📜 Tarix"
BTN_TOP       = "🔥 Top filmlar"
BTN_INFO      = "ℹ️ Ma'lumot"
BTN_LOCK      = "Maxfiy qulf 🔒🔐"

M_ID, M_CODE, M_NAME, M_DESC, M_CAT, M_YEAR, M_COUNTRY, M_LANG, \
M_QUALITY, M_DURATION, M_POSTER, M_FILE, M_CHANNEL, M_VIEWS, \
M_RSUM, M_RCNT, M_ACTIVE, M_CREATED = range(18)

# ============================================================
#           🌐 RENDER KEEP-ALIVE SOZLAMALARI
# ============================================================
PORT = int(os.getenv("PORT", "8080"))          
RENDER_URL = os.getenv("RENDER_URL", "")       
PING_INTERVAL = 15 * 60                        
INACTIVITY_NOTIFY_ID = SUPER_ADMIN_ID          

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
#           📊 AKTIVLIK TRACKER
# ============================================================
LAST_ACTIVITY = time.time()
BOT_STARTED_AT = time.time()

def touch_activity():
    global LAST_ACTIVITY
    LAST_ACTIVITY = time.time()

class ActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        touch_activity()
        return await handler(event, data)

# ============================================================
#                    💾 MA'LUMOTLAR BAZASI
# ============================================================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
            is_banned INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE,
            emoji TEXT DEFAULT '📁', position INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code INTEGER UNIQUE,
            name TEXT, description TEXT DEFAULT '', category_id INTEGER,
            year TEXT DEFAULT '', country TEXT DEFAULT '', language TEXT DEFAULT '',
            quality TEXT DEFAULT 'HD', duration TEXT DEFAULT '',
            poster_id TEXT, file_id TEXT, channel_id INTEGER,
            views INTEGER DEFAULT 0, rating_sum INTEGER DEFAULT 0,
            rating_count INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, link TEXT,
            channel_id TEXT, is_active INTEGER DEFAULT 1)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER, movie_id INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, movie_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            movie_id INTEGER, viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS ratings (
            user_id INTEGER, movie_id INTEGER, rating INTEGER,
            UNIQUE(user_id, movie_id))""")
        await db.commit()
        if SUPER_ADMIN_ID:
            await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
                             (SUPER_ADMIN_ID,))
            await db.commit()

# ---------- USERS ----------
async def add_user(uid, username, full_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
                         (uid, username, full_name))
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_banned = 0") as cur:
            return [r[0] for r in await cur.fetchall()]

# ---------- ADMINS ----------
async def is_admin(uid):
    if uid == SUPER_ADMIN_ID:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id = ?", (uid,)) as cur:
            return await cur.fetchone() is not None

async def add_admin(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
        await db.commit()

async def remove_admin(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (uid,))
        await db.commit()

async def get_all_admins():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins") as cur:
            return [r[0] for r in await cur.fetchall()]

# ---------- CATEGORIES ----------
async def get_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, emoji FROM categories ORDER BY position, id") as cur:
            return await cur.fetchall()

async def get_category(cid):
    if cid is None:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, emoji FROM categories WHERE id = ?", (cid,)) as cur:
            return await cur.fetchone()

async def add_category(name, emoji):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(MAX(position),0)+1 FROM categories") as cur:
            pos = (await cur.fetchone())[0]
        await db.execute("INSERT INTO categories (name, emoji, position) VALUES (?, ?, ?)",
                         (name, emoji, pos))
        await db.commit()

async def update_category(cid, field, value):
    if field not in {"name", "emoji"}:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE categories SET {field} = ? WHERE id = ?", (value, cid))
        await db.commit()

async def delete_category(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM categories WHERE id = ?", (cid,))
        await db.execute("UPDATE movies SET category_id = NULL WHERE category_id = ?", (cid,))
        await db.commit()

async def movies_count_in_category(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM movies WHERE category_id = ?", (cid,)) as cur:
            return (await cur.fetchone())[0]

# ---------- MOVIES ----------
async def get_next_movie_code():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(MAX(code),0)+1 FROM movies") as cur:
            return (await cur.fetchone())[0]

async def code_exists(code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM movies WHERE code = ?", (code,)) as cur:
            return await cur.fetchone() is not None

async def add_movie(data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT INTO movies
            (code, name, description, category_id, year, country, language,
             quality, duration, poster_id, file_id, channel_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data['code'], data['name'], data.get('description', ''),
             data.get('category_id'), data.get('year', ''),
             data.get('country', ''), data.get('language', ''),
             data.get('quality', 'HD'), data.get('duration', ''),
             data.get('poster_id'), data.get('file_id'), data.get('channel_id')))
        await db.commit()

async def get_movie_by_code(code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM movies WHERE code = ? AND is_active = 1", (code,)) as cur:
            return await cur.fetchone()

async def get_movie(mid):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM movies WHERE id = ?", (mid,)) as cur:
            return await cur.fetchone()

async def update_movie(mid, field, value):
    allowed = {"code", "name", "description", "category_id", "year", "country",
               "language", "quality", "duration", "poster_id", "file_id",
               "channel_id", "is_active"}
    if field not in allowed:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE movies SET {field} = ? WHERE id = ?", (value, mid))
        await db.commit()

async def delete_movie(mid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM movies WHERE id = ?", (mid,))
        await db.execute("DELETE FROM favorites WHERE movie_id = ?", (mid,))
        await db.execute("DELETE FROM history WHERE movie_id = ?", (mid,))
        await db.execute("DELETE FROM ratings WHERE movie_id = ?", (mid,))
        await db.commit()

async def get_movies_by_category(cid, page=0, per_page=MOVIES_PER_PAGE):
    offset = page * per_page
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""SELECT * FROM movies WHERE category_id = ? AND is_active = 1
            ORDER BY code LIMIT ? OFFSET ?""", (cid, per_page, offset)) as cur:
            return await cur.fetchall()

async def count_movies_by_category(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM movies WHERE category_id = ? AND is_active = 1",
                              (cid,)) as cur:
            return (await cur.fetchone())[0]

async def get_top_movies(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""SELECT * FROM movies WHERE is_active = 1
            ORDER BY views DESC LIMIT ?""", (limit,)) as cur:
            return await cur.fetchall()

async def increment_views(mid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE movies SET views = views + 1 WHERE id = ?", (mid,))
        await db.commit()

async def get_all_movies(page=0, per_page=10):
    offset = page * per_page
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""SELECT * FROM movies ORDER BY id DESC
            LIMIT ? OFFSET ?""", (per_page, offset)) as cur:
            return await cur.fetchall()

async def count_all_movies():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM movies") as cur:
            return (await cur.fetchone())[0]

# ---------- FAVORITES ----------
async def add_favorite(uid, mid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO favorites (user_id, movie_id) VALUES (?, ?)",
                         (uid, mid))
        await db.commit()

async def remove_favorite(uid, mid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM favorites WHERE user_id = ? AND movie_id = ?", (uid, mid))
        await db.commit()

async def is_favorite(uid, mid):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM favorites WHERE user_id = ? AND movie_id = ?",
                              (uid, mid)) as cur:
            return await cur.fetchone() is not None

async def get_favorites(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""SELECT m.* FROM favorites f
            JOIN movies m ON m.id = f.movie_id
            WHERE f.user_id = ? AND m.is_active = 1
            ORDER BY f.added_at DESC""", (uid,)) as cur:
            return await cur.fetchall()

# ---------- HISTORY ----------
async def add_history(uid, mid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO history (user_id, movie_id) VALUES (?, ?)", (uid, mid))
        await db.commit()

async def get_history(uid, limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""SELECT m.*, MAX(h.viewed_at) as last_view FROM history h
            JOIN movies m ON m.id = h.movie_id
            WHERE h.user_id = ? AND m.is_active = 1
            GROUP BY m.id ORDER BY last_view DESC LIMIT ?""", (uid, limit)) as cur:
            return await cur.fetchall()

async def clear_history(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM history WHERE user_id = ?", (uid,))
        await db.commit()

# ---------- RATINGS ----------
async def rate_movie(uid, mid, rating):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT rating FROM ratings WHERE user_id = ? AND movie_id = ?",
                              (uid, mid)) as cur:
            old = await cur.fetchone()
        if old:
            await db.execute("UPDATE ratings SET rating = ? WHERE user_id = ? AND movie_id = ?",
                             (rating, uid, mid))
            await db.execute("UPDATE movies SET rating_sum = rating_sum - ? + ? WHERE id = ?",
                             (old[0], rating, mid))
        else:
            await db.execute("INSERT INTO ratings (user_id, movie_id, rating) VALUES (?, ?, ?)",
                             (uid, mid, rating))
            await db.execute("""UPDATE movies SET rating_sum = rating_sum + ?,
                rating_count = rating_count + 1 WHERE id = ?""", (rating, mid))
        await db.commit()

async def get_avg_rating(mid):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT rating_sum, rating_count FROM movies WHERE id = ?",
                              (mid,)) as cur:
            row = await cur.fetchone()
        if row and row[1] > 0:
            return round(row[0] / row[1], 1), row[1]
        return 0, 0

# ---------- CHANNELS ----------
async def get_channels(only_active=True):
    async with aiosqlite.connect(DB_PATH) as db:
        q = "SELECT id, name, link, channel_id, is_active FROM channels"
        if only_active:
            q += " WHERE is_active = 1"
        q += " ORDER BY id"
        async with db.execute(q) as cur:
            return await cur.fetchall()

async def get_channel(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, link, channel_id, is_active FROM channels WHERE id = ?",
                              (cid,)) as cur:
            return await cur.fetchone()

async def add_channel(name, link, channel_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO channels (name, link, channel_id) VALUES (?, ?, ?)",
                         (name, link, channel_id))
        await db.commit()

async def update_channel(cid, field, value):
    if field not in {"name", "link", "channel_id", "is_active"}:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE channels SET {field} = ? WHERE id = ?", (value, cid))
        await db.commit()

async def delete_channel(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE id = ?", (cid,))
        await db.commit()

# ---------- STATS ----------
async def get_full_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM movies WHERE is_active = 1") as cur:
            movies = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM categories") as cur:
            cats = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(views),0) FROM movies") as cur:
            views = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM channels WHERE is_active = 1") as cur:
            channels = (await cur.fetchone())[0]
        return {"users": users, "movies": movies, "categories": cats,
                "views": views, "channels": channels}

# ============================================================
#                    🔄 FSM
# ============================================================
class AdminStates(StatesGroup):
    waiting_password = State()
    add_cat_name = State()
    add_cat_emoji = State()
    edit_cat_value = State()
    add_movie_code = State()
    add_movie_name = State()
    add_movie_desc = State()
    add_movie_category = State()
    add_movie_year = State()
    add_movie_country = State()
    add_movie_language = State()
    add_movie_quality = State()
    add_movie_duration = State()
    add_movie_poster = State()
    add_movie_video = State()
    edit_movie_value = State()
    add_channel_name = State()
    add_channel_link = State()
    add_channel_id = State()
    waiting_broadcast = State()
    add_admin_id = State()
    remove_admin_id = State()

class UserStates(StatesGroup):
    search_query = State()

router = Router()

# ============================================================
#                    ⌨️ KLAVIATURALAR
# ============================================================
async def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_MOVIES), KeyboardButton(text=BTN_SEARCH))
    builder.row(KeyboardButton(text=BTN_FAVORITES), KeyboardButton(text=BTN_HISTORY))
    builder.row(KeyboardButton(text=BTN_TOP), KeyboardButton(text=BTN_INFO))
    builder.row(KeyboardButton(text=BTN_LOCK))
    return builder.as_markup(resize_keyboard=True)

def back_kb(cb="back_main", text="⬅️ Orqaga"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=cb)]])

async def categories_kb():
    cats = await get_categories()
    builder = InlineKeyboardBuilder()
    for c in cats:
        builder.button(text=f"{c[2]} {c[1]}", callback_data=f"cat_{c[0]}")
    builder.button(text="⬅️ Orqaga", callback_data="back_main")
    builder.adjust(2)
    return builder.as_markup()

def movies_list_kb(movies, total, page=0, back_cb="back_cats", prefix="mdet", cat_id=None):
    builder = InlineKeyboardBuilder()
    for m in movies:
        builder.button(text=f"🎬 {m[M_NAME]} | {m[M_CODE]}", callback_data=f"{prefix}_{m[M_ID]}")
    builder.adjust(1)
    nav = []
    if page > 0:
        cb = f"pgcat_{cat_id}_{page-1}" if cat_id else f"pg_{page-1}"
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=cb))
    total_pages = max(1, (total + MOVIES_PER_PAGE - 1) // MOVIES_PER_PAGE)
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if (page + 1) * MOVIES_PER_PAGE < total:
        cb = f"pgcat_{cat_id}_{page+1}" if cat_id else f"pg_{page+1}"
        nav.append(InlineKeyboardButton(text="➡️", callback_data=cb))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=back_cb))
    return builder.as_markup()

async def movie_detail_kb(mid, uid):
    builder = InlineKeyboardBuilder()
    is_fav = await is_favorite(uid, mid)
    builder.button(text="❌ Sevimlilardan" if is_fav else "❤️ Sevimlilarga",
                   callback_data=f"fav_{mid}")
    builder.button(text="⭐ Reyting", callback_data=f"rate_{mid}")
    builder.button(text="📤 Ulashish", callback_data=f"share_{mid}")
    builder.button(text="⬅️ Orqaga", callback_data="back_cats")
    builder.adjust(2, 2)
    return builder.as_markup()

def rating_kb(mid):
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(text="⭐" * i, callback_data=f"setrate_{mid}_{i}")
    builder.button(text="⬅️ Orqaga", callback_data=f"mdet_{mid}")
    builder.adjust(1)
    return builder.as_markup()

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_cancel")]])

def admin_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Statistika", callback_data="admin_stats")
    builder.button(text="🎬 Filmlar", callback_data="admin_movies")
    builder.button(text="📂 Kategoriyalar", callback_data="admin_categories")
    builder.button(text="📢 Kanallar", callback_data="admin_channels")
    builder.button(text="📢 Broadcast", callback_data="admin_broadcast")
    builder.button(text="👤 Adminlar", callback_data="admin_admins")
    builder.button(text="⬅️ Yopish", callback_data="back_main")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

async def admin_categories_kb():
    cats = await get_categories()
    builder = InlineKeyboardBuilder()
    for c in cats:
        cnt = await movies_count_in_category(c[0])
        builder.button(text=f"{c[2]} {c[1]} ({cnt})", callback_data=f"acat_{c[0]}")
    builder.button(text="➕ Yangi kategoriya", callback_data="add_cat")
    builder.button(text="⬅️ Orqaga", callback_data="back_admin")
    builder.adjust(1)
    return builder.as_markup()

def category_manage_kb(cid):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Nomini", callback_data=f"ecat_name_{cid}")
    builder.button(text="😀 Emoji", callback_data=f"ecat_emoji_{cid}")
    builder.button(text="🗑 O'chirish", callback_data=f"delcat_{cid}")
    builder.button(text="⬅️ Orqaga", callback_data="admin_categories")
    builder.adjust(2, 1, 1)
    return builder.as_markup()

async def admin_movies_list_kb(page=0):
    movies = await get_all_movies(page=page)
    total = await count_all_movies()
    builder = InlineKeyboardBuilder()
    for m in movies:
        st = "✅" if m[M_ACTIVE] else "🚫"
        builder.button(text=f"{st} #{m[M_CODE]} — {m[M_NAME]}", callback_data=f"amov_{m[M_ID]}")
    builder.adjust(1)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"ampg_{page-1}"))
    total_pages = max(1, (total + MOVIES_PER_PAGE - 1) // MOVIES_PER_PAGE)
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if (page + 1) * MOVIES_PER_PAGE < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"ampg_{page+1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="➕ Yangi film", callback_data="add_movie_start"))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_admin"))
    return builder.as_markup()

def admin_movie_detail_kb(mid):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Nomini", callback_data=f"emov_name_{mid}")
    builder.button(text="🔢 Kodni", callback_data=f"emov_code_{mid}")
    builder.button(text="📝 Tavsif", callback_data=f"emov_desc_{mid}")
    builder.button(text="📅 Yil", callback_data=f"emov_year_{mid}")
    builder.button(text="🌍 Davlat", callback_data=f"emov_country_{mid}")
    builder.button(text="🗣 Til", callback_data=f"emov_language_{mid}")
    builder.button(text="🎞 Sifat", callback_data=f"emov_quality_{mid}")
    builder.button(text="⏱ Davomiylik", callback_data=f"emov_duration_{mid}")
    builder.button(text="🖼 Poster", callback_data=f"emov_poster_{mid}")
    builder.button(text="🎥 Video", callback_data=f"emov_video_{mid}")
    builder.button(text="📂 Kategoriya", callback_data=f"emov_cat_{mid}")
    builder.button(text="🔄 Faollik", callback_data=f"emov_active_{mid}")
    builder.button(text="🗑 O'chirish", callback_data=f"emov_del_{mid}")
    builder.button(text="⬅️ Orqaga", callback_data="admin_movies")
    builder.adjust(2, 2, 2, 2, 2, 2, 1, 1)
    return builder.as_markup()

async def admin_channels_kb():
    channels = await get_channels(only_active=False)
    builder = InlineKeyboardBuilder()
    for c in channels:
        st = "✅" if c[4] else "🚫"
        builder.button(text=f"{st} {c[1]}", callback_data=f"achan_{c[0]}")
    builder.button(text="➕ Yangi kanal", callback_data="add_channel")
    builder.button(text="⬅️ Orqaga", callback_data="back_admin")
    builder.adjust(1)
    return builder.as_markup()

def channel_manage_kb(cid):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Nomi", callback_data=f"echan_name_{cid}")
    builder.button(text="🔗 Link", callback_data=f"echan_link_{cid}")
    builder.button(text="🆔 ID", callback_data=f"echan_id_{cid}")
    builder.button(text="🔄 Faollik", callback_data=f"echan_active_{cid}")
    builder.button(text="🗑 O'chirish", callback_data=f"delchan_{cid}")
    builder.button(text="⬅️ Orqaga", callback_data="admin_channels")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

# ============================================================
#                    🚫 MAJBURIY OBUNA
# ============================================================
async def check_subscription(bot: Bot, uid: int):
    channels = await get_channels(only_active=True)
    if not channels:
        return True, []
    not_subscribed = []
    for ch in channels:
        ch_id = ch[3]
        try:
            target = int(ch_id) if str(ch_id).lstrip("-").isdigit() else ch_id
            member = await bot.get_chat_member(chat_id=target, user_id=uid)
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                not_subscribed.append(ch)
        except Exception as e:
            logger.warning(f"Obuna tekshirishda xato ({ch[1]}): {e}")
    return len(not_subscribed) == 0, not_subscribed

def subscription_kb(channels):
    builder = InlineKeyboardBuilder()
    for ch in channels:
        link = ch[2]
        if not link.startswith("http"):
            link = "https://" + link
        builder.button(text=f"📢 {ch[1]}", url=link)
    builder.button(text="✅ Tekshirish", callback_data="check_sub")
    builder.adjust(1)
    return builder.as_markup()

# ============================================================
#                    ▶️ /start
# ============================================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    u = message.from_user
    await add_user(u.id, u.username or "", u.full_name)

    ok, not_sub = await check_subscription(bot, u.id)
    if not ok:
        await message.answer(
            "👋 Assalomu alaykum!\n\n"
            "🔒 Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:",
            reply_markup=subscription_kb(not_sub))
        return

    await message.answer(
        f"👋 Assalomu alaykum, <b>{u.full_name}</b>!\n\n"
        f"🎬 <b>{BOT_NAME}</b> botiga xush kelibsiz!\n\n"
        f"Kino olish uchun <b>kodini</b> yuboring (masalan: <code>1</code>)\n"
        f"Yoki quyidagi tugmalardan foydalaning 👇",
        reply_markup=await main_menu_kb())

@router.callback_query(F.data == "check_sub")
async def check_sub_cb(call: CallbackQuery, bot: Bot):
    ok, not_sub = await check_subscription(bot, call.from_user.id)
    if ok:
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer(
            "✅ Rahmat! Endi botdan foydalanishingiz mumkin.",
            reply_markup=await main_menu_kb())
    else:
        await call.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)

# ============================================================
#                    🎬 FILMLAR
# ============================================================
@router.message(F.text == BTN_MOVIES)
async def show_movies(message: Message, bot: Bot):
    ok, not_sub = await check_subscription(bot, message.from_user.id)
    if not ok:
        await message.answer("🔒 Iltimos, avval kanallarga a'zo bo'ling:",
                             reply_markup=subscription_kb(not_sub))
        return
    cats = await get_categories()
    if not cats:
        await message.answer("😔 Hozircha kategoriyalar yo'q.")
        return
    await message.answer("📂 <b>Kategoriyani tanlang:</b>",
                         reply_markup=await categories_kb())

@router.callback_query(F.data == "back_cats")
async def back_cats(call: CallbackQuery):
    cats = await get_categories()
    if not cats:
        await call.answer("Bo'sh", show_alert=True)
        return
    try:
        await call.message.edit_text("📂 <b>Kategoriyani tanlang:</b>",
                                     reply_markup=await categories_kb())
    except Exception:
        await call.message.answer("📂 <b>Kategoriyani tanlang:</b>",
                                  reply_markup=await categories_kb())
    await call.answer()

@router.callback_query(F.data.regexp(r"^cat_\d+$"))
async def show_category(call: CallbackQuery):
    cid = int(call.data.replace("cat_", ""))
    cat = await get_category(cid)
    if not cat:
        await call.answer("❌ Topilmadi", show_alert=True)
        return
    await render_movies_page(call, cid, 0)

async def render_movies_page(call: CallbackQuery, cid, page):
    cat = await get_category(cid)
    movies = await get_movies_by_category(cid, page=page)
    total = await count_movies_by_category(cid)
    if not movies:
        await call.answer("Bu kategoriyada film yo'q", show_alert=True)
        return
    text = f"{cat[2]} <b>{cat[1]}</b>\n\n🎬 Jami: <b>{total}</b> ta film"
    kb = movies_list_kb(movies, total, page=page, back_cb="back_cats", cat_id=cid)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.regexp(r"^pgcat_\d+_\d+$"))
async def paginate_category(call: CallbackQuery):
    parts = call.data.replace("pgcat_", "").split("_")
    cid = int(parts[0])
    page = int(parts[1])
    await render_movies_page(call, cid, page)

@router.callback_query(F.data.regexp(r"^mdet_\d+$"))
async def movie_detail(call: CallbackQuery, bot: Bot):
    mid = int(call.data.replace("mdet_", ""))
    m = await get_movie(mid)
    if not m:
        await call.answer("❌ Topilmadi", show_alert=True)
        return
    await send_movie(bot, call, mid, m)

async def send_movie(bot: Bot, call_or_msg, mid, m):
    code = m[M_CODE]
    name = m[M_NAME]
    desc = m[M_DESC]
    year = m[M_YEAR]
    country = m[M_COUNTRY]
    language = m[M_LANG]
    quality = m[M_QUALITY]
    duration = m[M_DURATION]
    poster = m[M_POSTER]
    file_id = m[M_FILE]
    views = m[M_VIEWS]

    avg, cnt = await get_avg_rating(mid)
    rating_text = f"⭐ {avg}/5 ({cnt})" if cnt > 0 else "⭐ Baholanmagan"

    text = (
        f"🎬 <b>{name}</b>\n\n"
        f"🔢 Kod: <code>{code}</code>\n"
        f"📅 Yil: {year or '—'}\n"
        f"🌍 Davlat: {country or '—'}\n"
        f"🗣 Til: {language or '—'}\n"
        f"🎞 Sifat: {quality or '—'}\n"
        f"⏱ Davomiylik: {duration or '—'}\n"
        f"{rating_text}\n"
        f"👁 Ko'rishlar: {views}\n\n"
        f"📝 {desc or '—'}"
    )

    uid = call_or_msg.from_user.id
    kb = await movie_detail_kb(mid, uid)

    await increment_views(mid)
    await add_history(uid, mid)

    if isinstance(call_or_msg, CallbackQuery):
        try:
            await call_or_msg.answer()
        except Exception:
            pass

    try:
        if file_id:
            await bot.send_video(
                chat_id=uid, video=file_id, caption=text,
                reply_markup=kb, supports_streaming=True)
        elif poster:
            await bot.send_photo(uid, poster, caption=text, reply_markup=kb)
        else:
            await bot.send_message(uid, text, reply_markup=kb)
    except Exception as e:
        logger.error(f"Video yuborishda xato: {e}")
        try:
            await bot.send_message(uid, text + "\n\n⚠️ Video yuborilmadi.",
                                   reply_markup=kb)
        except Exception as e2:
            logger.error(f"Fallback ham xato: {e2}")

# ============================================================
#                    🔍 QIDIRUV
# ============================================================
@router.message(F.text == BTN_SEARCH)
async def search_start(message: Message, state: FSMContext, bot: Bot):
    ok, not_sub = await check_subscription(bot, message.from_user.id)
    if not ok:
        await message.answer("🔒 Kanallarga a'zo bo'ling:",
                             reply_markup=subscription_kb(not_sub))
        return
    await state.set_state(UserStates.search_query)
    await message.answer(
        "🔍 <b>Kino kodini kiriting (1 dan 99 gacha):</b>\n\n"
        "Masalan: <code>1</code> yoki <code>99</code>",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Bekor")]],
            resize_keyboard=True))

@router.message(UserStates.search_query, F.text)
async def search_do(message: Message, state: FSMContext, bot: Bot):
    if message.text == "❌ Bekor":
        await state.clear()
        await message.answer("Bekor qilindi", reply_markup=await main_menu_kb())
        return

    query = message.text.strip()

    if not query.isdigit():
        await message.answer(
            "❗ Iltimos, faqat <b>kino kodini</b> (raqam) kiriting.\n\n"
            "Masalan: <code>1</code> yoki <code>99</code>",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="❌ Bekor")]],
                resize_keyboard=True))
        return

    code = int(query)

    if not (1 <= code <= 99):
        await message.answer(
            "❗ Kod <b>1 dan 99 gacha</b> bo'lishi kerak.\n\n"
            "Qaytadan kiriting:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="❌ Bekor")]],
                resize_keyboard=True))
        return

    m = await get_movie_by_code(code)
    await state.clear()

    if not m:
        await message.answer(
            f"❌ <code>{code}</code> kodli kino topilmadi.\n\n"
            f"Kodni tekshirib qaytadan kiriting.",
            reply_markup=await main_menu_kb())
        return

    await send_movie(bot, message, m[M_ID], m)
    await message.answer("🏠 Asosiy menyu", reply_markup=await main_menu_kb())

@router.message(F.text.regexp(r"^\d{1,6}$"), StateFilter(None))
async def get_movie_by_code_handler(message: Message, bot: Bot):
    code = int(message.text.strip())
    m = await get_movie_by_code(code)
    if not m:
        await message.answer(f"❌ <code>{code}</code> kodli film topilmadi.")
        return
    await send_movie(bot, message, m[M_ID], m)

# ============================================================
#                    ⭐ SEVIMLILAR
# ============================================================
@router.message(F.text == BTN_FAVORITES)
async def favorites_list(message: Message):
    favs = await get_favorites(message.from_user.id)
    if not favs:
        await message.answer("⭐ Sevimlilar ro'yxati bo'sh.")
        return
    builder = InlineKeyboardBuilder()
    for m in favs:
        builder.button(text=f"🎬 #{m[M_CODE]} {m[M_NAME]}", callback_data=f"mdet_{m[M_ID]}")
    builder.button(text="⬅️ Orqaga", callback_data="back_main")
    builder.adjust(1)
    await message.answer("⭐ <b>Sevimli filmlar:</b>",
                         reply_markup=builder.as_markup())

@router.callback_query(F.data.regexp(r"^fav_\d+$"))
async def toggle_fav(call: CallbackQuery):
    mid = int(call.data.replace("fav_", ""))
    uid = call.from_user.id
    if await is_favorite(uid, mid):
        await remove_favorite(uid, mid)
        await call.answer("💔 Sevimlilardan olindi")
    else:
        await add_favorite(uid, mid)
        await call.answer("❤️ Sevimlilarga qo'shildi")
    try:
        await call.message.edit_reply_markup(reply_markup=await movie_detail_kb(mid, uid))
    except Exception:
        pass

# ============================================================
#                    📜 TARIX
# ============================================================
@router.message(F.text == BTN_HISTORY)
async def history_list(message: Message):
    hist = await get_history(message.from_user.id)
    if not hist:
        await message.answer("📜 Tarix bo'sh.")
        return
    builder = InlineKeyboardBuilder()
    for m in hist:
        builder.button(text=f"🎬 #{m[M_CODE]} {m[M_NAME]}", callback_data=f"mdet_{m[M_ID]}")
    builder.button(text="🗑 Tozalash", callback_data="clear_history")
    builder.button(text="⬅️ Orqaga", callback_data="back_main")
    builder.adjust(1)
    await message.answer("📜 <b>Ko'rilgan filmlar:</b>",
                         reply_markup=builder.as_markup())

@router.callback_query(F.data == "clear_history")
async def clear_hist(call: CallbackQuery):
    await clear_history(call.from_user.id)
    try:
        await call.message.edit_text("🗑 Tarix tozalandi.")
    except Exception:
        pass
    await call.answer("Tozalandi")

# ============================================================
#                    🔥 TOP FILMLAR
# ============================================================
@router.message(F.text == BTN_TOP)
async def top_movies(message: Message):
    movies = await get_top_movies(10)
    if not movies:
        await message.answer("Bo'sh.")
        return
    builder = InlineKeyboardBuilder()
    for i, m in enumerate(movies, 1):
        builder.button(text=f"{i}. 🎬 #{m[M_CODE]} {m[M_NAME]} ({m[M_VIEWS]} 👁)",
                       callback_data=f"mdet_{m[M_ID]}")
    builder.button(text="⬅️ Orqaga", callback_data="back_main")
    builder.adjust(1)
    await message.answer("🔥 <b>Top 10 filmlar:</b>",
                         reply_markup=builder.as_markup())

# ============================================================
#                    ⭐ REYTING
# ============================================================
@router.callback_query(F.data.regexp(r"^rate_\d+$"))
async def rate_start(call: CallbackQuery):
    mid = int(call.data.replace("rate_", ""))
    try:
        await call.message.edit_reply_markup(reply_markup=rating_kb(mid))
    except Exception:
        pass
    await call.answer("⭐ Baho bering")

@router.callback_query(F.data.regexp(r"^setrate_\d+_\d+$"))
async def rate_set(call: CallbackQuery):
    parts = call.data.split("_")
    mid = int(parts[1])
    rating = int(parts[2])
    await rate_movie(call.from_user.id, mid, rating)
    avg, cnt = await get_avg_rating(mid)
    await call.answer(f"✅ Rahmat! O'rtacha: {avg}/5 ({cnt} ta ovoz)")
    try:
        await call.message.edit_reply_markup(
            reply_markup=await movie_detail_kb(mid, call.from_user.id))
    except Exception:
        pass

# ============================================================
#                    📤 ULASHISH
# ============================================================
@router.callback_query(F.data.regexp(r"^share_\d+$"))
async def share_movie(call: CallbackQuery, bot: Bot):
    mid = int(call.data.replace("share_", ""))
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=movie_{mid}"
    await call.answer(f"🔗 {link}", show_alert=True)

# ============================================================
#                    ℹ️ MA'LUMOT
# ============================================================
@router.message(F.text == BTN_INFO)
async def info(message: Message):
    await message.answer(
        f"🎬 <b>{BOT_NAME}</b>\n\n"
        f"👨‍💻 Admin: {CONTACT_ADMIN}\n"
        f"📞 Murojaat uchun yozing")

# ============================================================
#                    🔒 ADMIN KIRISH
# ============================================================
@router.message(F.text == BTN_LOCK)
async def lock_section(message: Message, state: FSMContext):
    if await is_admin(message.from_user.id):
        await message.answer("👑 <b>Admin panel</b>", reply_markup=admin_kb())
        return
    await state.set_state(AdminStates.waiting_password)
    await message.answer("🔒 <b>Maxfiy qulf</b>\n\n🔑 Parolni kiriting:",
                         reply_markup=cancel_kb())

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if await is_admin(message.from_user.id):
        await message.answer("👑 <b>Admin panel</b>", reply_markup=admin_kb())
        return
    await state.set_state(AdminStates.waiting_password)
    await message.answer("🔒 Parolni kiriting:", reply_markup=cancel_kb())

@router.message(AdminStates.waiting_password)
async def check_password(message: Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        await state.clear()
        await add_admin(message.from_user.id)
        await message.answer("✅ <b>Parol to'g'ri!</b>", reply_markup=admin_kb())
    else:
        await message.answer("❌ <b>Parol noto'g'ri!</b>\n\nQaytadan:")

@router.callback_query(F.data == "admin_cancel")
async def admin_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("🏠 Asosiy menyu:", reply_markup=await main_menu_kb())
    await call.answer()

@router.callback_query(F.data == "back_admin")
async def back_admin(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    try:
        await call.message.edit_text("👑 <b>Admin panel</b>", reply_markup=admin_kb())
    except Exception:
        await call.message.answer("👑 <b>Admin panel</b>", reply_markup=admin_kb())
    await call.answer()

@router.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("🏠 Asosiy menyu", reply_markup=await main_menu_kb())
    await call.answer()

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()

# ============================================================
#                    📊 ADMIN: STATISTIKA
# ============================================================
@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    s = await get_full_stats()
    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b>\n"
        f"🎬 Filmlar: <b>{s['movies']}</b>\n"
        f"📂 Kategoriyalar: <b>{s['categories']}</b>\n"
        f"📢 Kanallar: <b>{s['channels']}</b>\n"
        f"👁 Jami ko'rishlar: <b>{s['views']}</b>")
    try:
        await call.message.edit_text(text, reply_markup=back_kb("back_admin"))
    except Exception:
        await call.message.answer(text, reply_markup=back_kb("back_admin"))
    await call.answer()

# ============================================================
#                    🎬 ADMIN: FILMLAR
# ============================================================
@router.callback_query(F.data == "admin_movies")
async def admin_movies(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    kb = await admin_movies_list_kb(0)
    try:
        await call.message.edit_text("🎬 <b>Filmlar</b>", reply_markup=kb)
    except Exception:
        await call.message.answer("🎬 <b>Filmlar</b>", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.regexp(r"^ampg_\d+$"))
async def admin_movies_page(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    page = int(call.data.replace("ampg_", ""))
    kb = await admin_movies_list_kb(page)
    try:
        await call.message.edit_text("🎬 <b>Filmlar</b>", reply_markup=kb)
    except Exception:
        await call.message.answer("🎬 <b>Filmlar</b>", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.regexp(r"^amov_\d+$"))
async def admin_movie_view(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    mid = int(call.data.replace("amov_", ""))
    await admin_movie_view_by_id(call, mid)
    await call.answer()

@router.callback_query(F.data == "add_movie_start")
async def add_movie_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    next_code = await get_next_movie_code()
    await state.clear()
    await state.set_state(AdminStates.add_movie_code)
    await call.message.answer(
        f"➕ <b>Yangi film</b>\n\n"
        f"1️⃣ Kod kiriting (yoki <code>avto</code> — keyingi bo'sh kod: <b>{next_code}</b>):",
        reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminStates.add_movie_code, F.text)
async def add_movie_code(message: Message, state: FSMContext):
    txt = message.text.strip().lower()
    if txt == "avto":
        code = await get_next_movie_code()
    else:
        try:
            code = int(txt)
        except ValueError:
            await message.answer("❗ Faqat raqam yoki 'avto':")
            return
    if await code_exists(code):
        await message.answer("❌ Bu kod band. Boshqa kiriting:")
        return
    await state.update_data(m_code=code)
    await state.set_state(AdminStates.add_movie_name)
    await message.answer("2️⃣ Nomi:")

@router.message(AdminStates.add_movie_name, F.text)
async def add_movie_name(message: Message, state: FSMContext):
    await state.update_data(m_name=message.text.strip())
    await state.set_state(AdminStates.add_movie_desc)
    await message.answer("3️⃣ Tavsif (yoki 'yoq'):")

@router.message(AdminStates.add_movie_desc, F.text)
async def add_movie_desc(message: Message, state: FSMContext):
    d = "" if message.text.strip().lower() == "yoq" else message.text.strip()
    await state.update_data(m_desc=d)
    cats = await get_categories()
    if not cats:
        await state.update_data(m_cat=None)
        await state.set_state(AdminStates.add_movie_year)
        await message.answer("4️⃣ Kategoriya yo'q. Yil (yoki 'yoq'):")
        return
    builder = InlineKeyboardBuilder()
    for c in cats:
        builder.button(text=f"{c[2]} {c[1]}", callback_data=f"setcat_{c[0]}")
    builder.button(text="⏭ O'tkazib yuborish", callback_data="setcat_skip")
    builder.adjust(2)
    await state.set_state(AdminStates.add_movie_category)
    await message.answer("4️⃣ Kategoriyani tanlang:",
                         reply_markup=builder.as_markup())

@router.callback_query(AdminStates.add_movie_category, F.data.regexp(r"^setcat_"))
async def add_movie_cat(call: CallbackQuery, state: FSMContext):
    val = call.data.replace("setcat_", "")
    if val == "skip":
        await state.update_data(m_cat=None)
    else:
        await state.update_data(m_cat=int(val))
    await state.set_state(AdminStates.add_movie_year)
    try:
        await call.message.edit_text("5️⃣ Yil (yoki 'yoq'):")
    except Exception:
        await call.message.answer("5️⃣ Yil (yoki 'yoq'):")
    await call.answer()

@router.message(AdminStates.add_movie_year, F.text)
async def add_movie_year(message: Message, state: FSMContext):
    v = "" if message.text.strip().lower() == "yoq" else message.text.strip()
    await state.update_data(m_year=v)
    await state.set_state(AdminStates.add_movie_country)
    await message.answer("6️⃣ Davlat (yoki 'yoq'):")

@router.message(AdminStates.add_movie_country, F.text)
async def add_movie_country(message: Message, state: FSMContext):
    v = "" if message.text.strip().lower() == "yoq" else message.text.strip()
    await state.update_data(m_country=v)
    await state.set_state(AdminStates.add_movie_language)
    await message.answer("7️⃣ Til (yoki 'yoq'):")

@router.message(AdminStates.add_movie_language, F.text)
async def add_movie_language(message: Message, state: FSMContext):
    v = "" if message.text.strip().lower() == "yoq" else message.text.strip()
    await state.update_data(m_language=v)
    await state.set_state(AdminStates.add_movie_quality)
    await message.answer("8️⃣ Sifat (HD, 4K, ... yoki 'yoq'):")

@router.message(AdminStates.add_movie_quality, F.text)
async def add_movie_quality(message: Message, state: FSMContext):
    v = "HD" if message.text.strip().lower() == "yoq" else message.text.strip()
    await state.update_data(m_quality=v)
    await state.set_state(AdminStates.add_movie_duration)
    await message.answer("9️⃣ Davomiylik (masalan 1s 30d yoki 'yoq'):")

@router.message(AdminStates.add_movie_duration, F.text)
async def add_movie_duration(message: Message, state: FSMContext):
    v = "" if message.text.strip().lower() == "yoq" else message.text.strip()
    await state.update_data(m_duration=v)
    await state.set_state(AdminStates.add_movie_poster)
    await message.answer("🔟 Poster rasmini yuboring (yoki 'yoq'):")

@router.message(AdminStates.add_movie_poster, F.photo)
async def add_movie_poster(message: Message, state: FSMContext):
    await state.update_data(m_poster=message.photo[-1].file_id)
    await state.set_state(AdminStates.add_movie_video)
    await message.answer("1️⃣1️⃣ Endi videoni yuboring (yoki forward qiling):")

@router.message(AdminStates.add_movie_poster, F.text)
async def add_movie_poster_text(message: Message, state: FSMContext):
    if message.text.strip().lower() == "yoq":
        await state.update_data(m_poster=None)
        await state.set_state(AdminStates.add_movie_video)
        await message.answer("1️⃣1️⃣ Endi videoni yuboring:")
    else:
        await message.answer("❗ Rasm yuboring yoki 'yoq':")

@router.message(AdminStates.add_movie_video, F.video)
async def add_movie_video(message: Message, state: FSMContext):
    await save_movie(message, state, message.video.file_id)

@router.message(AdminStates.add_movie_video, F.document)
async def add_movie_video_doc(message: Message, state: FSMContext):
    doc = message.document
    if doc.mime_type and doc.mime_type.startswith("video"):
        await save_movie(message, state, doc.file_id)
    else:
        await message.answer("❗ Iltimos, video yuboring.")

async def save_movie(message: Message, state: FSMContext, file_id: str):
    data = await state.get_data()
    movie_data = {
        'code': data['m_code'],
        'name': data['m_name'],
        'description': data.get('m_desc', ''),
        'category_id': data.get('m_cat'),
        'year': data.get('m_year', ''),
        'country': data.get('m_country', ''),
        'language': data.get('m_language', ''),
        'quality': data.get('m_quality', 'HD'),
        'duration': data.get('m_duration', ''),
        'poster_id': data.get('m_poster'),
        'file_id': file_id,
        'channel_id': MOVIE_CHANNEL_ID,
    }
    await add_movie(movie_data)
    await state.clear()
    await message.answer(
        f"✅ <b>Film qo'shildi!</b>\n\n"
        f"🔢 Kod: <code>{movie_data['code']}</code>\n"
        f"🎬 {movie_data['name']}",
        reply_markup=back_kb("admin_movies"))

# ---------- FILM TAHRIRLASH ----------
@router.callback_query(F.data.regexp(r"^emov_(name|code|desc|year|country|language|quality|duration|poster|video|cat)_\d+$"))
async def edit_movie_field(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split("_")
    field = parts[1]
    mid = int(parts[2])

    if field == "cat":
        cats = await get_categories()
        if not cats:
            await call.answer("Kategoriyalar yo'q", show_alert=True)
            return
        builder = InlineKeyboardBuilder()
        for c in cats:
            builder.button(text=f"{c[2]} {c[1]}", callback_data=f"emovsetcat_{mid}_{c[0]}")
        builder.button(text="⏭ O'tkazib yuborish", callback_data=f"emovsetcat_{mid}_skip")
        builder.button(text="⬅️ Orqaga", callback_data=f"amov_{mid}")
        builder.adjust(2)
        try:
            await call.message.edit_text("📂 Kategoriyani tanlang:",
                                         reply_markup=builder.as_markup())
        except Exception:
            await call.message.answer("📂 Kategoriyani tanlang:",
                                      reply_markup=builder.as_markup())
        await call.answer()
        return

    await state.update_data(edit_mid=mid, edit_field=field)
    await state.set_state(AdminStates.edit_movie_value)
    labels = {
        "name": "📝 Yangi nom:",
        "code": "🔢 Yangi kod (raqam):",
        "desc": "📝 Yangi tavsif:",
        "year": "📅 Yangi yil:",
        "country": "🌍 Yangi davlat:",
        "language": "🗣 Yangi til:",
        "quality": "🎞 Yangi sifat:",
        "duration": "⏱ Yangi davomiylik:",
        "poster": "🖼 Yangi poster (rasm):",
        "video": "🎥 Yangi video yuboring:",
    }
    try:
        await call.message.edit_text(labels.get(field, "Yangi qiymat:"),
                                     reply_markup=cancel_kb())
    except Exception:
        await call.message.answer(labels.get(field, "Yangi qiymat:"),
                                  reply_markup=cancel_kb())
    await call.answer()

@router.callback_query(F.data.regexp(r"^emovsetcat_\d+_"))
async def edit_movie_setcat(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    rest = call.data.replace("emovsetcat_", "")
    mid_s, cat_s = rest.split("_", 1)
    mid = int(mid_s)
    val = None if cat_s == "skip" else int(cat_s)
    await update_movie(mid, "category_id", val)
    await call.answer("✅ O'zgartirildi")
    await admin_movie_view_by_id(call, mid)

@router.message(AdminStates.edit_movie_value, F.photo)
async def edit_movie_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "poster":
        await message.answer("❗ Faqat matn/raqam kiriting.")
        return
    await update_movie(data['edit_mid'], "poster_id", message.photo[-1].file_id)
    await state.clear()
    await message.answer("✅ Poster yangilandi!",
                         reply_markup=back_kb("admin_movies"))

@router.message(AdminStates.edit_movie_value, F.video)
async def edit_movie_video(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "video":
        await message.answer("❗ Faqat matn kiriting.")
        return
    await update_movie(data['edit_mid'], "file_id", message.video.file_id)
    await state.clear()
    await message.answer("✅ Video yangilandi!",
                         reply_markup=back_kb("admin_movies"))

@router.message(AdminStates.edit_movie_value, F.document)
async def edit_movie_doc(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "video":
        await message.answer("❗ Faqat matn kiriting.")
        return
    doc = message.document
    if doc.mime_type and doc.mime_type.startswith("video"):
        await update_movie(data['edit_mid'], "file_id", doc.file_id)
        await state.clear()
        await message.answer("✅ Video yangilandi!",
                             reply_markup=back_kb("admin_movies"))
    else:
        await message.answer("❗ Video yuboring.")

@router.message(AdminStates.edit_movie_value, F.text)
async def edit_movie_save(message: Message, state: FSMContext):
    data = await state.get_data()
    mid = data['edit_mid']
    field = data['edit_field']
    val = message.text.strip()
    if val.lower() == "yoq":
        val = ""
    if field == "code":
        try:
            c = int(val)
        except ValueError:
            await message.answer("❗ Faqat raqam:")
            return
        if await code_exists(c):
            await message.answer("❌ Bu kod band:")
            return
        await update_movie(mid, "code", c)
    elif field in {"name", "year", "country", "language", "quality", "duration"}:
        await update_movie(mid, field, val)
    elif field == "desc":
        await update_movie(mid, "description", val)
    elif field in {"poster", "video"}:
        await message.answer("❗ Rasm/video yuboring.")
        return
    await state.clear()
    await message.answer("✅ Tahrirlandi!", reply_markup=back_kb("admin_movies"))

@router.callback_query(F.data.regexp(r"^emov_active_\d+$"))
async def edit_movie_active(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    mid = int(call.data.replace("emov_active_", ""))
    m = await get_movie(mid)
    if not m:
        await call.answer("❌", show_alert=True)
        return
    new = 0 if m[M_ACTIVE] else 1
    await update_movie(mid, "is_active", new)
    await call.answer("✅ O'zgartirildi")
    await admin_movie_view_by_id(call, mid)

@router.callback_query(F.data.regexp(r"^emov_del_\d+$"))
async def edit_movie_del(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    mid = int(call.data.replace("emov_del_", ""))
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, o'chirish", callback_data=f"emov_delok_{mid}")
    builder.button(text="❌ Yo'q", callback_data=f"amov_{mid}")
    builder.adjust(2)
    try:
        await call.message.edit_text("🗑 Rostdan o'chirmoqchimisiz?",
                                     reply_markup=builder.as_markup())
    except Exception:
        await call.message.answer("Rostdan?", reply_markup=builder.as_markup())
    await call.answer()

@router.callback_query(F.data.regexp(r"^emov_delok_\d+$"))
async def edit_movie_del_ok(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    mid = int(call.data.replace("emov_delok_", ""))
    await delete_movie(mid)
    await call.answer("🗑 O'chirildi")
    try:
        await call.message.edit_text("✅ Film o'chirildi.",
                                     reply_markup=back_kb("admin_movies"))
    except Exception:
        await call.message.answer("✅ O'chirildi.",
                                  reply_markup=back_kb("admin_movies"))

async def admin_movie_view_by_id(call: CallbackQuery, mid):
    m = await get_movie(mid)
    if not m:
        await call.answer("❌ Topilmadi", show_alert=True)
        return
    cat = await get_category(m[M_CAT])
    st = "✅ Faol" if m[M_ACTIVE] else "🚫 Nofaol"
    avg, cnt = await get_avg_rating(mid)
    text = (
        f"🎬 <b>{m[M_NAME]}</b>\n\n"
        f"🔢 Kod: <code>{m[M_CODE]}</code>\n"
        f"📂 Kategoriya: {cat[2] + ' ' + cat[1] if cat else '—'}\n"
        f"📅 Yil: {m[M_YEAR] or '—'}\n"
        f"🌍 Davlat: {m[M_COUNTRY] or '—'}\n"
        f"🗣 Til: {m[M_LANG] or '—'}\n"
        f"🎞 Sifat: {m[M_QUALITY] or '—'}\n"
        f"⏱ Davomiylik: {m[M_DURATION] or '—'}\n"
        f"⭐ Reyting: {avg}/5 ({cnt})\n"
        f"👁 Ko'rishlar: {m[M_VIEWS]}\n"
        f"📊 {st}\n"
        f"🆔 <code>{mid}</code>\n\n"
        f"📝 {m[M_DESC] or '—'}")
    kb = admin_movie_detail_kb(mid)
    if m[M_POSTER]:
        try:
            await call.message.delete()
            await call.message.answer_photo(m[M_POSTER], caption=text, reply_markup=kb)
        except Exception:
            await call.message.answer(text, reply_markup=kb)
    else:
        try:
            await call.message.edit_text(text, reply_markup=kb)
        except Exception:
            await call.message.answer(text, reply_markup=kb)

# ============================================================
#                    📂 ADMIN: KATEGORIYALAR
# ============================================================
@router.callback_query(F.data == "admin_categories")
async def admin_categories(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    kb = await admin_categories_kb()
    try:
        await call.message.edit_text("📂 <b>Kategoriyalar</b>", reply_markup=kb)
    except Exception:
        await call.message.answer("📂 <b>Kategoriyalar</b>", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "add_cat")
async def add_cat_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(AdminStates.add_cat_name)
    try:
        await call.message.edit_text("➕ 1️⃣ Kategoriya nomini kiriting:",
                                     reply_markup=cancel_kb())
    except Exception:
        await call.message.answer("1️⃣ Nomini kiriting:", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminStates.add_cat_name, F.text)
async def add_cat_name(message: Message, state: FSMContext):
    await state.update_data(cat_name=message.text.strip())
    await state.set_state(AdminStates.add_cat_emoji)
    await message.answer("2️⃣ Emoji kiriting (masalan 📁):")

@router.message(AdminStates.add_cat_emoji, F.text)
async def add_cat_emoji(message: Message, state: FSMContext):
    data = await state.get_data()
    await add_category(data['cat_name'], message.text.strip())
    await state.clear()
    await message.answer("✅ Kategoriya qo'shildi!",
                         reply_markup=await admin_categories_kb())

@router.callback_query(F.data.regexp(r"^acat_\d+$"))
async def admin_cat_view(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    cid = int(call.data.replace("acat_", ""))
    c = await get_category(cid)
    if not c:
        await call.answer("❌", show_alert=True)
        return
    cnt = await movies_count_in_category(cid)
    try:
        await call.message.edit_text(
            f"{c[2]} <b>{c[1]}</b>\n\n🎬 Filmlar: <b>{cnt}</b>",
            reply_markup=category_manage_kb(cid))
    except Exception:
        await call.message.answer(f"{c[2]} {c[1]}", reply_markup=category_manage_kb(cid))
    await call.answer()

@router.callback_query(F.data.regexp(r"^ecat_(name|emoji)_\d+$"))
async def edit_cat_field(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split("_")
    field = parts[1]
    cid = int(parts[2])
    await state.update_data(edit_cat_id=cid, edit_cat_field=field)
    await state.set_state(AdminStates.edit_cat_value)
    label = "📝 Yangi nom:" if field == "name" else "😀 Yangi emoji:"
    try:
        await call.message.edit_text(label, reply_markup=cancel_kb())
    except Exception:
        await call.message.answer(label, reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminStates.edit_cat_value, F.text)
async def edit_cat_save(message: Message, state: FSMContext):
    data = await state.get_data()
    if 'edit_chan_id' in data:
        field_map = {"name": "name", "link": "link", "id": "channel_id"}
        await update_channel(data['edit_chan_id'],
                             field_map[data['edit_chan_field']],
                             message.text.strip())
        await state.clear()
        await message.answer("✅ Tahrirlandi!", reply_markup=back_kb("admin_channels"))
        return
    if 'edit_cat_id' in data:
        await update_category(data['edit_cat_id'], data['edit_cat_field'],
                              message.text.strip())
        await state.clear()
        await message.answer("✅ Tahrirlandi!", reply_markup=back_kb("admin_categories"))
        return
    await state.clear()
    await message.answer("✅")

@router.callback_query(F.data.regexp(r"^delcat_\d+$"))
async def del_cat(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    cid = int(call.data.replace("delcat_", ""))
    await delete_category(cid)
    await call.answer("🗑 O'chirildi")
    kb = await admin_categories_kb()
    try:
        await call.message.edit_text("📂 <b>Kategoriyalar</b>", reply_markup=kb)
    except Exception:
        await call.message.answer("📂 Kategoriyalar", reply_markup=kb)

# ============================================================
#                    📢 ADMIN: KANALLAR
# ============================================================
@router.callback_query(F.data == "admin_channels")
async def admin_channels(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    kb = await admin_channels_kb()
    try:
        await call.message.edit_text("📢 <b>Majburiy kanallar</b>", reply_markup=kb)
    except Exception:
        await call.message.answer("📢 <b>Majburiy kanallar</b>", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(AdminStates.add_channel_name)
    try:
        await call.message.edit_text("➕ 1️⃣ Kanal nomi:", reply_markup=cancel_kb())
    except Exception:
        await call.message.answer("1️⃣ Kanal nomi:", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminStates.add_channel_name, F.text)
async def add_channel_name(message: Message, state: FSMContext):
    await state.update_data(ch_name=message.text.strip())
    await state.set_state(AdminStates.add_channel_link)
    await message.answer("2️⃣ Kanal linki (masalan https://t.me/kanal):")

@router.message(AdminStates.add_channel_link, F.text)
async def add_channel_link(message: Message, state: FSMContext):
    await state.update_data(ch_link=message.text.strip())
    await state.set_state(AdminStates.add_channel_id)
    await message.answer("3️⃣ Kanal ID (masalan -1001234567890):")

@router.message(AdminStates.add_channel_id, F.text)
async def add_channel_id(message: Message, state: FSMContext):
    data = await state.get_data()
    await add_channel(data['ch_name'], data['ch_link'], message.text.strip())
    await state.clear()
    kb = await admin_channels_kb()
    await message.answer("✅ Kanal qo'shildi!", reply_markup=kb)

@router.callback_query(F.data.regexp(r"^achan_\d+$"))
async def admin_chan_view(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    cid = int(call.data.replace("achan_", ""))
    c = await get_channel(cid)
    if not c:
        await call.answer("❌", show_alert=True)
        return
    st = "✅ Faol" if c[4] else "🚫 Nofaol"
    text = (f"📢 <b>{c[1]}</b>\n\n"
            f"🔗 {c[2]}\n🆔 <code>{c[3]}</code>\n📊 {st}")
    try:
        await call.message.edit_text(text, reply_markup=channel_manage_kb(cid))
    except Exception:
        await call.message.answer(text, reply_markup=channel_manage_kb(cid))
    await call.answer()

@router.callback_query(F.data.regexp(r"^echan_(name|link|id)_\d+$"))
async def edit_chan_field(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split("_")
    field = parts[1]
    cid = int(parts[2])
    await state.update_data(edit_chan_id=cid, edit_chan_field=field)
    await state.set_state(AdminStates.edit_cat_value)
    labels = {"name": "📝 Yangi nom:", "link": "🔗 Yangi link:", "id": "🆔 Yangi ID:"}
    try:
        await call.message.edit_text(labels[field], reply_markup=cancel_kb())
    except Exception:
        await call.message.answer(labels[field], reply_markup=cancel_kb())
    await call.answer()

@router.callback_query(F.data.regexp(r"^echan_active_\d+$"))
async def edit_chan_active(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    cid = int(call.data.replace("echan_active_", ""))
    c = await get_channel(cid)
    if not c:
        await call.answer("❌", show_alert=True)
        return
    await update_channel(cid, "is_active", 0 if c[4] else 1)
    await call.answer("✅ O'zgartirildi")
    c = await get_channel(cid)
    st = "✅ Faol" if c[4] else "🚫 Nofaol"
    text = (f"📢 <b>{c[1]}</b>\n\n"
            f"🔗 {c[2]}\n🆔 <code>{c[3]}</code>\n📊 {st}")
    try:
        await call.message.edit_text(text, reply_markup=channel_manage_kb(cid))
    except Exception:
        pass

@router.callback_query(F.data.regexp(r"^delchan_\d+$"))
async def del_chan(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    cid = int(call.data.replace("delchan_", ""))
    await delete_channel(cid)
    await call.answer("🗑 O'chirildi")
    kb = await admin_channels_kb()
    try:
        await call.message.edit_text("📢 <b>Kanallar</b>", reply_markup=kb)
    except Exception:
        await call.message.answer("📢 Kanallar", reply_markup=kb)

# ============================================================
#                    📢 ADMIN: BROADCAST
# ============================================================
@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_broadcast)
    try:
        await call.message.edit_text("📢 Xabarni yuboring:", reply_markup=cancel_kb())
    except Exception:
        await call.message.answer("📢 Xabarni yuboring:", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminStates.waiting_broadcast)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    users = await get_all_users()
    total = len(users)
    if total == 0:
        await message.answer("Foydalanuvchilar yo'q.")
        return
    success = failed = 0
    status = await message.answer(f"⏳ 0/{total}")
    for i, uid in enumerate(users, 1):
        try:
            await message.copy_to(uid)
            success += 1
        except Exception:
            failed += 1
        if i % 20 == 0 or i == total:
            try:
                await status.edit_text(f"⏳ {i}/{total}")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    try:
        await status.edit_text(
            f"✅ Yakunlandi!\n\n✔️ {success}\n❌ {failed}\n👥 {total}",
            reply_markup=back_kb("back_admin"))
    except Exception:
        pass

# ============================================================
#                    👤 ADMIN: ADMINLAR
# ============================================================
@router.callback_query(F.data == "admin_admins")
async def admin_admins(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    admins = await get_all_admins()
    text = "👤 <b>Adminlar</b>\n\n"
    for i, a in enumerate(admins, 1):
        text += f"{i}. <code>{a}</code>\n"
    text += f"\n👑 Super: <code>{SUPER_ADMIN_ID}</code>"
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Qo'shish", callback_data="adm_add_admin")
    builder.button(text="➖ O'chirish", callback_data="adm_remove_admin")
    builder.button(text="⬅️ Orqaga", callback_data="back_admin")
    builder.adjust(2, 1)
    try:
        await call.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await call.message.answer(text, reply_markup=builder.as_markup())
    await call.answer()

@router.callback_query(F.data == "adm_add_admin")
async def adm_add_admin(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != SUPER_ADMIN_ID:
        await call.answer("⛔ Faqat super admin", show_alert=True)
        return
    await state.set_state(AdminStates.add_admin_id)
    try:
        await call.message.edit_text("➕ Admin ID:", reply_markup=cancel_kb())
    except Exception:
        await call.message.answer("➕ Admin ID:", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminStates.add_admin_id, F.text)
async def adm_add_admin_save(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID:")
        return
    await add_admin(uid)
    await state.clear()
    await message.answer(f"✅ Qo'shildi: <code>{uid}</code>",
                         reply_markup=back_kb("admin_admins"))

@router.callback_query(F.data == "adm_remove_admin")
async def adm_remove_admin(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != SUPER_ADMIN_ID:
        await call.answer("⛔ Faqat super admin", show_alert=True)
        return
    await state.set_state(AdminStates.remove_admin_id)
    try:
        await call.message.edit_text("➖ Admin ID:", reply_markup=cancel_kb())
    except Exception:
        await call.message.answer("➖ Admin ID:", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminStates.remove_admin_id, F.text)
async def adm_remove_admin_save(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID:")
        return
    await remove_admin(uid)
    await state.clear()
    await message.answer(f"✅ O'chirildi: <code>{uid}</code>",
                         reply_markup=back_kb("admin_admins"))

# ============================================================
#           🌐 KEEP-ALIVE HTTP SERVER
# ============================================================
async def health_handler(request: web.Request) -> web.Response:
    idle = int(time.time() - LAST_ACTIVITY)
    return web.Response(
        text=f"OK | idle={idle}s | uptime={int(time.time() - BOT_STARTED_AT)}s",
        status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    logger.info(f"🌐 HTTP server {PORT}-portda ishga tushdi")

async def self_ping_loop(bot: Bot):
    global LAST_ACTIVITY  # <--- SHU YERGA TO'G'RI QO'YILDI!
    
    while True:
        await asyncio.sleep(PING_INTERVAL)

        # 1) Self-ping
        if RENDER_URL:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(RENDER_URL, timeout=10) as r:
                        logger.info(f"🌐 Self-ping: {r.status}")
            except Exception as e:
                logger.warning(f"⚠️ Self-ping xato: {e}")

        # 2) Inactivity check
        idle = time.time() - LAST_ACTIVITY
        if idle >= PING_INTERVAL:
            try:
                await bot.send_message(
                    INACTIVITY_NOTIFY_ID,
                    "🔔 <b>15 daqiqa ichida hech kim botdan foydalanmadi.</b>\n"
                    f"⏱ Oxirgi aktivlik: {int(idle // 60)} daqiqa oldin\n"
                    f"🕐 Bot ishlayapti: {int((time.time() - BOT_STARTED_AT) // 60)} daqiqa"
                )
                logger.info("📨 Inactivity xabari yuborildi")
                
                LAST_ACTIVITY = time.time()
            except Exception as e:
                logger.warning(f"⚠️ Inactivity xabar xato: {e}")

# ============================================================
#                    🚀 MAIN
# ============================================================
async def main():
    if sys.version_info < (3, 8):
        logger.error("❌ Python 3.8+ kerak!")
        return

    await init_db()

    if PROXY_URL:
        logger.info(f"🌐 Proxy ishlatilmoqda: {PROXY_URL}")
        session = AiohttpSession(proxy=PROXY_URL)
        bot = Bot(
            token=BOT_TOKEN,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    else:
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

    dp = Dispatcher()
    dp.update.outer_middleware(ActivityMiddleware())
    dp.include_router(router)

    await start_web_server()
    ping_task = asyncio.create_task(self_ping_loop(bot))

    logger.info("🚀 Bot ishga tushmoqda...")
    logger.info(f"🌐 Render URL: {RENDER_URL or '(yoq)'}")

    retry_delay = 5
    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            me = await bot.get_me()
            logger.info(f"✅ Bot: @{me.username}")
            logger.info(f"📢 Kanal: {MOVIE_CHANNEL_ID}")
            await dp.start_polling(bot)
            break
        except TelegramNetworkError as e:
            logger.warning(f"⚠️ Tarmoq xatosi: {e}")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        except (KeyboardInterrupt, SystemExit):
            logger.info("🛑 To'xtatildi.")
            break
        except Exception as e:
            logger.error(f"❌ Kutilmagan xato: {e}")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        finally:
            ping_task.cancel()
            try:
                await bot.session.close()
            except Exception:
                pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 To'xtatildi.")