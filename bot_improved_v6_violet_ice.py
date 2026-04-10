import os
import json
import time
import hmac
import html
import sqlite3
import hashlib
import logging
import mimetypes
import secrets
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

import telebot
from telebot import types
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
MINIAPP_DIR = BASE_DIR / "miniapp"

LOCAL_CONFIG = {
    "BOT_TOKEN": "PASTE_YOUR_BOT_TOKEN_HERE",
    "PUBLIC_BASE_URL": "",
    "MINI_APP_URL": "",
    "ADMIN_MINI_APP_URL": "",
    "WEB_HOST": "0.0.0.0",
    "WEB_PORT": 8081,
    "PORT": "",
    "DB_PATH": str(BASE_DIR / "shokerefund.db"),
    "CHANNEL_USERNAME": "@shokerefund",
    "CHANNEL_URL": "",
    "REVIEWS_URL": "https://t.me/shokerefund_reviews",
    "AGREEMENT_URL": "https://telegra.ph/Polzovatelskoe-soglashenie-ShokeRefund-Servisa-pomoshchi-v-oformlenii-vozvratov-za-nekachestvennuyu-dostavku-edy-04-05",
    "ADMIN_CHAT_ID": 0,
    "MAIN_ADMIN_ID": 0,
    "ADMIN_IDS": {"123456789": "Главный админ"},
    "MAX_TICKETS_PER_DAY": 3,
    "COMMISSION": 0.25,
    "SEND_STARTUP_MESSAGE": True,
    "DEV_ALLOW_UNSAFE_INITDATA": False,
    "INITDATA_MAX_AGE": 86400,
    "SESSION_TTL_DAYS": 30,
    "PASSWORD_RESET_ALLOWED": True,
}


def _raw_cfg(name: str, default=None):
    env_val = os.getenv(name)
    if env_val is not None and env_val != "":
        return env_val
    return LOCAL_CONFIG.get(name, default)


def _cfg_text(name: str, default: str = "") -> str:
    raw = _raw_cfg(name, default)
    return "" if raw is None else str(raw)


def _cfg_int(name: str, default: int = 0) -> int:
    try:
        return int(_raw_cfg(name, default))
    except Exception:
        return default


def _cfg_float(name: str, default: float = 0.0) -> float:
    try:
        return float(_raw_cfg(name, default))
    except Exception:
        return default


def _cfg_bool(name: str, default: bool = False) -> bool:
    raw = _raw_cfg(name, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y", "да"}


BOT_TOKEN = _cfg_text("BOT_TOKEN", "")
if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
    raise RuntimeError('Не задан BOT_TOKEN. Впиши токен в LOCAL_CONFIG["BOT_TOKEN"] или передай переменную окружения BOT_TOKEN.')

PUBLIC_BASE_URL = _cfg_text("PUBLIC_BASE_URL", "").rstrip("/")
WEB_HOST = _cfg_text("WEB_HOST", "0.0.0.0")
WEB_PORT = _cfg_int("PORT", _cfg_int("WEB_PORT", 8081))
DB_PATH = _cfg_text("DB_PATH", str(BASE_DIR / "shokerefund.db"))
CHANNEL_USERNAME = _cfg_text("CHANNEL_USERNAME", "@shokerefund")
CHANNEL_URL = _cfg_text("CHANNEL_URL", "") or f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
REVIEWS_URL = _cfg_text("REVIEWS_URL", "https://t.me/shokerefund_reviews")
AGREEMENT_URL = _cfg_text("AGREEMENT_URL", "https://telegra.ph/Polzovatelskoe-soglashenie-ShokeRefund-Servisa-pomoshchi-v-oformlenii-vozvratov-za-nekachestvennuyu-dostavku-edy-04-05")
ADMIN_CHAT_ID = _cfg_int("ADMIN_CHAT_ID", 0)
MAIN_ADMIN_ID = _cfg_int("MAIN_ADMIN_ID", 0)
MAX_TICKETS_PER_DAY = _cfg_int("MAX_TICKETS_PER_DAY", 3)
COMMISSION = _cfg_float("COMMISSION", 0.25)
SEND_STARTUP_MESSAGE = _cfg_bool("SEND_STARTUP_MESSAGE", True)
DEV_ALLOW_UNSAFE_INITDATA = _cfg_bool("DEV_ALLOW_UNSAFE_INITDATA", False)
INITDATA_MAX_AGE = _cfg_int("INITDATA_MAX_AGE", 86400)
SESSION_TTL_DAYS = _cfg_int("SESSION_TTL_DAYS", 30)
PASSWORD_RESET_ALLOWED = _cfg_bool("PASSWORD_RESET_ALLOWED", True)

try:
    raw_admins = os.getenv("ADMIN_IDS_JSON")
    parsed_admins = json.loads(raw_admins) if raw_admins else LOCAL_CONFIG.get("ADMIN_IDS", {})
except Exception:
    parsed_admins = LOCAL_CONFIG.get("ADMIN_IDS", {})
ADMIN_IDS = {int(k): str(v) for k, v in parsed_admins.items()}

MINI_APP_URL = _cfg_text("MINI_APP_URL", "").strip()
ADMIN_MINI_APP_URL = _cfg_text("ADMIN_MINI_APP_URL", "").strip()
if PUBLIC_BASE_URL:
    MINI_APP_URL = MINI_APP_URL or f"{PUBLIC_BASE_URL}/"
    ADMIN_MINI_APP_URL = ADMIN_MINI_APP_URL or f"{PUBLIC_BASE_URL}/?mode=admin"

if not MINI_APP_URL and PUBLIC_BASE_URL:
    MINI_APP_URL = f"{PUBLIC_BASE_URL}/"
if not ADMIN_MINI_APP_URL and PUBLIC_BASE_URL:
    ADMIN_MINI_APP_URL = f"{PUBLIC_BASE_URL}/?mode=admin"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(BASE_DIR / "bot.log", encoding="utf-8")],
)
log = logging.getLogger("shokerefund")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    conn = db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            cabinet_login TEXT UNIQUE,
            password_hash TEXT,
            password_salt TEXT,
            password_updated_at REAL,
            last_login_at REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            assigned_admin INTEGER,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            sender_role TEXT NOT NULL,
            sender_id INTEGER,
            sender_name TEXT,
            text TEXT NOT NULL,
            created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            user_agent TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket ON ticket_messages(ticket_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)")
    ensure_column(conn, "users", "cabinet_login", "TEXT UNIQUE")
    ensure_column(conn, "users", "password_hash", "TEXT")
    ensure_column(conn, "users", "password_salt", "TEXT")
    ensure_column(conn, "users", "password_updated_at", "REAL")
    ensure_column(conn, "users", "last_login_at", "REAL")
    conn.commit()
    conn.close()
    log.info("База данных инициализирована: %s", DB_PATH)


