# -*- coding: utf-8 -*-
# ============================================================
# CHUNK 1: Core Setup & Configuration
# ============================================================
# PASTE THIS FIRST - Everything else depends on this chunk
# ============================================================

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
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import hashlib
import mimetypes
import struct
import base64
import secrets
from functools import wraps
from cryptography.fernet import Fernet

# --- Flask Keep Alive ---
from flask import Flask, request as flask_request
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot is running...."

@app.route('/health')
def health():
    return {
        "status": "online",
        "uptime": str(datetime.now() - BOT_START_TIME) if 'BOT_START_TIME' in globals() else "unknown",
        "timestamp": datetime.now().isoformat()
    }

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logger.info("Flask Keep-Alive server started.")
# --- End Flask Keep Alive ---

# ============================================================
# CONFIGURATION - Edit these values
# ============================================================

# --- Bot Credentials ---
TOKEN = os.environ.get('BOT_TOKEN', '8718994817:AAHfQF5BusI0lCptm37PhdeFWcX8iHHLW2I')
OWNER_ID = int(os.environ.get('OWNER_ID', '6437451702'))
ADMIN_ID = int(os.environ.get('ADMIN_ID', '6437451702'))
YOUR_USERNAME = os.environ.get('BOT_USERNAME', '@zenkaimuzan')
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', '@zenkaic')

# --- Directory Setup ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATABASE_PATH = os.path.join(DATA_DIR, 'bot_data.db')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')
VERSIONS_DIR = os.path.join(BASE_DIR, 'versions')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')
CONFIG_PATH = os.path.join(DATA_DIR, 'bot_config.json')
ENCRYPTION_KEY_PATH = os.path.join(DATA_DIR, '.enc_key')

# --- Create Directories ---
for directory in [
    UPLOAD_BOTS_DIR, DATA_DIR, BACKUP_DIR,
    LOGS_DIR, VERSIONS_DIR, TEMP_DIR
]:
    os.makedirs(directory, exist_ok=True)

# --- File Upload Limits ---
FREE_USER_LIMIT = 10
SUBSCRIBED_USER_LIMIT = 15
VIP_USER_LIMIT = 50
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# --- Version Control Limits ---
FREE_VERSION_LIMIT = 3
PREMIUM_VERSION_LIMIT = 10
VIP_VERSION_LIMIT = 25
OWNER_VERSION_LIMIT = float('inf')

# --- Rate Limiting ---
RATE_LIMIT_SECONDS = 0.1
UPLOAD_COOLDOWN_SECONDS = 0.1

# --- Script Settings ---
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_LOG_SIZE_KB = 100
SCRIPT_PRE_CHECK_TIMEOUT = 5
MAX_RESTART_ATTEMPTS = 3
RESTART_DELAY_SECONDS = 5
RESTART_RESET_MINUTES = 30

# --- Live Log Settings ---
LIVE_LOG_REFRESH_SECONDS = 3
LIVE_LOG_MAX_LINES = 50
LIVE_LOG_MAX_SESSION_MINUTES = 5

# --- Broadcast Settings ---
BROADCAST_BATCH_SIZE = 25
BROADCAST_BATCH_DELAY = 1.5

# --- Security Settings ---
TERMINAL_TIMEOUT_SECONDS = 30
MAX_WARNINGS_BEFORE_BAN = 3
SESSION_TIMEOUT_MINUTES = 30

# --- Bot Start Time ---
BOT_START_TIME = datetime.now()

# --- Messages Processed Counter ---
MESSAGES_PROCESSED = 0
MESSAGES_LOCK = threading.Lock()

# ============================================================
# LOGGING SETUP
# ============================================================

log_file_path = os.path.join(LOGS_DIR, f"bot_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# ENCRYPTION SETUP
# ============================================================

def get_or_create_encryption_key():
    """Get existing or create new encryption key for env variables"""
    if os.path.exists(ENCRYPTION_KEY_PATH):
        with open(ENCRYPTION_KEY_PATH, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_PATH, 'wb') as f:
            f.write(key)
        logger.info("New encryption key created.")
        return key

try:
    ENCRYPTION_KEY = get_or_create_encryption_key()
    fernet = Fernet(ENCRYPTION_KEY)
    logger.info("Encryption initialized successfully.")
except Exception as e:
    logger.error(f"Encryption setup failed: {e}. Env variables will not be encrypted.")
    fernet = None

def encrypt_value(value: str) -> str:
    """Encrypt a string value"""
    if fernet:
        return fernet.encrypt(value.encode()).decode()
    return value

def decrypt_value(encrypted_value: str) -> str:
    """Decrypt an encrypted string value"""
    if fernet:
        try:
            return fernet.decrypt(encrypted_value.encode()).decode()
        except Exception:
            return encrypted_value
    return encrypted_value

# ============================================================
# BOT CONFIGURATION (Dynamic - loaded from DB/file)
# ============================================================

DEFAULT_CONFIG = {
    # Messages
    "welcome_message": "〽️ Welcome, {name}!\n\n🆔 Your User ID: `{user_id}`\n✳️ Username: `@{username}`\n🔰 Status: {status}\n📁 Files: {files}/{limit}\n\n👇 Use buttons or commands.",
    "help_message": "❓ Help Center\n\nUse buttons below to navigate.",
    "maintenance_message": "🔧 Bot is under maintenance. Please try again later.",
    "locked_message": "🔒 Bot is locked by admin. Please try again later.",
    "force_sub_message": "⚠️ You must join all required channels/groups first!",

    # Limits
    "free_user_limit": FREE_USER_LIMIT,
    "premium_user_limit": SUBSCRIBED_USER_LIMIT,
    "vip_user_limit": VIP_USER_LIMIT,
    "admin_limit": ADMIN_LIMIT,
    "max_file_size_mb": 20,

    # Features
    "force_sub_enabled": False,
    "maintenance_mode": False,
    "bot_locked": False,
    "webhook_mode": False,
    "webhook_url": "",
    "webhook_secret": "",
    "auto_restart_scripts": True,
    "max_restart_attempts": MAX_RESTART_ATTEMPTS,
    "restart_delay_seconds": RESTART_DELAY_SECONDS,

    # Rate Limiting
    "rate_limit_seconds": RATE_LIMIT_SECONDS,
    "upload_cooldown_seconds": UPLOAD_COOLDOWN_SECONDS,

    # Security
    "max_warnings_before_ban": MAX_WARNINGS_BEFORE_BAN,
    "terminal_timeout_seconds": TERMINAL_TIMEOUT_SECONDS,

    # Notifications (Owner)
    "notify_new_user": True,
    "notify_script_crash": True,
    "notify_system_alert": True,
    "notify_payment_request": True,
    "notify_ban_attempt": True,
    "notify_admin_action": True,

    # Alert Thresholds
    "cpu_alert_threshold": 90,
    "ram_alert_threshold": 85,
    "disk_alert_threshold": 90,

    # Scheduled Reports
    "daily_report": False,
    "weekly_report": False,

    # Payment
    "payment_methods": "Contact owner for payment details",
    "payment_instructions": "1. Choose a plan\n2. Contact owner\n3. Send payment proof",

    # Plans
    "plans": {
        "premium": {
            "name": "⭐ Premium",
            "duration_days": 30,
            "price": "Contact Owner",
            "file_limit": SUBSCRIBED_USER_LIMIT,
            "features": "15 files, Priority support, Advanced logs"
        },
        "vip": {
            "name": "💎 VIP",
            "duration_days": 30,
            "price": "Contact Owner",
            "file_limit": VIP_USER_LIMIT,
            "features": "50 files, All features, Priority support"
        }
    },

    # Uptime
    "uptime_tracking": True,
    "bot_status": "operational",  # operational/degraded/outage

    # Version Control
    "free_version_limit": FREE_VERSION_LIMIT,
    "premium_version_limit": PREMIUM_VERSION_LIMIT,
    "vip_version_limit": VIP_VERSION_LIMIT,

    # Live Log
    "live_log_refresh_seconds": LIVE_LOG_REFRESH_SECONDS,
    "live_log_max_lines": LIVE_LOG_MAX_LINES,
}

# Global config (loaded from DB, falls back to defaults)
BOT_CONFIG = DEFAULT_CONFIG.copy()

def get_config(key, default=None):
    """Get a configuration value"""
    return BOT_CONFIG.get(key, DEFAULT_CONFIG.get(key, default))

def set_config(key, value):
    """Set a configuration value in memory and DB"""
    BOT_CONFIG[key] = value
    save_config_to_db(key, value)

# ============================================================
# IN-MEMORY DATA STRUCTURES
# ============================================================

# Core data
bot_scripts = {}           # Running scripts
user_subscriptions = {}    # User subscription data
user_files = {}            # User files
active_users = set()       # All users who used bot
admin_ids = set()          # Admin user IDs
banned_users = {}          # Banned users {user_id: ban_info}
warned_users = {}          # Warned users {user_id: [warnings]}
verified_users = set()     # Users who passed force sub check
force_sub_chats = []       # Required chats for force sub

# Locks
BOT_SCRIPTS_LOCK = threading.Lock()
DB_LOCK = threading.Lock()
CONFIG_LOCK = threading.Lock()

# Rate limiting
user_last_action = {}
user_last_upload = {}

# Live log sessions
live_log_sessions = {}

# Owner sessions (for terminal etc)
owner_sessions = {}

# Crash tracking
script_crash_counts = {}

# Messages processed today
daily_stats = {
    'messages': 0,
    'uploads': 0,
    'scripts_started': 0,
    'date': datetime.now().date()
}

# ============================================================
# MALWARE DETECTION CONFIGURATION
# ============================================================

MALWARE_SIGNATURES = [
    b'\x7fELF',        # Linux executable
    b'\xfe\xed\xfa',   # Mach-O binary
    b'\xce\xfa\xed\xfe', # Mach-O binary (reverse)
    b'Rar!',           # RAR archive
]

EXECUTABLE_EXTENSIONS = [
    '.exe', '.dll', '.bat', '.cmd', '.scr', '.com',
    '.pif', '.application', '.gadget', '.msi', '.msp',
    '.hta', '.cpl', '.msc', '.jar', '.bin', '.deb',
    '.rpm', '.apk', '.app', '.dmg', '.iso', '.img'
]

ENCRYPTED_FILE_INDICATORS = [
    b'openssl', b'encrypted', b'cipher',
    b'AES', b'DES', b'RSA', b'GPG', b'PGP',
]

SUSPICIOUS_KEYWORDS = [
    b'ransomware', b'trojan', b'virus',
    b'malware', b'backdoor', b'exploit',
    b'payload', b'botnet', b'keylogger', b'rootkit',
]

# Blacklisted terminal commands (Owner protection)
BLACKLISTED_TERMINAL_COMMANDS = [
    'rm -rf /',
    'rm -rf /*',
    'mkfs',
    'dd if=/dev/zero',
    ':(){:|:&};:',  # Fork bomb
    'chmod -R 777 /',
    'chown -R',
    '> /dev/sda',
    'mv /* /dev/null',
]

# ============================================================
# TELEGRAM MODULE MAP (for auto pip install)
# ============================================================

TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'telepot': 'telepot',
    'bs4': 'beautifulsoup4',
    'requests': 'requests',
    'PIL': 'Pillow',
    'cv2': 'opencv-python',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'flask': 'Flask',
    'django': 'Django',
    'sqlalchemy': 'SQLAlchemy',
    'psutil': 'psutil',
    'cryptography': 'cryptography',
    'aiohttp': 'aiohttp',
    'fastapi': 'fastapi',
    'pymongo': 'pymongo',
    'redis': 'redis',
    'celery': 'celery',
    'asyncio': None,
    'json': None,
    'datetime': None,
    'os': None,
    'sys': None,
    're': None,
    'time': None,
    'math': None,
    'random': None,
    'logging': None,
    'threading': None,
    'subprocess': None,
    'zipfile': None,
    'tempfile': None,
    'shutil': None,
    'sqlite3': None,
    'atexit': None,
    'hashlib': None,
    'base64': None,
}

# ============================================================
# BUTTON LAYOUTS
# ============================================================

# User button layout
COMMAND_BUTTONS_USER = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 My Files"],
    ["⚡ Bot Speed", "📊 My Stats"],
    ["👤 My Profile", "❓ Help"],
    ["💳 Premium Info", "📞 Contact Owner"],
]

# Admin button layout
COMMAND_BUTTONS_ADMIN = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 My Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["👤 My Profile", "❓ Help"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Run All Scripts"],
    ["📤 Send Command", "🛡️ Admin Panel"],
    ["📞 Contact Owner"],
]

# Owner button layout
COMMAND_BUTTONS_OWNER = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 My Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["👤 My Profile", "❓ Help"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Run All Scripts"],
    ["📤 Send Command", "🛡️ Admin Panel"],
    ["👑 Owner Panel", "💻 System Monitor"],
    ["📞 Contact Owner"],
]

# ============================================================
# INITIALIZE BOT
# ============================================================

if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN_HERE':
    logger.critical("❌ BOT_TOKEN not set! Set it in environment variables.")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)
logger.info(f"Bot initialized with token ending: ...{TOKEN[-6:]}")

# ============================================================
# END OF CHUNK 1
## ============================================================
# CHUNK 2: Database Setup & Beautiful UI Constants
# ============================================================
# PASTE THIS AFTER CHUNK 1
# ============================================================

# ============================================================
# BEAUTIFUL UI CONSTANTS
# ============================================================

# --- Dividers & Decorators ---
DIVIDER = "═" * 30
THIN_DIVIDER = "─" * 30
STAR_DIVIDER = "✦" * 15
DOT_DIVIDER = "• " * 15

# --- Status Icons ---
ICON_ONLINE = "🟢"
ICON_OFFLINE = "🔴"
ICON_WARNING = "🟡"
ICON_ERROR = "❌"
ICON_SUCCESS = "✅"
ICON_INFO = "ℹ️"
ICON_LOADING = "⏳"
ICON_CROWN = "👑"
ICON_SHIELD = "🛡️"
ICON_STAR = "⭐"
ICON_DIAMOND = "💎"
ICON_FREE = "🆓"
ICON_LOCK = "🔒"
ICON_UNLOCK = "🔓"
ICON_BOT = "🤖"
ICON_USER = "👤"
ICON_ADMIN = "🛡️"
ICON_OWNER = "👑"
ICON_FIRE = "🔥"
ICON_ROCKET = "🚀"
ICON_GEAR = "⚙️"
ICON_DATABASE = "🗄️"
ICON_FILE = "📁"
ICON_SCRIPT = "📜"
ICON_LOG = "📋"
ICON_STATS = "📊"
ICON_SPEED = "⚡"
ICON_CLOCK = "🕐"
ICON_CALENDAR = "📅"
ICON_BELL = "🔔"
ICON_MONEY = "💰"
ICON_CARD = "💳"
ICON_PHONE = "📞"
ICON_GLOBE = "🌐"
ICON_TERMINAL = "💻"
ICON_SECURITY = "🔐"
ICON_BROADCAST = "📢"
ICON_REFRESH = "🔄"
ICON_TRASH = "🗑️"
ICON_EDIT = "✏️"
ICON_SEARCH = "🔍"
ICON_DOWNLOAD = "📥"
ICON_UPLOAD = "📤"
ICON_BACK = "🔙"
ICON_HOME = "🏠"
ICON_NEXT = "➡️"
ICON_PREV = "⬅️"
ICON_ADD = "➕"
ICON_REMOVE = "➖"
ICON_BAN = "🚫"
ICON_WARN = "⚠️"
ICON_VERSION = "🔖"
ICON_ENV = "🔑"
ICON_LIVE = "📺"
ICON_HEALTH = "💊"
ICON_PLAN = "📋"
ICON_HELP = "❓"
ICON_CONTACT = "💬"
ICON_CHANNEL = "📢"
ICON_CPU = "🖥️"
ICON_RAM = "🧠"
ICON_DISK = "💾"
ICON_NETWORK = "🌐"
ICON_PROCESS = "⚙️"
ICON_CRASH = "💥"
ICON_RESTART = "🔄"
ICON_SCHEDULE = "⏰"
ICON_WEBHOOK = "🔗"
ICON_MAINTENANCE = "🔧"

# --- Beautiful Message Templates ---
def make_header(title, icon="🤖"):
    return f"{icon} *{title}*\n{DIVIDER}"

def make_section(title, icon="▸"):
    return f"\n{icon} *{title}*"

def make_footer(text=""):
    if text:
        return f"\n{THIN_DIVIDER}\n_{text}_"
    return f"\n{THIN_DIVIDER}"

def make_status_bar(cpu, ram, disk):
    def bar(val, max_val=100, length=10):
        filled = int((val / max_val) * length)
        return "█" * filled + "░" * (length - filled)
    return (
        f"🖥️ CPU  [{bar(cpu)}] {cpu:.1f}%\n"
        f"🧠 RAM  [{bar(ram)}] {ram:.1f}%\n"
        f"💾 DISK [{bar(disk)}] {disk:.1f}%"
    )

def make_user_card(user_id, name, username, status, files, limit, expiry=None):
    limit_str = str(limit) if limit != float('inf') else "∞"
    expiry_str = f"\n⏳ *Expires:* {expiry}" if expiry else ""
    return (
        f"┌─────────────────────\n"
        f"│ {ICON_USER} *{name}*\n"
        f"│ 🆔 `{user_id}`\n"
        f"│ ✳️ @{username or 'Not set'}\n"
        f"│ 🔰 {status}\n"
        f"│ 📁 Files: {files}/{limit_str}"
        f"{expiry_str}\n"
        f"└─────────────────────"
    )

def make_script_card(file_name, file_type, status, pid=None, uptime=None):
    pid_str = f"\n│ 🔢 PID: `{pid}`" if pid else ""
    uptime_str = f"\n│ ⏱️ Uptime: {uptime}" if uptime else ""
    status_icon = ICON_ONLINE if "Running" in status else ICON_OFFLINE
    return (
        f"┌─────────────────────\n"
        f"│ 📜 *{file_name}*\n"
        f"│ 🏷️ Type: `{file_type.upper()}`\n"
        f"│ {status_icon} Status: {status}"
        f"{pid_str}"
        f"{uptime_str}\n"
        f"└─────────────────────"
    )

def make_stats_card(total_users, total_files, running_bots, uptime):
    return (
        f"┌─────────────────────\n"
        f"│ {ICON_STATS} *Bot Statistics*\n"
        f"├─────────────────────\n"
        f"│ 👥 Users: *{total_users}*\n"
        f"│ 📁 Files: *{total_files}*\n"
        f"│ 🟢 Running: *{running_bots}*\n"
        f"│ ⏱️ Uptime: *{uptime}*\n"
        f"└─────────────────────"
    )

def format_uptime(start_time):
    """Format uptime as human readable string"""
    delta = datetime.now() - start_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)

def format_size(size_bytes):
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def mask_value(value, show_chars=3):
    """Mask sensitive values"""
    if len(value) <= show_chars:
        return "*" * len(value)
    return value[:show_chars] + "*" * (len(value) - show_chars)

def get_user_status_icon(user_id):
    """Get status icon for user"""
    if user_id == OWNER_ID:
        return ICON_CROWN
    elif user_id in admin_ids:
        return ICON_SHIELD
    elif user_id in user_subscriptions:
        expiry = user_subscriptions[user_id].get('expiry')
        if expiry and expiry > datetime.now():
            plan = user_subscriptions[user_id].get('plan', 'premium')
            return ICON_DIAMOND if plan == 'vip' else ICON_STAR
    return ICON_FREE

def get_user_status_text(user_id):
    """Get full status text for user"""
    if user_id == OWNER_ID:
        return f"{ICON_CROWN} Owner"
    elif user_id in admin_ids:
        return f"{ICON_SHIELD} Admin"
    elif user_id in user_subscriptions:
        expiry = user_subscriptions[user_id].get('expiry')
        if expiry and expiry > datetime.now():
            plan = user_subscriptions[user_id].get('plan', 'premium')
            if plan == 'vip':
                return f"{ICON_DIAMOND} VIP"
            return f"{ICON_STAR} Premium"
        else:
            return f"{ICON_FREE} Free (Expired)"
    return f"{ICON_FREE} Free"

# ============================================================
# DATABASE SETUP
# ============================================================

def init_db():
    """Initialize database with all required tables"""
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        # --- Core Tables ---
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            plan TEXT DEFAULT 'premium',
            expiry TEXT,
            added_by INTEGER,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS user_files (
            user_id INTEGER,
            file_name TEXT,
            file_type TEXT,
            file_size INTEGER DEFAULT 0,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, file_name)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS active_users (
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP,
            total_messages INTEGER DEFAULT 0
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            can_ban INTEGER DEFAULT 1,
            can_broadcast INTEGER DEFAULT 1,
            can_manage_subs INTEGER DEFAULT 1,
            can_view_files INTEGER DEFAULT 1,
            can_stop_scripts INTEGER DEFAULT 1,
            can_system_monitor INTEGER DEFAULT 0
        )''')

        # --- Ban & Warning Tables ---
        c.execute('''CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ban_type TEXT DEFAULT 'permanent',
            reason TEXT,
            banned_by INTEGER,
            banned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT,
            is_active INTEGER DEFAULT 1
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            warned_by INTEGER,
            warned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )''')

        # --- Force Subscribe Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS force_sub_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            chat_type TEXT DEFAULT 'channel',
            chat_username TEXT,
            chat_name TEXT,
            invite_link TEXT,
            is_private INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS verified_force_sub (
            user_id INTEGER PRIMARY KEY,
            verified_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # --- User Profile Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP,
            total_uploads INTEGER DEFAULT 0,
            total_scripts_run INTEGER DEFAULT 0,
            total_run_time_seconds INTEGER DEFAULT 0,
            storage_used_bytes INTEGER DEFAULT 0,
            preferred_language TEXT DEFAULT 'en',
            notify_crash INTEGER DEFAULT 1,
            notify_start INTEGER DEFAULT 1,
            notify_stop INTEGER DEFAULT 1,
            notify_sub_expiry INTEGER DEFAULT 1,
            notify_announcements INTEGER DEFAULT 1,
            custom_file_limit INTEGER DEFAULT -1
        )''')

        # --- Environment Variables Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS env_variables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            script_name TEXT DEFAULT 'global',
            env_key TEXT,
            env_value TEXT,
            is_secret INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, script_name, env_key)
        )''')

        # --- File Versions Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS file_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            version_number INTEGER,
            file_path TEXT,
            file_size INTEGER DEFAULT 0,
            checksum TEXT,
            upload_note TEXT,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_locked INTEGER DEFAULT 0
        )''')

        # --- Script Scheduler Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            schedule_type TEXT,
            schedule_config TEXT,
            next_run_at TEXT,
            last_run_at TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # --- Crash Reports Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS crash_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            exit_code INTEGER,
            crash_time TEXT DEFAULT CURRENT_TIMESTAMP,
            last_log_lines TEXT,
            restart_count INTEGER DEFAULT 0,
            resolved INTEGER DEFAULT 0
        )''')

        # --- Payment Tables ---
        c.execute('''CREATE TABLE IF NOT EXISTS payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_name TEXT,
            payment_method TEXT,
            status TEXT DEFAULT 'pending',
            requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT,
            processed_by INTEGER,
            notes TEXT
        )''')

        # --- Bot Config Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS bot_config (
            config_key TEXT PRIMARY KEY,
            config_value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )''')

        # --- Audit Log Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            target_id INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            severity TEXT DEFAULT 'info'
        )''')

        # --- Uptime Logs Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS uptime_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'online',
            response_time_ms REAL
        )''')

        # --- Incidents Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            severity TEXT DEFAULT 'minor',
            status TEXT DEFAULT 'investigating',
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            updates TEXT DEFAULT '[]'
        )''')

        # --- Broadcast History Table ---
        c.execute('''CREATE TABLE IF NOT EXISTS broadcast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_by INTEGER,
            message_preview TEXT,
            target_type TEXT DEFAULT 'all',
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            blocked_count INTEGER DEFAULT 0,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            duration_seconds REAL DEFAULT 0
        )''')

        # --- Notification Subscriptions ---
        c.execute('''CREATE TABLE IF NOT EXISTS status_subscribers (
            user_id INTEGER PRIMARY KEY,
            subscribed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # --- Insert Default Data ---
        c.execute('INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)',
                  (OWNER_ID, OWNER_ID))
        if ADMIN_ID and ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)',
                      (ADMIN_ID, OWNER_ID))

        conn.commit()
        conn.close()
        logger.info("✅ Database initialized successfully with all tables.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)
        raise

# ============================================================
# DATABASE OPERATIONS
# ============================================================

def load_data():
    """Load all data from database into memory"""
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        # Load subscriptions
        c.execute('SELECT user_id, plan, expiry FROM subscriptions')
        for user_id, plan, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {
                    'expiry': datetime.fromisoformat(expiry),
                    'plan': plan or 'premium'
                }
            except ValueError:
                logger.warning(f"Invalid expiry for user {user_id}: {expiry}")

        # Load user files
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        # Load active users
        c.execute('SELECT user_id FROM active_users')
        active_users.update(row[0] for row in c.fetchall())

        # Load admins
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(row[0] for row in c.fetchall())

        # Load bans
        c.execute('''SELECT user_id, ban_type, reason, banned_by,
                     banned_at, expires_at FROM bans WHERE is_active = 1''')
        for row in c.fetchall():
            user_id, ban_type, reason, banned_by, banned_at, expires_at = row
            banned_users[user_id] = {
                'ban_type': ban_type,
                'reason': reason,
                'banned_by': banned_by,
                'banned_at': banned_at,
                'expires_at': expires_at
            }

        # Load warnings
        c.execute('''SELECT user_id, reason, warned_by, warned_at
                     FROM warnings WHERE is_active = 1''')
        for row in c.fetchall():
            user_id, reason, warned_by, warned_at = row
            if user_id not in warned_users:
                warned_users[user_id] = []
            warned_users[user_id].append({
                'reason': reason,
                'warned_by': warned_by,
                'warned_at': warned_at
            })

        # Load force sub chats
        c.execute('''SELECT id, chat_id, chat_type, chat_username,
                     chat_name, invite_link, is_private
                     FROM force_sub_chats WHERE is_active = 1''')
        force_sub_chats.clear()
        for row in c.fetchall():
            force_sub_chats.append({
                'id': row[0],
                'chat_id': row[1],
                'chat_type': row[2],
                'chat_username': row[3],
                'chat_name': row[4],
                'invite_link': row[5],
                'is_private': bool(row[6])
            })

        # Load verified force sub users
        c.execute('SELECT user_id FROM verified_force_sub')
        verified_users.update(row[0] for row in c.fetchall())

        # Load bot config
        c.execute('SELECT config_key, config_value FROM bot_config')
        for key, value in c.fetchall():
            try:
                BOT_CONFIG[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                BOT_CONFIG[key] = value

        conn.close()
        logger.info(
            f"✅ Data loaded: {len(active_users)} users, "
            f"{len(user_subscriptions)} subscriptions, "
            f"{len(admin_ids)} admins, "
            f"{len(banned_users)} bans, "
            f"{len(force_sub_chats)} force-sub chats."
        )
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

# --- Config DB Operations ---
def save_config_to_db(key, value, updated_by=None):
    """Save config to database"""
    with DB_LOCK:
        try:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO bot_config
                         (config_key, config_value, updated_at, updated_by)
                         VALUES (?, ?, ?, ?)''',
                      (key, json.dumps(value), datetime.now().isoformat(), updated_by))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving config {key}: {e}")

# --- User File Operations ---
def save_user_file(user_id, file_name, file_type='py', file_size=0):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT OR REPLACE INTO user_files
                         (user_id, file_name, file_type, file_size, uploaded_at)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, file_name, file_type, file_size,
                       datetime.now().isoformat()))
            conn.commit()
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id] = [
                (fn, ft) for fn, ft in user_files[user_id] if fn != file_name
            ]
            user_files[user_id].append((file_name, file_type))
            # Update profile stats
            update_user_profile_stat(user_id, 'total_uploads', 1)
            logger.info(f"Saved file '{file_name}' ({file_type}) for user {user_id}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving file: {e}")
        finally:
            conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?',
                      (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [
                    f for f in user_files[user_id] if f[0] != file_name
                ]
                if not user_files[user_id]:
                    del user_files[user_id]
            logger.info(f"Removed file '{file_name}' for user {user_id}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error removing file: {e}")
        finally:
            conn.close()

# --- Active User Operations ---
def add_active_user(user_id, first_name="", username=""):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT OR IGNORE INTO active_users (user_id, first_seen)
                         VALUES (?, ?)''',
                      (user_id, datetime.now().isoformat()))
            c.execute('''UPDATE active_users SET last_active = ?,
                         total_messages = total_messages + 1
                         WHERE user_id = ?''',
                      (datetime.now().isoformat(), user_id))
            # Create profile if not exists
            c.execute('''INSERT OR IGNORE INTO user_profiles
                         (user_id, first_name, username, first_seen)
                         VALUES (?, ?, ?, ?)''',
                      (user_id, first_name, username,
                       datetime.now().isoformat()))
            c.execute('''UPDATE user_profiles SET last_active = ?,
                         first_name = ?, username = ?
                         WHERE user_id = ?''',
                      (datetime.now().isoformat(), first_name,
                       username, user_id))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite error adding active user: {e}")
        finally:
            conn.close()

def update_user_profile_stat(user_id, stat_name, increment=1):
    """Update a numeric stat in user profile"""
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute(f'''UPDATE user_profiles
                         SET {stat_name} = {stat_name} + ?
                         WHERE user_id = ?''',
                      (increment, user_id))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite error updating profile stat: {e}")
        finally:
            conn.close()

# --- Subscription Operations ---
def save_subscription(user_id, expiry, plan='premium', added_by=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('''INSERT OR REPLACE INTO subscriptions
                         (user_id, plan, expiry, added_by, added_at)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, plan, expiry_str, added_by,
                       datetime.now().isoformat()))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry, 'plan': plan}
            log_audit(added_by or OWNER_ID, 'add_subscription',
                      f"Added {plan} sub for {user_id} until {expiry_str}",
                      target_id=user_id)
            logger.info(f"Saved {plan} subscription for {user_id}, expiry {expiry_str}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving subscription: {e}")
        finally:
            conn.close()

def remove_subscription_db(user_id, removed_by=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions:
                del user_subscriptions[user_id]
            log_audit(removed_by or OWNER_ID, 'remove_subscription',
                      f"Removed subscription for {user_id}",
                      target_id=user_id)
        except sqlite3.Error as e:
            logger.error(f"SQLite error removing subscription: {e}")
        finally:
            conn.close()

# --- Admin Operations ---
def add_admin_db(admin_id, added_by=OWNER_ID, permissions=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            perms = permissions or {}
            c.execute('''INSERT OR IGNORE INTO admins
                         (user_id, added_by, can_ban, can_broadcast,
                          can_manage_subs, can_view_files,
                          can_stop_scripts, can_system_monitor)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (admin_id, added_by,
                       perms.get('can_ban', 1),
                       perms.get('can_broadcast', 1),
                       perms.get('can_manage_subs', 1),
                       perms.get('can_view_files', 1),
                       perms.get('can_stop_scripts', 1),
                       perms.get('can_system_monitor', 0)))
            conn.commit()
            admin_ids.add(admin_id)
            log_audit(added_by, 'add_admin',
                      f"Added admin {admin_id}", target_id=admin_id)
        except sqlite3.Error as e:
            logger.error(f"SQLite error adding admin: {e}")
        finally:
            conn.close()

def remove_admin_db(admin_id, removed_by=OWNER_ID):
    if admin_id == OWNER_ID:
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            conn.commit()
            admin_ids.discard(admin_id)
            log_audit(removed_by, 'remove_admin',
                      f"Removed admin {admin_id}", target_id=admin_id)
            return True
        except sqlite3.Error as e:
            logger.error(f"SQLite error removing admin: {e}")
            return False
        finally:
            conn.close()

def get_admin_permissions(admin_id):
    """Get admin permissions from DB"""
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''SELECT can_ban, can_broadcast, can_manage_subs,
                     can_view_files, can_stop_scripts, can_system_monitor
                     FROM admins WHERE user_id = ?''', (admin_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                'can_ban': bool(row[0]),
                'can_broadcast': bool(row[1]),
                'can_manage_subs': bool(row[2]),
                'can_view_files': bool(row[3]),
                'can_stop_scripts': bool(row[4]),
                'can_system_monitor': bool(row[5])
            }
    except Exception as e:
        logger.error(f"Error getting admin permissions: {e}")
    return {}

# --- Ban Operations ---
def ban_user_db(user_id, ban_type='permanent', reason='No reason',
                banned_by=None, duration_hours=None):
    expires_at = None
    if ban_type == 'temporary' and duration_hours:
        expires_at = (datetime.now() + timedelta(hours=duration_hours)).isoformat()

    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            # Deactivate old bans
            c.execute('''UPDATE bans SET is_active = 0
                         WHERE user_id = ? AND is_active = 1''', (user_id,))
            # Add new ban
            c.execute('''INSERT INTO bans
                         (user_id, ban_type, reason, banned_by,
                          banned_at, expires_at, is_active)
                         VALUES (?, ?, ?, ?, ?, ?, 1)''',
                      (user_id, ban_type, reason, banned_by,
                       datetime.now().isoformat(), expires_at))
            conn.commit()
            banned_users[user_id] = {
                'ban_type': ban_type,
                'reason': reason,
                'banned_by': banned_by,
                'banned_at': datetime.now().isoformat(),
                'expires_at': expires_at
            }
            log_audit(banned_by, 'ban_user',
                      f"Banned user {user_id}: {reason}",
                      target_id=user_id, severity='warning')
            # Remove from verified if banned
            verified_users.discard(user_id)
            logger.warning(f"User {user_id} banned by {banned_by}: {reason}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error banning user: {e}")
        finally:
            conn.close()

def unban_user_db(user_id, unbanned_by=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''UPDATE bans SET is_active = 0
                         WHERE user_id = ? AND is_active = 1''', (user_id,))
            conn.commit()
            if user_id in banned_users:
                del banned_users[user_id]
            log_audit(unbanned_by, 'unban_user',
                      f"Unbanned user {user_id}", target_id=user_id)
            logger.info(f"User {user_id} unbanned by {unbanned_by}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error unbanning user: {e}")
        finally:
            conn.close()

def warn_user_db(user_id, reason, warned_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO warnings
                         (user_id, reason, warned_by, warned_at)
                         VALUES (?, ?, ?, ?)''',
                      (user_id, reason, warned_by,
                       datetime.now().isoformat()))
            conn.commit()
            if user_id not in warned_users:
                warned_users[user_id] = []
            warned_users[user_id].append({
                'reason': reason,
                'warned_by': warned_by,
                'warned_at': datetime.now().isoformat()
            })
            log_audit(warned_by, 'warn_user',
                      f"Warned user {user_id}: {reason}",
                      target_id=user_id, severity='warning')
            # Check auto-ban threshold
            max_warnings = get_config('max_warnings_before_ban',
                                      MAX_WARNINGS_BEFORE_BAN)
            active_warnings = len([
                w for w in warned_users.get(user_id, [])
            ])
            logger.info(f"User {user_id} warned ({active_warnings}/{max_warnings})")
            return active_warnings
        except sqlite3.Error as e:
            logger.error(f"SQLite error warning user: {e}")
            return 0
        finally:
            conn.close()

# --- Force Sub Operations ---
def add_force_sub_chat(chat_id, chat_type, chat_username=None,
                       chat_name=None, invite_link=None, is_private=False):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO force_sub_chats
                         (chat_id, chat_type, chat_username,
                          chat_name, invite_link, is_private)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (str(chat_id), chat_type, chat_username,
                       chat_name, invite_link, int(is_private)))
            conn.commit()
            new_id = c.lastrowid
            force_sub_chats.append({
                'id': new_id,
                'chat_id': str(chat_id),
                'chat_type': chat_type,
                'chat_username': chat_username,
                'chat_name': chat_name,
                'invite_link': invite_link,
                'is_private': is_private
            })
            # Clear verified users cache
            verified_users.clear()
            conn2 = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c2 = conn2.cursor()
            c2.execute('DELETE FROM verified_force_sub')
            conn2.commit()
            conn2.close()
            logger.info(f"Added force sub chat: {chat_id}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error adding force sub chat: {e}")
        finally:
            conn.close()

def remove_force_sub_chat(chat_db_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('UPDATE force_sub_chats SET is_active = 0 WHERE id = ?',
                      (chat_db_id,))
            conn.commit()
            force_sub_chats[:] = [
                ch for ch in force_sub_chats if ch['id'] != chat_db_id
            ]
            logger.info(f"Removed force sub chat ID: {chat_db_id}")
        except sqlite3.Error as e:
            logger.error(f"SQLite error removing force sub chat: {e}")
        finally:
            conn.close()

# --- Audit Log Operations ---
def log_audit(user_id, action, details, target_id=None,
              severity='info'):
    """Log an audit event"""
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute('''INSERT INTO audit_logs
                         (user_id, action, details, target_id,
                          timestamp, severity)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (user_id, action, details, target_id,
                       datetime.now().isoformat(), severity))
            conn.commit()
            conn.close()
    except Exception as e:
        logger.error(f"Error logging audit: {e}")

# --- Crash Report Operations ---
def save_crash_report(user_id, file_name, exit_code,
                      last_log_lines, restart_count):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO crash_reports
                         (user_id, file_name, exit_code,
                          last_log_lines, restart_count)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, file_name, exit_code,
                       last_log_lines, restart_count))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving crash report: {e}")
        finally:
            conn.close()

# --- Env Variable Operations ---
def save_env_variable(user_id, env_key, env_value,
                      script_name='global', is_secret=False):
    encrypted = encrypt_value(env_value)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT OR REPLACE INTO env_variables
                         (user_id, script_name, env_key,
                          env_value, is_secret, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (user_id, script_name, env_key,
                       encrypted, int(is_secret),
                       datetime.now().isoformat()))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving env variable: {e}")
        finally:
            conn.close()

def get_env_variables(user_id, script_name=None):
    """Get decrypted env variables for user"""
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        if script_name:
            c.execute('''SELECT env_key, env_value, is_secret
                         FROM env_variables
                         WHERE user_id = ?
                         AND (script_name = ? OR script_name = 'global')''',
                      (user_id, script_name))
        else:
            c.execute('''SELECT env_key, env_value, is_secret
                         FROM env_variables WHERE user_id = ?''',
                      (user_id,))
        rows = c.fetchall()
        conn.close()
        result = {}
        for key, encrypted_val, is_secret in rows:
            result[key] = decrypt_value(encrypted_val)
        return result
    except Exception as e:
        logger.error(f"Error getting env variables: {e}")
        return {}

def delete_env_variable(user_id, env_key, script_name='global'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''DELETE FROM env_variables
                         WHERE user_id = ? AND env_key = ?
                         AND script_name = ?''',
                      (user_id, env_key, script_name))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite error deleting env variable: {e}")
        finally:
            conn.close()

# --- File Version Operations ---
def save_file_version(user_id, file_name, version_number,
                      file_path, file_size, checksum, note=""):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO file_versions
                         (user_id, file_name, version_number,
                          file_path, file_size, checksum, upload_note)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, file_name, version_number,
                       file_path, file_size, checksum, note))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving file version: {e}")
        finally:
            conn.close()

def get_file_versions(user_id, file_name):
    """Get all versions of a file"""
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''SELECT id, version_number, file_path, file_size,
                     checksum, upload_note, uploaded_at, is_locked
                     FROM file_versions
                     WHERE user_id = ? AND file_name = ?
                     ORDER BY version_number DESC''',
                  (user_id, file_name))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error getting file versions: {e}")
        return []

def get_next_version_number(user_id, file_name):
    """Get next version number for a file"""
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''SELECT MAX(version_number) FROM file_versions
                     WHERE user_id = ? AND file_name = ?''',
                  (user_id, file_name))
        row = c.fetchone()
        conn.close()
        return (row[0] or 0) + 1
    except Exception as e:
        logger.error(f"Error getting version number: {e}")
        return 1

# --- Uptime Tracking ---
def log_uptime(status='online', response_time=None):
    """Log uptime heartbeat"""
    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            c.execute('''INSERT INTO uptime_logs
                         (timestamp, status, response_time_ms)
                         VALUES (?, ?, ?)''',
                      (datetime.now().isoformat(), status, response_time))
            conn.commit()
            conn.close()
    except Exception as e:
        logger.error(f"Error logging uptime: {e}")

def get_uptime_percentage(hours=24):
    """Calculate uptime percentage for last N hours"""
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        c.execute('''SELECT COUNT(*), SUM(CASE WHEN status='online' THEN 1 ELSE 0 END)
                     FROM uptime_logs WHERE timestamp > ?''', (since,))
        total, online = c.fetchone()
        conn.close()
        if total and total > 0:
            return round((online / total) * 100, 2)
        return 100.0
    except Exception as e:
        logger.error(f"Error calculating uptime: {e}")
        return 100.0

# --- Payment Request Operations ---
def save_payment_request(user_id, plan_name, payment_method):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO payment_requests
                         (user_id, plan_name, payment_method)
                         VALUES (?, ?, ?)''',
                      (user_id, plan_name, payment_method))
            conn.commit()
            req_id = c.lastrowid
            conn.close()
            return req_id
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving payment request: {e}")
            conn.close()
            return None

# --- Schedule Operations ---
def save_schedule(user_id, file_name, schedule_type,
                  schedule_config, next_run_at):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO schedules
                         (user_id, file_name, schedule_type,
                          schedule_config, next_run_at)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, file_name, schedule_type,
                       json.dumps(schedule_config),
                       next_run_at.isoformat()))
            conn.commit()
            schedule_id = c.lastrowid
            conn.close()
            return schedule_id
        except sqlite3.Error as e:
            logger.error(f"SQLite error saving schedule: {e}")
            conn.close()
            return None

def get_due_schedules():
    """Get all schedules that are due to run"""
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute('''SELECT id, user_id, file_name, schedule_type,
                     schedule_config, next_run_at
                     FROM schedules
                     WHERE is_active = 1 AND next_run_at <= ?''', (now,))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error getting due schedules: {e}")
        return []

def update_schedule_next_run(schedule_id, next_run_at):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''UPDATE schedules
                         SET next_run_at = ?, last_run_at = ?
                         WHERE id = ?''',
                      (next_run_at.isoformat(),
                       datetime.now().isoformat(), schedule_id))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite error updating schedule: {e}")
        finally:
            conn.close()

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_user_folder(user_id):
    """Get or create user's folder"""
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    """Get file upload limit for user"""
    if user_id == OWNER_ID:
        return float('inf')
    if user_id in admin_ids:
        return get_config('admin_limit', 999)
    # Check custom limit
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT custom_file_limit FROM user_profiles WHERE user_id = ?',
                  (user_id,))
        row = c.fetchone()
        conn.close()
        if row and row[0] and row[0] > 0:
            return row[0]
    except Exception:
        pass
    if user_id in user_subscriptions:
        expiry = user_subscriptions[user_id].get('expiry')
        plan = user_subscriptions[user_id].get('plan', 'premium')
        if expiry and expiry > datetime.now():
            if plan == 'vip':
                return get_config('vip_user_limit', 50)
            return get_config('premium_user_limit', 15)
    return get_config('free_user_limit', 10)

def get_user_file_count(user_id):
    """Get number of files uploaded by user"""
    return len(user_files.get(user_id, []))

def is_user_banned(user_id):
    """Check if user is banned"""
    if user_id not in banned_users:
        return False, None
    ban_info = banned_users[user_id]
    if ban_info.get('ban_type') == 'temporary':
        expires_at = ban_info.get('expires_at')
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) < datetime.now():
                    # Ban expired
                    unban_user_db(user_id)
                    return False, None
            except ValueError:
                pass
    return True, ban_info

def is_bot_running(script_owner_id, file_name):
    """Check if a bot script is currently running"""
    script_key = f"{script_owner_id}_{file_name}"
    with BOT_SCRIPTS_LOCK:
        script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = (proc.is_running() and
                         proc.status() != psutil.STATUS_ZOMBIE)
            if not is_running:
                _cleanup_script(script_key)
            return is_running
        except psutil.NoSuchProcess:
            _cleanup_script(script_key)
            return False
        except Exception as e:
            logger.error(f"Error checking process: {e}")
            return False
    return False

def _cleanup_script(script_key):
    """Clean up a dead script entry"""
    with BOT_SCRIPTS_LOCK:
        if script_key in bot_scripts:
            info = bot_scripts[script_key]
            if 'log_file' in info:
                try:
                    if not info['log_file'].closed:
                        info['log_file'].close()
                except Exception:
                    pass
            del bot_scripts[script_key]
            logger.info(f"Cleaned up dead script: {script_key}")

def get_script_uptime(script_key):
    """Get uptime of a running script"""
    with BOT_SCRIPTS_LOCK:
        info = bot_scripts.get(script_key)
    if info and 'start_time' in info:
        return format_uptime(info['start_time'])
    return "Unknown"

def get_script_resources(script_key):
    """Get CPU and RAM usage of a script"""
    with BOT_SCRIPTS_LOCK:
        info = bot_scripts.get(script_key)
    if info and info.get('process'):
        try:
            proc = psutil.Process(info['process'].pid)
            cpu = proc.cpu_percent(interval=0.1)
            ram = proc.memory_info().rss / 1024 / 1024  # MB
            return cpu, ram
        except Exception:
            pass
    return 0, 0

def check_file_hash(file_content):
    """Generate MD5 and SHA256 hash of file"""
    md5 = hashlib.md5(file_content).hexdigest()
    sha256 = hashlib.sha256(file_content).hexdigest()
    return md5, sha256

def rate_limit_check(user_id, action='general'):
    """Check if user is rate limited"""
    now = time.time()
    if action == 'upload':
        last = user_last_upload.get(user_id, 0)
        cooldown = get_config('upload_cooldown_seconds', UPLOAD_COOLDOWN_SECONDS)
        if now - last < cooldown:
            return False, cooldown - (now - last)
        user_last_upload[user_id] = now
    else:
        last = user_last_action.get(user_id, 0)
        cooldown = get_config('rate_limit_seconds', RATE_LIMIT_SECONDS)
        if now - last < cooldown:
            return False, cooldown - (now - last)
        user_last_action[user_id] = now
    return True, 0

# ============================================================
# INITIALIZE DATABASE
# ============================================================
init_db()
load_data()
logger.info("✅ Database ready.")

# ============================================================
# END OF CHUNK 2
# ============================================================
# CHUNK 3: Security, Force Subscribe & Malware Detection
# ============================================================
# PASTE THIS AFTER CHUNK 2
# ============================================================

# ============================================================
# SECURITY DECORATORS & MIDDLEWARE
# ============================================================

def check_user_access(func):
    """
    Master security decorator for all message handlers.
    Checks: ban, maintenance, force sub in order.
    """
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id

        # --- Always allow owner ---
        if user_id == OWNER_ID:
            return func(message, *args, **kwargs)

        # --- Check if banned ---
        is_banned, ban_info = is_user_banned(user_id)
        if is_banned:
            ban_type = ban_info.get('ban_type', 'permanent')
            reason = ban_info.get('reason', 'No reason provided')
            expires = ban_info.get('expires_at', None)

            ban_msg = (
                f"🚫 *Access Denied*\n"
                f"{DIVIDER}\n"
                f"You have been *banned* from this bot.\n\n"
                f"📋 *Reason:* {reason}\n"
                f"🔒 *Type:* {ban_type.title()}\n"
            )
            if expires:
                try:
                    exp_dt = datetime.fromisoformat(expires)
                    days_left = (exp_dt - datetime.now()).days
                    ban_msg += f"⏳ *Expires in:* {days_left} days\n"
                except Exception:
                    pass

            ban_msg += (
                f"\n{THIN_DIVIDER}\n"
                f"_Contact support if you think this is a mistake._"
            )

            # Notify owner if config says so
            if get_config('notify_ban_attempt', True):
                try:
                    bot.send_message(
                        OWNER_ID,
                        f"🚫 *Banned User Attempt*\n"
                        f"👤 User: `{user_id}`\n"
                        f"📝 Name: {message.from_user.first_name}\n"
                        f"⚡ Action: {message.text or 'Non-text message'}",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "📞 Contact Support",
                url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"
            ))
            try:
                bot.reply_to(message, ban_msg,
                            parse_mode='Markdown',
                            reply_markup=markup)
            except Exception:
                pass
            return

        # --- Check maintenance mode ---
        if get_config('maintenance_mode', False):
            maint_msg = (
                f"🔧 *Maintenance Mode*\n"
                f"{DIVIDER}\n"
                f"{get_config('maintenance_message', 'Bot is under maintenance.')}\n"
                f"{THIN_DIVIDER}\n"
                f"_Please try again later._"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "📢 Updates Channel",
                url=UPDATE_CHANNEL
            ))
            try:
                bot.reply_to(message, maint_msg,
                            parse_mode='Markdown',
                            reply_markup=markup)
            except Exception:
                pass
            return

        # --- Check bot locked ---
        if get_config('bot_locked', False) and user_id not in admin_ids:
            locked_msg = (
                f"🔒 *Bot Locked*\n"
                f"{DIVIDER}\n"
                f"{get_config('locked_message', 'Bot is locked by admin.')}\n"
                f"{THIN_DIVIDER}\n"
                f"_Please try again later._"
            )
            try:
                bot.reply_to(message, locked_msg, parse_mode='Markdown')
            except Exception:
                pass
            return

        # --- Check force subscribe ---
        if (get_config('force_sub_enabled', False) and
                force_sub_chats and
                user_id not in verified_users):
            if not check_force_sub(user_id):
                send_force_sub_message(message)
                return

        # --- Rate limit check ---
        allowed, wait_time = rate_limit_check(user_id)
        if not allowed:
            try:
                bot.reply_to(
                    message,
                    f"⏳ *Rate Limited*\n"
                    f"Please wait `{wait_time:.1f}` seconds.",
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return

        # --- Update user activity ---
        add_active_user(
            user_id,
            message.from_user.first_name or "",
            message.from_user.username or ""
        )

        # --- Update daily stats ---
        global daily_stats
        with MESSAGES_LOCK:
            if daily_stats['date'] != datetime.now().date():
                daily_stats = {
                    'messages': 0,
                    'uploads': 0,
                    'scripts_started': 0,
                    'date': datetime.now().date()
                }
            daily_stats['messages'] += 1

        return func(message, *args, **kwargs)
    return wrapper


def check_callback_access(func):
    """Security decorator for callback query handlers"""
    @wraps(func)
    def wrapper(call, *args, **kwargs):
        user_id = call.from_user.id

        if user_id == OWNER_ID:
            return func(call, *args, **kwargs)

        is_banned, ban_info = is_user_banned(user_id)
        if is_banned:
            bot.answer_callback_query(
                call.id,
                "🚫 You are banned from this bot.",
                show_alert=True
            )
            return

        if (get_config('maintenance_mode', False) and
                user_id not in admin_ids):
            bot.answer_callback_query(
                call.id,
                "🔧 Bot is under maintenance.",
                show_alert=True
            )
            return

        if (get_config('bot_locked', False) and
                user_id not in admin_ids and
                call.data not in ['back_to_main', 'speed', 'stats']):
            bot.answer_callback_query(
                call.id,
                "🔒 Bot is locked by admin.",
                show_alert=True
            )
            return

        return func(call, *args, **kwargs)
    return wrapper


def admin_required(func):
    """Decorator requiring admin permissions"""
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        if user_id not in admin_ids:
            bot.reply_to(
                message,
                f"🛡️ *Admin Required*\n"
                f"You need admin permissions for this action.",
                parse_mode='Markdown'
            )
            return
        return func(message, *args, **kwargs)
    return wrapper


def owner_required(func):
    """Decorator requiring owner permissions"""
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        if user_id != OWNER_ID:
            bot.reply_to(
                message,
                f"👑 *Owner Required*\n"
                f"This action requires owner permissions.",
                parse_mode='Markdown'
            )
            return
        return func(message, *args, **kwargs)
    return wrapper


# ============================================================
# FORCE SUBSCRIBE SYSTEM
# ============================================================

def check_force_sub(user_id):
    """
    Check if user is member of all required chats.
    Returns True if user passes all checks.
    """
    if user_id == OWNER_ID or user_id in admin_ids:
        return True

    if not force_sub_chats:
        return True

    if user_id in verified_users:
        return True

    all_joined = True
    for chat in force_sub_chats:
        chat_id = chat['chat_id']
        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status in ['left', 'kicked', 'banned']:
                all_joined = False
                break
        except Exception as e:
            logger.error(f"Error checking force sub for {user_id} in {chat_id}: {e}")
            all_joined = False
            break

    if all_joined:
        # Mark as verified
        verified_users.add(user_id)
        with DB_LOCK:
            try:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute('''INSERT OR REPLACE INTO verified_force_sub
                             (user_id, verified_at) VALUES (?, ?)''',
                          (user_id, datetime.now().isoformat()))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Error saving verified user: {e}")

    return all_joined


def get_unjoined_chats(user_id):
    """Get list of chats user hasn't joined yet"""
    unjoined = []
    for chat in force_sub_chats:
        chat_id = chat['chat_id']
        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status in ['left', 'kicked', 'banned']:
                unjoined.append(chat)
        except Exception:
            unjoined.append(chat)
    return unjoined


def send_force_sub_message(message):
    """Send beautiful force subscribe message with join buttons"""
    user_id = message.from_user.id
    unjoined = get_unjoined_chats(user_id)

    if not unjoined:
        # User actually joined all - verify and continue
        verified_users.add(user_id)
        return

    # Build beautiful message
    msg_text = (
        f"📢 *Join Required Chats*\n"
        f"{DIVIDER}\n"
        f"To use this bot, you must join\n"
        f"all the channels/groups below:\n\n"
    )

    for i, chat in enumerate(unjoined, 1):
        chat_name = chat.get('chat_name') or 'Channel/Group'
        chat_type = chat.get('chat_type', 'channel')
        type_icon = "📢" if chat_type == 'channel' else "👥"
        msg_text += f"{type_icon} *{i}. {chat_name}*\n"

    msg_text += (
        f"\n{THIN_DIVIDER}\n"
        f"After joining, click *✅ Check Membership*"
    )

    # Build inline keyboard with join buttons
    markup = types.InlineKeyboardMarkup(row_width=1)

    for chat in unjoined:
        chat_name = chat.get('chat_name') or 'Join Channel'
        chat_type = chat.get('chat_type', 'channel')
        type_icon = "📢" if chat_type == 'channel' else "👥"
        btn_text = f"{type_icon} Join {chat_name}"

        if chat.get('is_private'):
            # Private chat - use invite link
            invite_link = chat.get('invite_link')
            if invite_link:
                markup.add(types.InlineKeyboardButton(
                    btn_text,
                    url=invite_link
                ))
            else:
                markup.add(types.InlineKeyboardButton(
                    f"⚠️ {chat_name} (Link unavailable)",
                    callback_data='no_link'
                ))
        else:
            # Public chat - use username or link
            username = chat.get('chat_username', '')
            if username:
                if not username.startswith('@'):
                    username = '@' + username
                join_url = f"https://t.me/{username.replace('@', '')}"
            else:
                join_url = chat.get('invite_link', '')

            if join_url:
                markup.add(types.InlineKeyboardButton(
                    btn_text,
                    url=join_url
                ))

    # Check membership button
    markup.add(types.InlineKeyboardButton(
        "✅ I've Joined All - Check Now",
        callback_data='check_force_sub'
    ))

    try:
        bot.reply_to(
            message,
            msg_text,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error sending force sub message: {e}")


def handle_check_force_sub_callback(call):
    """Handle when user clicks 'I've Joined' button"""
    user_id = call.from_user.id

    bot.answer_callback_query(call.id, "🔍 Checking membership...")

    unjoined = get_unjoined_chats(user_id)

    if not unjoined:
        # All joined!
        verified_users.add(user_id)
        with DB_LOCK:
            try:
                conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                c = conn.cursor()
                c.execute('''INSERT OR REPLACE INTO verified_force_sub
                             (user_id, verified_at) VALUES (?, ?)''',
                          (user_id, datetime.now().isoformat()))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Error saving verified user: {e}")

        success_msg = (
            f"✅ *Access Granted!*\n"
            f"{DIVIDER}\n"
            f"Welcome! You've joined all required chats.\n"
            f"You can now use the bot freely.\n"
            f"{THIN_DIVIDER}\n"
            f"_Use /start to begin._"
        )
        try:
            bot.edit_message_text(
                success_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                success_msg,
                parse_mode='Markdown'
            )
    else:
        # Still not joined all
        remaining = len(unjoined)
        chat_names = "\n".join([
            f"• {c.get('chat_name', 'Unknown')}"
            for c in unjoined
        ])

        still_msg = (
            f"⚠️ *Not Joined Yet*\n"
            f"{DIVIDER}\n"
            f"You still need to join "
            f"*{remaining}* chat(s):\n\n"
            f"{chat_names}\n\n"
            f"{THIN_DIVIDER}\n"
            f"_Please join and try again._"
        )

        # Rebuild buttons for remaining chats
        markup = types.InlineKeyboardMarkup(row_width=1)
        for chat in unjoined:
            chat_name = chat.get('chat_name') or 'Join'
            chat_type = chat.get('chat_type', 'channel')
            type_icon = "📢" if chat_type == 'channel' else "👥"

            if chat.get('is_private'):
                invite_link = chat.get('invite_link')
                if invite_link:
                    markup.add(types.InlineKeyboardButton(
                        f"{type_icon} Join {chat_name}",
                        url=invite_link
                    ))
            else:
                username = chat.get('chat_username', '')
                if username:
                    if not username.startswith('@'):
                        username = '@' + username
                    join_url = f"https://t.me/{username.replace('@', '')}"
                    markup.add(types.InlineKeyboardButton(
                        f"{type_icon} Join {chat_name}",
                        url=join_url
                    ))

        markup.add(types.InlineKeyboardButton(
            "✅ Check Again",
            callback_data='check_force_sub'
        ))

        try:
            bot.edit_message_text(
                still_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error updating force sub message: {e}")


# ============================================================
# MALWARE DETECTION SYSTEM
# ============================================================

def get_file_type_from_content(file_content):
    """Detect file type from magic bytes"""
    signatures = {
        b'\x7fELF': 'application/x-executable',
        b'MZ': 'application/x-dosexec',
        b'\xfe\xed\xfa': 'application/x-mach-binary',
        b'\xce\xfa\xed\xfe': 'application/x-mach-binary',
        b'PK': 'application/zip',
        b'Rar!': 'application/x-rar',
        b'\x89PNG': 'image/png',
        b'\xff\xd8\xff': 'image/jpeg',
        b'GIF8': 'image/gif',
        b'%PDF': 'application/pdf',
    }
    for sig, mime in signatures.items():
        if file_content[:len(sig)] == sig:
            return mime
    return 'application/octet-stream'


def calculate_entropy(data):
    """
    Calculate Shannon entropy of data.
    High entropy (>7.0) may indicate encryption/packing.
    """
    if not data:
        return 0.0
    byte_counts = [0] * 256
    for byte in data:
        byte_counts[byte] += 1
    entropy = 0.0
    data_len = len(data)
    for count in byte_counts:
        if count > 0:
            prob = count / data_len
            entropy -= prob * (prob.bit_length() - 1)
    return entropy


def is_suspicious_file(file_content, file_name, file_ext):
    """
    Comprehensive file security check.
    Returns (is_suspicious, reason, severity)
    """
    file_lower = file_name.lower()

    # --- Check 1: Executable extensions ---
    if any(file_lower.endswith(ext) for ext in EXECUTABLE_EXTENSIONS):
        return True, f"Executable file extension: {file_ext}", "high"

    # --- Check 2: Malware signatures in content ---
    for signature in MALWARE_SIGNATURES:
        if file_content[:len(signature)] == signature:
            return (True,
                    f"Malware signature: {signature.hex()}",
                    "critical")

    # --- Check 3: Sample first 8KB ---
    sample_size = min(len(file_content), 8192)
    file_sample = file_content[:sample_size]

    # --- Check 4: Encrypted indicators ---
    for indicator in ENCRYPTED_FILE_INDICATORS:
        if indicator in file_sample:
            return (True,
                    f"Encrypted indicator: "
                    f"{indicator.decode('utf-8', errors='ignore')}",
                    "medium")

    # --- Check 5: Suspicious keywords ---
    sample_text = file_sample.decode('utf-8', errors='ignore').lower()
    for keyword in SUSPICIOUS_KEYWORDS:
        kw = keyword.decode('utf-8').lower()
        if kw in sample_text:
            return True, f"Suspicious keyword: {kw}", "high"

    # --- Check 6: File type mismatch ---
    detected_type = get_file_type_from_content(file_content)
    if (file_ext not in ['.zip'] and
            detected_type in [
                'application/x-dosexec',
                'application/x-executable',
                'application/x-mach-binary'
            ]):
        return (True,
                f"Executable type detected: {detected_type}",
                "high")

    # --- Check 7: High entropy (possible encrypted/packed) ---
    # Only for non-zip files since zips are naturally high entropy
    if file_ext not in ['.zip'] and len(file_content) > 1024:
        entropy = calculate_entropy(file_content[:4096])
        if entropy > 7.5:
            return (True,
                    f"Suspiciously high entropy: {entropy:.2f} "
                    f"(possible encryption/packing)",
                    "medium")

    # --- Check 8: ZIP content scan (non-owner) ---
    if file_ext == '.zip':
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
                for name in zf.namelist():
                    name_lower = name.lower()
                    if any(name_lower.endswith(ext)
                           for ext in EXECUTABLE_EXTENSIONS):
                        return (True,
                                f"ZIP contains executable: {name}",
                                "high")
                    # Path traversal check
                    if '..' in name or name.startswith('/'):
                        return (True,
                                f"ZIP path traversal: {name}",
                                "critical")
        except zipfile.BadZipFile:
            return True, "Invalid/corrupted ZIP file", "medium"
        except Exception as e:
            logger.warning(f"ZIP scan error: {e}")

    return False, "File appears safe", "none"


def scan_file_for_malware(file_content, file_name, user_id):
    """
    Full malware scan with logging.
    Owner bypasses all checks.
    Returns (is_safe, reason)
    """
    if user_id == OWNER_ID:
        return True, "✅ Owner bypass - no scan needed"

    file_ext = os.path.splitext(file_name)[1].lower()
    is_suspicious, reason, severity = is_suspicious_file(
        file_content, file_name, file_ext
    )

    if is_suspicious:
        logger.warning(
            f"🚨 MALWARE DETECTED: {file_name} "
            f"from user {user_id} | "
            f"Reason: {reason} | "
            f"Severity: {severity}"
        )

        # Log to audit
        log_audit(
            user_id,
            'malware_detected',
            f"Malware in '{file_name}': {reason} (Severity: {severity})",
            severity='critical'
        )

        # Notify owner
        if get_config('notify_system_alert', True):
            try:
                severity_icon = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡'
                }.get(severity, '⚠️')

                bot.send_message(
                    OWNER_ID,
                    f"🚨 *Malware Detection Alert*\n"
                    f"{DIVIDER}\n"
                    f"{severity_icon} *Severity:* {severity.upper()}\n"
                    f"👤 *User:* `{user_id}`\n"
                    f"📄 *File:* `{file_name}`\n"
                    f"🔍 *Reason:* {reason}\n"
                    f"🕐 *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify owner of malware: {e}")

        return False, f"🚨 Security violation: {reason}"

    return True, "✅ File passed security scan"


# ============================================================
# BAN SYSTEM HELPERS
# ============================================================

def check_and_auto_ban(user_id, warned_by):
    """Check if user should be auto-banned after warnings"""
    max_warns = get_config('max_warnings_before_ban', MAX_WARNINGS_BEFORE_BAN)
    current_warns = len(warned_users.get(user_id, []))

    if current_warns >= max_warns:
        # Auto ban
        ban_user_db(
            user_id,
            ban_type='permanent',
            reason=f'Auto-banned after {current_warns} warnings',
            banned_by=OWNER_ID
        )

        # Notify owner
        try:
            bot.send_message(
                OWNER_ID,
                f"🤖 *Auto-Ban Triggered*\n"
                f"{DIVIDER}\n"
                f"👤 User `{user_id}` has been auto-banned\n"
                f"after reaching {current_warns} warnings.\n"
                f"{THIN_DIVIDER}\n"
                f"_Use owner panel to review._",
                parse_mode='Markdown'
            )
        except Exception:
            pass

        # Notify user
        try:
            bot.send_message(
                user_id,
                f"🚫 *You Have Been Banned*\n"
                f"{DIVIDER}\n"
                f"You received too many warnings "
                f"and have been automatically banned.\n"
                f"{THIN_DIVIDER}\n"
                f"_Contact support to appeal._"
            )
        except Exception:
            pass

        return True
    return False


def send_warning_to_user(user_id, reason, warned_by,
                         remaining_before_ban):
    """Send warning notification to user"""
    max_warns = get_config('max_warnings_before_ban',
                           MAX_WARNINGS_BEFORE_BAN)
    current = len(warned_users.get(user_id, []))

    warn_msg = (
        f"⚠️ *Official Warning*\n"
        f"{DIVIDER}\n"
        f"You have received a warning from an admin.\n\n"
        f"📋 *Reason:* {reason}\n"
        f"⚠️ *Warnings:* {current}/{max_warns}\n"
    )

    if remaining_before_ban <= 1:
        warn_msg += (
            f"\n🚨 *FINAL WARNING!*\n"
            f"One more violation will result in a permanent ban."
        )
    else:
        warn_msg += (
            f"\n_{remaining_before_ban} more warnings "
            f"will result in a ban._"
        )

    try:
        bot.send_message(user_id, warn_msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Failed to send warning to {user_id}: {e}")


# ============================================================
# PROCESS KILL HELPER
# ============================================================

def kill_process_tree(process_info):
    """Kill a process and all its children safely"""
    pid = None
    script_key = process_info.get('script_key', 'N/A')

    try:
        # Close log file first
        if ('log_file' in process_info and
                hasattr(process_info['log_file'], 'close') and
                not process_info['log_file'].closed):
            try:
                process_info['log_file'].close()
            except Exception as e:
                logger.error(f"Error closing log file for {script_key}: {e}")

        process = process_info.get('process')
        if not process or not hasattr(process, 'pid'):
            return

        pid = process.pid
        if not pid:
            return

        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)

            # Terminate children first
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
                except Exception:
                    try:
                        child.kill()
                    except Exception:
                        pass

            # Wait for children
            gone, alive = psutil.wait_procs(children, timeout=2)
            for p in alive:
                try:
                    p.kill()
                except Exception:
                    pass

            # Terminate parent
            try:
                parent.terminate()
                try:
                    parent.wait(timeout=2)
                except psutil.TimeoutExpired:
                    parent.kill()
            except psutil.NoSuchProcess:
                pass
            except Exception:
                try:
                    parent.kill()
                except Exception:
                    pass

            logger.info(f"✅ Killed process tree for {script_key} (PID: {pid})")

        except psutil.NoSuchProcess:
            logger.warning(f"Process {pid} for {script_key} already gone")

    except Exception as e:
        logger.error(
            f"Error killing process tree for {script_key}: {e}",
            exc_info=True
        )


# ============================================================
# AUTO RESTART MONITOR
# ============================================================

def monitor_script_crashes():
    """
    Background thread that monitors running scripts
    and auto-restarts them if they crash.
    """
    logger.info("🔍 Script crash monitor started.")
    while True:
        try:
            time.sleep(10)  # Check every 10 seconds

            if not get_config('auto_restart_scripts', True):
                continue

            with BOT_SCRIPTS_LOCK:
                scripts_to_check = list(bot_scripts.items())

            for script_key, info in scripts_to_check:
                try:
                    process = info.get('process')
                    if not process:
                        continue

                    # Check if process has exited
                    return_code = process.poll()
                    if return_code is None:
                        continue  # Still running

                    # Process has exited
                    owner_id = info.get('script_owner_id')
                    file_name = info.get('file_name')
                    file_type = info.get('file_type', 'py')
                    user_folder = info.get('user_folder')
                    chat_id = info.get('chat_id')

                    logger.warning(
                        f"Script {script_key} exited with "
                        f"code {return_code}"
                    )

                    # Read last log lines for crash report
                    last_log = ""
                    log_file_path = os.path.join(
                        user_folder,
                        f"{os.path.splitext(file_name)[0]}.log"
                    )
                    if os.path.exists(log_file_path):
                        try:
                            with open(log_file_path, 'r',
                                      encoding='utf-8',
                                      errors='ignore') as f:
                                lines = f.readlines()
                                last_log = "".join(lines[-20:])
                        except Exception:
                            pass

                    # Clean up from bot_scripts
                    _cleanup_script(script_key)

                    # Normal exit (code 0) - don't restart
                    if return_code == 0:
                        logger.info(f"Script {script_key} exited normally")
                        if chat_id:
                            try:
                                bot.send_message(
                                    chat_id,
                                    f"ℹ️ *Script Stopped*\n"
                                    f"{DIVIDER}\n"
                                    f"📜 `{file_name}` exited normally.\n"
                                    f"_(Exit code: 0)_",
                                    parse_mode='Markdown'
                                )
                            except Exception:
                                pass
                        continue

                    # Crash detected - attempt restart
                    crash_key = f"{owner_id}_{file_name}"
                    if crash_key not in script_crash_counts:
                        script_crash_counts[crash_key] = {
                            'count': 0,
                            'first_crash': datetime.now()
                        }

                    crash_info = script_crash_counts[crash_key]

                    # Reset counter if stable for reset period
                    reset_minutes = get_config(
                        'restart_reset_minutes',
                        RESTART_RESET_MINUTES
                    )
                    time_since_first = (
                        datetime.now() - crash_info['first_crash']
                    ).total_seconds() / 60

                    if time_since_first > reset_minutes:
                        crash_info['count'] = 0
                        crash_info['first_crash'] = datetime.now()

                    crash_info['count'] += 1
                    max_restarts = get_config(
                        'max_restart_attempts',
                        MAX_RESTART_ATTEMPTS
                    )

                    # Save crash report
                    save_crash_report(
                        owner_id, file_name, return_code,
                        last_log, crash_info['count']
                    )

                    # Notify user of crash
                    crash_msg = (
                        f"💥 *Script Crashed!*\n"
                        f"{DIVIDER}\n"
                        f"📜 *File:* `{file_name}`\n"
                        f"🔢 *Exit Code:* `{return_code}`\n"
                        f"🔄 *Restart:* {crash_info['count']}"
                        f"/{max_restarts}\n"
                    )

                    if crash_info['count'] <= max_restarts:
                        delay = get_config(
                            'restart_delay_seconds',
                            RESTART_DELAY_SECONDS
                        )
                        crash_msg += (
                            f"⏳ *Restarting in:* {delay}s\n"
                            f"{THIN_DIVIDER}\n"
                            f"📋 *Last log:*\n"
                            f"```\n{last_log[-500:]}\n```"
                        )

                        if (chat_id and
                                get_config('notify_script_crash', True)):
                            try:
                                bot.send_message(
                                    chat_id,
                                    crash_msg,
                                    parse_mode='Markdown'
                                )
                            except Exception:
                                pass

                        # Restart after delay
                        def do_restart(fn=file_name, ft=file_type,
                                       oid=owner_id, uf=user_folder,
                                       cid=chat_id):
                            time.sleep(get_config(
                                'restart_delay_seconds',
                                RESTART_DELAY_SECONDS
                            ))
                            fp = os.path.join(uf, fn)
                            if not os.path.exists(fp):
                                logger.error(
                                    f"Cannot restart {fn}: file missing"
                                )
                                return

                            # Create fake message for reply
                            class FakeMessage:
                                class chat:
                                    id = cid
                                class from_user:
                                    id = oid

                            fake_msg = FakeMessage()

                            if ft == 'py':
                                run_script(fp, oid, uf, fn, fake_msg)
                            elif ft == 'js':
                                run_js_script(fp, oid, uf, fn, fake_msg)

                        threading.Thread(
                            target=do_restart,
                            daemon=True
                        ).start()

                    else:
                        # Max restarts reached
                        crash_msg = (
                            f"💥 *Script Permanently Stopped*\n"
                            f"{DIVIDER}\n"
                            f"📜 *File:* `{file_name}`\n"
                            f"🔢 *Exit Code:* `{return_code}`\n"
                            f"🔄 *Restarts Attempted:* "
                            f"{crash_info['count'] - 1}\n\n"
                            f"❌ *Maximum restart attempts reached.*\n"
                            f"Please fix your script and restart manually.\n"
                            f"{THIN_DIVIDER}\n"
                            f"📋 *Last log:*\n"
                            f"```\n{last_log[-500:]}\n```"
                        )

                        if chat_id:
                            try:
                                bot.send_message(
                                    chat_id,
                                    crash_msg,
                                    parse_mode='Markdown'
                                )
                            except Exception:
                                pass

                        # Notify owner too
                        if get_config('notify_script_crash', True):
                            try:
                                bot.send_message(
                                    OWNER_ID,
                                    f"💥 *Script Gave Up Restarting*\n"
                                    f"{DIVIDER}\n"
                                    f"👤 *User:* `{owner_id}`\n"
                                    f"📜 *File:* `{file_name}`\n"
                                    f"🔄 *Attempts:* {crash_info['count'] - 1}",
                                    parse_mode='Markdown'
                                )
                            except Exception:
                                pass

                        # Reset crash counter
                        if crash_key in script_crash_counts:
                            del script_crash_counts[crash_key]

                except Exception as e:
                    logger.error(
                        f"Error monitoring script {script_key}: {e}",
                        exc_info=True
                    )

        except Exception as e:
            logger.error(f"Crash monitor error: {e}", exc_info=True)
            time.sleep(30)


# ============================================================
# DEAD PROCESS CLEANER
# ============================================================

def clean_dead_processes():
    """
    Background thread that periodically cleans up
    dead/zombie processes from bot_scripts dict.
    """
    logger.info("🧹 Dead process cleaner started.")
    while True:
        try:
            time.sleep(60)  # Every minute

            with BOT_SCRIPTS_LOCK:
                keys = list(bot_scripts.keys())

            cleaned = 0
            for key in keys:
                with BOT_SCRIPTS_LOCK:
                    info = bot_scripts.get(key)
                if not info:
                    continue

                owner_id = info.get('script_owner_id')
                file_name = info.get('file_name')

                if not is_bot_running(owner_id, file_name):
                    _cleanup_script(key)
                    cleaned += 1

            if cleaned > 0:
                logger.info(f"🧹 Cleaned {cleaned} dead processes")

        except Exception as e:
            logger.error(f"Dead process cleaner error: {e}")
            time.sleep(60)


# ============================================================
# UPTIME HEARTBEAT
# ============================================================

def uptime_heartbeat():
    """
    Background thread that logs bot uptime every minute
    and sends daily/weekly reports to owner.
    """
    logger.info("💓 Uptime heartbeat started.")
    last_daily_report = datetime.now().date()
    last_weekly_report = datetime.now().isocalendar()[1]

    while True:
        try:
            time.sleep(60)  # Every minute

            # Log uptime
            start = time.time()
            log_uptime('online', round((time.time() - start) * 1000, 2))

            now = datetime.now()

            # Daily report
            if (get_config('daily_report', False) and
                    now.date() != last_daily_report and
                    now.hour == 9):
                send_daily_report()
                last_daily_report = now.date()

            # Weekly report
            current_week = now.isocalendar()[1]
            if (get_config('weekly_report', False) and
                    current_week != last_weekly_report and
                    now.weekday() == 0):
                send_weekly_report()
                last_weekly_report = current_week

        except Exception as e:
            logger.error(f"Uptime heartbeat error: {e}")
            time.sleep(60)


def send_daily_report():
    """Send daily statistics report to owner"""
    try:
        uptime_24h = get_uptime_percentage(24)
        total_users = len(active_users)
        running_scripts = len(bot_scripts)

        report = (
            f"📊 *Daily Report*\n"
            f"{DIVIDER}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"👥 Total Users: *{total_users}*\n"
            f"🟢 Running Scripts: *{running_scripts}*\n"
            f"⏱️ Uptime (24h): *{uptime_24h}%*\n"
            f"💬 Messages Today: *{daily_stats.get('messages', 0)}*\n"
            f"📤 Uploads Today: *{daily_stats.get('uploads', 0)}*\n"
            f"🚀 Scripts Started: "
            f"*{daily_stats.get('scripts_started', 0)}*\n"
            f"{THIN_DIVIDER}\n"
            f"_Automated daily report_"
        )

        bot.send_message(OWNER_ID, report, parse_mode='Markdown')
        logger.info("Daily report sent to owner")
    except Exception as e:
        logger.error(f"Error sending daily report: {e}")


def send_weekly_report():
    """Send weekly statistics report to owner"""
    try:
        uptime_7d = get_uptime_percentage(168)  # 7 days

        report = (
            f"📈 *Weekly Report*\n"
            f"{DIVIDER}\n"
            f"📅 Week: {datetime.now().strftime('%Y-W%W')}\n\n"
            f"👥 Total Users: *{len(active_users)}*\n"
            f"💳 Premium Users: *{len(user_subscriptions)}*\n"
            f"⏱️ Uptime (7d): *{uptime_7d}%*\n"
            f"🔒 Banned Users: *{len(banned_users)}*\n"
            f"{THIN_DIVIDER}\n"
            f"_Automated weekly report_"
        )

        bot.send_message(OWNER_ID, report, parse_mode='Markdown')
        logger.info("Weekly report sent to owner")
    except Exception as e:
        logger.error(f"Error sending weekly report: {e}")


# ============================================================
# SYSTEM RESOURCE ALERT
# ============================================================

def system_resource_monitor():
    """
    Background thread monitoring system resources.
    Alerts owner if thresholds exceeded.
    """
    logger.info("🖥️ System resource monitor started.")
    alert_cooldown = {}  # Prevent spam alerts

    while True:
        try:
            time.sleep(30)  # Check every 30 seconds

            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent

            alerts = []
            now = time.time()

            cpu_thresh = get_config('cpu_alert_threshold', 90)
            ram_thresh = get_config('ram_alert_threshold', 85)
            disk_thresh = get_config('disk_alert_threshold', 90)

            if cpu > cpu_thresh:
                if now - alert_cooldown.get('cpu', 0) > 300:
                    alerts.append(
                        f"🖥️ CPU: *{cpu:.1f}%* "
                        f"(Threshold: {cpu_thresh}%)"
                    )
                    alert_cooldown['cpu'] = now

            if ram > ram_thresh:
                if now - alert_cooldown.get('ram', 0) > 300:
                    alerts.append(
                        f"🧠 RAM: *{ram:.1f}%* "
                        f"(Threshold: {ram_thresh}%)"
                    )
                    alert_cooldown['ram'] = now

            if disk > disk_thresh:
                if now - alert_cooldown.get('disk', 0) > 3600:
                    alerts.append(
                        f"💾 Disk: *{disk:.1f}%* "
                        f"(Threshold: {disk_thresh}%)"
                    )
                    alert_cooldown['disk'] = now

            if alerts and get_config('notify_system_alert', True):
                alert_text = (
                    f"⚠️ *System Resource Alert*\n"
                    f"{DIVIDER}\n"
                    + "\n".join(alerts) +
                    f"\n{THIN_DIVIDER}\n"
                    f"🕐 {datetime.now().strftime('%H:%M:%S')}"
                )
                try:
                    bot.send_message(
                        OWNER_ID,
                        alert_text,
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Resource monitor error: {e}")
            time.sleep(60)


# ============================================================
# START BACKGROUND THREADS
# ============================================================

def start_background_threads():
    """Start all background monitoring threads"""
    threads = [
        ("CrashMonitor", monitor_script_crashes),
        ("DeadProcessCleaner", clean_dead_processes),
        ("UptimeHeartbeat", uptime_heartbeat),
        ("ResourceMonitor", system_resource_monitor),
    ]

    for name, target in threads:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        logger.info(f"✅ Background thread started: {name}")


# ============================================================
# END OF CHUNK 3
# ============================================================
# CHUNK 4: Script Runner System
# ============================================================
# PASTE THIS AFTER CHUNK 3
# ============================================================

# ============================================================
# PENDING APPROVAL SYSTEM
# ============================================================

# Store files pending owner approval
pending_approvals = {}
# Format: {
#   approval_id: {
#     'user_id': int,
#     'file_name': str,
#     'file_type': str,
#     'file_path': str,
#     'user_folder': str,
#     'reason': str,
#     'severity': str,
#     'submitted_at': datetime,
#     'message_obj': message,
#     'file_content': bytes
#   }
# }

def generate_approval_id():
    """Generate unique approval ID"""
    return secrets.token_hex(8)

def request_owner_approval(
    file_content, file_name, file_type,
    file_path, user_folder, reason,
    severity, message
):
    """
    Send file to owner for approval when
    potentially harmful content detected.
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    username = message.from_user.username or "N/A"

    approval_id = generate_approval_id()

    # Store pending approval
    pending_approvals[approval_id] = {
        'user_id': user_id,
        'file_name': file_name,
        'file_type': file_type,
        'file_path': file_path,
        'user_folder': user_folder,
        'reason': reason,
        'severity': severity,
        'submitted_at': datetime.now(),
        'message_obj': message,
        'file_content': file_content
    }

    # Severity icon
    severity_icon = {
        'critical': '🔴',
        'high': '🟠',
        'medium': '🟡',
        'low': '🟢'
    }.get(severity, '⚠️')

    # Get file hash
    md5, sha256 = check_file_hash(file_content)

    # Message to owner
    owner_msg = (
        f"🔍 *File Approval Required*\n"
        f"{DIVIDER}\n"
        f"A file has been flagged and requires\n"
        f"your approval before hosting.\n\n"
        f"👤 *User:* {user_name}\n"
        f"🆔 *User ID:* `{user_id}`\n"
        f"✳️ *Username:* @{username}\n\n"
        f"📄 *File:* `{file_name}`\n"
        f"🏷️ *Type:* `{file_type.upper()}`\n"
        f"📦 *Size:* {format_size(len(file_content))}\n\n"
        f"{severity_icon} *Severity:* `{severity.upper()}`\n"
        f"🔍 *Reason:* {reason}\n\n"
        f"🔑 *MD5:* `{md5}`\n"
        f"🔒 *SHA256:* `{sha256[:32]}...`\n\n"
        f"🆔 *Approval ID:* `{approval_id}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Review the file and approve or reject._"
    )

    # Approval buttons
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✅ Approve & Run",
            callback_data=f'approve_file_{approval_id}'
        ),
        types.InlineKeyboardButton(
            "❌ Reject",
            callback_data=f'reject_file_{approval_id}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📥 Download File",
            callback_data=f'download_approval_{approval_id}'
        ),
        types.InlineKeyboardButton(
            "👤 View User",
            callback_data=f'view_user_{user_id}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🔍 Scan Report",
            callback_data=f'scan_report_{approval_id}'
        )
    )

    try:
        bot.send_message(
            OWNER_ID,
            owner_msg,
            parse_mode='Markdown',
            reply_markup=markup
        )
        # Send the actual file to owner for review
        try:
            file_bytes = file_content
            import io
            file_obj = io.BytesIO(file_bytes)
            file_obj.name = file_name
            bot.send_document(
                OWNER_ID,
                file_obj,
                caption=f"📄 File for review: `{file_name}`\n"
                        f"ID: `{approval_id}`",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send file to owner: {e}")

        logger.info(
            f"Approval request sent to owner for "
            f"'{file_name}' from user {user_id}"
        )
    except Exception as e:
        logger.error(f"Failed to send approval request: {e}")
        return None

    # Notify user their file is pending
    pending_msg = (
        f"🔍 *File Under Review*\n"
        f"{DIVIDER}\n"
        f"Your file `{file_name}` has been flagged\n"
        f"for security review by the owner.\n\n"
        f"{severity_icon} *Reason:* {reason}\n\n"
        f"⏳ *Status:* Pending approval\n"
        f"🆔 *Review ID:* `{approval_id}`\n"
        f"{THIN_DIVIDER}\n"
        f"_You will be notified once reviewed._"
    )
    try:
        bot.reply_to(
            message,
            pending_msg,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to notify user of pending: {e}")

    return approval_id


def handle_approve_file_callback(call):
    """Handle owner approving a flagged file"""
    approval_id = call.data.replace('approve_file_', '')

    if approval_id not in pending_approvals:
        bot.answer_callback_query(
            call.id,
            "⚠️ Approval request expired or not found.",
            show_alert=True
        )
        return

    approval = pending_approvals[approval_id]
    user_id = approval['user_id']
    file_name = approval['file_name']
    file_type = approval['file_type']
    file_path = approval['file_path']
    user_folder = approval['user_folder']
    message_obj = approval['message_obj']
    file_content = approval['file_content']

    bot.answer_callback_query(call.id, "✅ Approving file...")

    # Save file to disk
    try:
        os.makedirs(user_folder, exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        bot.send_message(
            OWNER_ID,
            f"❌ Failed to save approved file: {e}"
        )
        return

    # Log audit
    log_audit(
        OWNER_ID, 'approve_file',
        f"Approved '{file_name}' for user {user_id}",
        target_id=user_id
    )

    # Update owner message
    try:
        bot.edit_message_text(
            f"✅ *File Approved*\n"
            f"{DIVIDER}\n"
            f"📄 `{file_name}` approved for user `{user_id}`\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
    except Exception:
        pass

    # Notify user
    try:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "📂 View My Files",
            callback_data='check_files'
        ))
        bot.send_message(
            user_id,
            f"✅ *File Approved!*\n"
            f"{DIVIDER}\n"
            f"Your file `{file_name}` has been\n"
            f"approved by the owner and is now running!\n"
            f"{THIN_DIVIDER}\n"
            f"_Check your files to manage it._",
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Failed to notify user of approval: {e}")

    # Start the script
    save_user_file(user_id, file_name, file_type,
                   len(file_content))

    class ApprovalMessage:
        """Fake message for script runner"""
        class chat:
            id = user_id
        class from_user:
            id = user_id

    fake_msg = ApprovalMessage()
    fake_msg.chat.id = user_id

    if file_type == 'py':
        threading.Thread(
            target=run_script,
            args=(file_path, user_id, user_folder,
                  file_name, message_obj),
            daemon=True
        ).start()
    elif file_type == 'js':
        threading.Thread(
            target=run_js_script,
            args=(file_path, user_id, user_folder,
                  file_name, message_obj),
            daemon=True
        ).start()

    # Clean up
    del pending_approvals[approval_id]


def handle_reject_file_callback(call):
    """Handle owner rejecting a flagged file"""
    approval_id = call.data.replace('reject_file_', '')

    if approval_id not in pending_approvals:
        bot.answer_callback_query(
            call.id,
            "⚠️ Approval request expired or not found.",
            show_alert=True
        )
        return

    approval = pending_approvals[approval_id]
    user_id = approval['user_id']
    file_name = approval['file_name']
    reason = approval['reason']

    bot.answer_callback_query(call.id, "❌ Rejecting file...")

    # Ask owner for reject reason
    msg = bot.send_message(
        OWNER_ID,
        f"📝 Enter rejection reason for `{file_name}`\n"
        f"_(or send 'skip' for default reason)_",
        parse_mode='Markdown'
    )

    def process_reject_reason(reason_msg):
        reject_reason = reason_msg.text
        if reject_reason.lower() == 'skip':
            reject_reason = reason

        # Log audit
        log_audit(
            OWNER_ID, 'reject_file',
            f"Rejected '{file_name}' for user {user_id}: "
            f"{reject_reason}",
            target_id=user_id
        )

        # Update owner message
        try:
            bot.edit_message_text(
                f"❌ *File Rejected*\n"
                f"{DIVIDER}\n"
                f"📄 `{file_name}` rejected for user `{user_id}`\n"
                f"📋 Reason: {reject_reason}\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
        except Exception:
            pass

        # Notify user
        try:
            bot.send_message(
                user_id,
                f"❌ *File Rejected*\n"
                f"{DIVIDER}\n"
                f"Your file `{file_name}` was rejected\n"
                f"by the owner.\n\n"
                f"📋 *Reason:* {reject_reason}\n"
                f"{THIN_DIVIDER}\n"
                f"_Contact owner for more info._",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify user of rejection: {e}")

        # Clean up file if saved
        if os.path.exists(approval.get('file_path', '')):
            try:
                os.remove(approval['file_path'])
            except Exception:
                pass

        # Clean up approval
        if approval_id in pending_approvals:
            del pending_approvals[approval_id]

    bot.register_next_step_handler(msg, process_reject_reason)


def handle_scan_report_callback(call):
    """Show detailed scan report to owner"""
    approval_id = call.data.replace('scan_report_', '')

    if approval_id not in pending_approvals:
        bot.answer_callback_query(
            call.id,
            "⚠️ Report not found.",
            show_alert=True
        )
        return

    approval = pending_approvals[approval_id]
    file_content = approval['file_content']
    file_name = approval['file_name']

    bot.answer_callback_query(call.id)

    # Run full scan
    file_ext = os.path.splitext(file_name)[1].lower()
    is_susp, reason, severity = is_suspicious_file(
        file_content, file_name, file_ext
    )
    detected_type = get_file_type_from_content(file_content)
    entropy = calculate_entropy(file_content[:4096])
    md5, sha256 = check_file_hash(file_content)

    report = (
        f"🔍 *Detailed Scan Report*\n"
        f"{DIVIDER}\n"
        f"📄 *File:* `{file_name}`\n"
        f"📦 *Size:* {format_size(len(file_content))}\n"
        f"🏷️ *Detected Type:* `{detected_type}`\n\n"
        f"🔢 *Entropy:* `{entropy:.4f}` "
        f"{'(HIGH ⚠️)' if entropy > 7.0 else '(Normal ✅)'}\n\n"
        f"🔑 *MD5:* `{md5}`\n"
        f"🔒 *SHA256:*\n`{sha256}`\n\n"
        f"{'🚨' if is_susp else '✅'} *Suspicious:* "
        f"{'Yes' if is_susp else 'No'}\n"
        f"📋 *Reason:* {reason}\n"
        f"⚡ *Severity:* `{severity.upper()}`"
    )

    bot.send_message(
        OWNER_ID,
        report,
        parse_mode='Markdown'
    )


def handle_download_approval_callback(call):
    """Send the pending file to owner for download"""
    approval_id = call.data.replace('download_approval_', '')

    if approval_id not in pending_approvals:
        bot.answer_callback_query(
            call.id,
            "⚠️ File not found.",
            show_alert=True
        )
        return

    approval = pending_approvals[approval_id]
    bot.answer_callback_query(call.id, "📥 Sending file...")

    try:
        import io
        file_obj = io.BytesIO(approval['file_content'])
        file_obj.name = approval['file_name']
        bot.send_document(
            OWNER_ID,
            file_obj,
            caption=f"📄 `{approval['file_name']}`\n"
                    f"User: `{approval['user_id']}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(OWNER_ID, f"❌ Error sending file: {e}")


# ============================================================
# PACKAGE INSTALLATION SYSTEM
# ============================================================

def create_package_install_menu(user_id, script_name=None):
    """Create beautiful package installation menu"""
    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.row(
        types.InlineKeyboardButton(
            "🐍 Install Python Package",
            callback_data=f'pkg_install_py_{user_id}'
        ),
        types.InlineKeyboardButton(
            "🟠 Install Node Package",
            callback_data=f'pkg_install_npm_{user_id}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📋 Installed Packages",
            callback_data=f'pkg_list_{user_id}'
        ),
        types.InlineKeyboardButton(
            "🔄 Update Package",
            callback_data=f'pkg_update_{user_id}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📦 Install from requirements.txt",
            callback_data=f'pkg_req_{user_id}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🗑️ Uninstall Package",
            callback_data=f'pkg_uninstall_{user_id}'
        ),
        types.InlineKeyboardButton(
            "🔍 Search Package",
            callback_data=f'pkg_search_{user_id}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='back_to_main'
        )
    )
    return markup


def show_package_manager(message_or_call):
    """Show the package manager panel"""
    if isinstance(message_or_call, types.Message):
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.chat.id
        send_func = lambda t, **kw: bot.send_message(chat_id, t, **kw)
    else:
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        send_func = lambda t, **kw: bot.send_message(chat_id, t, **kw)

    # Get popular packages list
    popular_py = [
        "requests", "flask", "django",
        "numpy", "pandas", "pillow",
        "aiohttp", "fastapi", "sqlalchemy"
    ]
    popular_node = [
        "express", "axios", "lodash",
        "moment", "mongoose", "dotenv"
    ]

    msg = (
        f"📦 *Package Manager*\n"
        f"{DIVIDER}\n"
        f"Install, update or remove packages\n"
        f"for your scripts.\n\n"
        f"🐍 *Popular Python:*\n"
        f"`{' | '.join(popular_py[:5])}`\n\n"
        f"🟠 *Popular Node:*\n"
        f"`{' | '.join(popular_node[:5])}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select an action below:_"
    )

    send_func(
        msg,
        parse_mode='Markdown',
        reply_markup=create_package_install_menu(user_id)
    )


def install_python_package_prompt(call):
    """Prompt user to enter Python package name"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    msg = bot.send_message(
        call.message.chat.id,
        f"🐍 *Install Python Package*\n"
        f"{DIVIDER}\n"
        f"Enter the package name to install:\n\n"
        f"💡 *Examples:*\n"
        f"`requests` `flask` `numpy`\n"
        f"`pillow` `pandas` `aiohttp`\n\n"
        f"_Or send multiple separated by spaces:_\n"
        f"`requests flask numpy`\n"
        f"{THIN_DIVIDER}\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_python_install(m, user_id)
    )


def process_python_install(message, requesting_user_id):
    """Process Python package installation"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Installation cancelled.")
        return

    packages = message.text.strip().split()
    if not packages:
        bot.reply_to(message, "⚠️ No package name provided.")
        return

    # Security check - validate package names
    invalid = []
    for pkg in packages:
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', pkg):
            invalid.append(pkg)

    if invalid:
        bot.reply_to(
            message,
            f"⚠️ Invalid package name(s): "
            f"`{'`, `'.join(invalid)}`",
            parse_mode='Markdown'
        )
        return

    chat_id = message.chat.id

    def do_install():
        for pkg in packages:
            # Show installing message
            wait_msg = bot.send_message(
                chat_id,
                f"⏳ *Installing* `{pkg}`...\n"
                f"_This may take a moment._",
                parse_mode='Markdown'
            )
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install',
                     '--upgrade', pkg],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    encoding='utf-8',
                    errors='ignore'
                )

                if result.returncode == 0:
                    # Get installed version
                    ver_result = subprocess.run(
                        [sys.executable, '-m', 'pip', 'show', pkg],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='ignore'
                    )
                    version = "Unknown"
                    for line in ver_result.stdout.split('\n'):
                        if line.startswith('Version:'):
                            version = line.split(':', 1)[1].strip()
                            break

                    success_msg = (
                        f"✅ *Package Installed!*\n"
                        f"{DIVIDER}\n"
                        f"📦 *Package:* `{pkg}`\n"
                        f"🔖 *Version:* `{version}`\n"
                        f"🐍 *Python:* `{sys.version.split()[0]}`\n"
                        f"{THIN_DIVIDER}\n"
                        f"_Package ready to use in your scripts._"
                    )

                    try:
                        bot.edit_message_text(
                            success_msg,
                            chat_id,
                            wait_msg.message_id,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        bot.send_message(
                            chat_id,
                            success_msg,
                            parse_mode='Markdown'
                        )

                    log_audit(
                        requesting_user_id,
                        'install_package',
                        f"Installed Python package: {pkg} v{version}"
                    )

                else:
                    error_output = (result.stderr or result.stdout)[:800]
                    error_msg = (
                        f"❌ *Installation Failed*\n"
                        f"{DIVIDER}\n"
                        f"📦 *Package:* `{pkg}`\n\n"
                        f"📋 *Error:*\n"
                        f"```\n{error_output}\n```"
                    )
                    try:
                        bot.edit_message_text(
                            error_msg,
                            chat_id,
                            wait_msg.message_id,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        bot.send_message(
                            chat_id,
                            error_msg,
                            parse_mode='Markdown'
                        )

            except subprocess.TimeoutExpired:
                bot.edit_message_text(
                    f"⏰ *Installation Timeout*\n"
                    f"Package `{pkg}` took too long to install.",
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
            except Exception as e:
                bot.send_message(
                    chat_id,
                    f"❌ Error installing `{pkg}`: {e}",
                    parse_mode='Markdown'
                )

    threading.Thread(target=do_install, daemon=True).start()


def install_npm_package_prompt(call):
    """Prompt user to enter npm package name"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    msg = bot.send_message(
        call.message.chat.id,
        f"🟠 *Install Node.js Package*\n"
        f"{DIVIDER}\n"
        f"Enter the npm package name to install:\n\n"
        f"💡 *Examples:*\n"
        f"`express` `axios` `lodash`\n"
        f"`moment` `mongoose` `dotenv`\n\n"
        f"_Or send multiple separated by spaces:_\n"
        f"`express axios mongoose`\n"
        f"{THIN_DIVIDER}\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_npm_install(m, user_id)
    )


def process_npm_install(message, requesting_user_id):
    """Process npm package installation"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Installation cancelled.")
        return

    packages = message.text.strip().split()
    if not packages:
        bot.reply_to(message, "⚠️ No package name provided.")
        return

    # Validate package names
    invalid = []
    for pkg in packages:
        if not re.match(r'^[@a-zA-Z0-9_\-\.\/]+$', pkg):
            invalid.append(pkg)

    if invalid:
        bot.reply_to(
            message,
            f"⚠️ Invalid package name(s): "
            f"`{'`, `'.join(invalid)}`",
            parse_mode='Markdown'
        )
        return

    user_folder = get_user_folder(requesting_user_id)
    chat_id = message.chat.id

    def do_npm_install():
        for pkg in packages:
            wait_msg = bot.send_message(
                chat_id,
                f"⏳ *Installing* `{pkg}` via npm...\n"
                f"_This may take a moment._",
                parse_mode='Markdown'
            )
            try:
                result = subprocess.run(
                    ['npm', 'install', pkg],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=user_folder,
                    encoding='utf-8',
                    errors='ignore'
                )

                if result.returncode == 0:
                    success_msg = (
                        f"✅ *Node Package Installed!*\n"
                        f"{DIVIDER}\n"
                        f"📦 *Package:* `{pkg}`\n"
                        f"📁 *Location:* User folder\n"
                        f"🟠 *npm* installation complete\n"
                        f"{THIN_DIVIDER}\n"
                        f"_Package ready to use in your JS scripts._"
                    )
                    try:
                        bot.edit_message_text(
                            success_msg,
                            chat_id,
                            wait_msg.message_id,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        bot.send_message(
                            chat_id,
                            success_msg,
                            parse_mode='Markdown'
                        )

                    log_audit(
                        requesting_user_id,
                        'install_npm_package',
                        f"Installed npm package: {pkg}"
                    )

                else:
                    error_output = (result.stderr or result.stdout)[:800]
                    error_msg = (
                        f"❌ *NPM Installation Failed*\n"
                        f"{DIVIDER}\n"
                        f"📦 *Package:* `{pkg}`\n\n"
                        f"📋 *Error:*\n"
                        f"```\n{error_output}\n```"
                    )
                    try:
                        bot.edit_message_text(
                            error_msg,
                            chat_id,
                            wait_msg.message_id,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        bot.send_message(
                            chat_id,
                            error_msg,
                            parse_mode='Markdown'
                        )

            except FileNotFoundError:
                bot.edit_message_text(
                    f"❌ *npm Not Found*\n"
                    f"Node.js/npm is not installed on the server.",
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
                break
            except subprocess.TimeoutExpired:
                bot.edit_message_text(
                    f"⏰ *Installation Timeout*\n"
                    f"Package `{pkg}` took too long.",
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
            except Exception as e:
                bot.send_message(
                    chat_id,
                    f"❌ Error installing `{pkg}`: {e}",
                    parse_mode='Markdown'
                )

    threading.Thread(target=do_npm_install, daemon=True).start()


def list_installed_packages(call):
    """Show list of installed Python packages"""
    bot.answer_callback_query(call.id, "📋 Loading packages...")
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    def do_list():
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list',
                 '--format=columns'],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='ignore'
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                # Skip header lines
                packages = lines[2:] if len(lines) > 2 else []
                total = len(packages)

                # Format nicely - show first 30
                pkg_list = '\n'.join(packages[:30])
                if total > 30:
                    pkg_list += f"\n... and {total - 30} more"

                msg = (
                    f"📋 *Installed Python Packages*\n"
                    f"{DIVIDER}\n"
                    f"📦 *Total:* {total} packages\n\n"
                    f"```\n{pkg_list}\n```"
                )

                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    f"{ICON_BACK} Back to Package Manager",
                    callback_data=f'pkg_manager_{user_id}'
                ))

                bot.send_message(
                    chat_id,
                    msg,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
            else:
                bot.send_message(
                    chat_id,
                    f"❌ Failed to list packages:\n"
                    f"```\n{result.stderr[:500]}\n```",
                    parse_mode='Markdown'
                )
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_list, daemon=True).start()


def uninstall_package_prompt(call):
    """Prompt user to enter package to uninstall"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    msg = bot.send_message(
        call.message.chat.id,
        f"🗑️ *Uninstall Python Package*\n"
        f"{DIVIDER}\n"
        f"Enter the package name to uninstall:\n\n"
        f"⚠️ _Be careful - this affects all scripts!_\n"
        f"{THIN_DIVIDER}\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_uninstall(m, user_id)
    )


def process_uninstall(message, requesting_user_id):
    """Process package uninstallation"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Uninstall cancelled.")
        return

    # Owner only for uninstall
    if message.from_user.id not in admin_ids:
        bot.reply_to(
            message,
            f"🛡️ *Admin Required*\n"
            f"Only admins can uninstall packages.",
            parse_mode='Markdown'
        )
        return

    pkg = message.text.strip()
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', pkg):
        bot.reply_to(message, "⚠️ Invalid package name.")
        return

    chat_id = message.chat.id

    def do_uninstall():
        wait_msg = bot.send_message(
            chat_id,
            f"⏳ Uninstalling `{pkg}`...",
            parse_mode='Markdown'
        )
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'uninstall',
                 pkg, '-y'],
                capture_output=True,
                text=True,
                timeout=60,
                encoding='utf-8',
                errors='ignore'
            )

            if result.returncode == 0:
                bot.edit_message_text(
                    f"✅ *Package Uninstalled*\n"
                    f"📦 `{pkg}` has been removed.",
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
                log_audit(
                    requesting_user_id,
                    'uninstall_package',
                    f"Uninstalled package: {pkg}"
                )
            else:
                bot.edit_message_text(
                    f"❌ *Uninstall Failed*\n"
                    f"```\n{(result.stderr or result.stdout)[:500]}\n```",
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
        except Exception as e:
            bot.edit_message_text(
                f"❌ Error: {e}",
                chat_id,
                wait_msg.message_id
            )

    threading.Thread(target=do_uninstall, daemon=True).start()


def search_package_prompt(call):
    """Prompt user to search for a package"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"🔍 *Search Package*\n"
        f"{DIVIDER}\n"
        f"Enter package name to search on PyPI:\n"
        f"{THIN_DIVIDER}\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_package_search(m)
    )


def process_package_search(message):
    """Search for package on PyPI"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Search cancelled.")
        return

    pkg_name = message.text.strip()
    chat_id = message.chat.id

    def do_search():
        wait_msg = bot.send_message(
            chat_id,
            f"🔍 Searching for `{pkg_name}`...",
            parse_mode='Markdown'
        )
        try:
            response = requests.get(
                f"https://pypi.org/pypi/{pkg_name}/json",
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                info = data.get('info', {})

                name = info.get('name', pkg_name)
                version = info.get('version', 'Unknown')
                summary = info.get('summary', 'No description')[:200]
                author = info.get('author', 'Unknown')
                home_page = info.get('home_page', '')
                license_info = info.get('license', 'Unknown')
                requires_py = info.get('requires_python', 'Any')

                result_msg = (
                    f"📦 *Package Found on PyPI*\n"
                    f"{DIVIDER}\n"
                    f"🏷️ *Name:* `{name}`\n"
                    f"🔖 *Version:* `{version}`\n"
                    f"👤 *Author:* {author}\n"
                    f"📄 *License:* {license_info}\n"
                    f"🐍 *Requires Python:* {requires_py}\n\n"
                    f"📝 *Description:*\n{summary}\n"
                )

                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton(
                        f"🐍 Install {name}",
                        callback_data=f'quick_install_{name}'
                    )
                )
                if home_page:
                    markup.add(types.InlineKeyboardButton(
                        "🌐 Homepage",
                        url=home_page
                    ))

                try:
                    bot.edit_message_text(
                        result_msg,
                        chat_id,
                        wait_msg.message_id,
                        parse_mode='Markdown',
                        reply_markup=markup
                    )
                except Exception:
                    bot.send_message(
                        chat_id,
                        result_msg,
                        parse_mode='Markdown',
                        reply_markup=markup
                    )
            else:
                bot.edit_message_text(
                    f"❌ *Package Not Found*\n"
                    f"No package named `{pkg_name}` on PyPI.",
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
        except requests.Timeout:
            bot.edit_message_text(
                "⏰ Search timed out. Try again.",
                chat_id,
                wait_msg.message_id
            )
        except Exception as e:
            bot.edit_message_text(
                f"❌ Search error: {e}",
                chat_id,
                wait_msg.message_id
            )

    threading.Thread(target=do_search, daemon=True).start()


def quick_install_package(call):
    """Quick install from search result"""
    pkg_name = call.data.replace('quick_install_', '')
    bot.answer_callback_query(call.id, f"⏳ Installing {pkg_name}...")
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    def do_quick_install():
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', pkg_name],
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode == 0:
                bot.send_message(
                    chat_id,
                    f"✅ `{pkg_name}` installed successfully!",
                    parse_mode='Markdown'
                )
            else:
                bot.send_message(
                    chat_id,
                    f"❌ Failed to install `{pkg_name}`.\n"
                    f"```\n{(result.stderr or result.stdout)[:500]}\n```",
                    parse_mode='Markdown'
                )
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_quick_install, daemon=True).start()


def update_package_prompt(call):
    """Prompt to update a package"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"🔄 *Update Package*\n"
        f"{DIVIDER}\n"
        f"Enter package name to update\n"
        f"_(or 'all' to update all packages)_:\n"
        f"{THIN_DIVIDER}\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_package_update(m)
    )


def process_package_update(message):
    """Process package update"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Update cancelled.")
        return

    pkg = message.text.strip()
    chat_id = message.chat.id

    # Only owner/admin can update all
    if pkg.lower() == 'all' and message.from_user.id not in admin_ids:
        bot.reply_to(
            message,
            "🛡️ Only admins can update all packages.",
            parse_mode='Markdown'
        )
        return

    def do_update():
        if pkg.lower() == 'all':
            wait_msg = bot.send_message(
                chat_id,
                "⏳ *Updating all packages...*\n"
                "_This may take several minutes._",
                parse_mode='Markdown'
            )
            try:
                # Get list of outdated packages
                list_result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'list',
                     '--outdated', '--format=columns'],
                    capture_output=True, text=True,
                    timeout=60, encoding='utf-8'
                )
                lines = list_result.stdout.strip().split('\n')[2:]
                pkg_names = [l.split()[0] for l in lines if l.strip()]

                if not pkg_names:
                    bot.edit_message_text(
                        "✅ *All packages are up to date!*",
                        chat_id, wait_msg.message_id,
                        parse_mode='Markdown'
                    )
                    return

                updated = []
                failed = []
                for p in pkg_names:
                    res = subprocess.run(
                        [sys.executable, '-m', 'pip',
                         'install', '--upgrade', p],
                        capture_output=True, text=True,
                        timeout=60, encoding='utf-8'
                    )
                    if res.returncode == 0:
                        updated.append(p)
                    else:
                        failed.append(p)

                result_text = (
                    f"✅ *Update Complete*\n"
                    f"{DIVIDER}\n"
                    f"✅ Updated: {len(updated)}\n"
                    f"❌ Failed: {len(failed)}\n"
                )
                if updated:
                    result_text += (
                        f"\n*Updated:*\n"
                        f"`{'`, `'.join(updated[:10])}`"
                    )
                bot.edit_message_text(
                    result_text,
                    chat_id, wait_msg.message_id,
                    parse_mode='Markdown'
                )
            except Exception as e:
                bot.edit_message_text(
                    f"❌ Update failed: {e}",
                    chat_id, wait_msg.message_id
                )
        else:
            wait_msg = bot.send_message(
                chat_id,
                f"⏳ Updating `{pkg}`...",
                parse_mode='Markdown'
            )
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install',
                     '--upgrade', pkg],
                    capture_output=True, text=True,
                    timeout=120, encoding='utf-8'
                )
                if result.returncode == 0:
                    bot.edit_message_text(
                        f"✅ `{pkg}` updated successfully!",
                        chat_id, wait_msg.message_id,
                        parse_mode='Markdown'
                    )
                else:
                    bot.edit_message_text(
                        f"❌ Update failed:\n"
                        f"```\n{(result.stderr or result.stdout)[:500]}\n```",
                        chat_id, wait_msg.message_id,
                        parse_mode='Markdown'
                    )
            except Exception as e:
                bot.edit_message_text(
                    f"❌ Error: {e}",
                    chat_id, wait_msg.message_id
                )

    threading.Thread(target=do_update, daemon=True).start()


def install_from_requirements(call):
    """Install from requirements.txt"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    user_folder = get_user_folder(user_id)
    req_path = os.path.join(user_folder, 'requirements.txt')
    chat_id = call.message.chat.id

    if not os.path.exists(req_path):
        bot.send_message(
            chat_id,
            f"⚠️ *No requirements.txt Found*\n"
            f"Upload a `requirements.txt` file first.",
            parse_mode='Markdown'
        )
        return

    def do_req_install():
        wait_msg = bot.send_message(
            chat_id,
            f"⏳ *Installing from requirements.txt*...\n"
            f"_Reading packages..._",
            parse_mode='Markdown'
        )
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-r', req_path],
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                errors='ignore'
            )

            if result.returncode == 0:
                # Count packages
                with open(req_path, 'r') as f:
                    pkg_count = len([
                        l for l in f.readlines()
                        if l.strip() and not l.startswith('#')
                    ])

                bot.edit_message_text(
                    f"✅ *Requirements Installed!*\n"
                    f"{DIVIDER}\n"
                    f"📦 *Packages:* {pkg_count}\n"
                    f"📄 *From:* requirements.txt\n"
                    f"{THIN_DIVIDER}\n"
                    f"_All packages ready to use._",
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
            else:
                error = (result.stderr or result.stdout)[:800]
                bot.edit_message_text(
                    f"❌ *Installation Failed*\n"
                    f"```\n{error}\n```",
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
        except Exception as e:
            bot.edit_message_text(
                f"❌ Error: {e}",
                chat_id,
                wait_msg.message_id
            )

    threading.Thread(target=do_req_install, daemon=True).start()


# ============================================================
# AUTO PACKAGE INSTALLATION
# ============================================================

def attempt_install_pip(module_name, message):
    """Auto-install missing Python package"""
    package_name = TELEGRAM_MODULES.get(
        module_name.lower(), module_name
    )
    if package_name is None:
        logger.info(f"Module '{module_name}' is core. Skipping.")
        return False

    try:
        wait_msg = bot.reply_to(
            message,
            f"🐍 *Auto-Installing Package*\n"
            f"{DIVIDER}\n"
            f"📦 Missing: `{module_name}`\n"
            f"⏳ Installing `{package_name}`...",
            parse_mode='Markdown'
        )

        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', package_name],
            capture_output=True,
            text=True,
            timeout=120,
            encoding='utf-8',
            errors='ignore'
        )

        if result.returncode == 0:
            try:
                bot.edit_message_text(
                    f"✅ *Auto-Install Success!*\n"
                    f"📦 `{package_name}` installed.",
                    message.chat.id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return True
        else:
            error = (result.stderr or result.stdout)[:500]
            try:
                bot.edit_message_text(
                    f"❌ *Auto-Install Failed*\n"
                    f"📦 `{package_name}`\n"
                    f"```\n{error}\n```",
                    message.chat.id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return False

    except Exception as e:
        logger.error(f"Auto-install error for {package_name}: {e}")
        return False


def attempt_install_npm(module_name, user_folder, message):
    """Auto-install missing npm package"""
    try:
        wait_msg = bot.reply_to(
            message,
            f"🟠 *Auto-Installing Node Package*\n"
            f"{DIVIDER}\n"
            f"📦 Missing: `{module_name}`\n"
            f"⏳ Running npm install...",
            parse_mode='Markdown'
        )

        result = subprocess.run(
            ['npm', 'install', module_name],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=user_folder,
            encoding='utf-8',
            errors='ignore'
        )

        if result.returncode == 0:
            try:
                bot.edit_message_text(
                    f"✅ *NPM Auto-Install Success!*\n"
                    f"📦 `{module_name}` installed.",
                    message.chat.id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return True
        else:
            error = (result.stderr or result.stdout)[:500]
            try:
                bot.edit_message_text(
                    f"❌ *NPM Auto-Install Failed*\n"
                    f"```\n{error}\n```",
                    message.chat.id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return False

    except FileNotFoundError:
        bot.reply_to(
            message,
            f"❌ *npm Not Found*\n"
            f"Node.js is not installed on the server.",
            parse_mode='Markdown'
        )
        return False
    except Exception as e:
        logger.error(f"NPM auto-install error: {e}")
        return False


# ============================================================
# SCRIPT RUNNER - PYTHON
# ============================================================

def run_script(script_path, script_owner_id, user_folder,
               file_name, message_obj_for_reply, attempt=1):
    """
    Run Python script with full monitoring.
    Handles auto-install of missing packages.
    """
    max_attempts = 2
    if attempt > max_attempts:
        try:
            bot.reply_to(
                message_obj_for_reply,
                f"❌ *Script Failed to Start*\n"
                f"{DIVIDER}\n"
                f"📜 `{file_name}` failed after "
                f"{max_attempts} attempts.\n"
                f"_Check script for errors._",
                parse_mode='Markdown'
            )
        except Exception:
            pass
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(
        f"Attempt {attempt} to run Python: "
        f"{script_path} (Key: {script_key})"
    )

    try:
        # Check script exists
        if not os.path.exists(script_path):
            bot.reply_to(
                message_obj_for_reply,
                f"❌ *Script Not Found*\n"
                f"📜 `{file_name}` is missing!\n"
                f"Please re-upload the file.",
                parse_mode='Markdown'
            )
            remove_user_file_db(script_owner_id, file_name)
            return

        # --- Pre-check for missing modules (attempt 1 only) ---
        if attempt == 1:
            check_proc = None
            try:
                check_proc = subprocess.Popen(
                    [sys.executable, script_path],
                    cwd=user_folder,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore'
                )
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode

                if return_code != 0 and stderr:
                    # Check for missing module
                    match = re.search(
                        r"ModuleNotFoundError: No module named '(.+?)'",
                        stderr
                    )
                    if match:
                        module_name = match.group(1).strip().strip("'\"")
                        logger.info(f"Missing module: {module_name}")

                        if attempt_install_pip(
                            module_name,
                            message_obj_for_reply
                        ):
                            bot.reply_to(
                                message_obj_for_reply,
                                f"🔄 *Retrying Script*\n"
                                f"Package installed. Starting `{file_name}`...",
                                parse_mode='Markdown'
                            )
                            time.sleep(2)
                            threading.Thread(
                                target=run_script,
                                args=(script_path, script_owner_id,
                                      user_folder, file_name,
                                      message_obj_for_reply, attempt + 1),
                                daemon=True
                            ).start()
                            return
                        else:
                            return
                    else:
                        # Other error in pre-check
                        error_summary = stderr[:600]
                        markup = types.InlineKeyboardMarkup(row_width=2)
                        markup.row(
                            types.InlineKeyboardButton(
                                "🐍 Install Package",
                                callback_data=f'pkg_install_py_{script_owner_id}'
                            ),
                            types.InlineKeyboardButton(
                                "📜 View Error",
                                callback_data=f'logs_{script_owner_id}_{file_name}'
                            )
                        )
                        bot.reply_to(
                            message_obj_for_reply,
                            f"❌ *Script Error Detected*\n"
                            f"{DIVIDER}\n"
                            f"📜 `{file_name}` has an error:\n"
                            f"```\n{error_summary}\n```\n"
                            f"_Fix the script and re-upload._",
                            parse_mode='Markdown',
                            reply_markup=markup
                        )
                        return

            except subprocess.TimeoutExpired:
                logger.info(f"Pre-check timeout for {file_name}. Proceeding.")
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()
            except FileNotFoundError:
                bot.reply_to(
                    message_obj_for_reply,
                    f"❌ Python interpreter not found: `{sys.executable}`",
                    parse_mode='Markdown'
                )
                return
            except Exception as e:
                logger.error(f"Pre-check error for {script_key}: {e}")
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()

        # --- Start long-running process ---
        log_file_path = os.path.join(
            user_folder,
            f"{os.path.splitext(file_name)[0]}.log"
        )

        log_file = None
        process = None

        try:
            log_file = open(
                log_file_path, 'w',
                encoding='utf-8', errors='ignore'
            )
        except Exception as e:
            bot.reply_to(
                message_obj_for_reply,
                f"❌ Cannot create log file: {e}"
            )
            return

        try:
            # Get user env variables
            user_env = os.environ.copy()
            user_env_vars = get_env_variables(script_owner_id, file_name)
            user_env.update(user_env_vars)

            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            process = subprocess.Popen(
                [sys.executable, script_path],
                cwd=user_folder,
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.PIPE,
                env=user_env,
                startupinfo=startupinfo,
                creationflags=creationflags,
                encoding='utf-8',
                errors='ignore'
            )

            logger.info(
                f"✅ Started Python process {process.pid} "
                f"for {script_key}"
            )

            with BOT_SCRIPTS_LOCK:
                bot_scripts[script_key] = {
                    'process': process,
                    'log_file': log_file,
                    'file_name': file_name,
                    'chat_id': message_obj_for_reply.chat.id,
                    'script_owner_id': script_owner_id,
                    'start_time': datetime.now(),
                    'user_folder': user_folder,
                    'type': 'py',
                    'script_key': script_key
                }

            # Update stats
            update_user_profile_stat(
                script_owner_id, 'total_scripts_run', 1
            )
            with MESSAGES_LOCK:
                daily_stats['scripts_started'] += 1

            # Beautiful success message
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "🔴 Stop",
                    callback_data=f'stop_{script_owner_id}_{file_name}'
                ),
                types.InlineKeyboardButton(
                    "📜 Logs",
                    callback_data=f'logs_{script_owner_id}_{file_name}'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "📺 Live Logs",
                    callback_data=f'livelogs_{script_owner_id}_{file_name}'
                ),
                types.InlineKeyboardButton(
                    "📂 My Files",
                    callback_data='check_files'
                )
            )

            bot.reply_to(
                message_obj_for_reply,
                f"✅ *Script Started!*\n"
                f"{DIVIDER}\n"
                f"{make_script_card(file_name, 'py', '🟢 Running', process.pid)}\n"
                f"{THIN_DIVIDER}\n"
                f"_Use buttons below to manage._",
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            if log_file and not log_file.closed:
                log_file.close()
            error_msg = (
                f"❌ *Failed to Start Script*\n"
                f"{DIVIDER}\n"
                f"📜 `{file_name}`\n"
                f"Error: `{str(e)}`"
            )
            bot.reply_to(
                message_obj_for_reply,
                error_msg,
                parse_mode='Markdown'
            )
            if process and process.poll() is None:
                kill_process_tree({
                    'process': process,
                    'log_file': log_file,
                    'script_key': script_key
                })
            with BOT_SCRIPTS_LOCK:
                if script_key in bot_scripts:
                    del bot_scripts[script_key]

    except Exception as e:
        error_msg = (
            f"❌ *Unexpected Error*\n"
            f"Running `{file_name}`: `{str(e)}`"
        )
        logger.error(error_msg, exc_info=True)
        try:
            bot.reply_to(
                message_obj_for_reply,
                error_msg,
                parse_mode='Markdown'
            )
        except Exception:
            pass
        with BOT_SCRIPTS_LOCK:
            if script_key in bot_scripts:
                kill_process_tree(bot_scripts[script_key])
                del bot_scripts[script_key]


# ============================================================
# SCRIPT RUNNER - JAVASCRIPT
# ============================================================

def run_js_script(script_path, script_owner_id, user_folder,
                  file_name, message_obj_for_reply, attempt=1):
    """
    Run JavaScript script with full monitoring.
    Handles auto-install of missing npm packages.
    """
    max_attempts = 2
    if attempt > max_attempts:
        try:
            bot.reply_to(
                message_obj_for_reply,
                f"❌ *Script Failed to Start*\n"
                f"{DIVIDER}\n"
                f"📜 `{file_name}` failed after "
                f"{max_attempts} attempts.",
                parse_mode='Markdown'
            )
        except Exception:
            pass
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(
        f"Attempt {attempt} to run JS: "
        f"{script_path} (Key: {script_key})"
    )

    try:
        if not os.path.exists(script_path):
            bot.reply_to(
                message_obj_for_reply,
                f"❌ *Script Not Found*\n"
                f"📜 `{file_name}` is missing!\n"
                f"Please re-upload the file.",
                parse_mode='Markdown'
            )
            remove_user_file_db(script_owner_id, file_name)
            return

        # --- Pre-check ---
        if attempt == 1:
            check_proc = None
            try:
                check_proc = subprocess.Popen(
                    ['node', script_path],
                    cwd=user_folder,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore'
                )
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode

                if return_code != 0 and stderr:
                    match = re.search(
                        r"Cannot find module '(.+?)'",
                        stderr
                    )
                    if match:
                        module_name = match.group(1).strip().strip("'\"")
                        if (not module_name.startswith('.') and
                                not module_name.startswith('/')):
                            if attempt_install_npm(
                                module_name,
                                user_folder,
                                message_obj_for_reply
                            ):
                                bot.reply_to(
                                    message_obj_for_reply,
                                    f"🔄 *Retrying Script*\n"
                                    f"Package installed. "
                                    f"Starting `{file_name}`...",
                                    parse_mode='Markdown'
                                )
                                time.sleep(2)
                                threading.Thread(
                                    target=run_js_script,
                                    args=(script_path, script_owner_id,
                                          user_folder, file_name,
                                          message_obj_for_reply, attempt + 1),
                                    daemon=True
                                ).start()
                                return
                            else:
                                return
                    else:
                        error_summary = stderr[:600]
                        markup = types.InlineKeyboardMarkup(row_width=2)
                        markup.row(
                            types.InlineKeyboardButton(
                                "🟠 Install npm Package",
                                callback_data=f'pkg_install_npm_{script_owner_id}'
                            ),
                            types.InlineKeyboardButton(
                                "📜 View Error",
                                callback_data=f'logs_{script_owner_id}_{file_name}'
                            )
                        )
                        bot.reply_to(
                            message_obj_for_reply,
                            f"❌ *JS Script Error*\n"
                            f"{DIVIDER}\n"
                            f"📜 `{file_name}`:\n"
                            f"```\n{error_summary}\n```",
                            parse_mode='Markdown',
                            reply_markup=markup
                        )
                        return

            except subprocess.TimeoutExpired:
                logger.info(f"JS pre-check timeout for {file_name}.")
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()
            except FileNotFoundError:
                bot.reply_to(
                    message_obj_for_reply,
                    f"❌ *Node.js Not Found*\n"
                    f"Node.js is not installed on the server.",
                    parse_mode='Markdown'
                )
                return
            except Exception as e:
                logger.error(f"JS pre-check error for {script_key}: {e}")
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()

        # --- Start long-running JS process ---
        log_file_path = os.path.join(
            user_folder,
            f"{os.path.splitext(file_name)[0]}.log"
        )

        log_file = None
        process = None

        try:
            log_file = open(
                log_file_path, 'w',
                encoding='utf-8', errors='ignore'
            )
        except Exception as e:
            bot.reply_to(
                message_obj_for_reply,
                f"❌ Cannot create log file: {e}"
            )
            return

        try:
            user_env = os.environ.copy()
            user_env_vars = get_env_variables(script_owner_id, file_name)
            user_env.update(user_env_vars)

            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            process = subprocess.Popen(
                ['node', script_path],
                cwd=user_folder,
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.PIPE,
                env=user_env,
                startupinfo=startupinfo,
                creationflags=creationflags,
                encoding='utf-8',
                errors='ignore'
            )

            logger.info(
                f"✅ Started JS process {process.pid} "
                f"for {script_key}"
            )

            with BOT_SCRIPTS_LOCK:
                bot_scripts[script_key] = {
                    'process': process,
                    'log_file': log_file,
                    'file_name': file_name,
                    'chat_id': message_obj_for_reply.chat.id,
                    'script_owner_id': script_owner_id,
                    'start_time': datetime.now(),
                    'user_folder': user_folder,
                    'type': 'js',
                    'script_key': script_key
                }

            update_user_profile_stat(
                script_owner_id, 'total_scripts_run', 1
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "🔴 Stop",
                    callback_data=f'stop_{script_owner_id}_{file_name}'
                ),
                types.InlineKeyboardButton(
                    "📜 Logs",
                    callback_data=f'logs_{script_owner_id}_{file_name}'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "📺 Live Logs",
                    callback_data=f'livelogs_{script_owner_id}_{file_name}'
                ),
                types.InlineKeyboardButton(
                    "📂 My Files",
                    callback_data='check_files'
                )
            )

            bot.reply_to(
                message_obj_for_reply,
                f"✅ *Script Started!*\n"
                f"{DIVIDER}\n"
                f"{make_script_card(file_name, 'js', '🟢 Running', process.pid)}\n"
                f"{THIN_DIVIDER}\n"
                f"_Use buttons below to manage._",
                parse_mode='Markdown',
                reply_markup=markup
            )

        except FileNotFoundError:
            if log_file and not log_file.closed:
                log_file.close()
            bot.reply_to(
                message_obj_for_reply,
                f"❌ *Node.js Not Found*\n"
                f"Cannot run JS scripts.",
                parse_mode='Markdown'
            )
        except Exception as e:
            if log_file and not log_file.closed:
                log_file.close()
            bot.reply_to(
                message_obj_for_reply,
                f"❌ *Failed to Start JS Script*\n"
                f"Error: `{str(e)}`",
                parse_mode='Markdown'
            )
            if process and process.poll() is None:
                kill_process_tree({
                    'process': process,
                    'log_file': log_file,
                    'script_key': script_key
                })
            with BOT_SCRIPTS_LOCK:
                if script_key in bot_scripts:
                    del bot_scripts[script_key]

    except Exception as e:
        error_msg = (
            f"❌ *Unexpected Error*\n"
            f"Running `{file_name}`: `{str(e)}`"
        )
        logger.error(error_msg, exc_info=True)
        try:
            bot.reply_to(
                message_obj_for_reply,
                error_msg,
                parse_mode='Markdown'
            )
        except Exception:
            pass


# ============================================================
# FILE HANDLERS
# ============================================================

def handle_file_upload(message, file_content, file_name,
                       file_ext, user_folder):
    """
    Central file handler with security scan.
    Routes to approval or direct run.
    """
    user_id = message.from_user.id
    file_path = os.path.join(user_folder, file_name)
    file_type = file_ext.replace('.', '')

    # --- Security Scan ---
    if user_id != OWNER_ID:
        file_ext_lower = file_ext.lower()
        is_suspicious, reason, severity = is_suspicious_file(
            file_content, file_name, file_ext_lower
        )

        if is_suspicious:
            # Send for owner approval instead of blocking
            logger.warning(
                f"Suspicious file from {user_id}: "
                f"{file_name} - {reason}"
            )
            request_owner_approval(
                file_content, file_name, file_type,
                file_path, user_folder, reason,
                severity, message
            )
            return  # Don't run automatically

    # --- Safe file or Owner upload ---
    # Save to disk
    try:
        with open(file_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Failed to save file: {e}"
        )
        return

    # Check version control
    existing_versions = get_file_versions(user_id, file_name)
    if existing_versions:
        # Archive current version
        current_path = file_path
        if os.path.exists(current_path):
            next_ver = get_next_version_number(user_id, file_name)
            ver_dir = os.path.join(
                VERSIONS_DIR, str(user_id), file_name
            )
            os.makedirs(ver_dir, exist_ok=True)
            ver_path = os.path.join(ver_dir, f"v{next_ver}_{file_name}")
            try:
                shutil.copy2(current_path, ver_path)
                _, sha256 = check_file_hash(file_content)
                save_file_version(
                    user_id, file_name, next_ver,
                    ver_path, len(file_content), sha256
                )
                bot.reply_to(
                    message,
                    f"🔖 *Version {next_ver} Saved*\n"
                    f"Previous version archived.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Version archive error: {e}")
    else:
        # First upload - save as v1
        ver_dir = os.path.join(
            VERSIONS_DIR, str(user_id), file_name
        )
        os.makedirs(ver_dir, exist_ok=True)
        ver_path = os.path.join(ver_dir, f"v1_{file_name}")
        try:
            shutil.copy2(file_path, ver_path)
            _, sha256 = check_file_hash(file_content)
            save_file_version(
                user_id, file_name, 1,
                ver_path, len(file_content), sha256
            )
        except Exception as e:
            logger.error(f"Version save error: {e}")

    # Save to DB and run
    save_user_file(user_id, file_name, file_type, len(file_content))

    if file_type == 'py':
        threading.Thread(
            target=run_script,
            args=(file_path, user_id, user_folder,
                  file_name, message),
            daemon=True
        ).start()
    elif file_type == 'js':
        threading.Thread(
            target=run_js_script,
            args=(file_path, user_id, user_folder,
                  file_name, message),
            daemon=True
        ).start()


def handle_zip_file(downloaded_file_content, file_name_zip, message):
    """Handle ZIP file upload with security and extraction"""
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None

    try:
        temp_dir = tempfile.mkdtemp(
            prefix=f"user_{user_id}_zip_",
            dir=TEMP_DIR
        )

        # Save zip
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as f:
            f.write(downloaded_file_content)

        # Extract
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            if user_id != OWNER_ID:
                for member in zip_ref.infolist():
                    member_lower = member.filename.lower()
                    if any(member_lower.endswith(ext)
                           for ext in EXECUTABLE_EXTENSIONS):
                        is_susp = True
                        reason = f"ZIP contains executable: {member.filename}"
                        severity = "high"
                        request_owner_approval(
                            downloaded_file_content,
                            file_name_zip, 'zip',
                            zip_path, user_folder,
                            reason, severity, message
                        )
                        return

                    # Path traversal check
                    member_path = os.path.abspath(
                        os.path.join(temp_dir, member.filename)
                    )
                    if not member_path.startswith(
                            os.path.abspath(temp_dir)):
                        raise zipfile.BadZipFile(
                            f"Path traversal: {member.filename}"
                        )

            zip_ref.extractall(temp_dir)

        # Find scripts (flatten if needed)
        target_dir = temp_dir
        root_files = os.listdir(target_dir)

        if not any(f.endswith(('.py', '.js')) for f in root_files):
            for root, dirs, files in os.walk(temp_dir):
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith('.') and
                    not d.startswith('__')
                ]
                if any(f.endswith(('.py', '.js')) for f in files):
                    target_dir = root
                    break

        if target_dir != temp_dir:
            for item in os.listdir(target_dir):
                s = os.path.join(target_dir, item)
                d = os.path.join(temp_dir, item)
                if os.path.exists(d):
                    if os.path.isdir(d):
                        shutil.rmtree(d)
                    else:
                        os.remove(d)
                shutil.move(s, d)

        extracted_items = os.listdir(temp_dir)
        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' in extracted_items
        pkg_json = 'package.json' in extracted_items

        # Install requirements
        if req_file:
            req_path = os.path.join(temp_dir, 'requirements.txt')
            bot.reply_to(
                message,
                f"🔄 *Installing Dependencies*\n"
                f"Found requirements.txt...",
                parse_mode='Markdown'
            )
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'pip',
                     'install', '-r', req_path],
                    capture_output=True, text=True,
                    timeout=300, encoding='utf-8'
                )
                if result.returncode == 0:
                    bot.reply_to(
                        message,
                        "✅ Python dependencies installed!",
                        parse_mode='Markdown'
                    )
                else:
                    bot.reply_to(
                        message,
                        f"⚠️ Some dependencies failed:\n"
                        f"```\n{(result.stderr or result.stdout)[:500]}\n```",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Requirements install error: {e}")

        if pkg_json:
            bot.reply_to(
                message,
                f"🔄 *Installing Node Dependencies*...",
                parse_mode='Markdown'
            )
            try:
                result = subprocess.run(
                    ['npm', 'install'],
                    capture_output=True, text=True,
                    timeout=300, cwd=temp_dir, encoding='utf-8'
                )
                if result.returncode == 0:
                    bot.reply_to(
                        message,
                        "✅ Node dependencies installed!",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"NPM install error: {e}")

        # Find main script
        main_script = None
        file_type = None
        for p in ['main.py', 'bot.py', 'app.py']:
            if p in py_files:
                main_script = p
                file_type = 'py'
                break
        if not main_script:
            for p in ['index.js', 'main.js', 'bot.js', 'app.js']:
                if p in js_files:
                    main_script = p
                    file_type = 'js'
                    break
        if not main_script:
            if py_files:
                main_script = py_files[0]
                file_type = 'py'
            elif js_files:
                main_script = js_files[0]
                file_type = 'js'

        if not main_script:
            bot.reply_to(
                message,
                "❌ *No Script Found*\n"
                "No `.py` or `.js` file in archive!",
                parse_mode='Markdown'
            )
            return

        # Move files to user folder
        for item in os.listdir(temp_dir):
            if item == file_name_zip:
                continue
            src = os.path.join(temp_dir, item)
            dst = os.path.join(user_folder, item)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)

        # Run main script
        main_path = os.path.join(user_folder, main_script)
        bot.reply_to(
            message,
            f"✅ *ZIP Extracted!*\n"
            f"{DIVIDER}\n"
            f"📄 Main script: `{main_script}`\n"
            f"⏳ Starting...",
            parse_mode='Markdown'
        )

        save_user_file(user_id, main_script, file_type,
                       os.path.getsize(main_path))

        if file_type == 'py':
            threading.Thread(
                target=run_script,
                args=(main_path, user_id, user_folder,
                      main_script, message),
                daemon=True
            ).start()
        elif file_type == 'js':
            threading.Thread(
                target=run_js_script,
                args=(main_path, user_id, user_folder,
                      main_script, message),
                daemon=True
            ).start()

    except zipfile.BadZipFile as e:
        bot.reply_to(
            message,
            f"❌ *Invalid ZIP File*\n{e}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"ZIP handling error: {e}", exc_info=True)
        bot.reply_to(
            message,
            f"❌ *ZIP Processing Error*\n`{str(e)}`",
            parse_mode='Markdown'
        )
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Temp cleanup error: {e}")


# ============================================================
# END OF CHUNK 4
# ============================================================
# CHUNK 5: Owner Panel Part 1
# ============================================================
# PASTE THIS AFTER CHUNK 4
# ============================================================

# ============================================================
# OWNER PANEL - MAIN MENU
# ============================================================

def show_owner_panel(message_or_call):
    """Show the main owner command center"""
    if isinstance(message_or_call, types.Message):
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.chat.id
        send_func = lambda t, **kw: bot.send_message(chat_id, t, **kw)
    else:
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        send_func = lambda t, **kw: bot.send_message(chat_id, t, **kw)

    if user_id != OWNER_ID:
        send_func(
            f"👑 *Owner Only*\n"
            f"This panel is restricted to the owner.",
            parse_mode='Markdown'
        )
        return

    # Get live stats
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    running = sum(
        1 for k, v in bot_scripts.items()
        if is_bot_running(
            v['script_owner_id'],
            v['file_name']
        )
    )
    uptime = format_uptime(BOT_START_TIME)
    uptime_pct = get_uptime_percentage(24)
    pending = len(pending_approvals)

    panel_msg = (
        f"👑 *OWNER COMMAND CENTER*\n"
        f"{DIVIDER}\n"
        f"🤖 *Bot:* `{bot.get_me().username}`\n"
        f"⏱️ *Uptime:* `{uptime}`\n"
        f"📈 *Uptime %:* `{uptime_pct}%` (24h)\n\n"
        f"{make_status_bar(cpu, ram, disk)}\n\n"
        f"👥 *Users:* `{len(active_users)}`\n"
        f"🟢 *Running:* `{running}` scripts\n"
        f"💳 *Premium:* `{len(user_subscriptions)}`\n"
        f"🚫 *Banned:* `{len(banned_users)}`\n"
        f"⏳ *Pending Approvals:* `{pending}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select a panel to manage:_"
    )

    markup = create_owner_main_markup()
    send_func(panel_msg, parse_mode='Markdown', reply_markup=markup)


def create_owner_main_markup():
    """Create owner panel main keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🤖 Bot Control",
            callback_data='owner_bot_control'
        ),
        types.InlineKeyboardButton(
            "👥 User Management",
            callback_data='owner_user_mgmt'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🛡️ Admin Management",
            callback_data='owner_admin_mgmt'
        ),
        types.InlineKeyboardButton(
            "💻 System Control",
            callback_data='owner_system'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🗄️ Database Control",
            callback_data='owner_database'
        ),
        types.InlineKeyboardButton(
            "⚙️ Bot Config",
            callback_data='owner_config'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📢 Communication",
            callback_data='owner_communication'
        ),
        types.InlineKeyboardButton(
            "🔒 Security Center",
            callback_data='owner_security'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📊 Analytics",
            callback_data='owner_analytics'
        ),
        types.InlineKeyboardButton(
            "📁 File System",
            callback_data='owner_filesystem'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🔧 Script Control",
            callback_data='owner_scripts'
        ),
        types.InlineKeyboardButton(
            "💰 Payment Control",
            callback_data='owner_payment'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🔔 Notifications",
            callback_data='owner_notifications'
        ),
        types.InlineKeyboardButton(
            "📜 Audit & Logs",
            callback_data='owner_audit'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🌐 Health & Status",
            callback_data='owner_health'
        ),
        types.InlineKeyboardButton(
            "⏳ Approvals",
            callback_data='owner_approvals'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🔙 Back to Main Menu",
            callback_data='back_to_main'
        )
    )
    return markup


def owner_back_button(callback_data='owner_panel'):
    """Create owner back button row"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data=callback_data
        ),
        types.InlineKeyboardButton(
            f"{ICON_HOME} Owner Panel",
            callback_data='owner_panel'
        )
    )
    return markup


# ============================================================
# OWNER - BOT CONTROL PANEL
# ============================================================

def show_owner_bot_control(call):
    """Show bot control panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    status = "🟢 Online"
    mode = "🔄 Polling" if not get_config('webhook_mode') else "🌐 Webhook"
    locked = "🔒 Locked" if get_config('bot_locked') else "🔓 Unlocked"
    maintenance = "🔧 ON" if get_config('maintenance_mode') else "✅ OFF"
    uptime = format_uptime(BOT_START_TIME)

    msg = (
        f"🤖 *Bot Control Panel*\n"
        f"{DIVIDER}\n"
        f"📡 *Status:* {status}\n"
        f"🌐 *Mode:* {mode}\n"
        f"🔒 *Lock:* {locked}\n"
        f"🔧 *Maintenance:* {maintenance}\n"
        f"⏱️ *Uptime:* `{uptime}`\n"
        f"🐍 *Python:* `{sys.version.split()[0]}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select an action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🔄 Restart Bot",
            callback_data='owner_restart_bot'
        ),
        types.InlineKeyboardButton(
            "🔃 Update Code",
            callback_data='owner_update_code'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🔒 Toggle Lock",
            callback_data='owner_toggle_lock'
        ),
        types.InlineKeyboardButton(
            "🔧 Toggle Maintenance",
            callback_data='owner_toggle_maintenance'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🌐 Switch Mode",
            callback_data='owner_switch_mode'
        ),
        types.InlineKeyboardButton(
            "🔍 Health Check",
            callback_data='owner_health_check'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🚨 Emergency Stop All",
            callback_data='owner_emergency_stop'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg,
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_restart_bot(call):
    """Handle bot restart"""
    bot.answer_callback_query(call.id)

    # Confirm first
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✅ Yes, Restart",
            callback_data='owner_confirm_restart'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data='owner_bot_control'
        )
    )

    bot.send_message(
        call.message.chat.id,
        f"⚠️ *Confirm Bot Restart*\n"
        f"{DIVIDER}\n"
        f"This will restart the bot process.\n"
        f"All running scripts will continue.\n\n"
        f"Are you sure?",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_confirm_restart(call):
    """Execute bot restart"""
    bot.answer_callback_query(call.id, "🔄 Restarting...")

    log_audit(
        OWNER_ID, 'bot_restart',
        'Owner initiated bot restart',
        severity='warning'
    )

    bot.send_message(
        call.message.chat.id,
        f"🔄 *Bot Restarting...*\n"
        f"{DIVIDER}\n"
        f"The bot will be back in a few seconds.\n"
        f"_Running scripts will not be affected._",
        parse_mode='Markdown'
    )

    def do_restart():
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=do_restart, daemon=True).start()


def handle_owner_toggle_lock(call):
    """Toggle bot lock"""
    bot.answer_callback_query(call.id)
    current = get_config('bot_locked', False)
    new_state = not current
    set_config('bot_locked', new_state)

    state_text = "🔒 Locked" if new_state else "🔓 Unlocked"

    log_audit(
        OWNER_ID, 'toggle_lock',
        f'Bot {state_text}',
        severity='warning'
    )

    bot.send_message(
        call.message.chat.id,
        f"{'🔒' if new_state else '🔓'} *Bot {state_text}*\n"
        f"{DIVIDER}\n"
        f"{'All users are now blocked.' if new_state else 'Users can access the bot again.'}\n"
        f"_Admins and owner are not affected._",
        parse_mode='Markdown'
    )
    show_owner_bot_control(call)


def handle_owner_toggle_maintenance(call):
    """Toggle maintenance mode"""
    bot.answer_callback_query(call.id)
    current = get_config('maintenance_mode', False)
    new_state = not current
    set_config('maintenance_mode', new_state)

    state_text = "ON 🔧" if new_state else "OFF ✅"

    log_audit(
        OWNER_ID, 'toggle_maintenance',
        f'Maintenance mode {state_text}',
        severity='warning'
    )

    bot.send_message(
        call.message.chat.id,
        f"🔧 *Maintenance Mode {state_text}*\n"
        f"{DIVIDER}\n"
        f"{'Bot is now in maintenance mode.' if new_state else 'Maintenance mode disabled.'}\n"
        f"{'Users will see maintenance message.' if new_state else 'Bot is fully operational.'}",
        parse_mode='Markdown'
    )


def handle_owner_emergency_stop(call):
    """Emergency stop all scripts"""
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🚨 CONFIRM STOP ALL",
            callback_data='owner_confirm_emergency_stop'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data='owner_bot_control'
        )
    )

    bot.send_message(
        call.message.chat.id,
        f"🚨 *Emergency Stop All Scripts*\n"
        f"{DIVIDER}\n"
        f"⚠️ This will *immediately stop*\n"
        f"ALL running scripts for ALL users!\n\n"
        f"🟢 Currently running: "
        f"`{len(bot_scripts)}` scripts\n\n"
        f"*This cannot be undone!*",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_confirm_emergency_stop(call):
    """Execute emergency stop"""
    bot.answer_callback_query(call.id, "🚨 Stopping all scripts...")

    stopped = 0
    with BOT_SCRIPTS_LOCK:
        keys = list(bot_scripts.keys())

    for key in keys:
        with BOT_SCRIPTS_LOCK:
            info = bot_scripts.get(key)
        if info:
            try:
                kill_process_tree(info)
                # Notify script owner
                try:
                    bot.send_message(
                        info.get('chat_id', OWNER_ID),
                        f"🚨 *Emergency Stop*\n"
                        f"Your script `{info.get('file_name')}` "
                        f"was stopped by the owner.",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
                stopped += 1
            except Exception as e:
                logger.error(f"Emergency stop error for {key}: {e}")
            finally:
                with BOT_SCRIPTS_LOCK:
                    if key in bot_scripts:
                        del bot_scripts[key]

    log_audit(
        OWNER_ID, 'emergency_stop',
        f'Emergency stopped {stopped} scripts',
        severity='critical'
    )

    bot.send_message(
        call.message.chat.id,
        f"🚨 *Emergency Stop Complete*\n"
        f"{DIVIDER}\n"
        f"⏹️ Stopped: `{stopped}` scripts\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}",
        parse_mode='Markdown'
    )


def handle_owner_health_check(call):
    """Run full system health check"""
    bot.answer_callback_query(call.id, "🔍 Running diagnostics...")
    chat_id = call.message.chat.id

    wait_msg = bot.send_message(
        chat_id,
        f"🔍 *Running Health Check...*\n"
        f"_Please wait..._",
        parse_mode='Markdown'
    )

    def do_health_check():
        results = []

        # Check 1: Telegram API
        try:
            start = time.time()
            me = bot.get_me()
            api_time = round((time.time() - start) * 1000, 2)
            results.append(
                f"✅ Telegram API: `{api_time}ms`"
            )
        except Exception as e:
            results.append(f"❌ Telegram API: `{e}`")

        # Check 2: Database
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            conn.execute('SELECT 1')
            conn.close()
            db_size = os.path.getsize(DATABASE_PATH)
            results.append(
                f"✅ Database: `{format_size(db_size)}`"
            )
        except Exception as e:
            results.append(f"❌ Database: `{e}`")

        # Check 3: File System
        try:
            test_path = os.path.join(TEMP_DIR, 'health_test.tmp')
            with open(test_path, 'w') as f:
                f.write('test')
            os.remove(test_path)
            results.append(f"✅ File System: Writable")
        except Exception as e:
            results.append(f"❌ File System: `{e}`")

        # Check 4: Python
        try:
            result = subprocess.run(
                [sys.executable, '--version'],
                capture_output=True, text=True, timeout=5
            )
            results.append(
                f"✅ Python: `{result.stdout.strip() or result.stderr.strip()}`"
            )
        except Exception as e:
            results.append(f"❌ Python: `{e}`")

        # Check 5: Node.js
        try:
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True, text=True, timeout=5
            )
            results.append(
                f"✅ Node.js: `{result.stdout.strip()}`"
            )
        except FileNotFoundError:
            results.append(f"⚠️ Node.js: Not installed")
        except Exception as e:
            results.append(f"❌ Node.js: `{e}`")

        # Check 6: System Resources
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        results.append(
            f"{'✅' if cpu < 90 else '⚠️'} CPU: `{cpu}%`"
        )
        results.append(
            f"{'✅' if ram.percent < 85 else '⚠️'} RAM: "
            f"`{ram.percent}%` ({format_size(ram.available)} free)"
        )
        results.append(
            f"{'✅' if disk.percent < 90 else '⚠️'} Disk: "
            f"`{disk.percent}%` ({format_size(disk.free)} free)"
        )

        # Check 7: Encryption
        try:
            test_enc = encrypt_value("test_health_check")
            test_dec = decrypt_value(test_enc)
            if test_dec == "test_health_check":
                results.append("✅ Encryption: Working")
            else:
                results.append("❌ Encryption: Mismatch!")
        except Exception as e:
            results.append(f"❌ Encryption: `{e}`")

        # Check 8: Upload directory
        if os.path.exists(UPLOAD_BOTS_DIR):
            dir_size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, dn, fn in os.walk(UPLOAD_BOTS_DIR)
                for f in fn
            )
            results.append(
                f"✅ Upload Dir: `{format_size(dir_size)}`"
            )
        else:
            results.append(f"❌ Upload Dir: Missing!")

        # Build report
        all_ok = all(r.startswith('✅') for r in results)
        status_icon = "✅" if all_ok else "⚠️"

        report = (
            f"{status_icon} *Health Check Report*\n"
            f"{DIVIDER}\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            + "\n".join(results) +
            f"\n{THIN_DIVIDER}\n"
            f"{'_All systems operational_ ✅' if all_ok else '_Some issues detected_ ⚠️'}"
        )

        markup = owner_back_button('owner_bot_control')

        try:
            bot.edit_message_text(
                report,
                chat_id,
                wait_msg.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception:
            bot.send_message(
                chat_id, report,
                parse_mode='Markdown',
                reply_markup=markup
            )

    threading.Thread(target=do_health_check, daemon=True).start()


def handle_owner_switch_mode(call):
    """Switch between polling and webhook mode"""
    bot.answer_callback_query(call.id)
    current_mode = get_config('webhook_mode', False)
    chat_id = call.message.chat.id

    if current_mode:
        # Switch to polling
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "✅ Switch to Polling",
                callback_data='owner_set_polling'
            ),
            types.InlineKeyboardButton(
                "❌ Cancel",
                callback_data='owner_bot_control'
            )
        )
        bot.send_message(
            chat_id,
            f"🔄 *Switch to Polling Mode*\n"
            f"{DIVIDER}\n"
            f"Current: 🌐 Webhook\n"
            f"Switch to: 🔄 Polling\n\n"
            f"_This will remove the webhook and_\n"
            f"_start long polling._",
            parse_mode='Markdown',
            reply_markup=markup
        )
    else:
        # Switch to webhook
        msg = bot.send_message(
            chat_id,
            f"🌐 *Switch to Webhook Mode*\n"
            f"{DIVIDER}\n"
            f"Enter your webhook URL:\n"
            f"_(Must be HTTPS)_\n\n"
            f"Example:\n"
            f"`https://yourserver.com/webhook`\n"
            f"{THIN_DIVIDER}\n"
            f"Send /cancel to abort.",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(
            msg,
            process_webhook_url_input
        )


def process_webhook_url_input(message):
    """Process webhook URL from owner"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Webhook setup cancelled.")
        return

    if message.from_user.id != OWNER_ID:
        return

    webhook_url = message.text.strip()

    if not webhook_url.startswith('https://'):
        bot.reply_to(
            message,
            f"❌ *Invalid URL*\n"
            f"Webhook URL must start with `https://`",
            parse_mode='Markdown'
        )
        return

    chat_id = message.chat.id

    def do_set_webhook():
        wait_msg = bot.send_message(
            chat_id,
            f"⏳ Setting webhook...",
            parse_mode='Markdown'
        )
        try:
            secret = secrets.token_hex(32)
            bot.set_webhook(
                url=f"{webhook_url}/{TOKEN}",
                secret_token=secret
            )
            set_config('webhook_mode', True)
            set_config('webhook_url', webhook_url)
            set_config('webhook_secret', secret)

            log_audit(
                OWNER_ID, 'set_webhook',
                f'Webhook set to {webhook_url}',
                severity='warning'
            )

            bot.edit_message_text(
                f"✅ *Webhook Set!*\n"
                f"{DIVIDER}\n"
                f"🌐 URL: `{webhook_url}`\n"
                f"🔑 Secret: `{secret[:16]}...`\n"
                f"{THIN_DIVIDER}\n"
                f"_Switching to webhook mode._",
                chat_id,
                wait_msg.message_id,
                parse_mode='Markdown'
            )
        except Exception as e:
            bot.edit_message_text(
                f"❌ *Webhook Failed*\n`{e}`",
                chat_id,
                wait_msg.message_id,
                parse_mode='Markdown'
            )

    threading.Thread(target=do_set_webhook, daemon=True).start()


def handle_owner_set_polling(call):
    """Switch to polling mode"""
    bot.answer_callback_query(call.id, "🔄 Switching to polling...")

    try:
        bot.remove_webhook()
        set_config('webhook_mode', False)
        set_config('webhook_url', '')

        log_audit(
            OWNER_ID, 'set_polling',
            'Switched to polling mode',
            severity='warning'
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ *Switched to Polling Mode*\n"
            f"{DIVIDER}\n"
            f"Webhook removed.\n"
            f"_Bot is now using long polling._",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error switching mode: `{e}`",
            parse_mode='Markdown'
        )


def handle_owner_update_code(call):
    """Handle bot code update"""
    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        f"🔃 *Update Bot Code*\n"
        f"{DIVIDER}\n"
        f"Send the new bot `.py` file\n"
        f"to update the bot code.\n\n"
        f"⚠️ *Warning:*\n"
        f"• Current code will be backed up\n"
        f"• Bot will restart after update\n"
        f"• All scripts continue running\n"
        f"{THIN_DIVIDER}\n"
        f"_Send the file or /cancel to abort._",
        parse_mode='Markdown'
    )
    # Note: File will be handled by document handler
    # with special owner update flag


# ============================================================
# OWNER - USER MANAGEMENT
# ============================================================

def show_owner_user_mgmt(call):
    """Show user management panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    total = len(active_users)
    premium = len(user_subscriptions)
    banned_count = len(banned_users)
    warned_count = len(warned_users)
    admins_count = len(admin_ids)

    msg = (
        f"👥 *User Management*\n"
        f"{DIVIDER}\n"
        f"👥 *Total Users:* `{total}`\n"
        f"💳 *Premium:* `{premium}`\n"
        f"🛡️ *Admins:* `{admins_count}`\n"
        f"🚫 *Banned:* `{banned_count}`\n"
        f"⚠️ *Warned:* `{warned_count}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select an action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🔍 Search User",
            callback_data='owner_search_user'
        ),
        types.InlineKeyboardButton(
            "📋 List Users",
            callback_data='owner_list_users'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🚫 Ban User",
            callback_data='owner_ban_user'
        ),
        types.InlineKeyboardButton(
            "✅ Unban User",
            callback_data='owner_unban_user'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "⚠️ Warn User",
            callback_data='owner_warn_user'
        ),
        types.InlineKeyboardButton(
            "💬 Message User",
            callback_data='owner_message_user'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "✏️ Edit User Limit",
            callback_data='owner_edit_user_limit'
        ),
        types.InlineKeyboardButton(
            "🗑️ Delete User",
            callback_data='owner_delete_user'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📊 User Stats",
            callback_data='owner_user_stats'
        ),
        types.InlineKeyboardButton(
            "📤 Export Users",
            callback_data='owner_export_users'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🚫 Banned List",
            callback_data='owner_banned_list'
        ),
        types.InlineKeyboardButton(
            "⚠️ Warned List",
            callback_data='owner_warned_list'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_search_user(call):
    """Search for a user"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"🔍 *Search User*\n"
        f"{DIVIDER}\n"
        f"Enter user ID or @username:\n"
        f"{THIN_DIVIDER}\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        process_user_search
    )


def process_user_search(message):
    """Process user search and show full profile"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Search cancelled.")
        return

    query = message.text.strip()
    chat_id = message.chat.id

    def do_search():
        target_id = None
        target_info = None

        # Search by ID
        try:
            target_id = int(query.replace('@', ''))
        except ValueError:
            # Search by username in DB
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                c = conn.cursor()
                username = query.replace('@', '').lower()
                c.execute(
                    '''SELECT user_id FROM user_profiles
                       WHERE LOWER(username) = ?''',
                    (username,)
                )
                row = c.fetchone()
                conn.close()
                if row:
                    target_id = row[0]
            except Exception as e:
                logger.error(f"User search DB error: {e}")

        if not target_id:
            bot.send_message(
                chat_id,
                f"❌ *User Not Found*\n"
                f"No user found for: `{query}`",
                parse_mode='Markdown'
            )
            return

        show_user_full_profile(chat_id, target_id)

    threading.Thread(target=do_search, daemon=True).start()


def show_user_full_profile(chat_id, target_id):
    """Show complete user profile to owner"""
    try:
        # Get from DB
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT first_name, username, first_seen,
               last_active, total_uploads, total_scripts_run,
               total_run_time_seconds, storage_used_bytes,
               custom_file_limit
               FROM user_profiles WHERE user_id = ?''',
            (target_id,)
        )
        profile = c.fetchone()

        # Get subscription
        c.execute(
            'SELECT plan, expiry FROM subscriptions WHERE user_id = ?',
            (target_id,)
        )
        sub = c.fetchone()

        # Get file count
        c.execute(
            'SELECT COUNT(*) FROM user_files WHERE user_id = ?',
            (target_id,)
        )
        file_count = c.fetchone()[0]

        # Get ban info
        c.execute(
            '''SELECT ban_type, reason, banned_at, expires_at
               FROM bans WHERE user_id = ? AND is_active = 1''',
            (target_id,)
        )
        ban_info = c.fetchone()

        # Get warning count
        c.execute(
            '''SELECT COUNT(*) FROM warnings
               WHERE user_id = ? AND is_active = 1''',
            (target_id,)
        )
        warn_count = c.fetchone()[0]

        conn.close()

        # Status
        status_icon = get_user_status_icon(target_id)
        status_text = get_user_status_text(target_id)

        # Running scripts
        user_running = sum(
            1 for k, v in bot_scripts.items()
            if v.get('script_owner_id') == target_id
            and is_bot_running(target_id, v['file_name'])
        )

        # File limit
        file_limit = get_user_file_limit(target_id)
        limit_str = str(file_limit) if file_limit != float('inf') else "∞"

        # Build profile
        name = profile[0] if profile else "Unknown"
        username = profile[1] if profile else "Unknown"
        first_seen = profile[2][:10] if profile and profile[2] else "Unknown"
        last_active = profile[3][:10] if profile and profile[3] else "Unknown"
        total_uploads = profile[4] if profile else 0
        total_runs = profile[5] if profile else 0
        run_time = profile[6] if profile else 0
        storage = profile[7] if profile else 0
        custom_limit = profile[8] if profile else -1

        # Format run time
        run_hours = run_time // 3600
        run_mins = (run_time % 3600) // 60

        profile_msg = (
            f"👤 *User Full Profile*\n"
            f"{DIVIDER}\n"
            f"📋 *Basic Info*\n"
            f"┌─────────────────────\n"
            f"│ {status_icon} *{name}*\n"
            f"│ 🆔 `{target_id}`\n"
            f"│ ✳️ @{username or 'Not set'}\n"
            f"│ 🔰 {status_text}\n"
            f"│ 📅 Joined: {first_seen}\n"
            f"│ 🕐 Last: {last_active}\n"
            f"└─────────────────────\n\n"
            f"📊 *Usage Stats*\n"
            f"┌─────────────────────\n"
            f"│ 📁 Files: {file_count}/{limit_str}\n"
            f"│ 🟢 Running: {user_running}\n"
            f"│ 📤 Total Uploads: {total_uploads}\n"
            f"│ 🚀 Scripts Run: {total_runs}\n"
            f"│ ⏱️ Run Time: {run_hours}h {run_mins}m\n"
            f"│ 💾 Storage: {format_size(storage)}\n"
        )

        if custom_limit and custom_limit > 0:
            profile_msg += f"│ 🎯 Custom Limit: {custom_limit}\n"

        profile_msg += f"└─────────────────────\n\n"

        # Subscription
        if sub:
            try:
                exp_dt = datetime.fromisoformat(sub[1])
                days_left = (exp_dt - datetime.now()).days
                exp_status = f"✅ Active ({days_left}d left)"
            except Exception:
                exp_status = "❓ Unknown"
            profile_msg += (
                f"💳 *Subscription*\n"
                f"┌─────────────────────\n"
                f"│ 🏷️ Plan: {sub[0].upper()}\n"
                f"│ 📅 Expiry: {sub[1][:10]}\n"
                f"│ 📊 Status: {exp_status}\n"
                f"└─────────────────────\n\n"
            )

        # Ban info
        if ban_info:
            profile_msg += (
                f"🚫 *Ban Info*\n"
                f"┌─────────────────────\n"
                f"│ 🔒 Type: {ban_info[0]}\n"
                f"│ 📋 Reason: {ban_info[1]}\n"
                f"│ 📅 Banned: {ban_info[2][:10]}\n"
                f"└─────────────────────\n\n"
            )

        # Warnings
        if warn_count > 0:
            profile_msg += (
                f"⚠️ *Warnings:* {warn_count}\n\n"
            )

        # Action buttons
        markup = types.InlineKeyboardMarkup(row_width=2)
        is_banned = target_id in banned_users
        is_admin = target_id in admin_ids

        markup.row(
            types.InlineKeyboardButton(
                "✅ Unban" if is_banned else "🚫 Ban",
                callback_data=(
                    f'owner_do_unban_{target_id}'
                    if is_banned
                    else f'owner_do_ban_{target_id}'
                )
            ),
            types.InlineKeyboardButton(
                "⚠️ Warn",
                callback_data=f'owner_do_warn_{target_id}'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "💬 Message",
                callback_data=f'owner_do_msg_{target_id}'
            ),
            types.InlineKeyboardButton(
                "✏️ Edit Limit",
                callback_data=f'owner_do_limit_{target_id}'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "💳 Add Sub",
                callback_data=f'owner_do_sub_{target_id}'
            ),
            types.InlineKeyboardButton(
                "🗑️ Delete User",
                callback_data=f'owner_do_delete_{target_id}'
            )
        )
        if not is_admin and target_id != OWNER_ID:
            markup.row(
                types.InlineKeyboardButton(
                    "🛡️ Make Admin",
                    callback_data=f'owner_do_admin_{target_id}'
                )
            )
        elif is_admin and target_id != OWNER_ID:
            markup.row(
                types.InlineKeyboardButton(
                    "➖ Remove Admin",
                    callback_data=f'owner_do_unadmin_{target_id}'
                )
            )
        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='owner_user_mgmt'
        ))

        bot.send_message(
            chat_id,
            profile_msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error showing user profile: {e}", exc_info=True)
        bot.send_message(
            chat_id,
            f"❌ Error loading profile for `{target_id}`: {e}",
            parse_mode='Markdown'
        )


def handle_owner_list_users(call):
    """List all users with pagination"""
    bot.answer_callback_query(call.id)
    show_users_page(call.message.chat.id, 0)


def show_users_page(chat_id, page, filter_type='all'):
    """Show paginated user list"""
    page_size = 10

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()

        if filter_type == 'premium':
            c.execute(
                '''SELECT up.user_id, up.first_name, up.username,
                   up.last_active, s.plan
                   FROM user_profiles up
                   JOIN subscriptions s ON up.user_id = s.user_id
                   ORDER BY up.last_active DESC
                   LIMIT ? OFFSET ?''',
                (page_size, page * page_size)
            )
        elif filter_type == 'banned':
            c.execute(
                '''SELECT up.user_id, up.first_name, up.username,
                   up.last_active, 'banned'
                   FROM user_profiles up
                   JOIN bans b ON up.user_id = b.user_id
                   WHERE b.is_active = 1
                   ORDER BY b.banned_at DESC
                   LIMIT ? OFFSET ?''',
                (page_size, page * page_size)
            )
        else:
            c.execute(
                '''SELECT user_id, first_name, username,
                   last_active, 'free'
                   FROM user_profiles
                   ORDER BY last_active DESC
                   LIMIT ? OFFSET ?''',
                (page_size, page * page_size)
            )

        users = c.fetchall()

        # Total count
        c.execute('SELECT COUNT(*) FROM user_profiles')
        total = c.fetchone()[0]
        conn.close()

        if not users:
            bot.send_message(
                chat_id,
                f"👥 No users found.",
                parse_mode='Markdown'
            )
            return

        total_pages = (total + page_size - 1) // page_size

        msg = (
            f"👥 *User List*\n"
            f"{DIVIDER}\n"
            f"📄 Page {page + 1}/{total_pages} "
            f"({total} total)\n\n"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)

        for user in users:
            uid, fname, uname, last_active, extra = user
            status_icon = get_user_status_icon(uid)
            is_running = any(
                v.get('script_owner_id') == uid
                for v in bot_scripts.values()
            )
            run_icon = "🟢" if is_running else "⚫"
            btn_text = (
                f"{status_icon} {fname or 'Unknown'} "
                f"(@{uname or 'N/A'}) [{uid}] {run_icon}"
            )
            markup.add(types.InlineKeyboardButton(
                btn_text,
                callback_data=f'owner_view_user_{uid}'
            ))

        # Navigation
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                types.InlineKeyboardButton(
                    "⬅️ Prev",
                    callback_data=f'owner_users_page_{page-1}'
                )
            )
        if page < total_pages - 1:
            nav_buttons.append(
                types.InlineKeyboardButton(
                    "➡️ Next",
                    callback_data=f'owner_users_page_{page+1}'
                )
            )
        if nav_buttons:
            markup.row(*nav_buttons)

        # Filter buttons
        markup.row(
            types.InlineKeyboardButton(
                "👥 All",
                callback_data='owner_users_filter_all'
            ),
            types.InlineKeyboardButton(
                "💳 Premium",
                callback_data='owner_users_filter_premium'
            ),
            types.InlineKeyboardButton(
                "🚫 Banned",
                callback_data='owner_users_filter_banned'
            )
        )
        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='owner_user_mgmt'
        ))

        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error listing users: {e}", exc_info=True)
        bot.send_message(chat_id, f"❌ Error: {e}")


def handle_owner_ban_user(call):
    """Initiate ban flow"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"🚫 *Ban User*\n"
        f"{DIVIDER}\n"
        f"Enter the User ID to ban:\n"
        f"{THIN_DIVIDER}\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_ban_user_id)


def process_ban_user_id(message):
    """Process ban - get user ID"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Ban cancelled.")
        return

    if message.from_user.id != OWNER_ID:
        return

    try:
        target_id = int(message.text.strip())
        if target_id == OWNER_ID:
            bot.reply_to(message, "⚠️ Cannot ban yourself.")
            return

        # Ask ban type
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "🔴 Permanent",
                callback_data=f'ban_type_permanent_{target_id}'
            ),
            types.InlineKeyboardButton(
                "⏱️ Temporary",
                callback_data=f'ban_type_temporary_{target_id}'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "🔇 Soft Ban",
                callback_data=f'ban_type_soft_{target_id}'
            ),
            types.InlineKeyboardButton(
                "❌ Cancel",
                callback_data='owner_user_mgmt'
            )
        )

        bot.reply_to(
            message,
            f"🚫 *Ban Type for* `{target_id}`\n"
            f"{DIVIDER}\n"
            f"Select ban type:",
            parse_mode='Markdown',
            reply_markup=markup
        )

    except ValueError:
        bot.reply_to(
            message,
            "⚠️ Invalid ID. Send a valid numeric user ID."
        )


def handle_ban_type_selection(call):
    """Handle ban type selection"""
    parts = call.data.split('_')
    ban_type = parts[2]
    target_id = int(parts[3])
    bot.answer_callback_query(call.id)

    if ban_type == 'temporary':
        msg = bot.send_message(
            call.message.chat.id,
            f"⏱️ *Temporary Ban Duration*\n"
            f"Enter hours (e.g., `24` for 1 day):",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(
            msg,
            lambda m: process_temp_ban_duration(
                m, target_id
            )
        )
    else:
        msg = bot.send_message(
            call.message.chat.id,
            f"📋 *Ban Reason*\n"
            f"Enter reason for banning `{target_id}`:",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(
            msg,
            lambda m: process_ban_reason(
                m, target_id, ban_type
            )
        )


def process_temp_ban_duration(message, target_id):
    """Process temporary ban duration"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        hours = int(message.text.strip())
        if hours <= 0:
            raise ValueError()
        msg = bot.reply_to(
            message,
            f"📋 Enter reason for temp ban ({hours}h):"
        )
        bot.register_next_step_handler(
            msg,
            lambda m: process_ban_reason(
                m, target_id, 'temporary', hours
            )
        )
    except ValueError:
        bot.reply_to(
            message,
            "⚠️ Invalid duration. Enter hours as number."
        )


def process_ban_reason(message, target_id,
                       ban_type, duration_hours=None):
    """Execute the ban"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Ban cancelled.")
        return

    reason = message.text.strip()

    ban_user_db(
        target_id,
        ban_type=ban_type,
        reason=reason,
        banned_by=message.from_user.id,
        duration_hours=duration_hours
    )

    # Notify banned user
    try:
        dur_text = (
            f" for {duration_hours} hours"
            if duration_hours else ""
        )
        bot.send_message(
            target_id,
            f"🚫 *You Have Been Banned*\n"
            f"{DIVIDER}\n"
            f"📋 *Reason:* {reason}\n"
            f"🔒 *Type:* {ban_type.title()}{dur_text}\n"
            f"{THIN_DIVIDER}\n"
            f"_Contact support to appeal._"
        )
    except Exception:
        pass

    bot.reply_to(
        message,
        f"✅ *User Banned*\n"
        f"{DIVIDER}\n"
        f"👤 ID: `{target_id}`\n"
        f"🔒 Type: {ban_type}\n"
        f"📋 Reason: {reason}\n"
        f"{'⏱️ Duration: ' + str(duration_hours) + 'h' if duration_hours else ''}",
        parse_mode='Markdown'
    )


def handle_owner_unban_user(call):
    """Initiate unban flow"""
    bot.answer_callback_query(call.id)

    if not banned_users:
        bot.send_message(
            call.message.chat.id,
            f"✅ *No Banned Users*\n"
            f"There are no currently banned users.",
            parse_mode='Markdown'
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, info in list(banned_users.items())[:20]:
        markup.add(types.InlineKeyboardButton(
            f"🚫 {uid} - {info.get('reason', 'N/A')[:30]}",
            callback_data=f'owner_do_unban_{uid}'
        ))
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_user_mgmt'
    ))

    bot.send_message(
        call.message.chat.id,
        f"✅ *Unban User*\n"
        f"{DIVIDER}\n"
        f"Select user to unban:",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_do_unban(call):
    """Execute unban"""
    target_id = int(call.data.replace('owner_do_unban_', ''))
    bot.answer_callback_query(call.id, "✅ Unbanning...")

    unban_user_db(target_id, unbanned_by=call.from_user.id)

    # Notify user
    try:
        bot.send_message(
            target_id,
            f"✅ *You Have Been Unbanned*\n"
            f"{DIVIDER}\n"
            f"Your ban has been lifted.\n"
            f"You can now use the bot again.",
            parse_mode='Markdown'
        )
    except Exception:
        pass

    bot.send_message(
        call.message.chat.id,
        f"✅ *User Unbanned*\n"
        f"👤 `{target_id}` has been unbanned.",
        parse_mode='Markdown'
    )


def handle_owner_warn_user(call):
    """Initiate warn flow"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"⚠️ *Warn User*\n"
        f"{DIVIDER}\n"
        f"Enter User ID to warn:\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_warn_user_id)


def process_warn_user_id(message):
    """Process warn - get user ID"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        target_id = int(message.text.strip())
        msg = bot.reply_to(
            message,
            f"📋 Enter warning reason for `{target_id}`:",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(
            msg,
            lambda m: process_warn_reason(m, target_id)
        )
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")


def process_warn_reason(message, target_id):
    """Execute warning"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    reason = message.text.strip()
    warned_by = message.from_user.id

    warn_count = warn_user_db(target_id, reason, warned_by)
    max_warns = get_config(
        'max_warnings_before_ban', MAX_WARNINGS_BEFORE_BAN
    )
    remaining = max_warns - warn_count

    # Send warning to user
    send_warning_to_user(target_id, reason, warned_by, remaining)

    # Check auto-ban
    auto_banned = check_and_auto_ban(target_id, warned_by)

    if auto_banned:
        bot.reply_to(
            message,
            f"🚫 *User Auto-Banned*\n"
            f"User `{target_id}` reached max warnings\n"
            f"and has been automatically banned.",
            parse_mode='Markdown'
        )
    else:
        bot.reply_to(
            message,
            f"⚠️ *Warning Sent*\n"
            f"{DIVIDER}\n"
            f"👤 User: `{target_id}`\n"
            f"📋 Reason: {reason}\n"
            f"⚠️ Count: {warn_count}/{max_warns}\n"
            f"_({remaining} warnings until auto-ban)_",
            parse_mode='Markdown'
        )


def handle_owner_message_user(call):
    """Send direct message to user"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"💬 *Message User*\n"
        f"{DIVIDER}\n"
        f"Enter User ID to message:\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_message_user_id
    )


def process_message_user_id(message):
    """Get user ID for direct message"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        target_id = int(message.text.strip())
        msg = bot.reply_to(
            message,
            f"💬 Enter message to send to `{target_id}`:\n"
            f"_Supports Markdown formatting_",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(
            msg,
            lambda m: process_send_direct_message(m, target_id)
        )
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")


def process_send_direct_message(message, target_id):
    """Send direct message to user"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    msg_text = message.text

    try:
        bot.send_message(
            target_id,
            f"📨 *Message from Owner*\n"
            f"{DIVIDER}\n"
            f"{msg_text}",
            parse_mode='Markdown'
        )
        bot.reply_to(
            message,
            f"✅ *Message Sent!*\n"
            f"Delivered to `{target_id}`",
            parse_mode='Markdown'
        )
        log_audit(
            OWNER_ID, 'direct_message',
            f"Messaged user {target_id}",
            target_id=target_id
        )
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Failed to send: `{e}`",
            parse_mode='Markdown'
        )


def handle_owner_edit_user_limit(call):
    """Edit custom file limit for user"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"✏️ *Edit User File Limit*\n"
        f"{DIVIDER}\n"
        f"Enter: `USER_ID NEW_LIMIT`\n\n"
        f"Examples:\n"
        f"`123456789 25` - Set 25 file limit\n"
        f"`123456789 -1` - Reset to default\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_edit_user_limit
    )


def process_edit_user_limit(message):
    """Process user limit edit"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            raise ValueError("Invalid format")
        target_id = int(parts[0])
        new_limit = int(parts[1])

        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''UPDATE user_profiles
                   SET custom_file_limit = ?
                   WHERE user_id = ?''',
                (new_limit, target_id)
            )
            conn.commit()
            conn.close()

        limit_text = (
            str(new_limit) if new_limit > 0 else "Default"
        )
        bot.reply_to(
            message,
            f"✅ *Limit Updated*\n"
            f"👤 User: `{target_id}`\n"
            f"📁 New Limit: `{limit_text}`",
            parse_mode='Markdown'
        )
        log_audit(
            OWNER_ID, 'edit_user_limit',
            f"Set limit {new_limit} for {target_id}",
            target_id=target_id
        )
    except ValueError:
        bot.reply_to(
            message,
            "⚠️ Invalid format. Use: `USER_ID LIMIT`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


def handle_owner_delete_user(call):
    """Initiate delete user flow"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"🗑️ *Delete User*\n"
        f"{DIVIDER}\n"
        f"⚠️ This will permanently delete:\n"
        f"• User account & profile\n"
        f"• All uploaded files\n"
        f"• All subscriptions\n"
        f"• All data\n\n"
        f"Enter User ID to delete:\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_delete_user_id
    )


def process_delete_user_id(message):
    """Process user deletion"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    if message.from_user.id != OWNER_ID:
        return

    try:
        target_id = int(message.text.strip())
        if target_id == OWNER_ID:
            bot.reply_to(message, "⚠️ Cannot delete owner.")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "🗑️ CONFIRM DELETE",
                callback_data=f'owner_confirm_delete_{target_id}'
            ),
            types.InlineKeyboardButton(
                "❌ Cancel",
                callback_data='owner_user_mgmt'
            )
        )

        bot.reply_to(
            message,
            f"⚠️ *Confirm Delete User*\n"
            f"ID: `{target_id}`\n\n"
            f"*This cannot be undone!*",
            parse_mode='Markdown',
            reply_markup=markup
        )

    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")


def handle_owner_confirm_delete_user(call):
    """Execute user deletion"""
    target_id = int(
        call.data.replace('owner_confirm_delete_', '')
    )
    bot.answer_callback_query(call.id, "🗑️ Deleting user...")

    try:
        # Stop all scripts
        user_script_keys = [
            k for k, v in bot_scripts.items()
            if v.get('script_owner_id') == target_id
        ]
        for key in user_script_keys:
            with BOT_SCRIPTS_LOCK:
                info = bot_scripts.get(key)
            if info:
                kill_process_tree(info)
            with BOT_SCRIPTS_LOCK:
                if key in bot_scripts:
                    del bot_scripts[key]

        # Delete files from disk
        user_folder = get_user_folder(target_id)
        if os.path.exists(user_folder):
            shutil.rmtree(user_folder)

        # Delete from DB
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            tables = [
                'active_users', 'user_files',
                'subscriptions', 'bans', 'warnings',
                'user_profiles', 'env_variables',
                'file_versions', 'schedules',
                'crash_reports', 'payment_requests'
            ]
            for table in tables:
                c.execute(
                    f'DELETE FROM {table} WHERE user_id = ?',
                    (target_id,)
                )
            conn.commit()
            conn.close()

        # Clean memory
        active_users.discard(target_id)
        if target_id in user_subscriptions:
            del user_subscriptions[target_id]
        if target_id in user_files:
            del user_files[target_id]
        if target_id in banned_users:
            del banned_users[target_id]
        if target_id in warned_users:
            del warned_users[target_id]
        verified_users.discard(target_id)

        log_audit(
            OWNER_ID, 'delete_user',
            f"Deleted user {target_id}",
            target_id=target_id,
            severity='critical'
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ *User Deleted*\n"
            f"All data for `{target_id}` removed.",
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error deleting user: {e}", exc_info=True)
        bot.send_message(
            call.message.chat.id,
            f"❌ Error deleting user: {e}",
            parse_mode='Markdown'
        )


def handle_owner_export_users(call):
    """Export all users as CSV"""
    bot.answer_callback_query(call.id, "📤 Exporting...")
    chat_id = call.message.chat.id

    def do_export():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''SELECT up.user_id, up.first_name,
                   up.username, up.first_seen,
                   up.last_active, up.total_uploads,
                   up.total_scripts_run,
                   CASE WHEN s.user_id IS NOT NULL
                        THEN s.plan ELSE 'free' END as plan,
                   CASE WHEN b.user_id IS NOT NULL
                        THEN 'banned' ELSE 'active' END as status
                   FROM user_profiles up
                   LEFT JOIN subscriptions s ON up.user_id = s.user_id
                   LEFT JOIN bans b ON up.user_id = b.user_id
                   AND b.is_active = 1
                   ORDER BY up.first_seen DESC'''
            )
            rows = c.fetchall()
            conn.close()

            # Create CSV
            import io
            output = io.StringIO()
            output.write(
                "user_id,first_name,username,first_seen,"
                "last_active,total_uploads,total_scripts_run,"
                "plan,status\n"
            )
            for row in rows:
                output.write(','.join(str(x or '') for x in row) + '\n')

            csv_bytes = output.getvalue().encode('utf-8')
            csv_file = io.BytesIO(csv_bytes)
            csv_file.name = (
                f"users_export_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            bot.send_document(
                chat_id,
                csv_file,
                caption=(
                    f"📤 *Users Export*\n"
                    f"Total: {len(rows)} users\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                ),
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Export error: {e}")

    threading.Thread(target=do_export, daemon=True).start()


def handle_owner_banned_list(call):
    """Show list of banned users"""
    bot.answer_callback_query(call.id)

    if not banned_users:
        bot.send_message(
            call.message.chat.id,
            f"✅ *No Banned Users*\n"
            f"There are currently no banned users.",
            parse_mode='Markdown'
        )
        return

    msg = (
        f"🚫 *Banned Users*\n"
        f"{DIVIDER}\n"
        f"Total: {len(banned_users)}\n\n"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, info in list(banned_users.items())[:15]:
        ban_type = info.get('ban_type', 'permanent')
        reason = info.get('reason', 'N/A')[:25]
        markup.add(types.InlineKeyboardButton(
            f"🚫 {uid} [{ban_type}] - {reason}",
            callback_data=f'owner_view_user_{uid}'
        ))

    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_user_mgmt'
    ))

    bot.send_message(
        call.message.chat.id,
        msg,
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_warned_list(call):
    """Show list of warned users"""
    bot.answer_callback_query(call.id)

    if not warned_users:
        bot.send_message(
            call.message.chat.id,
            f"✅ *No Warned Users*",
            parse_mode='Markdown'
        )
        return

    msg = (
        f"⚠️ *Warned Users*\n"
        f"{DIVIDER}\n"
        f"Total: {len(warned_users)}\n\n"
    )
    max_warns = get_config(
        'max_warnings_before_ban',
        MAX_WARNINGS_BEFORE_BAN
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, warns in list(warned_users.items())[:15]:
        count = len(warns)
        markup.add(types.InlineKeyboardButton(
            f"⚠️ {uid} - {count}/{max_warns} warnings",
            callback_data=f'owner_view_user_{uid}'
        ))

    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_user_mgmt'
    ))

    bot.send_message(
        call.message.chat.id,
        msg,
        parse_mode='Markdown',
        reply_markup=markup
    )


# ============================================================
# OWNER - PENDING APPROVALS PANEL
# ============================================================

def show_owner_approvals(call):
    """Show pending file approvals"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    if not pending_approvals:
        markup = owner_back_button()
        bot.send_message(
            chat_id,
            f"✅ *No Pending Approvals*\n"
            f"{DIVIDER}\n"
            f"All file submissions are reviewed.",
            parse_mode='Markdown',
            reply_markup=markup
        )
        return

    msg = (
        f"⏳ *Pending Approvals*\n"
        f"{DIVIDER}\n"
        f"Files awaiting your review: "
        f"`{len(pending_approvals)}`\n\n"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    for appr_id, info in pending_approvals.items():
        user_id = info['user_id']
        file_name = info['file_name']
        severity = info['severity']
        submitted = info['submitted_at'].strftime('%H:%M:%S')
        sev_icon = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡'
        }.get(severity, '⚠️')

        markup.add(types.InlineKeyboardButton(
            f"{sev_icon} {file_name} | User:{user_id} | {submitted}",
            callback_data=f'owner_review_approval_{appr_id}'
        ))

    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    bot.send_message(
        chat_id, msg,
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_review_approval(call):
    """Show approval review options"""
    approval_id = call.data.replace('owner_review_approval_', '')
    bot.answer_callback_query(call.id)

    if approval_id not in pending_approvals:
        bot.send_message(
            call.message.chat.id,
            "⚠️ Approval not found.",
            parse_mode='Markdown'
        )
        return

    info = pending_approvals[approval_id]
    file_content = info['file_content']
    file_name = info['file_name']
    severity = info['severity']
    reason = info['reason']
    user_id = info['user_id']
    md5, sha256 = check_file_hash(file_content)
    sev_icon = {
        'critical': '🔴',
        'high': '🟠',
        'medium': '🟡'
    }.get(severity, '⚠️')

    msg = (
        f"🔍 *File Review*\n"
        f"{DIVIDER}\n"
        f"📄 *File:* `{file_name}`\n"
        f"👤 *User:* `{user_id}`\n"
        f"{sev_icon} *Severity:* `{severity.upper()}`\n"
        f"🔍 *Reason:* {reason}\n"
        f"📦 *Size:* {format_size(len(file_content))}\n"
        f"🔑 *MD5:* `{md5}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✅ Approve & Run",
            callback_data=f'approve_file_{approval_id}'
        ),
        types.InlineKeyboardButton(
            "❌ Reject",
            callback_data=f'reject_file_{approval_id}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📥 Download",
            callback_data=f'download_approval_{approval_id}'
        ),
        types.InlineKeyboardButton(
            "🔍 Scan Report",
            callback_data=f'scan_report_{approval_id}'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back to Approvals",
        callback_data='owner_approvals'
    ))

    bot.send_message(
        call.message.chat.id,
        msg,
        parse_mode='Markdown',
        reply_markup=markup
    )


# ============================================================
# END OF CHUNK 5
# ============================================================
# CHUNK 6: Owner Panel Part 2
# ============================================================
# PASTE THIS AFTER CHUNK 5
# ============================================================

# ============================================================
# OWNER - ADMIN MANAGEMENT
# ============================================================

def show_owner_admin_mgmt(call):
    """Show admin management panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    msg = (
        f"🛡️ *Admin Management*\n"
        f"{DIVIDER}\n"
        f"👑 *Owner:* `{OWNER_ID}`\n"
        f"🛡️ *Total Admins:* `{len(admin_ids)}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select an action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "➕ Add Admin",
            callback_data='owner_add_admin'
        ),
        types.InlineKeyboardButton(
            "➖ Remove Admin",
            callback_data='owner_remove_admin'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📋 List Admins",
            callback_data='owner_list_admins'
        ),
        types.InlineKeyboardButton(
            "✏️ Edit Permissions",
            callback_data='owner_edit_admin_perms'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "👁️ Admin Activity",
            callback_data='owner_admin_activity'
        ),
        types.InlineKeyboardButton(
            "📢 Message All Admins",
            callback_data='owner_msg_all_admins'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_add_admin(call):
    """Add new admin"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"➕ *Add Admin*\n"
        f"{DIVIDER}\n"
        f"Enter User ID to promote to Admin:\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_add_admin_input
    )


def process_add_admin_input(message):
    """Process add admin"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    if message.from_user.id != OWNER_ID:
        return

    try:
        new_admin_id = int(message.text.strip())

        if new_admin_id == OWNER_ID:
            bot.reply_to(
                message,
                "⚠️ You are already the Owner."
            )
            return

        if new_admin_id in admin_ids:
            bot.reply_to(
                message,
                f"⚠️ User `{new_admin_id}` is already an Admin.",
                parse_mode='Markdown'
            )
            return

        # Ask for permissions
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "👑 Full Admin (All Permissions)",
                callback_data=f'admin_perms_full_{new_admin_id}'
            ),
            types.InlineKeyboardButton(
                "🔧 Custom Permissions",
                callback_data=f'admin_perms_custom_{new_admin_id}'
            )
        )

        bot.reply_to(
            message,
            f"➕ *Add Admin* `{new_admin_id}`\n"
            f"{DIVIDER}\n"
            f"Select permission level:",
            parse_mode='Markdown',
            reply_markup=markup
        )

    except ValueError:
        bot.reply_to(message, "⚠️ Invalid User ID.")


def handle_admin_perms_full(call):
    """Add admin with full permissions"""
    new_admin_id = int(
        call.data.replace('admin_perms_full_', '')
    )
    bot.answer_callback_query(call.id)

    add_admin_db(
        new_admin_id,
        added_by=OWNER_ID,
        permissions={
            'can_ban': 1,
            'can_broadcast': 1,
            'can_manage_subs': 1,
            'can_view_files': 1,
            'can_stop_scripts': 1,
            'can_system_monitor': 1
        }
    )

    # Notify new admin
    try:
        bot.send_message(
            new_admin_id,
            f"🎉 *You Are Now an Admin!*\n"
            f"{DIVIDER}\n"
            f"You have been promoted to Admin\n"
            f"with full permissions.\n"
            f"{THIN_DIVIDER}\n"
            f"_Use /start to access admin features._"
        )
    except Exception:
        pass

    bot.send_message(
        call.message.chat.id,
        f"✅ *Admin Added*\n"
        f"👤 `{new_admin_id}` promoted with full permissions.",
        parse_mode='Markdown'
    )


def handle_admin_perms_custom(call):
    """Set custom permissions for admin"""
    new_admin_id = int(
        call.data.replace('admin_perms_custom_', '')
    )
    bot.answer_callback_query(call.id)

    # Show permission toggles
    show_permission_editor(
        call.message.chat.id,
        new_admin_id,
        {
            'can_ban': False,
            'can_broadcast': False,
            'can_manage_subs': False,
            'can_view_files': False,
            'can_stop_scripts': False,
            'can_system_monitor': False
        }
    )


def show_permission_editor(chat_id, admin_id, perms):
    """Show permission editor for admin"""
    def perm_icon(val):
        return "✅" if val else "❌"

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            f"{perm_icon(perms.get('can_ban'))} Ban Users",
            callback_data=f'toggle_perm_can_ban_{admin_id}'
        ),
        types.InlineKeyboardButton(
            f"{perm_icon(perms.get('can_broadcast'))} Broadcast",
            callback_data=f'toggle_perm_can_broadcast_{admin_id}'
        ),
        types.InlineKeyboardButton(
            f"{perm_icon(perms.get('can_manage_subs'))} Manage Subscriptions",
            callback_data=f'toggle_perm_can_manage_subs_{admin_id}'
        ),
        types.InlineKeyboardButton(
            f"{perm_icon(perms.get('can_view_files'))} View All Files",
            callback_data=f'toggle_perm_can_view_files_{admin_id}'
        ),
        types.InlineKeyboardButton(
            f"{perm_icon(perms.get('can_stop_scripts'))} Stop Scripts",
            callback_data=f'toggle_perm_can_stop_scripts_{admin_id}'
        ),
        types.InlineKeyboardButton(
            f"{perm_icon(perms.get('can_system_monitor'))} System Monitor",
            callback_data=f'toggle_perm_can_system_monitor_{admin_id}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "✅ Save & Add Admin",
            callback_data=f'save_admin_perms_{admin_id}'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data='owner_admin_mgmt'
        )
    )

    # Store temp perms
    if not hasattr(show_permission_editor, 'temp_perms'):
        show_permission_editor.temp_perms = {}
    show_permission_editor.temp_perms[admin_id] = perms

    bot.send_message(
        chat_id,
        f"✏️ *Custom Permissions*\n"
        f"{DIVIDER}\n"
        f"Admin: `{admin_id}`\n\n"
        f"Toggle permissions below:\n"
        f"_(✅ = Allowed | ❌ = Denied)_",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_toggle_perm(call):
    """Toggle a permission for admin"""
    parts = call.data.split('_')
    # Format: toggle_perm_{perm_name}_{admin_id}
    admin_id = int(parts[-1])
    perm_name = '_'.join(parts[2:-1])

    if not hasattr(show_permission_editor, 'temp_perms'):
        show_permission_editor.temp_perms = {}

    perms = show_permission_editor.temp_perms.get(admin_id, {})
    perms[perm_name] = not perms.get(perm_name, False)
    show_permission_editor.temp_perms[admin_id] = perms

    bot.answer_callback_query(
        call.id,
        f"{'✅ Enabled' if perms[perm_name] else '❌ Disabled'}: {perm_name}"
    )

    # Refresh permission editor
    try:
        def perm_icon(val):
            return "✅" if val else "❌"

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                f"{perm_icon(perms.get('can_ban'))} Ban Users",
                callback_data=f'toggle_perm_can_ban_{admin_id}'
            ),
            types.InlineKeyboardButton(
                f"{perm_icon(perms.get('can_broadcast'))} Broadcast",
                callback_data=f'toggle_perm_can_broadcast_{admin_id}'
            ),
            types.InlineKeyboardButton(
                f"{perm_icon(perms.get('can_manage_subs'))} Manage Subscriptions",
                callback_data=f'toggle_perm_can_manage_subs_{admin_id}'
            ),
            types.InlineKeyboardButton(
                f"{perm_icon(perms.get('can_view_files'))} View All Files",
                callback_data=f'toggle_perm_can_view_files_{admin_id}'
            ),
            types.InlineKeyboardButton(
                f"{perm_icon(perms.get('can_stop_scripts'))} Stop Scripts",
                callback_data=f'toggle_perm_can_stop_scripts_{admin_id}'
            ),
            types.InlineKeyboardButton(
                f"{perm_icon(perms.get('can_system_monitor'))} System Monitor",
                callback_data=f'toggle_perm_can_system_monitor_{admin_id}'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "✅ Save & Add Admin",
                callback_data=f'save_admin_perms_{admin_id}'
            ),
            types.InlineKeyboardButton(
                "❌ Cancel",
                callback_data='owner_admin_mgmt'
            )
        )
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error updating permission editor: {e}")


def handle_save_admin_perms(call):
    """Save admin with custom permissions"""
    admin_id = int(
        call.data.replace('save_admin_perms_', '')
    )
    bot.answer_callback_query(call.id)

    if not hasattr(show_permission_editor, 'temp_perms'):
        show_permission_editor.temp_perms = {}

    perms = show_permission_editor.temp_perms.get(admin_id, {})

    add_admin_db(
        admin_id,
        added_by=OWNER_ID,
        permissions=perms
    )

    enabled_perms = [
        k.replace('can_', '').replace('_', ' ').title()
        for k, v in perms.items() if v
    ]

    try:
        bot.send_message(
            admin_id,
            f"🎉 *You Are Now an Admin!*\n"
            f"{DIVIDER}\n"
            f"Promoted with custom permissions.\n"
            f"_Use /start to access admin features._"
        )
    except Exception:
        pass

    perms_text = (
        '\n'.join([f"• {p}" for p in enabled_perms])
        if enabled_perms
        else "• No permissions granted"
    )

    bot.edit_message_text(
        f"✅ *Admin Added*\n"
        f"{DIVIDER}\n"
        f"👤 Admin: `{admin_id}`\n\n"
        f"🔑 *Permissions:*\n{perms_text}",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )

    # Clean temp
    if admin_id in show_permission_editor.temp_perms:
        del show_permission_editor.temp_perms[admin_id]


def handle_owner_remove_admin(call):
    """Remove admin"""
    bot.answer_callback_query(call.id)

    removable = [
        aid for aid in admin_ids
        if aid != OWNER_ID
    ]

    if not removable:
        bot.send_message(
            call.message.chat.id,
            f"⚠️ *No Admins to Remove*\n"
            f"Only the Owner exists.",
            parse_mode='Markdown'
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for aid in removable:
        markup.add(types.InlineKeyboardButton(
            f"🛡️ Remove Admin: {aid}",
            callback_data=f'owner_confirm_rm_admin_{aid}'
        ))
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_admin_mgmt'
    ))

    bot.send_message(
        call.message.chat.id,
        f"➖ *Remove Admin*\n"
        f"{DIVIDER}\n"
        f"Select admin to remove:",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_confirm_rm_admin(call):
    """Confirm and execute admin removal"""
    admin_id = int(
        call.data.replace('owner_confirm_rm_admin_', '')
    )
    bot.answer_callback_query(call.id)

    if remove_admin_db(admin_id, removed_by=OWNER_ID):
        try:
            bot.send_message(
                admin_id,
                f"ℹ️ *Admin Status Removed*\n"
                f"You are no longer an admin.",
                parse_mode='Markdown'
            )
        except Exception:
            pass

        bot.send_message(
            call.message.chat.id,
            f"✅ *Admin Removed*\n"
            f"👤 `{admin_id}` is no longer an admin.",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            call.message.chat.id,
            f"❌ Failed to remove admin `{admin_id}`.",
            parse_mode='Markdown'
        )


def handle_owner_list_admins(call):
    """List all admins with details"""
    bot.answer_callback_query(call.id)

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT user_id, added_by, added_at,
               can_ban, can_broadcast, can_manage_subs,
               can_view_files, can_stop_scripts,
               can_system_monitor
               FROM admins ORDER BY added_at'''
        )
        admins = c.fetchall()
        conn.close()

        msg = (
            f"📋 *Admin List*\n"
            f"{DIVIDER}\n"
            f"Total: {len(admins)}\n\n"
        )

        for admin in admins:
            uid = admin[0]
            added_by = admin[1]
            added_at = admin[2][:10] if admin[2] else 'N/A'
            perms = admin[3:]
            perm_names = [
                'Ban', 'Broadcast', 'Subs',
                'Files', 'Scripts', 'SysMon'
            ]
            perm_str = ' | '.join([
                f"{'✅' if p else '❌'}{name}"
                for p, name in zip(perms, perm_names)
            ])

            is_owner = uid == OWNER_ID
            role = "👑 Owner" if is_owner else "🛡️ Admin"

            msg += (
                f"┌─────────────────────\n"
                f"│ {role}: `{uid}`\n"
                f"│ 📅 Added: {added_at}\n"
                f"│ 👤 By: `{added_by}`\n"
            )
            if not is_owner:
                msg += f"│ 🔑 {perm_str}\n"
            msg += f"└─────────────────────\n\n"

        markup = owner_back_button('owner_admin_mgmt')
        bot.send_message(
            call.message.chat.id,
            msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error: {e}"
        )


def handle_owner_admin_activity(call):
    """Show admin activity logs"""
    bot.answer_callback_query(call.id)

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT user_id, action, details,
               timestamp, severity
               FROM audit_logs
               WHERE user_id IN ({})
               ORDER BY timestamp DESC
               LIMIT 30'''.format(
                ','.join('?' * len(admin_ids))
            ),
            list(admin_ids)
        )
        logs = c.fetchall()
        conn.close()

        if not logs:
            bot.send_message(
                call.message.chat.id,
                f"📋 *No Admin Activity Yet*",
                parse_mode='Markdown'
            )
            return

        msg = (
            f"👁️ *Admin Activity Log*\n"
            f"{DIVIDER}\n"
            f"Last 30 actions:\n\n"
        )

        for log in logs:
            uid, action, details, timestamp, severity = log
            sev_icon = {
                'critical': '🔴',
                'warning': '🟡',
                'info': '🔵'
            }.get(severity, '⚪')

            time_str = timestamp[11:16] if timestamp else 'N/A'
            date_str = timestamp[:10] if timestamp else 'N/A'

            msg += (
                f"{sev_icon} `{uid}` • {action}\n"
                f"   _{details[:50]}_\n"
                f"   🕐 {date_str} {time_str}\n\n"
            )

        if len(msg) > 4000:
            msg = msg[:3900] + "\n\n_...truncated_"

        markup = owner_back_button('owner_admin_mgmt')
        bot.send_message(
            call.message.chat.id,
            msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error: {e}"
        )


def handle_owner_msg_all_admins(call):
    """Send message to all admins"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"📢 *Message All Admins*\n"
        f"{DIVIDER}\n"
        f"Enter message to send to all admins:\n"
        f"_{len(admin_ids) - 1} admin(s) will receive it_\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_msg_all_admins
    )


def process_msg_all_admins(message):
    """Send message to all admins"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    msg_text = message.text
    sent = 0
    failed = 0

    for aid in admin_ids:
        if aid == OWNER_ID:
            continue
        try:
            bot.send_message(
                aid,
                f"📢 *Message from Owner*\n"
                f"{DIVIDER}\n"
                f"{msg_text}",
                parse_mode='Markdown'
            )
            sent += 1
        except Exception:
            failed += 1

    bot.reply_to(
        message,
        f"✅ *Message Sent to Admins*\n"
        f"✅ Delivered: {sent}\n"
        f"❌ Failed: {failed}",
        parse_mode='Markdown'
    )


# ============================================================
# OWNER - SYSTEM CONTROL
# ============================================================

def show_owner_system_control(call):
    """Show system control panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    # Get system info
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    sys_uptime = format_uptime(boot_time)

    msg = (
        f"💻 *System Control*\n"
        f"{DIVIDER}\n"
        f"{make_status_bar(cpu, ram.percent, disk.percent)}\n\n"
        f"🧠 RAM: {format_size(ram.used)}/{format_size(ram.total)}\n"
        f"💾 Disk: {format_size(disk.used)}/{format_size(disk.total)}\n"
        f"🌐 Net ↑: {format_size(net.bytes_sent)} "
        f"↓: {format_size(net.bytes_recv)}\n"
        f"⏱️ System Uptime: {sys_uptime}\n"
        f"🐍 Python: {sys.version.split()[0]}\n"
        f"💻 OS: {sys.platform}\n"
        f"{THIN_DIVIDER}\n"
        f"_Select an action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "📊 Live Monitor",
            callback_data='owner_live_monitor'
        ),
        types.InlineKeyboardButton(
            "⚙️ Process Manager",
            callback_data='owner_process_mgr'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "💻 Terminal",
            callback_data='owner_terminal'
        ),
        types.InlineKeyboardButton(
            "📁 File Browser",
            callback_data='owner_file_browser'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🔄 Clear Temp Files",
            callback_data='owner_clear_temp'
        ),
        types.InlineKeyboardButton(
            "📊 Resource Graph",
            callback_data='owner_resource_graph'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_live_monitor(call):
    """Show live system monitor"""
    bot.answer_callback_query(call.id, "📊 Loading monitor...")
    chat_id = call.message.chat.id

    def get_monitor_data():
        cpu_per_core = psutil.cpu_percent(
            interval=1, percpu=True
        )
        cpu_total = psutil.cpu_percent(interval=0)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        temps = {}
        try:
            temps = psutil.sensors_temperatures()
        except Exception:
            pass

        # Top processes by CPU
        processes = []
        for proc in psutil.process_iter(
            ['pid', 'name', 'cpu_percent', 'memory_percent']
        ):
            try:
                processes.append(proc.info)
            except Exception:
                pass
        processes.sort(
            key=lambda x: x.get('cpu_percent', 0),
            reverse=True
        )
        top_procs = processes[:5]

        return (
            cpu_per_core, cpu_total, ram,
            disk, net, top_procs
        )

    def build_monitor_msg(data):
        cpu_per_core, cpu_total, ram, disk, net, top_procs = data

        # CPU cores bar
        core_bars = ""
        for i, core in enumerate(cpu_per_core[:4]):
            filled = int(core / 10)
            bar = "█" * filled + "░" * (10 - filled)
            core_bars += f"Core {i}: [{bar}] {core:.1f}%\n"

        # Top processes
        proc_text = ""
        for p in top_procs:
            proc_text += (
                f"• `{p.get('name', 'N/A')[:15]}` "
                f"CPU:{p.get('cpu_percent', 0):.1f}% "
                f"RAM:{p.get('memory_percent', 0):.1f}%\n"
            )

        msg = (
            f"📊 *Live System Monitor*\n"
            f"{DIVIDER}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🖥️ *CPU* - Total: `{cpu_total:.1f}%`\n"
            f"```\n{core_bars}```\n"
            f"🧠 *RAM*\n"
            f"```\n"
            f"Used:  {format_size(ram.used)}\n"
            f"Free:  {format_size(ram.available)}\n"
            f"Total: {format_size(ram.total)}\n"
            f"Usage: {ram.percent:.1f}%\n"
            f"```\n"
            f"💾 *Disk*\n"
            f"```\n"
            f"Used:  {format_size(disk.used)}\n"
            f"Free:  {format_size(disk.free)}\n"
            f"Total: {format_size(disk.total)}\n"
            f"Usage: {disk.percent:.1f}%\n"
            f"```\n"
            f"🌐 *Network*\n"
            f"```\n"
            f"Sent: {format_size(net.bytes_sent)}\n"
            f"Recv: {format_size(net.bytes_recv)}\n"
            f"```\n"
            f"⚙️ *Top Processes*\n"
            f"{proc_text}"
            f"{THIN_DIVIDER}\n"
            f"🤖 Bot Scripts: `{len(bot_scripts)}`"
        )
        return msg

    try:
        data = get_monitor_data()
        msg = build_monitor_msg(data)

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "🔄 Refresh",
                callback_data='owner_live_monitor'
            ),
            types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='owner_system'
            )
        )

        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ Monitor error: {e}")


def handle_owner_process_manager(call):
    """Show process manager"""
    bot.answer_callback_query(call.id, "⚙️ Loading processes...")
    chat_id = call.message.chat.id

    def do_load():
        try:
            processes = []
            for proc in psutil.process_iter([
                'pid', 'name', 'status',
                'cpu_percent', 'memory_percent',
                'create_time'
            ]):
                try:
                    processes.append(proc.info)
                except Exception:
                    pass

            processes.sort(
                key=lambda x: x.get('cpu_percent', 0),
                reverse=True
            )
            top = processes[:15]

            msg = (
                f"⚙️ *Process Manager*\n"
                f"{DIVIDER}\n"
                f"Total Processes: {len(processes)}\n\n"
                f"```\n"
                f"{'PID':<8} {'Name':<20} {'CPU%':<8} {'MEM%'}\n"
                f"{'-'*45}\n"
            )

            for p in top:
                pid = str(p.get('pid', 'N/A'))[:7]
                name = str(p.get('name', 'N/A'))[:19]
                cpu = f"{p.get('cpu_percent', 0):.1f}"
                mem = f"{p.get('memory_percent', 0):.1f}"
                msg += f"{pid:<8} {name:<20} {cpu:<8} {mem}\n"

            msg += f"```\n{THIN_DIVIDER}\n"
            msg += "_Click PID to kill process:_\n"

            markup = types.InlineKeyboardMarkup(row_width=3)

            # Add kill buttons for top 9 processes
            buttons = []
            for p in top[:9]:
                pid = p.get('pid')
                name = p.get('name', 'N/A')[:8]
                buttons.append(
                    types.InlineKeyboardButton(
                        f"🔴 {name}",
                        callback_data=f'owner_kill_pid_{pid}'
                    )
                )

            for i in range(0, len(buttons), 3):
                markup.row(*buttons[i:i+3])

            markup.row(
                types.InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data='owner_process_mgr'
                ),
                types.InlineKeyboardButton(
                    f"{ICON_BACK} Back",
                    callback_data='owner_system'
                )
            )

            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_load, daemon=True).start()


def handle_owner_kill_pid(call):
    """Kill a specific process by PID"""
    pid = int(call.data.replace('owner_kill_pid_', ''))

    # Safety check - don't kill own process
    if pid == os.getpid():
        bot.answer_callback_query(
            call.id,
            "⚠️ Cannot kill bot process!",
            show_alert=True
        )
        return

    bot.answer_callback_query(call.id, f"🔴 Killing PID {pid}...")

    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except psutil.TimeoutExpired:
            proc.kill()

        log_audit(
            OWNER_ID, 'kill_process',
            f"Killed process {pid} ({proc_name})",
            severity='warning'
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ *Process Killed*\n"
            f"PID: `{pid}` ({proc_name})",
            parse_mode='Markdown'
        )
    except psutil.NoSuchProcess:
        bot.send_message(
            call.message.chat.id,
            f"⚠️ Process `{pid}` not found.",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error killing PID {pid}: {e}",
            parse_mode='Markdown'
        )


def handle_owner_terminal(call):
    """Open terminal access"""
    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        f"💻 *Terminal Access*\n"
        f"{DIVIDER}\n"
        f"⚠️ *Owner Only - Use Carefully*\n\n"
        f"Send any terminal command:\n\n"
        f"💡 *Examples:*\n"
        f"`ls -la` `pwd` `df -h`\n"
        f"`pip list` `python --version`\n"
        f"`cat /proc/meminfo`\n\n"
        f"🚫 *Blocked Commands:*\n"
        f"Destructive system commands\n"
        f"are automatically blocked.\n"
        f"{THIN_DIVIDER}\n"
        f"_All commands are logged._\n"
        f"Send /cancel to exit terminal.",
        parse_mode='Markdown'
    )

    # Set terminal mode
    if not hasattr(handle_owner_terminal, 'active_sessions'):
        handle_owner_terminal.active_sessions = set()
    handle_owner_terminal.active_sessions.add(
        call.from_user.id
    )

    msg = bot.send_message(
        call.message.chat.id,
        f"💻 *Terminal Ready*\n"
        f"Enter command:",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_terminal_command
    )


def process_terminal_command(message):
    """Process and execute terminal command"""
    if message.from_user.id != OWNER_ID:
        return

    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(
            message,
            f"💻 *Terminal Closed*\n"
            f"_Returned to normal mode._",
            parse_mode='Markdown'
        )
        return

    command = message.text.strip()
    chat_id = message.chat.id

    # Check blacklist
    cmd_lower = command.lower()
    for blocked in BLACKLISTED_TERMINAL_COMMANDS:
        if blocked.lower() in cmd_lower:
            bot.reply_to(
                message,
                f"🚫 *Command Blocked*\n"
                f"This command is blacklisted\n"
                f"for safety reasons.\n"
                f"Command: `{command}`",
                parse_mode='Markdown'
            )
            # Continue terminal session
            msg = bot.send_message(
                chat_id,
                f"💻 Enter next command:",
                parse_mode='Markdown'
            )
            bot.register_next_step_handler(
                msg, process_terminal_command
            )
            return

    # Log command
    log_audit(
        OWNER_ID, 'terminal_command',
        f"Executed: {command}",
        severity='warning'
    )

    def do_execute():
        wait_msg = bot.send_message(
            chat_id,
            f"⏳ *Executing...*\n`{command}`",
            parse_mode='Markdown'
        )

        try:
            timeout = get_config(
                'terminal_timeout_seconds',
                TERMINAL_TIMEOUT_SECONDS
            )

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=BASE_DIR,
                encoding='utf-8',
                errors='ignore'
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            return_code = result.returncode

            output = stdout + stderr
            if not output.strip():
                output = "(No output)"

            # Truncate if too long
            if len(output) > 3500:
                output = output[:3500] + "\n...(truncated)"

            rc_icon = "✅" if return_code == 0 else "❌"

            result_msg = (
                f"💻 *Terminal Output*\n"
                f"{DIVIDER}\n"
                f"$ `{command}`\n"
                f"{rc_icon} Exit Code: `{return_code}`\n\n"
                f"```\n{output}\n```"
            )

            try:
                bot.edit_message_text(
                    result_msg,
                    chat_id,
                    wait_msg.message_id,
                    parse_mode='Markdown'
                )
            except Exception:
                bot.send_message(
                    chat_id,
                    result_msg,
                    parse_mode='Markdown'
                )

        except subprocess.TimeoutExpired:
            bot.edit_message_text(
                f"⏰ *Command Timeout*\n"
                f"Command exceeded "
                f"`{timeout}s` limit.\n"
                f"`{command}`",
                chat_id,
                wait_msg.message_id,
                parse_mode='Markdown'
            )
        except Exception as e:
            bot.edit_message_text(
                f"❌ *Execution Error*\n`{e}`",
                chat_id,
                wait_msg.message_id,
                parse_mode='Markdown'
            )

        # Continue terminal session
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "💻 Continue Terminal",
            callback_data='owner_terminal'
        ))
        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Exit Terminal",
            callback_data='owner_system'
        ))
        bot.send_message(
            chat_id,
            f"💻 *Next Command:*\n"
            f"_(Send command or use buttons)_",
            parse_mode='Markdown',
            reply_markup=markup
        )

    threading.Thread(target=do_execute, daemon=True).start()


def handle_owner_file_browser(call):
    """Browse server file system"""
    bot.answer_callback_query(call.id)
    browse_directory(call.message.chat.id, BASE_DIR)


def browse_directory(chat_id, path):
    """Show directory contents"""
    try:
        if not os.path.exists(path):
            bot.send_message(chat_id, f"❌ Path not found: `{path}`")
            return

        items = os.listdir(path)
        dirs = sorted([
            i for i in items
            if os.path.isdir(os.path.join(path, i))
        ])
        files = sorted([
            i for i in items
            if os.path.isfile(os.path.join(path, i))
        ])

        rel_path = os.path.relpath(path, BASE_DIR)
        if rel_path == '.':
            rel_path = '/'

        msg = (
            f"📁 *File Browser*\n"
            f"{DIVIDER}\n"
            f"📍 `{rel_path}`\n"
            f"📂 {len(dirs)} folders | "
            f"📄 {len(files)} files\n\n"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)

        # Parent directory
        parent = os.path.dirname(path)
        if path != BASE_DIR and parent:
            markup.add(types.InlineKeyboardButton(
                "⬆️ Parent Directory",
                callback_data=f'browse_{parent}'
            ))

        # Directories
        for d in dirs[:10]:
            full_path = os.path.join(path, d)
            try:
                count = len(os.listdir(full_path))
            except Exception:
                count = 0
            markup.add(types.InlineKeyboardButton(
                f"📂 {d}/ ({count} items)",
                callback_data=f'browse_{full_path}'
            ))

        # Files
        for f in files[:10]:
            full_path = os.path.join(path, f)
            try:
                size = format_size(os.path.getsize(full_path))
            except Exception:
                size = "?"
            markup.add(types.InlineKeyboardButton(
                f"📄 {f} ({size})",
                callback_data=f'file_action_{full_path}'
            ))

        if len(dirs) > 10 or len(files) > 10:
            msg += f"_Showing first 10 of each type_\n"

        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back to System",
            callback_data='owner_system'
        ))

        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except PermissionError:
        bot.send_message(
            chat_id,
            f"🔒 Permission denied: `{path}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(chat_id, f"❌ Browser error: {e}")


def handle_file_action(call):
    """Show file action options"""
    file_path = call.data.replace('file_action_', '')
    bot.answer_callback_query(call.id)

    if not os.path.exists(file_path):
        bot.send_message(
            call.message.chat.id,
            f"❌ File not found: `{file_path}`",
            parse_mode='Markdown'
        )
        return

    file_name = os.path.basename(file_path)
    file_size = format_size(os.path.getsize(file_path))
    parent_dir = os.path.dirname(file_path)

    msg = (
        f"📄 *File Options*\n"
        f"{DIVIDER}\n"
        f"📄 *Name:* `{file_name}`\n"
        f"📦 *Size:* {file_size}\n"
        f"📁 *Path:* `{file_path}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "📥 Download",
            callback_data=f'dl_file_{file_path}'
        ),
        types.InlineKeyboardButton(
            "👁️ View Content",
            callback_data=f'view_file_{file_path}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🗑️ Delete",
            callback_data=f'del_file_{file_path}'
        ),
        types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data=f'browse_{parent_dir}'
        )
    )

    bot.send_message(
        call.message.chat.id,
        msg,
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_download_file(call):
    """Download a file from server"""
    file_path = call.data.replace('dl_file_', '')
    bot.answer_callback_query(call.id, "📥 Sending file...")

    if not os.path.exists(file_path):
        bot.send_message(
            call.message.chat.id,
            "❌ File not found.",
            parse_mode='Markdown'
        )
        return

    try:
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            bot.send_message(
                call.message.chat.id,
                f"❌ File too large: {format_size(file_size)}\n"
                f"Max: 50MB",
                parse_mode='Markdown'
            )
            return

        with open(file_path, 'rb') as f:
            bot.send_document(
                call.message.chat.id,
                f,
                caption=(
                    f"📥 `{os.path.basename(file_path)}`\n"
                    f"Size: {format_size(file_size)}"
                ),
                parse_mode='Markdown'
            )
        log_audit(
            OWNER_ID, 'download_file',
            f"Downloaded: {file_path}"
        )
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Download error: {e}"
        )


def handle_view_file(call):
    """View file content"""
    file_path = call.data.replace('view_file_', '')
    bot.answer_callback_query(call.id)

    if not os.path.exists(file_path):
        bot.send_message(
            call.message.chat.id,
            "❌ File not found."
        )
        return

    try:
        file_size = os.path.getsize(file_path)
        max_view = 3000

        with open(file_path, 'r',
                  encoding='utf-8', errors='ignore') as f:
            content = f.read(max_view)

        truncated = file_size > max_view
        msg = (
            f"👁️ *File Content*\n"
            f"{DIVIDER}\n"
            f"📄 `{os.path.basename(file_path)}`\n"
            f"{'_(truncated to 3KB)_' if truncated else ''}\n\n"
            f"```\n{content}\n```"
        )

        if len(msg) > 4096:
            msg = msg[:4000] + "\n```\n_(cut)_"

        markup = owner_back_button('owner_system')
        bot.send_message(
            call.message.chat.id,
            msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except UnicodeDecodeError:
        bot.send_message(
            call.message.chat.id,
            f"⚠️ Binary file - cannot display as text.\n"
            f"Use Download instead.",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ View error: {e}"
        )


def handle_delete_server_file(call):
    """Delete a file from server"""
    file_path = call.data.replace('del_file_', '')
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🗑️ CONFIRM DELETE",
            callback_data=f'confirm_del_file_{file_path}'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data=f'browse_{os.path.dirname(file_path)}'
        )
    )

    bot.send_message(
        call.message.chat.id,
        f"⚠️ *Confirm Delete*\n"
        f"{DIVIDER}\n"
        f"Delete: `{os.path.basename(file_path)}`?\n\n"
        f"*This cannot be undone!*",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_confirm_delete_server_file(call):
    """Execute file deletion"""
    file_path = call.data.replace('confirm_del_file_', '')
    bot.answer_callback_query(call.id, "🗑️ Deleting...")

    try:
        os.remove(file_path)
        log_audit(
            OWNER_ID, 'delete_file',
            f"Deleted: {file_path}",
            severity='warning'
        )
        bot.send_message(
            call.message.chat.id,
            f"✅ *File Deleted*\n"
            f"`{os.path.basename(file_path)}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Delete error: {e}"
        )


def handle_owner_clear_temp(call):
    """Clear temporary files"""
    bot.answer_callback_query(call.id, "🔄 Clearing temp...")

    try:
        cleared = 0
        total_size = 0

        for item in os.listdir(TEMP_DIR):
            item_path = os.path.join(TEMP_DIR, item)
            try:
                size = os.path.getsize(item_path)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    size = sum(
                        os.path.getsize(os.path.join(dp, f))
                        for dp, dn, fn in os.walk(item_path)
                        for f in fn
                    )
                    shutil.rmtree(item_path)
                cleared += 1
                total_size += size
            except Exception:
                pass

        log_audit(
            OWNER_ID, 'clear_temp',
            f"Cleared {cleared} temp items "
            f"({format_size(total_size)})"
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ *Temp Files Cleared*\n"
            f"{DIVIDER}\n"
            f"🗑️ Items: `{cleared}`\n"
            f"💾 Freed: `{format_size(total_size)}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Clear error: {e}"
        )


# ============================================================
# OWNER - DATABASE CONTROL
# ============================================================

def show_owner_database(call):
    """Show database control panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    try:
        db_size = format_size(os.path.getsize(DATABASE_PATH))
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()

        # Get table counts
        tables = [
            'active_users', 'user_files',
            'subscriptions', 'admins', 'bans',
            'warnings', 'audit_logs', 'schedules'
        ]
        table_counts = {}
        for table in tables:
            try:
                c.execute(f'SELECT COUNT(*) FROM {table}')
                table_counts[table] = c.fetchone()[0]
            except Exception:
                table_counts[table] = 0

        conn.close()

        counts_text = "\n".join([
            f"│ {t.replace('_', ' ').title()}: "
            f"`{table_counts.get(t, 0)}`"
            for t in tables
        ])

        msg = (
            f"🗄️ *Database Control*\n"
            f"{DIVIDER}\n"
            f"📦 *Size:* `{db_size}`\n"
            f"📍 *Path:* `{DATABASE_PATH}`\n\n"
            f"📊 *Table Records:*\n"
            f"┌─────────────────────\n"
            f"{counts_text}\n"
            f"└─────────────────────\n"
            f"{THIN_DIVIDER}\n"
            f"_Select an action:_"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "💾 Backup DB",
                callback_data='owner_backup_db'
            ),
            types.InlineKeyboardButton(
                "📥 Download DB",
                callback_data='owner_download_db'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "🔧 Optimize DB",
                callback_data='owner_optimize_db'
            ),
            types.InlineKeyboardButton(
                "✅ Check Integrity",
                callback_data='owner_check_db'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "🗑️ Clean Old Records",
                callback_data='owner_clean_db'
            ),
            types.InlineKeyboardButton(
                "📊 Browse Tables",
                callback_data='owner_browse_db'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "📥 Restore DB",
                callback_data='owner_restore_db'
            ),
            types.InlineKeyboardButton(
                "⚠️ Reset DB",
                callback_data='owner_reset_db'
            )
        )
        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='owner_panel'
        ))

        try:
            bot.edit_message_text(
                msg, chat_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception:
            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

    except Exception as e:
        bot.send_message(chat_id, f"❌ DB error: {e}")


def handle_owner_backup_db(call):
    """Create database backup"""
    bot.answer_callback_query(call.id, "💾 Creating backup...")
    chat_id = call.message.chat.id

    try:
        backup_name = (
            f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        )
        backup_path = os.path.join(BACKUP_DIR, backup_name)

        # Copy database
        shutil.copy2(DATABASE_PATH, backup_path)
        backup_size = format_size(os.path.getsize(backup_path))

        log_audit(
            OWNER_ID, 'backup_db',
            f"Created backup: {backup_name}"
        )

        # Send backup file
        with open(backup_path, 'rb') as f:
            bot.send_document(
                chat_id,
                f,
                caption=(
                    f"💾 *Database Backup*\n"
                    f"📄 `{backup_name}`\n"
                    f"📦 Size: {backup_size}\n"
                    f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                parse_mode='Markdown'
            )

        bot.send_message(
            chat_id,
            f"✅ *Backup Created*\n"
            f"💾 Saved: `{backup_name}`\n"
            f"📦 Size: {backup_size}",
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ Backup error: {e}")


def handle_owner_download_db(call):
    """Download the live database"""
    bot.answer_callback_query(call.id, "📥 Sending database...")

    try:
        db_size = os.path.getsize(DATABASE_PATH)
        with open(DATABASE_PATH, 'rb') as f:
            bot.send_document(
                call.message.chat.id,
                f,
                caption=(
                    f"📥 *Live Database*\n"
                    f"📦 Size: {format_size(db_size)}\n"
                    f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                parse_mode='Markdown'
            )
        log_audit(
            OWNER_ID, 'download_db',
            f"Downloaded live database"
        )
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Download error: {e}"
        )


def handle_owner_optimize_db(call):
    """Optimize database"""
    bot.answer_callback_query(call.id, "🔧 Optimizing...")

    def do_optimize():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            before_size = os.path.getsize(DATABASE_PATH)

            conn.execute('VACUUM')
            conn.execute('ANALYZE')
            conn.execute('REINDEX')
            conn.commit()
            conn.close()

            after_size = os.path.getsize(DATABASE_PATH)
            saved = before_size - after_size

            log_audit(
                OWNER_ID, 'optimize_db',
                f"Optimized DB. Saved {format_size(max(saved, 0))}"
            )

            bot.send_message(
                call.message.chat.id,
                f"✅ *Database Optimized*\n"
                f"{DIVIDER}\n"
                f"📦 Before: {format_size(before_size)}\n"
                f"📦 After: {format_size(after_size)}\n"
                f"💾 Saved: {format_size(max(saved, 0))}",
                parse_mode='Markdown'
            )
        except Exception as e:
            bot.send_message(
                call.message.chat.id,
                f"❌ Optimize error: {e}"
            )

    threading.Thread(target=do_optimize, daemon=True).start()


def handle_owner_check_db(call):
    """Check database integrity"""
    bot.answer_callback_query(call.id, "✅ Checking...")

    def do_check():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('PRAGMA integrity_check')
            result = c.fetchone()[0]

            c.execute('PRAGMA foreign_key_check')
            fk_issues = c.fetchall()

            c.execute('PRAGMA quick_check')
            quick = c.fetchone()[0]

            conn.close()

            is_ok = result == 'ok' and not fk_issues

            msg = (
                f"{'✅' if is_ok else '❌'} *Integrity Check*\n"
                f"{DIVIDER}\n"
                f"Main Check: `{result}`\n"
                f"Quick Check: `{quick}`\n"
                f"FK Issues: `{len(fk_issues)}`\n"
                f"{THIN_DIVIDER}\n"
                f"{'_Database is healthy_ ✅' if is_ok else '_Issues found! Consider restore_ ❌'}"
            )

            markup = owner_back_button('owner_database')
            bot.send_message(
                call.message.chat.id,
                msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(
                call.message.chat.id,
                f"❌ Check error: {e}"
            )

    threading.Thread(target=do_check, daemon=True).start()


def handle_owner_clean_db(call):
    """Clean old/expired records from database"""
    bot.answer_callback_query(call.id, "🗑️ Cleaning...")

    def do_clean():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            removed = {}

            # Remove expired subscriptions
            c.execute(
                '''DELETE FROM subscriptions
                   WHERE expiry < ?''',
                (datetime.now().isoformat(),)
            )
            removed['expired_subs'] = c.rowcount

            # Remove old audit logs (>30 days)
            cutoff = (
                datetime.now() - timedelta(days=30)
            ).isoformat()
            c.execute(
                'DELETE FROM audit_logs WHERE timestamp < ?',
                (cutoff,)
            )
            removed['old_logs'] = c.rowcount

            # Remove old uptime logs (>7 days)
            cutoff_7d = (
                datetime.now() - timedelta(days=7)
            ).isoformat()
            c.execute(
                'DELETE FROM uptime_logs WHERE timestamp < ?',
                (cutoff_7d,)
            )
            removed['old_uptime'] = c.rowcount

            # Remove resolved crash reports (>7 days)
            c.execute(
                '''DELETE FROM crash_reports
                   WHERE resolved = 1
                   AND crash_time < ?''',
                (cutoff_7d,)
            )
            removed['old_crashes'] = c.rowcount

            conn.commit()
            conn.execute('VACUUM')
            conn.commit()
            conn.close()

            log_audit(
                OWNER_ID, 'clean_db',
                f"Cleaned DB: {removed}"
            )

            msg = (
                f"✅ *Database Cleaned*\n"
                f"{DIVIDER}\n"
                f"🗑️ Expired subs: `{removed['expired_subs']}`\n"
                f"🗑️ Old logs: `{removed['old_logs']}`\n"
                f"🗑️ Old uptime: `{removed['old_uptime']}`\n"
                f"🗑️ Old crashes: `{removed['old_crashes']}`"
            )

            markup = owner_back_button('owner_database')
            bot.send_message(
                call.message.chat.id,
                msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(
                call.message.chat.id,
                f"❌ Clean error: {e}"
            )

    threading.Thread(target=do_clean, daemon=True).start()


def handle_owner_browse_db(call):
    """Browse database tables"""
    bot.answer_callback_query(call.id)

    tables = [
        'active_users', 'user_files', 'subscriptions',
        'admins', 'bans', 'warnings', 'force_sub_chats',
        'user_profiles', 'env_variables', 'file_versions',
        'schedules', 'crash_reports', 'payment_requests',
        'bot_config', 'audit_logs', 'uptime_logs',
        'incidents', 'broadcast_history'
    ]

    markup = types.InlineKeyboardMarkup(row_width=2)
    for i in range(0, len(tables), 2):
        row_tables = tables[i:i+2]
        buttons = [
            types.InlineKeyboardButton(
                f"🗄️ {t.replace('_', ' ').title()}",
                callback_data=f'view_table_{t}'
            )
            for t in row_tables
        ]
        markup.row(*buttons)

    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_database'
    ))

    bot.send_message(
        call.message.chat.id,
        f"📊 *Browse Database Tables*\n"
        f"{DIVIDER}\n"
        f"Select a table to view:",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_view_table(call):
    """View contents of a database table"""
    table_name = call.data.replace('view_table_', '')
    bot.answer_callback_query(call.id, f"📊 Loading {table_name}...")

    # Whitelist table names for security
    allowed_tables = [
        'active_users', 'user_files', 'subscriptions',
        'admins', 'bans', 'warnings', 'force_sub_chats',
        'user_profiles', 'env_variables', 'file_versions',
        'schedules', 'crash_reports', 'payment_requests',
        'bot_config', 'audit_logs', 'uptime_logs',
        'incidents', 'broadcast_history'
    ]

    if table_name not in allowed_tables:
        bot.send_message(
            call.message.chat.id,
            "⚠️ Invalid table name.",
            parse_mode='Markdown'
        )
        return

    def do_view():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            # Get columns
            c.execute(f'PRAGMA table_info({table_name})')
            columns = [row[1] for row in c.fetchall()]

            # Get count
            c.execute(f'SELECT COUNT(*) FROM {table_name}')
            total = c.fetchone()[0]

            # Get last 5 records
            c.execute(
                f'SELECT * FROM {table_name} '
                f'ORDER BY rowid DESC LIMIT 5'
            )
            rows = c.fetchall()
            conn.close()

            msg = (
                f"📊 *Table: {table_name}*\n"
                f"{DIVIDER}\n"
                f"📋 *Columns:* {len(columns)}\n"
                f"📝 *Total Records:* {total}\n\n"
                f"*Last 5 Records:*\n"
                f"```\n"
            )

            # Column headers
            msg += " | ".join(
                [c[:8] for c in columns[:4]]
            ) + "\n"
            msg += "-" * 40 + "\n"

            for row in rows:
                row_text = " | ".join([
                    str(v)[:8] if v is not None else 'NULL'
                    for v in row[:4]
                ])
                msg += row_text + "\n"

            msg += "```"

            if len(msg) > 4000:
                msg = msg[:3900] + "\n```"

            markup = owner_back_button('owner_browse_db')
            bot.send_message(
                call.message.chat.id,
                msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(
                call.message.chat.id,
                f"❌ Table view error: {e}"
            )

    threading.Thread(target=do_view, daemon=True).start()


def handle_owner_reset_db(call):
    """Reset entire database (with confirmation)"""
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "⚠️ TYPE 'RESET' TO CONFIRM",
            callback_data='owner_reset_db_step2'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data='owner_database'
        )
    )

    bot.send_message(
        call.message.chat.id,
        f"🚨 *Database Reset Warning*\n"
        f"{DIVIDER}\n"
        f"⚠️ This will *permanently delete*\n"
        f"*ALL data* from the database!\n\n"
        f"This includes:\n"
        f"• All users & profiles\n"
        f"• All subscriptions\n"
        f"• All files records\n"
        f"• All settings\n\n"
        f"*This CANNOT be undone!*\n"
        f"Make a backup first!",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_reset_db_step2(call):
    """Second step of DB reset"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"⚠️ *Final Confirmation*\n"
        f"Type `RESET` to confirm database reset.\n"
        f"Any other text will cancel.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_db_reset_confirm
    )


def process_db_reset_confirm(message):
    """Execute database reset if confirmed"""
    if message.from_user.id != OWNER_ID:
        return

    if message.text.strip() != 'RESET':
        bot.reply_to(
            message,
            f"❌ *Reset Cancelled*\n"
            f"Type mismatch. Database safe.",
            parse_mode='Markdown'
        )
        return

    try:
        # Backup first
        backup_path = os.path.join(
            BACKUP_DIR,
            f"pre_reset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        )
        shutil.copy2(DATABASE_PATH, backup_path)

        # Stop all scripts
        with BOT_SCRIPTS_LOCK:
            for key, info in list(bot_scripts.items()):
                kill_process_tree(info)
            bot_scripts.clear()

        # Clear memory
        active_users.clear()
        user_subscriptions.clear()
        user_files.clear()
        banned_users.clear()
        warned_users.clear()
        verified_users.clear()
        force_sub_chats.clear()
        admin_ids.clear()
        admin_ids.add(OWNER_ID)

        # Delete and recreate database
        os.remove(DATABASE_PATH)
        init_db()

        log_audit(
            OWNER_ID, 'reset_db',
            'Full database reset performed',
            severity='critical'
        )

        bot.reply_to(
            message,
            f"✅ *Database Reset Complete*\n"
            f"{DIVIDER}\n"
            f"💾 Backup saved before reset.\n"
            f"🗄️ Fresh database created.\n"
            f"_Restart bot for full effect._",
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Reset error: {e}"
        )


def handle_owner_restore_db(call):
    """Restore database from backup"""
    bot.answer_callback_query(call.id)

    try:
        backups = sorted([
            f for f in os.listdir(BACKUP_DIR)
            if f.endswith('.db')
        ], reverse=True)

        if not backups:
            bot.send_message(
                call.message.chat.id,
                f"⚠️ *No Backups Found*\n"
                f"Create a backup first.",
                parse_mode='Markdown'
            )
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for backup in backups[:10]:
            backup_path = os.path.join(BACKUP_DIR, backup)
            size = format_size(os.path.getsize(backup_path))
            markup.add(types.InlineKeyboardButton(
                f"💾 {backup} ({size})",
                callback_data=f'restore_backup_{backup}'
            ))

        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='owner_database'
        ))

        bot.send_message(
            call.message.chat.id,
            f"💾 *Restore Database*\n"
            f"{DIVIDER}\n"
            f"Select backup to restore:\n"
            f"_⚠️ Current DB will be replaced!_",
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error listing backups: {e}"
        )


def handle_restore_backup(call):
    """Execute database restore"""
    backup_name = call.data.replace('restore_backup_', '')
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    bot.answer_callback_query(call.id, "💾 Restoring...")

    try:
        if not os.path.exists(backup_path):
            bot.send_message(
                call.message.chat.id,
                "❌ Backup file not found."
            )
            return

        # Backup current DB first
        current_backup = os.path.join(
            BACKUP_DIR,
            f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        )
        shutil.copy2(DATABASE_PATH, current_backup)

        # Restore
        shutil.copy2(backup_path, DATABASE_PATH)

        log_audit(
            OWNER_ID, 'restore_db',
            f"Restored from: {backup_name}",
            severity='critical'
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ *Database Restored*\n"
            f"{DIVIDER}\n"
            f"💾 Restored: `{backup_name}`\n"
            f"💾 Old DB backed up.\n"
            f"_Restart bot for full effect._",
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Restore error: {e}"
        )


# ============================================================
# OWNER - BOT CONFIGURATION
# ============================================================

def show_owner_config(call):
    """Show bot configuration panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    force_sub = get_config('force_sub_enabled', False)
    maintenance = get_config('maintenance_mode', False)
    locked = get_config('bot_locked', False)
    auto_restart = get_config('auto_restart_scripts', True)
    daily_report = get_config('daily_report', False)
    webhook = get_config('webhook_mode', False)

    def s(val):
        return "✅ ON" if val else "❌ OFF"

    msg = (
        f"⚙️ *Bot Configuration*\n"
        f"{DIVIDER}\n"
        f"📋 *Current Settings:*\n\n"
        f"🔒 Bot Locked: {s(locked)}\n"
        f"🔧 Maintenance: {s(maintenance)}\n"
        f"📢 Force Sub: {s(force_sub)}\n"
        f"🔄 Auto-Restart: {s(auto_restart)}\n"
        f"📊 Daily Report: {s(daily_report)}\n"
        f"🌐 Webhook Mode: {s(webhook)}\n\n"
        f"📁 Free Limit: "
        f"`{get_config('free_user_limit', FREE_USER_LIMIT)}`\n"
        f"⭐ Premium Limit: "
        f"`{get_config('premium_user_limit', SUBSCRIBED_USER_LIMIT)}`\n"
        f"💎 VIP Limit: "
        f"`{get_config('vip_user_limit', VIP_USER_LIMIT)}`\n"
        f"⚠️ Max Warnings: "
        f"`{get_config('max_warnings_before_ban', MAX_WARNINGS_BEFORE_BAN)}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select setting to change:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "📢 Force Sub Settings",
            callback_data='owner_config_forcesub'
        ),
        types.InlineKeyboardButton(
            "📁 File Limits",
            callback_data='owner_config_limits'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "💬 Edit Messages",
            callback_data='owner_config_messages'
        ),
        types.InlineKeyboardButton(
            "🔔 Notifications",
            callback_data='owner_notifications'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "⏰ Timeouts & Delays",
            callback_data='owner_config_timeouts'
        ),
        types.InlineKeyboardButton(
            "🔒 Security Settings",
            callback_data='owner_config_security'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "💰 Payment Config",
            callback_data='owner_payment'
        ),
        types.InlineKeyboardButton(
            "📋 Subscription Plans",
            callback_data='owner_config_plans'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def show_owner_forcesub_config(call):
    """Show force subscribe configuration"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    enabled = get_config('force_sub_enabled', False)
    chat_count = len(force_sub_chats)

    msg = (
        f"📢 *Force Subscribe Settings*\n"
        f"{DIVIDER}\n"
        f"📊 *Status:* "
        f"{'✅ Enabled' if enabled else '❌ Disabled'}\n"
        f"📋 *Required Chats:* `{chat_count}`\n\n"
    )

    if force_sub_chats:
        msg += f"*Required Chats:*\n"
        for i, chat in enumerate(force_sub_chats, 1):
            chat_name = chat.get('chat_name', 'Unknown')
            chat_type = chat.get('chat_type', 'channel')
            is_private = chat.get('is_private', False)
            type_icon = "📢" if chat_type == 'channel' else "👥"
            priv_icon = "🔒" if is_private else "🌐"
            msg += (
                f"{i}. {type_icon} {priv_icon} "
                f"`{chat_name}`\n"
                f"   ID: `{chat.get('chat_id')}`\n"
            )

    msg += f"\n{THIN_DIVIDER}\n_Select action:_"

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✅ Enable" if not enabled else "❌ Disable",
            callback_data='owner_toggle_forcesub'
        ),
        types.InlineKeyboardButton(
            "➕ Add Public Chat",
            callback_data='owner_add_public_chat'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "➕ Add Private Chat",
            callback_data='owner_add_private_chat'
        ),
        types.InlineKeyboardButton(
            "➖ Remove Chat",
            callback_data='owner_remove_sub_chat'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🧹 Clear Verify Cache",
            callback_data='owner_clear_verify_cache'
        ),
        types.InlineKeyboardButton(
            "🔄 Refresh Invite Links",
            callback_data='owner_refresh_invite_links'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_config'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_toggle_forcesub(call):
    """Toggle force subscribe"""
    bot.answer_callback_query(call.id)
    current = get_config('force_sub_enabled', False)
    new_state = not current
    set_config('force_sub_enabled', new_state)

    state = "✅ Enabled" if new_state else "❌ Disabled"
    log_audit(
        OWNER_ID, 'toggle_forcesub',
        f"Force sub {state}",
        severity='warning'
    )

    bot.send_message(
        call.message.chat.id,
        f"📢 *Force Subscribe {state}*\n"
        f"{'Users must join required chats.' if new_state else 'Users can access bot freely.'}",
        parse_mode='Markdown'
    )
    show_owner_forcesub_config(call)


def handle_owner_add_public_chat(call):
    """Add public chat to force sub"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"➕ *Add Public Chat*\n"
        f"{DIVIDER}\n"
        f"Send the channel/group:\n"
        f"• Username: `@channelname`\n"
        f"• Link: `t.me/channelname`\n\n"
        f"_Format: @username or link_\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_add_public_chat
    )


def process_add_public_chat(message):
    """Process adding public chat"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    input_text = message.text.strip()
    chat_id = message.chat.id

    # Extract username
    if 't.me/' in input_text:
        username = '@' + input_text.split('t.me/')[-1].strip('/')
    elif input_text.startswith('@'):
        username = input_text
    else:
        username = '@' + input_text

    def do_add():
        try:
            # Verify chat exists
            chat_info = bot.get_chat(username)
            chat_db_id = str(chat_info.id)
            chat_name = (
                chat_info.title or
                chat_info.username or
                username
            )
            chat_type = (
                'channel'
                if chat_info.type == 'channel'
                else 'group'
            )

            add_force_sub_chat(
                chat_id=chat_db_id,
                chat_type=chat_type,
                chat_username=username,
                chat_name=chat_name,
                is_private=False
            )

            bot.send_message(
                chat_id,
                f"✅ *Public Chat Added*\n"
                f"{DIVIDER}\n"
                f"📢 *Name:* {chat_name}\n"
                f"🆔 *ID:* `{chat_db_id}`\n"
                f"✳️ *Username:* {username}\n"
                f"🏷️ *Type:* {chat_type}",
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(
                chat_id,
                f"❌ *Failed to Add Chat*\n"
                f"Error: `{e}`\n\n"
                f"_Make sure:\n"
                f"• Bot is admin in the chat\n"
                f"• Username is correct_",
                parse_mode='Markdown'
            )

    threading.Thread(target=do_add, daemon=True).start()


def handle_owner_add_private_chat(call):
    """Add private chat to force sub"""
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"➕ *Add Private Chat*\n"
        f"{DIVIDER}\n"
        f"Send in this format:\n"
        f"`CHAT_ID | INVITE_LINK | CHAT_NAME`\n\n"
        f"Example:\n"
        f"`-1001234567890 | https://t.me/+abc123 | My Channel`\n\n"
        f"💡 *How to get Chat ID:*\n"
        f"Forward a message from the chat\n"
        f"to @userinfobot\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_add_private_chat
    )


def process_add_private_chat(message):
    """Process adding private chat"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    try:
        parts = [p.strip() for p in message.text.split('|')]
        if len(parts) < 2:
            raise ValueError(
                "Format: CHAT_ID | INVITE_LINK | CHAT_NAME"
            )

        chat_id_str = parts[0].strip()
        invite_link = parts[1].strip()
        chat_name = parts[2].strip() if len(parts) > 2 else "Private Chat"

        # Validate chat ID
        chat_numeric_id = int(chat_id_str)

        # Validate invite link
        if not invite_link.startswith('https://t.me/'):
            raise ValueError("Invalid invite link format")

        # Try to verify
        try:
            chat_info = bot.get_chat(chat_numeric_id)
            chat_name = chat_info.title or chat_name
            chat_type = (
                'channel'
                if chat_info.type == 'channel'
                else 'group'
            )
        except Exception:
            chat_type = 'channel'

        add_force_sub_chat(
            chat_id=str(chat_numeric_id),
            chat_type=chat_type,
            chat_name=chat_name,
            invite_link=invite_link,
            is_private=True
        )

        bot.reply_to(
            message,
            f"✅ *Private Chat Added*\n"
            f"{DIVIDER}\n"
            f"📢 *Name:* {chat_name}\n"
            f"🆔 *ID:* `{chat_numeric_id}`\n"
            f"🔗 *Link:* {invite_link}\n"
            f"🔒 *Type:* Private",
            parse_mode='Markdown'
        )

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ *Invalid Format*\n"
            f"Error: {e}\n\n"
            f"Format: `CHAT_ID | INVITE_LINK | NAME`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Error: `{e}`",
            parse_mode='Markdown'
        )


def handle_owner_remove_sub_chat(call):
    """Remove a force sub chat"""
    bot.answer_callback_query(call.id)

    if not force_sub_chats:
        bot.send_message(
            call.message.chat.id,
            f"⚠️ No force sub chats configured.",
            parse_mode='Markdown'
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for chat in force_sub_chats:
        chat_name = chat.get('chat_name', 'Unknown')
        is_private = chat.get('is_private', False)
        priv_icon = "🔒" if is_private else "🌐"
        markup.add(types.InlineKeyboardButton(
            f"🗑️ {priv_icon} {chat_name}",
            callback_data=f'rm_sub_chat_{chat["id"]}'
        ))

    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_config_forcesub'
    ))

    bot.send_message(
        call.message.chat.id,
        f"➖ *Remove Force Sub Chat*\n"
        f"{DIVIDER}\n"
        f"Select chat to remove:",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_rm_sub_chat(call):
    """Execute chat removal"""
    chat_db_id = int(call.data.replace('rm_sub_chat_', ''))
    bot.answer_callback_query(call.id, "🗑️ Removing...")

    remove_force_sub_chat(chat_db_id)
    log_audit(
        OWNER_ID, 'remove_force_sub_chat',
        f"Removed force sub chat ID: {chat_db_id}"
    )

    bot.send_message(
        call.message.chat.id,
        f"✅ *Chat Removed*\n"
        f"Force sub chat removed successfully.\n"
        f"_Verification cache cleared._",
        parse_mode='Markdown'
    )


def handle_owner_clear_verify_cache(call):
    """Clear force sub verification cache"""
    bot.answer_callback_query(call.id, "🧹 Clearing cache...")

    verified_users.clear()

    with DB_LOCK:
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('DELETE FROM verified_force_sub')
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error clearing verify cache: {e}")

    log_audit(
        OWNER_ID, 'clear_verify_cache',
        'Cleared force sub verification cache'
    )

    bot.send_message(
        call.message.chat.id,
        f"✅ *Verification Cache Cleared*\n"
        f"All users will need to re-verify\n"
        f"their channel membership.",
        parse_mode='Markdown'
    )


def handle_owner_refresh_invite_links(call):
    """Refresh invite links for private chats"""
    bot.answer_callback_query(call.id, "🔄 Refreshing links...")

    private_chats = [
        c for c in force_sub_chats
        if c.get('is_private')
    ]

    if not private_chats:
        bot.send_message(
            call.message.chat.id,
            f"ℹ️ No private chats to refresh.",
            parse_mode='Markdown'
        )
        return

    refreshed = 0
    failed = 0

    for chat in private_chats:
        chat_id = chat.get('chat_id')
        db_id = chat.get('id')
        try:
            # Create new invite link
            link = bot.create_chat_invite_link(chat_id)
            new_link = link.invite_link

            with DB_LOCK:
                conn = sqlite3.connect(DATABASE_PATH)
                c = conn.cursor()
                c.execute(
                    '''UPDATE force_sub_chats
                       SET invite_link = ?
                       WHERE id = ?''',
                    (new_link, db_id)
                )
                conn.commit()
                conn.close()

            # Update memory
            for fc in force_sub_chats:
                if fc['id'] == db_id:
                    fc['invite_link'] = new_link
                    break

            refreshed += 1
        except Exception as e:
            logger.error(
                f"Failed to refresh link for {chat_id}: {e}"
            )
            failed += 1

    bot.send_message(
        call.message.chat.id,
        f"🔄 *Invite Links Refreshed*\n"
        f"{DIVIDER}\n"
        f"✅ Refreshed: {refreshed}\n"
        f"❌ Failed: {failed}",
        parse_mode='Markdown'
    )


def show_owner_config_limits(call):
    """Show file limit configuration"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"📁 *File Limit Configuration*\n"
        f"{DIVIDER}\n"
        f"Current limits:\n"
        f"🆓 Free: `{get_config('free_user_limit', FREE_USER_LIMIT)}`\n"
        f"⭐ Premium: `{get_config('premium_user_limit', SUBSCRIBED_USER_LIMIT)}`\n"
        f"💎 VIP: `{get_config('vip_user_limit', VIP_USER_LIMIT)}`\n\n"
        f"Send new limits in format:\n"
        f"`FREE PREMIUM VIP`\n\n"
        f"Example: `10 20 50`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_config_limits
    )


def process_config_limits(message):
    """Process file limit changes"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.strip().split()
        if len(parts) != 3:
            raise ValueError("Need 3 values: FREE PREMIUM VIP")

        free = int(parts[0])
        premium = int(parts[1])
        vip = int(parts[2])

        if not all(v > 0 for v in [free, premium, vip]):
            raise ValueError("All limits must be positive")

        set_config('free_user_limit', free)
        set_config('premium_user_limit', premium)
        set_config('vip_user_limit', vip)

        log_audit(
            OWNER_ID, 'update_limits',
            f"Updated limits: Free={free}, Premium={premium}, VIP={vip}"
        )

        bot.reply_to(
            message,
            f"✅ *Limits Updated*\n"
            f"{DIVIDER}\n"
            f"🆓 Free: `{free}`\n"
            f"⭐ Premium: `{premium}`\n"
            f"💎 VIP: `{vip}`",
            parse_mode='Markdown'
        )
    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid format: {e}\n"
            f"Use: `FREE PREMIUM VIP`",
            parse_mode='Markdown'
        )


def show_owner_config_messages(call):
    """Show message configuration"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "👋 Edit Welcome Message",
            callback_data='owner_edit_msg_welcome'
        ),
        types.InlineKeyboardButton(
            "❓ Edit Help Message",
            callback_data='owner_edit_msg_help'
        ),
        types.InlineKeyboardButton(
            "🔧 Edit Maintenance Message",
            callback_data='owner_edit_msg_maintenance'
        ),
        types.InlineKeyboardButton(
            "🔒 Edit Locked Message",
            callback_data='owner_edit_msg_locked'
        ),
        types.InlineKeyboardButton(
            "📢 Edit Force Sub Message",
            callback_data='owner_edit_msg_forcesub'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_config'
    ))

    bot.send_message(
        chat_id,
        f"💬 *Message Configuration*\n"
        f"{DIVIDER}\n"
        f"Select a message to edit:",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_edit_message(call):
    """Handle editing a bot message"""
    bot.answer_callback_query(call.id)
    msg_type = call.data.replace('owner_edit_msg_', '')

    msg_names = {
        'welcome': 'Welcome Message',
        'help': 'Help Message',
        'maintenance': 'Maintenance Message',
        'locked': 'Locked Message',
        'forcesub': 'Force Sub Message'
    }

    config_keys = {
        'welcome': 'welcome_message',
        'help': 'help_message',
        'maintenance': 'maintenance_message',
        'locked': 'locked_message',
        'forcesub': 'force_sub_message'
    }

    msg_name = msg_names.get(msg_type, msg_type)
    config_key = config_keys.get(msg_type)
    current = get_config(config_key, '')

    msg = bot.send_message(
        call.message.chat.id,
        f"✏️ *Edit {msg_name}*\n"
        f"{DIVIDER}\n"
        f"*Current:*\n"
        f"```\n{current[:500]}\n```\n\n"
        f"Send new message text:\n"
        f"_(Supports Markdown)_\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_edit_message(m, config_key, msg_name)
    )


def process_edit_message(message, config_key, msg_name):
    """Process message edit"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    new_text = message.text
    set_config(config_key, new_text)

    log_audit(
        OWNER_ID, 'edit_message',
        f"Edited {config_key}"
    )

    bot.reply_to(
        message,
        f"✅ *{msg_name} Updated*\n"
        f"{DIVIDER}\n"
        f"New message saved successfully.",
        parse_mode='Markdown'
    )


def show_owner_config_timeouts(call):
    """Show timeout configuration"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"⏰ *Timeouts & Delays*\n"
        f"{DIVIDER}\n"
        f"Current settings:\n"
        f"⏱️ Rate Limit: `{get_config('rate_limit_seconds', RATE_LIMIT_SECONDS)}s`\n"
        f"📤 Upload Cooldown: `{get_config('upload_cooldown_seconds', UPLOAD_COOLDOWN_SECONDS)}s`\n"
        f"💻 Terminal Timeout: `{get_config('terminal_timeout_seconds', TERMINAL_TIMEOUT_SECONDS)}s`\n"
        f"🔄 Restart Delay: `{get_config('restart_delay_seconds', RESTART_DELAY_SECONDS)}s`\n"
        f"🔢 Max Restarts: `{get_config('max_restart_attempts', MAX_RESTART_ATTEMPTS)}`\n\n"
        f"Send new values:\n"
        f"`RATE UPLOAD TERMINAL RESTART MAX_RESTART`\n"
        f"Example: `3 10 30 5 3`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_config_timeouts
    )


def process_config_timeouts(message):
    """Process timeout configuration"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.strip().split()
        if len(parts) != 5:
            raise ValueError("Need 5 values")

        values = [int(p) for p in parts]
        keys = [
            'rate_limit_seconds',
            'upload_cooldown_seconds',
            'terminal_timeout_seconds',
            'restart_delay_seconds',
            'max_restart_attempts'
        ]

        for key, val in zip(keys, values):
            set_config(key, val)

        bot.reply_to(
            message,
            f"✅ *Timeouts Updated*\n"
            f"⏱️ Rate: `{values[0]}s`\n"
            f"📤 Upload: `{values[1]}s`\n"
            f"💻 Terminal: `{values[2]}s`\n"
            f"🔄 Restart: `{values[3]}s`\n"
            f"🔢 Max Restarts: `{values[4]}`",
            parse_mode='Markdown'
        )
    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}\n"
            f"Send 5 numbers.",
            parse_mode='Markdown'
        )


def show_owner_config_security(call):
    """Show security configuration"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"🔒 *Security Settings*\n"
        f"{DIVIDER}\n"
        f"⚠️ Max Warnings: "
        f"`{get_config('max_warnings_before_ban', MAX_WARNINGS_BEFORE_BAN)}`\n\n"
        f"Enter new max warnings:\n"
        f"_(Number before auto-ban)_\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_security_config
    )


def process_security_config(message):
    """Process security configuration"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        max_warns = int(message.text.strip())
        if max_warns < 1:
            raise ValueError("Must be at least 1")

        set_config('max_warnings_before_ban', max_warns)
        bot.reply_to(
            message,
            f"✅ *Security Updated*\n"
            f"⚠️ Max Warnings: `{max_warns}`",
            parse_mode='Markdown'
        )
    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}",
            parse_mode='Markdown'
        )


# ============================================================
# END OF CHUNK 6
# ============================================================
# ============================================================
# CHUNK 7: Owner Panel Part 3
# ============================================================
# PASTE THIS AFTER CHUNK 6
# ============================================================

# ============================================================
# OWNER - ANALYTICS CENTER
# ============================================================

def show_owner_analytics(call):
    """Show analytics center"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def do_analytics():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            # Total users
            c.execute('SELECT COUNT(*) FROM active_users')
            total_users = c.fetchone()[0]

            # New users today
            today = datetime.now().date().isoformat()
            c.execute(
                '''SELECT COUNT(*) FROM active_users
                   WHERE first_seen LIKE ?''',
                (f'{today}%',)
            )
            new_today = c.fetchone()[0]

            # New users this week
            week_ago = (
                datetime.now() - timedelta(days=7)
            ).isoformat()
            c.execute(
                '''SELECT COUNT(*) FROM active_users
                   WHERE first_seen > ?''',
                (week_ago,)
            )
            new_week = c.fetchone()[0]

            # Total files
            c.execute('SELECT COUNT(*) FROM user_files')
            total_files = c.fetchone()[0]

            # Files by type
            c.execute(
                '''SELECT file_type, COUNT(*)
                   FROM user_files GROUP BY file_type'''
            )
            files_by_type = dict(c.fetchall())

            # Total scripts run
            c.execute(
                '''SELECT SUM(total_scripts_run)
                   FROM user_profiles'''
            )
            total_runs = c.fetchone()[0] or 0

            # Total storage
            c.execute(
                '''SELECT SUM(storage_used_bytes)
                   FROM user_profiles'''
            )
            total_storage = c.fetchone()[0] or 0

            # Premium users
            c.execute(
                '''SELECT COUNT(*) FROM subscriptions
                   WHERE expiry > ?''',
                (datetime.now().isoformat(),)
            )
            premium_count = c.fetchone()[0]

            # VIP users
            c.execute(
                '''SELECT COUNT(*) FROM subscriptions
                   WHERE plan = "vip" AND expiry > ?''',
                (datetime.now().isoformat(),)
            )
            vip_count = c.fetchone()[0]

            # Expiring soon (7 days)
            expiring_soon = (
                datetime.now() + timedelta(days=7)
            ).isoformat()
            c.execute(
                '''SELECT COUNT(*) FROM subscriptions
                   WHERE expiry BETWEEN ? AND ?''',
                (datetime.now().isoformat(), expiring_soon)
            )
            expiring_count = c.fetchone()[0]

            # Most active users
            c.execute(
                '''SELECT user_id, first_name,
                   total_scripts_run, total_uploads
                   FROM user_profiles
                   ORDER BY total_scripts_run DESC
                   LIMIT 5'''
            )
            top_users = c.fetchall()

            # Crash stats
            c.execute(
                '''SELECT COUNT(*) FROM crash_reports
                   WHERE crash_time > ?''',
                (week_ago,)
            )
            crashes_week = c.fetchone()[0]

            # Banned users
            c.execute(
                '''SELECT COUNT(*) FROM bans
                   WHERE is_active = 1'''
            )
            banned_count = c.fetchone()[0]

            # Broadcast stats
            c.execute(
                '''SELECT COUNT(*), SUM(sent_count)
                   FROM broadcast_history'''
            )
            bc_stats = c.fetchone()
            bc_count = bc_stats[0] or 0
            bc_sent = bc_stats[1] or 0

            conn.close()

            # Running scripts
            running = sum(
                1 for k, v in bot_scripts.items()
                if is_bot_running(
                    v['script_owner_id'],
                    v['file_name']
                )
            )

            # Uptime stats
            uptime_24h = get_uptime_percentage(24)
            uptime_7d = get_uptime_percentage(168)

            # Build top users text
            top_users_text = ""
            for i, u in enumerate(top_users, 1):
                uid, fname, runs, uploads = u
                icon = get_user_status_icon(uid)
                top_users_text += (
                    f"{i}. {icon} `{fname or uid}`\n"
                    f"   🚀 {runs} runs | 📤 {uploads} uploads\n"
                )

            msg = (
                f"📊 *Analytics Center*\n"
                f"{DIVIDER}\n"
                f"👥 *User Analytics*\n"
                f"┌─────────────────────\n"
                f"│ Total Users: `{total_users}`\n"
                f"│ New Today: `{new_today}`\n"
                f"│ New This Week: `{new_week}`\n"
                f"│ Premium: `{premium_count}`\n"
                f"│ VIP: `{vip_count}`\n"
                f"│ Expiring (7d): `{expiring_count}`\n"
                f"│ Banned: `{banned_count}`\n"
                f"└─────────────────────\n\n"
                f"📁 *File Analytics*\n"
                f"┌─────────────────────\n"
                f"│ Total Files: `{total_files}`\n"
                f"│ Python: `{files_by_type.get('py', 0)}`\n"
                f"│ JavaScript: `{files_by_type.get('js', 0)}`\n"
                f"│ Storage: `{format_size(total_storage)}`\n"
                f"└─────────────────────\n\n"
                f"🤖 *Script Analytics*\n"
                f"┌─────────────────────\n"
                f"│ Total Runs: `{total_runs}`\n"
                f"│ Running Now: `{running}`\n"
                f"│ Crashes (7d): `{crashes_week}`\n"
                f"└─────────────────────\n\n"
                f"📢 *Broadcast Analytics*\n"
                f"┌─────────────────────\n"
                f"│ Total Broadcasts: `{bc_count}`\n"
                f"│ Total Delivered: `{bc_sent}`\n"
                f"└─────────────────────\n\n"
                f"⏱️ *Uptime*\n"
                f"┌─────────────────────\n"
                f"│ Last 24h: `{uptime_24h}%`\n"
                f"│ Last 7d: `{uptime_7d}%`\n"
                f"└─────────────────────\n\n"
                f"🏆 *Top Users (by runs)*\n"
                f"{top_users_text}"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data='owner_analytics'
                ),
                types.InlineKeyboardButton(
                    "📤 Export Report",
                    callback_data='owner_export_analytics'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "💳 Subscription Report",
                    callback_data='owner_sub_report'
                ),
                types.InlineKeyboardButton(
                    "💥 Crash Report",
                    callback_data='owner_crash_report'
                )
            )
            markup.add(types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='owner_panel'
            ))

            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            logger.error(f"Analytics error: {e}", exc_info=True)
            bot.send_message(chat_id, f"❌ Analytics error: {e}")

    threading.Thread(target=do_analytics, daemon=True).start()


def handle_owner_export_analytics(call):
    """Export analytics as CSV report"""
    bot.answer_callback_query(call.id, "📤 Generating report...")
    chat_id = call.message.chat.id

    def do_export():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            import io
            output = io.StringIO()

            # Write report header
            output.write(
                f"Bot Analytics Report\n"
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'='*50}\n\n"
            )

            # User stats
            c.execute(
                '''SELECT up.user_id, up.first_name,
                   up.username, up.first_seen,
                   up.last_active, up.total_uploads,
                   up.total_scripts_run,
                   COALESCE(s.plan, 'free') as plan,
                   CASE WHEN b.user_id IS NOT NULL
                        THEN 'banned' ELSE 'active' END
                   FROM user_profiles up
                   LEFT JOIN subscriptions s
                   ON up.user_id = s.user_id
                   LEFT JOIN bans b
                   ON up.user_id = b.user_id
                   AND b.is_active = 1
                   ORDER BY up.total_scripts_run DESC'''
            )
            users = c.fetchall()

            output.write("USER ANALYTICS\n")
            output.write(
                "user_id,name,username,joined,last_active,"
                "uploads,scripts_run,plan,status\n"
            )
            for u in users:
                output.write(
                    ','.join(str(x or '') for x in u) + '\n'
                )

            output.write(f"\n{'='*50}\n\n")

            # Subscription stats
            c.execute(
                '''SELECT user_id, plan, expiry,
                   added_at FROM subscriptions
                   ORDER BY added_at DESC'''
            )
            subs = c.fetchall()

            output.write("SUBSCRIPTION ANALYTICS\n")
            output.write("user_id,plan,expiry,added_at\n")
            for s in subs:
                output.write(
                    ','.join(str(x or '') for x in s) + '\n'
                )

            output.write(f"\n{'='*50}\n\n")

            # Crash stats
            c.execute(
                '''SELECT user_id, file_name, exit_code,
                   crash_time, restart_count
                   FROM crash_reports
                   ORDER BY crash_time DESC
                   LIMIT 100'''
            )
            crashes = c.fetchall()

            output.write("CRASH ANALYTICS\n")
            output.write(
                "user_id,file_name,exit_code,"
                "crash_time,restart_count\n"
            )
            for cr in crashes:
                output.write(
                    ','.join(str(x or '') for x in cr) + '\n'
                )

            conn.close()

            # Send as file
            csv_bytes = output.getvalue().encode('utf-8')
            csv_file = io.BytesIO(csv_bytes)
            csv_file.name = (
                f"analytics_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            bot.send_document(
                chat_id,
                csv_file,
                caption=(
                    f"📊 *Analytics Export*\n"
                    f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    f"👥 Users: {len(users)}\n"
                    f"💳 Subscriptions: {len(subs)}"
                ),
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Export error: {e}")

    threading.Thread(target=do_export, daemon=True).start()


def handle_owner_sub_report(call):
    """Show subscription analytics report"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def do_report():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            now = datetime.now()

            # Active subs by plan
            c.execute(
                '''SELECT plan, COUNT(*)
                   FROM subscriptions
                   WHERE expiry > ?
                   GROUP BY plan''',
                (now.isoformat(),)
            )
            by_plan = dict(c.fetchall())

            # Expiring in 24h
            tomorrow = (now + timedelta(days=1)).isoformat()
            c.execute(
                '''SELECT user_id, plan, expiry
                   FROM subscriptions
                   WHERE expiry BETWEEN ? AND ?''',
                (now.isoformat(), tomorrow)
            )
            expiring_24h = c.fetchall()

            # Expiring in 7 days
            week = (now + timedelta(days=7)).isoformat()
            c.execute(
                '''SELECT user_id, plan, expiry
                   FROM subscriptions
                   WHERE expiry BETWEEN ? AND ?''',
                (now.isoformat(), week)
            )
            expiring_7d = c.fetchall()

            # Recently added (last 7 days)
            week_ago = (now - timedelta(days=7)).isoformat()
            c.execute(
                '''SELECT COUNT(*) FROM subscriptions
                   WHERE added_at > ?''',
                (week_ago,)
            )
            new_subs_week = c.fetchone()[0]

            # Total expired
            c.execute(
                '''SELECT COUNT(*) FROM subscriptions
                   WHERE expiry < ?''',
                (now.isoformat(),)
            )
            total_expired = c.fetchone()[0]

            conn.close()

            msg = (
                f"💳 *Subscription Report*\n"
                f"{DIVIDER}\n"
                f"📊 *Active by Plan:*\n"
                f"⭐ Premium: `{by_plan.get('premium', 0)}`\n"
                f"💎 VIP: `{by_plan.get('vip', 0)}`\n\n"
                f"📈 *This Week:*\n"
                f"➕ New Subs: `{new_subs_week}`\n"
                f"❌ Expired Total: `{total_expired}`\n\n"
                f"⚠️ *Expiring Soon:*\n"
                f"24h: `{len(expiring_24h)}`\n"
                f"7 days: `{len(expiring_7d)}`\n"
            )

            if expiring_24h:
                msg += f"\n⚠️ *Expiring in 24h:*\n"
                for uid, plan, expiry in expiring_24h[:5]:
                    exp_dt = expiry[:16]
                    msg += f"• `{uid}` ({plan}) - {exp_dt}\n"

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "📢 Notify Expiring",
                    callback_data='owner_notify_expiring'
                ),
                types.InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data='owner_sub_report'
                )
            )
            markup.add(types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='owner_analytics'
            ))

            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Report error: {e}")

    threading.Thread(target=do_report, daemon=True).start()


def handle_owner_notify_expiring(call):
    """Notify users whose sub is expiring"""
    bot.answer_callback_query(call.id, "📢 Notifying...")
    chat_id = call.message.chat.id

    def do_notify():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            week = (
                datetime.now() + timedelta(days=7)
            ).isoformat()
            c.execute(
                '''SELECT user_id, plan, expiry
                   FROM subscriptions
                   WHERE expiry BETWEEN ? AND ?''',
                (datetime.now().isoformat(), week)
            )
            expiring = c.fetchall()
            conn.close()

            sent = 0
            for uid, plan, expiry in expiring:
                try:
                    exp_dt = datetime.fromisoformat(expiry)
                    days_left = (exp_dt - datetime.now()).days
                    bot.send_message(
                        uid,
                        f"⚠️ *Subscription Expiring Soon*\n"
                        f"{DIVIDER}\n"
                        f"💳 Plan: {plan.upper()}\n"
                        f"⏳ Expires in: *{days_left} days*\n"
                        f"📅 Date: {expiry[:10]}\n"
                        f"{THIN_DIVIDER}\n"
                        f"_Contact owner to renew._",
                        parse_mode='Markdown'
                    )
                    sent += 1
                    time.sleep(0.3)
                except Exception:
                    pass

            bot.send_message(
                chat_id,
                f"✅ *Notifications Sent*\n"
                f"📢 Notified {sent}/{len(expiring)} users.",
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_notify, daemon=True).start()


def handle_owner_crash_report(call):
    """Show crash analytics"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def do_report():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            week_ago = (
                datetime.now() - timedelta(days=7)
            ).isoformat()

            # Recent crashes
            c.execute(
                '''SELECT user_id, file_name, exit_code,
                   crash_time, restart_count
                   FROM crash_reports
                   WHERE crash_time > ?
                   ORDER BY crash_time DESC
                   LIMIT 10''',
                (week_ago,)
            )
            crashes = c.fetchall()

            # Most crashed files
            c.execute(
                '''SELECT file_name, COUNT(*) as count
                   FROM crash_reports
                   GROUP BY file_name
                   ORDER BY count DESC
                   LIMIT 5'''
            )
            most_crashed = c.fetchall()

            # Total crashes
            c.execute('SELECT COUNT(*) FROM crash_reports')
            total = c.fetchone()[0]

            conn.close()

            msg = (
                f"💥 *Crash Report*\n"
                f"{DIVIDER}\n"
                f"📊 Total Crashes: `{total}`\n"
                f"📅 Last 7 days: `{len(crashes)}`\n\n"
            )

            if most_crashed:
                msg += f"🔥 *Most Crashed Files:*\n"
                for fname, count in most_crashed:
                    msg += f"• `{fname}`: {count} crashes\n"
                msg += "\n"

            if crashes:
                msg += f"📋 *Recent Crashes:*\n"
                for uid, fname, code, ctime, restarts in crashes:
                    time_str = ctime[11:16] if ctime else 'N/A'
                    msg += (
                        f"• `{fname}` (User:`{uid}`)\n"
                        f"  Code:{code} | {time_str} | "
                        f"Restarts:{restarts}\n"
                    )

            markup = owner_back_button('owner_analytics')
            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_report, daemon=True).start()


# ============================================================
# OWNER - FILE SYSTEM CONTROL
# ============================================================

def show_owner_filesystem(call):
    """Show file system control panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def do_fs():
        try:
            # Calculate sizes
            def dir_size(path):
                total = 0
                if os.path.exists(path):
                    for dp, dn, fn in os.walk(path):
                        for f in fn:
                            try:
                                total += os.path.getsize(
                                    os.path.join(dp, f)
                                )
                            except Exception:
                                pass
                return total

            upload_size = dir_size(UPLOAD_BOTS_DIR)
            versions_size = dir_size(VERSIONS_DIR)
            logs_size = dir_size(LOGS_DIR)
            backups_size = dir_size(BACKUP_DIR)
            temp_size = dir_size(TEMP_DIR)
            db_size = os.path.getsize(DATABASE_PATH)

            total_size = (
                upload_size + versions_size +
                logs_size + backups_size + db_size
            )

            # Count files per user
            user_count = 0
            if os.path.exists(UPLOAD_BOTS_DIR):
                user_count = len(os.listdir(UPLOAD_BOTS_DIR))

            msg = (
                f"📁 *File System Control*\n"
                f"{DIVIDER}\n"
                f"📊 *Storage Breakdown:*\n"
                f"┌─────────────────────\n"
                f"│ 📂 User Files: "
                f"`{format_size(upload_size)}`\n"
                f"│ 🔖 Versions: "
                f"`{format_size(versions_size)}`\n"
                f"│ 📋 Logs: "
                f"`{format_size(logs_size)}`\n"
                f"│ 💾 Backups: "
                f"`{format_size(backups_size)}`\n"
                f"│ 🗄️ Database: "
                f"`{format_size(db_size)}`\n"
                f"│ 📦 Temp: "
                f"`{format_size(temp_size)}`\n"
                f"├─────────────────────\n"
                f"│ 💾 Total: `{format_size(total_size)}`\n"
                f"└─────────────────────\n\n"
                f"👥 User Folders: `{user_count}`\n"
                f"{THIN_DIVIDER}\n"
                f"_Select an action:_"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "👁️ Browse Files",
                    callback_data='owner_file_browser'
                ),
                types.InlineKeyboardButton(
                    "📊 User Storage",
                    callback_data='owner_user_storage'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "🗑️ Clean Orphaned",
                    callback_data='owner_clean_orphaned'
                ),
                types.InlineKeyboardButton(
                    "🗑️ Clean Old Logs",
                    callback_data='owner_clean_logs'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "🗑️ Clean Versions",
                    callback_data='owner_clean_versions'
                ),
                types.InlineKeyboardButton(
                    "🗑️ Clean Backups",
                    callback_data='owner_clean_backups'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "✅ Integrity Check",
                    callback_data='owner_fs_integrity'
                ),
                types.InlineKeyboardButton(
                    "📦 Export All Files",
                    callback_data='owner_export_all_files'
                )
            )
            markup.add(types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='owner_panel'
            ))

            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_fs, daemon=True).start()


def handle_owner_user_storage(call):
    """Show storage usage per user"""
    bot.answer_callback_query(call.id, "📊 Calculating...")
    chat_id = call.message.chat.id

    def do_storage():
        try:
            storage_data = []

            if os.path.exists(UPLOAD_BOTS_DIR):
                for uid_folder in os.listdir(UPLOAD_BOTS_DIR):
                    folder_path = os.path.join(
                        UPLOAD_BOTS_DIR, uid_folder
                    )
                    if os.path.isdir(folder_path):
                        size = sum(
                            os.path.getsize(
                                os.path.join(dp, f)
                            )
                            for dp, dn, fn in os.walk(folder_path)
                            for f in fn
                        )
                        file_count = len([
                            f for f in os.listdir(folder_path)
                            if os.path.isfile(
                                os.path.join(folder_path, f)
                            )
                        ])
                        try:
                            uid = int(uid_folder)
                        except ValueError:
                            uid = uid_folder
                        storage_data.append((uid, size, file_count))

            # Sort by size
            storage_data.sort(key=lambda x: x[1], reverse=True)

            msg = (
                f"📊 *User Storage Report*\n"
                f"{DIVIDER}\n"
                f"👥 Total Folders: {len(storage_data)}\n\n"
                f"📋 *Top Users by Storage:*\n"
            )

            for uid, size, count in storage_data[:15]:
                status_icon = get_user_status_icon(uid) \
                    if isinstance(uid, int) else "👤"
                msg += (
                    f"• {status_icon} `{uid}`\n"
                    f"  📦 {format_size(size)} | "
                    f"📄 {count} files\n"
                )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data='owner_user_storage'
                ),
                types.InlineKeyboardButton(
                    f"{ICON_BACK} Back",
                    callback_data='owner_filesystem'
                )
            )

            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_storage, daemon=True).start()


def handle_owner_clean_orphaned(call):
    """Clean orphaned files (no DB record)"""
    bot.answer_callback_query(call.id, "🔍 Scanning...")
    chat_id = call.message.chat.id

    def do_clean():
        try:
            orphaned = []

            if os.path.exists(UPLOAD_BOTS_DIR):
                for uid_folder in os.listdir(UPLOAD_BOTS_DIR):
                    folder_path = os.path.join(
                        UPLOAD_BOTS_DIR, uid_folder
                    )
                    if not os.path.isdir(folder_path):
                        continue
                    try:
                        uid = int(uid_folder)
                    except ValueError:
                        continue

                    db_files = [
                        f[0] for f in
                        user_files.get(uid, [])
                    ]

                    for fname in os.listdir(folder_path):
                        if fname.endswith('.log'):
                            continue
                        fpath = os.path.join(folder_path, fname)
                        if (os.path.isfile(fpath) and
                                fname not in db_files):
                            orphaned.append((uid, fpath, fname))

            if not orphaned:
                bot.send_message(
                    chat_id,
                    f"✅ *No Orphaned Files*\n"
                    f"All files have DB records.",
                    parse_mode='Markdown'
                )
                return

            # Remove orphaned files
            removed = 0
            freed = 0
            for uid, fpath, fname in orphaned:
                try:
                    size = os.path.getsize(fpath)
                    os.remove(fpath)
                    removed += 1
                    freed += size
                except Exception:
                    pass

            log_audit(
                OWNER_ID, 'clean_orphaned',
                f"Removed {removed} orphaned files, "
                f"freed {format_size(freed)}"
            )

            bot.send_message(
                chat_id,
                f"✅ *Orphaned Files Cleaned*\n"
                f"{DIVIDER}\n"
                f"🗑️ Removed: `{removed}` files\n"
                f"💾 Freed: `{format_size(freed)}`",
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_clean, daemon=True).start()


def handle_owner_clean_logs(call):
    """Clean old log files"""
    bot.answer_callback_query(call.id, "🗑️ Cleaning logs...")
    chat_id = call.message.chat.id

    def do_clean():
        try:
            removed = 0
            freed = 0
            cutoff = datetime.now() - timedelta(days=7)

            # Clean bot logs
            if os.path.exists(LOGS_DIR):
                for fname in os.listdir(LOGS_DIR):
                    fpath = os.path.join(LOGS_DIR, fname)
                    if os.path.isfile(fpath):
                        mtime = datetime.fromtimestamp(
                            os.path.getmtime(fpath)
                        )
                        if mtime < cutoff:
                            size = os.path.getsize(fpath)
                            os.remove(fpath)
                            removed += 1
                            freed += size

            # Clean user script logs
            if os.path.exists(UPLOAD_BOTS_DIR):
                for uid_folder in os.listdir(UPLOAD_BOTS_DIR):
                    folder_path = os.path.join(
                        UPLOAD_BOTS_DIR, uid_folder
                    )
                    if os.path.isdir(folder_path):
                        for fname in os.listdir(folder_path):
                            if fname.endswith('.log'):
                                fpath = os.path.join(
                                    folder_path, fname
                                )
                                size = os.path.getsize(fpath)
                                # Truncate large logs instead of delete
                                if size > 5 * 1024 * 1024:
                                    with open(fpath, 'w') as f:
                                        f.write(
                                            f"[Log truncated by owner "
                                            f"on {datetime.now()}]\n"
                                        )
                                    freed += size - 100
                                    removed += 1

            bot.send_message(
                chat_id,
                f"✅ *Logs Cleaned*\n"
                f"{DIVIDER}\n"
                f"🗑️ Files: `{removed}`\n"
                f"💾 Freed: `{format_size(freed)}`",
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_clean, daemon=True).start()


def handle_owner_clean_versions(call):
    """Clean old file versions"""
    bot.answer_callback_query(call.id, "🗑️ Cleaning versions...")
    chat_id = call.message.chat.id

    def do_clean():
        try:
            removed = 0
            freed = 0

            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            # Get all file versions
            c.execute(
                '''SELECT id, user_id, file_name,
                   version_number, file_path
                   FROM file_versions
                   WHERE is_locked = 0
                   ORDER BY user_id, file_name,
                   version_number ASC'''
            )
            versions = c.fetchall()
            conn.close()

            # Group by user+file
            from itertools import groupby
            from operator import itemgetter

            sorted_versions = sorted(
                versions,
                key=lambda x: (x[1], x[2])
            )

            for (uid, fname), group in groupby(
                sorted_versions,
                key=lambda x: (x[1], x[2])
            ):
                ver_list = list(group)
                max_versions = get_config(
                    'free_version_limit',
                    FREE_VERSION_LIMIT
                )

                # Keep only latest N versions
                to_delete = ver_list[:-max_versions]

                for ver in to_delete:
                    ver_id, _, _, _, fpath = ver
                    if fpath and os.path.exists(fpath):
                        try:
                            size = os.path.getsize(fpath)
                            os.remove(fpath)
                            freed += size
                        except Exception:
                            pass

                    with DB_LOCK:
                        conn2 = sqlite3.connect(DATABASE_PATH)
                        c2 = conn2.cursor()
                        c2.execute(
                            'DELETE FROM file_versions WHERE id = ?',
                            (ver_id,)
                        )
                        conn2.commit()
                        conn2.close()
                    removed += 1

            bot.send_message(
                chat_id,
                f"✅ *Versions Cleaned*\n"
                f"{DIVIDER}\n"
                f"🗑️ Removed: `{removed}` old versions\n"
                f"💾 Freed: `{format_size(freed)}`",
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_clean, daemon=True).start()


def handle_owner_clean_backups(call):
    """Clean old database backups"""
    bot.answer_callback_query(call.id, "🗑️ Cleaning backups...")
    chat_id = call.message.chat.id

    def do_clean():
        try:
            backups = sorted([
                f for f in os.listdir(BACKUP_DIR)
                if f.endswith('.db')
            ])

            # Keep last 5 backups
            to_delete = backups[:-5] if len(backups) > 5 else []
            removed = 0
            freed = 0

            for backup in to_delete:
                bpath = os.path.join(BACKUP_DIR, backup)
                try:
                    size = os.path.getsize(bpath)
                    os.remove(bpath)
                    removed += 1
                    freed += size
                except Exception:
                    pass

            bot.send_message(
                chat_id,
                f"✅ *Backups Cleaned*\n"
                f"{DIVIDER}\n"
                f"🗑️ Removed: `{removed}` old backups\n"
                f"💾 Freed: `{format_size(freed)}`\n"
                f"💾 Kept: `{len(backups) - removed}` backups",
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_clean, daemon=True).start()


def handle_owner_fs_integrity(call):
    """Check file system integrity"""
    bot.answer_callback_query(
        call.id, "✅ Checking integrity..."
    )
    chat_id = call.message.chat.id

    def do_check():
        try:
            issues = []
            checked = 0

            # Check each user's files
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('SELECT user_id, file_name FROM user_files')
            db_files = c.fetchall()
            conn.close()

            for uid, fname in db_files:
                folder = get_user_folder(uid)
                fpath = os.path.join(folder, fname)
                checked += 1

                if not os.path.exists(fpath):
                    issues.append(
                        f"❌ Missing: `{fname}` (User:{uid})"
                    )

            # Check version files
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                'SELECT file_path, file_name FROM file_versions'
            )
            versions = c.fetchall()
            conn.close()

            for fpath, fname in versions:
                checked += 1
                if fpath and not os.path.exists(fpath):
                    issues.append(
                        f"⚠️ Missing version: `{fname}`"
                    )

            if not issues:
                status = "✅ *All Files Intact*"
                detail = f"Checked {checked} files. No issues found."
            else:
                status = f"⚠️ *{len(issues)} Issues Found*"
                detail = '\n'.join(issues[:20])
                if len(issues) > 20:
                    detail += f"\n_...and {len(issues)-20} more_"

            msg = (
                f"{status}\n"
                f"{DIVIDER}\n"
                f"📊 Checked: {checked} files\n\n"
                f"{detail}"
            )

            markup = owner_back_button('owner_filesystem')
            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_check, daemon=True).start()


# ============================================================
# OWNER - SCRIPT CONTROL CENTER
# ============================================================

def show_owner_script_control(call):
    """Show script control center"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    # Count running scripts
    running_scripts = []
    with BOT_SCRIPTS_LOCK:
        for key, info in bot_scripts.items():
            if is_bot_running(
                info['script_owner_id'],
                info['file_name']
            ):
                running_scripts.append(info)

    total_running = len(running_scripts)
    total_files = sum(len(v) for v in user_files.values())

    msg = (
        f"🔧 *Script Control Center*\n"
        f"{DIVIDER}\n"
        f"🟢 *Running:* `{total_running}`\n"
        f"📁 *Total Files:* `{total_files}`\n"
        f"👥 *Users with Files:* `{len(user_files)}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select an action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "📋 All Running Scripts",
            callback_data='owner_all_running'
        ),
        types.InlineKeyboardButton(
            "▶️ Start All Scripts",
            callback_data='owner_start_all'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "⏹️ Stop All Scripts",
            callback_data='owner_stop_all_scripts'
        ),
        types.InlineKeyboardButton(
            "🔄 Restart All",
            callback_data='owner_restart_all'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📺 Monitor All",
            callback_data='owner_monitor_scripts'
        ),
        types.InlineKeyboardButton(
            "⏰ All Schedules",
            callback_data='owner_all_schedules'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🚨 Emergency Stop",
            callback_data='owner_emergency_stop'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_all_running(call):
    """Show all currently running scripts"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    running = []
    with BOT_SCRIPTS_LOCK:
        for key, info in list(bot_scripts.items()):
            if is_bot_running(
                info['script_owner_id'],
                info['file_name']
            ):
                cpu, ram = get_script_resources(key)
                uptime = get_script_uptime(key)
                running.append({
                    'key': key,
                    'info': info,
                    'cpu': cpu,
                    'ram': ram,
                    'uptime': uptime
                })

    if not running:
        bot.send_message(
            chat_id,
            f"ℹ️ *No Scripts Running*\n"
            f"No scripts are currently active.",
            parse_mode='Markdown'
        )
        return

    msg = (
        f"🟢 *Running Scripts*\n"
        f"{DIVIDER}\n"
        f"Total: `{len(running)}`\n\n"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)

    for item in running:
        info = item['info']
        fname = info['file_name']
        uid = info['script_owner_id']
        ftype = info.get('type', 'py')
        uptime = item['uptime']
        cpu = item['cpu']
        ram_mb = item['ram']

        msg += (
            f"📜 `{fname}` ({ftype.upper()})\n"
            f"👤 User: `{uid}`\n"
            f"⏱️ {uptime} | "
            f"CPU:{cpu:.1f}% | "
            f"RAM:{ram_mb:.1f}MB\n\n"
        )

        markup.add(types.InlineKeyboardButton(
            f"🔴 Stop {fname[:20]} (User:{uid})",
            callback_data=f'stop_{uid}_{fname}'
        ))

    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_scripts'
    ))

    if len(msg) > 4000:
        msg = msg[:3900] + "\n\n_...more scripts_"

    bot.send_message(
        chat_id, msg,
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_start_all(call):
    """Start all stopped scripts for all users"""
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✅ Confirm Start All",
            callback_data='owner_confirm_start_all'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data='owner_scripts'
        )
    )

    stopped_count = sum(
        1 for uid, files in user_files.items()
        for fname, ftype in files
        if not is_bot_running(uid, fname)
    )

    bot.send_message(
        call.message.chat.id,
        f"▶️ *Start All Scripts*\n"
        f"{DIVIDER}\n"
        f"📊 Scripts to start: `{stopped_count}`\n\n"
        f"This will start ALL stopped scripts\n"
        f"for ALL users.\n\n"
        f"Are you sure?",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_confirm_start_all(call):
    """Execute start all scripts"""
    bot.answer_callback_query(call.id, "▶️ Starting all...")
    chat_id = call.message.chat.id

    def do_start_all():
        started = 0
        skipped = 0
        errors = 0

        for uid, files in list(user_files.items()):
            for fname, ftype in files:
                if is_bot_running(uid, fname):
                    skipped += 1
                    continue

                user_folder = get_user_folder(uid)
                fpath = os.path.join(user_folder, fname)

                if not os.path.exists(fpath):
                    errors += 1
                    continue

                try:
                    class FakeMsg:
                        class chat:
                            id = uid
                        class from_user:
                            id = uid

                    fake_msg = FakeMsg()

                    if ftype == 'py':
                        threading.Thread(
                            target=run_script,
                            args=(fpath, uid, user_folder,
                                  fname, fake_msg),
                            daemon=True
                        ).start()
                    elif ftype == 'js':
                        threading.Thread(
                            target=run_js_script,
                            args=(fpath, uid, user_folder,
                                  fname, fake_msg),
                            daemon=True
                        ).start()

                    started += 1
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(
                        f"Error starting {fname}: {e}"
                    )
                    errors += 1

        log_audit(
            OWNER_ID, 'start_all_scripts',
            f"Started {started} scripts",
            severity='warning'
        )

        bot.send_message(
            chat_id,
            f"✅ *Start All Complete*\n"
            f"{DIVIDER}\n"
            f"▶️ Started: `{started}`\n"
            f"⏭️ Already Running: `{skipped}`\n"
            f"❌ Errors: `{errors}`",
            parse_mode='Markdown'
        )

    threading.Thread(target=do_start_all, daemon=True).start()


def handle_owner_stop_all_scripts(call):
    """Stop all running scripts"""
    bot.answer_callback_query(call.id)

    running_count = len([
        k for k, v in bot_scripts.items()
        if is_bot_running(
            v['script_owner_id'],
            v['file_name']
        )
    ])

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✅ Confirm Stop All",
            callback_data='owner_confirm_emergency_stop'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data='owner_scripts'
        )
    )

    bot.send_message(
        call.message.chat.id,
        f"⏹️ *Stop All Scripts*\n"
        f"{DIVIDER}\n"
        f"🟢 Currently running: `{running_count}`\n\n"
        f"⚠️ This will stop ALL scripts!\n"
        f"Users will be notified.",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_owner_monitor_scripts(call):
    """Show script monitoring dashboard"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def do_monitor():
        running_data = []
        with BOT_SCRIPTS_LOCK:
            for key, info in list(bot_scripts.items()):
                if is_bot_running(
                    info['script_owner_id'],
                    info['file_name']
                ):
                    cpu, ram = get_script_resources(key)
                    uptime = get_script_uptime(key)
                    running_data.append({
                        'name': info['file_name'],
                        'uid': info['script_owner_id'],
                        'type': info.get('type', 'py'),
                        'cpu': cpu,
                        'ram': ram,
                        'uptime': uptime,
                        'pid': info['process'].pid
                        if info.get('process') else 'N/A'
                    })

        if not running_data:
            bot.send_message(
                chat_id,
                "ℹ️ No scripts running.",
                parse_mode='Markdown'
            )
            return

        msg = (
            f"📺 *Script Monitor Dashboard*\n"
            f"{DIVIDER}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
            f"🟢 Running: {len(running_data)}\n\n"
            f"```\n"
            f"{'Script':<15} {'CPU%':<8} "
            f"{'RAM MB':<10} {'Uptime'}\n"
            f"{'-'*45}\n"
        )

        for s in running_data:
            name = s['name'][:14]
            msg += (
                f"{name:<15} {s['cpu']:<8.1f}"
                f"{s['ram']:<10.1f} {s['uptime']}\n"
            )

        msg += "```"

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "🔄 Refresh",
                callback_data='owner_monitor_scripts'
            ),
            types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='owner_scripts'
            )
        )

        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    threading.Thread(target=do_monitor, daemon=True).start()


def handle_owner_all_schedules(call):
    """Show all schedules"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def do_schedules():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''SELECT id, user_id, file_name,
                   schedule_type, next_run_at, is_active
                   FROM schedules
                   ORDER BY next_run_at ASC'''
            )
            schedules = c.fetchall()
            conn.close()

            if not schedules:
                bot.send_message(
                    chat_id,
                    f"ℹ️ *No Schedules*\n"
                    f"No scripts are scheduled.",
                    parse_mode='Markdown'
                )
                return

            msg = (
                f"⏰ *All Schedules*\n"
                f"{DIVIDER}\n"
                f"Total: {len(schedules)}\n\n"
            )

            markup = types.InlineKeyboardMarkup(row_width=1)

            for sid, uid, fname, stype, next_run, active in schedules:
                status = "✅" if active else "❌"
                next_str = next_run[:16] if next_run else 'N/A'
                msg += (
                    f"{status} `{fname}` (User:{uid})\n"
                    f"  Type: {stype} | Next: {next_str}\n\n"
                )
                markup.add(types.InlineKeyboardButton(
                    f"{'✅' if active else '❌'} "
                    f"{fname[:20]} | User:{uid}",
                    callback_data=f'owner_toggle_schedule_{sid}'
                ))

            markup.add(types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='owner_scripts'
            ))

            if len(msg) > 4000:
                msg = msg[:3900] + "\n_...more_"

            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_schedules, daemon=True).start()


def handle_owner_toggle_schedule(call):
    """Toggle a schedule active/inactive"""
    schedule_id = int(
        call.data.replace('owner_toggle_schedule_', '')
    )
    bot.answer_callback_query(call.id)

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            'SELECT is_active FROM schedules WHERE id = ?',
            (schedule_id,)
        )
        row = c.fetchone()
        if row:
            new_state = 0 if row[0] else 1
            c.execute(
                'UPDATE schedules SET is_active = ? WHERE id = ?',
                (new_state, schedule_id)
            )
            conn.commit()
            state_text = "✅ Enabled" if new_state else "❌ Disabled"
            bot.send_message(
                call.message.chat.id,
                f"⏰ *Schedule {state_text}*\n"
                f"Schedule ID: {schedule_id}",
                parse_mode='Markdown'
            )
        conn.close()
    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error: {e}"
        )


# ============================================================
# OWNER - PAYMENT CONTROL
# ============================================================

def show_owner_payment(call):
    """Show payment control panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT COUNT(*) FROM payment_requests
               WHERE status = "pending"'''
        )
        pending = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM payment_requests')
        total = c.fetchone()[0]
        conn.close()
    except Exception:
        pending = 0
        total = 0

    msg = (
        f"💰 *Payment Control*\n"
        f"{DIVIDER}\n"
        f"⏳ *Pending Requests:* `{pending}`\n"
        f"📊 *Total Requests:* `{total}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select an action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            f"⏳ Pending ({pending})",
            callback_data='owner_pending_payments'
        ),
        types.InlineKeyboardButton(
            "📋 All Requests",
            callback_data='owner_all_payments'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📋 Edit Plans",
            callback_data='owner_edit_plans'
        ),
        types.InlineKeyboardButton(
            "💬 Edit Payment Info",
            callback_data='owner_edit_payment_info'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_pending_payments(call):
    """Show pending payment requests"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT id, user_id, plan_name,
               payment_method, requested_at
               FROM payment_requests
               WHERE status = "pending"
               ORDER BY requested_at DESC'''
        )
        requests = c.fetchall()
        conn.close()

        if not requests:
            bot.send_message(
                chat_id,
                f"✅ *No Pending Requests*\n"
                f"All payment requests processed.",
                parse_mode='Markdown'
            )
            return

        msg = (
            f"⏳ *Pending Payment Requests*\n"
            f"{DIVIDER}\n"
            f"Total: {len(requests)}\n\n"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)

        for req_id, uid, plan, method, req_at in requests:
            req_time = req_at[:10] if req_at else 'N/A'
            markup.add(types.InlineKeyboardButton(
                f"💰 {plan} | User:{uid} | {req_time}",
                callback_data=f'owner_process_payment_{req_id}'
            ))

        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='owner_payment'
        ))

        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")


def handle_owner_process_payment(call):
    """Process a payment request"""
    req_id = int(
        call.data.replace('owner_process_payment_', '')
    )
    bot.answer_callback_query(call.id)

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT user_id, plan_name, payment_method,
               requested_at, notes
               FROM payment_requests WHERE id = ?''',
            (req_id,)
        )
        req = c.fetchone()
        conn.close()

        if not req:
            bot.send_message(
                call.message.chat.id,
                "⚠️ Request not found.",
                parse_mode='Markdown'
            )
            return

        uid, plan, method, req_at, notes = req

        # Get plan config
        plans = get_config('plans', DEFAULT_CONFIG['plans'])
        plan_info = plans.get(plan, {})
        duration = plan_info.get('duration_days', 30)

        msg = (
            f"💰 *Payment Request #{req_id}*\n"
            f"{DIVIDER}\n"
            f"👤 User: `{uid}`\n"
            f"💳 Plan: `{plan.upper()}`\n"
            f"💰 Method: `{method}`\n"
            f"📅 Requested: {req_at[:10] if req_at else 'N/A'}\n"
            f"⏳ Duration: `{duration} days`\n"
            f"📝 Notes: {notes or 'None'}\n"
            f"{THIN_DIVIDER}\n"
            f"_Select action:_"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "✅ Approve",
                callback_data=f'approve_payment_{req_id}_{uid}_{plan}_{duration}'
            ),
            types.InlineKeyboardButton(
                "❌ Reject",
                callback_data=f'reject_payment_{req_id}_{uid}'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "💬 Message User",
                callback_data=f'owner_do_msg_{uid}'
            ),
            types.InlineKeyboardButton(
                "👤 View Profile",
                callback_data=f'owner_view_user_{uid}'
            )
        )
        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='owner_pending_payments'
        ))

        bot.send_message(
            call.message.chat.id,
            msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error: {e}"
        )


def handle_approve_payment(call):
    """Approve payment and activate subscription"""
    parts = call.data.split('_')
    # approve_payment_{req_id}_{uid}_{plan}_{duration}
    req_id = int(parts[2])
    uid = int(parts[3])
    plan = parts[4]
    duration = int(parts[5])

    bot.answer_callback_query(call.id, "✅ Approving...")

    try:
        # Activate subscription
        expiry = datetime.now() + timedelta(days=duration)
        save_subscription(uid, expiry, plan, OWNER_ID)

        # Update request status
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''UPDATE payment_requests
                   SET status = "approved",
                   processed_at = ?,
                   processed_by = ?
                   WHERE id = ?''',
                (datetime.now().isoformat(), OWNER_ID, req_id)
            )
            conn.commit()
            conn.close()

        # Notify user
        try:
            plan_icon = (
                ICON_DIAMOND if plan == 'vip' else ICON_STAR
            )
            bot.send_message(
                uid,
                f"🎉 *Payment Approved!*\n"
                f"{DIVIDER}\n"
                f"{plan_icon} *Plan:* {plan.upper()}\n"
                f"📅 *Expires:* {expiry.strftime('%Y-%m-%d')}\n"
                f"⏳ *Duration:* {duration} days\n"
                f"{THIN_DIVIDER}\n"
                f"_Thank you! Enjoy your subscription._",
                parse_mode='Markdown'
            )
        except Exception:
            pass

        log_audit(
            OWNER_ID, 'approve_payment',
            f"Approved {plan} for user {uid}",
            target_id=uid
        )

        bot.edit_message_text(
            f"✅ *Payment Approved*\n"
            f"{DIVIDER}\n"
            f"👤 User `{uid}` activated\n"
            f"💳 Plan: {plan.upper()} ({duration} days)\n"
            f"📅 Expires: {expiry.strftime('%Y-%m-%d')}",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error approving: {e}"
        )


def handle_reject_payment(call):
    """Reject payment request"""
    parts = call.data.split('_')
    req_id = int(parts[2])
    uid = int(parts[3])

    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"❌ *Reject Payment #{req_id}*\n"
        f"Enter rejection reason:",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_payment_rejection(m, req_id, uid)
    )


def process_payment_rejection(message, req_id, uid):
    """Process payment rejection"""
    reason = message.text.strip()

    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''UPDATE payment_requests
                   SET status = "rejected",
                   processed_at = ?,
                   processed_by = ?,
                   notes = ?
                   WHERE id = ?''',
                (datetime.now().isoformat(),
                 OWNER_ID, reason, req_id)
            )
            conn.commit()
            conn.close()

        try:
            bot.send_message(
                uid,
                f"❌ *Payment Rejected*\n"
                f"{DIVIDER}\n"
                f"📋 Reason: {reason}\n"
                f"{THIN_DIVIDER}\n"
                f"_Contact owner for more info._",
                parse_mode='Markdown'
            )
        except Exception:
            pass

        bot.reply_to(
            message,
            f"✅ *Payment #{req_id} Rejected*\n"
            f"User `{uid}` has been notified.",
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


def handle_owner_edit_plans(call):
    """Edit subscription plans"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    plans = get_config('plans', DEFAULT_CONFIG['plans'])

    plans_text = ""
    for plan_key, plan_info in plans.items():
        plans_text += (
            f"*{plan_info.get('name', plan_key)}*\n"
            f"  Duration: {plan_info.get('duration_days', 30)} days\n"
            f"  Price: {plan_info.get('price', 'N/A')}\n"
            f"  Limit: {plan_info.get('file_limit', 15)} files\n"
            f"  Features: {plan_info.get('features', 'N/A')}\n\n"
        )

    msg = bot.send_message(
        chat_id,
        f"📋 *Edit Subscription Plans*\n"
        f"{DIVIDER}\n"
        f"*Current Plans:*\n\n"
        f"{plans_text}"
        f"Send plan config in JSON format:\n"
        f"```\n"
        f'{{"premium": {{"name": "⭐ Premium", '
        f'"duration_days": 30, "price": "5$", '
        f'"file_limit": 15}}}}\n'
        f"```\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_edit_plans
    )


def process_edit_plans(message):
    """Process plan configuration update"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    try:
        new_plans = json.loads(message.text)
        current_plans = get_config('plans', {})
        current_plans.update(new_plans)
        set_config('plans', current_plans)

        bot.reply_to(
            message,
            f"✅ *Plans Updated*\n"
            f"Subscription plans saved successfully.",
            parse_mode='Markdown'
        )
        log_audit(OWNER_ID, 'edit_plans', 'Updated subscription plans')
    except json.JSONDecodeError as e:
        bot.reply_to(
            message,
            f"❌ *Invalid JSON*\n`{e}`",
            parse_mode='Markdown'
        )


def handle_owner_edit_payment_info(call):
    """Edit payment information"""
    bot.answer_callback_query(call.id)

    current = get_config(
        'payment_methods',
        'Contact owner for payment details'
    )

    msg = bot.send_message(
        call.message.chat.id,
        f"💬 *Edit Payment Information*\n"
        f"{DIVIDER}\n"
        f"*Current:*\n"
        f"```\n{current[:500]}\n```\n\n"
        f"Send new payment information:\n"
        f"_(Include methods, instructions, contact)_\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_edit_payment_info
    )


def process_edit_payment_info(message):
    """Process payment info update"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    set_config('payment_methods', message.text)
    bot.reply_to(
        message,
        f"✅ *Payment Info Updated*\n"
        f"Payment information saved.",
        parse_mode='Markdown'
    )


# ============================================================
# OWNER - NOTIFICATIONS CONTROL
# ============================================================

def show_owner_notifications(call):
    """Show notification settings"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def s(key, default=True):
        return (
            "✅ ON" if get_config(key, default) else "❌ OFF"
        )

    def btn(label, key, default=True):
        current = get_config(key, default)
        return types.InlineKeyboardButton(
            f"{'✅' if current else '❌'} {label}",
            callback_data=f'toggle_notif_{key}'
        )

    msg = (
        f"🔔 *Notification Control*\n"
        f"{DIVIDER}\n"
        f"*Owner Notifications:*\n"
        f"👤 New User: {s('notify_new_user')}\n"
        f"💥 Script Crash: {s('notify_script_crash')}\n"
        f"⚠️ System Alert: {s('notify_system_alert')}\n"
        f"💰 Payment Request: {s('notify_payment_request')}\n"
        f"🚫 Ban Attempt: {s('notify_ban_attempt')}\n"
        f"🛡️ Admin Action: {s('notify_admin_action')}\n\n"
        f"*Alert Thresholds:*\n"
        f"🖥️ CPU Alert: "
        f"`{get_config('cpu_alert_threshold', 90)}%`\n"
        f"🧠 RAM Alert: "
        f"`{get_config('ram_alert_threshold', 85)}%`\n"
        f"💾 Disk Alert: "
        f"`{get_config('disk_alert_threshold', 90)}%`\n\n"
        f"*Scheduled Reports:*\n"
        f"📅 Daily Report: {s('daily_report', False)}\n"
        f"📅 Weekly Report: {s('weekly_report', False)}\n"
        f"{THIN_DIVIDER}\n"
        f"_Toggle notifications:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        btn("New User", 'notify_new_user'),
        btn("Script Crash", 'notify_script_crash')
    )
    markup.row(
        btn("System Alert", 'notify_system_alert'),
        btn("Payment Req", 'notify_payment_request')
    )
    markup.row(
        btn("Ban Attempt", 'notify_ban_attempt'),
        btn("Admin Action", 'notify_admin_action')
    )
    markup.row(
        btn("Daily Report", 'daily_report', False),
        btn("Weekly Report", 'weekly_report', False)
    )
    markup.row(
        types.InlineKeyboardButton(
            "⚙️ Set Thresholds",
            callback_data='owner_set_thresholds'
        ),
        types.InlineKeyboardButton(
            "🔄 Refresh",
            callback_data='owner_notifications'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_toggle_notification(call):
    """Toggle a notification setting"""
    key = call.data.replace('toggle_notif_', '')
    current = get_config(key, True)
    new_val = not current
    set_config(key, new_val)

    state = "✅ ON" if new_val else "❌ OFF"
    bot.answer_callback_query(
        call.id,
        f"{key.replace('_', ' ').title()}: {state}"
    )
    show_owner_notifications(call)


def handle_owner_set_thresholds(call):
    """Set alert thresholds"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"⚙️ *Set Alert Thresholds*\n"
        f"{DIVIDER}\n"
        f"Current:\n"
        f"CPU: `{get_config('cpu_alert_threshold', 90)}%`\n"
        f"RAM: `{get_config('ram_alert_threshold', 85)}%`\n"
        f"Disk: `{get_config('disk_alert_threshold', 90)}%`\n\n"
        f"Send new values:\n"
        f"`CPU RAM DISK`\n"
        f"Example: `90 85 90`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_set_thresholds
    )


def process_set_thresholds(message):
    """Process threshold update"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.strip().split()
        if len(parts) != 3:
            raise ValueError("Need 3 values: CPU RAM DISK")
        cpu_t, ram_t, disk_t = [int(p) for p in parts]

        if not all(0 < v <= 100 for v in [cpu_t, ram_t, disk_t]):
            raise ValueError("Values must be 1-100")

        set_config('cpu_alert_threshold', cpu_t)
        set_config('ram_alert_threshold', ram_t)
        set_config('disk_alert_threshold', disk_t)

        bot.reply_to(
            message,
            f"✅ *Thresholds Updated*\n"
            f"🖥️ CPU: `{cpu_t}%`\n"
            f"🧠 RAM: `{ram_t}%`\n"
            f"💾 Disk: `{disk_t}%`",
            parse_mode='Markdown'
        )
    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}",
            parse_mode='Markdown'
        )


# ============================================================
# OWNER - AUDIT & LOGS CENTER
# ============================================================

def show_owner_audit(call):
    """Show audit and logs center"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM audit_logs')
        total_logs = c.fetchone()[0]
        c.execute(
            '''SELECT COUNT(*) FROM audit_logs
               WHERE severity = "critical"'''
        )
        critical_logs = c.fetchone()[0]
        conn.close()
    except Exception:
        total_logs = 0
        critical_logs = 0

    msg = (
        f"📜 *Audit & Logs Center*\n"
        f"{DIVIDER}\n"
        f"📊 Total Audit Logs: `{total_logs}`\n"
        f"🔴 Critical Events: `{critical_logs}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select a log type:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "📋 Action Logs",
            callback_data='owner_audit_action'
        ),
        types.InlineKeyboardButton(
            "🔴 Critical Logs",
            callback_data='owner_audit_critical'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🔒 Security Logs",
            callback_data='owner_audit_security'
        ),
        types.InlineKeyboardButton(
            "💻 Terminal Logs",
            callback_data='owner_audit_terminal'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📤 Export Logs",
            callback_data='owner_export_logs'
        ),
        types.InlineKeyboardButton(
            "🗑️ Clear Old Logs",
            callback_data='owner_clean_db'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📋 Bot System Logs",
            callback_data='owner_system_logs'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_audit_logs(call, severity=None):
    """Show audit logs filtered by severity"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    filter_map = {
        'owner_audit_action': None,
        'owner_audit_critical': 'critical',
        'owner_audit_security': 'warning',
        'owner_audit_terminal': None
    }

    action_filter = None
    if call.data == 'owner_audit_terminal':
        action_filter = 'terminal_command'

    severity_filter = filter_map.get(call.data)

    def do_fetch():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            if action_filter:
                c.execute(
                    '''SELECT user_id, action, details,
                       timestamp, severity
                       FROM audit_logs
                       WHERE action = ?
                       ORDER BY timestamp DESC LIMIT 30''',
                    (action_filter,)
                )
            elif severity_filter:
                c.execute(
                    '''SELECT user_id, action, details,
                       timestamp, severity
                       FROM audit_logs
                       WHERE severity = ?
                       ORDER BY timestamp DESC LIMIT 30''',
                    (severity_filter,)
                )
            else:
                c.execute(
                    '''SELECT user_id, action, details,
                       timestamp, severity
                       FROM audit_logs
                       ORDER BY timestamp DESC LIMIT 30'''
                )

            logs = c.fetchall()
            conn.close()

            log_type = call.data.replace('owner_audit_', '').title()
            msg = (
                f"📋 *{log_type} Logs*\n"
                f"{DIVIDER}\n"
                f"Showing last {len(logs)} entries:\n\n"
            )

            for uid, action, details, ts, sev in logs:
                sev_icon = {
                    'critical': '🔴',
                    'warning': '🟡',
                    'info': '🔵'
                }.get(sev, '⚪')

                time_str = ts[11:16] if ts else 'N/A'
                date_str = ts[:10] if ts else 'N/A'

                msg += (
                    f"{sev_icon} `{action}`\n"
                    f"👤 `{uid}` | 🕐 {date_str} {time_str}\n"
                    f"_{details[:60]}_\n\n"
                )

            if len(msg) > 4000:
                msg = msg[:3900] + "\n_...truncated_"

            markup = owner_back_button('owner_audit')
            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_fetch, daemon=True).start()


def handle_owner_export_logs(call):
    """Export audit logs as file"""
    bot.answer_callback_query(call.id, "📤 Exporting logs...")
    chat_id = call.message.chat.id

    def do_export():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''SELECT user_id, action, details,
                   target_id, timestamp, severity
                   FROM audit_logs
                   ORDER BY timestamp DESC'''
            )
            logs = c.fetchall()
            conn.close()

            import io
            output = io.StringIO()
            output.write(
                "user_id,action,details,"
                "target_id,timestamp,severity\n"
            )
            for log in logs:
                row = [
                    str(x or '').replace(',', ';')
                    for x in log
                ]
                output.write(','.join(row) + '\n')

            log_bytes = output.getvalue().encode('utf-8')
            log_file = io.BytesIO(log_bytes)
            log_file.name = (
                f"audit_logs_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            bot.send_document(
                chat_id,
                log_file,
                caption=(
                    f"📋 *Audit Logs Export*\n"
                    f"Total: {len(logs)} entries\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d')}"
                ),
                parse_mode='Markdown'
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Export error: {e}")

    threading.Thread(target=do_export, daemon=True).start()


def handle_owner_system_logs(call):
    """Show bot system log file"""
    bot.answer_callback_query(call.id, "📋 Loading system logs...")
    chat_id = call.message.chat.id

    try:
        log_file_path = os.path.join(
            LOGS_DIR,
            f"bot_{datetime.now().strftime('%Y%m%d')}.log"
        )

        if not os.path.exists(log_file_path):
            bot.send_message(
                chat_id,
                f"⚠️ No log file for today.",
                parse_mode='Markdown'
            )
            return

        file_size = os.path.getsize(log_file_path)

        if file_size > 50 * 1024 * 1024:
            bot.send_message(
                chat_id,
                f"❌ Log file too large: {format_size(file_size)}",
                parse_mode='Markdown'
            )
            return

        # Send last 100 lines as message
        with open(log_file_path, 'r',
                  encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        last_lines = ''.join(lines[-50:])
        if len(last_lines) > 3500:
            last_lines = last_lines[-3500:]

        msg = (
            f"📋 *System Logs (Last 50 lines)*\n"
            f"{DIVIDER}\n"
            f"📄 File: {format_size(file_size)}\n\n"
            f"```\n{last_lines}\n```"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "📥 Download Full Log",
                callback_data='owner_download_log'
            ),
            types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='owner_audit'
            )
        )

        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")


def handle_owner_download_log(call):
    """Download today's system log file"""
    bot.answer_callback_query(call.id, "📥 Sending log...")

    log_file_path = os.path.join(
        LOGS_DIR,
        f"bot_{datetime.now().strftime('%Y%m%d')}.log"
    )

    try:
        if not os.path.exists(log_file_path):
            bot.send_message(
                call.message.chat.id,
                "❌ Log file not found."
            )
            return

        with open(log_file_path, 'rb') as f:
            bot.send_document(
                call.message.chat.id,
                f,
                caption=(
                    f"📋 *System Log*\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d')}\n"
                    f"Size: {format_size(os.path.getsize(log_file_path))}"
                ),
                parse_mode='Markdown'
            )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error: {e}"
        )


# ============================================================
# OWNER - HEALTH & STATUS
# ============================================================

def show_owner_health(call):
    """Show health and status panel"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    uptime_24h = get_uptime_percentage(24)
    uptime_7d = get_uptime_percentage(168)
    bot_status = get_config('bot_status', 'operational')

    status_icons = {
        'operational': '🟢',
        'degraded': '🟡',
        'outage': '🔴'
    }
    status_icon = status_icons.get(bot_status, '🟡')

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT COUNT(*) FROM incidents
               WHERE status != "resolved"'''
        )
        active_incidents = c.fetchone()[0]
        conn.close()
    except Exception:
        active_incidents = 0

    msg = (
        f"🌐 *Health & Status*\n"
        f"{DIVIDER}\n"
        f"{status_icon} *Status:* "
        f"`{bot_status.upper()}`\n"
        f"⏱️ *Uptime (24h):* `{uptime_24h}%`\n"
        f"⏱️ *Uptime (7d):* `{uptime_7d}%`\n"
        f"🕐 *Bot Uptime:* `{format_uptime(BOT_START_TIME)}`\n"
        f"🚨 *Active Incidents:* `{active_incidents}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Select an action:_"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            f"{status_icon} Set Status",
            callback_data='owner_set_status'
        ),
        types.InlineKeyboardButton(
            "🚨 Create Incident",
            callback_data='owner_create_incident'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📋 View Incidents",
            callback_data='owner_view_incidents'
        ),
        types.InlineKeyboardButton(
            "📊 Uptime History",
            callback_data='owner_uptime_history'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📢 Notify Users",
            callback_data='owner_notify_status'
        ),
        types.InlineKeyboardButton(
            "🔄 Refresh",
            callback_data='owner_health'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_panel'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_owner_set_status(call):
    """Set bot status"""
    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "🟢 Operational",
            callback_data='set_status_operational'
        ),
        types.InlineKeyboardButton(
            "🟡 Degraded Performance",
            callback_data='set_status_degraded'
        ),
        types.InlineKeyboardButton(
            "🔴 Major Outage",
            callback_data='set_status_outage'
        ),
        types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='owner_health'
        )
    )

    bot.send_message(
        call.message.chat.id,
        f"🌐 *Set Bot Status*\n"
        f"{DIVIDER}\n"
        f"Select current status:",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_set_status(call):
    """Execute status change"""
    new_status = call.data.replace('set_status_', '')
    bot.answer_callback_query(call.id)

    set_config('bot_status', new_status)

    status_icons = {
        'operational': '🟢',
        'degraded': '🟡',
        'outage': '🔴'
    }
    icon = status_icons.get(new_status, '⚪')

    log_audit(
        OWNER_ID, 'set_status',
        f"Status changed to {new_status}",
        severity='warning'
    )

    bot.send_message(
        call.message.chat.id,
        f"{icon} *Status Updated*\n"
        f"Bot status: `{new_status.upper()}`",
        parse_mode='Markdown'
    )


def handle_owner_create_incident(call):
    """Create a new incident"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"🚨 *Create Incident*\n"
        f"{DIVIDER}\n"
        f"Send incident details:\n"
        f"`TITLE | DESCRIPTION | SEVERITY`\n\n"
        f"Severity: minor/major/critical\n\n"
        f"Example:\n"
        f"`Bot slowdown | High latency | minor`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_create_incident
    )


def process_create_incident(message):
    """Process incident creation"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    try:
        parts = [p.strip() for p in message.text.split('|')]
        if len(parts) < 2:
            raise ValueError(
                "Format: TITLE | DESCRIPTION | SEVERITY"
            )

        title = parts[0]
        description = parts[1]
        severity = parts[2] if len(parts) > 2 else 'minor'

        if severity not in ['minor', 'major', 'critical']:
            severity = 'minor'

        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''INSERT INTO incidents
                   (title, description, severity,
                    status, created_by)
                   VALUES (?, ?, ?, "investigating", ?)''',
                (title, description, severity, OWNER_ID)
            )
            inc_id = c.lastrowid
            conn.commit()
            conn.close()

        log_audit(
            OWNER_ID, 'create_incident',
            f"Created incident: {title}",
            severity='warning'
        )

        bot.reply_to(
            message,
            f"🚨 *Incident Created*\n"
            f"{DIVIDER}\n"
            f"🆔 ID: `{inc_id}`\n"
            f"📋 Title: {title}\n"
            f"⚡ Severity: `{severity}`\n"
            f"📊 Status: `investigating`",
            parse_mode='Markdown'
        )

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid format: {e}",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


def handle_owner_view_incidents(call):
    """View all incidents"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT id, title, severity, status,
               created_at, resolved_at
               FROM incidents
               ORDER BY created_at DESC
               LIMIT 20'''
        )
        incidents = c.fetchall()
        conn.close()

        if not incidents:
            bot.send_message(
                chat_id,
                f"✅ *No Incidents*\n"
                f"No incidents recorded.",
                parse_mode='Markdown'
            )
            return

        msg = (
            f"📋 *Incidents*\n"
            f"{DIVIDER}\n"
            f"Total: {len(incidents)}\n\n"
        )

        status_icons = {
            'investigating': '🔍',
            'identified': '🎯',
            'monitoring': '👁️',
            'resolved': '✅'
        }
        sev_icons = {
            'critical': '🔴',
            'major': '🟠',
            'minor': '🟡'
        }

        markup = types.InlineKeyboardMarkup(row_width=1)

        for inc_id, title, sev, status, created, resolved in incidents:
            s_icon = status_icons.get(status, '📋')
            sev_icon = sev_icons.get(sev, '⚪')
            date = created[:10] if created else 'N/A'

            msg += (
                f"{sev_icon} {s_icon} *{title}*\n"
                f"  {sev.upper()} | {status} | {date}\n\n"
            )

            if status != 'resolved':
                markup.add(types.InlineKeyboardButton(
                    f"✅ Resolve #{inc_id}: {title[:20]}",
                    callback_data=f'resolve_incident_{inc_id}'
                ))

        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='owner_health'
        ))

        if len(msg) > 4000:
            msg = msg[:3900] + "\n_...more_"

        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")


def handle_resolve_incident(call):
    """Resolve an incident"""
    inc_id = int(call.data.replace('resolve_incident_', ''))
    bot.answer_callback_query(call.id, "✅ Resolving...")

    try:
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''UPDATE incidents
                   SET status = "resolved",
                   resolved_at = ?
                   WHERE id = ?''',
                (datetime.now().isoformat(), inc_id)
            )
            conn.commit()
            conn.close()

        log_audit(
            OWNER_ID, 'resolve_incident',
            f"Resolved incident #{inc_id}"
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ *Incident #{inc_id} Resolved*\n"
            f"Status updated to resolved.",
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Error: {e}"
        )


def handle_owner_uptime_history(call):
    """Show uptime history"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    def do_history():
        try:
            uptime_1h = get_uptime_percentage(1)
            uptime_24h = get_uptime_percentage(24)
            uptime_7d = get_uptime_percentage(168)
            uptime_30d = get_uptime_percentage(720)

            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            # Get daily uptime for last 7 days
            daily_uptimes = []
            for i in range(7):
                day = datetime.now() - timedelta(days=i)
                day_start = day.replace(
                    hour=0, minute=0, second=0
                ).isoformat()
                day_end = day.replace(
                    hour=23, minute=59, second=59
                ).isoformat()
                c.execute(
                    '''SELECT COUNT(*),
                       SUM(CASE WHEN status="online"
                           THEN 1 ELSE 0 END)
                       FROM uptime_logs
                       WHERE timestamp BETWEEN ? AND ?''',
                    (day_start, day_end)
                )
                total, online = c.fetchone()
                pct = (
                    round((online / total) * 100, 1)
                    if total and total > 0 else 100.0
                )
                day_str = day.strftime('%m/%d')
                daily_uptimes.append((day_str, pct))

            conn.close()

            # Build chart
            chart = ""
            for day_str, pct in reversed(daily_uptimes):
                bar_len = int(pct / 10)
                bar = "█" * bar_len + "░" * (10 - bar_len)
                icon = (
                    "🟢" if pct >= 99
                    else "🟡" if pct >= 95
                    else "🔴"
                )
                chart += (
                    f"{icon} {day_str} [{bar}] {pct}%\n"
                )

            msg = (
                f"📈 *Uptime History*\n"
                f"{DIVIDER}\n"
                f"⏱️ Last 1h: `{uptime_1h}%`\n"
                f"⏱️ Last 24h: `{uptime_24h}%`\n"
                f"⏱️ Last 7d: `{uptime_7d}%`\n"
                f"⏱️ Last 30d: `{uptime_30d}%`\n\n"
                f"📅 *Daily Breakdown:*\n"
                f"```\n{chart}```"
            )

            markup = owner_back_button('owner_health')
            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_history, daemon=True).start()


def handle_owner_notify_status(call):
    """Notify all users of current bot status"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"📢 *Notify Users of Status*\n"
        f"{DIVIDER}\n"
        f"Enter status message to send:\n"
        f"_(Leave blank for auto-message)_\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_notify_status
    )


def process_notify_status(message):
    """Process status notification"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    bot_status = get_config('bot_status', 'operational')
    status_icons = {
        'operational': '🟢',
        'degraded': '🟡',
        'outage': '🔴'
    }
    icon = status_icons.get(bot_status, '⚪')

    if message.text.strip():
        notify_text = message.text
    else:
        notify_text = (
            f"{icon} *Bot Status Update*\n"
            f"Current status: `{bot_status.upper()}`"
        )

    def do_notify():
        sent = 0
        for uid in list(active_users):
            try:
                bot.send_message(
                    uid,
                    f"📢 *Bot Status Notification*\n"
                    f"{DIVIDER}\n"
                    f"{notify_text}",
                    parse_mode='Markdown'
                )
                sent += 1
                time.sleep(0.05)
            except Exception:
                pass

        bot.send_message(
            message.chat.id,
            f"✅ *Notification Sent*\n"
            f"Notified {sent}/{len(active_users)} users.",
            parse_mode='Markdown'
        )

    threading.Thread(target=do_notify, daemon=True).start()


# ============================================================
# SUBSCRIPTION PLAN CONFIG
# ============================================================

def show_owner_config_plans(call):
    """Show subscription plan configuration"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    plans = get_config('plans', DEFAULT_CONFIG['plans'])

    msg = (
        f"📋 *Subscription Plans*\n"
        f"{DIVIDER}\n"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)

    for plan_key, plan_info in plans.items():
        plan_name = plan_info.get('name', plan_key)
        duration = plan_info.get('duration_days', 30)
        price = plan_info.get('price', 'N/A')
        limit = plan_info.get('file_limit', 15)
        features = plan_info.get('features', 'N/A')

        msg += (
            f"*{plan_name}*\n"
            f"┌─────────────────────\n"
            f"│ ⏳ Duration: {duration} days\n"
            f"│ 💰 Price: {price}\n"
            f"│ 📁 File Limit: {limit}\n"
            f"│ ✨ {features}\n"
            f"└─────────────────────\n\n"
        )

        markup.add(types.InlineKeyboardButton(
            f"✏️ Edit {plan_name}",
            callback_data=f'edit_plan_{plan_key}'
        ))

    markup.row(
        types.InlineKeyboardButton(
            "➕ Add New Plan",
            callback_data='add_new_plan'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='owner_config'
    ))

    try:
        bot.edit_message_text(
            msg, chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )


def handle_edit_plan(call):
    """Edit a specific plan"""
    plan_key = call.data.replace('edit_plan_', '')
    bot.answer_callback_query(call.id)

    plans = get_config('plans', DEFAULT_CONFIG['plans'])
    plan = plans.get(plan_key, {})

    msg = bot.send_message(
        call.message.chat.id,
        f"✏️ *Edit Plan: {plan_key.upper()}*\n"
        f"{DIVIDER}\n"
        f"Current values:\n"
        f"Name: `{plan.get('name', plan_key)}`\n"
        f"Duration: `{plan.get('duration_days', 30)}` days\n"
        f"Price: `{plan.get('price', 'N/A')}`\n"
        f"File Limit: `{plan.get('file_limit', 15)}`\n"
        f"Features: `{plan.get('features', 'N/A')}`\n\n"
        f"Send new values:\n"
        f"`NAME | DAYS | PRICE | FILE_LIMIT | FEATURES`\n\n"
        f"Example:\n"
        f"`⭐ Premium | 30 | 5$ | 15 | Priority support`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_plan_edit(m, plan_key)
    )


def process_plan_edit(message, plan_key):
    """Process plan edit"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    try:
        parts = [p.strip() for p in message.text.split('|')]
        if len(parts) < 4:
            raise ValueError(
                "Need: NAME | DAYS | PRICE | LIMIT | FEATURES"
            )

        plans = get_config('plans', DEFAULT_CONFIG['plans'])
        plans[plan_key] = {
            'name': parts[0],
            'duration_days': int(parts[1]),
            'price': parts[2],
            'file_limit': int(parts[3]),
            'features': parts[4] if len(parts) > 4 else 'Standard'
        }
        set_config('plans', plans)

        bot.reply_to(
            message,
            f"✅ *Plan Updated: {plan_key.upper()}*\n"
            f"Changes saved successfully.",
            parse_mode='Markdown'
        )
        log_audit(OWNER_ID, 'edit_plan', f"Updated plan: {plan_key}")

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}",
            parse_mode='Markdown'
        )


def handle_add_new_plan(call):
    """Add a completely new plan"""
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"➕ *Add New Plan*\n"
        f"{DIVIDER}\n"
        f"Send plan details:\n"
        f"`KEY | NAME | DAYS | PRICE | LIMIT | FEATURES`\n\n"
        f"Example:\n"
        f"`gold | 🥇 Gold | 60 | 10$ | 30 | All features`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg, process_add_new_plan
    )


def process_add_new_plan(message):
    """Process new plan addition"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    try:
        parts = [p.strip() for p in message.text.split('|')]
        if len(parts) < 5:
            raise ValueError("Need all 6 fields")

        plan_key = parts[0].lower().replace(' ', '_')
        plans = get_config('plans', DEFAULT_CONFIG['plans'])

        if plan_key in plans:
            bot.reply_to(
                message,
                f"⚠️ Plan `{plan_key}` already exists.\n"
                f"Use edit to modify it.",
                parse_mode='Markdown'
            )
            return

        plans[plan_key] = {
            'name': parts[1],
            'duration_days': int(parts[2]),
            'price': parts[3],
            'file_limit': int(parts[4]),
            'features': parts[5] if len(parts) > 5 else 'Standard'
        }
        set_config('plans', plans)

        bot.reply_to(
            message,
            f"✅ *New Plan Added: {plan_key.upper()}*\n"
            f"Plan saved successfully.",
            parse_mode='Markdown'
        )
        log_audit(OWNER_ID, 'add_plan', f"Added plan: {plan_key}")

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}",
            parse_mode='Markdown'
        )


# ============================================================
# END OF CHUNK 7
# ============================================================
# ============================================================
# CHUNK 8: User Features
# ============================================================
# PASTE THIS AFTER CHUNK 7
# ============================================================

# ============================================================
# USER PROFILE PANEL
# ============================================================

def show_user_profile(message_or_call):
    """Show user's own profile"""
    if isinstance(message_or_call, types.Message):
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.chat.id
        first_name = message_or_call.from_user.first_name
        username = message_or_call.from_user.username
    else:
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.message.chat.id
        first_name = message_or_call.from_user.first_name
        username = message_or_call.from_user.username
        bot.answer_callback_query(message_or_call.id)

    def do_profile():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''SELECT first_seen, last_active,
                   total_uploads, total_scripts_run,
                   total_run_time_seconds, storage_used_bytes,
                   notify_crash, notify_start,
                   notify_stop, notify_sub_expiry
                   FROM user_profiles WHERE user_id = ?''',
                (user_id,)
            )
            profile = c.fetchone()
            conn.close()

            status_text = get_user_status_text(user_id)
            status_icon = get_user_status_icon(user_id)
            file_limit = get_user_file_limit(user_id)
            file_count = get_user_file_count(user_id)
            limit_str = (
                str(file_limit)
                if file_limit != float('inf')
                else "∞"
            )

            # Running scripts
            running = sum(
                1 for k, v in bot_scripts.items()
                if v.get('script_owner_id') == user_id
                and is_bot_running(user_id, v['file_name'])
            )

            # Subscription info
            sub_text = ""
            if user_id in user_subscriptions:
                sub = user_subscriptions[user_id]
                expiry = sub.get('expiry')
                plan = sub.get('plan', 'premium')
                if expiry and expiry > datetime.now():
                    days_left = (expiry - datetime.now()).days
                    sub_text = (
                        f"\n💳 *Subscription*\n"
                        f"┌─────────────────────\n"
                        f"│ 🏷️ Plan: {plan.upper()}\n"
                        f"│ ⏳ Expires in: {days_left} days\n"
                        f"│ 📅 Date: {expiry.strftime('%Y-%m-%d')}\n"
                        f"└─────────────────────"
                    )

            # Profile data
            if profile:
                first_seen = profile[0][:10] if profile[0] else 'N/A'
                last_active = profile[1][:10] if profile[1] else 'N/A'
                total_uploads = profile[2] or 0
                total_runs = profile[3] or 0
                run_time = profile[4] or 0
                storage = profile[5] or 0
                run_hours = run_time // 3600
                run_mins = (run_time % 3600) // 60
            else:
                first_seen = last_active = 'N/A'
                total_uploads = total_runs = 0
                run_hours = run_mins = 0
                storage = 0

            msg = (
                f"👤 *My Profile*\n"
                f"{DIVIDER}\n"
                f"{make_user_card(user_id, first_name, username, status_text, file_count, limit_str)}\n\n"
                f"📊 *My Statistics*\n"
                f"┌─────────────────────\n"
                f"│ 📅 Member Since: {first_seen}\n"
                f"│ 🕐 Last Active: {last_active}\n"
                f"│ 📤 Total Uploads: {total_uploads}\n"
                f"│ 🚀 Scripts Run: {total_runs}\n"
                f"│ ⏱️ Run Time: {run_hours}h {run_mins}m\n"
                f"│ 💾 Storage: {format_size(storage)}\n"
                f"│ 🟢 Running Now: {running}\n"
                f"└─────────────────────"
                f"{sub_text}"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "🔔 Notifications",
                    callback_data='user_notifications'
                ),
                types.InlineKeyboardButton(
                    "🔑 Env Variables",
                    callback_data='user_env_vars'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "📂 My Files",
                    callback_data='check_files'
                ),
                types.InlineKeyboardButton(
                    "💳 Premium Info",
                    callback_data='premium_info'
                )
            )
            markup.add(types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='back_to_main'
            ))

            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            logger.error(f"Profile error: {e}", exc_info=True)
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_profile, daemon=True).start()


def show_user_notifications(call):
    """Show user notification preferences"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT notify_crash, notify_start,
               notify_stop, notify_sub_expiry,
               notify_announcements
               FROM user_profiles WHERE user_id = ?''',
            (user_id,)
        )
        prefs = c.fetchone()
        conn.close()

        if prefs:
            n_crash, n_start, n_stop, n_expiry, n_ann = prefs
        else:
            n_crash = n_start = n_stop = n_expiry = n_ann = 1

        def s(val):
            return "✅" if val else "❌"

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                f"{s(n_crash)} Script Crash Alert",
                callback_data='toggle_user_notif_notify_crash'
            ),
            types.InlineKeyboardButton(
                f"{s(n_start)} Script Started",
                callback_data='toggle_user_notif_notify_start'
            ),
            types.InlineKeyboardButton(
                f"{s(n_stop)} Script Stopped",
                callback_data='toggle_user_notif_notify_stop'
            ),
            types.InlineKeyboardButton(
                f"{s(n_expiry)} Subscription Expiry",
                callback_data='toggle_user_notif_notify_sub_expiry'
            ),
            types.InlineKeyboardButton(
                f"{s(n_ann)} Announcements",
                callback_data='toggle_user_notif_notify_announcements'
            )
        )
        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='user_profile'
        ))

        bot.send_message(
            chat_id,
            f"🔔 *Notification Settings*\n"
            f"{DIVIDER}\n"
            f"Toggle your notifications:\n"
            f"_(✅ = On | ❌ = Off)_",
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")


def handle_toggle_user_notif(call):
    """Toggle user notification preference"""
    key = call.data.replace('toggle_user_notif_', '')
    user_id = call.from_user.id

    valid_keys = [
        'notify_crash', 'notify_start', 'notify_stop',
        'notify_sub_expiry', 'notify_announcements'
    ]
    if key not in valid_keys:
        bot.answer_callback_query(call.id, "⚠️ Invalid.")
        return

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            f'SELECT {key} FROM user_profiles WHERE user_id = ?',
            (user_id,)
        )
        row = c.fetchone()
        current = row[0] if row else 1
        new_val = 0 if current else 1
        c.execute(
            f'UPDATE user_profiles SET {key} = ? WHERE user_id = ?',
            (new_val, user_id)
        )
        conn.commit()
        conn.close()

        state = "✅ ON" if new_val else "❌ OFF"
        bot.answer_callback_query(
            call.id,
            f"{key.replace('_', ' ').title()}: {state}"
        )
        show_user_notifications(call)

    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {e}")


# ============================================================
# HELP SYSTEM
# ============================================================

def show_help_panel(message_or_call):
    """Show help center"""
    if isinstance(message_or_call, types.Message):
        chat_id = message_or_call.chat.id
        send = lambda t, **kw: bot.send_message(chat_id, t, **kw)
    else:
        chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        send = lambda t, **kw: bot.send_message(chat_id, t, **kw)

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🚀 Getting Started",
            callback_data='help_start'
        ),
        types.InlineKeyboardButton(
            "📁 File Management",
            callback_data='help_files'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🤖 Script Guide",
            callback_data='help_scripts'
        ),
        types.InlineKeyboardButton(
            "💳 Premium & Plans",
            callback_data='help_premium'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "🔑 Env Variables",
            callback_data='help_env'
        ),
        types.InlineKeyboardButton(
            "⏰ Scheduler",
            callback_data='help_scheduler'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "❓ FAQ",
            callback_data='help_faq'
        ),
        types.InlineKeyboardButton(
            "📞 Support",
            callback_data='help_support'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='back_to_main'
    ))

    send(
        f"❓ *Help Center*\n"
        f"{DIVIDER}\n"
        f"Welcome! Select a topic below:\n\n"
        f"🚀 Getting Started - New users guide\n"
        f"📁 Files - Upload & manage scripts\n"
        f"🤖 Scripts - Run Python & JS bots\n"
        f"💳 Premium - Plans & benefits\n"
        f"🔑 Env Vars - Environment variables\n"
        f"⏰ Scheduler - Schedule scripts\n"
        f"❓ FAQ - Common questions\n"
        f"📞 Support - Contact owner",
        parse_mode='Markdown',
        reply_markup=markup
    )


HELP_TEXTS = {
    'help_start': (
        f"🚀 *Getting Started*\n"
        f"{DIVIDER}\n"
        f"*Step 1:* Send /start\n"
        f"*Step 2:* Upload your script\n"
        f"  • Python (.py) files\n"
        f"  • JavaScript (.js) files\n"
        f"  • ZIP archives\n"
        f"*Step 3:* Bot auto-runs your script\n"
        f"*Step 4:* Manage via buttons\n\n"
        f"💡 *Tips:*\n"
        f"• Include requirements.txt in ZIP\n"
        f"• Use env variables for API keys\n"
        f"• Check logs if script fails\n"
        f"• Auto-restart on crash is enabled"
    ),
    'help_files': (
        f"📁 *File Management*\n"
        f"{DIVIDER}\n"
        f"*Upload:*\n"
        f"• Send .py, .js, or .zip file\n"
        f"• Max size: 20MB\n"
        f"• Bot auto-detects main script\n\n"
        f"*Manage:*\n"
        f"• 📂 My Files - View all files\n"
        f"• 🟢 Start - Run script\n"
        f"• 🔴 Stop - Stop script\n"
        f"• 🔄 Restart - Restart script\n"
        f"• 📜 Logs - View output logs\n"
        f"• 📺 Live Logs - Real-time logs\n"
        f"• 🗑️ Delete - Remove file\n"
        f"• 🔖 Versions - File history\n\n"
        f"*Limits:*\n"
        f"• 🆓 Free: 10 files\n"
        f"• ⭐ Premium: 15 files\n"
        f"• 💎 VIP: 50 files"
    ),
    'help_scripts': (
        f"🤖 *Script Guide*\n"
        f"{DIVIDER}\n"
        f"*Python Scripts:*\n"
        f"• Upload .py file directly\n"
        f"• Missing packages auto-install\n"
        f"• Uses your env variables\n"
        f"• Logs saved automatically\n\n"
        f"*JavaScript Scripts:*\n"
        f"• Upload .js file directly\n"
        f"• npm packages auto-install\n"
        f"• Node.js required on server\n\n"
        f"*ZIP Archives:*\n"
        f"• Include main.py or index.js\n"
        f"• Include requirements.txt\n"
        f"• Include package.json\n"
        f"• Bot finds & runs main script\n\n"
        f"*Auto Features:*\n"
        f"• 🔄 Auto-restart on crash\n"
        f"• 📦 Auto-install packages\n"
        f"• 🔑 Env variable injection\n"
        f"• 📜 Automatic log files"
    ),
    'help_premium': (
        f"💳 *Premium & Plans*\n"
        f"{DIVIDER}\n"
        f"*Free Plan:*\n"
        f"• 10 file slots\n"
        f"• Basic features\n"
        f"• Standard support\n\n"
        f"*⭐ Premium Plan:*\n"
        f"• 15 file slots\n"
        f"• Priority support\n"
        f"• Advanced logs\n"
        f"• Version control (10 versions)\n\n"
        f"*💎 VIP Plan:*\n"
        f"• 50 file slots\n"
        f"• All features\n"
        f"• Maximum version history\n"
        f"• Highest priority\n\n"
        f"*How to Subscribe:*\n"
        f"1. Click 💳 Premium Info\n"
        f"2. Select a plan\n"
        f"3. Contact owner to pay\n"
        f"4. Get activated instantly"
    ),
    'help_env': (
        f"🔑 *Environment Variables*\n"
        f"{DIVIDER}\n"
        f"Store sensitive data securely!\n\n"
        f"*What are they?*\n"
        f"Key-value pairs injected into\n"
        f"your script when it runs.\n\n"
        f"*Example:*\n"
        f"Instead of hardcoding:\n"
        f"`TOKEN = 'abc123'`\n\n"
        f"Use in script:\n"
        f"`TOKEN = os.environ.get('TOKEN')`\n\n"
        f"Set in bot:\n"
        f"`TOKEN = abc123`\n\n"
        f"*Features:*\n"
        f"• 🔒 Encrypted storage\n"
        f"• 👁️ Values masked in display\n"
        f"• 🌐 Global or per-script\n"
        f"• 📥 Import from .env file\n"
        f"• ✏️ Easy add/edit/delete"
    ),
    'help_scheduler': (
        f"⏰ *Script Scheduler*\n"
        f"{DIVIDER}\n"
        f"Schedule your scripts to run\n"
        f"automatically at set times!\n\n"
        f"*Schedule Types:*\n"
        f"• 🕐 Once - Run at specific time\n"
        f"• 🔁 Interval - Every X minutes\n"
        f"• 📅 Daily - Every day at time\n"
        f"• 📅 Weekly - On specific days\n\n"
        f"*How to use:*\n"
        f"1. Go to 📂 My Files\n"
        f"2. Select a script\n"
        f"3. Click ⏰ Schedule\n"
        f"4. Choose schedule type\n"
        f"5. Set the time/interval\n\n"
        f"*Note:*\n"
        f"Script will auto-start at\n"
        f"scheduled time even if stopped."
    ),
    'help_faq': (
        f"❓ *Frequently Asked Questions*\n"
        f"{DIVIDER}\n"
        f"*Q: My script won't start?*\n"
        f"A: Check logs for errors.\n"
        f"Missing packages auto-install.\n\n"
        f"*Q: Script keeps crashing?*\n"
        f"A: Check your script for bugs.\n"
        f"View crash report in logs.\n\n"
        f"*Q: How to use API keys?*\n"
        f"A: Use environment variables.\n"
        f"Never hardcode sensitive data.\n\n"
        f"*Q: What files can I upload?*\n"
        f"A: .py, .js, and .zip files.\n"
        f"Max 20MB per file.\n\n"
        f"*Q: How to update my script?*\n"
        f"A: Upload same filename.\n"
        f"Old version auto-archived.\n\n"
        f"*Q: Can I run multiple scripts?*\n"
        f"A: Yes! Up to your file limit."
    ),
    'help_support': (
        f"📞 *Support*\n"
        f"{DIVIDER}\n"
        f"Need help? Contact us!\n\n"
        f"*Support Options:*\n"
        f"• 💬 Owner: {YOUR_USERNAME}\n"
        f"• 📢 Updates: {UPDATE_CHANNEL}\n\n"
        f"*Before contacting:*\n"
        f"✅ Check FAQ section\n"
        f"✅ View script logs\n"
        f"✅ Try restarting script\n"
        f"✅ Check env variables\n\n"
        f"*When contacting include:*\n"
        f"• Your User ID\n"
        f"• Script name\n"
        f"• Error message/logs\n"
        f"• What you expected"
    )
}


def show_help_topic(call):
    """Show specific help topic"""
    bot.answer_callback_query(call.id)
    topic = call.data
    text = HELP_TEXTS.get(topic, "❓ Topic not found.")

    markup = types.InlineKeyboardMarkup(row_width=2)
    if topic == 'help_support':
        markup.add(types.InlineKeyboardButton(
            "💬 Contact Owner",
            url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"
        ))
        markup.add(types.InlineKeyboardButton(
            "📢 Updates Channel",
            url=UPDATE_CHANNEL
        ))
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back to Help",
        callback_data='help_center'
    ))

    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode='Markdown',
        reply_markup=markup
    )


# ============================================================
# ENVIRONMENT VARIABLES MANAGER
# ============================================================

def show_env_manager(message_or_call):
    """Show environment variables manager"""
    if isinstance(message_or_call, types.Message):
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.chat.id
    else:
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)

    def do_show():
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''SELECT env_key, env_value, is_secret,
                   script_name, updated_at
                   FROM env_variables
                   WHERE user_id = ?
                   ORDER BY script_name, env_key''',
                (user_id,)
            )
            vars_list = c.fetchall()
            conn.close()

            msg = (
                f"🔑 *Environment Variables*\n"
                f"{DIVIDER}\n"
                f"Total: `{len(vars_list)}` variables\n\n"
            )

            if vars_list:
                current_scope = None
                for key, val, is_secret, scope, updated in vars_list:
                    if scope != current_scope:
                        current_scope = scope
                        msg += f"\n📌 *Scope: {scope}*\n"

                    display_val = (
                        "••••••••"
                        if is_secret
                        else mask_value(
                            decrypt_value(val), 4
                        )
                    )
                    msg += (
                        f"• `{key}` = `{display_val}`"
                        f"{'🔒' if is_secret else ''}\n"
                    )
            else:
                msg += "_No variables set yet._\n"

            msg += (
                f"\n{THIN_DIVIDER}\n"
                f"_Select an action:_"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "➕ Add Variable",
                    callback_data='env_add'
                ),
                types.InlineKeyboardButton(
                    "🗑️ Delete Variable",
                    callback_data='env_delete'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "📥 Import .env File",
                    callback_data='env_import'
                ),
                types.InlineKeyboardButton(
                    "📤 Export Variables",
                    callback_data='env_export'
                )
            )
            markup.row(
                types.InlineKeyboardButton(
                    "👁️ View All (Unmasked)",
                    callback_data='env_view_all'
                ),
                types.InlineKeyboardButton(
                    "🗑️ Clear All",
                    callback_data='env_clear_all'
                )
            )
            markup.add(types.InlineKeyboardButton(
                f"{ICON_BACK} Back",
                callback_data='user_profile'
            ))

            if len(msg) > 4000:
                msg = msg[:3900] + "\n_...more_"

            bot.send_message(
                chat_id, msg,
                parse_mode='Markdown',
                reply_markup=markup
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}")

    threading.Thread(target=do_show, daemon=True).start()


def handle_env_add(call):
    """Add environment variable"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    # Get user's script names
    scripts = [f[0] for f in user_files.get(user_id, [])]

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "🌐 Global (all scripts)",
        callback_data='env_scope_global'
    ))
    for script in scripts[:10]:
        markup.add(types.InlineKeyboardButton(
            f"📜 {script}",
            callback_data=f'env_scope_{script}'
        ))
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='user_env_vars'
    ))

    bot.send_message(
        call.message.chat.id,
        f"➕ *Add Environment Variable*\n"
        f"{DIVIDER}\n"
        f"Select scope:\n"
        f"• Global = applies to all scripts\n"
        f"• Script = applies to one script",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_env_scope_select(call):
    """Handle scope selection for env var"""
    scope = call.data.replace('env_scope_', '')
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    msg = bot.send_message(
        call.message.chat.id,
        f"➕ *Add Variable*\n"
        f"{DIVIDER}\n"
        f"Scope: `{scope}`\n\n"
        f"Send in format:\n"
        f"`KEY=VALUE`\n\n"
        f"Examples:\n"
        f"`BOT_TOKEN=1234567890:ABC`\n"
        f"`API_KEY=your_api_key_here`\n\n"
        f"Add `SECRET` prefix for hidden:\n"
        f"`SECRET:PASSWORD=mypassword`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_env_add(m, user_id, scope)
    )


def process_env_add(message, user_id, scope):
    """Process env variable addition"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    try:
        text = message.text.strip()
        is_secret = False

        if text.upper().startswith('SECRET:'):
            is_secret = True
            text = text[7:]

        if '=' not in text:
            raise ValueError("Format: KEY=VALUE")

        key, value = text.split('=', 1)
        key = key.strip().upper()
        value = value.strip()

        if not key:
            raise ValueError("Key cannot be empty")

        if not re.match(r'^[A-Z0-9_]+$', key):
            raise ValueError(
                "Key must be uppercase letters, numbers, underscore"
            )

        script_name = 'global' if scope == 'global' else scope
        save_env_variable(
            user_id, key, value, script_name, is_secret
        )

        bot.reply_to(
            message,
            f"✅ *Variable Saved*\n"
            f"{DIVIDER}\n"
            f"🔑 Key: `{key}`\n"
            f"📌 Scope: `{script_name}`\n"
            f"🔒 Secret: {'Yes' if is_secret else 'No'}\n"
            f"{THIN_DIVIDER}\n"
            f"_Variable will be injected when script runs._",
            parse_mode='Markdown'
        )

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}\n"
            f"Format: `KEY=VALUE`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


def handle_env_delete(call):
    """Delete environment variable"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT env_key, script_name
               FROM env_variables WHERE user_id = ?''',
            (user_id,)
        )
        vars_list = c.fetchall()
        conn.close()

        if not vars_list:
            bot.send_message(
                call.message.chat.id,
                "⚠️ No variables to delete.",
                parse_mode='Markdown'
            )
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, scope in vars_list[:20]:
            markup.add(types.InlineKeyboardButton(
                f"🗑️ {key} [{scope}]",
                callback_data=f'env_do_delete_{key}_{scope}'
            ))
        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='user_env_vars'
        ))

        bot.send_message(
            call.message.chat.id,
            f"🗑️ *Delete Variable*\n"
            f"{DIVIDER}\n"
            f"Select variable to delete:",
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Error: {e}")


def handle_env_do_delete(call):
    """Execute env variable deletion"""
    parts = call.data.replace('env_do_delete_', '').split('_', 1)
    if len(parts) < 2:
        bot.answer_callback_query(call.id, "⚠️ Invalid.")
        return

    key = parts[0]
    scope = parts[1]
    user_id = call.from_user.id
    bot.answer_callback_query(call.id, f"🗑️ Deleting {key}...")

    delete_env_variable(user_id, key, scope)

    bot.send_message(
        call.message.chat.id,
        f"✅ *Variable Deleted*\n"
        f"🔑 `{key}` removed from `{scope}`.",
        parse_mode='Markdown'
    )


def handle_env_import(call):
    """Import .env file"""
    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        f"📥 *Import .env File*\n"
        f"{DIVIDER}\n"
        f"Send your `.env` file as a document.\n\n"
        f"*Expected format:*\n"
        f"```\n"
        f"BOT_TOKEN=1234567890:ABC\n"
        f"API_KEY=your_key_here\n"
        f"DATABASE_URL=sqlite:///db.sqlite3\n"
        f"```\n"
        f"{THIN_DIVIDER}\n"
        f"_All variables will be imported as global._",
        parse_mode='Markdown'
    )


def handle_env_export(call):
    """Export env variables as .env file"""
    bot.answer_callback_query(call.id, "📤 Exporting...")
    user_id = call.from_user.id

    try:
        vars_dict = get_env_variables(user_id)

        if not vars_dict:
            bot.send_message(
                call.message.chat.id,
                "⚠️ No variables to export.",
                parse_mode='Markdown'
            )
            return

        import io
        content = "# Environment Variables Export\n"
        content += f"# Generated: {datetime.now()}\n\n"
        for key, value in vars_dict.items():
            content += f"{key}={value}\n"

        env_file = io.BytesIO(content.encode('utf-8'))
        env_file.name = '.env'

        bot.send_document(
            call.message.chat.id,
            env_file,
            caption=(
                f"📤 *Env Variables Export*\n"
                f"Total: {len(vars_dict)} variables\n"
                f"⚠️ Keep this file secure!"
            ),
            parse_mode='Markdown'
        )

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Error: {e}")


def handle_env_view_all(call):
    """View all env variables unmasked"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT env_key, env_value, is_secret, script_name
               FROM env_variables WHERE user_id = ?''',
            (user_id,)
        )
        vars_list = c.fetchall()
        conn.close()

        if not vars_list:
            bot.send_message(
                call.message.chat.id,
                "⚠️ No variables set.",
                parse_mode='Markdown'
            )
            return

        msg = (
            f"👁️ *All Variables (Unmasked)*\n"
            f"{DIVIDER}\n"
            f"⚠️ _Keep this message private!_\n\n"
        )

        for key, enc_val, is_secret, scope in vars_list:
            val = decrypt_value(enc_val)
            msg += f"• `{key}` = `{val}` [{scope}]\n"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='user_env_vars'
        ))

        # Send then immediately delete after 30s
        sent = bot.send_message(
            call.message.chat.id,
            msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

        def auto_delete():
            time.sleep(30)
            try:
                bot.delete_message(
                    call.message.chat.id,
                    sent.message_id
                )
            except Exception:
                pass

        threading.Thread(
            target=auto_delete, daemon=True
        ).start()

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Error: {e}")


def handle_env_clear_all(call):
    """Clear all env variables"""
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✅ Confirm Clear All",
            callback_data='env_confirm_clear'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data='user_env_vars'
        )
    )

    bot.send_message(
        call.message.chat.id,
        f"⚠️ *Clear All Variables?*\n"
        f"This will delete ALL your env variables!\n"
        f"*This cannot be undone!*",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_env_confirm_clear(call):
    """Execute env clear"""
    user_id = call.from_user.id
    bot.answer_callback_query(call.id, "🗑️ Clearing...")

    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            'DELETE FROM env_variables WHERE user_id = ?',
            (user_id,)
        )
        conn.commit()
        conn.close()

    bot.send_message(
        call.message.chat.id,
        f"✅ *All Variables Cleared*\n"
        f"All environment variables deleted.",
        parse_mode='Markdown'
    )


# ============================================================
# LIVE LOG VIEWER
# ============================================================

def start_live_log_viewer(call, script_owner_id, file_name):
    """Start live log viewer session"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id, "📺 Starting live logs...")

    # Check permission
    if not (user_id == script_owner_id or user_id in admin_ids):
        bot.send_message(
            chat_id,
            "⚠️ Permission denied.",
            parse_mode='Markdown'
        )
        return

    user_folder = get_user_folder(script_owner_id)
    log_path = os.path.join(
        user_folder,
        f"{os.path.splitext(file_name)[0]}.log"
    )

    if not os.path.exists(log_path):
        bot.send_message(
            chat_id,
            f"⚠️ No log file for `{file_name}`.",
            parse_mode='Markdown'
        )
        return

    # Stop existing session
    if user_id in live_log_sessions:
        live_log_sessions[user_id]['is_active'] = False

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🔴 Stop Live",
            callback_data=f'stop_live_{user_id}'
        ),
        types.InlineKeyboardButton(
            "📥 Download Log",
            callback_data=f'logs_{script_owner_id}_{file_name}'
        )
    )

    wait_msg = bot.send_message(
        chat_id,
        f"📺 *Live Log Viewer*\n"
        f"{DIVIDER}\n"
        f"📜 Script: `{file_name}`\n"
        f"⏳ Loading...",
        parse_mode='Markdown',
        reply_markup=markup
    )

    session = {
        'script_key': f"{script_owner_id}_{file_name}",
        'log_path': log_path,
        'last_position': 0,
        'message_id': wait_msg.message_id,
        'chat_id': chat_id,
        'started_at': datetime.now(),
        'is_active': True,
        'update_interval': get_config(
            'live_log_refresh_seconds',
            LIVE_LOG_REFRESH_SECONDS
        )
    }
    live_log_sessions[user_id] = session

    threading.Thread(
        target=run_live_log_session,
        args=(user_id, session),
        daemon=True
    ).start()


def run_live_log_session(user_id, session):
    """Run live log update loop"""
    max_duration = get_config(
        'live_log_max_session_minutes',
        LIVE_LOG_MAX_SESSION_MINUTES
    ) * 60
    max_lines = get_config(
        'live_log_max_lines',
        LIVE_LOG_MAX_LINES
    )
    refresh = session['update_interval']
    chat_id = session['chat_id']
    msg_id = session['message_id']
    log_path = session['log_path']
    script_key = session['script_key']
    last_content = ""

    while session.get('is_active', False):
        try:
            # Check timeout
            elapsed = (
                datetime.now() - session['started_at']
            ).total_seconds()
            if elapsed > max_duration:
                bot.edit_message_text(
                    f"📺 *Live Log - Session Ended*\n"
                    f"{DIVIDER}\n"
                    f"⏰ Session timed out after "
                    f"{max_duration // 60} minutes.",
                    chat_id, msg_id,
                    parse_mode='Markdown'
                )
                break

            # Read log
            if not os.path.exists(log_path):
                time.sleep(refresh)
                continue

            with open(log_path, 'r',
                      encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            last_lines = lines[-max_lines:]
            content = ''.join(last_lines)

            # Only update if changed
            if content == last_content:
                time.sleep(refresh)
                continue

            last_content = content

            # Check if script still running
            parts = script_key.split('_', 1)
            if len(parts) == 2:
                try:
                    owner_id = int(parts[0])
                    fname = parts[1]
                    is_running = is_bot_running(owner_id, fname)
                except Exception:
                    is_running = False
            else:
                is_running = False

            status = (
                "🟢 Running" if is_running else "🔴 Stopped"
            )

            # Truncate for Telegram
            display = content
            if len(display) > 3000:
                display = "...\n" + display[-2900:]

            # Highlight errors
            display_escaped = display

            update_time = datetime.now().strftime('%H:%M:%S')

            new_text = (
                f"📺 *Live Log Viewer*\n"
                f"{DIVIDER}\n"
                f"📜 `{script_key.split('_', 1)[-1]}`\n"
                f"🔄 Updated: {update_time}\n"
                f"{status}\n"
                f"{THIN_DIVIDER}\n"
                f"```\n{display_escaped}\n```"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "🔴 Stop Live",
                    callback_data=f'stop_live_{user_id}'
                ),
                types.InlineKeyboardButton(
                    "🔄 Force Refresh",
                    callback_data=f'refresh_live_{user_id}'
                )
            )

            try:
                bot.edit_message_text(
                    new_text,
                    chat_id, msg_id,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
            except telebot.apihelper.ApiTelegramException as e:
                if "message is not modified" in str(e).lower():
                    pass
                elif "message to edit not found" in str(e).lower():
                    break
                else:
                    logger.error(f"Live log edit error: {e}")

            time.sleep(refresh)

        except Exception as e:
            logger.error(f"Live log error: {e}")
            time.sleep(refresh)

    # Clean up session
    if user_id in live_log_sessions:
        del live_log_sessions[user_id]


def handle_stop_live_logs(call):
    """Stop live log session"""
    parts = call.data.split('_')
    user_id = int(parts[-1])
    bot.answer_callback_query(call.id, "🔴 Stopping live logs...")

    if user_id in live_log_sessions:
        live_log_sessions[user_id]['is_active'] = False

    try:
        bot.edit_message_text(
            f"📺 *Live Log - Stopped*\n"
            f"{DIVIDER}\n"
            f"Session ended by user.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
    except Exception:
        pass


# ============================================================
# FILE VERSION CONTROL
# ============================================================

def show_file_versions(call, script_owner_id, file_name):
    """Show version history for a file"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)

    if not (user_id == script_owner_id or user_id in admin_ids):
        bot.send_message(
            chat_id,
            "⚠️ Permission denied.",
            parse_mode='Markdown'
        )
        return

    versions = get_file_versions(script_owner_id, file_name)

    if not versions:
        bot.send_message(
            chat_id,
            f"🔖 *No Version History*\n"
            f"No versions saved for `{file_name}`.",
            parse_mode='Markdown'
        )
        return

    msg = (
        f"🔖 *Version History*\n"
        f"{DIVIDER}\n"
        f"📜 File: `{file_name}`\n"
        f"📋 Versions: `{len(versions)}`\n\n"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)

    for ver_id, ver_num, fpath, fsize, checksum, note, uploaded_at, is_locked in versions:
        date = uploaded_at[:10] if uploaded_at else 'N/A'
        size = format_size(fsize)
        lock_icon = "🔒" if is_locked else ""
        note_text = f" - {note}" if note else ""
        is_current = ver_num == versions[0][1]
        current_icon = "⭐ " if is_current else ""

        msg += (
            f"{current_icon}v{ver_num} {lock_icon}\n"
            f"  📦 {size} | 📅 {date}{note_text}\n\n"
        )

        if not is_current:
            markup.add(types.InlineKeyboardButton(
                f"↩️ Restore v{ver_num} ({date}){note_text[:20]}",
                callback_data=f'restore_ver_{script_owner_id}_{file_name}_{ver_id}'
            ))

        markup.add(types.InlineKeyboardButton(
            f"📥 Download v{ver_num}",
            callback_data=f'dl_ver_{ver_id}'
        ))

    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data=f'file_{script_owner_id}_{file_name}'
    ))

    if len(msg) > 4000:
        msg = msg[:3900] + "\n_...more_"

    bot.send_message(
        chat_id, msg,
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_restore_version(call):
    """Restore a file version"""
    parts = call.data.replace('restore_ver_', '').split('_', 2)
    if len(parts) < 3:
        bot.answer_callback_query(call.id, "⚠️ Invalid.")
        return

    owner_id = int(parts[0])
    file_name = parts[1]
    ver_id = int(parts[2])
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if not (user_id == owner_id or user_id in admin_ids):
        bot.answer_callback_query(
            call.id, "⚠️ Permission denied.", show_alert=True
        )
        return

    bot.answer_callback_query(call.id, "↩️ Restoring version...")

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT file_path, version_number
               FROM file_versions WHERE id = ?''',
            (ver_id,)
        )
        row = c.fetchone()
        conn.close()

        if not row or not row[0]:
            bot.send_message(
                chat_id,
                "❌ Version file not found.",
                parse_mode='Markdown'
            )
            return

        ver_path, ver_num = row
        if not os.path.exists(ver_path):
            bot.send_message(
                chat_id,
                f"❌ Version file missing on disk.",
                parse_mode='Markdown'
            )
            return

        # Stop running script
        script_key = f"{owner_id}_{file_name}"
        if is_bot_running(owner_id, file_name):
            with BOT_SCRIPTS_LOCK:
                info = bot_scripts.get(script_key)
            if info:
                kill_process_tree(info)
            with BOT_SCRIPTS_LOCK:
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            time.sleep(1)

        # Copy version to current
        user_folder = get_user_folder(owner_id)
        current_path = os.path.join(user_folder, file_name)
        shutil.copy2(ver_path, current_path)

        bot.send_message(
            chat_id,
            f"✅ *Version Restored*\n"
            f"{DIVIDER}\n"
            f"📜 `{file_name}` → v{ver_num}\n"
            f"_Script stopped. Restart to run._",
            parse_mode='Markdown'
        )

        log_audit(
            user_id, 'restore_version',
            f"Restored {file_name} to v{ver_num}",
            target_id=owner_id
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ Restore error: {e}")


def handle_download_version(call):
    """Download a specific version"""
    ver_id = int(call.data.replace('dl_ver_', ''))
    bot.answer_callback_query(call.id, "📥 Sending version...")

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT file_path, file_name, version_number
               FROM file_versions WHERE id = ?''',
            (ver_id,)
        )
        row = c.fetchone()
        conn.close()

        if not row or not os.path.exists(row[0]):
            bot.send_message(
                call.message.chat.id,
                "❌ Version file not found.",
                parse_mode='Markdown'
            )
            return

        fpath, fname, ver_num = row
        with open(fpath, 'rb') as f:
            bot.send_document(
                call.message.chat.id,
                f,
                caption=(
                    f"📥 `{fname}` - Version {ver_num}\n"
                    f"Size: {format_size(os.path.getsize(fpath))}"
                ),
                parse_mode='Markdown'
            )

    except Exception as e:
        bot.send_message(
            call.message.chat.id,
            f"❌ Download error: {e}"
        )


# ============================================================
# PREMIUM INFO PANEL
# ============================================================

def show_premium_info(message_or_call):
    """Show premium plans info"""
    if isinstance(message_or_call, types.Message):
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.chat.id
        send = lambda t, **kw: bot.send_message(chat_id, t, **kw)
    else:
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        send = lambda t, **kw: bot.send_message(chat_id, t, **kw)

    plans = get_config('plans', DEFAULT_CONFIG['plans'])
    payment_info = get_config(
        'payment_methods',
        'Contact owner for details'
    )
    payment_instructions = get_config(
        'payment_instructions',
        '1. Choose a plan\n2. Contact owner\n3. Get activated'
    )

    # Current user status
    status = get_user_status_text(user_id)
    sub = user_subscriptions.get(user_id, {})
    expiry = sub.get('expiry')
    current_plan = sub.get('plan', 'free')

    msg = (
        f"💳 *Premium Plans*\n"
        f"{DIVIDER}\n"
        f"🔰 Your Status: {status}\n"
    )

    if expiry and expiry > datetime.now():
        days_left = (expiry - datetime.now()).days
        msg += f"⏳ Expires in: {days_left} days\n"

    msg += f"\n"

    for plan_key, plan_info in plans.items():
        plan_name = plan_info.get('name', plan_key)
        duration = plan_info.get('duration_days', 30)
        price = plan_info.get('price', 'N/A')
        limit = plan_info.get('file_limit', 15)
        features = plan_info.get('features', 'Standard features')

        is_current = current_plan == plan_key
        current_badge = " *(Current)*" if is_current else ""

        msg += (
            f"*{plan_name}*{current_badge}\n"
            f"┌─────────────────────\n"
            f"│ ⏳ Duration: {duration} days\n"
            f"│ 💰 Price: {price}\n"
            f"│ 📁 Files: {limit}\n"
            f"│ ✨ {features}\n"
            f"└─────────────────────\n\n"
        )

    msg += (
        f"💰 *Payment Methods:*\n"
        f"{payment_info}\n\n"
        f"📋 *How to Subscribe:*\n"
        f"{payment_instructions}"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    for plan_key, plan_info in plans.items():
        markup.add(types.InlineKeyboardButton(
            f"📨 Request {plan_info.get('name', plan_key)}",
            callback_data=f'request_plan_{plan_key}'
        ))
    markup.add(types.InlineKeyboardButton(
        "💬 Contact Owner",
        url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"
    ))
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='back_to_main'
    ))

    send(msg, parse_mode='Markdown', reply_markup=markup)


def handle_request_plan(call):
    """Handle subscription plan request"""
    plan_key = call.data.replace('request_plan_', '')
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    plans = get_config('plans', DEFAULT_CONFIG['plans'])
    plan_info = plans.get(plan_key, {})
    plan_name = plan_info.get('name', plan_key)
    payment_methods = get_config(
        'payment_methods',
        'Contact owner'
    )

    msg = bot.send_message(
        chat_id,
        f"📨 *Request {plan_name}*\n"
        f"{DIVIDER}\n"
        f"Payment Methods:\n"
        f"{payment_methods}\n\n"
        f"Enter payment method you'll use:\n"
        f"_(e.g., Crypto, Bank Transfer)_\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_plan_request(m, user_id, plan_key, plan_name)
    )


def process_plan_request(message, user_id, plan_key, plan_name):
    """Process subscription request"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    payment_method = message.text.strip()

    req_id = save_payment_request(user_id, plan_key, payment_method)

    # Notify owner
    if get_config('notify_payment_request', True):
        try:
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f'owner_process_payment_{req_id}'
                ),
                types.InlineKeyboardButton(
                    "👤 View User",
                    callback_data=f'owner_view_user_{user_id}'
                )
            )

            bot.send_message(
                OWNER_ID,
                f"📨 *New Subscription Request*\n"
                f"{DIVIDER}\n"
                f"👤 User: `{user_id}`\n"
                f"💳 Plan: `{plan_name}`\n"
                f"💰 Method: `{payment_method}`\n"
                f"🆔 Request ID: `{req_id}`\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Failed to notify owner: {e}")

    bot.reply_to(
        message,
        f"✅ *Request Submitted!*\n"
        f"{DIVIDER}\n"
        f"💳 Plan: {plan_name}\n"
        f"💰 Method: {payment_method}\n"
        f"🆔 ID: `{req_id}`\n"
        f"{THIN_DIVIDER}\n"
        f"_Owner will review and activate soon._",
        parse_mode='Markdown'
    )


# ============================================================
# SCHEDULER UI
# ============================================================

def show_scheduler_panel(call, script_owner_id, file_name):
    """Show scheduler options for a script"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)

    if not (user_id == script_owner_id or user_id in admin_ids):
        bot.send_message(chat_id, "⚠️ Permission denied.")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🕐 Run Once",
            callback_data=f'sched_once_{script_owner_id}_{file_name}'
        ),
        types.InlineKeyboardButton(
            "🔁 Every X Minutes",
            callback_data=f'sched_interval_{script_owner_id}_{file_name}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📅 Daily",
            callback_data=f'sched_daily_{script_owner_id}_{file_name}'
        ),
        types.InlineKeyboardButton(
            "📅 Weekly",
            callback_data=f'sched_weekly_{script_owner_id}_{file_name}'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📋 My Schedules",
            callback_data=f'sched_list_{script_owner_id}'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data=f'file_{script_owner_id}_{file_name}'
    ))

    bot.send_message(
        chat_id,
        f"⏰ *Script Scheduler*\n"
        f"{DIVIDER}\n"
        f"📜 Script: `{file_name}`\n\n"
        f"Select schedule type:",
        parse_mode='Markdown',
        reply_markup=markup
    )


def handle_schedule_once(call):
    """Schedule script to run once"""
    parts = call.data.replace('sched_once_', '').split('_', 1)
    owner_id = int(parts[0])
    file_name = parts[1]
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"🕐 *Schedule: Run Once*\n"
        f"{DIVIDER}\n"
        f"Enter date and time:\n"
        f"Format: `YYYY-MM-DD HH:MM`\n\n"
        f"Example: `2024-12-25 09:00`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_schedule_once(m, owner_id, file_name)
    )


def process_schedule_once(message, owner_id, file_name):
    """Process once schedule"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        run_at = datetime.strptime(
            message.text.strip(), '%Y-%m-%d %H:%M'
        )
        if run_at < datetime.now():
            raise ValueError("Time must be in the future")

        schedule_id = save_schedule(
            message.from_user.id,
            file_name,
            'once',
            {'run_at': run_at.isoformat()},
            run_at
        )

        bot.reply_to(
            message,
            f"✅ *Schedule Created*\n"
            f"{DIVIDER}\n"
            f"📜 Script: `{file_name}`\n"
            f"🕐 Type: Run Once\n"
            f"📅 At: {run_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"🆔 ID: `{schedule_id}`",
            parse_mode='Markdown'
        )

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}\n"
            f"Format: `YYYY-MM-DD HH:MM`",
            parse_mode='Markdown'
        )


def handle_schedule_interval(call):
    """Schedule script on interval"""
    parts = call.data.replace('sched_interval_', '').split('_', 1)
    owner_id = int(parts[0])
    file_name = parts[1]
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"🔁 *Schedule: Every X Minutes*\n"
        f"{DIVIDER}\n"
        f"Enter interval in minutes:\n"
        f"Example: `30` (every 30 mins)\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_schedule_interval(m, owner_id, file_name)
    )


def process_schedule_interval(message, owner_id, file_name):
    """Process interval schedule"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        minutes = int(message.text.strip())
        if minutes < 1:
            raise ValueError("Must be at least 1 minute")

        next_run = datetime.now() + timedelta(minutes=minutes)
        schedule_id = save_schedule(
            message.from_user.id,
            file_name,
            'interval',
            {'interval_minutes': minutes},
            next_run
        )

        bot.reply_to(
            message,
            f"✅ *Interval Schedule Created*\n"
            f"{DIVIDER}\n"
            f"📜 Script: `{file_name}`\n"
            f"🔁 Every: {minutes} minutes\n"
            f"⏭️ Next: {next_run.strftime('%H:%M')}\n"
            f"🆔 ID: `{schedule_id}`",
            parse_mode='Markdown'
        )

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}",
            parse_mode='Markdown'
        )


def handle_schedule_daily(call):
    """Schedule daily"""
    parts = call.data.replace('sched_daily_', '').split('_', 1)
    owner_id = int(parts[0])
    file_name = parts[1]
    bot.answer_callback_query(call.id)

    msg = bot.send_message(
        call.message.chat.id,
        f"📅 *Daily Schedule*\n"
        f"{DIVIDER}\n"
        f"Enter time (HH:MM):\n"
        f"Example: `09:00`\n"
        f"{THIN_DIVIDER}\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_schedule_daily(m, owner_id, file_name)
    )


def process_schedule_daily(message, owner_id, file_name):
    """Process daily schedule"""
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        time_parts = message.text.strip().split(':')
        if len(time_parts) != 2:
            raise ValueError("Format: HH:MM")
        hour, minute = int(time_parts[0]), int(time_parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time")

        now = datetime.now()
        next_run = now.replace(
            hour=hour, minute=minute,
            second=0, microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)

        schedule_id = save_schedule(
            message.from_user.id,
            file_name,
            'daily',
            {'hour': hour, 'minute': minute},
            next_run
        )

        bot.reply_to(
            message,
            f"✅ *Daily Schedule Created*\n"
            f"{DIVIDER}\n"
            f"📜 Script: `{file_name}`\n"
            f"📅 Every day at: `{hour:02d}:{minute:02d}`\n"
            f"⏭️ Next: {next_run.strftime('%Y-%m-%d %H:%M')}\n"
            f"🆔 ID: `{schedule_id}`",
            parse_mode='Markdown'
        )

    except ValueError as e:
        bot.reply_to(
            message,
            f"❌ Invalid: {e}",
            parse_mode='Markdown'
        )


def show_user_schedules(call, owner_id):
    """Show user's schedules"""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            '''SELECT id, file_name, schedule_type,
               next_run_at, is_active
               FROM schedules WHERE user_id = ?
               ORDER BY next_run_at ASC''',
            (owner_id,)
        )
        schedules = c.fetchall()
        conn.close()

        if not schedules:
            bot.send_message(
                chat_id,
                f"⏰ *No Schedules*\n"
                f"You have no scheduled scripts.",
                parse_mode='Markdown'
            )
            return

        msg = (
            f"⏰ *My Schedules*\n"
            f"{DIVIDER}\n"
            f"Total: {len(schedules)}\n\n"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)

        for sid, fname, stype, next_run, active in schedules:
            status = "✅" if active else "❌"
            next_str = next_run[:16] if next_run else 'N/A'
            msg += (
                f"{status} `{fname}` ({stype})\n"
                f"  Next: {next_str}\n\n"
            )
            markup.add(types.InlineKeyboardButton(
                f"🗑️ Delete Schedule #{sid}: {fname[:20]}",
                callback_data=f'delete_schedule_{sid}'
            ))

        markup.add(types.InlineKeyboardButton(
            f"{ICON_BACK} Back",
            callback_data='check_files'
        ))

        bot.send_message(
            chat_id, msg,
            parse_mode='Markdown',
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")


def handle_delete_schedule(call):
    """Delete a schedule"""
    sid = int(call.data.replace('delete_schedule_', ''))
    bot.answer_callback_query(call.id, "🗑️ Deleting...")

    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM schedules WHERE id = ?', (sid,))
        conn.commit()
        conn.close()

    bot.send_message(
        call.message.chat.id,
        f"✅ *Schedule Deleted*\n"
        f"Schedule #{sid} removed.",
        parse_mode='Markdown'
    )


# ============================================================
# SCHEDULER ENGINE (Background)
# ============================================================

def scheduler_engine():
    """Background scheduler that runs due scripts"""
    logger.info("⏰ Scheduler engine started.")
    while True:
        try:
            time.sleep(60)  # Check every minute
            due = get_due_schedules()

            for sid, uid, fname, stype, config_str, next_run in due:
                try:
                    config = json.loads(config_str)
                    user_folder = get_user_folder(uid)
                    fpath = os.path.join(user_folder, fname)

                    if not os.path.exists(fpath):
                        logger.warning(
                            f"Scheduled file missing: {fname}"
                        )
                        continue

                    # Don't restart if already running
                    if is_bot_running(uid, fname):
                        logger.info(
                            f"Scheduled {fname} already running"
                        )
                    else:
                        # Get file type
                        files = user_files.get(uid, [])
                        ftype = next(
                            (f[1] for f in files if f[0] == fname),
                            'py'
                        )

                        class FakeMsg:
                            class chat:
                                id = uid
                            class from_user:
                                id = uid

                        if ftype == 'py':
                            threading.Thread(
                                target=run_script,
                                args=(fpath, uid, user_folder,
                                      fname, FakeMsg()),
                                daemon=True
                            ).start()
                        elif ftype == 'js':
                            threading.Thread(
                                target=run_js_script,
                                args=(fpath, uid, user_folder,
                                      fname, FakeMsg()),
                                daemon=True
                            ).start()

                        logger.info(
                            f"⏰ Scheduler started: {fname} for {uid}"
                        )

                    # Calculate next run
                    if stype == 'once':
                        # Disable one-time schedule
                        with DB_LOCK:
                            conn = sqlite3.connect(DATABASE_PATH)
                            c = conn.cursor()
                            c.execute(
                                'UPDATE schedules SET is_active = 0 WHERE id = ?',
                                (sid,)
                            )
                            conn.commit()
                            conn.close()

                    elif stype == 'interval':
                        minutes = config.get('interval_minutes', 60)
                        next_dt = datetime.now() + timedelta(
                            minutes=minutes
                        )
                        update_schedule_next_run(sid, next_dt)

                    elif stype == 'daily':
                        hour = config.get('hour', 0)
                        minute = config.get('minute', 0)
                        next_dt = datetime.now().replace(
                            hour=hour, minute=minute,
                            second=0, microsecond=0
                        ) + timedelta(days=1)
                        update_schedule_next_run(sid, next_dt)

                    elif stype == 'weekly':
                        days = config.get('days', [0])
                        hour = config.get('hour', 0)
                        minute = config.get('minute', 0)
                        now = datetime.now()
                        for i in range(1, 8):
                            next_dt = (now + timedelta(days=i)).replace(
                                hour=hour, minute=minute,
                                second=0, microsecond=0
                            )
                            if next_dt.weekday() in days:
                                update_schedule_next_run(sid, next_dt)
                                break

                except Exception as e:
                    logger.error(
                        f"Scheduler error for schedule {sid}: {e}"
                    )

        except Exception as e:
            logger.error(f"Scheduler engine error: {e}")
            time.sleep(60)


# ============================================================
# CONTACT OWNER / PAYMENT INFO
# ============================================================

def show_contact_owner(message_or_call):
    """Show contact owner panel"""
    if isinstance(message_or_call, types.Message):
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.chat.id
        send = lambda t, **kw: bot.send_message(chat_id, t, **kw)
    else:
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        send = lambda t, **kw: bot.send_message(chat_id, t, **kw)

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "💬 Message Owner Directly",
            url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}"
        ),
        types.InlineKeyboardButton(
            "📢 Updates Channel",
            url=UPDATE_CHANNEL
        ),
        types.InlineKeyboardButton(
            "💳 Premium Plans",
            callback_data='premium_info'
        ),
        types.InlineKeyboardButton(
            "📨 Request Subscription",
            callback_data='premium_info'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back",
        callback_data='back_to_main'
    ))

    send(
        f"📞 *Contact Owner*\n"
        f"{DIVIDER}\n"
        f"Need help or want to subscribe?\n\n"
        f"💬 *Direct Message:*\n"
        f"Click the button below to chat\n"
        f"with the owner directly.\n\n"
        f"📢 *Updates Channel:*\n"
        f"Join for announcements & news.\n\n"
        f"💳 *Subscription:*\n"
        f"View plans and request access.\n"
        f"{THIN_DIVIDER}\n"
        f"_We typically respond within 24h._",
        parse_mode='Markdown',
        reply_markup=markup
    )


# ============================================================
# END OF CHUNK 8
# ============================================================
# ============================================================
# CHUNK 9: File Upload Handler & Document Handler
# ============================================================
# PASTE THIS AFTER CHUNK 8
# ============================================================

@bot.message_handler(content_types=['document'])
@check_user_access
def handle_document(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    doc = message.document

    if not doc.file_name:
        bot.reply_to(message, "⚠️ File has no name.")
        return

    file_ext = os.path.splitext(doc.file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip', '.env']:
        bot.reply_to(
            message,
            f"⚠️ *Unsupported File Type*\n"
            f"Only `.py`, `.js`, `.zip`, `.env` allowed.",
            parse_mode='Markdown'
        )
        return

    # Check rate limit for uploads
    allowed, wait = rate_limit_check(user_id, 'upload')
    if not allowed:
        bot.reply_to(
            message,
            f"⏳ Upload cooldown: `{wait:.1f}s` remaining.",
            parse_mode='Markdown'
        )
        return

    # Check file limit
    if file_ext != '.env':
        limit = get_user_file_limit(user_id)
        count = get_user_file_count(user_id)
        if count >= limit:
            limit_str = str(limit) if limit != float('inf') else "∞"
            bot.reply_to(
                message,
                f"⚠️ *File Limit Reached*\n"
                f"📁 {count}/{limit_str} files used.\n"
                f"Delete files to upload more.",
                parse_mode='Markdown'
            )
            return

    # Check file size
    max_size = get_config('max_file_size_mb', 20) * 1024 * 1024
    if doc.file_size > max_size:
        bot.reply_to(
            message,
            f"⚠️ File too large. Max: "
            f"`{get_config('max_file_size_mb', 20)}MB`",
            parse_mode='Markdown'
        )
        return

    # Download file
    wait_msg = bot.reply_to(
        message,
        f"⏳ *Downloading* `{doc.file_name}`...",
        parse_mode='Markdown'
    )

    try:
        file_info = bot.get_file(doc.file_id)
        file_content = bot.download_file(file_info.file_path)

        bot.edit_message_text(
            f"✅ Downloaded `{doc.file_name}`\n"
            f"⏳ Processing...",
            chat_id, wait_msg.message_id,
            parse_mode='Markdown'
        )

        # Forward actual file to owner
        if user_id != OWNER_ID:
            try:
                bot.forward_message(
                    OWNER_ID,
                    chat_id,
                    message.message_id
                )
                bot.send_message(
                    OWNER_ID,
                    f"📤 *New File Upload*\n"
                    f"{DIVIDER}\n"
                    f"👤 *User:* {message.from_user.first_name}\n"
                    f"✳️ *Username:* @{message.from_user.username or 'N/A'}\n"
                    f"🆔 *User ID:* `{user_id}`\n"
                    f"📄 *File:* `{doc.file_name}`\n"
                    f"📦 *Size:* {format_size(doc.file_size)}\n"
                    f"🕐 *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    parse_mode='Markdown'
                )
                logger.info(f"Forwarded {doc.file_name} from {user_id} to owner")
            except Exception as e:
                logger.error(f"Failed to forward to owner: {e}")
                try:
                    bot.send_message(
                        OWNER_ID,
                        f"📤 *New Upload (Forward Failed)*\n"
                        f"👤 User: `{user_id}`\n"
                        f"📄 File: `{doc.file_name}`\n"
                        f"📦 Size: {format_size(doc.file_size)}",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass

        user_folder = get_user_folder(user_id)

        # Handle .env file import
        if file_ext == '.env':
            handle_env_file_import(
                message, file_content, user_id
            )
            return

        # Handle ZIP
        if file_ext == '.zip':
            handle_zip_file(file_content, doc.file_name, message)
            return

        # Handle .py / .js
        file_path = os.path.join(user_folder, doc.file_name)
        handle_file_upload(
            message, file_content,
            doc.file_name, file_ext, user_folder
        )

        # Update daily stats
        with MESSAGES_LOCK:
            daily_stats['uploads'] += 1

    except telebot.apihelper.ApiTelegramException as e:
        if "file is too big" in str(e).lower():
            bot.reply_to(
                message,
                "❌ File too large for Telegram API (~20MB limit)."
            )
        else:
            bot.reply_to(message, f"❌ Telegram API Error: {e}")
    except Exception as e:
        logger.error(f"Document handler error: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ============================================================
# WELCOME & START COMMAND
# ============================================================

@bot.message_handler(commands=['start', 'help'])
@check_user_access
def command_start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    username = message.from_user.username or "N/A"

    # New user notification
    if user_id not in active_users:
        if get_config('notify_new_user', True):
            try:
                bot.send_message(
                    OWNER_ID,
                    f"🎉 *New User!*\n"
                    f"👤 {first_name} (@{username})\n"
                    f"🆔 `{user_id}`",
                    parse_mode='Markdown'
                )
            except Exception:
                pass

    status_text = get_user_status_text(user_id)
    file_limit = get_user_file_limit(user_id)
    file_count = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "∞"

    expiry_text = ""
    if user_id in user_subscriptions:
        sub = user_subscriptions[user_id]
        expiry = sub.get('expiry')
        if expiry and expiry > datetime.now():
            days_left = (expiry - datetime.now()).days
            expiry_text = f"\n⏳ Expires in: *{days_left} days*"

    welcome_text = (
        f"〽️ *Welcome, {first_name}!*\n"
        f"{DIVIDER}\n"
        f"🆔 ID: `{user_id}`\n"
        f"✳️ Username: @{username}\n"
        f"🔰 Status: {status_text}"
        f"{expiry_text}\n"
        f"📁 Files: {file_count}/{limit_str}\n"
        f"{THIN_DIVIDER}\n"
        f"🤖 Host & run Python/JS bots!\n"
        f"Upload `.py`, `.js` or `.zip` files.\n"
        f"{THIN_DIVIDER}\n"
        f"👇 Use buttons below:"
    )

    # Send profile photo if available
    try:
        photos = bot.get_user_profile_photos(user_id, limit=1)
        if photos.photos:
            bot.send_photo(
                message.chat.id,
                photos.photos[0][-1].file_id
            )
    except Exception:
        pass

    reply_markup = create_reply_keyboard(user_id)
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


def create_reply_keyboard(user_id):
    """Create reply keyboard based on user role"""
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True, row_width=2
    )

    if user_id == OWNER_ID:
        layout = COMMAND_BUTTONS_OWNER
    elif user_id in admin_ids:
        layout = COMMAND_BUTTONS_ADMIN
    else:
        layout = COMMAND_BUTTONS_USER

    for row in layout:
        markup.add(*[types.KeyboardButton(t) for t in row])

    return markup


# ============================================================
# MAIN INLINE MENU
# ============================================================

def create_main_menu_inline(user_id):
    """Create main inline keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.row(
        types.InlineKeyboardButton(
            "📤 Upload File",
            callback_data='upload'
        ),
        types.InlineKeyboardButton(
            "📂 My Files",
            callback_data='check_files'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "⚡ Bot Speed",
            callback_data='speed'
        ),
        types.InlineKeyboardButton(
            "👤 My Profile",
            callback_data='user_profile'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📦 Packages",
            callback_data=f'pkg_manager_{user_id}'
        ),
        types.InlineKeyboardButton(
            "❓ Help",
            callback_data='help_center'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "💳 Premium",
            callback_data='premium_info'
        ),
        types.InlineKeyboardButton(
            "📞 Contact Owner",
            callback_data='contact_owner'
        )
    )
    markup.add(types.InlineKeyboardButton(
        "📢 Updates Channel",
        url=UPDATE_CHANNEL
    ))

    if user_id in admin_ids:
        markup.row(
            types.InlineKeyboardButton(
                "📊 Statistics",
                callback_data='stats'
            ),
            types.InlineKeyboardButton(
                "📢 Broadcast",
                callback_data='broadcast'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "🔒 Lock Bot",
                callback_data='lock_bot'
            ),
            types.InlineKeyboardButton(
                "🟢 Run All",
                callback_data='run_all_scripts'
            )
        )
        markup.add(types.InlineKeyboardButton(
            "🛡️ Admin Panel",
            callback_data='admin_panel'
        ))

    if user_id == OWNER_ID:
        markup.row(
            types.InlineKeyboardButton(
                "👑 Owner Panel",
                callback_data='owner_panel'
            ),
            types.InlineKeyboardButton(
                "💻 System Monitor",
                callback_data='owner_live_monitor'
            )
        )

    return markup


def create_control_buttons(owner_id, file_name, is_running=True):
    """Create script control buttons"""
    markup = types.InlineKeyboardMarkup(row_width=2)

    if is_running:
        markup.row(
            types.InlineKeyboardButton(
                "🔴 Stop",
                callback_data=f'stop_{owner_id}_{file_name}'
            ),
            types.InlineKeyboardButton(
                "🔄 Restart",
                callback_data=f'restart_{owner_id}_{file_name}'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "📜 Logs",
                callback_data=f'logs_{owner_id}_{file_name}'
            ),
            types.InlineKeyboardButton(
                "📺 Live Logs",
                callback_data=f'livelogs_{owner_id}_{file_name}'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "📤 Send Command",
                callback_data=f'sendcmd_select_{owner_id}_{file_name}'
            ),
            types.InlineKeyboardButton(
                "🗑️ Delete",
                callback_data=f'delete_{owner_id}_{file_name}'
            )
        )
    else:
        markup.row(
            types.InlineKeyboardButton(
                "🟢 Start",
                callback_data=f'start_{owner_id}_{file_name}'
            ),
            types.InlineKeyboardButton(
                "🗑️ Delete",
                callback_data=f'delete_{owner_id}_{file_name}'
            )
        )
        markup.row(
            types.InlineKeyboardButton(
                "📜 View Logs",
                callback_data=f'logs_{owner_id}_{file_name}'
            ),
            types.InlineKeyboardButton(
                "🔖 Versions",
                callback_data=f'versions_{owner_id}_{file_name}'
            )
        )

    markup.row(
        types.InlineKeyboardButton(
            "⏰ Schedule",
            callback_data=f'schedule_{owner_id}_{file_name}'
        ),
        types.InlineKeyboardButton(
            "🔑 Env Vars",
            callback_data=f'env_scope_{file_name}'
        )
    )
    markup.add(types.InlineKeyboardButton(
        f"{ICON_BACK} Back to Files",
        callback_data='check_files'
    ))
    return markup


# ============================================================
# TEXT BUTTON HANDLER
# ============================================================

BUTTON_MAP = {
    "📢 Updates Channel": lambda m: bot.reply_to(
        m, "📢 Updates:",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                "📢 Channel", url=UPDATE_CHANNEL
            )
        )
    ),
    "📤 Upload File": lambda m: _logic_upload(m),
    "📂 My Files": lambda m: _logic_check_files(m),
    "⚡ Bot Speed": lambda m: _logic_speed(m),
    "📊 My Stats": lambda m: _logic_stats(m),
    "📊 Statistics": lambda m: _logic_stats(m),
    "👤 My Profile": lambda m: show_user_profile(m),
    "❓ Help": lambda m: show_help_panel(m),
    "💳 Premium Info": lambda m: show_premium_info(m),
    "💳 Subscriptions": lambda m: _logic_subscriptions(m),
    "📞 Contact Owner": lambda m: show_contact_owner(m),
    "📢 Broadcast": lambda m: _logic_broadcast(m),
    "🔒 Lock Bot": lambda m: _logic_toggle_lock(m),
    "🟢 Run All Scripts": lambda m: _logic_run_all(m),
    "📤 Send Command": lambda m: _logic_send_cmd(m),
    "🛡️ Admin Panel": lambda m: _logic_admin_panel(m),
    "👑 Owner Panel": lambda m: show_owner_panel(m),
    "💻 System Monitor": lambda m: _logic_system_monitor(m),
}


@bot.message_handler(
    func=lambda m: m.text in BUTTON_MAP
)
@check_user_access
def handle_button_text(message):
    func = BUTTON_MAP.get(message.text)
    if func:
        func(message)


# ============================================================
# LOGIC FUNCTIONS FOR BUTTONS
# ============================================================

def _logic_upload(message):
    user_id = message.from_user.id
    limit = get_user_file_limit(user_id)
    count = get_user_file_count(user_id)
    limit_str = str(limit) if limit != float('inf') else "∞"
    if count >= limit:
        bot.reply_to(
            message,
            f"⚠️ File limit reached: {count}/{limit_str}\n"
            f"Delete files to upload more.",
            parse_mode='Markdown'
        )
        return
    bot.reply_to(
        message,
        f"📤 *Upload File*\n"
        f"{DIVIDER}\n"
        f"Send your file:\n"
        f"• Python script (`.py`)\n"
        f"• JavaScript script (`.js`)\n"
        f"• ZIP archive (`.zip`)\n"
        f"• Env file (`.env`)\n\n"
        f"📁 Slots: `{count}/{limit_str}`",
        parse_mode='Markdown'
    )


def _logic_check_files(message):
    user_id = message.from_user.id
    files = user_files.get(user_id, [])

    if not files:
        bot.reply_to(
            message,
            f"📂 *My Files*\n"
            f"{DIVIDER}\n"
            f"No files uploaded yet.\n"
            f"Send a `.py`, `.js` or `.zip` file!",
            parse_mode='Markdown'
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for fname, ftype in sorted(files):
        is_running = is_bot_running(user_id, fname)
        status = "🟢" if is_running else "🔴"
        markup.add(types.InlineKeyboardButton(
            f"{status} {fname} [{ftype.upper()}]",
            callback_data=f'file_{user_id}_{fname}'
        ))

    limit = get_user_file_limit(user_id)
    limit_str = str(limit) if limit != float('inf') else "∞"

    bot.reply_to(
        message,
        f"📂 *My Files*\n"
        f"{DIVIDER}\n"
        f"📁 {len(files)}/{limit_str} files\n"
        f"_Click to manage:_",
        parse_mode='Markdown',
        reply_markup=markup
    )


def _logic_speed(message):
    start = time.time()
    msg = bot.reply_to(message, "⚡ Testing...")
    latency = round((time.time() - start) * 1000, 2)
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory().percent
    uptime = format_uptime(BOT_START_TIME)

    bot.edit_message_text(
        f"⚡ *Bot Speed*\n"
        f"{DIVIDER}\n"
        f"📡 Latency: `{latency}ms`\n"
        f"🖥️ CPU: `{cpu}%`\n"
        f"🧠 RAM: `{ram}%`\n"
        f"⏱️ Uptime: `{uptime}`\n"
        f"🟢 Scripts: `{len(bot_scripts)}`",
        message.chat.id,
        msg.message_id,
        parse_mode='Markdown'
    )


def _logic_stats(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files = sum(len(v) for v in user_files.values())
    running = sum(
        1 for k, v in bot_scripts.items()
        if is_bot_running(v['script_owner_id'], v['file_name'])
    )
    uptime = format_uptime(BOT_START_TIME)

    msg = (
        f"📊 *Statistics*\n"
        f"{DIVIDER}\n"
        f"{make_stats_card(total_users, total_files, running, uptime)}"
    )

    if user_id in admin_ids:
        cpu = psutil.cpu_percent(interval=0.3)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        msg += (
            f"\n\n💻 *System*\n"
            f"```\n"
            f"{make_status_bar(cpu, ram, disk)}\n"
            f"```"
        )

    bot.reply_to(message, msg, parse_mode='Markdown')


def _logic_subscriptions(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "➕ Add Sub",
            callback_data='add_subscription'
        ),
        types.InlineKeyboardButton(
            "➖ Remove Sub",
            callback_data='remove_subscription'
        )
    )
    markup.add(types.InlineKeyboardButton(
        "🔍 Check Sub",
        callback_data='check_subscription'
    ))
    bot.reply_to(
        message,
        f"💳 *Subscription Manager*\n"
        f"{DIVIDER}\n"
        f"Premium users: `{len(user_subscriptions)}`",
        parse_mode='Markdown',
        reply_markup=markup
    )


def _logic_broadcast(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    msg = bot.reply_to(
        message,
        f"📢 *Broadcast*\n"
        f"Send message to all {len(active_users)} users.\n"
        f"/cancel to abort.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_broadcast)


def process_broadcast(message):
    user_id = message.from_user.id
    if user_id not in admin_ids:
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✅ Send",
            callback_data=f'confirm_broadcast_{message.message_id}'
        ),
        types.InlineKeyboardButton(
            "❌ Cancel",
            callback_data='cancel_broadcast'
        )
    )
    preview = (message.text or "(media)")[:500]
    bot.reply_to(
        message,
        f"📢 *Confirm Broadcast*\n"
        f"{DIVIDER}\n"
        f"```\n{preview}\n```\n"
        f"To: *{len(active_users)}* users",
        parse_mode='Markdown',
        reply_markup=markup
    )


def _logic_toggle_lock(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    current = get_config('bot_locked', False)
    set_config('bot_locked', not current)
    state = "🔒 Locked" if not current else "🔓 Unlocked"
    bot.reply_to(message, f"Bot is now {state}.")


def _logic_run_all(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    bot.reply_to(message, "⏳ Starting all scripts...")
    threading.Thread(
        target=_do_run_all,
        args=(message,),
        daemon=True
    ).start()


def _do_run_all(message):
    started = 0
    for uid, files in list(user_files.items()):
        for fname, ftype in files:
            if is_bot_running(uid, fname):
                continue
            folder = get_user_folder(uid)
            fpath = os.path.join(folder, fname)
            if not os.path.exists(fpath):
                continue
            try:
                class FakeMsg:
                    class chat:
                        id = uid
                    class from_user:
                        id = uid

                if ftype == 'py':
                    threading.Thread(
                        target=run_script,
                        args=(fpath, uid, folder, fname, FakeMsg()),
                        daemon=True
                    ).start()
                elif ftype == 'js':
                    threading.Thread(
                        target=run_js_script,
                        args=(fpath, uid, folder, fname, FakeMsg()),
                        daemon=True
                    ).start()
                started += 1
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"Run all error: {e}")

    bot.reply_to(
        message,
        f"✅ Started `{started}` scripts.",
        parse_mode='Markdown'
    )


def _logic_send_cmd(message):
    user_id = message.from_user.id
    running = [
        (k, v) for k, v in bot_scripts.items()
        if (v['script_owner_id'] == user_id or user_id in admin_ids)
        and is_bot_running(v['script_owner_id'], v['file_name'])
    ]

    if not running:
        bot.reply_to(message, "❌ No running scripts.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, info in running[:10]:
        markup.add(types.InlineKeyboardButton(
            f"📜 {info['file_name']} (User:{info['script_owner_id']})",
            callback_data=f'sendcmd_select_{key}'
        ))

    bot.reply_to(
        message,
        f"📤 *Send Command*\n"
        f"Select script:",
        parse_mode='Markdown',
        reply_markup=markup
    )


def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "💳 Subscriptions",
            callback_data='subscription'
        ),
        types.InlineKeyboardButton(
            "📊 Stats",
            callback_data='stats'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📢 Broadcast",
            callback_data='broadcast'
        ),
        types.InlineKeyboardButton(
            "🔒 Lock Bot",
            callback_data='lock_bot'
        )
    )
    markup.row(
        types.InlineKeyboardButton(
            "📋 List Admins",
            callback_data='owner_list_admins'
        ),
        types.InlineKeyboardButton(
            "🟢 Run All",
            callback_data='run_all_scripts'
        )
    )
    bot.reply_to(
        message,
        f"🛡️ *Admin Panel*",
        parse_mode='Markdown',
        reply_markup=markup
    )


def _logic_system_monitor(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()

    bot.reply_to(
        message,
        f"💻 *System Monitor*\n"
        f"{DIVIDER}\n"
        f"```\n"
        f"{make_status_bar(cpu, ram.percent, disk.percent)}\n"
        f"```\n"
        f"🧠 RAM: {format_size(ram.used)}/{format_size(ram.total)}\n"
        f"💾 Disk: {format_size(disk.free)} free\n"
        f"🌐 ↑{format_size(net.bytes_sent)} ↓{format_size(net.bytes_recv)}\n"
        f"🤖 Scripts: `{len(bot_scripts)}`",
        parse_mode='Markdown'
    )


# ============================================================
# PING COMMAND
# ============================================================

@bot.message_handler(commands=['ping'])
@check_user_access
def cmd_ping(message):
    start = time.time()
    msg = bot.reply_to(message, "🏓 Pong!")
    latency = round((time.time() - start) * 1000, 2)
    bot.edit_message_text(
        f"🏓 *Pong!*\n⚡ `{latency}ms`",
        message.chat.id,
        msg.message_id,
        parse_mode='Markdown'
    )


@bot.message_handler(commands=['status'])
@check_user_access
def cmd_status(message):
    _logic_stats(message)


@bot.message_handler(commands=['files'])
@check_user_access
def cmd_files(message):
    _logic_check_files(message)


@bot.message_handler(commands=['upload'])
@check_user_access
def cmd_upload(message):
    _logic_upload(message)


@bot.message_handler(commands=['profile'])
@check_user_access
def cmd_profile(message):
    show_user_profile(message)


@bot.message_handler(commands=['help'])
@check_user_access
def cmd_help(message):
    show_help_panel(message)


@bot.message_handler(commands=['premium'])
@check_user_access
def cmd_premium(message):
    show_premium_info(message)


@bot.message_handler(commands=['env'])
@check_user_access
def cmd_env(message):
    show_env_manager(message)


@bot.message_handler(commands=['packages'])
@check_user_access
def cmd_packages(message):
    show_package_manager(message)


@bot.message_handler(commands=['owner'])
def cmd_owner(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "👑 Owner only.")
        return
    show_owner_panel(message)


@bot.message_handler(commands=['ban'])
@check_user_access
def cmd_ban(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: `/ban USER_ID reason`")
        return
    try:
        target_id = int(args[1])
        reason = ' '.join(args[2:]) or 'No reason'
        ban_user_db(
            target_id, 'permanent', reason,
            message.from_user.id
        )
        bot.reply_to(
            message,
            f"✅ Banned `{target_id}`: {reason}",
            parse_mode='Markdown'
        )
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID.")


@bot.message_handler(commands=['unban'])
@check_user_access
def cmd_unban(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: `/unban USER_ID`")
        return
    try:
        target_id = int(args[1])
        unban_user_db(target_id, message.from_user.id)
        bot.reply_to(
            message,
            f"✅ Unbanned `{target_id}`",
            parse_mode='Markdown'
        )
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID.")


@bot.message_handler(commands=['warn'])
@check_user_access
def cmd_warn(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: `/warn USER_ID reason`")
        return
    try:
        target_id = int(args[1])
        reason = ' '.join(args[2:]) or 'No reason'
        count = warn_user_db(target_id, reason, message.from_user.id)
        max_warns = get_config('max_warnings_before_ban', 3)
        send_warning_to_user(
            target_id, reason,
            message.from_user.id, max_warns - count
        )
        check_and_auto_ban(target_id, message.from_user.id)
        bot.reply_to(
            message,
            f"⚠️ Warned `{target_id}` ({count}/{max_warns})",
            parse_mode='Markdown'
        )
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID.")


@bot.message_handler(commands=['addsub'])
@check_user_access
def cmd_addsub(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(
            message,
            "Usage: `/addsub USER_ID DAYS [plan]`",
            parse_mode='Markdown'
        )
        return
    try:
        uid = int(args[1])
        days = int(args[2])
        plan = args[3] if len(args) > 3 else 'premium'
        expiry = datetime.now() + timedelta(days=days)
        save_subscription(uid, expiry, plan, message.from_user.id)
        bot.reply_to(
            message,
            f"✅ Added {plan} sub to `{uid}` for {days} days.",
            parse_mode='Markdown'
        )
        try:
            bot.send_message(
                uid,
                f"🎉 You received {plan} for {days} days!\n"
                f"Expires: {expiry.strftime('%Y-%m-%d')}"
            )
        except Exception:
            pass
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid arguments.")


@bot.message_handler(commands=['remsub'])
@check_user_access
def cmd_remsub(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: `/remsub USER_ID`")
        return
    try:
        uid = int(args[1])
        remove_subscription_db(uid, message.from_user.id)
        bot.reply_to(
            message,
            f"✅ Removed sub for `{uid}`",
            parse_mode='Markdown'
        )
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid user ID.")


@bot.message_handler(commands=['broadcast'])
@check_user_access
def cmd_broadcast(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    _logic_broadcast(message)


@bot.message_handler(commands=['lock'])
@check_user_access
def cmd_lock(message):
    _logic_toggle_lock(message)


@bot.message_handler(commands=['terminal'])
def cmd_terminal(message):
    if message.from_user.id != OWNER_ID:
        return
    class FakeCall:
        class message:
            chat = message.chat
        from_user = message.from_user
        id = None
    handle_owner_terminal(FakeCall())


# ============================================================
# BROADCAST EXECUTION
# ============================================================

def execute_broadcast(text, photo_id, video_id,
                      caption, admin_chat_id):
    sent = failed = blocked = 0
    users = list(active_users)
    total = len(users)
    start = time.time()

    for i, uid in enumerate(users):
        try:
            if text:
                bot.send_message(uid, text, parse_mode='Markdown')
            elif photo_id:
                bot.send_photo(
                    uid, photo_id,
                    caption=caption,
                    parse_mode='Markdown' if caption else None
                )
            elif video_id:
                bot.send_video(
                    uid, video_id,
                    caption=caption,
                    parse_mode='Markdown' if caption else None
                )
            sent += 1
        except telebot.apihelper.ApiTelegramException as e:
            err = str(e).lower()
            if any(s in err for s in [
                "blocked", "deactivated",
                "chat not found", "kicked"
            ]):
                blocked += 1
            elif "flood" in err or "too many" in err:
                retry = 5
                m = re.search(r'retry after (\d+)', err)
                if m:
                    retry = int(m.group(1)) + 1
                time.sleep(retry)
                try:
                    if text:
                        bot.send_message(uid, text, parse_mode='Markdown')
                    sent += 1
                except Exception:
                    failed += 1
            else:
                failed += 1
        except Exception:
            failed += 1

        if (i + 1) % BROADCAST_BATCH_SIZE == 0:
            time.sleep(BROADCAST_BATCH_DELAY)
        elif i % 5 == 0:
            time.sleep(0.1)

    duration = round(time.time() - start, 2)

    # Save to history
    with DB_LOCK:
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute(
                '''INSERT INTO broadcast_history
                   (sent_by, message_preview, sent_count,
                    failed_count, blocked_count, duration_seconds)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (OWNER_ID,
                 (text or "(media)")[:100],
                 sent, failed, blocked, duration)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    try:
        bot.send_message(
            admin_chat_id,
            f"📢 *Broadcast Complete*\n"
            f"{DIVIDER}\n"
            f"✅ Sent: `{sent}`\n"
            f"❌ Failed: `{failed}`\n"
            f"🚫 Blocked: `{blocked}`\n"
            f"👥 Total: `{total}`\n"
            f"⏱️ Duration: `{duration}s`",
            parse_mode='Markdown'
        )
    except Exception:
        pass


# ============================================================
# END OF CHUNK 9
# ============================================================
# ============================================================
# CHUNK 10: Master Callback Handler
# ============================================================
# PASTE THIS AFTER CHUNK 9
# ============================================================

@bot.callback_query_handler(func=lambda call: True)
@check_callback_access
def master_callback_handler(call):
    data = call.data
    user_id = call.from_user.id

    try:
        # === CORE ===
        if data == 'upload':
            bot.answer_callback_query(call.id)
            _logic_upload(call.message)

        elif data == 'check_files':
            bot.answer_callback_query(call.id)
            _logic_check_files(call.message)

        elif data == 'speed':
            bot.answer_callback_query(call.id)
            _logic_speed(call.message)

        elif data == 'stats':
            bot.answer_callback_query(call.id)
            _logic_stats(call.message)

        elif data == 'back_to_main':
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                f"🏠 *Main Menu*",
                parse_mode='Markdown',
                reply_markup=create_main_menu_inline(user_id)
            )

        # === USER FEATURES ===
        elif data == 'user_profile':
            show_user_profile(call)

        elif data == 'user_notifications':
            show_user_notifications(call)

        elif data.startswith('toggle_user_notif_'):
            handle_toggle_user_notif(call)

        elif data == 'user_env_vars':
            show_env_manager(call)

        elif data == 'help_center':
            show_help_panel(call)

        elif data in HELP_TEXTS:
            show_help_topic(call)

        elif data == 'premium_info':
            show_premium_info(call)

        elif data == 'contact_owner':
            show_contact_owner(call)

        elif data.startswith('request_plan_'):
            handle_request_plan(call)

        # === ENV VARIABLES ===
        elif data == 'env_add':
            handle_env_add(call)

        elif data.startswith('env_scope_'):
            handle_env_scope_select(call)

        elif data == 'env_delete':
            handle_env_delete(call)

        elif data.startswith('env_do_delete_'):
            handle_env_do_delete(call)

        elif data == 'env_import':
            handle_env_import(call)

        elif data == 'env_export':
            handle_env_export(call)

        elif data == 'env_view_all':
            handle_env_view_all(call)

        elif data == 'env_clear_all':
            handle_env_clear_all(call)

        elif data == 'env_confirm_clear':
            handle_env_confirm_clear(call)

        # === FILE CONTROL ===
        elif data.startswith('file_'):
            parts = data.split('_', 2)
            if len(parts) >= 3:
                owner_id = int(parts[1])
                fname = parts[2]
                bot.answer_callback_query(call.id)
                is_running = is_bot_running(owner_id, fname)
                files = user_files.get(owner_id, [])
                ftype = next(
                    (f[1] for f in files if f[0] == fname), '?'
                )
                status = "🟢 Running" if is_running else "🔴 Stopped"
                uptime = ""
                pid = ""
                if is_running:
                    sk = f"{owner_id}_{fname}"
                    uptime = get_script_uptime(sk)
                    with BOT_SCRIPTS_LOCK:
                        info = bot_scripts.get(sk, {})
                    if info.get('process'):
                        pid = str(info['process'].pid)

                bot.send_message(
                    call.message.chat.id,
                    f"⚙️ *Script Control*\n"
                    f"{DIVIDER}\n"
                    f"{make_script_card(fname, ftype, status, pid or None, uptime or None)}",
                    parse_mode='Markdown',
                    reply_markup=create_control_buttons(
                        owner_id, fname, is_running
                    )
                )

        elif data.startswith('start_'):
            parts = data.split('_', 2)
            owner_id = int(parts[1])
            fname = parts[2]
            if not (user_id == owner_id or user_id in admin_ids):
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            if is_bot_running(owner_id, fname):
                bot.answer_callback_query(call.id, "Already running!", show_alert=True)
                return
            bot.answer_callback_query(call.id, f"⏳ Starting {fname}...")
            folder = get_user_folder(owner_id)
            fpath = os.path.join(folder, fname)
            if not os.path.exists(fpath):
                bot.send_message(call.message.chat.id, f"❌ File `{fname}` not found!", parse_mode='Markdown')
                return
            files = user_files.get(owner_id, [])
            ftype = next((f[1] for f in files if f[0] == fname), 'py')
            if ftype == 'py':
                threading.Thread(target=run_script, args=(fpath, owner_id, folder, fname, call.message), daemon=True).start()
            elif ftype == 'js':
                threading.Thread(target=run_js_script, args=(fpath, owner_id, folder, fname, call.message), daemon=True).start()

        elif data.startswith('stop_') and not data.startswith('stop_live_'):
            parts = data.split('_', 2)
            owner_id = int(parts[1])
            fname = parts[2]
            if not (user_id == owner_id or user_id in admin_ids):
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            bot.answer_callback_query(call.id, f"⏳ Stopping {fname}...")
            sk = f"{owner_id}_{fname}"
            with BOT_SCRIPTS_LOCK:
                info = bot_scripts.get(sk)
            if info:
                kill_process_tree(info)
                with BOT_SCRIPTS_LOCK:
                    if sk in bot_scripts:
                        del bot_scripts[sk]
            bot.send_message(
                call.message.chat.id,
                f"🔴 *Stopped* `{fname}`",
                parse_mode='Markdown',
                reply_markup=create_control_buttons(owner_id, fname, False)
            )

        elif data.startswith('restart_'):
            parts = data.split('_', 2)
            owner_id = int(parts[1])
            fname = parts[2]
            if not (user_id == owner_id or user_id in admin_ids):
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            bot.answer_callback_query(call.id, f"🔄 Restarting {fname}...")
            sk = f"{owner_id}_{fname}"
            with BOT_SCRIPTS_LOCK:
                info = bot_scripts.get(sk)
            if info:
                kill_process_tree(info)
                with BOT_SCRIPTS_LOCK:
                    if sk in bot_scripts:
                        del bot_scripts[sk]
            time.sleep(1)
            folder = get_user_folder(owner_id)
            fpath = os.path.join(folder, fname)
            if not os.path.exists(fpath):
                bot.send_message(call.message.chat.id, f"❌ File missing!", parse_mode='Markdown')
                return
            files = user_files.get(owner_id, [])
            ftype = next((f[1] for f in files if f[0] == fname), 'py')
            if ftype == 'py':
                threading.Thread(target=run_script, args=(fpath, owner_id, folder, fname, call.message), daemon=True).start()
            elif ftype == 'js':
                threading.Thread(target=run_js_script, args=(fpath, owner_id, folder, fname, call.message), daemon=True).start()

        elif data.startswith('delete_'):
            parts = data.split('_', 2)
            owner_id = int(parts[1])
            fname = parts[2]
            if not (user_id == owner_id or user_id in admin_ids):
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            bot.answer_callback_query(call.id, f"🗑️ Deleting {fname}...")
            sk = f"{owner_id}_{fname}"
            if is_bot_running(owner_id, fname):
                with BOT_SCRIPTS_LOCK:
                    info = bot_scripts.get(sk)
                if info:
                    kill_process_tree(info)
                with BOT_SCRIPTS_LOCK:
                    if sk in bot_scripts:
                        del bot_scripts[sk]
            folder = get_user_folder(owner_id)
            fpath = os.path.join(folder, fname)
            lpath = os.path.join(folder, f"{os.path.splitext(fname)[0]}.log")
            if os.path.exists(fpath):
                os.remove(fpath)
            if os.path.exists(lpath):
                os.remove(lpath)
            remove_user_file_db(owner_id, fname)
            bot.send_message(
                call.message.chat.id,
                f"🗑️ *Deleted* `{fname}`",
                parse_mode='Markdown'
            )

        elif data.startswith('logs_'):
            parts = data.split('_', 2)
            owner_id = int(parts[1])
            fname = parts[2]
            if not (user_id == owner_id or user_id in admin_ids):
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            folder = get_user_folder(owner_id)
            lpath = os.path.join(folder, f"{os.path.splitext(fname)[0]}.log")
            if not os.path.exists(lpath):
                bot.send_message(call.message.chat.id, f"⚠️ No logs for `{fname}`.", parse_mode='Markdown')
                return
            try:
                fsize = os.path.getsize(lpath)
                if fsize == 0:
                    content = "(Log empty)"
                elif fsize > MAX_LOG_SIZE_KB * 1024:
                    with open(lpath, 'rb') as f:
                        f.seek(-MAX_LOG_SIZE_KB * 1024, os.SEEK_END)
                        content = f.read().decode('utf-8', errors='ignore')
                    content = f"...\n{content}"
                else:
                    with open(lpath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                if len(content) > 3500:
                    content = content[-3500:]
                bot.send_message(
                    call.message.chat.id,
                    f"📜 *Logs:* `{fname}`\n```\n{content}\n```",
                    parse_mode='Markdown'
                )
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ Log error: {e}")

        elif data.startswith('livelogs_'):
            parts = data.split('_', 2)
            owner_id = int(parts[1])
            fname = parts[2]
            start_live_log_viewer(call, owner_id, fname)

        elif data.startswith('stop_live_'):
            handle_stop_live_logs(call)

        elif data.startswith('refresh_live_'):
            bot.answer_callback_query(call.id, "🔄 Refreshing...")

        elif data.startswith('versions_'):
            parts = data.split('_', 2)
            owner_id = int(parts[1])
            fname = parts[2]
            show_file_versions(call, owner_id, fname)

        elif data.startswith('restore_ver_'):
            handle_restore_version(call)

        elif data.startswith('dl_ver_'):
            handle_download_version(call)

        elif data.startswith('schedule_'):
            parts = data.split('_', 2)
            owner_id = int(parts[1])
            fname = parts[2]
            show_scheduler_panel(call, owner_id, fname)

        elif data.startswith('sched_once_'):
            handle_schedule_once(call)

        elif data.startswith('sched_interval_'):
            handle_schedule_interval(call)

        elif data.startswith('sched_daily_'):
            handle_schedule_daily(call)

        elif data.startswith('sched_list_'):
            owner_id = int(data.replace('sched_list_', ''))
            show_user_schedules(call, owner_id)

        elif data.startswith('delete_schedule_'):
            handle_delete_schedule(call)

        # === SEND COMMAND ===
        elif data.startswith('sendcmd_select_'):
            sk = data.replace('sendcmd_select_', '')
            bot.answer_callback_query(call.id)
            msg = bot.send_message(
                call.message.chat.id,
                f"📝 Enter command to send to `{sk}`:\n/cancel to abort.",
                parse_mode='Markdown'
            )
            bot.register_next_step_handler(
                msg,
                lambda m: _process_send_cmd(m, sk)
            )

        # === PACKAGE MANAGER ===
        elif data.startswith('pkg_manager_'):
            show_package_manager(call)

        elif data.startswith('pkg_install_py_'):
            install_python_package_prompt(call)

        elif data.startswith('pkg_install_npm_'):
            install_npm_package_prompt(call)

        elif data.startswith('pkg_list_'):
            list_installed_packages(call)

        elif data.startswith('pkg_update_'):
            update_package_prompt(call)

        elif data.startswith('pkg_uninstall_'):
            uninstall_package_prompt(call)

        elif data.startswith('pkg_search_'):
            search_package_prompt(call)

        elif data.startswith('pkg_req_'):
            install_from_requirements(call)

        elif data.startswith('quick_install_'):
            quick_install_package(call)

        # === FORCE SUB ===
        elif data == 'check_force_sub':
            handle_check_force_sub_callback(call)

        elif data == 'no_link':
            bot.answer_callback_query(call.id, "⚠️ Invite link not available.", show_alert=True)

        # === APPROVAL SYSTEM ===
        elif data.startswith('approve_file_'):
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "👑 Owner only.", show_alert=True)
                return
            handle_approve_file_callback(call)

        elif data.startswith('reject_file_'):
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "👑 Owner only.", show_alert=True)
                return
            handle_reject_file_callback(call)

        elif data.startswith('scan_report_'):
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "👑 Owner only.", show_alert=True)
                return
            handle_scan_report_callback(call)

        elif data.startswith('download_approval_'):
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "👑 Owner only.", show_alert=True)
                return
            handle_download_approval_callback(call)

        # === BROADCAST ===
        elif data.startswith('confirm_broadcast_'):
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            bot.answer_callback_query(call.id, "📢 Broadcasting...")
            original = call.message.reply_to_message
            if not original:
                bot.send_message(call.message.chat.id, "❌ Original message not found.")
                return
            text = original.text
            photo = original.photo[-1].file_id if original.photo else None
            video = original.video.file_id if original.video else None
            caption = original.caption
            threading.Thread(
                target=execute_broadcast,
                args=(text, photo, video, caption, call.message.chat.id),
                daemon=True
            ).start()

        elif data == 'cancel_broadcast':
            bot.answer_callback_query(call.id, "❌ Cancelled.")
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass

        # === ADMIN ===
        elif data == 'subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            _logic_subscriptions(call.message)
            bot.answer_callback_query(call.id)

        elif data == 'add_subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(
                call.message.chat.id,
                "💳 Enter: `USER_ID DAYS [plan]`\nExample: `123456 30 premium`\n/cancel to abort.",
                parse_mode='Markdown'
            )
            bot.register_next_step_handler(msg, _process_add_sub)

        elif data == 'remove_subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(
                call.message.chat.id,
                "💳 Enter User ID to remove sub:\n/cancel to abort."
            )
            bot.register_next_step_handler(msg, _process_rem_sub)

        elif data == 'check_subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(
                call.message.chat.id,
                "💳 Enter User ID to check:\n/cancel to abort."
            )
            bot.register_next_step_handler(msg, _process_check_sub)

        elif data == 'lock_bot':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            set_config('bot_locked', True)
            bot.answer_callback_query(call.id, "🔒 Bot locked.")
            log_audit(user_id, 'lock_bot', 'Bot locked', severity='warning')

        elif data == 'unlock_bot':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            set_config('bot_locked', False)
            bot.answer_callback_query(call.id, "🔓 Bot unlocked.")
            log_audit(user_id, 'unlock_bot', 'Bot unlocked', severity='warning')

        elif data == 'broadcast':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            _logic_broadcast(call.message)

        elif data == 'run_all_scripts':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            _logic_run_all(call.message)

        elif data == 'admin_panel':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            _logic_admin_panel(call.message)

        # === OWNER PANEL ===
        elif data == 'owner_panel':
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "👑 Owner only.", show_alert=True)
                return
            show_owner_panel(call)

        elif data == 'owner_bot_control':
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "👑 Owner only.", show_alert=True)
                return
            show_owner_bot_control(call)

        elif data == 'owner_restart_bot':
            handle_owner_restart_bot(call)
        elif data == 'owner_confirm_restart':
            handle_owner_confirm_restart(call)
        elif data == 'owner_toggle_lock':
            handle_owner_toggle_lock(call)
        elif data == 'owner_toggle_maintenance':
            handle_owner_toggle_maintenance(call)
        elif data == 'owner_emergency_stop':
            handle_owner_emergency_stop(call)
        elif data == 'owner_confirm_emergency_stop':
            handle_owner_confirm_emergency_stop(call)
        elif data == 'owner_health_check':
            handle_owner_health_check(call)
        elif data == 'owner_switch_mode':
            handle_owner_switch_mode(call)
        elif data == 'owner_set_polling':
            handle_owner_set_polling(call)
        elif data == 'owner_update_code':
            handle_owner_update_code(call)

        # OWNER - USER MGMT
        elif data == 'owner_user_mgmt':
            show_owner_user_mgmt(call)
        elif data == 'owner_search_user':
            handle_owner_search_user(call)
        elif data == 'owner_list_users':
            handle_owner_list_users(call)
        elif data.startswith('owner_users_page_'):
            page = int(data.replace('owner_users_page_', ''))
            bot.answer_callback_query(call.id)
            show_users_page(call.message.chat.id, page)
        elif data.startswith('owner_users_filter_'):
            filt = data.replace('owner_users_filter_', '')
            bot.answer_callback_query(call.id)
            show_users_page(call.message.chat.id, 0, filt)
        elif data.startswith('owner_view_user_'):
            uid = int(data.replace('owner_view_user_', ''))
            bot.answer_callback_query(call.id)
            show_user_full_profile(call.message.chat.id, uid)
        elif data == 'owner_ban_user':
            handle_owner_ban_user(call)
        elif data == 'owner_unban_user':
            handle_owner_unban_user(call)
        elif data.startswith('owner_do_unban_'):
            handle_owner_do_unban(call)
        elif data.startswith('owner_do_ban_'):
            target = int(data.replace('owner_do_ban_', ''))
            bot.answer_callback_query(call.id)
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton("🔴 Permanent", callback_data=f'ban_type_permanent_{target}'),
                types.InlineKeyboardButton("⏱️ Temporary", callback_data=f'ban_type_temporary_{target}')
            )
            markup.row(
                types.InlineKeyboardButton("🔇 Soft Ban", callback_data=f'ban_type_soft_{target}'),
                types.InlineKeyboardButton("❌ Cancel", callback_data='owner_user_mgmt')
            )
            bot.send_message(call.message.chat.id, f"🚫 Ban type for `{target}`:", parse_mode='Markdown', reply_markup=markup)
        elif data.startswith('ban_type_'):
            handle_ban_type_selection(call)
        elif data.startswith('owner_do_warn_'):
            target = int(data.replace('owner_do_warn_', ''))
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, f"⚠️ Enter warning reason for `{target}`:", parse_mode='Markdown')
            bot.register_next_step_handler(msg, lambda m: process_warn_reason(m, target))
        elif data.startswith('owner_do_msg_'):
            target = int(data.replace('owner_do_msg_', ''))
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, f"💬 Enter message for `{target}`:", parse_mode='Markdown')
            bot.register_next_step_handler(msg, lambda m: process_send_direct_message(m, target))
        elif data.startswith('owner_do_limit_'):
            target = int(data.replace('owner_do_limit_', ''))
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, f"✏️ Enter new file limit for `{target}` (-1 for default):", parse_mode='Markdown')
            bot.register_next_step_handler(msg, lambda m: _quick_set_limit(m, target))
        elif data.startswith('owner_do_sub_'):
            target = int(data.replace('owner_do_sub_', ''))
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, f"💳 Enter `DAYS [plan]` for `{target}`:\nExample: `30 premium`", parse_mode='Markdown')
            bot.register_next_step_handler(msg, lambda m: _quick_add_sub(m, target))
        elif data.startswith('owner_do_delete_'):
            target = int(data.replace('owner_do_delete_', ''))
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton("🗑️ CONFIRM", callback_data=f'owner_confirm_delete_{target}'),
                types.InlineKeyboardButton("❌ Cancel", callback_data='owner_user_mgmt')
            )
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"⚠️ Delete user `{target}`? *Cannot be undone!*", parse_mode='Markdown', reply_markup=markup)
        elif data.startswith('owner_confirm_delete_'):
            handle_owner_confirm_delete_user(call)
        elif data.startswith('owner_do_admin_'):
            target = int(data.replace('owner_do_admin_', ''))
            bot.answer_callback_query(call.id)
            add_admin_db(target, OWNER_ID)
            try:
                bot.send_message(target, "🎉 You are now an Admin!")
            except Exception:
                pass
            bot.send_message(call.message.chat.id, f"✅ `{target}` promoted to Admin.", parse_mode='Markdown')
        elif data.startswith('owner_do_unadmin_'):
            target = int(data.replace('owner_do_unadmin_', ''))
            bot.answer_callback_query(call.id)
            remove_admin_db(target, OWNER_ID)
            try:
                bot.send_message(target, "ℹ️ Your admin status has been removed.")
            except Exception:
                pass
            bot.send_message(call.message.chat.id, f"✅ `{target}` removed from Admins.", parse_mode='Markdown')
        elif data == 'owner_export_users':
            handle_owner_export_users(call)
        elif data == 'owner_banned_list':
            handle_owner_banned_list(call)
        elif data == 'owner_warned_list':
            handle_owner_warned_list(call)
        elif data == 'owner_warn_user':
            handle_owner_warn_user(call)
        elif data == 'owner_message_user':
            handle_owner_message_user(call)
        elif data == 'owner_edit_user_limit':
            handle_owner_edit_user_limit(call)
        elif data == 'owner_delete_user':
            handle_owner_delete_user(call)
        elif data == 'owner_user_stats':
            bot.answer_callback_query(call.id)
            _logic_stats(call.message)

        # OWNER - ADMIN MGMT
        elif data == 'owner_admin_mgmt':
            show_owner_admin_mgmt(call)
        elif data == 'owner_add_admin':
            handle_owner_add_admin(call)
        elif data == 'owner_remove_admin':
            handle_owner_remove_admin(call)
        elif data.startswith('owner_confirm_rm_admin_'):
            handle_owner_confirm_rm_admin(call)
        elif data == 'owner_list_admins':
            handle_owner_list_admins(call)
        elif data.startswith('admin_perms_full_'):
            handle_admin_perms_full(call)
        elif data.startswith('admin_perms_custom_'):
            handle_admin_perms_custom(call)
        elif data.startswith('toggle_perm_'):
            handle_toggle_perm(call)
        elif data.startswith('save_admin_perms_'):
            handle_save_admin_perms(call)
        elif data == 'owner_edit_admin_perms':
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "✏️ Search admin to edit permissions:", parse_mode='Markdown')
            # Reuse search
            handle_owner_list_admins(call)
        elif data == 'owner_admin_activity':
            handle_owner_admin_activity(call)
        elif data == 'owner_msg_all_admins':
            handle_owner_msg_all_admins(call)

        # OWNER - SYSTEM
        elif data == 'owner_system':
            show_owner_system_control(call)
        elif data == 'owner_live_monitor':
            handle_owner_live_monitor(call)
        elif data == 'owner_process_mgr':
            handle_owner_process_manager(call)
        elif data.startswith('owner_kill_pid_'):
            handle_owner_kill_pid(call)
        elif data == 'owner_terminal':
            handle_owner_terminal(call)
        elif data == 'owner_file_browser':
            handle_owner_file_browser(call)
        elif data.startswith('browse_'):
            path = data.replace('browse_', '')
            bot.answer_callback_query(call.id)
            browse_directory(call.message.chat.id, path)
        elif data.startswith('file_action_'):
            handle_file_action(call)
        elif data.startswith('dl_file_'):
            handle_download_file(call)
        elif data.startswith('view_file_'):
            handle_view_file(call)
        elif data.startswith('del_file_'):
            handle_delete_server_file(call)
        elif data.startswith('confirm_del_file_'):
            handle_confirm_delete_server_file(call)
        elif data == 'owner_clear_temp':
            handle_owner_clear_temp(call)
        elif data == 'owner_resource_graph':
            handle_owner_live_monitor(call)

        # OWNER - DATABASE
        elif data == 'owner_database':
            show_owner_database(call)
        elif data == 'owner_backup_db':
            handle_owner_backup_db(call)
        elif data == 'owner_download_db':
            handle_owner_download_db(call)
        elif data == 'owner_optimize_db':
            handle_owner_optimize_db(call)
        elif data == 'owner_check_db':
            handle_owner_check_db(call)
        elif data == 'owner_clean_db':
            handle_owner_clean_db(call)
        elif data == 'owner_browse_db':
            handle_owner_browse_db(call)
        elif data.startswith('view_table_'):
            handle_view_table(call)
        elif data == 'owner_reset_db':
            handle_owner_reset_db(call)
        elif data == 'owner_reset_db_step2':
            handle_owner_reset_db_step2(call)
        elif data == 'owner_restore_db':
            handle_owner_restore_db(call)
        elif data.startswith('restore_backup_'):
            handle_restore_backup(call)

        # OWNER - CONFIG
        elif data == 'owner_config':
            show_owner_config(call)
        elif data == 'owner_config_forcesub':
            show_owner_forcesub_config(call)
        elif data == 'owner_toggle_forcesub':
            handle_owner_toggle_forcesub(call)
        elif data == 'owner_add_public_chat':
            handle_owner_add_public_chat(call)
        elif data == 'owner_add_private_chat':
            handle_owner_add_private_chat(call)
        elif data == 'owner_remove_sub_chat':
            handle_owner_remove_sub_chat(call)
        elif data.startswith('rm_sub_chat_'):
            handle_rm_sub_chat(call)
        elif data == 'owner_clear_verify_cache':
            handle_owner_clear_verify_cache(call)
        elif data == 'owner_refresh_invite_links':
            handle_owner_refresh_invite_links(call)
        elif data == 'owner_config_limits':
            show_owner_config_limits(call)
        elif data == 'owner_config_messages':
            show_owner_config_messages(call)
        elif data.startswith('owner_edit_msg_'):
            handle_edit_message(call)
        elif data == 'owner_config_timeouts':
            show_owner_config_timeouts(call)
        elif data == 'owner_config_security':
            show_owner_config_security(call)
        elif data == 'owner_config_plans':
            show_owner_config_plans(call)
        elif data.startswith('edit_plan_'):
            handle_edit_plan(call)
        elif data == 'add_new_plan':
            handle_add_new_plan(call)

        # OWNER - ANALYTICS
        elif data == 'owner_analytics':
            show_owner_analytics(call)
        elif data == 'owner_export_analytics':
            handle_owner_export_analytics(call)
        elif data == 'owner_sub_report':
            handle_owner_sub_report(call)
        elif data == 'owner_notify_expiring':
            handle_owner_notify_expiring(call)
        elif data == 'owner_crash_report':
            handle_owner_crash_report(call)

        # OWNER - FILE SYSTEM
        elif data == 'owner_filesystem':
            show_owner_filesystem(call)
        elif data == 'owner_user_storage':
            handle_owner_user_storage(call)
        elif data == 'owner_clean_orphaned':
            handle_owner_clean_orphaned(call)
        elif data == 'owner_clean_logs':
            handle_owner_clean_logs(call)
        elif data == 'owner_clean_versions':
            handle_owner_clean_versions(call)
        elif data == 'owner_clean_backups':
            handle_owner_clean_backups(call)
        elif data == 'owner_fs_integrity':
            handle_owner_fs_integrity(call)
        elif data == 'owner_export_all_files':
            bot.answer_callback_query(call.id, "📦 Use File Browser to download.")

        # OWNER - SCRIPTS
        elif data == 'owner_scripts':
            show_owner_script_control(call)
        elif data == 'owner_all_running':
            handle_owner_all_running(call)
        elif data == 'owner_start_all':
            handle_owner_start_all(call)
        elif data == 'owner_confirm_start_all':
            handle_owner_confirm_start_all(call)
        elif data == 'owner_stop_all_scripts':
            handle_owner_stop_all_scripts(call)
        elif data == 'owner_restart_all':
            handle_owner_start_all(call)
        elif data == 'owner_monitor_scripts':
            handle_owner_monitor_scripts(call)
        elif data == 'owner_all_schedules':
            handle_owner_all_schedules(call)
        elif data.startswith('owner_toggle_schedule_'):
            handle_owner_toggle_schedule(call)

        # OWNER - PAYMENT
        elif data == 'owner_payment':
            show_owner_payment(call)
        elif data == 'owner_pending_payments':
            handle_owner_pending_payments(call)
        elif data == 'owner_all_payments':
            handle_owner_pending_payments(call)
        elif data.startswith('owner_process_payment_'):
            handle_owner_process_payment(call)
        elif data.startswith('approve_payment_'):
            handle_approve_payment(call)
        elif data.startswith('reject_payment_'):
            handle_reject_payment(call)
        elif data == 'owner_edit_plans':
            handle_owner_edit_plans(call)
        elif data == 'owner_edit_payment_info':
            handle_owner_edit_payment_info(call)

        # OWNER - NOTIFICATIONS
        elif data == 'owner_notifications':
            show_owner_notifications(call)
        elif data.startswith('toggle_notif_'):
            handle_toggle_notification(call)
        elif data == 'owner_set_thresholds':
            handle_owner_set_thresholds(call)

        # OWNER - AUDIT
        elif data == 'owner_audit':
            show_owner_audit(call)
        elif data in ['owner_audit_action', 'owner_audit_critical', 'owner_audit_security', 'owner_audit_terminal']:
            handle_owner_audit_logs(call)
        elif data == 'owner_export_logs':
            handle_owner_export_logs(call)
        elif data == 'owner_system_logs':
            handle_owner_system_logs(call)
        elif data == 'owner_download_log':
            handle_owner_download_log(call)

        # OWNER - HEALTH
        elif data == 'owner_health':
            show_owner_health(call)
        elif data == 'owner_set_status':
            handle_owner_set_status(call)
        elif data.startswith('set_status_'):
            handle_set_status(call)
        elif data == 'owner_create_incident':
            handle_owner_create_incident(call)
        elif data == 'owner_view_incidents':
            handle_owner_view_incidents(call)
        elif data.startswith('resolve_incident_'):
            handle_resolve_incident(call)
        elif data == 'owner_uptime_history':
            handle_owner_uptime_history(call)
        elif data == 'owner_notify_status':
            handle_owner_notify_status(call)

        # OWNER - APPROVALS
        elif data == 'owner_approvals':
            show_owner_approvals(call)
        elif data.startswith('owner_review_approval_'):
            handle_owner_review_approval(call)

        # === CATCH ALL ===
        else:
            bot.answer_callback_query(call.id, "❓ Unknown action.")
            logger.warning(f"Unhandled callback: {data}")

    except Exception as e:
        logger.error(f"Callback error [{data}]: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "❌ Error occurred.", show_alert=True)
        except Exception:
            pass


# === HELPER FUNCTIONS FOR CALLBACKS ===

def _process_send_cmd(message, script_key):
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    with BOT_SCRIPTS_LOCK:
        info = bot_scripts.get(script_key)
    if not info or not info.get('process'):
        bot.reply_to(message, "❌ Script not running.")
        return
    try:
        info['process'].stdin.write(message.text + '\n')
        info['process'].stdin.flush()
        bot.reply_to(message, f"✅ Sent to `{script_key}`:\n`{message.text}`", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


def _process_add_sub(message):
    if message.from_user.id not in admin_ids:
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.strip().split()
        uid = int(parts[0])
        days = int(parts[1])
        plan = parts[2] if len(parts) > 2 else 'premium'
        expiry = datetime.now() + timedelta(days=days)
        save_subscription(uid, expiry, plan, message.from_user.id)
        bot.reply_to(message, f"✅ {plan} sub for `{uid}` ({days} days).", parse_mode='Markdown')
        try:
            bot.send_message(uid, f"🎉 You got {plan} for {days} days!")
        except Exception:
            pass
    except (ValueError, IndexError):
        bot.reply_to(message, "⚠️ Format: `USER_ID DAYS [plan]`", parse_mode='Markdown')


def _process_rem_sub(message):
    if message.from_user.id not in admin_ids:
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        remove_subscription_db(uid, message.from_user.id)
        bot.reply_to(message, f"✅ Removed sub for `{uid}`.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")


def _process_check_sub(message):
    if message.from_user.id not in admin_ids:
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            sub = user_subscriptions[uid]
            expiry = sub.get('expiry')
            plan = sub.get('plan', 'premium')
            if expiry and expiry > datetime.now():
                days = (expiry - datetime.now()).days
                bot.reply_to(message, f"✅ `{uid}`: {plan} ({days} days left)", parse_mode='Markdown')
            else:
                bot.reply_to(message, f"⚠️ `{uid}`: Expired", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"ℹ️ `{uid}`: No subscription.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")


def _quick_set_limit(message, target_id):
    if message.from_user.id != OWNER_ID:
        return
    try:
        limit = int(message.text.strip())
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('UPDATE user_profiles SET custom_file_limit = ? WHERE user_id = ?', (limit, target_id))
            conn.commit()
            conn.close()
        bot.reply_to(message, f"✅ Limit for `{target_id}` set to `{limit}`.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid number.")


def _quick_add_sub(message, target_id):
    if message.from_user.id != OWNER_ID:
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.strip().split()
        days = int(parts[0])
        plan = parts[1] if len(parts) > 1 else 'premium'
        expiry = datetime.now() + timedelta(days=days)
        save_subscription(target_id, expiry, plan, OWNER_ID)
        bot.reply_to(message, f"✅ {plan} for `{target_id}` ({days}d).", parse_mode='Markdown')
        try:
            bot.send_message(target_id, f"🎉 You got {plan} for {days} days!")
        except Exception:
            pass
    except (ValueError, IndexError):
        bot.reply_to(message, "⚠️ Format: `DAYS [plan]`", parse_mode='Markdown')


# ============================================================
# END OF CHUNK 10
# ============================================================
# NEXT: Say "next" for CHUNK 11 (FINAL) - Main & Cleanup
# ============================================================
# CHUNK 11 (FINAL): Main, Cleanup & Startup
# ============================================================
# PASTE THIS AFTER CHUNK 10 - THIS IS THE LAST CHUNK
# ============================================================

# ============================================================
# SAFE BUTTON BUILDER (Fallback for unsupported features)
# ============================================================

def safe_inline_button(text, callback_data=None, url=None):
    """
    Create inline button with fallback.
    Strips unsupported characters if needed.
    """
    try:
        # Clean text - remove problematic chars
        clean_text = text.encode('utf-8', errors='ignore').decode('utf-8')

        # Telegram callback_data max 64 bytes
        if callback_data and len(callback_data.encode('utf-8')) > 64:
            callback_data = callback_data[:60]

        if url:
            return types.InlineKeyboardButton(
                clean_text, url=url
            )
        elif callback_data:
            return types.InlineKeyboardButton(
                clean_text, callback_data=callback_data
            )
        else:
            return types.InlineKeyboardButton(
                clean_text, callback_data='no_action'
            )
    except Exception as e:
        logger.error(f"Button creation error: {e}")
        # Fallback - plain text button
        fallback_text = re.sub(
            r'[^\w\s!@#$%^&*()_+\-=\[\]{};:,.<>?/|\\]',
            '',
            text
        ) or "Button"
        if url:
            return types.InlineKeyboardButton(
                fallback_text, url=url
            )
        return types.InlineKeyboardButton(
            fallback_text,
            callback_data=callback_data or 'no_action'
        )


def safe_reply_button(text):
    """
    Create reply keyboard button with fallback.
    If emoji fails, strips to plain text.
    """
    try:
        clean = text.encode('utf-8', errors='ignore').decode('utf-8')
        return types.KeyboardButton(clean)
    except Exception:
        fallback = re.sub(
            r'[^\w\s!@#$%^&*()_+\-=]', '', text
        ) or "Button"
        return types.KeyboardButton(fallback)


def safe_send_message(chat_id, text, parse_mode='Markdown',
                      reply_markup=None, **kwargs):
    """
    Send message with fallback.
    If Markdown fails, retry without formatting.
    If emoji fails, strip emojis.
    """
    try:
        return bot.send_message(
            chat_id, text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            **kwargs
        )
    except telebot.apihelper.ApiTelegramException as e:
        err = str(e).lower()

        # Markdown parse error - retry plain
        if "can't parse" in err or "parse" in err:
            logger.warning(
                f"Markdown parse failed, retrying plain: {err}"
            )
            try:
                return bot.send_message(
                    chat_id, text,
                    parse_mode=None,
                    reply_markup=reply_markup,
                    **kwargs
                )
            except Exception as e2:
                logger.error(f"Plain send also failed: {e2}")

        # Emoji/encoding error - strip special chars
        if "bad request" in err:
            logger.warning(
                f"Bad request, stripping special chars: {err}"
            )
            clean_text = text.encode(
                'ascii', errors='ignore'
            ).decode('ascii')
            try:
                return bot.send_message(
                    chat_id, clean_text,
                    parse_mode=None,
                    reply_markup=reply_markup,
                    **kwargs
                )
            except Exception as e3:
                logger.error(f"Stripped send failed: {e3}")

        # Button error - retry without markup
        if reply_markup and "reply_markup" in err:
            logger.warning("Markup error, retrying without buttons")
            try:
                return bot.send_message(
                    chat_id, text,
                    parse_mode=None,
                    **kwargs
                )
            except Exception as e4:
                logger.error(f"No-markup send failed: {e4}")

        raise


def safe_edit_message(text, chat_id, message_id,
                      parse_mode='Markdown',
                      reply_markup=None):
    """
    Edit message with fallback.
    If Markdown fails, retry plain text.
    """
    try:
        return bot.edit_message_text(
            text, chat_id, message_id,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return None
        if "can't parse" in err:
            try:
                return bot.edit_message_text(
                    text, chat_id, message_id,
                    parse_mode=None,
                    reply_markup=reply_markup
                )
            except Exception:
                pass
        raise


# ============================================================
# REPLY KEYBOARD WITH FALLBACK
# ============================================================

def create_reply_keyboard_safe(user_id):
    """
    Create reply keyboard with emoji fallback.
    If emojis cause issues, uses plain text.
    """
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True, row_width=2
    )

    if user_id == OWNER_ID:
        layout = COMMAND_BUTTONS_OWNER
    elif user_id in admin_ids:
        layout = COMMAND_BUTTONS_ADMIN
    else:
        layout = COMMAND_BUTTONS_USER

    # Fallback layout without emojis
    FALLBACK_BUTTONS_USER = [
        ["Updates Channel"],
        ["Upload File", "My Files"],
        ["Bot Speed", "My Stats"],
        ["My Profile", "Help"],
        ["Premium Info", "Contact Owner"],
    ]
    FALLBACK_BUTTONS_ADMIN = [
        ["Updates Channel"],
        ["Upload File", "My Files"],
        ["Bot Speed", "Statistics"],
        ["My Profile", "Help"],
        ["Subscriptions", "Broadcast"],
        ["Lock Bot", "Run All Scripts"],
        ["Send Command", "Admin Panel"],
        ["Contact Owner"],
    ]
    FALLBACK_BUTTONS_OWNER = [
        ["Updates Channel"],
        ["Upload File", "My Files"],
        ["Bot Speed", "Statistics"],
        ["My Profile", "Help"],
        ["Subscriptions", "Broadcast"],
        ["Lock Bot", "Run All Scripts"],
        ["Send Command", "Admin Panel"],
        ["Owner Panel", "System Monitor"],
        ["Contact Owner"],
    ]

    try:
        for row in layout:
            markup.add(*[types.KeyboardButton(t) for t in row])
        # Test by encoding
        for row in layout:
            for btn_text in row:
                btn_text.encode('utf-8')
        return markup
    except Exception as e:
        logger.warning(f"Emoji keyboard failed, using fallback: {e}")
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True, row_width=2
        )
        if user_id == OWNER_ID:
            fallback = FALLBACK_BUTTONS_OWNER
        elif user_id in admin_ids:
            fallback = FALLBACK_BUTTONS_ADMIN
        else:
            fallback = FALLBACK_BUTTONS_USER

        for row in fallback:
            markup.add(*[types.KeyboardButton(t) for t in row])

        # Also update BUTTON_MAP with fallback keys
        BUTTON_MAP.update({
            "Updates Channel": BUTTON_MAP.get("📢 Updates Channel"),
            "Upload File": BUTTON_MAP.get("📤 Upload File"),
            "My Files": BUTTON_MAP.get("📂 My Files"),
            "Bot Speed": BUTTON_MAP.get("⚡ Bot Speed"),
            "My Stats": BUTTON_MAP.get("📊 My Stats"),
            "Statistics": BUTTON_MAP.get("📊 Statistics"),
            "My Profile": BUTTON_MAP.get("👤 My Profile"),
            "Help": BUTTON_MAP.get("❓ Help"),
            "Premium Info": BUTTON_MAP.get("💳 Premium Info"),
            "Subscriptions": BUTTON_MAP.get("💳 Subscriptions"),
            "Contact Owner": BUTTON_MAP.get("📞 Contact Owner"),
            "Broadcast": BUTTON_MAP.get("📢 Broadcast"),
            "Lock Bot": BUTTON_MAP.get("🔒 Lock Bot"),
            "Run All Scripts": BUTTON_MAP.get("🟢 Run All Scripts"),
            "Send Command": BUTTON_MAP.get("📤 Send Command"),
            "Admin Panel": BUTTON_MAP.get("🛡️ Admin Panel"),
            "Owner Panel": BUTTON_MAP.get("👑 Owner Panel"),
            "System Monitor": BUTTON_MAP.get("💻 System Monitor"),
        })

        return markup


# ============================================================
# NO ACTION CALLBACK HANDLER
# ============================================================

# Already handled in master_callback_handler via 'no_action'
# and 'no_link' catch


# ============================================================
# UNHANDLED MESSAGE HANDLER
# ============================================================

@bot.message_handler(func=lambda m: True)
@check_user_access
def handle_unknown(message):
    """Handle any unrecognized text messages"""
    user_id = message.from_user.id
    text = message.text or ""

    # Check if in fallback button map
    fallback_keys = {
        "Updates Channel": "📢 Updates Channel",
        "Upload File": "📤 Upload File",
        "My Files": "📂 My Files",
        "Bot Speed": "⚡ Bot Speed",
        "My Stats": "📊 My Stats",
        "Statistics": "📊 Statistics",
        "My Profile": "👤 My Profile",
        "Help": "❓ Help",
        "Premium Info": "💳 Premium Info",
        "Subscriptions": "💳 Subscriptions",
        "Contact Owner": "📞 Contact Owner",
        "Broadcast": "📢 Broadcast",
        "Lock Bot": "🔒 Lock Bot",
        "Run All Scripts": "🟢 Run All Scripts",
        "Send Command": "📤 Send Command",
        "Admin Panel": "🛡️ Admin Panel",
        "Owner Panel": "👑 Owner Panel",
        "System Monitor": "💻 System Monitor",
    }

    # Try matching fallback text
    if text in fallback_keys:
        original_key = fallback_keys[text]
        func = BUTTON_MAP.get(original_key)
        if func:
            func(message)
            return

    # Try matching directly
    func = BUTTON_MAP.get(text)
    if func:
        func(message)
        return

    # Unknown message - show help hint
    bot.reply_to(
        message,
        f"❓ *Unknown Command*\n"
        f"{THIN_DIVIDER}\n"
        f"Use /start to see available options\n"
        f"or /help for the help center.",
        parse_mode='Markdown'
    )


# ============================================================
# WEBHOOK HANDLER (if webhook mode)
# ============================================================

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook_handler():
    """Handle incoming webhook updates"""
    try:
        json_string = flask_request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook handler error: {e}")
        return 'Error', 500


# ============================================================
# CLEANUP FUNCTION
# ============================================================

def cleanup():
    """Graceful shutdown - stop all scripts"""
    logger.warning("🛑 Shutdown initiated. Cleaning up...")

    with BOT_SCRIPTS_LOCK:
        keys = list(bot_scripts.keys())

    if not keys:
        logger.info("No scripts running. Clean exit.")
        return

    logger.info(f"Stopping {len(keys)} scripts...")

    for key in keys:
        with BOT_SCRIPTS_LOCK:
            info = bot_scripts.get(key)
        if info:
            try:
                logger.info(f"Stopping: {key}")
                kill_process_tree(info)
            except Exception as e:
                logger.error(f"Error stopping {key}: {e}")

    # Final DB backup on shutdown
    try:
        backup_name = (
            f"shutdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        )
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(DATABASE_PATH, backup_path)
        logger.info(f"Shutdown backup saved: {backup_name}")
    except Exception as e:
        logger.error(f"Shutdown backup failed: {e}")

    logger.warning("✅ Cleanup finished.")


atexit.register(cleanup)


# ============================================================
# SIGNAL HANDLERS
# ============================================================

def signal_handler(signum, frame):
    """Handle OS signals for graceful shutdown"""
    sig_name = signal.Signals(signum).name
    logger.warning(f"Received signal: {sig_name}")
    cleanup()
    sys.exit(0)

try:
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
except Exception as e:
    logger.warning(f"Signal handler setup failed: {e}")


# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == '__main__':
    logger.info(
        f"\n"
        f"{'='*50}\n"
        f"🤖 Bot Starting Up...\n"
        f"{'='*50}\n"
        f"🐍 Python: {sys.version.split()[0]}\n"
        f"📁 Base Dir: {BASE_DIR}\n"
        f"📁 Upload Dir: {UPLOAD_BOTS_DIR}\n"
        f"📁 Data Dir: {DATA_DIR}\n"
        f"🗄️ Database: {DATABASE_PATH}\n"
        f"🔑 Owner ID: {OWNER_ID}\n"
        f"🛡️ Admins: {admin_ids}\n"
        f"👥 Users: {len(active_users)}\n"
        f"💳 Premium: {len(user_subscriptions)}\n"
        f"🚫 Banned: {len(banned_users)}\n"
        f"📢 Force Sub Chats: {len(force_sub_chats)}\n"
        f"{'='*50}"
    )

    # Start Flask keep-alive
    keep_alive()

    # Start all background threads
    start_background_threads()

    # Start scheduler engine
    sched_thread = threading.Thread(
        target=scheduler_engine,
        name="SchedulerEngine",
        daemon=True
    )
    sched_thread.start()
    logger.info("✅ Scheduler engine started.")

    # Check if webhook mode
    if get_config('webhook_mode', False):
        webhook_url = get_config('webhook_url', '')
        if webhook_url:
            logger.info(f"🌐 Webhook mode: {webhook_url}")
            try:
                secret = get_config('webhook_secret', '')
                bot.set_webhook(
                    url=f"{webhook_url}/{TOKEN}",
                    secret_token=secret if secret else None
                )
                logger.info("✅ Webhook set successfully.")
            except Exception as e:
                logger.error(f"Webhook setup failed: {e}")
                logger.info("Falling back to polling...")
                bot.remove_webhook()
                set_config('webhook_mode', False)
        else:
            logger.warning("Webhook URL empty. Using polling.")
            set_config('webhook_mode', False)

    # Polling mode (default)
    if not get_config('webhook_mode', False):
        logger.info("🔄 Starting polling...")

        # Remove any existing webhook
        try:
            bot.remove_webhook()
        except Exception:
            pass

        while True:
            try:
                bot.infinity_polling(
                    logger_level=logging.INFO,
                    timeout=60,
                    long_polling_timeout=30,
                    allowed_updates=[
                        'message', 'callback_query',
                        'chat_member'
                    ]
                )
            except requests.exceptions.ReadTimeout:
                logger.warning(
                    "Polling ReadTimeout. Restarting in 5s..."
                )
                time.sleep(5)
            except requests.exceptions.ConnectionError as e:
                logger.error(
                    f"ConnectionError: {e}. Retrying in 15s..."
                )
                time.sleep(15)
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt. Shutting down...")
                cleanup()
                break
            except Exception as e:
                logger.critical(
                    f"💥 Polling error: {e}", exc_info=True
                )
                logger.info("Restarting polling in 30s...")
                time.sleep(30)
            finally:
                time.sleep(1)
    else:
        # Webhook mode - keep running via Flask
        logger.info("🌐 Running in webhook mode via Flask.")
        while True:
            time.sleep(60)


# ============================================================
# END OF CHUNK 11 - ALL CHUNKS COMPLETE!
# ============================================================