# -*- coding: utf-8 -*-
"""
=================================================================
🤖 ULTIMATE HOSTING BOT - TERMINAL ACCESS (OWNER ONLY)
=================================================================
"""

import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import logging
import threading
import re
import sys
import atexit
import requests
import platform
import math
import socket
import glob
import shlex
from collections import defaultdict
from flask import Flask, jsonify

# ====================== FLASK KEEP ALIVE ======================
app = Flask('')

@app.route('/')
def home(): return "🤖 ULTIMATE HOSTING BOT - ONLINE"

@app.route('/health')
def health():
    return jsonify({
        "status": "online",
        "users": len(active_users),
        "running_scripts": len(bot_scripts),
        "uptime": get_uptime()
    })

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)

def keep_alive():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

# ====================== CONFIGURATION ======================
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OWNER_ID = 6480827931
ADMIN_ID = 8841730104
YOUR_USERNAME = 'https://t.me/NEXRO12H'
UPDATE_CHANNEL = 'https://t.me/NEXRO12H'

# AI Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# Limits
FREE_USER_LIMIT = 2
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join('/data', 'upload_bots') if os.path.exists('/data') else os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join('/data', 'inf') if os.path.exists('/data') else os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')
BACKUP_DIR = os.path.join(IROTECH_DIR, 'backups')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True, mode=0o755)
os.makedirs(IROTECH_DIR, exist_ok=True, mode=0o755)
os.makedirs(BACKUP_DIR, exist_ok=True, mode=0o755)

BOT_START_TIME = datetime.now()
# Docker is the preferred isolation boundary. If Docker is unavailable, the bot can
# use a restricted subprocess fallback; set REQUIRE_DOCKER_SANDBOX=1 to fail closed.
REQUIRE_DOCKER_SANDBOX = os.environ.get("REQUIRE_DOCKER_SANDBOX", "0").lower() in ("1", "true", "yes")
BOT_MEMORY_LIMIT = os.environ.get("BOT_MEMORY_LIMIT", "512m")
BOT_CPU_LIMIT = os.environ.get("BOT_CPU_LIMIT", "1.0")
BOT_PIDS_LIMIT = int(os.environ.get("BOT_PIDS_LIMIT", "128"))
MAX_AUTO_RESTARTS = max(0, int(os.environ.get("MAX_AUTO_RESTARTS", "3")))
# Missing-dependency repairs have their own bounded retry budget and do not consume
# the normal crash-restart allowance.
MAX_DEPENDENCY_RETRIES = max(1, int(os.environ.get("MAX_DEPENDENCY_RETRIES", "10")))
AUTO_RESTART_DELAY = max(1, int(os.environ.get("AUTO_RESTART_DELAY", "10")))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
DOCKER_BIN = shutil.which("docker")

def get_uptime():
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

# ====================== LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(IROTECH_DIR, 'bot.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ====================== BOT INIT ======================
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required. Set your NEW Telegram bot token before starting.")
bot = telebot.TeleBot(TOKEN)

# ====================== DATA STRUCTURES ======================
bot_scripts = {}
BOT_SCRIPTS_LOCK = threading.RLock()
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {OWNER_ID, ADMIN_ID}
banned_users = set()
whitelist_users = set()
user_limits = {}
bot_locked = False
mandatory_channels = {}
pending_zip_files = {}
terminal_mode_users = set()  # Only OWNER can use terminal
referrals = defaultdict(set)

FILE_STATUS_PENDING = "pending"
FILE_STATUS_APPROVED = "approved"
FILE_STATUS_REJECTED = "rejected"
FILE_STATUS_AUTO_APPROVED = "auto_approved"

TERMINAL_BLACKLIST = [
    'rm -rf /', 'mkfs', 'dd if=', 'shutdown', 'reboot', 'halt',
    'init 0', 'init 6', 'fork bomb', 'chmod 777 /', 'mv / ',
    '>/dev/sda', 'format c:', 'sudo', 'su -', 'passwd', 'chown',
    'chattr', 'dd if=/dev/zero', 'dd of=/dev/sda', 'kill -9',
    'pkill', 'killall', 'systemctl stop', 'service stop'
]

# ====================== BUTTON LAYOUTS ======================
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "⏱ Uptime"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner", "🤖 VIP AI"],
    ["📦 Manual Install", "📝 My Notes"],
    ["⏰ Reminders", "👥 Referral"],
    ["🆘 Help"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel", "🚀 Ping"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Run All Code"],
    ["👑 Admin Panel", "📞 Contact Owner"],
    ["🤖 VIP AI", "⏱ Uptime"],
    ["📋 All Codes Status", "👥 Whitelist Users"],
    ["💻 Terminal", "📁 File Manager"],
    ["📢 Channel Add", "👥 User Management"],
    ["⚙️ Settings", "💾 Backup"],
    ["🌐 Network Info", "📊 System Monitor"],
    ["🔧 Process Manager", "🆘 Help"]
]

# ====================== DATABASE ======================
DB_LOCK = threading.Lock()

def init_db():
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, expiry TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS user_files (user_id INTEGER, file_name TEXT, file_type TEXT, PRIMARY KEY (user_id, file_name))')
        c.execute('CREATE TABLE IF NOT EXISTS active_users (user_id INTEGER PRIMARY KEY, join_date TEXT, last_seen TEXT, username TEXT, first_name TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_date TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, ban_date TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS user_limits (user_id INTEGER PRIMARY KEY, file_limit INTEGER, set_by INTEGER, set_date TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS mandatory_channels (channel_id TEXT PRIMARY KEY, channel_username TEXT, channel_name TEXT, added_by INTEGER, added_date TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS install_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, module_name TEXT, package_name TEXT, status TEXT, log TEXT, install_date TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS file_approvals (user_id INTEGER, file_name TEXT, status TEXT, reviewed_by INTEGER, review_time TEXT, file_type TEXT, uploaded_time TEXT, PRIMARY KEY (user_id, file_name))')
        c.execute('CREATE TABLE IF NOT EXISTS whitelist_users (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_time TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS user_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, note TEXT, created_date TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, reminder_text TEXT, remind_at TEXT, created_date TEXT, is_sent INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS referrals (user_id INTEGER PRIMARY KEY, referred_by INTEGER, referred_count INTEGER DEFAULT 0, join_date TEXT)')
        c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)', (OWNER_ID, OWNER_ID, datetime.now().isoformat()))
        c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)', (ADMIN_ID, OWNER_ID, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Init Error: {e}")

def load_data():
    global admin_ids, whitelist_users
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for uid, exp in c.fetchall():
            try: user_subscriptions[uid] = {'expiry': datetime.fromisoformat(exp)}
            except: pass
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for uid, fn, ft in c.fetchall():
            if uid not in user_files: user_files[uid] = []
            user_files[uid].append((fn, ft))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(uid for (uid,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        for (uid,) in c.fetchall(): admin_ids.add(uid)
        admin_ids.add(OWNER_ID); admin_ids.add(ADMIN_ID)
        c.execute('SELECT user_id FROM banned_users')
        banned_users.update(uid for (uid,) in c.fetchall())
        c.execute('SELECT user_id FROM whitelist_users')
        whitelist_users.update(uid for (uid,) in c.fetchall())
        c.execute('SELECT user_id, file_limit FROM user_limits')
        for uid, fl in c.fetchall(): user_limits[uid] = fl
        c.execute('SELECT channel_id, channel_username, channel_name FROM mandatory_channels')
        for cid, cu, cn in c.fetchall(): mandatory_channels[cid] = {'username': cu, 'name': cn}
        c.execute('SELECT user_id, referred_by FROM referrals')
        for uid, rb in c.fetchall():
            if rb: referrals[rb].add(uid)
        conn.close()
    except Exception as e:
        logger.error(f"Load Data Error: {e}")

init_db()
load_data()

# ====================== HELPERS ======================
def is_admin(uid): return uid in admin_ids
def is_owner(uid): return uid == OWNER_ID
def is_user_banned(uid): return uid in banned_users
def is_user_whitelisted(uid): return uid in whitelist_users
def is_user_premium(uid): return uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now()

def format_bytes(b):
    if b == 0: return "0 B"
    s = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(b, 1024)))
    p = math.pow(1024, i)
    return f"{round(b/p, 2)} {s[i]}"

def format_duration(s):
    if s < 60: return f"{int(s)}s"
    elif s < 3600: return f"{int(s/60)}m {int(s%60)}s"
    elif s < 86400: return f"{int(s/3600)}h {int((s%3600)/60)}m"
    else: return f"{int(s/86400)}d {int((s%86400)/3600)}h"

def get_user_folder(uid):
    f = os.path.join(UPLOAD_BOTS_DIR, str(uid))
    os.makedirs(f, exist_ok=True, mode=0o755)
    return f

def get_user_file_limit(uid):
    if uid == OWNER_ID: return OWNER_LIMIT
    if is_admin(uid): return ADMIN_LIMIT
    if uid in user_limits: return user_limits[uid]
    if is_user_premium(uid): return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(uid): return len(user_files.get(uid, []))

# ====================== TELEGRAM MODULES ======================
TELEGRAM_MODULES = {
    # Import-name -> PyPI distribution-name mappings for common bot/web projects.
    'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot', 'aiogram': 'aiogram',
    'pyrogram': 'pyrogram', 'tgcrypto': 'TgCrypto', 'telethon': 'telethon',
    'bs4': 'beautifulsoup4', 'requests': 'requests', 'PIL': 'Pillow', 'pillow': 'Pillow',
    'cv2': 'opencv-python-headless', 'yaml': 'PyYAML', 'dotenv': 'python-dotenv',
    'pandas': 'pandas', 'numpy': 'numpy', 'flask': 'Flask', 'django': 'Django',
    'sqlalchemy': 'SQLAlchemy', 'psutil': 'psutil', 'aiohttp': 'aiohttp',
    'aiofiles': 'aiofiles', 'motor': 'motor', 'pymongo': 'pymongo', 'yt_dlp': 'yt-dlp',
    'youtube_dl': 'youtube_dl', 'youtube_search': 'youtube-search-python',
    'ffmpeg': 'ffmpeg-python', 'pydub': 'pydub', 'Crypto': 'pycryptodome',
    'cryptography': 'cryptography', 'dateutil': 'python-dateutil', 'pytz': 'pytz',
    'apscheduler': 'APScheduler', 'redis': 'redis', 'pymysql': 'PyMySQL',
    'mysql': 'mysql-connector-python', 'aiomysql': 'aiomysql', 'asyncpg': 'asyncpg',
    'psycopg2': 'psycopg2-binary', 'discord': 'discord.py', 'nextcord': 'nextcord',
    'disnake': 'disnake', 'wavelink': 'wavelink', 'gtts': 'gTTS', 'edge_tts': 'edge-tts',
    'speech_recognition': 'SpeechRecognition', 'googleapiclient': 'google-api-python-client',
    'firebase_admin': 'firebase-admin', 'supabase': 'supabase', 'fastapi': 'fastapi',
    'uvicorn': 'uvicorn', 'websockets': 'websockets', 'openai': 'openai', 'groq': 'groq',
    'spotipy': 'spotipy', 'lxml': 'lxml', 'jinja2': 'Jinja2', 'decouple': 'python-decouple',
}

# ====================== DATABASE OPS ======================
def add_admin_db(aid, by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)',
                     (aid, by, datetime.now().isoformat()))
            conn.commit()
            admin_ids.add(aid)
            return True
        except: return False
        finally: conn.close()

def remove_admin_db(aid):
    if aid == OWNER_ID: return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM admins WHERE user_id = ?', (aid,))
            conn.commit()
            admin_ids.discard(aid)
            return True
        except: return False
        finally: conn.close()

def add_user_to_whitelist(uid, aid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO whitelist_users (user_id, added_by, added_time) VALUES (?, ?, ?)',
                     (uid, aid, datetime.now().isoformat()))
            conn.commit()
            whitelist_users.add(uid)
            return True
        except: return False
        finally: conn.close()

def remove_user_from_whitelist(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM whitelist_users WHERE user_id = ?', (uid,))
            conn.commit()
            whitelist_users.discard(uid)
            return True
        except: return False
        finally: conn.close()

def ban_user_db(uid, reason, by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by, ban_date) VALUES (?, ?, ?, ?)',
                     (uid, reason, by, datetime.now().isoformat()))
            conn.commit()
            banned_users.add(uid)
            return True
        except: return False
        finally: conn.close()

def unban_user_db(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM banned_users WHERE user_id = ?', (uid,))
            conn.commit()
            banned_users.discard(uid)
            return True
        except: return False
        finally: conn.close()

def set_user_limit_db(uid, limit, by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_limits (user_id, file_limit, set_by, set_date) VALUES (?, ?, ?, ?)',
                     (uid, limit, by, datetime.now().isoformat()))
            conn.commit()
            user_limits[uid] = limit
            return True
        except: return False
        finally: conn.close()

def remove_user_limit_db(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_limits WHERE user_id = ?', (uid,))
            conn.commit()
            if uid in user_limits: del user_limits[uid]
            return True
        except: return False
        finally: conn.close()

def save_file_approval(uid, fn, ft, status=FILE_STATUS_PENDING, by=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO file_approvals (user_id, file_name, file_type, status, reviewed_by, review_time, uploaded_time) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (uid, fn, ft, status, by, datetime.now().isoformat() if by else None, datetime.now().isoformat()))
            conn.commit()
        except: pass
        finally: conn.close()

def get_file_status(uid, fn):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT status, file_type FROM file_approvals WHERE user_id=? AND file_name=?', (uid, fn))
            r = c.fetchone()
            if r: return {'status': r[0], 'file_type': r[1]}
            return {'status': FILE_STATUS_PENDING, 'file_type': 'unknown'}
        except: return {'status': FILE_STATUS_PENDING, 'file_type': 'unknown'}
        finally: conn.close()

def update_file_status(uid, fn, status, by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('UPDATE file_approvals SET status=?, reviewed_by=?, review_time=? WHERE user_id=? AND file_name=?',
                     (status, by, datetime.now().isoformat(), uid, fn))
            conn.commit()
            return True
        except: return False
        finally: conn.close()

def get_pending_files():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT user_id, file_name, file_type, uploaded_time FROM file_approvals WHERE status=? ORDER BY uploaded_time DESC', (FILE_STATUS_PENDING,))
            return c.fetchall()
        except: return []
        finally: conn.close()

def get_pending_files_count():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT COUNT(*) FROM file_approvals WHERE status=?', (FILE_STATUS_PENDING,))
            return c.fetchone()[0]
        except: return 0
        finally: conn.close()

def save_user_file(uid, fn, ft='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)', (uid, fn, ft))
            conn.commit()
            if uid not in user_files: user_files[uid] = []
            user_files[uid] = [(n, t) for n, t in user_files[uid] if n != fn]
            user_files[uid].append((fn, ft))
        except: pass
        finally: conn.close()

def remove_user_file_db(uid, fn):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (uid, fn))
            c.execute('DELETE FROM file_approvals WHERE user_id=? AND file_name=?', (uid, fn))
            conn.commit()
            if uid in user_files:
                user_files[uid] = [f for f in user_files[uid] if f[0] != fn]
                if not user_files[uid]: del user_files[uid]
        except: pass
        finally: conn.close()

def save_subscription(uid, exp):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (uid, exp.isoformat()))
            conn.commit()
            user_subscriptions[uid] = {'expiry': exp}
        except: pass
        finally: conn.close()

def remove_subscription_db(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (uid,))
            conn.commit()
            if uid in user_subscriptions: del user_subscriptions[uid]
        except: pass
        finally: conn.close()

def save_mandatory_channel(cid, cu, cn, by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO mandatory_channels (channel_id, channel_username, channel_name, added_by, added_date) VALUES (?, ?, ?, ?, ?)',
                     (cid, cu, cn, by, datetime.now().isoformat()))
            conn.commit()
            mandatory_channels[cid] = {'username': cu, 'name': cn}
            return True
        except: return False
        finally: conn.close()

def remove_mandatory_channel_db(cid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM mandatory_channels WHERE channel_id = ?', (cid,))
            conn.commit()
            if cid in mandatory_channels: del mandatory_channels[cid]
            return True
        except: return False
        finally: conn.close()

def save_install_log(uid, mn, pn, status, log):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO install_logs (user_id, module_name, package_name, status, log, install_date) VALUES (?, ?, ?, ?, ?, ?)',
                     (uid, mn, pn, status, log[:500], datetime.now().isoformat()))
            conn.commit()
        except: pass
        finally: conn.close()

# ====================== NOTES ======================
def save_note(uid, note):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO user_notes (user_id, note, created_date) VALUES (?, ?, ?)',
                     (uid, note, datetime.now().isoformat()))
            conn.commit()
            return True
        except: return False
        finally: conn.close()