def now_ts() -> float:
    return time.time()


def h(text: Any) -> str:
    return html.escape(str(text or ""))


def full_name_from_user(user_obj: Any) -> str:
    if not user_obj:
        return ""
    first = getattr(user_obj, "first_name", None) if not isinstance(user_obj, dict) else user_obj.get("first_name")
    last = getattr(user_obj, "last_name", None) if not isinstance(user_obj, dict) else user_obj.get("last_name")
    parts = [p for p in [first, last] if p]
    return " ".join(parts).strip()


def is_admin(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS or (MAIN_ADMIN_ID and int(user_id) == MAIN_ADMIN_ID)


def user_main_kb(user_id: Optional[int] = None):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if MINI_APP_URL:
        kb.add(types.KeyboardButton("🖥 Открыть кабинет", web_app=types.WebAppInfo(MINI_APP_URL)))
    else:
        kb.add(types.KeyboardButton("🖥 Открыть кабинет"))
    if user_id and is_admin(user_id) and ADMIN_MINI_APP_URL:
        kb.add(types.KeyboardButton("🧿 Web Admin", web_app=types.WebAppInfo(ADMIN_MINI_APP_URL)))
    return kb


def admin_inline_open():
    if not ADMIN_MINI_APP_URL:
        return None
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🧿 Открыть Web Admin", web_app=types.WebAppInfo(ADMIN_MINI_APP_URL)))
    return kb


def user_inline_open():
    if not MINI_APP_URL:
        return None
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🖥 Открыть личный кабинет", web_app=types.WebAppInfo(MINI_APP_URL)))
    return kb


def upsert_user_from_telegram(user_obj: Any) -> Dict[str, Any]:
    user_id = int(getattr(user_obj, "id", None) if not isinstance(user_obj, dict) else user_obj.get("id"))
    username = getattr(user_obj, "username", None) if not isinstance(user_obj, dict) else user_obj.get("username")
    full_name = full_name_from_user(user_obj)
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    ts = now_ts()
    if row:
        conn.execute(
            "UPDATE users SET username=?, full_name=?, updated_at=? WHERE user_id=?",
            (username, full_name, ts, user_id),
        )
    else:
        conn.execute(
            "INSERT INTO users(user_id, username, full_name, created_at, updated_at) VALUES(?,?,?,?,?)",
            (user_id, username, full_name, ts, ts),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row)


def get_user_record(user_id: int) -> Optional[Dict[str, Any]]:
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (int(user_id),)).fetchone()
    conn.close()
    return dict(row) if row else None


