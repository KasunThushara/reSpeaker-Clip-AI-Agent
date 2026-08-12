import sqlite3
import uuid
from config import settings


def _db_path() -> str:
    return settings.DATABASE_URL.replace("sqlite:///", "")


def init_db() -> None:
    conn = sqlite3.connect(_db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    conn.commit()
    conn.close()


def create_conversation() -> str:
    conversation_id = str(uuid.uuid4())
    conn = sqlite3.connect(_db_path())
    conn.execute("INSERT INTO conversations (id) VALUES (?)", (conversation_id,))
    conn.commit()
    conn.close()
    return conversation_id


def save_turn(conversation_id: str, role: str, content: str) -> None:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "INSERT INTO turns (conversation_id, role, content) VALUES (?, ?, ?)",
        (conversation_id, role, content),
    )
    conn.commit()
    conn.close()


def get_conversation(conversation_id: str) -> list[dict]:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT role, content, created_at FROM turns WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