def get_notes(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT id, note, created_date FROM user_notes WHERE user_id=? ORDER BY created_date DESC', (uid,))
            return c.fetchall()
        except: return []
        finally: conn.close()

def delete_note_db(note_id, uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_notes WHERE id = ? AND user_id = ?', (note_id, uid))
            conn.commit()
            return True
        except: return False
        finally: conn.close()

# ====================== REMINDERS ======================
def save_reminder(uid, text, remind_at):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO reminders (user_id, reminder_text, remind_at, created_date) VALUES (?, ?, ?, ?)',
                     (uid, text, remind_at.isoformat(), datetime.now().isoformat()))
            conn.commit()
            return True
        except: return False
        finally: conn.close()

def get_reminders(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT id, reminder_text, remind_at FROM reminders WHERE user_id=? AND is_sent=0 ORDER BY remind_at', (uid,))
            return c.fetchall()
        except: return []
        finally: conn.close()

def get_pending_reminders():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT id, user_id, reminder_text, remind_at FROM reminders WHERE is_sent=0 AND remind_at<=?',
                     (datetime.now().isoformat(),))
            return c.fetchall()
        except: return []
        finally: conn.close()

def mark_reminder_sent(rid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('UPDATE reminders SET is_sent=1 WHERE id=?', (rid,))
            conn.commit()
        except: pass
        finally: conn.close()

def delete_reminder_db(rid, uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM reminders WHERE id = ? AND user_id = ?', (rid, uid))
            conn.commit()
            return True
        except: return False
        finally: conn.close()

# ====================== REFERRAL ======================
def save_referral(uid, ref_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT referred_by FROM referrals WHERE user_id = ?', (uid,))
            if c.fetchone(): return
            c.execute('INSERT INTO referrals (user_id, referred_by, referred_count, join_date) VALUES (?, ?, 0, ?)',
                     (uid, ref_by, datetime.now().isoformat()))
            c.execute('UPDATE referrals SET referred_count = referred_count + 1 WHERE user_id = ?', (ref_by,))
            conn.commit()
            referrals[ref_by].add(uid)
            c.execute('SELECT referred_count FROM referrals WHERE user_id = ?', (ref_by,))
            count = c.fetchone()[0]
            if count >= 10 and ref_by not in user_subscriptions:
                exp = datetime.now() + timedelta(days=30)
                save_subscription(ref_by, exp)
                try:
                    bot.send_message(ref_by, "🎉 **Congratulations!**\nYou reached 10 referrals!\nYou got **30 days Premium**!")
                except: pass
        except Exception as e:
            logger.error(f"Referral error: {e}")
        finally: conn.close()

def get_referral_count(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT referred_count FROM referrals WHERE user_id=?', (uid,))
            r = c.fetchone()
            return r[0] if r else 0
        except: return 0
        finally: conn.close()

def get_referred_users(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT user_id FROM referrals WHERE referred_by=?', (uid,))
            return [r[0] for r in c.fetchall()]
        except: return []
        finally: conn.close()

# ====================== MANDATORY CHANNELS ======================
def is_user_member(user_id, channel_id):
    try:
        chat_member = bot.get_chat_member(channel_id, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except: return False

def check_mandatory_subscription(user_id):
    if not mandatory_channels: return True, []
    not_joined = []
    for channel_id, channel_info in mandatory_channels.items():
        if not is_user_member(user_id, channel_id):
            not_joined.append((channel_id, channel_info))
    if not_joined: return False, not_joined
    return True, []

def create_subscription_check_message(not_joined_channels):
    message = "📢 **Important: Join Our Channels First:**\n\n"
    markup = types.InlineKeyboardMarkup()
    for channel_id, channel_info in not_joined_channels:
        channel_username = channel_info.get('username', '')
        channel_name = channel_info.get('name', 'Channel')
        if channel_username:
            channel_link = f"https://t.me/{channel_username.replace('@', '')}"
        else:
            channel_link = f"https://t.me/c/{channel_id.replace('-100', '')}"
        message += f"• {channel_name}\n"
        markup.add(types.InlineKeyboardButton(f"Join {channel_name}", url=channel_link))
    markup.add(types.InlineKeyboardButton("✅ Verify Subscription", callback_data='check_subscription_status'))
    return message, markup

# ====================== PROCESS MANAGEMENT ======================
def is_bot_running(uid, fn):
    sk = f"{uid}_{fn}"
    si = bot_scripts.get(sk)
    if si and si.get('process'):
        try:
            p = psutil.Process(si['process'].pid)
            r = p.is_running() and p.status() != psutil.STATUS_ZOMBIE
            if not r:
                if 'log_file' in si and hasattr(si['log_file'], 'close') and not si['log_file'].closed:
                    try: si['log_file'].close()
                    except: pass
                if sk in bot_scripts: del bot_scripts[sk]
            return r
        except:
            if sk in bot_scripts: del bot_scripts[sk]
            return False
    return False

def kill_process_tree(pi):
    try:
        if 'log_file' in pi and hasattr(pi['log_file'], 'close') and not pi['log_file'].closed:
            try: pi['log_file'].close()
            except: pass
        container_name = pi.get('container_name')
        if container_name and DOCKER_BIN:
            try:
                subprocess.run([DOCKER_BIN, 'stop', '--time', '2', container_name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
            except Exception:
                logger.warning('Could not stop Docker container %s cleanly', container_name)
        p = pi.get('process')
        if p and hasattr(p, 'pid'):
            try:
                par = psutil.Process(p.pid)
                ch = par.children(recursive=True)
                for c in ch:
                    try: c.terminate()
                    except: pass
                gone, alive = psutil.wait_procs(ch, timeout=1)
                for a in alive:
                    try: a.kill()
                    except: pass
                try:
                    par.terminate()
                    par.wait(timeout=1)
                except:
                    try: par.kill()
                    except: pass
            except: pass
    except: pass

# ====================== MODULE INSTALLATION ======================
def attempt_install_pip(module_name, message, manual_request=False):
    pkg = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if pkg is None:
        save_install_log(message.from_user.id, module_name, module_name, "skipped", "Core module, skipping")
        return False, "Core module"
    try:
        if manual_request:
            bot.reply_to(message, f"🔄 Manual installing `{pkg}`...")
        else:
            bot.reply_to(message, f"🐍 Installing `{pkg}`...")
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', pkg],
                               capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            bot.reply_to(message, f"✅ `{pkg}` installed.")
            save_install_log(message.from_user.id, module_name, pkg, "success", result.stdout[:500])
            return True, "Success"
        else:
            save_install_log(message.from_user.id, module_name, pkg, "failed", result.stderr[:500])
            return False, result.stderr[:500]
    except Exception as e:
        save_install_log(message.from_user.id, module_name, pkg, "error", str(e))
        return False, str(e)

def attempt_install_npm(module_name, user_folder, message, manual_request=False):
    try:
        if manual_request:
            bot.reply_to(message, f"🔄 Manual npm installing `{module_name}`...")
        else:
            bot.reply_to(message, f"🟠 Installing npm `{module_name}`...")
        result = subprocess.run(['npm', 'install', module_name], capture_output=True, text=True,
                               check=False, cwd=user_folder, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            bot.reply_to(message, f"✅ npm `{module_name}` installed.")
            save_install_log(message.from_user.id, module_name, module_name, "success", result.stdout[:500])
            return True, "Success"
        else:
            save_install_log(message.from_user.id, module_name, module_name, "failed", result.stderr[:500])
            return False, result.stderr[:500]
    except Exception as e:
        save_install_log(message.from_user.id, module_name, module_name, "error", str(e))
        return False, str(e)

# ====================== SCRIPT RUNNER ======================
def _message_chat_id(message_obj, uid):
    try:
        return message_obj.chat.id
    except Exception:
        return int(uid)

def _runner_reply(message_obj, uid, text):
    try:
        if hasattr(message_obj, 'chat'):
            bot.reply_to(message_obj, text)
        else:
            bot.send_message(_message_chat_id(message_obj, uid), text)
    except Exception as exc:
        logger.warning("Could not send runner notification: %s", exc)

def _docker_available():
    if not DOCKER_BIN:
        return False
    try:
        return subprocess.run([DOCKER_BIN, 'info'], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=3).returncode == 0
    except Exception:
        return False

def _sandbox_command(script_path, user_folder, file_name, file_type):
    """Return (command, sandboxed). Docker containers get CPU/RAM/PID limits and no capabilities."""
    safe_tag = re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.splitext(file_name)[0])[:80] or 'bot'
    per_script_requirements = f'.auto_requirements_{safe_tag}.txt'
    per_script_npm = f'.auto_npm_packages_{safe_tag}.txt'
    if _docker_available():
        image = 'python:3.12-slim' if file_type == 'py' else 'node:20-slim'
        script_in_container = '/workspace/' + os.path.basename(script_path)
        if file_type == 'py':
            launch = ("if [ -f requirements.txt ]; then python -m pip install --disable-pip-version-check -r requirements.txt || exit $?; fi; "
                      "if [ -f .auto_requirements.txt ]; then python -m pip install --disable-pip-version-check -r .auto_requirements.txt || exit $?; fi; "
                      f"if [ -f {shlex.quote(per_script_requirements)} ]; then python -m pip install --disable-pip-version-check -r {shlex.quote(per_script_requirements)} || exit $?; fi; "
                      f"exec python -u {shlex.quote(script_in_container)}")
        else:
            launch = ("if [ -f package.json ]; then npm install --no-audit --no-fund || exit $?; fi; "
                      "if [ -f .auto_npm_packages.txt ]; then while IFS= read -r pkg; do [ -z \"$pkg\" ] || npm install --no-audit --no-fund \"$pkg\" || exit $?; done < .auto_npm_packages.txt; fi; "
                      f"if [ -f {shlex.quote(per_script_npm)} ]; then while IFS= read -r pkg; do [ -z \"$pkg\" ] || npm install --no-audit --no-fund \"$pkg\" || exit $?; done < {shlex.quote(per_script_npm)}; fi; "
                      f"exec node {shlex.quote(script_in_container)}")
        name = 'hostbot-' + re.sub(r'[^a-zA-Z0-9_.-]', '-', f'{os.path.basename(user_folder)}-{os.path.splitext(file_name)[0]}')[:45]
        cmd = [DOCKER_BIN, 'run', '--rm', '--name', name,
               '--memory', BOT_MEMORY_LIMIT, '--cpus', BOT_CPU_LIMIT,
               '--pids-limit', str(BOT_PIDS_LIMIT), '--security-opt', 'no-new-privileges',
               '--cap-drop', 'ALL', '--network', 'bridge',
               '-v', f'{os.path.abspath(user_folder)}:/workspace:rw', '-w', '/workspace',
               image, 'sh', '-lc', launch]
        return cmd, True
    if REQUIRE_DOCKER_SANDBOX:
        raise RuntimeError('Secure Docker sandbox is required but Docker is not available. Install Docker or set REQUIRE_DOCKER_SANDBOX=0 only if you accept the risk.')
    # Compatibility fallback for platforms such as basic PaaS containers without Docker.
    # This limits subprocess resources where supported, but is NOT a security sandbox.
    if file_type == 'py':
        venv_dir = os.path.join(user_folder, '.venv_' + safe_tag)
        py = os.path.join(venv_dir, 'bin', 'python')
        if os.name == 'nt': py = os.path.join(venv_dir, 'Scripts', 'python.exe')
        if not os.path.exists(py):
            subprocess.run([sys.executable, '-m', 'venv', venv_dir], check=True, timeout=120)
        req = os.path.join(user_folder, 'requirements.txt')
        auto_req = os.path.join(user_folder, '.auto_requirements.txt')  # legacy shared recovery list
        per_script_req = os.path.join(user_folder, per_script_requirements)
        for req_path in (req, auto_req, per_script_req):
            if os.path.isfile(req_path):
                pip = [py, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', req_path]
                result = subprocess.run(pip, cwd=user_folder, capture_output=True, text=True, timeout=900)
                if result.returncode:
                    raise RuntimeError(os.path.basename(req_path) + ' install failed: ' + (result.stderr or result.stdout)[-1200:])
        return [py, '-u', script_path], False
    if os.path.isfile(os.path.join(user_folder, 'package.json')):
        result = subprocess.run(['npm', 'install', '--no-audit', '--no-fund'], cwd=user_folder,
                                capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError('npm install failed: ' + (result.stderr or result.stdout)[-1200:])
    auto_npm = os.path.join(user_folder, '.auto_npm_packages.txt')
    per_script_auto_npm = os.path.join(user_folder, per_script_npm)
    for npm_list in (auto_npm, per_script_auto_npm):
      if os.path.isfile(npm_list):
        for package in open(npm_list, encoding='utf-8', errors='ignore'):
            package = package.strip()
            if package and re.fullmatch(r'[A-Za-z0-9@._/-]+', package):
                result = subprocess.run(['npm', 'install', '--no-audit', '--no-fund', package], cwd=user_folder,
                                        capture_output=True, text=True, timeout=600)
                if result.returncode:
                    raise RuntimeError('npm package install failed: ' + (result.stderr or result.stdout)[-1200:])
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is not installed on the hosting server.')
    return [node, script_path], False

def _start_hosted_process(script_path, uid, user_folder, file_name, message_obj, file_type, attempt=1, dependency_attempt=0):
    sk = f'{uid}_{file_name}'
    if is_bot_running(uid, file_name):
        _runner_reply(message_obj, uid, f'ℹ️ `{file_name}` is already running.')
        return
    if not os.path.isfile(script_path):
        _runner_reply(message_obj, uid, f'❌ File not found: `{file_name}`')
        return
    fs = get_file_status(uid, file_name)
    if not fs or fs.get('status') not in [FILE_STATUS_APPROVED, FILE_STATUS_AUTO_APPROVED]:
        status = fs.get('status', 'unknown') if fs else 'unknown'
        _runner_reply(message_obj, uid, f'❌ File `{file_name}` is not approved. Status: {str(status).upper()}')
        return
    log_path = os.path.join(user_folder, f'{os.path.splitext(file_name)[0]}.log')
    try:
        command, sandboxed = _sandbox_command(script_path, user_folder, file_name, file_type)
        log_file = open(log_path, 'a', encoding='utf-8', errors='replace')
        log_file.write(f'\n\n===== START {datetime.now().isoformat()} =====\n')
        log_file.flush()
        kwargs = {'cwd': user_folder, 'stdout': log_file, 'stderr': log_file,
                  'stdin': subprocess.DEVNULL, 'close_fds': True}
        if os.name != 'nt':
            kwargs['start_new_session'] = True
            try:
                import resource
                def limit_resources():
                    resource.setrlimit(resource.RLIMIT_CPU, (3600, 3600))
                    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                kwargs['preexec_fn'] = limit_resources
            except Exception:
                pass
        process = subprocess.Popen(command, **kwargs)
        container_name = None
        if sandboxed and '--name' in command:
            try: container_name = command[command.index('--name') + 1]
            except Exception: container_name = None
        bot_scripts[sk] = {
            'process': process, 'log_file': log_file, 'file_name': file_name,
            'container_name': container_name,
            'chat_id': _message_chat_id(message_obj, uid), 'script_owner_id': uid,
            'start_time': datetime.now(), 'user_folder': user_folder,
            'type': file_type, 'script_key': sk, 'message_obj': message_obj,
            'sandboxed': sandboxed, 'restart_count': max(0, int(attempt) - 1),
            'dependency_retry_count': max(0, int(dependency_attempt)), 'last_exit_code': None,
            'last_notified_exit': None, 'command': command
        }
        mode = 'Docker sandbox' if sandboxed else 'compatibility mode (Docker unavailable; not fully isolated)'
        _runner_reply(message_obj, uid, f'✅ `{file_name}` started! PID: `{process.pid}`\n🛡️ Runtime: {mode}\n📜 Logs are available in the file controls.')
        if not sandboxed:
            logger.warning('Hosted script %s is running without Docker isolation.', sk)
    except Exception as exc:
        logger.exception('Failed to start hosted script %s', sk)
        _runner_reply(message_obj, uid, f'❌ Could not start `{file_name}`: {str(exc)[:900]}')

def run_script(script_path, uid, user_folder, file_name, message_obj, attempt=1, dependency_attempt=0):
    _start_hosted_process(script_path, uid, user_folder, file_name, message_obj, 'py', attempt, dependency_attempt)

def run_js_script(script_path, uid, user_folder, file_name, message_obj, attempt=1, dependency_attempt=0):
    _start_hosted_process(script_path, uid, user_folder, file_name, message_obj, 'js', attempt, dependency_attempt)

# ====================== FILE HANDLERS ======================
def send_file_for_approval(message, uid, file_name, file_type):
    user = message.from_user
    file_info = (f"📄 **NEW FILE FOR APPROVAL**\n\n"
                 f"👤 **User:** {user.first_name}\n"
                 f"🆔 **ID:** `{uid}`\n"
                 f"📁 **File:** `{file_name}`\n"
                 f"📊 **Type:** {file_type}\n"
                 f"🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve & Start", callback_data=f'approve_{uid}_{file_name}'),
        types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{uid}_{file_name}')
    )
    markup.add(types.InlineKeyboardButton("📋 View All Pending", callback_data='view_pending'))
    
    for admin_id in admin_ids:
        try:
            bot.forward_message(admin_id, message.chat.id, message.message_id)
            bot.send_message(admin_id, file_info, reply_markup=markup, parse_mode='Markdown')
        except: pass

def handle_py_file(file_path, uid, user_folder, file_name, message):
    try:
        save_user_file(uid, file_name, 'py')
        if is_user_whitelisted(uid):
            save_file_approval(uid, file_name, 'py', FILE_STATUS_AUTO_APPROVED)
            bot.reply_to(message, f"✅ Python `{file_name}` uploaded!\n🤖 Auto-Approved (Whitelisted)\n🚀 Starting automatically...", parse_mode='Markdown')
            threading.Thread(target=run_script, args=(file_path, uid, user_folder, file_name, message)).start()
        else:
            save_file_approval(uid, file_name, 'py', FILE_STATUS_PENDING)
            send_file_for_approval(message, uid, file_name, 'py')
            bot.reply_to(message, f"✅ Python `{file_name}` uploaded!\n📋 **PENDING APPROVAL**\n⏳ Waiting for admin approval.", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

def handle_js_file(file_path, uid, user_folder, file_name, message):
    try:
        save_user_file(uid, file_name, 'js')
        if is_user_whitelisted(uid):
            save_file_approval(uid, file_name, 'js', FILE_STATUS_AUTO_APPROVED)
            bot.reply_to(message, f"✅ JS `{file_name}` uploaded!\n🤖 Auto-Approved (Whitelisted)\n🚀 Starting automatically...", parse_mode='Markdown')
            threading.Thread(target=run_js_script, args=(file_path, uid, user_folder, file_name, message)).start()
        else:
            save_file_approval(uid, file_name, 'js', FILE_STATUS_PENDING)
            send_file_for_approval(message, uid, file_name, 'js')
            bot.reply_to(message, f"✅ JS `{file_name}` uploaded!\n📋 **PENDING APPROVAL**\n⏳ Waiting for admin approval.", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

def handle_zip_file(content, file_name, message):
    uid = message.from_user.id
    user_folder = get_user_folder(uid)
    temp_dir = tempfile.mkdtemp(prefix=f"user_{uid}_zip_")
    try:
        zip_path = os.path.join(temp_dir, file_name)
        with open(zip_path, 'wb') as f: f.write(content)
        with zipfile.ZipFile(zip_path, 'r') as z:
            # Reject path traversal, symlinks, and oversized archives before extracting.
            total_uncompressed = 0
            for info in z.infolist():
                member = info.filename.replace('\\', '/')
                if member.startswith('/') or any(part == '..' for part in member.split('/')):
                    raise ValueError('Unsafe ZIP path detected.')
                total_uncompressed += info.file_size
                if total_uncompressed > 100 * 1024 * 1024:
                    raise ValueError('ZIP expands beyond the 100 MB limit.')
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ValueError('ZIP symlinks are not allowed.')
            z.extractall(temp_dir)
        
        py_files = [f for f in os.listdir(temp_dir) if f.endswith('.py')]
        js_files = [f for f in os.listdir(temp_dir) if f.endswith('.js')]
        
        if py_files:
            main_script = 'main.py' if 'main.py' in py_files else py_files[0]
            for item in os.listdir(temp_dir):
                shutil.move(os.path.join(temp_dir, item), os.path.join(user_folder, item))
            save_user_file(uid, main_script, 'py')
            if is_user_whitelisted(uid):
                save_file_approval(uid, main_script, 'py', FILE_STATUS_AUTO_APPROVED)
                bot.reply_to(message, f"✅ ZIP Extracted! Main: `{main_script}`\n🤖 Auto-Approved\n🚀 Starting...", parse_mode='Markdown')
                threading.Thread(target=run_script, args=(os.path.join(user_folder, main_script), uid, user_folder, main_script, message)).start()
            else:
                save_file_approval(uid, main_script, 'py', FILE_STATUS_PENDING)
                send_file_for_approval(message, uid, main_script, 'py')
                bot.reply_to(message, f"✅ ZIP Extracted! Main: `{main_script}`\n📋 **PENDING APPROVAL**", parse_mode='Markdown')
        elif js_files:
            main_script = 'index.js' if 'index.js' in js_files else js_files[0]
            for item in os.listdir(temp_dir):
                shutil.move(os.path.join(temp_dir, item), os.path.join(user_folder, item))
            save_user_file(uid, main_script, 'js')
            if is_user_whitelisted(uid):
                save_file_approval(uid, main_script, 'js', FILE_STATUS_AUTO_APPROVED)
                bot.reply_to(message, f"✅ ZIP Extracted! Main: `{main_script}`\n🤖 Auto-Approved\n🚀 Starting...", parse_mode='Markdown')
                threading.Thread(target=run_js_script, args=(os.path.join(user_folder, main_script), uid, user_folder, main_script, message)).start()
            else:
                save_file_approval(uid, main_script, 'js', FILE_STATUS_PENDING)
                send_file_for_approval(message, uid, main_script, 'js')
                bot.reply_to(message, f"✅ ZIP Extracted! Main: `{main_script}`\n📋 **PENDING APPROVAL**", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ No .py or .js found in ZIP!")
    except Exception as e:
        bot.reply_to(message, f"❌ ZIP Error: {e}")
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

# ====================== APPROVAL CALLBACKS ======================
def handle_approve_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    
    _, uid_str, fn = call.data.split('_', 2)
    uid = int(uid_str)
    
    if update_file_status(uid, fn, FILE_STATUS_APPROVED, call.from_user.id):
        bot.answer_callback_query(call.id, "✅ Approved & Starting!")
        try:
            bot.edit_message_text(f"✅ **APPROVED & STARTING**\n📁 `{fn}`\n👤 `{uid}`", 
                                 call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        except: pass
        try:
            bot.send_message(uid, f"✅ **File Approved!**\n📁 `{fn}`\n🚀 Starting automatically...", parse_mode='Markdown')
        except: pass
        user_folder = get_user_folder(uid)
        file_path = os.path.join(user_folder, fn)
        fs = get_file_status(uid, fn)
        if fs['file_type'] == 'py':
            threading.Thread(target=run_script, args=(file_path, uid, user_folder, fn, call.message)).start()
        elif fs['file_type'] == 'js':
            threading.Thread(target=run_js_script, args=(file_path, uid, user_folder, fn, call.message)).start()
    else:
        bot.answer_callback_query(call.id, "❌ Failed to approve.", show_alert=True)

def handle_reject_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    
    _, uid_str, fn = call.data.split('_', 2)
    uid = int(uid_str)
    
    if update_file_status(uid, fn, FILE_STATUS_REJECTED, call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Rejected!")
        try:
            bot.edit_message_text(f"❌ **REJECTED**\n📁 `{fn}`\n👤 `{uid}`", 
                                 call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        except: pass
        try:
            bot.send_message(uid, f"❌ **File Rejected!**\n📁 `{fn}`\nPlease contact admin.", parse_mode='Markdown')
        except: pass
        user_folder = get_user_folder(uid)
        file_path = os.path.join(user_folder, fn)
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass
        remove_user_file_db(uid, fn)
    else:
        bot.answer_callback_query(call.id, "❌ Failed to reject.", show_alert=True)

# ====================== MENU CREATION ======================
def create_main_menu_inline(uid):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton('📢 Updates', url=UPDATE_CHANNEL))
    markup.add(types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
               types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'))
    markup.add(types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
               types.InlineKeyboardButton('📊 Statistics', callback_data='stats'))
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'),
               types.InlineKeyboardButton('🤖 VIP AI', callback_data='royal_ai'))
    markup.add(types.InlineKeyboardButton('📦 Manual Install', callback_data='manual_install'),
               types.InlineKeyboardButton('📝 My Notes', callback_data='my_notes'))
    markup.add(types.InlineKeyboardButton('⏰ Reminders', callback_data='reminders'),
               types.InlineKeyboardButton('👥 Referral', callback_data='referral'))
    
    if is_admin(uid):
        pending_count = get_pending_files_count()
        pending_text = f"📋 Pending ({pending_count})" if pending_count > 0 else "📋 Pending Files"
        markup.add(types.InlineKeyboardButton(pending_text, callback_data='view_pending'),
                   types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'))
        markup.add(types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'),
                   types.InlineKeyboardButton('🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot',
                   callback_data='lock_bot' if not bot_locked else 'unlock_bot'))
        markup.add(types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'),
                   types.InlineKeyboardButton('🟢 Run All', callback_data='run_all_scripts'))
        markup.add(types.InlineKeyboardButton('📋 All Codes', callback_data='all_codes_status'),
                   types.InlineKeyboardButton('👥 Whitelist', callback_data='whitelist_panel'))
        
        # Terminal - ONLY for Owner
        if is_owner(uid):
            markup.add(types.InlineKeyboardButton('💻 Terminal', callback_data='terminal'),
                       types.InlineKeyboardButton('📁 File Manager', callback_data='file_manager'))
        else:
            markup.add(types.InlineKeyboardButton('📁 File Manager', callback_data='file_manager'))
        
        markup.add(types.InlineKeyboardButton('📢 Channels', callback_data='manage_mandatory_channels'),
                   types.InlineKeyboardButton('👥 User Mgmt', callback_data='user_management'))
        markup.add(types.InlineKeyboardButton('⚙️ Settings', callback_data='admin_settings'),
                   types.InlineKeyboardButton('💾 Backup', callback_data='backup'))
        markup.add(types.InlineKeyboardButton('🌐 Network Info', callback_data='network_info'),
                   types.InlineKeyboardButton('📊 Sys Monitor', callback_data='system_monitor'))
        markup.add(types.InlineKeyboardButton('🔧 Proc Mgr', callback_data='process_manager'))
    
    markup.add(types.InlineKeyboardButton('📈 Live Dashboard', callback_data='dashboard'))
    markup.add(types.InlineKeyboardButton('⏱ Uptime', callback_data='uptime'))
    markup.add(types.InlineKeyboardButton('🆘 Help', callback_data='help'))
    return markup

def create_reply_keyboard_main_menu(uid):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if is_owner(uid):
        # Owner gets full admin menu with Terminal
        layout = [
            ["📢 Updates Channel", "🚀 Ping"],
            ["📤 Upload File", "📂 Check Files"],
            ["⚡ Bot Speed", "📊 Statistics"],
            ["💳 Subscriptions", "📢 Broadcast"],
            ["🔒 Lock Bot", "🟢 Run All Code"],
            ["👑 Admin Panel", "📞 Contact Owner"],
            ["🤖 VIP AI", "⏱ Uptime"],
            ["📋 All Codes Status", "👥 Whitelist Users"],
            ["💻 Terminal", "📁 File Manager"],
            ["📢 Channel Add", "👥 User Management"],
            ["⚙️ Settings", "💾 Backup"],
            ["🌐 Network Info", "📊 System Monitor"],
            ["🔧 Process Manager", "🆘 Help"]
        ]
    elif is_admin(uid):
        # Admin gets menu WITHOUT Terminal
        layout = [
            ["📢 Updates Channel", "🚀 Ping"],
            ["📤 Upload File", "📂 Check Files"],
            ["⚡ Bot Speed", "📊 Statistics"],
            ["💳 Subscriptions", "📢 Broadcast"],
            ["🔒 Lock Bot", "🟢 Run All Code"],
            ["👑 Admin Panel", "📞 Contact Owner"],
            ["🤖 VIP AI", "⏱ Uptime"],
            ["📋 All Codes Status", "👥 Whitelist Users"],
            ["📁 File Manager", "📢 Channel Add"],
            ["👥 User Management", "⚙️ Settings"],
            ["💾 Backup", "🌐 Network Info"],
            ["📊 System Monitor", "🔧 Process Manager"],
            ["🆘 Help"]
        ]
    else:
        layout = COMMAND_BUTTONS_LAYOUT_USER_SPEC
    
    for row in layout:
        markup.add(*[types.KeyboardButton(text) for text in row])
    return markup

def create_control_buttons(uid, fn, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{uid}_{fn}'),
                   types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{uid}_{fn}'))
        markup.row(types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{uid}_{fn}'),
                   types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{uid}_{fn}'))
    else:
        markup.row(types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{uid}_{fn}'),
                   types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{uid}_{fn}'))
        markup.row(types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{uid}_{fn}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
               types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin'))
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton('➕ Add Sub', callback_data='add_subscription'),
               types.InlineKeyboardButton('➖ Remove Sub', callback_data='remove_subscription'))
    markup.row(types.InlineKeyboardButton('🔍 Check Sub', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_whitelist_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton('➕ Add Whitelist', callback_data='add_whitelist'),
               types.InlineKeyboardButton('➖ Remove Whitelist', callback_data='remove_whitelist'))
    markup.row(types.InlineKeyboardButton('📋 List Whitelisted', callback_data='list_whitelist'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_user_management_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton('🚫 Ban User', callback_data='ban_user'),
               types.InlineKeyboardButton('✅ Unban User', callback_data='unban_user'))
    markup.row(types.InlineKeyboardButton('📊 User Info', callback_data='user_info'),
               types.InlineKeyboardButton('👥 All Users', callback_data='all_users'))
    markup.row(types.InlineKeyboardButton('🔧 Set Limit', callback_data='set_user_limit'),
               types.InlineKeyboardButton('🗑️ Remove Limit', callback_data='remove_user_limit'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_admin_settings_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton('📊 System Info', callback_data='system_info'),
               types.InlineKeyboardButton('📈 Performance', callback_data='bot_performance'))
    markup.row(types.InlineKeyboardButton('🧹 Cleanup', callback_data='cleanup_files'),
               types.InlineKeyboardButton('📋 Install Logs', callback_data='install_logs'))
    markup.row(types.InlineKeyboardButton('📜 Bot Logs', callback_data='bot_logs'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_mandatory_channels_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton('➕ Add Channel', callback_data='add_mandatory_channel'),
               types.InlineKeyboardButton('➖ Remove Channel', callback_data='remove_mandatory_channel'))
    markup.row(types.InlineKeyboardButton('📋 List Channels', callback_data='list_mandatory_channels'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_file_manager_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📂 List All User Folders", callback_data='fm_list_users'))
    markup.add(types.InlineKeyboardButton("🔍 Search File", callback_data='fm_search'))
    markup.add(types.InlineKeyboardButton("📊 Storage Stats", callback_data='fm_stats'))
    markup.add(types.InlineKeyboardButton("🧹 Clean Empty Folders", callback_data='fm_clean'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    return markup

# ====================== AI COMMAND ======================
@bot.message_handler(commands=['royal_ai', 'ai', 'mpx', 'vip_ai'])
def handle_royal_ai(message):
    if is_user_banned(message.from_user.id): return
    if not message.text or len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: `/royal_ai your question`", parse_mode='Markdown')
        return
    query = message.text.split(' ', 1)[1]
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": query}], "temperature": 0.7}
        response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        answer = result.get('choices', [{}])[0].get('message', {}).get('content', 'No response from AI')
        if len(answer) > 4000:
            for x in range(0, len(answer), 4000):
                bot.reply_to(message, answer[x:x+4000], parse_mode='Markdown')
        else:
            bot.reply_to(message, answer, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ AI Error: {str(e)}")

# ====================== COMMAND HANDLERS ======================
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    if is_user_banned(message.from_user.id):
        bot.reply_to(message, "❌ You are banned.")
        return
    if message.text == '/help':
        _logic_help(message)
    else:
        _logic_send_welcome(message)

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    if message.from_user.id in terminal_mode_users:
        terminal_mode_users.remove(message.from_user.id)
        bot.reply_to(message, "❌ Terminal mode exited.")
    else:
        bot.reply_to(message, "No active mode to cancel.")

@bot.message_handler(commands=['ping'])
def cmd_ping(message):
    if is_user_banned(message.from_user.id):
        bot.reply_to(message, "❌ You are banned.")
        return
    start = time.time()
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start) * 1000, 2)
    bot.edit_message_text(f"Pong! Latency: {latency} ms\nUptime: {get_uptime()}", message.chat.id, msg.message_id)

@bot.message_handler(commands=['uptime'])
def cmd_uptime(message):
    bot.reply_to(message, f"⏱ Uptime: `{get_uptime()}`", parse_mode='Markdown')

@bot.message_handler(commands=['status', 'statistics'])
def cmd_status(message):
    _logic_statistics(message)

@bot.message_handler(commands=['dashboard', 'hosting'])
def cmd_dashboard(message):
    send_live_dashboard(message.chat.id, message.from_user.id)

# ====================== TERMINAL COMMAND (ONLY OWNER) ======================
def _logic_terminal(message):
    # Only Owner can access terminal
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "⚠️ **Terminal access is only for Owner!**", parse_mode='Markdown')
        return
    
    terminal_mode_users.add(message.from_user.id)
    bot.reply_to(message, 
        "💻 **Terminal Mode Activated!**\n\n"
        "Send any command to execute.\n"
        "Send `/cancel` to exit terminal mode.\n"
        "⚠️ Use with caution! Dangerous commands are blocked.\n"
        "🔒 **Owner Only Access**",
        parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.from_user.id in terminal_mode_users and m.text and not m.text.startswith('/'), content_types=['text'])
def handle_terminal_command(message):
    # Verify it's still the owner
    if not is_owner(message.from_user.id):
        terminal_mode_users.remove(message.from_user.id)
        bot.reply_to(message, "⚠️ Terminal access removed. Owner only.")
        return
    
    command = message.text
    # Block dangerous commands
    for blocked in TERMINAL_BLACKLIST:
        if blocked in command.lower():
            bot.reply_to(message, "🚫 **Command blocked!**")
            return
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, encoding='utf-8', errors='ignore')
        output = result.stdout + result.stderr
        if not output.strip():
            output = "(no output)"
        if len(output) > 4000:
            output = output[:4000] + "\n... (truncated)"
        bot.reply_to(message, f"💻 `{command}`\n```\n{output}\n```", parse_mode='Markdown')
    except subprocess.TimeoutExpired:
        bot.reply_to(message, "⏱️ Timed out (30s).")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# ====================== LOGIC FUNCTIONS ======================
def _logic_send_welcome(message):
    uid = message.from_user.id
    chat_id = message.chat.id
    uname = message.from_user.first_name
    
    if is_user_banned(uid):
        bot.send_message(chat_id, "❌ You are banned.")
        return

    if message.text and message.text.startswith('/start ref_'):
        try:
            ref_by = int(message.text.split('_')[1])
            if uid != ref_by:
                save_referral(uid, ref_by)
        except: pass

    if uid not in active_users:
        active_users.add(uid)
        try:
            bot.send_message(OWNER_ID, f"🎉 New user!\n👤 {uname}\n🆔 `{uid}`", parse_mode='Markdown')
        except: pass

    fl = get_user_file_limit(uid)
    cf = get_user_file_count(uid)
    ls = str(fl) if fl != float('inf') else "Unlimited"
    
    if uid == OWNER_ID:
        us = "👑 Owner"
        ei = ""
    elif is_admin(uid):
        us = "🛡️ Admin"
        ei = ""
    elif is_user_premium(uid):
        us = "⭐ Premium"
        exp = user_subscriptions[uid]['expiry']
        days = (exp - datetime.now()).days
        ei = f"\n⏳ Expires in: {days} days"
    else:
        us = "🆓 Free User"
        ei = ""
    
    pending_count = get_pending_files_count() if is_admin(uid) else 0
    pending_text = f"\n📋 Pending approvals: {pending_count}" if is_admin(uid) and pending_count > 0 else ""
    
    # Show terminal info if owner
    terminal_info = "\n🔒 **You have Terminal Access!**" if is_owner(uid) else ""
    
    text = (f"〽️ Welcome, {uname}!\n\n🆔 ID: `{uid}`\n🔰 Status: {us}{ei}\n"
            f"📁 Files: {cf} / {ls}\n👥 Referrals: {get_referral_count(uid)}{pending_text}{terminal_info}\n\n"
            f"🤖 Host Python/JS scripts.\n📤 Upload `.py`, `.js`, or `.zip`.\n\n"
            f"📋 **All files require admin approval before starting.**")
    bot.send_message(chat_id, text, reply_markup=create_reply_keyboard_main_menu(uid), parse_mode='Markdown')

def _logic_upload_file(message):
    uid = message.from_user.id
    if is_user_banned(uid):
        bot.reply_to(message, "❌ Banned.")
        return
    if bot_locked and not is_admin(uid):
        bot.reply_to(message, "⚠️ Bot locked.")
        return
    if get_user_file_count(uid) >= get_user_file_limit(uid):
        bot.reply_to(message, f"⚠️ Limit reached. ({get_user_file_count(uid)}/{get_user_file_limit(uid)})")
        return
    bot.reply_to(message, "📤 Send `.py`, `.js`, or `.zip` file.\n\n📋 **All files require admin approval before running.**")

def _logic_check_files(message):
    uid = message.from_user.id
    ufl = user_files.get(uid, [])
    if not ufl:
        bot.reply_to(message, "📂 No files uploaded yet.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    text = "📁 **Your Files:**\n\n"
    for fn, ft in sorted(ufl):
        is_run = is_bot_running(uid, fn)
        fs = get_file_status(uid, fn)
        si = "🟢" if is_run else "⚪"
        if fs['status'] == FILE_STATUS_APPROVED:
            ai = "✅"
        elif fs['status'] == FILE_STATUS_AUTO_APPROVED:
            ai = "🤖"
        elif fs['status'] == FILE_STATUS_PENDING:
            ai = "⏳"
        else:
            ai = "❌"
        markup.add(types.InlineKeyboardButton(f"{ai} {fn} ({ft}) - {si}", callback_data=f'file_{uid}_{fn}'))
        text += f"{ai} `{fn}` - {fs['status'].upper()}\n"
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    bot.reply_to(message, text, reply_markup=markup, parse_mode='Markdown')

def _logic_bot_speed(message):
    uid = message.from_user.id
    chat_id = message.chat.id
    start = time.time()
    msg = bot.reply_to(message, "🏃 Testing speed...")
    try:
        bot.send_chat_action(chat_id, 'typing')
        rt = round((time.time() - start) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if uid == OWNER_ID: ul = "👑 Owner"
        elif is_admin(uid): ul = "🛡️ Admin"
        elif is_user_premium(uid): ul = "⭐ Premium"
        else: ul = "🆓 Free"
        speed_msg = f"⚡ Bot Speed & Status:\n\n⏱️ API Response Time: {rt} ms\n🚦 Bot Status: {status}\n👤 Your Level: {ul}"
        bot.edit_message_text(speed_msg, chat_id, msg.message_id)
    except Exception as e:
        logger.error(f"Speed test error: {e}")
        bot.edit_message_text("❌ Error during speed test.", chat_id, msg.message_id)

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Click to contact Owner:", reply_markup=markup)

def _logic_help(message):
    text = ("🤖 **ULTIMATE HOSTING BOT - Help**\n\n"
            "**📌 Basic Commands:**\n• /start - Start bot\n• /help - This help\n"
            "• /status - Statistics\n• /ping - Speed test\n• /uptime - Bot uptime\n\n"
            "**📁 File Management:**\n• Upload `.py`, `.js`, or `.zip`\n"
            "• Auto-install dependencies (15 retries)\n• Admin approval required\n"
            "• Start/Stop/Restart/Delete scripts\n• /dashboard - Live CPU/RAM/disk and process status\n• Docker sandbox (when Docker is available), resource limits, auto-restart and logs\n\n"
            "**👑 Admin Features:**\n• 💻 Terminal access **(Owner Only)**\n• 📁 File Manager\n"
            "• 📊 System Monitor\n• 🔧 Process Manager\n• 💾 Backup System\n"
            "• User management (ban/unban)\n• Set custom file limits\n"
            "• Mandatory channels\n• Broadcast messages\n"
            "• Run all scripts\n• Whitelist users\n"
            "• Subscriptions management\n• File approval system\n\n"
            "**📝 User Features:**\n• Notes system\n• Reminders\n"
            "• Referral system (10 refs = Premium)\n• VIP AI assistant\n\n"
            "**Support:** @NEXRO12H\n**Updates:** https://t.me/NEXRO12H")
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_statistics(message):
    uid = message.from_user.id
    total = len(active_users)
    files = sum(len(f) for f in user_files.values())
    running = len(bot_scripts)
    pending = get_pending_files_count()
    text = f"📊 **Bot Statistics:**\n\n👥 Users: {total}\n📂 Files: {files}\n🟢 Running: {running}\n🚫 Banned: {len(banned_users)}"
    if is_admin(uid):
        text += f"\n📋 Pending: {pending}\n🔒 Status: {'Locked' if bot_locked else 'Unlocked'}"
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_subscriptions_panel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "💳 Subscription Management", reply_markup=create_subscription_menu())

def _logic_toggle_lock_bot(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked" if bot_locked else "unlocked"
    bot.reply_to(message, f"🔒 Bot has been {status}.")

def _logic_broadcast_init(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.reply_to(message, "📢 Send broadcast message.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_broadcast_{message.message_id}"),
               types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast"))
    bot.reply_to(message, f"⚠️ Confirm broadcast to **{len(active_users)}** users?", reply_markup=markup)

def handle_confirm_broadcast(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id, "🚀 Broadcasting...")
    try:
        text = call.message.reply_to_message.text
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)} users...", call.message.chat.id, call.message.message_id)
        threading.Thread(target=execute_broadcast, args=(text, call.message.chat.id)).start()
    except: pass

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "Cancelled.")
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

def execute_broadcast(text, admin_chat_id):
    sent = 0; failed = 0; blocked = 0
    for uid in list(active_users):
        try:
            bot.send_message(uid, text, parse_mode='Markdown')
            sent += 1
        except telebot.apihelper.ApiTelegramException as e:
            if any(s in str(e).lower() for s in ["blocked", "deactivated", "not found"]):
                blocked += 1
            else:
                failed += 1
        except: failed += 1
        time.sleep(0.1)
    bot.send_message(admin_chat_id, f"📢 Broadcast Complete!\n✅ Sent: {sent}\n❌ Failed: {failed}\n🚫 Blocked: {blocked}")

def _logic_admin_panel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "👑 Admin Panel", reply_markup=create_admin_panel())

def _logic_user_management(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "👥 User Management", reply_markup=create_user_management_menu())

def _logic_admin_settings(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "⚙️ Admin Settings", reply_markup=create_admin_settings_menu())

def _logic_manage_mandatory_channels(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "📢 Mandatory Channels Management", reply_markup=create_mandatory_channels_menu())

def _logic_manual_install(message):
    msg = bot.reply_to(message, "📦 Send module name to install\nFor Node.js: `npm:module_name`\n/cancel to abort", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_manual_install)

def process_manual_install(message):
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    module_name = message.text.strip()
    if module_name.lower().startswith('npm:'):
        module_name = module_name[4:].strip()
        user_folder = get_user_folder(message.from_user.id)
        attempt_install_npm(module_name, user_folder, message, manual_request=True)
    else:
        attempt_install_pip(module_name, message, manual_request=True)

def _logic_all_codes_status(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    text = "📋 **All Codes Status:**\n\n"
    for uid, files in user_files.items():
        for fn, ft in files:
            is_run = is_bot_running(uid, fn)
            fs = get_file_status(uid, fn)
            si = "🟢" if is_run else "⚪"
            if fs['status'] == FILE_STATUS_APPROVED:
                ai = "✅"
            elif fs['status'] == FILE_STATUS_AUTO_APPROVED:
                ai = "🤖"
            elif fs['status'] == FILE_STATUS_PENDING:
                ai = "⏳"
            else:
                ai = "❌"
            text += f"{ai} `{fn}` (User: {uid}) - {si}\n"
    if not user_files: text += "No files found."
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_whitelist_panel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "👥 Whitelist Management", reply_markup=create_whitelist_panel())

def _logic_whitelist(message):
    _logic_whitelist_panel(message)

def _logic_add_whitelist(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.reply_to(message, "Enter User ID to add to whitelist.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_whitelist)

def process_add_whitelist(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if is_user_whitelisted(uid):
            bot.reply_to(message, f"User `{uid}` already whitelisted.")
            return
        if add_user_to_whitelist(uid, message.from_user.id):
            bot.reply_to(message, f"✅ `{uid}` whitelisted.")
            try: bot.send_message(uid, "🎉 **You are whitelisted!**\nFiles auto-approved now.", parse_mode='Markdown')
            except: pass
        else:
            bot.reply_to(message, "❌ Failed.")
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def _logic_remove_whitelist(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.reply_to(message, "Enter User ID to remove from whitelist.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_whitelist)

def process_remove_whitelist(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if not is_user_whitelisted(uid):
            bot.reply_to(message, f"User `{uid}` not whitelisted.")
            return
        if remove_user_from_whitelist(uid):
            bot.reply_to(message, f"✅ `{uid}` removed from whitelist.")
            try: bot.send_message(uid, "⚠️ You are no longer whitelisted.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def _logic_list_whitelist(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    text = "👥 **Whitelisted Users:**\n\n"
    for uid in sorted(whitelist_users):
        text += f"- `{uid}`\n"
    if not whitelist_users: text += "No whitelisted users."
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_ban_user(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.send_message(message.chat.id, "Enter `user_id reason`\nExample: `12345678 Spamming`\n/cancel to abort")
    bot.register_next_step_handler(msg, process_ban_user)

def process_ban_user(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        parts = message.text.split()
        uid = int(parts[0]); reason = ' '.join(parts[1:])
        if uid == OWNER_ID:
            bot.reply_to(message, "⚠️ Cannot ban owner.")
            return
        if is_admin(uid):
            bot.reply_to(message, "⚠️ Cannot ban admin.")
            return
        if ban_user_db(uid, reason, message.from_user.id):
            bot.reply_to(message, f"✅ `{uid}` banned.\nReason: {reason}")
            for fn, _ in user_files.get(uid, []):
                sk = f"{uid}_{fn}"
                if sk in bot_scripts:
                    kill_process_tree(bot_scripts[sk])
                    del bot_scripts[sk]
            try: bot.send_message(uid, f"🚫 You have been banned.\nReason: {reason}")
            except: pass
        else:
            bot.reply_to(message, "❌ Failed.")
    except: bot.reply_to(message, "⚠️ Invalid format.")

def _logic_unban_user(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.send_message(message.chat.id, "Enter User ID to unban\n/cancel to abort")
    bot.register_next_step_handler(msg, process_unban_user)

def process_unban_user(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if uid not in banned_users:
            bot.reply_to(message, "ℹ️ User not banned.")
            return
        if unban_user_db(uid):
            bot.reply_to(message, f"✅ `{uid}` unbanned.")
            try: bot.send_message(uid, "✅ You have been unbanned.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def _logic_user_info(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.send_message(message.chat.id, "Enter User ID to get info\n/cancel to abort")
    bot.register_next_step_handler(msg, process_user_info)

def process_user_info(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        text = f"👤 **User ID:** `{uid}`\n"
        if uid == OWNER_ID: text += "👑 Status: Owner"
        elif is_admin(uid): text += "🛡️ Status: Admin"
        elif is_user_banned(uid): text += "🚫 Status: Banned"
        elif is_user_whitelisted(uid): text += "✅ Status: Whitelisted"
        elif is_user_premium(uid): text += "⭐ Status: Premium"
        else: text += "🆓 Status: Free"
        text += f"\n📁 Files: {get_user_file_count(uid)}/{get_user_file_limit(uid) if get_user_file_limit(uid) != float('inf') else '∞'}"
        text += f"\n👥 Referrals: {get_referral_count(uid)}"
        if uid in user_files:
            text += "\n\n📂 **Files:**"
            for fn, ft in user_files[uid]:
                fs = get_file_status(uid, fn)
                text += f"\n• `{fn}` ({ft}) - {fs['status'].upper()}"
        bot.reply_to(message, text, parse_mode='Markdown')
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def _logic_all_users(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    text = "👥 **Active Users:**\n\n"
    for i, uid in enumerate(list(active_users)[:100], 1):
        if uid == OWNER_ID: s = "👑"
        elif is_admin(uid): s = "🛡️"
        elif is_user_banned(uid): s = "🚫"
        elif is_user_whitelisted(uid): s = "✅"
        else: s = "🆓"
        text += f"{i}. `{uid}` {s}\n"
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_set_user_limit(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.send_message(message.chat.id, "Enter `user_id limit` (e.g., `12345678 50`)\n/cancel to abort")
    bot.register_next_step_handler(msg, process_set_user_limit)

def process_set_user_limit(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        parts = message.text.split()
        uid = int(parts[0]); limit = int(parts[1])
        if set_user_limit_db(uid, limit, message.from_user.id):
            bot.reply_to(message, f"✅ Limit {limit} for `{uid}`")
            try: bot.send_message(uid, f"⚙️ Your file limit has been set to {limit}.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid. Format: `user_id limit`")

def _logic_remove_user_limit(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.send_message(message.chat.id, "Enter User ID to remove limit\n/cancel to abort")
    bot.register_next_step_handler(msg, process_remove_user_limit)

def process_remove_user_limit(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if uid not in user_limits:
            bot.reply_to(message, "ℹ️ No custom limit.")
            return
        if remove_user_limit_db(uid):
            bot.reply_to(message, f"✅ Custom limit removed for `{uid}`")
            try: bot.send_message(uid, "ℹ️ Your custom file limit has been removed.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def _logic_system_info(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    text = (f"🤖 **System Info:**\n• Python: {platform.python_version()}\n"
            f"• Platform: {platform.platform()}\n• Uptime: {get_uptime()}\n"
            f"• Running Scripts: {len(bot_scripts)}\n• Active Users: {len(active_users)}")
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_bot_performance(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    try:
        proc = psutil.Process()
        mem = proc.memory_info().rss / 1024 / 1024
        cpu = proc.cpu_percent(interval=0.5)
        text = (f"📈 **Performance:**\n• Memory: {mem:.1f} MB\n• CPU: {cpu:.1f}%\n"
                f"• Running Scripts: {len(bot_scripts)}\n• Active Users: {len(active_users)}\n"
                f"• Bot Status: {'🔒 Locked' if bot_locked else '🔓 Unlocked'}")
        bot.reply_to(message, text, parse_mode='Markdown')
    except: bot.reply_to(message, "❌ Error getting performance data.")

def _logic_cleanup_files(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "🧹 Cleaning empty folders...")
    cleaned = 0
    for d in os.listdir(UPLOAD_BOTS_DIR):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p) and not os.listdir(p):
            try: os.rmdir(p); cleaned += 1
            except: pass
    bot.reply_to(message, f"🧹 Cleaned {cleaned} empty folders!")

def _logic_install_logs(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, module_name, package_name, status, install_date FROM install_logs ORDER BY install_date DESC LIMIT 20')
        logs = c.fetchall()
        conn.close()
    if not logs:
        bot.reply_to(message, "📋 No installation logs.")
        return
    text = "📋 **Install Logs (Last 20):**\n\n"
    for uid, mn, pn, status, date in logs:
        icon = "✅" if status == "success" else "❌" if status == "failed" else "⚠️"
        text += f"{icon} `{uid}`: {mn} → {pn} ({status})\n"
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_bot_logs(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    try:
        with open(os.path.join(IROTECH_DIR, 'bot.log'), 'r', errors='ignore') as f:
            content = f.read()[-3000:]
        bot.send_message(message.chat.id, f"📜 **Bot Logs:**\n```\n{content}\n```", parse_mode='Markdown')
    except: bot.reply_to(message, "❌ No log file found.")

def _logic_file_manager(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    bot.reply_to(message, "📁 **File Manager**", reply_markup=create_file_manager_menu(), parse_mode='Markdown')

def _logic_fm_list_users(message):
    if not is_admin(message.from_user.id): return
    text = "📂 **User Folders:**\n\n"
    total_size = 0
    for d in sorted(os.listdir(UPLOAD_BOTS_DIR)):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p):
            files = os.listdir(p)
            size = sum(os.path.getsize(os.path.join(p, f)) for f in files if os.path.isfile(os.path.join(p, f)))
            total_size += size
            text += f"👤 `{d}` - {len(files)} files ({format_bytes(size)})\n"
    text += f"\n📊 **Total Storage:** {format_bytes(total_size)}"
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_fm_search(message):
    if not is_admin(message.from_user.id): return
    msg = bot.reply_to(message, "🔍 Send file name to search:\n/cancel to abort")
    bot.register_next_step_handler(msg, process_fm_search)

def process_fm_search(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    term = message.text.strip().lower()
    results = []
    for d in os.listdir(UPLOAD_BOTS_DIR):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                if term in fn.lower():
                    results.append(f"👤 `{d}` | 📁 {fn}")
    text = f"🔍 **Results for '{term}':**\n\n"
    if results:
        text += "\n".join(results[:30])
    else: text += "No files found."
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_fm_stats(message):
    if not is_admin(message.from_user.id): return
    total_size = 0; total_files = 0
    for d in os.listdir(UPLOAD_BOTS_DIR):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                fp = os.path.join(p, fn)
                if os.path.isfile(fp):
                    total_files += 1; total_size += os.path.getsize(fp)
    text = f"📊 **Storage Stats:**\n\n📄 Files: {total_files}\n💾 Size: {format_bytes(total_size)}"
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_fm_clean(message):
    if not is_admin(message.from_user.id): return
    cleaned = 0
    for d in os.listdir(UPLOAD_BOTS_DIR):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p) and not os.listdir(p):
            try: os.rmdir(p); cleaned += 1
            except: pass
    bot.reply_to(message, f"🧹 Cleaned {cleaned} empty folders!")

def create_full_backup():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_path = os.path.join(BACKUP_DIR, f'hosting_backup_{ts}.zip')
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        if os.path.isfile(DATABASE_PATH):
            archive.write(DATABASE_PATH, 'bot_data.db')
        if os.path.isdir(UPLOAD_BOTS_DIR):
            for root, dirs, files in os.walk(UPLOAD_BOTS_DIR):
                dirs[:] = [d for d in dirs if d not in ('.venv', 'node_modules', '__pycache__')]
                for name in files:
                    full = os.path.join(root, name)
                    if os.path.abspath(full) == os.path.abspath(archive_path):
                        continue
                    rel = os.path.relpath(full, UPLOAD_BOTS_DIR)
                    archive.write(full, os.path.join('upload_bots', rel))
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('hosting_backup_') and f.endswith('.zip')], reverse=True)
    for old in backups[5:]:
        try: os.remove(os.path.join(BACKUP_DIR, old))
        except OSError: pass
    return archive_path

def _logic_backup(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    try:
        bp = create_full_backup()
        with open(bp, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"✅ Full backup created (database + hosted files).\n💾 Size: {format_bytes(os.path.getsize(bp))}")
    except Exception as e:
        logger.exception('Backup failed')
        bot.reply_to(message, f"❌ Backup error: {e}")

def _logic_network_info(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        text = f"🌐 **Network Info:**\n\n• Hostname: `{hostname}`\n• Local IP: `{local_ip}`\n"
        try:
            ext_ip = requests.get('https://api.ipify.org?format=json', timeout=5).json().get('ip', 'N/A')
            text += f"• External IP: `{ext_ip}`\n"
        except: pass
        io = psutil.net_io_counters()
        text += f"\n**Network I/O:**\n• Sent: {format_bytes(io.bytes_sent)}\n• Received: {format_bytes(io.bytes_recv)}"
        bot.reply_to(message, text, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

def _logic_system_monitor(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        text = (f"📊 **System Monitor:**\n\n**CPU:** {cpu}%\n**RAM:** {mem.percent}% ({format_bytes(mem.used)}/{format_bytes(mem.total)})\n"
                f"**Disk:** {disk.percent}% ({format_bytes(disk.used)}/{format_bytes(disk.total)})\n\n"
                f"**Bot:**\n• Scripts: {len(bot_scripts)}\n• Users: {len(active_users)}\n• Uptime: {get_uptime()}")
        bot.reply_to(message, text, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

def _logic_process_manager(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    try:
        text = "🔧 **Process Manager:**\n\n**Bot Scripts:**\n"
        if bot_scripts:
            for sk, si in bot_scripts.items():
                pid = si['process'].pid
                fn = si['file_name']
                uid = si['script_owner_id']
                start = si['start_time']
                runtime = format_duration((datetime.now() - start).total_seconds())
                text += f"• PID:{pid} | `{fn}` (User:{uid}) | ⏱️{runtime}\n"
        else: text += "(No scripts running)\n"
        text += "\n**Top System Processes:**\n"
        for p in sorted(psutil.process_iter(['pid', 'name', 'memory_percent']), key=lambda x: x.info.get('memory_percent', 0) or 0, reverse=True)[:10]:
            pid = p.info.get('pid', '?')
            name = p.info.get('name', '?')[:15]
            mem = p.info.get('memory_percent', 0)
            text += f"• PID:{pid} | {name} | RAM:{mem:.1f}%\n"
        bot.reply_to(message, text, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

def _logic_run_all_scripts(message_or_call):
    if isinstance(message_or_call, telebot.types.Message):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.chat.id
        reply_func = lambda text, **kwargs: bot.reply_to(message_or_call, text, **kwargs)
        admin_message_obj = message_or_call
    elif isinstance(message_or_call, telebot.types.CallbackQuery):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        reply_func = lambda text, **kwargs: bot.send_message(admin_chat_id, text, **kwargs)
        admin_message_obj = message_or_call.message
    else:
        logger.error("Invalid argument for _logic_run_all_scripts")
        return

    if not is_admin(admin_user_id):
        reply_func("⚠️ Admin permissions required.")
        return

    reply_func("⏳ Starting all scripts...")
    started = 0
    for uid, files in user_files.items():
        for fn, ft in files:
            if not is_bot_running(uid, fn) and get_file_status(uid, fn)['status'] in [FILE_STATUS_APPROVED, FILE_STATUS_AUTO_APPROVED]:
                fpath = os.path.join(get_user_folder(uid), fn)
                fs = get_file_status(uid, fn)
                if fs['file_type'] == 'py':
                    threading.Thread(target=run_script, args=(fpath, uid, get_user_folder(uid), fn, admin_message_obj)).start()
                else:
                    threading.Thread(target=run_js_script, args=(fpath, uid, get_user_folder(uid), fn, admin_message_obj)).start()
                started += 1
                time.sleep(0.5)
    reply_func(f"🚀 Started {started} scripts.")

def _logic_add_mandatory_channel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    msg = bot.send_message(message.chat.id, "📢 Send channel ID or @username\n/cancel to abort")
    bot.register_next_step_handler(msg, process_add_channel)

def process_add_channel(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        chat = bot.get_chat(message.text.strip())
        if save_mandatory_channel(str(chat.id), f"@{chat.username}" if chat.username else "", chat.title, message.from_user.id):
            bot.reply_to(message, f"✅ Added: **{chat.title}**")
        else: bot.reply_to(message, "❌ Failed.")
    except Exception as e: bot.reply_to(message, f"❌ Error: {e}")

def _logic_remove_mandatory_channel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    if not mandatory_channels:
        bot.reply_to(message, "❌ No channels.")
        return
    text = "📢 **Remove Mandatory Channel:**\n\n"
    for cid, info in mandatory_channels.items():
        text += f"• {info['name']} - `/remove_channel_{cid}`\n"
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_list_mandatory_channels(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⚠️ Admin only.")
        return
    text = "📢 **Mandatory Channels:**\n\n"
    for cid, info in mandatory_channels.items():
        text += f"• **{info['name']}**\n  {info.get('username', '') or cid}\n\n"
    if not mandatory_channels: text += "No channels."
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_my_notes(message):
    uid = message.from_user.id
    notes = get_notes(uid)
    text = "📝 **My Notes:**\n\n"
    if notes:
        for nid, note, date in notes[:20]:
            try:
                dt = datetime.fromisoformat(date)
                text += f"📌 {note}\n   📅 {dt.strftime('%Y-%m-%d %H:%M')}\n\n"
            except:
                text += f"📌 {note}\n\n"
        text += f"\nTo delete: `/delnote_{nid}`"
    else:
        text += "No notes yet.\n\nSend `/addnote your note` to add one."
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['addnote'])
def cmd_add_note(message):
    if not message.text or len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: `/addnote your note`", parse_mode='Markdown')
        return
    note = message.text.split(' ', 1)[1]
    if save_note(message.from_user.id, note):
        bot.reply_to(message, f"✅ Note saved!\n\n📌 {note}")
    else:
        bot.reply_to(message, "❌ Failed to save note.")

@bot.message_handler(func=lambda m: m.text.startswith('/delnote_'))
def cmd_delete_note(message):
    try:
        note_id = int(message.text.split('_')[1])
        if delete_note_db(note_id, message.from_user.id):
            bot.reply_to(message, "🗑️ Note deleted!")
        else:
            bot.reply_to(message, "❌ Note not found.")
    except: bot.reply_to(message, "❌ Invalid note ID.")

def _logic_reminders(message):
    uid = message.from_user.id
    rems = get_reminders(uid)
    text = "⏰ **Your Reminders:**\n\n"
    if rems:
        for rid, rtext, rat in rems:
            try:
                dt = datetime.fromisoformat(rat)
                time_left = (dt - datetime.now()).total_seconds()
                if time_left > 0:
                    if time_left < 3600:
                        time_str = f"{int(time_left/60)} minutes"
                    elif time_left < 86400:
                        time_str = f"{int(time_left/3600)} hours"
                    else:
                        time_str = f"{int(time_left/86400)} days"
                    text += f"⏰ {rtext}\n   📅 {dt.strftime('%Y-%m-%d %H:%M')} ({time_str} left)\n\n"
                else:
                    text += f"⏰ {rtext}\n   📅 {dt.strftime('%Y-%m-%d %H:%M')} (⚠️ Overdue!)\n\n"
            except:
                text += f"⏰ {rtext}\n\n"
        text += f"\nTo delete: `/delremind_{rid}`"
    else:
        text += "No active reminders.\n\nSend `/addremind minutes | text` to add one."
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['addremind'])
def cmd_add_remind(message):
    if not message.text or len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: `/addremind 30 | Check my bot`", parse_mode='Markdown')
        return
    try:
        parts = message.text.split(' ', 1)[1].split('|', 1)
        if len(parts) != 2:
            raise ValueError("Format")
        minutes = int(parts[0].strip())
        rtext = parts[1].strip()
        if minutes <= 0 or not rtext:
            bot.reply_to(message, "Invalid input. Use: `minutes | text`")
            return
        remind_at = datetime.now() + timedelta(minutes=minutes)
        if save_reminder(message.from_user.id, rtext, remind_at):
            bot.reply_to(message, f"✅ Reminder set!\n⏰ Will remind in {minutes} minutes\n📅 At: {remind_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            bot.reply_to(message, "❌ Failed to save reminder.")
    except:
        bot.reply_to(message, "Usage: `/addremind 30 | Check my bot`", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text.startswith('/delremind_'))
def cmd_delete_remind(message):
    try:
        rid = int(message.text.split('_')[1])
        if delete_reminder_db(rid, message.from_user.id):
            bot.reply_to(message, "🗑️ Reminder deleted!")
        else:
            bot.reply_to(message, "❌ Reminder not found.")
    except: bot.reply_to(message, "❌ Invalid reminder ID.")

def _logic_referral(message):
    uid = message.from_user.id
    count = get_referral_count(uid)
    referred_users = get_referred_users(uid)
    bot_info = bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
    
    if count >= 10:
        status = "🎉 **PREMIUM UNLOCKED!**"
    else:
        status = f"⏳ Need {10 - count} more referrals"
    
    text = (f"👥 **Referral Program**\n\n"
            f"📊 Your Referrals: **{count} / 10**\n"
            f"🔗 Your Link: `{link}`\n\n"
            f"👤 Referred Users: {len(referred_users)}\n"
            f"Status: {status}\n\n"
            f"Share this link with friends!\n"
            f"🎁 **Reward:** Reach 10 referrals and get 30 days Premium FREE!")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📋 Share Link", 
        url=f"https://t.me/share/url?url={link}&text=Join%20this%20awesome%20bot!"))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    bot.reply_to(message, text, reply_markup=markup, parse_mode='Markdown')

# ====================== FILE UPLOAD HANDLER ======================
@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    uid = message.from_user.id
    chat_id = message.chat.id
    
    if is_user_banned(uid):
        bot.reply_to(message, "❌ Banned.")
        return
    if bot_locked and not is_admin(uid):
        bot.reply_to(message, "⚠️ Bot locked.")
        return
    if get_user_file_count(uid) >= get_user_file_limit(uid):
        bot.reply_to(message, f"⚠️ Limit reached. ({get_user_file_count(uid)}/{get_user_file_limit(uid)})")
        return
    
    doc = message.document
    file_name = os.path.basename(doc.file_name or 'upload.bin')
    if file_name.startswith('hosting_backup_') and file_name.lower().endswith('.zip'):
        if not is_admin(uid):
            bot.reply_to(message, '⚠️ Only admins can restore backups.')
            return
        if (doc.file_size or 0) > MAX_UPLOAD_BYTES:
            bot.reply_to(message, f'❌ Backup too large. Limit: {format_bytes(MAX_UPLOAD_BYTES)}.')
            return
        try:
            file_info = bot.get_file(doc.file_id)
            archive_data = bot.download_file(file_info.file_path)
            pending_path = os.path.join(BACKUP_DIR, 'pending_restore.zip')
            with open(pending_path, 'wb') as out:
                out.write(archive_data)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('⚠️ Confirm Restore', callback_data='confirm_restore'),
                       types.InlineKeyboardButton('Cancel', callback_data='cancel_restore'))
            bot.reply_to(message, '⚠️ Backup received. Restore replaces the current database and uploaded bot files. Confirm only if you trust this archive.', reply_markup=markup)
        except Exception as exc:
            bot.reply_to(message, f'❌ Could not stage restore: {exc}')
        return
    if not file_name or file_name in ('.', '..'):
        bot.reply_to(message, '❌ Invalid file name.')
        return
    if (doc.file_size or 0) > MAX_UPLOAD_BYTES:
        bot.reply_to(message, f'❌ File too large. Maximum upload size: {format_bytes(MAX_UPLOAD_BYTES)}.')
        return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Only .py, .js, .zip allowed.")
        return
    
    try:
        wait_msg = bot.reply_to(message, f"⏳ Downloading `{file_name}`...")
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path)
        bot.edit_message_text("✅ Downloaded. Processing...", chat_id, wait_msg.message_id)
        
        user_folder = get_user_folder(uid)
        file_path = os.path.join(user_folder, file_name)
        with open(file_path, 'wb') as f:
            f.write(content)
        
        if file_ext == '.py':
            handle_py_file(file_path, uid, user_folder, file_name, message)
        elif file_ext == '.js':
            handle_js_file(file_path, uid, user_folder, file_name, message)
        elif file_ext == '.zip':
            handle_zip_file(content, file_name, message)
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ====================== CALLBACK HANDLER ======================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.from_user.id
    data = call.data
    
    if is_user_banned(uid) and data not in ['back_to_main']:
        bot.answer_callback_query(call.id, "❌ Banned.", show_alert=True)
        return
    
    if data not in ['check_subscription_status', 'back_to_main', 'manual_install']:
        is_subscribed, not_joined = check_mandatory_subscription(uid)
        if not is_subscribed and uid not in admin_ids:
            subscription_message, markup = create_subscription_check_message(not_joined)
            bot.answer_callback_query(call.id)
            try:
                bot.edit_message_text(subscription_message, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
            except:
                bot.send_message(call.message.chat.id, subscription_message, reply_markup=markup, parse_mode='Markdown')
            return
    
    # Terminal - Only Owner
    if data == 'terminal':
        if not is_owner(uid):
            bot.answer_callback_query(call.id, "⚠️ Terminal access is only for Owner!", show_alert=True)
            return
        terminal_callback(call)
        return
    
    try:
        if data == 'upload':
            bot.answer_callback_query(call.id)
            _logic_upload_file(call.message)
        
        elif data == 'check_files':
            check_files_callback(call)
        
        elif data.startswith('file_') and not data.startswith('file_manager'):
            file_control_callback(call)
        
        elif data.startswith('start_'):
            start_bot_callback(call)
        
        elif data.startswith('stop_'):
            stop_bot_callback(call)
        
        elif data.startswith('restart_'):
            restart_bot_callback(call)
        
        elif data.startswith('delete_'):
            delete_bot_callback(call)
        
        elif data.startswith('logs_'):
            logs_bot_callback(call)
        
        elif data == 'royal_ai':
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "Use `/royal_ai your question`", parse_mode='Markdown')
        
        elif data == 'uptime':
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"Uptime: `{get_uptime()}`", parse_mode='Markdown')

        elif data == 'dashboard':
            bot.answer_callback_query(call.id, 'Refreshing dashboard...')
            send_live_dashboard(call.message.chat.id, uid)
        
        elif data == 'back_to_main':
            back_to_main_callback(call)
        
        elif data == 'speed':
            speed_callback(call)
        
        elif data == 'stats':
            stats_callback(call)
        
        elif data == 'help':
            _logic_help(call.message)
        
        elif data == 'my_notes':
            _logic_my_notes(call.message)
            bot.answer_callback_query(call.id)
        
        elif data == 'reminders':
            _logic_reminders(call.message)
            bot.answer_callback_query(call.id)
        
        elif data == 'referral':
            _logic_referral(call.message)
            bot.answer_callback_query(call.id)
        
        elif data == 'manual_install':
            bot.answer_callback_query(call.id)
            _logic_manual_install(call.message)
        
        elif data == 'admin_panel':
            admin_panel_callback(call)
        
        elif data == 'add_admin':
            add_admin_init_callback(call)
        
        elif data == 'remove_admin':
            remove_admin_init_callback(call)
        
        elif data == 'list_admins':
            list_admins_callback(call)
        
        elif data == 'subscription':
            subscription_management_callback(call)
        
        elif data == 'add_subscription':
            add_subscription_init_callback(call)
        
        elif data == 'remove_subscription':
            remove_subscription_init_callback(call)
        
        elif data == 'check_subscription':
            check_subscription_init_callback(call)
        
        elif data == 'whitelist_panel':
            whitelist_panel_callback(call)
        
        elif data == 'add_whitelist':
            add_whitelist_callback(call)
        
        elif data == 'remove_whitelist':
            remove_whitelist_callback(call)
        
        elif data == 'list_whitelist':
            list_whitelist_callback(call)
        
        elif data == 'user_management':
            user_management_callback(call)
        
        elif data == 'ban_user':
            ban_user_callback(call)
        
        elif data == 'unban_user':
            unban_user_callback(call)
        
        elif data == 'user_info':
            user_info_callback(call)
        
        elif data == 'all_users':
            all_users_callback(call)
        
        elif data == 'set_user_limit':
            set_user_limit_callback(call)
        
        elif data == 'remove_user_limit':
            remove_user_limit_callback(call)
        
        elif data == 'admin_settings':
            admin_settings_callback(call)
        
        elif data == 'system_info':
            system_info_callback(call)
        
        elif data == 'bot_performance':
            bot_performance_callback(call)
        
        elif data == 'cleanup_files':
            cleanup_files_callback(call)
        
        elif data == 'install_logs':
            install_logs_callback(call)
        
        elif data == 'bot_logs':
            bot_logs_callback(call)
        
        elif data == 'manage_mandatory_channels':
            manage_mandatory_channels_callback(call)
        
        elif data == 'add_mandatory_channel':
            add_mandatory_channel_callback(call)
        
        elif data == 'remove_mandatory_channel':
            remove_mandatory_channel_callback(call)
        
        elif data == 'list_mandatory_channels':
            list_mandatory_channels_callback(call)
        
        elif data == 'file_manager':
            file_manager_callback(call)
        
        elif data == 'fm_list_users':
            fm_list_users_callback(call)
        
        elif data == 'fm_search':
            fm_search_callback(call)
        
        elif data == 'fm_stats':
            fm_stats_callback(call)
        
        elif data == 'fm_clean':
            fm_clean_callback(call)
        
        elif data == 'backup':
            backup_callback(call)

        elif data == 'confirm_restore':
            restore_backup_callback(call)

        elif data == 'cancel_restore':
            if not is_admin(uid):
                bot.answer_callback_query(call.id, 'Admin only.', show_alert=True)
            else:
                try: os.remove(os.path.join(BACKUP_DIR, 'pending_restore.zip'))
                except OSError: pass
                bot.answer_callback_query(call.id, 'Restore cancelled.')
                bot.send_message(call.message.chat.id, '✅ Restore cancelled.')
        
        elif data == 'network_info':
            network_info_callback(call)
        
        elif data == 'system_monitor':
            system_monitor_callback(call)
        
        elif data == 'process_manager':
            process_manager_callback(call)
        
        elif data == 'broadcast':
            broadcast_init_callback(call)
        
        elif data.startswith('confirm_broadcast_'):
            handle_confirm_broadcast(call)
        
        elif data == 'cancel_broadcast':
            handle_cancel_broadcast(call)
        
        elif data == 'lock_bot':
            lock_bot_callback(call)
        
        elif data == 'unlock_bot':
            unlock_bot_callback(call)
        
        elif data == 'run_all_scripts':
            run_all_scripts_callback(call)
        
        elif data == 'all_codes_status':
            all_codes_status_callback(call)
        
        elif data == 'view_pending':
            view_pending_callback(call)
        
        elif data.startswith('review_'):
            review_callback(call)
        
        elif data.startswith('approve_'):
            handle_approve_callback(call)
        
        elif data.startswith('reject_'):
            handle_reject_callback(call)
        
        elif data == 'check_subscription_status':
            check_subscription_status_callback(call)
        
        else:
            bot.answer_callback_query(call.id, "Unknown action.")
    except Exception as e:
        logger.error(f"Callback error {data}: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)
        except: pass

def send_live_dashboard(chat_id, uid):
    """Send a current live resource and hosted-process summary."""
    try:
        cpu = psutil.cpu_percent(interval=0.25)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        running = []
        stopped = []
        for key, info in list(bot_scripts.items()):
            proc = info.get('process')
            try:
                if proc and proc.poll() is None:
                    running.append((key, info))
                else:
                    stopped.append((key, info))
            except Exception:
                stopped.append((key, info))
        text = ("📈 **LIVE HOSTING DASHBOARD**\n\n"
                f"🟢 Running bots: {len(running)}\n🔴 Stopped/exited tracked: {len(stopped)}\n"
                f"👥 Users: {len(active_users)}\n📦 Stored bot files: {sum(len(x) for x in user_files.values())}\n"
                f"⚙️ CPU: {cpu}%\n🧠 RAM: {mem.percent}% ({format_bytes(mem.used)} / {format_bytes(mem.total)})\n"
                f"💽 Disk: {disk.percent}% ({format_bytes(disk.used)} / {format_bytes(disk.total)})\n"
                f"⏱️ Hosting service uptime: {get_uptime()}")
        if is_admin(uid):
            text += f"\n\n🛡️ Sandbox: {'Docker available' if _docker_available() else 'Docker unavailable — fallback is not fully isolated'}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('🔄 Refresh', callback_data='dashboard'),
                   types.InlineKeyboardButton('📂 My Bots', callback_data='check_files'))
        if is_admin(uid):
            markup.add(types.InlineKeyboardButton('📊 System Monitor', callback_data='system_monitor'),
                       types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'))
        markup.add(types.InlineKeyboardButton('🔙 Main Menu', callback_data='back_to_main'))
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')
    except Exception as exc:
        logger.exception('Dashboard error')
        bot.send_message(chat_id, f'❌ Dashboard error: {str(exc)[:300]}')

def hosted_process_monitor():
    """Notify users about exits and retry a bounded number of times."""
    while True:
        try:
            for key, info in list(bot_scripts.items()):
                proc = info.get('process')
                if not proc:
                    continue
                try:
                    exit_code = proc.poll()
                except Exception:
                    exit_code = None
                if exit_code is None:
                    continue
                # Remove stale entries before restart so is_bot_running does not block it.
                bot_scripts.pop(key, None)
                log_path = os.path.join(info.get('user_folder', ''), f"{os.path.splitext(info.get('file_name', 'bot'))[0]}.log")
                log_tail = ''
                try:
                    if os.path.isfile(log_path):
                        with open(log_path, 'r', encoding='utf-8', errors='ignore') as lf_read:
                            log_tail = lf_read.read()[-12000:]
                except Exception:
                    pass
                try:
                    lf = info.get('log_file')
                    if lf and not lf.closed:
                        lf.write(f'\n===== EXIT {datetime.now().isoformat()} code={exit_code} =====\n')
                        lf.flush(); lf.close()
                except Exception:
                    pass
                # Recover missing dependencies independently from ordinary crash restarts.
                # The next launch installs the script-specific auto-requirements list first.
                user_folder = info.get('user_folder', '')
                dependency_recovery = False
                dependency_attempt = int(info.get('dependency_retry_count', 0))
                if info.get('type') == 'py':
                    match = re.search(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", log_tail)
                    if match:
                        module = match.group(1).split('.')[0]
                        package = TELEGRAM_MODULES.get(module, TELEGRAM_MODULES.get(module.lower(), module))
                        # Do not pip-install Python's standard library or a local project module.
                        local_module = os.path.isfile(os.path.join(user_folder, module + '.py')) or os.path.isdir(os.path.join(user_folder, module))
                        stdlib_module = module in getattr(sys, 'stdlib_module_names', set())
                        if not local_module and not stdlib_module and re.fullmatch(r'[A-Za-z0-9_.-]+', package):
                            safe_tag = re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.splitext(info.get('file_name', 'bot'))[0])[:80] or 'bot'
                            auto_req = os.path.join(user_folder, f'.auto_requirements_{safe_tag}.txt')
                            try:
                                existing = [line.strip() for line in open(auto_req, encoding='utf-8').read().splitlines()] if os.path.isfile(auto_req) else []
                                if package not in existing and dependency_attempt < MAX_DEPENDENCY_RETRIES:
                                    with open(auto_req, 'a', encoding='utf-8') as req_file:
                                        req_file.write(package + '\n')
                                    dependency_recovery = True
                                    dependency_attempt += 1
                                    logger.info('Queued missing Python dependency %s for %s (%s/%s)', package, info.get('file_name', 'bot'), dependency_attempt, MAX_DEPENDENCY_RETRIES)
                            except Exception:
                                logger.exception('Could not queue missing Python package')
                elif info.get('type') == 'js':
                    match = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", log_tail)
                    if match:
                        package = match.group(1)
                        if not package.startswith(('.', '/')) and re.fullmatch(r'[A-Za-z0-9@._/-]+', package):
                            safe_tag = re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.splitext(info.get('file_name', 'bot'))[0])[:80] or 'bot'
                            auto_npm = os.path.join(user_folder, f'.auto_npm_packages_{safe_tag}.txt')
                            try:
                                existing = [line.strip() for line in open(auto_npm, encoding='utf-8').read().splitlines()] if os.path.isfile(auto_npm) else []
                                if package not in existing and dependency_attempt < MAX_DEPENDENCY_RETRIES:
                                    with open(auto_npm, 'a', encoding='utf-8') as req_file:
                                        req_file.write(package + '\n')
                                    dependency_recovery = True
                                    dependency_attempt += 1
                            except Exception:
                                logger.exception('Could not queue missing npm package')
                uid = int(info.get('script_owner_id', 0))
                chat_id = int(info.get('chat_id', uid))
                fn = info.get('file_name', 'bot')
                count = int(info.get('restart_count', 0))
                if info.get('last_notified_exit') != exit_code:
                    try:
                        bot.send_message(chat_id, f'⚠️ Bot `{fn}` stopped (exit code: {exit_code}). Check Logs for details.', parse_mode='Markdown')
                    except Exception:
                        pass
                may_restart = dependency_recovery or count < MAX_AUTO_RESTARTS
                if may_restart and not info.get('stopping_by_user'):
                    try:
                        if dependency_recovery:
                            bot.send_message(chat_id, f'📦 Missing dependency detected for `{fn}`. Installing `{package}` and retrying in {AUTO_RESTART_DELAY}s ({dependency_attempt}/{MAX_DEPENDENCY_RETRIES}).', parse_mode='Markdown')
                        else:
                            bot.send_message(chat_id, f'🔄 Auto-restarting `{fn}` ({count + 1}/{MAX_AUTO_RESTARTS}) in {AUTO_RESTART_DELAY}s.', parse_mode='Markdown')
                    except Exception:
                        pass
                    time.sleep(max(1, AUTO_RESTART_DELAY))
                    msg_obj = info.get('message_obj')
                    if msg_obj is not None:
                        # Dependency repairs do not consume the normal crash-restart budget.
                        next_attempt = count + 1 if dependency_recovery else count + 2
                        threading.Thread(target=(run_script if info.get('type') == 'py' else run_js_script),
                                         args=(os.path.join(info.get('user_folder', ''), fn), uid,
                                               info.get('user_folder', get_user_folder(uid)), fn, msg_obj,
                                               next_attempt, dependency_attempt), daemon=True).start()
                        time.sleep(1)
                        new_info = bot_scripts.get(key)
                        if new_info:
                            new_info['restart_count'] = count if dependency_recovery else count + 1
                            new_info['dependency_retry_count'] = dependency_attempt
                            new_info['last_notified_exit'] = exit_code
                else:
                    try:
                        bot.send_message(chat_id, f'🛑 `{fn}` stopped and reached the auto-restart limit ({MAX_AUTO_RESTARTS}).', parse_mode='Markdown')
                    except Exception:
                        pass
        except Exception as exc:
            logger.exception('Hosted process monitor error: %s', exc)
        time.sleep(5)

# ====================== CALLBACK FUNCTIONS ======================

def check_files_callback(call):
    uid = call.from_user.id
    ufl = user_files.get(uid, [])
    if not ufl:
        bot.answer_callback_query(call.id, "⚠️ No files.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn, ft in sorted(ufl):
        is_run = is_bot_running(uid, fn)
        si = "🟢" if is_run else "⚪"
        markup.add(types.InlineKeyboardButton(f"{fn} ({ft}) - {si}", callback_data=f'file_{uid}_{fn}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    try:
        bot.edit_message_text("📁 **Your Files:**", call.message.chat.id, call.message.message_id, 
                             reply_markup=markup, parse_mode='Markdown')
    except: pass

def file_control_callback(call):
    _, oid, fn = call.data.split('_', 2)
    oid = int(oid)
    if call.from_user.id != oid and not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Not your file.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    is_run = is_bot_running(oid, fn)
    try:
        bot.edit_message_text(f"⚙️ `{fn}`\nStatus: {'🟢 Running' if is_run else '🔴 Stopped'}",
                             call.message.chat.id, call.message.message_id,
                             reply_markup=create_control_buttons(oid, fn, is_run), parse_mode='Markdown')
    except: pass

def start_bot_callback(call):
    _, oid, fn = call.data.split('_', 2)
    oid = int(oid)
    if call.from_user.id != oid and not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
        return
    fs = get_file_status(oid, fn)
    if fs['status'] not in [FILE_STATUS_APPROVED, FILE_STATUS_AUTO_APPROVED]:
        bot.answer_callback_query(call.id, f"⚠️ Status: {fs['status'].upper()}", show_alert=True)
        return
    bot.answer_callback_query(call.id, "⏳ Starting...")
    fpath = os.path.join(get_user_folder(oid), fn)
    if fs['file_type'] == 'py':
        threading.Thread(target=run_script, args=(fpath, oid, get_user_folder(oid), fn, call.message)).start()
    else:
        threading.Thread(target=run_js_script, args=(fpath, oid, get_user_folder(oid), fn, call.message)).start()

def stop_bot_callback(call):
    _, oid, fn = call.data.split('_', 2)
    oid = int(oid)
    if call.from_user.id != oid and not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
        return
    bot.answer_callback_query(call.id, "⏳ Stopping...")
    sk = f"{oid}_{fn}"
    if sk in bot_scripts:
        bot_scripts[sk]['stopping_by_user'] = True
        kill_process_tree(bot_scripts[sk])
        del bot_scripts[sk]

def restart_bot_callback(call):
    _, oid, fn = call.data.split('_', 2)
    oid = int(oid)
    if call.from_user.id != oid and not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
        return
    bot.answer_callback_query(call.id, "⏳ Restarting...")
    sk = f"{oid}_{fn}"
    if sk in bot_scripts:
        bot_scripts[sk]['stopping_by_user'] = True
        kill_process_tree(bot_scripts[sk])
        del bot_scripts[sk]
    time.sleep(1)
    fpath = os.path.join(get_user_folder(oid), fn)
    fs = get_file_status(oid, fn)
    if fs['file_type'] == 'py':
        threading.Thread(target=run_script, args=(fpath, oid, get_user_folder(oid), fn, call.message)).start()
    else:
        threading.Thread(target=run_js_script, args=(fpath, oid, get_user_folder(oid), fn, call.message)).start()

def delete_bot_callback(call):
    _, oid, fn = call.data.split('_', 2)
    oid = int(oid)
    if call.from_user.id != oid and not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
        return
    bot.answer_callback_query(call.id, "🗑️ Deleting...")
    sk = f"{oid}_{fn}"
    if sk in bot_scripts:
        bot_scripts[sk]['stopping_by_user'] = True
        kill_process_tree(bot_scripts[sk])
        del bot_scripts[sk]
    remove_user_file_db(oid, fn)
    try: os.remove(os.path.join(get_user_folder(oid), fn))
    except: pass
    try: bot.edit_message_text(f"🗑️ `{fn}` deleted!", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except: pass

def logs_bot_callback(call):
    _, oid, fn = call.data.split('_', 2)
    oid = int(oid)
    if call.from_user.id != oid and not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Denied.", show_alert=True)
        return
    lp = os.path.join(get_user_folder(oid), f"{os.path.splitext(fn)[0]}.log")
    if not os.path.exists(lp):
        bot.answer_callback_query(call.id, "⚠️ No logs.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        with open(lp, 'r', errors='ignore') as f:
            content = f.read()[-3000:]
        bot.send_message(call.message.chat.id, f"📜 Logs for `{fn}`:\n```\n{content}\n```", parse_mode='Markdown')
    except:
        bot.send_message(call.message.chat.id, f"❌ Error reading logs for `{fn}`.")

def back_to_main_callback(call):
    uid = call.from_user.id
    fl = get_user_file_limit(uid)
    cf = get_user_file_count(uid)
    ls = str(fl) if fl != float('inf') else "Unlimited"
    if uid == OWNER_ID: us = "👑 Owner"
    elif is_admin(uid): us = "🛡️ Admin"
    elif is_user_premium(uid): us = "⭐ Premium"
    else: us = "🆓 Free"
    
    terminal_info = "\n🔒 **You have Terminal Access!**" if is_owner(uid) else ""
    
    text = f"〽️ **Main Menu**\n\n🆔 `{uid}`\n🔰 {us}\n📁 {cf}/{ls}\n⏱️ {get_uptime()}{terminal_info}"
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_main_menu_inline(uid), parse_mode='Markdown')
    except: pass

def speed_callback(call):
    uid = call.from_user.id
    start = time.time()
    try:
        bot.edit_message_text("🏃 Testing...", call.message.chat.id, call.message.message_id)
        bot.send_chat_action(call.message.chat.id, 'typing')
        rt = round((time.time() - start) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if uid == OWNER_ID: ul = "👑 Owner"
        elif is_admin(uid): ul = "🛡️ Admin"
        elif is_user_premium(uid): ul = "⭐ Premium"
        else: ul = "🆓 Free"
        msg = f"⚡ **Speed:**\n⏱️ {rt} ms\n🚦 {status}\n👤 {ul}"
        bot.answer_callback_query(call.id)
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id,
                             reply_markup=create_main_menu_inline(uid), parse_mode='Markdown')
    except: pass

def stats_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    total = len(active_users)
    files = sum(len(f) for f in user_files.values())
    running = len(bot_scripts)
    pending = get_pending_files_count()
    text = f"📊 **Bot Statistics:**\n\n👥 Users: {total}\n📂 Files: {files}\n🟢 Running: {running}\n🚫 Banned: {len(banned_users)}"
    if is_admin(uid):
        text += f"\n📋 Pending: {pending}\n🔒 Status: {'Locked' if bot_locked else 'Unlocked'}"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_main_menu_inline(uid), parse_mode='Markdown')
    except: pass

def lock_bot_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    global bot_locked
    bot_locked = True
    bot.answer_callback_query(call.id, "🔒 Bot locked.")

def unlock_bot_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    global bot_locked
    bot_locked = False
    bot.answer_callback_query(call.id, "🔓 Bot unlocked.")

# ====================== TERMINAL CALLBACK ======================
def terminal_callback(call):
    # Only Owner can access terminal
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ **Terminal access is only for Owner!**", show_alert=True)
        return
    
    terminal_mode_users.add(call.from_user.id)
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("💻 **Terminal Mode Activated!**\n\n"
                             "Send commands directly.\n"
                             "Send `/cancel` to exit.\n"
                             "⚠️ Use with caution!\n"
                             "🔒 **Owner Only Access**",
                             call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except: pass

# ====================== ADMIN PANEL CALLBACKS ======================
def admin_panel_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("👑 Admin Panel", call.message.chat.id, call.message.message_id,
                             reply_markup=create_admin_panel())
    except: pass

def add_admin_init_callback(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter User ID to promote.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID: return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        new_id = int(message.text.strip())
        if new_id == OWNER_ID:
            bot.reply_to(message, "⚠️ Already owner.")
            return
        if is_admin(new_id):
            bot.reply_to(message, "⚠️ Already admin.")
            return
        add_admin_db(new_id, message.from_user.id)
        bot.reply_to(message, f"✅ `{new_id}` promoted to Admin.")
        try: bot.send_message(new_id, "🎉 You are now an Admin!")
        except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def remove_admin_init_callback(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter Admin ID to remove.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID: return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        aid = int(message.text.strip())
        if aid == OWNER_ID:
            bot.reply_to(message, "⚠️ Cannot remove owner.")
            return
        if not is_admin(aid):
            bot.reply_to(message, "⚠️ Not an admin.")
            return
        if remove_admin_db(aid):
            bot.reply_to(message, f"✅ `{aid}` removed.")
            try: bot.send_message(aid, "ℹ️ You are no longer an Admin.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def list_admins_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    text = "👑 **Admins:**\n\n"
    for aid in sorted(admin_ids):
        text += f"- `{aid}` {'(Owner)' if aid == OWNER_ID else ''}\n"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_admin_panel(), parse_mode='Markdown')
    except: pass

# ====================== SUBSCRIPTION CALLBACKS ======================
def subscription_management_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("💳 Subscription Management", call.message.chat.id, call.message.message_id,
                             reply_markup=create_subscription_menu())
    except: pass

def add_subscription_init_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter `user_id days` (e.g., `12345678 30`)\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_subscription_details)

def process_add_subscription_details(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        parts = message.text.split()
        uid = int(parts[0]); days = int(parts[1])
        exp = datetime.now() + timedelta(days=days)
        save_subscription(uid, exp)
        bot.reply_to(message, f"✅ Sub for `{uid}` +{days} days.\nExpires: {exp:%Y-%m-%d}")
        try: bot.send_message(uid, f"🎉 Subscription added! {days} days.\nExpires: {exp:%Y-%m-%d}")
        except: pass
    except: bot.reply_to(message, "⚠️ Invalid. Format: `ID days`")

def remove_subscription_init_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter User ID to remove sub.\n/cancel to abort")
    bot.register_next_step_handler(msg, process_remove_subscription_id)

def process_remove_subscription_id(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if uid not in user_subscriptions:
            bot.reply_to(message, "⚠️ No active sub.")
            return
        remove_subscription_db(uid)
        bot.reply_to(message, f"✅ Sub removed for `{uid}`.")
        try: bot.send_message(uid, "ℹ️ Your subscription has been removed.")
        except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def check_subscription_init_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter User ID to check.\n/cancel to abort")
    bot.register_next_step_handler(msg, process_check_subscription_id)

def process_check_subscription_id(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            exp = user_subscriptions[uid].get('expiry')
            if exp and exp > datetime.now():
                days = (exp - datetime.now()).days
                bot.reply_to(message, f"✅ `{uid}` active sub.\nExpires: {exp:%Y-%m-%d} ({days} days left)")
            else:
                bot.reply_to(message, f"⚠️ `{uid}` expired.")
                remove_subscription_db(uid)
        else: bot.reply_to(message, f"ℹ️ `{uid}` no sub.")
    except: bot.reply_to(message, "⚠️ Invalid ID.")

# ====================== WHITELIST CALLBACKS ======================
def whitelist_panel_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("👥 **Whitelist Management**", call.message.chat.id, call.message.message_id,
                             reply_markup=create_whitelist_panel(), parse_mode='Markdown')
    except: pass

def add_whitelist_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter User ID to whitelist.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_whitelist_cb)

def process_add_whitelist_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if is_user_whitelisted(uid):
            bot.reply_to(message, f"User `{uid}` already whitelisted.")
            return
        if add_user_to_whitelist(uid, message.from_user.id):
            bot.reply_to(message, f"✅ `{uid}` whitelisted.")
            try: bot.send_message(uid, "🎉 **You are whitelisted!**\nFiles auto-approved now.", parse_mode='Markdown')
            except: pass
        else: bot.reply_to(message, "❌ Failed.")
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def remove_whitelist_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter User ID to remove.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_whitelist_cb)

def process_remove_whitelist_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if not is_user_whitelisted(uid):
            bot.reply_to(message, f"User `{uid}` not whitelisted.")
            return
        if remove_user_from_whitelist(uid):
            bot.reply_to(message, f"✅ `{uid}` removed from whitelist.")
            try: bot.send_message(uid, "⚠️ You are no longer whitelisted.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def list_whitelist_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    text = "👥 **Whitelisted Users:**\n\n"
    for uid in sorted(whitelist_users):
        text += f"- `{uid}`\n"
    if not whitelist_users: text += "No whitelisted users."
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_whitelist_panel(), parse_mode='Markdown')
    except: pass

# ====================== USER MANAGEMENT CALLBACKS ======================
def user_management_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("👥 User Management", call.message.chat.id, call.message.message_id,
                             reply_markup=create_user_management_menu())
    except: pass

def ban_user_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter `user_id reason`\nExample: `12345678 Spamming`\n/cancel to abort")
    bot.register_next_step_handler(msg, process_ban_user_cb)

def process_ban_user_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        parts = message.text.split()
        uid = int(parts[0]); reason = ' '.join(parts[1:])
        if uid == OWNER_ID:
            bot.reply_to(message, "⚠️ Cannot ban owner.")
            return
        if is_admin(uid):
            bot.reply_to(message, "⚠️ Cannot ban admin.")
            return
        if ban_user_db(uid, reason, message.from_user.id):
            bot.reply_to(message, f"✅ `{uid}` banned.\nReason: {reason}")
            for fn, _ in user_files.get(uid, []):
                sk = f"{uid}_{fn}"
                if sk in bot_scripts:
                    kill_process_tree(bot_scripts[sk])
                    del bot_scripts[sk]
            try: bot.send_message(uid, f"🚫 You have been banned.\nReason: {reason}")
            except: pass
        else: bot.reply_to(message, "❌ Failed.")
    except: bot.reply_to(message, "⚠️ Invalid format.")

def unban_user_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter User ID to unban\n/cancel to abort")
    bot.register_next_step_handler(msg, process_unban_user_cb)

def process_unban_user_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if uid not in banned_users:
            bot.reply_to(message, "ℹ️ User not banned.")
            return
        if unban_user_db(uid):
            bot.reply_to(message, f"✅ `{uid}` unbanned.")
            try: bot.send_message(uid, "✅ You have been unbanned.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def user_info_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter User ID to get info\n/cancel to abort")
    bot.register_next_step_handler(msg, process_user_info_cb)

def process_user_info_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        text = f"👤 **User ID:** `{uid}`\n"
        if uid == OWNER_ID: text += "👑 Status: Owner"
        elif is_admin(uid): text += "🛡️ Status: Admin"
        elif is_user_banned(uid): text += "🚫 Status: Banned"
        elif is_user_whitelisted(uid): text += "✅ Status: Whitelisted"
        elif is_user_premium(uid): text += "⭐ Status: Premium"
        else: text += "🆓 Status: Free"
        text += f"\n📁 Files: {get_user_file_count(uid)}/{get_user_file_limit(uid) if get_user_file_limit(uid) != float('inf') else '∞'}"
        text += f"\n👥 Referrals: {get_referral_count(uid)}"
        bot.reply_to(message, text, parse_mode='Markdown')
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def all_users_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    text = "👥 **Active Users:**\n\n"
    for i, uid in enumerate(list(active_users)[:50], 1):
        if uid == OWNER_ID: s = "👑"
        elif is_admin(uid): s = "🛡️"
        elif is_user_banned(uid): s = "🚫"
        elif is_user_whitelisted(uid): s = "✅"
        else: s = "🆓"
        text += f"{i}. `{uid}` {s}\n"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except: pass

def set_user_limit_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter `user_id limit` (e.g., `12345678 50`)\n/cancel to abort")
    bot.register_next_step_handler(msg, process_set_user_limit_cb)

def process_set_user_limit_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        parts = message.text.split()
        uid = int(parts[0]); limit = int(parts[1])
        if set_user_limit_db(uid, limit, message.from_user.id):
            bot.reply_to(message, f"✅ Limit {limit} for `{uid}`")
            try: bot.send_message(uid, f"⚙️ Your file limit has been set to {limit}.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid. Format: `user_id limit`")

def remove_user_limit_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter User ID to remove limit\n/cancel to abort")
    bot.register_next_step_handler(msg, process_remove_user_limit_cb)

def process_remove_user_limit_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if uid not in user_limits:
            bot.reply_to(message, "ℹ️ No custom limit.")
            return
        if remove_user_limit_db(uid):
            bot.reply_to(message, f"✅ Custom limit removed for `{uid}`")
            try: bot.send_message(uid, "ℹ️ Your custom file limit has been removed.")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

# ====================== ADMIN SETTINGS CALLBACKS ======================
def admin_settings_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("⚙️ Admin Settings", call.message.chat.id, call.message.message_id,
                             reply_markup=create_admin_settings_menu())
    except: pass

def system_info_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    text = (f"🤖 **System Info:**\n• Python: {platform.python_version()}\n"
            f"• Platform: {platform.platform()}\n• Uptime: {get_uptime()}\n"
            f"• Running Scripts: {len(bot_scripts)}\n• Active Users: {len(active_users)}")
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except: pass

def bot_performance_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        proc = psutil.Process()
        mem = proc.memory_info().rss / 1024 / 1024
        cpu = proc.cpu_percent(interval=0.5)
        text = (f"📈 **Performance:**\n• Memory: {mem:.1f} MB\n• CPU: {cpu:.1f}%\n"
                f"• Running Scripts: {len(bot_scripts)}\n• Active Users: {len(active_users)}")
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except: pass

def cleanup_files_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id, "🧹 Cleaning...")
    cleaned = 0
    for d in os.listdir(UPLOAD_BOTS_DIR):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p) and not os.listdir(p):
            try: os.rmdir(p); cleaned += 1
            except: pass
    try:
        bot.edit_message_text(f"🧹 Cleaned {cleaned} empty folders!", call.message.chat.id, call.message.message_id,
                             reply_markup=create_admin_settings_menu())
    except: pass

def install_logs_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, module_name, package_name, status, install_date FROM install_logs ORDER BY install_date DESC LIMIT 20')
        logs = c.fetchall()
        conn.close()
    if not logs:
        try: bot.edit_message_text("📋 No installation logs.", call.message.chat.id, call.message.message_id)
        except: return
    text = "📋 **Install Logs (Last 20):**\n\n"
    for uid, mn, pn, status, date in logs:
        icon = "✅" if status == "success" else "❌" if status == "failed" else "⚠️"
        text += f"{icon} `{uid}`: {mn} → {pn} ({status})\n"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except: pass

def bot_logs_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        with open(os.path.join(IROTECH_DIR, 'bot.log'), 'r', errors='ignore') as f:
            content = f.read()[-3000:]
        bot.send_message(call.message.chat.id, f"📜 **Bot Logs:**\n```\n{content}\n```", parse_mode='Markdown')
    except: pass

# ====================== MANDATORY CHANNELS CALLBACKS ======================
def manage_mandatory_channels_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("📢 Manage Channels", call.message.chat.id, call.message.message_id,
                             reply_markup=create_mandatory_channels_menu())
    except: pass

def add_mandatory_channel_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Send channel ID or @username\n/cancel to abort")
    bot.register_next_step_handler(msg, process_add_channel_cb)

def process_add_channel_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    try:
        chat = bot.get_chat(message.text.strip())
        if save_mandatory_channel(str(chat.id), f"@{chat.username}" if chat.username else "", chat.title, message.from_user.id):
            bot.reply_to(message, f"✅ Added: **{chat.title}**")
        else: bot.reply_to(message, "❌ Failed.")
    except Exception as e: bot.reply_to(message, f"❌ Error: {e}")

def remove_mandatory_channel_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    if not mandatory_channels:
        bot.answer_callback_query(call.id, "❌ No channels.", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup()
    for cid, info in mandatory_channels.items():
        markup.add(types.InlineKeyboardButton(f"🗑️ {info['name']}", callback_data=f'remove_channel_{cid}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='manage_mandatory_channels'))
    try:
        bot.edit_message_text("Choose channel to delete:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except: pass

def list_mandatory_channels_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    text = "📢 **Mandatory Channels:**\n\n"
    for cid, info in mandatory_channels.items():
        text += f"• **{info['name']}**\n  {info.get('username', '') or cid}\n\n"
    if not mandatory_channels: text += "No channels."
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_mandatory_channels_menu(), parse_mode='Markdown')
    except: pass

# ====================== FILE MANAGER CALLBACKS ======================
def file_manager_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("📁 **File Manager**", call.message.chat.id, call.message.message_id,
                             reply_markup=create_file_manager_menu())
    except: pass

def fm_list_users_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    text = "📂 **User Folders:**\n\n"
    total_size = 0
    for d in sorted(os.listdir(UPLOAD_BOTS_DIR)):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p):
            files = os.listdir(p)
            size = sum(os.path.getsize(os.path.join(p, f)) for f in files if os.path.isfile(os.path.join(p, f)))
            total_size += size
            text += f"👤 `{d}` - {len(files)} files ({format_bytes(size)})\n"
    text += f"\n📊 **Total Storage:** {format_bytes(total_size)}"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except: pass

def fm_search_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔍 Send file name to search:\n/cancel to abort")
    bot.register_next_step_handler(msg, process_fm_search_cb)

def process_fm_search_cb(message):
    if not is_admin(message.from_user.id): return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled.")
        return
    term = message.text.strip().lower()
    results = []
    for d in os.listdir(UPLOAD_BOTS_DIR):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                if term in fn.lower():
                    results.append(f"👤 `{d}` | 📁 {fn}")
    text = f"🔍 **Results for '{term}':**\n\n"
    if results:
        text += "\n".join(results[:30])
    else: text += "No files found."
    bot.reply_to(message, text, parse_mode='Markdown')

def fm_stats_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    total_size = 0; total_files = 0
    for d in os.listdir(UPLOAD_BOTS_DIR):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                fp = os.path.join(p, fn)
                if os.path.isfile(fp):
                    total_files += 1; total_size += os.path.getsize(fp)
    text = f"📊 **Storage Stats:**\n\n📄 Files: {total_files}\n💾 Size: {format_bytes(total_size)}"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                             reply_markup=create_file_manager_menu(), parse_mode='Markdown')
    except: pass

def fm_clean_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id, "🧹 Cleaning...")
    cleaned = 0
    for d in os.listdir(UPLOAD_BOTS_DIR):
        p = os.path.join(UPLOAD_BOTS_DIR, d)
        if os.path.isdir(p) and not os.listdir(p):
            try: os.rmdir(p); cleaned += 1
            except: pass
    try:
        bot.edit_message_text(f"🧹 Cleaned {cleaned} empty folders!", call.message.chat.id, call.message.message_id,
                             reply_markup=create_file_manager_menu())
    except: pass

# ====================== SYSTEM TOOLS CALLBACKS ======================
def backup_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    bot.answer_callback_query(call.id, "💾 Creating full backup...")
    try:
        bp = create_full_backup()
        with open(bp, 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption=f"✅ Full backup created (database + hosted files).\n💾 Size: {format_bytes(os.path.getsize(bp))}")
    except Exception as e:
        logger.exception('Backup failed')
        bot.send_message(call.message.chat.id, f"❌ Backup error: {e}")

def restore_backup_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, 'Admin only.', show_alert=True)
        return
    pending = os.path.join(BACKUP_DIR, 'pending_restore.zip')
    if not os.path.isfile(pending):
        bot.answer_callback_query(call.id, 'No staged backup found.', show_alert=True)
        return
    staging = tempfile.mkdtemp(prefix='restore_check_')
    try:
        with zipfile.ZipFile(pending, 'r') as archive:
            total = 0
            for info in archive.infolist():
                name = info.filename.replace('\\\\', '/')
                if name.startswith('/') or any(part == '..' for part in name.split('/')):
                    raise ValueError('Unsafe path in backup archive.')
                total += info.file_size
                if total > 500 * 1024 * 1024:
                    raise ValueError('Backup expands beyond 500 MB.')
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError('Symlinks are not allowed in backup archives.')
            archive.extractall(staging)
        db_src = os.path.join(staging, 'bot_data.db')
        files_src = os.path.join(staging, 'upload_bots')
        if not os.path.isfile(db_src):
            raise ValueError('Backup is missing bot_data.db.')
        # Validate DB before replacing the current one.
        conn = sqlite3.connect(db_src)
        integrity = conn.execute('PRAGMA integrity_check').fetchone()
        conn.close()
        if not integrity or integrity[0] != 'ok':
            raise ValueError('Backup database failed integrity check.')
        if os.path.isfile(DATABASE_PATH):
            shutil.copy2(DATABASE_PATH, DATABASE_PATH + '.pre_restore')
        shutil.copy2(db_src, DATABASE_PATH)
        if os.path.isdir(files_src):
            for name in os.listdir(UPLOAD_BOTS_DIR):
                target = os.path.join(UPLOAD_BOTS_DIR, name)
                try:
                    if os.path.isdir(target): shutil.rmtree(target)
                    else: os.remove(target)
                except OSError: logger.warning('Could not clear restore target %s', target)
            for name in os.listdir(files_src):
                src = os.path.join(files_src, name)
                dst = os.path.join(UPLOAD_BOTS_DIR, name)
                if os.path.isdir(src): shutil.copytree(src, dst, dirs_exist_ok=True)
                else: shutil.copy2(src, dst)
        try: os.remove(pending)
        except OSError: pass
        bot.answer_callback_query(call.id, 'Restore complete.')
        bot.send_message(call.message.chat.id, '✅ Restore completed. Restart the hosting bot process to reload database-backed in-memory state.')
    except Exception as exc:
        logger.exception('Restore failed')
        bot.answer_callback_query(call.id, 'Restore failed.', show_alert=True)
        bot.send_message(call.message.chat.id, f'❌ Restore failed: {str(exc)[:700]}')
    finally:
        shutil.rmtree(staging, ignore_errors=True)

def network_info_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        text = f"🌐 **Network Info:**\n\n• Hostname: `{hostname}`\n• Local IP: `{local_ip}`\n"
        try:
            ext_ip = requests.get('https://api.ipify.org?format=json', timeout=5).json().get('ip', 'N/A')
            text += f"• External IP: `{ext_ip}`\n"
        except: pass
        io = psutil.net_io_counters()
        text += f"\n**Network I/O:**\n• Sent: {format_bytes(io.bytes_sent)}\n• Received: {format_bytes(io.bytes_recv)}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", call.message.chat.id, call.message.message_id)

def system_monitor_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        text = (f"📊 **System Monitor:**\n\n**CPU:** {cpu}%\n**RAM:** {mem.percent}% ({format_bytes(mem.used)}/{format_bytes(mem.total)})\n"
                f"**Disk:** {disk.percent}% ({format_bytes(disk.used)}/{format_bytes(disk.total)})\n\n"
                f"**Bot:**\n• Scripts: {len(bot_scripts)}\n• Users: {len(active_users)}\n• Uptime: {get_uptime()}")
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", call.message.chat.id, call.message.message_id)

def process_manager_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        text = "🔧 **Process Manager:**\n\n**Bot Scripts:**\n"
        if bot_scripts:
            for sk, si in bot_scripts.items():
                pid = si['process'].pid
                fn = si['file_name']
                uid = si['script_owner_id']
                start = si['start_time']
                runtime = format_duration((datetime.now() - start).total_seconds())
                text += f"• PID:{pid} | `{fn}` (User:{uid}) | ⏱️{runtime}\n"
        else: text += "(No scripts running)\n"
        text += "\n**Top System Processes:**\n"
        for p in sorted(psutil.process_iter(['pid', 'name', 'memory_percent']), key=lambda x: x.info.get('memory_percent', 0) or 0, reverse=True)[:10]:
            pid = p.info.get('pid', '?')
            name = p.info.get('name', '?')[:15]
            mem = p.info.get('memory_percent', 0)
            text += f"• PID:{pid} | {name} | RAM:{mem:.1f}%\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", call.message.chat.id, call.message.message_id)

def run_all_scripts_callback(call):
    _logic_run_all_scripts(call)

def broadcast_init_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 Send broadcast message.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def all_codes_status_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    text = "📋 **All Codes Status:**\n\n"
    for uid, files in user_files.items():
        for fn, ft in files:
            is_run = is_bot_running(uid, fn)
            fs = get_file_status(uid, fn)
            si = "🟢" if is_run else "⚪"
            if fs['status'] == FILE_STATUS_APPROVED:
                ai = "✅"
            elif fs['status'] == FILE_STATUS_AUTO_APPROVED:
                ai = "🤖"
            elif fs['status'] == FILE_STATUS_PENDING:
                ai = "⏳"
            else:
                ai = "❌"
            text += f"{ai} `{fn}` (User: {uid}) - {si}\n"
    if not user_files: text += "No files found."
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except: pass

def view_pending_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    pending = get_pending_files()
    if not pending:
        try: bot.edit_message_text("✅ No pending files.", call.message.chat.id, call.message.message_id)
        except: return
    text = "📋 **Pending Files:**\n\n"
    for uid, fn, ft, ut in pending[:20]:
        try:
            dt = datetime.fromisoformat(ut)
            time_str = dt.strftime('%Y-%m-%d %H:%M')
        except:
            time_str = "Unknown"
        text += f"• `{fn}` (User: {uid}) - {ft} - {time_str}\n"
    if len(pending) > 20: text += f"\n... and {len(pending) - 20} more."
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except: pass

def review_callback(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id)
    try:
        _, uid, fn = call.data.split('_', 2)
        fs = get_file_status(int(uid), fn)
        text = f"📋 **Review:**\n\nUser: `{uid}`\nFile: `{fn}`\nStatus: {fs['status'].upper()}"
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_{uid}_{fn}'),
                   types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{uid}_{fn}'))
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='view_pending'))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
    except: pass

def check_subscription_status_callback(call):
    uid = call.from_user.id
    is_subscribed, not_joined = check_mandatory_subscription(uid)
    if is_subscribed or uid in admin_ids:
        bot.answer_callback_query(call.id, "✅ You are subscribed to all required channels!", show_alert=True)
        back_to_main_callback(call)
    else:
        bot.answer_callback_query(call.id, "❌ You haven't joined all required channels yet!", show_alert=True)
        subscription_message, markup = create_subscription_check_message(not_joined)
        try:
            bot.edit_message_text(subscription_message, call.message.chat.id, 
                                  call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        except: pass

# ====================== BUTTON TEXT HANDLERS ======================
BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": lambda m: bot.reply_to(m, "Visit: " + UPDATE_CHANNEL),
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": lambda m: bot.reply_to(m, "Contact: " + YOUR_USERNAME),
    "🤖 VIP AI": lambda m: bot.reply_to(m, "Use `/royal_ai your question`", parse_mode='Markdown'),
    "⏱ Uptime": lambda m: bot.reply_to(m, f"Uptime: {get_uptime()}"),
    "🚀 Ping": cmd_ping,
    "💳 Subscriptions": _logic_subscriptions_panel,
    "📢 Broadcast": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🟢 Run All Code": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    "📋 All Codes Status": _logic_all_codes_status,
    "👥 Whitelist Users": _logic_whitelist_panel,
    "📢 Channel Add": _logic_manage_mandatory_channels,
    "👥 User Management": _logic_user_management,
    "⚙️ Settings": _logic_admin_settings,
    "💻 Terminal": _logic_terminal,  # Only Owner can access
    "📁 File Manager": _logic_file_manager,
    "💾 Backup": _logic_backup,
    "🌐 Network Info": _logic_network_info,
    "📊 System Monitor": _logic_system_monitor,
    "🔧 Process Manager": _logic_process_manager,
    "📊 Statistics": _logic_statistics,
    "🆘 Help": _logic_help,
    "📦 Manual Install": _logic_manual_install,
    "📝 My Notes": _logic_my_notes,
    "⏰ Reminders": _logic_reminders,
    "👥 Referral": _logic_referral,
}

@bot.message_handler(func=lambda m: m.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    if is_user_banned(message.from_user.id):
        bot.reply_to(message, "❌ You are banned.")
        return
    
    # Check mandatory subscription
    is_subscribed, not_joined = check_mandatory_subscription(message.from_user.id)
    if not is_subscribed and message.from_user.id not in admin_ids:
        subscription_message, markup = create_subscription_check_message(not_joined)
        bot.reply_to(message, subscription_message, reply_markup=markup, parse_mode='Markdown')
        return
    
    # Terminal - Only Owner check
    if message.text == "💻 Terminal" and not is_owner(message.from_user.id):
        bot.reply_to(message, "⚠️ **Terminal access is only for Owner!**", parse_mode='Markdown')
        return
    
    BUTTON_TEXT_TO_LOGIC.get(message.text)(message)

# ====================== REMINDER CHECKER ======================
def reminder_checker():
    while True:
        try:
            rems = get_pending_reminders()
            for rid, uid, rtext, rat in rems:
                try:
                    bot.send_message(uid, f"⏰ **Reminder!**\n\n{rtext}", parse_mode='Markdown')
                    mark_reminder_sent(rid)
                except: pass
        except: pass
        time.sleep(30)

# ====================== CLEANUP ======================
def cleanup():
    logger.warning("Shutdown. Cleaning up processes...")
    for key in list(bot_scripts.keys()):
        if key in bot_scripts:
            logger.info(f"Stopping: {key}")
            kill_process_tree(bot_scripts[key])
    logger.warning("Cleanup finished.")
atexit.register(cleanup)

# ====================== MAIN ======================
if __name__ == '__main__':
    keep_alive()
    threading.Thread(target=reminder_checker, daemon=True, name='reminder-checker').start()
    threading.Thread(target=hosted_process_monitor, daemon=True, name='hosted-process-monitor').start()
    logger.info("🚀 ULTIMATE HOSTING BOT STARTED...")
    logger.info('Docker sandbox available: %s', _docker_available())
    logger.info(f"👑 Owner ID: {OWNER_ID}")
    logger.info(f"🛡️ Admin IDs: {admin_ids}")
    logger.info(f"🔒 Terminal Access: Only Owner ({OWNER_ID})")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)