def validate_login_value(login: str) -> bool:
    if not login or len(login) < 4 or len(login) > 32:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return all(ch in allowed for ch in login)


def validate_password_value(password: str) -> bool:
    return bool(password) and len(password) >= 6 and len(password) <= 128


def password_hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200_000).hex()


def set_user_password(user_id: int, login: str, password: str) -> Dict[str, Any]:
    salt = secrets.token_hex(16)
    hashed = password_hash(password, salt)
    ts = now_ts()
    conn = db()
    conn.execute(
        """UPDATE users
           SET cabinet_login=?, password_hash=?, password_salt=?, password_updated_at=?, updated_at=?
           WHERE user_id=?""",
        (login.lower(), hashed, salt, ts, ts, int(user_id)),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (int(user_id),)).fetchone()
    conn.close()
    return dict(row)


def verify_user_password(user_id: int, login: str, password: str) -> bool:
    row = get_user_record(user_id)
    if not row or not row.get("password_hash") or not row.get("password_salt"):
        return False
    if (row.get("cabinet_login") or "").lower() != login.lower():
        return False
    return hmac.compare_digest(row["password_hash"], password_hash(password, row["password_salt"]))


def create_session(user_id: int, user_agent: str = "") -> str:
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    ts = now_ts()
    expires = ts + SESSION_TTL_DAYS * 86400
    conn = db()
    conn.execute(
        "INSERT INTO user_sessions(user_id, token_hash, created_at, expires_at, user_agent) VALUES(?,?,?,?,?)",
        (int(user_id), token_hash, ts, expires, user_agent[:200]),
    )
    conn.execute("UPDATE users SET last_login_at=? WHERE user_id=?", (ts, int(user_id)))
    conn.commit()
    conn.close()
    return raw


def clear_expired_sessions() -> None:
    conn = db()
    conn.execute("DELETE FROM user_sessions WHERE expires_at < ?", (now_ts(),))
    conn.commit()
    conn.close()


def revoke_user_session(token: str) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = db()
    conn.execute("DELETE FROM user_sessions WHERE token_hash=?", (token_hash,))
    conn.commit()
    conn.close()


def validate_session_token(user_id: int, token: str) -> bool:
    if not token:
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = db()
    row = conn.execute(
        "SELECT * FROM user_sessions WHERE user_id=? AND token_hash=? AND expires_at>?",
        (int(user_id), token_hash, now_ts()),
    ).fetchone()
    conn.close()
    return bool(row)


def parse_init_data(init_data: str) -> Dict[str, str]:
    return dict(parse_qsl(init_data or "", keep_blank_values=True))


def validate_webapp_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    if not init_data:
        return None
    parsed_pairs = parse_qsl(init_data, keep_blank_values=True)
    data = {k: v for k, v in parsed_pairs}
    if DEV_ALLOW_UNSAFE_INITDATA and "hash" not in data:
        user_payload = {}
        if "user" in data:
            try:
                user_payload = json.loads(data["user"])
            except Exception:
                user_payload = {}
        return {"ok": True, "user": user_payload, "raw": data}

    their_hash = data.get("hash")
    if not their_hash:
        return None
    check_pairs = [f"{k}={v}" for k, v in sorted(parsed_pairs) if k != "hash"]
    data_check_string = "\n".join(check_pairs)
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, their_hash):
        return None
    auth_date = int(data.get("auth_date", "0") or 0)
    if auth_date and abs(now_ts() - auth_date) > INITDATA_MAX_AGE:
        return None
    user_payload = {}
    if data.get("user"):
        try:
            user_payload = json.loads(data["user"])
        except Exception:
            return None
    return {"ok": True, "user": user_payload, "raw": data}


def auth_user_from_http(init_data: str, session_token: str = "") -> Optional[Dict[str, Any]]:
    auth = validate_webapp_init_data(init_data)
    if not auth:
        return None
    user = auth.get("user") or {}
    try:
        user_id = int(user.get("id"))
    except Exception:
        return None
    row = upsert_user_from_telegram(user)
    has_password = bool(row.get("password_hash"))
    session_valid = validate_session_token(user_id, session_token) if has_password else True
    return {
        "user_id": user_id,
        "telegram_user": user,
        "db_user": row,
        "has_password": has_password,
        "session_valid": session_valid,
    }


def require_user_session(init_data: str, session_token: str = "") -> Optional[Dict[str, Any]]:
    auth = auth_user_from_http(init_data, session_token)
    if not auth:
        return None
    if not auth["has_password"]:
        return None
    if not auth["session_valid"]:
        return None
    return auth


