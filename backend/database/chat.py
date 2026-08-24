import logging
import sqlite3
import uuid

from config import settings
from backend.database import supabase_client

logger = logging.getLogger(__name__)


def _use_supabase() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)


# ---------------------------------------------------------------------------
# SQLite backend (fallback / tests)
# ---------------------------------------------------------------------------

def _sqlite_db_path() -> str:
    return settings.DATABASE_URL.replace("sqlite:///", "")


def _sqlite_ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    additions = {
        "user_id": "user_id TEXT",
        "title": "title TEXT",
        "overview": "overview TEXT",
        "action_items": "action_items TEXT",
    }
    for col, ddl in additions.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE conversations ADD COLUMN {ddl}")


def _sqlite_init_db() -> None:
    conn = sqlite3.connect(_sqlite_db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            title TEXT,
            overview TEXT,
            action_items TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)
    _sqlite_ensure_columns(conn)
    conn.execute("INSERT OR IGNORE INTO users (id, email) VALUES (?, ?)", (settings.USER_ID, "user-1@local"))
    conn.commit()
    conn.close()


def _sqlite_create_conversation(user_id: str) -> str:
    conversation_id = str(uuid.uuid4())
    conn = sqlite3.connect(_sqlite_db_path())
    conn.execute("INSERT INTO conversations (id, user_id) VALUES (?, ?)", (conversation_id, user_id))
    conn.commit()
    conn.close()
    return conversation_id


def _sqlite_save_turn(conversation_id: str, role: str, content: str) -> None:
    conn = sqlite3.connect(_sqlite_db_path())
    conn.execute(
        "INSERT INTO turns (conversation_id, role, content) VALUES (?, ?, ?)",
        (conversation_id, role, content),
    )
    conn.commit()
    conn.close()


def _sqlite_get_conversation(conversation_id: str) -> list[dict]:
    conn = sqlite3.connect(_sqlite_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT role, content, created_at FROM turns WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _sqlite_get_recent_messages(conversation_id: str, limit: int) -> list[dict]:
    conn = sqlite3.connect(_sqlite_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT role, content FROM turns WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    conn.close()
    messages = [{"role": r["role"], "content": r["content"]} for r in rows]
    messages.reverse()
    return messages


def _sqlite_save_summary(conversation_id: str, title: str, overview: str, action_items: str = "") -> None:
    conn = sqlite3.connect(_sqlite_db_path())
    conn.execute(
        "UPDATE conversations SET title=?, overview=?, action_items=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (title, overview, action_items, conversation_id),
    )
    conn.commit()
    conn.close()


def _sqlite_get_summary(conversation_id: str) -> dict | None:
    conn = sqlite3.connect(_sqlite_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT title, overview, action_items FROM conversations WHERE id=?",
        (conversation_id,),
    ).fetchone()
    conn.close()
    if not row or row["title"] is None:
        return None
    return dict(row)


def _sqlite_get_by_ids(conversation_ids: list[str]) -> list[dict]:
    if not conversation_ids:
        return []
    placeholders = ",".join("?" * len(conversation_ids))
    conn = sqlite3.connect(_sqlite_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"SELECT id, title, overview FROM conversations WHERE id IN ({placeholders})",
        conversation_ids,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Supabase backend
# ---------------------------------------------------------------------------

def _supabase_init_db() -> None:
    try:
        supabase_client.get_client().table("users").upsert(
            {"id": settings.USER_ID, "email": "user-1@local"}, on_conflict="id"
        ).execute()
    except Exception as e:
        logger.warning("Supabase init failed (run supabase_schema.sql?): %s", e)


def _supabase_create_conversation(user_id: str) -> str:
    conversation_id = str(uuid.uuid4())
    supabase_client.get_client().table("conversations").insert(
        {"id": conversation_id, "user_id": user_id}
    ).execute()
    return conversation_id


def _supabase_save_turn(conversation_id: str, role: str, content: str) -> None:
    supabase_client.get_client().table("messages").insert(
        {"conversation_id": conversation_id, "role": role, "content": content}
    ).execute()


def _supabase_get_conversation(conversation_id: str) -> list[dict]:
    res = (
        supabase_client.get_client()
        .table("messages")
        .select("role, content, created_at")
        .eq("conversation_id", conversation_id)
        .order("id")
        .execute()
    )
    return res.data


def _supabase_get_recent_messages(conversation_id: str, limit: int) -> list[dict]:
    res = (
        supabase_client.get_client()
        .table("messages")
        .select("role, content")
        .eq("conversation_id", conversation_id)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    messages = [{"role": r["role"], "content": r["content"]} for r in res.data]
    messages.reverse()
    return messages


def _supabase_save_summary(conversation_id: str, title: str, overview: str, action_items: str = "") -> None:
    supabase_client.get_client().table("conversations").update(
        {"title": title, "overview": overview, "action_items": action_items, "updated_at": "now()"}
    ).eq("id", conversation_id).execute()


def _supabase_get_summary(conversation_id: str) -> dict | None:
    res = (
        supabase_client.get_client()
        .table("conversations")
        .select("title, overview, action_items")
        .eq("id", conversation_id)
        .execute()
    )
    if not res.data or res.data[0].get("title") is None:
        return None
    return res.data[0]


def _supabase_get_by_ids(conversation_ids: list[str]) -> list[dict]:
    if not conversation_ids:
        return []
    res = (
        supabase_client.get_client()
        .table("conversations")
        .select("id, title, overview")
        .in_("id", conversation_ids)
        .execute()
    )
    return res.data


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------

def init_db() -> None:
    if _use_supabase():
        _supabase_init_db()
    else:
        _sqlite_init_db()


def create_conversation(user_id: str | None = None) -> str:
    uid = user_id or settings.USER_ID
    if _use_supabase():
        return _supabase_create_conversation(uid)
    return _sqlite_create_conversation(uid)


def save_turn(conversation_id: str, role: str, content: str) -> None:
    if _use_supabase():
        _supabase_save_turn(conversation_id, role, content)
    else:
        _sqlite_save_turn(conversation_id, role, content)


def get_conversation(conversation_id: str) -> list[dict]:
    if _use_supabase():
        return _supabase_get_conversation(conversation_id)
    return _sqlite_get_conversation(conversation_id)


def get_recent_messages(conversation_id: str, limit: int = 10) -> list[dict]:
    if _use_supabase():
        return _supabase_get_recent_messages(conversation_id, limit)
    return _sqlite_get_recent_messages(conversation_id, limit)


def save_conversation_summary(conversation_id: str, title: str, overview: str, action_items: str = "") -> None:
    if _use_supabase():
        _supabase_save_summary(conversation_id, title, overview, action_items)
    else:
        _sqlite_save_summary(conversation_id, title, overview, action_items)


def get_conversation_summary(conversation_id: str) -> dict | None:
    if _use_supabase():
        return _supabase_get_summary(conversation_id)
    return _sqlite_get_summary(conversation_id)


def get_conversations_by_ids(conversation_ids: list[str]) -> list[dict]:
    if _use_supabase():
        return _supabase_get_by_ids(conversation_ids)
    return _sqlite_get_by_ids(conversation_ids)
