"""
SQLite helper для хранения пользователей и объявлений.
"""
import sqlite3
import json
import time
from typing import Optional, List, Dict
from .config import DB_PATH

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            vip INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            server TEXT,
            category TEXT,
            type TEXT,
            action TEXT,
            fields TEXT,
            photos TEXT,
            vip INTEGER DEFAULT 0,
            pinned INTEGER DEFAULT 0,
            created_at INTEGER
        )
        """
    )
    conn.commit()
    conn.close()

def ensure_user(user_id: int, username: Optional[str]):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?, ?)", (user_id, username))
    # update username if changed
    cur.execute("UPDATE users SET username = ? WHERE user_id = ? AND (username IS NULL OR username != ?)", (username, user_id, username))
    conn.commit()
    conn.close()

def set_vip(user_id: int, vip: bool = True):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?, ?)", (user_id, None))
    cur.execute("UPDATE users SET vip = ? WHERE user_id = ?", (1 if vip else 0, user_id))
    conn.commit()
    conn.close()

def get_user(user_id: int) -> Optional[Dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def add_ad(user_id: int, username: str, server: str, category: str, type_: str, action: str, fields: Dict, photos: List[str], vip: bool=False, pinned: bool=False) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ads(user_id, username, server, category, type, action, fields, photos, vip, pinned, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, server, category, type_, action, json.dumps(fields, ensure_ascii=False), json.dumps(photos), 1 if vip else 0, 1 if pinned else 0, int(time.time())),
    )
    ad_id = cur.lastrowid
    conn.commit()
    conn.close()
    return ad_id

def get_ad(ad_id: int) -> Optional[Dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ads WHERE id = ?", (ad_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_ad(ad_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0

def get_ads(server: Optional[str]=None, category: Optional[str]=None, action: Optional[str]=None, limit: int=100, include_pinned_first: bool=True) -> List[Dict]:
    conn = get_conn()
    cur = conn.cursor()
    where = []
    params = []
    if server:
        where.append("server = ?")
        params.append(server)
    if category:
        where.append("category = ?")
        params.append(category)
    if action:
        where.append("action = ?")
        params.append(action)
    q = "SELECT * FROM ads"
    if where:
        q += " WHERE " + " AND ".join(where)
    if include_pinned_first:
        q += " ORDER BY pinned DESC, created_at DESC"
    else:
        q += " ORDER BY created_at DESC"
    q += f" LIMIT {limit}"
    cur.execute(q, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_ads(user_id: int) -> List[Dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ads WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_pin(ad_id: int, pinned: bool=True):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE ads SET pinned = ? WHERE id = ?", (1 if pinned else 0, ad_id))
    conn.commit()
    conn.close()