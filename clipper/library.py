"""Bibliothèque SQLite des vidéos et des rendus."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from .config import DB_FILE

_lock = threading.Lock()
_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS videos (
        id TEXT PRIMARY KEY, path TEXT NOT NULL, name TEXT, size INTEGER, duration REAL,
        orientation TEXT, game TEXT, status TEXT DEFAULT 'new', stage TEXT, progress REAL DEFAULT 0,
        error TEXT, n_moments INTEGER DEFAULT 0, best_score REAL DEFAULT 0, added_at REAL
    );
    CREATE TABLE IF NOT EXISTS renders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT, moment_id INTEGER, kind TEXT,
        path TEXT, created_at REAL
    );
    """
)


def _q(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        cur = _conn.execute(sql, args)
        _conn.commit()
        return [dict(r) for r in cur.fetchall()]


def add_video(vid: str, path: str, game: str) -> dict:
    p = Path(path)
    _q("INSERT OR IGNORE INTO videos (id, path, name, size, game, added_at) VALUES (?,?,?,?,?,?)",
       (vid, str(p), p.stem, p.stat().st_size, game, time.time()))
    return get_video(vid)


def get_video(vid: str) -> dict | None:
    rows = _q("SELECT * FROM videos WHERE id=?", (vid,))
    return rows[0] if rows else None


def list_videos() -> list[dict]:
    return _q("SELECT * FROM videos ORDER BY added_at DESC")


def update_video(vid: str, **fields) -> None:
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        _q(f"UPDATE videos SET {cols} WHERE id=?", (*fields.values(), vid))


def delete_video(vid: str) -> None:
    _q("DELETE FROM videos WHERE id=?", (vid,))
    _q("DELETE FROM renders WHERE video_id=?", (vid,))


def add_render(vid: str, moment_id: int | None, kind: str, path: str) -> None:
    _q("DELETE FROM renders WHERE video_id=? AND path=?", (vid, path))
    _q("INSERT INTO renders (video_id, moment_id, kind, path, created_at) VALUES (?,?,?,?,?)",
       (vid, moment_id, kind, path, time.time()))


def list_renders(vid: str) -> list[dict]:
    return [r for r in _q("SELECT * FROM renders WHERE video_id=? ORDER BY created_at DESC", (vid,))
            if Path(r["path"]).exists()]