def auth_admin_from_http(init_data: str) -> Optional[Dict[str, Any]]:
    auth = validate_webapp_init_data(init_data)
    if not auth:
        return None
    user = auth.get("user") or {}
    try:
        user_id = int(user.get("id"))
    except Exception:
        return None
    if not is_admin(user_id):
        return None
    upsert_user_from_telegram(user)
    return {"user_id": user_id, "telegram_user": user}


def active_statuses() -> set:
    return {"new", "in_progress", "waiting_user"}


def find_active_ticket(user_id: int) -> Optional[Dict[str, Any]]:
    conn = db()
    row = conn.execute(
        "SELECT * FROM tickets WHERE user_id=? AND status IN ('new','in_progress','waiting_user') ORDER BY created_at DESC LIMIT 1",
        (int(user_id),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    conn = db()
    row = conn.execute("SELECT * FROM tickets WHERE id=?", (int(ticket_id),)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_ticket(user_id: int, service: str, amount: float, description: str) -> Dict[str, Any]:
    ts = now_ts()
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO tickets(user_id, service, amount, description, status, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?)""",
        (int(user_id), service[:120], float(amount), description[:4000], "new", ts, ts),
    )
    ticket_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    conn.close()
    add_ticket_message(ticket_id, "system", "Заявка создана. Поддержка подключится в ближайшее время.")
    return dict(row)


def user_ticket_count_today(user_id: int) -> int:
    day_ago = now_ts() - 86400
    conn = db()
    count = conn.execute("SELECT COUNT(*) FROM tickets WHERE user_id=? AND created_at>=?", (int(user_id), day_ago)).fetchone()[0]
    conn.close()
    return int(count or 0)


def assign_ticket(ticket_id: int, admin_id: int) -> None:
    conn = db()
    conn.execute("UPDATE tickets SET assigned_admin=?, updated_at=? WHERE id=?", (int(admin_id), now_ts(), int(ticket_id)))
    conn.commit()
    conn.close()


def update_ticket_status(ticket_id: int, status: str) -> None:
    conn = db()
    conn.execute("UPDATE tickets SET status=?, updated_at=? WHERE id=?", (status, now_ts(), int(ticket_id)))
    conn.commit()
    conn.close()


def add_ticket_message(ticket_id: int, sender_role: str, text: str, sender_id: Optional[int] = None, sender_name: Optional[str] = None) -> None:
    clean = (text or "").strip()
    if not clean:
        return
    conn = db()
    conn.execute(
        """INSERT INTO ticket_messages(ticket_id, sender_role, sender_id, sender_name, text, created_at)
           VALUES(?,?,?,?,?,?)""",
        (int(ticket_id), sender_role[:30], sender_id, (sender_name or "")[:120], clean[:4000], now_ts()),
    )
    conn.execute("UPDATE tickets SET updated_at=? WHERE id=?", (now_ts(), int(ticket_id)))
    conn.commit()
    conn.close()


def get_ticket_messages(ticket_id: int) -> List[Dict[str, Any]]:
    conn = db()
    rows = conn.execute(
        "SELECT * FROM ticket_messages WHERE ticket_id=? ORDER BY created_at ASC, id ASC",
        (int(ticket_id),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def commission_amount(amount: float) -> float:
    return round(float(amount or 0) * COMMISSION, 2)


def status_label(status: str) -> str:
    mapping = {
        "new": "Новая",
        "in_progress": "В работе",
        "waiting_user": "Ждёт пользователя",
        "done": "Завершена",
        "rejected": "Отклонена",
    }
    return mapping.get(status, status or "—")


def format_dt(ts: Optional[float]) -> str:
    if not ts:
        return "—"
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(float(ts)))


def serialize_ticket(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    data = dict(row)
    data["status_label"] = status_label(data.get("status"))
    data["commission"] = commission_amount(data.get("amount") or 0)
    data["created_at_label"] = format_dt(data.get("created_at"))
    data["updated_at_label"] = format_dt(data.get("updated_at"))
    assigned_admin = data.get("assigned_admin")
    data["assigned_admin_name"] = ADMIN_IDS.get(int(assigned_admin), f"Админ {assigned_admin}") if assigned_admin else None
    return data


def admin_summary() -> Dict[str, Any]:
    conn = db()
    summary = {
        "new": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='new'").fetchone()[0],
        "in_progress": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='in_progress'").fetchone()[0],
        "waiting_user": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='waiting_user'").fetchone()[0],
        "done": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='done'").fetchone()[0],
        "rejected": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='rejected'").fetchone()[0],
        "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
    }
    conn.close()
    return summary


def list_admin_tickets(status: str = "all", search: str = "") -> List[Dict[str, Any]]:
    sql = "SELECT * FROM tickets WHERE 1=1"
    params: List[Any] = []
    if status and status != "all":
        sql += " AND status=?"
        params.append(status)
    term = (search or "").strip()
    if term:
        like = f"%{term}%"
        sql += " AND (CAST(id AS TEXT) LIKE ? OR CAST(user_id AS TEXT) LIKE ? OR service LIKE ? OR IFNULL(description,'') LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY updated_at DESC, created_at DESC LIMIT 200"
    conn = db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [serialize_ticket(dict(row)) for row in rows]


def notify_admin_new_ticket(ticket: Dict[str, Any]) -> None:
    if not ADMIN_CHAT_ID:
        return
    text = (
        f"🆕 <b>Новая заявка #{ticket['id']}</b>\n"
        f"👤 <code>{ticket['user_id']}</code>\n"
        f"🛍 {h(ticket['service'])}\n"
        f"💳 {ticket['amount']} ₽\n"
        f"📝 {h(ticket.get('description') or 'Без комментария')}"
    )
    try:
        bot.send_message(ADMIN_CHAT_ID, text, reply_markup=admin_inline_open())
    except Exception as exc:
        log.warning("Не удалось отправить уведомление админу: %s", exc)


def notify_user_ticket_update(user_id: int, text: str) -> None:
    try:
        bot.send_message(int(user_id), text, reply_markup=user_main_kb(int(user_id)))
    except Exception:
        pass


@bot.message_handler(commands=["start"])
def cmd_start(message):
    user = message.from_user
    row = upsert_user_from_telegram(user)
    text = (
        f"👋 <b>Привет, {h(full_name_from_user(user) or 'друг')}!</b>\n\n"
        "Это финальная версия ShokeRefund: пользователь работает через Mini App, "
        "а администратор — через Web Admin.\n\n"
        "Внутри кабинета доступны:\n"
        "• авторизация по логину и паролю;\n"
        "• создание и просмотр заявки;\n"
        "• переписка с поддержкой;\n"
        "• личный кабинет со статусом кейса.\n"
    )
    if row.get("cabinet_login"):
        text += f"\nВаш логин кабинета: <code>{h(row['cabinet_login'])}</code>"
    bot.send_message(user.id, text, reply_markup=user_main_kb(user.id))


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔️ Доступ только для администраторов.")
        return
    upsert_user_from_telegram(message.from_user)
    text = (
        "🧿 <b>Web Admin</b>\n\n"
        "Откройте мини-приложение администратора, чтобы:\n"
        "• просматривать тикеты;\n"
        "• назначать их на себя;\n"
        "• менять статус;\n"
        "• отвечать пользователям прямо из панели."
    )
    bot.send_message(message.chat.id, text, reply_markup=user_main_kb(message.from_user.id))
    inline = admin_inline_open()
    if inline:
        bot.send_message(message.chat.id, "Открыть панель:", reply_markup=inline)


@bot.message_handler(content_types=["web_app_data"])
def on_web_app_data(message):
    upsert_user_from_telegram(message.from_user)
    try:
        payload = json.loads(message.web_app_data.data or "{}")
    except Exception:
        bot.send_message(message.chat.id, "⚠️ Не удалось прочитать данные Mini App.")
        return
    action = str(payload.get("action") or "").strip()
    if action == "create_ticket":
        if find_active_ticket(message.from_user.id):
            bot.send_message(message.chat.id, "У вас уже есть активная заявка. Откройте личный кабинет.", reply_markup=user_main_kb(message.from_user.id))
            return
        amount = float(payload.get("amount") or 0)
        service = str(payload.get("service") or "").strip()
        description = str(payload.get("description") or "").strip()
        if not service or amount <= 0:
            bot.send_message(message.chat.id, "⚠️ Недостаточно данных для создания заявки.")
            return
        ticket = create_ticket(message.from_user.id, service, amount, description)
        notify_admin_new_ticket(ticket)
        bot.send_message(message.chat.id, f"✅ Заявка #{ticket['id']} создана.", reply_markup=user_main_kb(message.from_user.id))
        return
    if action == "open_status":
        ticket = find_active_ticket(message.from_user.id)
        if not ticket:
            bot.send_message(message.chat.id, "Активной заявки пока нет.", reply_markup=user_main_kb(message.from_user.id))
            return
        ticket = serialize_ticket(ticket)
        bot.send_message(
            message.chat.id,
            f"📌 <b>Заявка #{ticket['id']}</b>\nСтатус: <b>{h(ticket['status_label'])}</b>\nОбновлено: {h(ticket['updated_at_label'])}",
            reply_markup=user_main_kb(message.from_user.id),
        )
        return
    bot.send_message(message.chat.id, "Используйте Mini App для работы с заявками.", reply_markup=user_main_kb(message.from_user.id))


@bot.message_handler(content_types=["text", "photo", "document", "video", "audio", "voice", "sticker"])
def on_other_message(message):
    if message.content_type == "text" and message.text and message.text.startswith("/"):
        return
    upsert_user_from_telegram(message.from_user)
    if is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "Используйте команду /admin или кнопку 🧿 Web Admin.", reply_markup=user_main_kb(message.from_user.id))
    else:
        bot.send_message(
            message.chat.id,
            "🖥 Этот бот работает через Mini App. Откройте личный кабинет кнопкой ниже.",
            reply_markup=user_main_kb(message.from_user.id),
        )


class MiniAppHandler(BaseHTTPRequestHandler):
    server_version = "ShokeRefundFinal/1.0"

    def log_message(self, format, *args):
        log.info("HTTP %s - %s", self.address_string(), format % args)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_json(self, payload: Dict[str, Any], status: int = 200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, file_path: Path):
        if not file_path.exists():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        raw = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except Exception:
            length = 0
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if path == "/healthz":
            return self._send_json({"ok": True, "service": "shokerefund-final", "port": WEB_PORT})
        if path.startswith("/api/"):
            return self.handle_api_get(path, query)

        rel = path.lstrip("/") or "index.html"
        file_path = (MINIAPP_DIR / rel).resolve()
        if not str(file_path).startswith(str(MINIAPP_DIR.resolve())):
            return self._send_json({"ok": False, "error": "forbidden"}, 403)
        if file_path.is_dir():
            file_path = file_path / "index.html"
        if not file_path.exists():
            file_path = MINIAPP_DIR / "index.html"
        return self._send_file(file_path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json()
        if not path.startswith("/api/"):
            return self._send_json({"ok": False, "error": "not_found"}, 404)
        return self.handle_api_post(path, body)

    def handle_api_get(self, path: str, query: Dict[str, str]):
        if path == "/api/user/bootstrap":
            init_data = query.get("initData", "")
            session_token = query.get("sessionToken", "")
            auth = auth_user_from_http(init_data, session_token)
            if not auth:
                return self._send_json({"ok": False, "error": "unauthorized"}, 401)
            account = {
                "login": auth["db_user"].get("cabinet_login"),
                "hasPassword": auth["has_password"],
                "sessionValid": auth["session_valid"],
                "passwordResetAllowed": PASSWORD_RESET_ALLOWED,
            }
            user = auth["telegram_user"]
            ticket = find_active_ticket(auth["user_id"]) if account["sessionValid"] and account["hasPassword"] else None
            messages = get_ticket_messages(ticket["id"]) if ticket else []
            return self._send_json(
                {
                    "ok": True,
                    "user": {
                        "id": auth["user_id"],
                        "username": user.get("username"),
                        "fullName": full_name_from_user(user),
                    },
                    "account": account,
                    "ticket": serialize_ticket(ticket),
                    "messages": messages,
                    "links": {
                        "reviews": REVIEWS_URL,
                        "agreement": AGREEMENT_URL,
                        "channel": CHANNEL_URL,
                    },
                }
            )

        if path == "/api/admin/bootstrap":
            init_data = query.get("initData", "")
            auth = auth_admin_from_http(init_data)
            if not auth:
                return self._send_json({"ok": False, "error": "forbidden"}, 403)
            return self._send_json({"ok": True, "summary": admin_summary(), "tickets": list_admin_tickets()})

        if path == "/api/admin/tickets":
            init_data = query.get("initData", "")
            auth = auth_admin_from_http(init_data)
            if not auth:
                return self._send_json({"ok": False, "error": "forbidden"}, 403)
            status = query.get("status", "all")
            search = query.get("search", "")
            return self._send_json({"ok": True, "tickets": list_admin_tickets(status, search)})

        if path.startswith("/api/admin/tickets/"):
            init_data = query.get("initData", "")
            auth = auth_admin_from_http(init_data)
            if not auth:
                return self._send_json({"ok": False, "error": "forbidden"}, 403)
            try:
                ticket_id = int(path.split("/")[4])
            except Exception:
                return self._send_json({"ok": False, "error": "bad_ticket_id"}, 400)
            ticket = get_ticket(ticket_id)
            if not ticket:
                return self._send_json({"ok": False, "error": "not_found"}, 404)
            return self._send_json({"ok": True, "ticket": serialize_ticket(ticket), "messages": get_ticket_messages(ticket_id)})

        return self._send_json({"ok": False, "error": "not_found"}, 404)

    def handle_api_post(self, path: str, body: Dict[str, Any]):
        init_data = str(body.get("initData") or "")
        session_token = str(body.get("sessionToken") or "")
        user_agent = self.headers.get("User-Agent", "")

        if path == "/api/user/account/register":
            auth = auth_user_from_http(init_data, session_token)
            if not auth:
                return self._send_json({"ok": False, "error": "unauthorized"}, 401)
            login_value = str(body.get("login") or "").strip().lower()
            password_value = str(body.get("password") or "")
            if not validate_login_value(login_value):
                return self._send_json({"ok": False, "error": "bad_login", "message": "Логин: 4-32 символа, латиница, цифры, . _ -"}, 400)
            if not validate_password_value(password_value):
                return self._send_json({"ok": False, "error": "bad_password", "message": "Пароль должен быть не короче 6 символов."}, 400)
            conn = db()
            exists = conn.execute("SELECT user_id FROM users WHERE cabinet_login=? AND user_id<>?", (login_value, auth["user_id"])).fetchone()
            conn.close()
            if exists:
                return self._send_json({"ok": False, "error": "login_taken"}, 409)
            set_user_password(auth["user_id"], login_value, password_value)
            token = create_session(auth["user_id"], user_agent)
            return self._send_json({"ok": True, "token": token, "login": login_value})

        if path == "/api/user/account/login":
            auth = auth_user_from_http(init_data, session_token="")
            if not auth:
                return self._send_json({"ok": False, "error": "unauthorized"}, 401)
            login_value = str(body.get("login") or "").strip().lower()
            password_value = str(body.get("password") or "")
            if not verify_user_password(auth["user_id"], login_value, password_value):
                return self._send_json({"ok": False, "error": "invalid_credentials"}, 401)
            token = create_session(auth["user_id"], user_agent)
            return self._send_json({"ok": True, "token": token})

        if path == "/api/user/account/logout":
            revoke_user_session(session_token)
            return self._send_json({"ok": True})

        if path == "/api/user/account/reset-password":
            if not PASSWORD_RESET_ALLOWED:
                return self._send_json({"ok": False, "error": "disabled"}, 403)
            auth = auth_user_from_http(init_data, session_token="")
            if not auth:
                return self._send_json({"ok": False, "error": "unauthorized"}, 401)
            login_value = str(body.get("login") or "").strip().lower()
            password_value = str(body.get("password") or "")
            if not validate_login_value(login_value) or not validate_password_value(password_value):
                return self._send_json({"ok": False, "error": "bad_payload"}, 400)
            conn = db()
            exists = conn.execute("SELECT user_id FROM users WHERE cabinet_login=? AND user_id<>?", (login_value, auth["user_id"])).fetchone()
            conn.close()
            if exists:
                return self._send_json({"ok": False, "error": "login_taken"}, 409)
            set_user_password(auth["user_id"], login_value, password_value)
            token = create_session(auth["user_id"], user_agent)
            return self._send_json({"ok": True, "token": token})

        if path == "/api/user/tickets/create":
            auth = require_user_session(init_data, session_token)
            if not auth:
                return self._send_json({"ok": False, "error": "session_required"}, 401)
            if find_active_ticket(auth["user_id"]):
                return self._send_json({"ok": False, "error": "active_ticket_exists"}, 409)
            if user_ticket_count_today(auth["user_id"]) >= MAX_TICKETS_PER_DAY:
                return self._send_json({"ok": False, "error": "daily_limit"}, 429)
            service = str(body.get("service") or "").strip()
            description = str(body.get("description") or "").strip()
            try:
                amount = float(body.get("amount") or 0)
            except Exception:
                amount = 0.0
            if not service:
                return self._send_json({"ok": False, "error": "service_required"}, 400)
            if amount < 100 or amount > 100000:
                return self._send_json({"ok": False, "error": "bad_amount"}, 400)
            ticket = create_ticket(auth["user_id"], service, amount, description)
            notify_admin_new_ticket(ticket)
            notify_user_ticket_update(auth["user_id"], f"✅ Ваша заявка #{ticket['id']} создана. Откройте кабинет для переписки с поддержкой.")
            return self._send_json({"ok": True, "ticket": serialize_ticket(ticket), "messages": get_ticket_messages(ticket["id"])})

        if path.startswith("/api/user/tickets/") and path.endswith("/reply"):
            auth = require_user_session(init_data, session_token)
            if not auth:
                return self._send_json({"ok": False, "error": "session_required"}, 401)
            try:
                ticket_id = int(path.split("/")[4])
            except Exception:
                return self._send_json({"ok": False, "error": "bad_ticket_id"}, 400)
            ticket = get_ticket(ticket_id)
            if not ticket or int(ticket["user_id"]) != auth["user_id"]:
                return self._send_json({"ok": False, "error": "forbidden"}, 403)
            text = str(body.get("text") or "").strip()
            if not text:
                return self._send_json({"ok": False, "error": "empty_text"}, 400)
            add_ticket_message(ticket_id, "user", text, sender_id=auth["user_id"], sender_name=full_name_from_user(auth["telegram_user"]) or "Клиент")
            update_ticket_status(ticket_id, "in_progress" if ticket["status"] == "new" else ticket["status"])
            if ADMIN_CHAT_ID:
                try:
                    bot.send_message(
                        ADMIN_CHAT_ID,
                        f"📨 <b>Новый ответ от клиента</b>\nЗаявка #{ticket_id}\nПользователь: <code>{auth['user_id']}</code>\n\n{h(text)}",
                        reply_markup=admin_inline_open(),
                    )
                except Exception:
                    pass
            return self._send_json({"ok": True, "messages": get_ticket_messages(ticket_id), "ticket": serialize_ticket(get_ticket(ticket_id))})

        if path.startswith("/api/admin/tickets/"):
            auth = auth_admin_from_http(init_data)
            if not auth:
                return self._send_json({"ok": False, "error": "forbidden"}, 403)
            parts = [p for p in path.split("/") if p]
            if len(parts) < 5:
                return self._send_json({"ok": False, "error": "bad_path"}, 400)
            try:
                ticket_id = int(parts[3])
            except Exception:
                return self._send_json({"ok": False, "error": "bad_ticket_id"}, 400)
            ticket = get_ticket(ticket_id)
            if not ticket:
                return self._send_json({"ok": False, "error": "not_found"}, 404)
            action = parts[4]

            if action == "assign":
                assign_ticket(ticket_id, auth["user_id"])
                add_ticket_message(ticket_id, "system", f"Заявка назначена на администратора {auth['user_id']}.")
                return self._send_json({"ok": True, "ticket": serialize_ticket(get_ticket(ticket_id))})

            if action == "status":
                status = str(body.get("status") or "").strip()
                if status not in {"new", "in_progress", "waiting_user", "done", "rejected"}:
                    return self._send_json({"ok": False, "error": "bad_status"}, 400)
                update_ticket_status(ticket_id, status)
                add_ticket_message(ticket_id, "system", f"Статус заявки изменён: {status_label(status)}.")
                notify_user_ticket_update(ticket["user_id"], f"ℹ️ Статус заявки #{ticket_id}: {status_label(status)}.")
                return self._send_json({"ok": True, "ticket": serialize_ticket(get_ticket(ticket_id)), "messages": get_ticket_messages(ticket_id)})

            if action == "reply":
                text = str(body.get("text") or "").strip()
                if not text:
                    return self._send_json({"ok": False, "error": "empty_text"}, 400)
                assign_ticket(ticket_id, auth["user_id"])
                update_ticket_status(ticket_id, "waiting_user")
                add_ticket_message(ticket_id, "admin", text, sender_id=auth["user_id"], sender_name=ADMIN_IDS.get(auth["user_id"], f"Админ {auth['user_id']}"))
                notify_user_ticket_update(ticket["user_id"], f"💬 Поддержка ответила по заявке #{ticket_id}. Откройте личный кабинет.")
                return self._send_json({"ok": True, "ticket": serialize_ticket(get_ticket(ticket_id)), "messages": get_ticket_messages(ticket_id)})

        return self._send_json({"ok": False, "error": "not_found"}, 404)


def run_http_server() -> None:
    if not MINIAPP_DIR.exists():
        raise RuntimeError(f"Не найдена папка miniapp: {MINIAPP_DIR}")
    server = ThreadingHTTPServer((WEB_HOST, WEB_PORT), MiniAppHandler)
    log.info("Mini App server listening on http://%s:%s", WEB_HOST, WEB_PORT)
    server.serve_forever()


def setup_bot_commands() -> None:
    try:
        bot.set_my_commands(
            [
                types.BotCommand("start", "Открыть личный кабинет"),
                types.BotCommand("admin", "Открыть Web Admin"),
            ]
        )
    except Exception as exc:
        log.warning("Не удалось установить команды: %s", exc)


def main() -> None:
    init_db()
    clear_expired_sessions()
    setup_bot_commands()

    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    if SEND_STARTUP_MESSAGE and ADMIN_CHAT_ID:
        try:
            bot.send_message(
                ADMIN_CHAT_ID,
                "🚀 <b>ShokeRefund Final запущен</b>\nПользовательская и админ-панель готовы.",
                reply_markup=admin_inline_open(),
            )
        except Exception as exc:
            log.warning("Стартовое сообщение не отправлено: %s", exc)

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as exc:
            log.error("Polling error: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
