import json
import os
import sqlite3
from datetime import datetime

from app.config import data_dir


DB_PATH = str(data_dir() / "agent.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                skill_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                name TEXT,
                tool_call_id TEXT,
                tool_calls TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
            """
        )


def utc_now():
    return datetime.utcnow().isoformat(timespec="seconds")


def get_or_create_session(session_id, default_skill_name):
    now = utc_now()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT session_id, skill_name FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row:
            return {"session_id": row[0], "skill_name": row[1]}

        conn.execute(
            """
            INSERT INTO sessions (session_id, skill_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, default_skill_name, now, now),
        )
        return {"session_id": session_id, "skill_name": default_skill_name}


def update_session_skill(session_id, skill_name):
    now = utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (session_id, skill_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                skill_name = excluded.skill_name,
                updated_at = excluded.updated_at
            """,
            (session_id, skill_name, now, now),
        )


def load_messages(session_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content, name, tool_call_id, tool_calls
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    messages = []
    for role, content, name, tool_call_id, tool_calls in rows:
        message = {"role": role, "content": content}
        if name:
            message["name"] = name
        if tool_call_id:
            message["tool_call_id"] = tool_call_id
        if tool_calls:
            message["tool_calls"] = json.loads(tool_calls)
        messages.append(message)
    return messages


def append_message(session_id, message):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (
                session_id, role, content, name, tool_call_id, tool_calls, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                message.get("role"),
                message.get("content"),
                message.get("name"),
                message.get("tool_call_id"),
                json.dumps(message.get("tool_calls"), ensure_ascii=False)
                if message.get("tool_calls")
                else None,
                utc_now(),
            ),
        )


def clear_messages(session_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
