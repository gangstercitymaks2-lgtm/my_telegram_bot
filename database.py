import sqlite3
from contextlib import closing

DB_PATH = "drafts.db"

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            user_id INTEGER PRIMARY KEY,
            data TEXT
        )
        """)
        con.commit()

def save_draft(user_id: int, data: str):
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.execute(
            "REPLACE INTO drafts (user_id, data) VALUES (?, ?)",
            (user_id, data),
        )
        con.commit()

def load_draft(user_id: int) -> str | None:
    with closing(sqlite3.connect(DB_PATH)) as con:
        row = con.execute(
            "SELECT data FROM drafts WHERE user_id=?",
            (user_id,),
        ).fetchone()
        return row[0] if row else None

def delete_draft(user_id: int):
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.execute("DELETE FROM drafts WHERE user_id=?", (user_id,))
        con.commit()
