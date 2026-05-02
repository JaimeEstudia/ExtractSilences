"""
Database layer using SQLite for persistent storage of videos and segments.
"""

import sqlite3
import os
from typing import List, Dict, Optional

DB_PATH = os.path.join(os.path.expanduser("~"), ".silence_detector.db")


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS videos (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS segments (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id    INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
                    start_time  REAL NOT NULL,
                    end_time    REAL NOT NULL,
                    label       TEXT DEFAULT '',
                    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)

    # ── Videos ────────────────────────────────────────────────────────────────

    def add_video(self, path: str) -> int:
        with self._connect() as conn:
            try:
                cur = conn.execute("INSERT INTO videos (path) VALUES (?)", (path,))
                return cur.lastrowid
            except sqlite3.IntegrityError:
                # Already exists — return its id
                row = conn.execute("SELECT id FROM videos WHERE path = ?", (path,)).fetchone()
                return row["id"]

    def get_all_videos(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM videos ORDER BY added_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_video(self, vid_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM videos WHERE id = ?", (vid_id,)).fetchone()
            return dict(row) if row else None

    def remove_video(self, vid_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM videos WHERE id = ?", (vid_id,))

    # ── Segments ──────────────────────────────────────────────────────────────

    def save_segments(self, video_id: int, segments: List[Dict]):
        """Replace all segments for a video with a fresh analysis result."""
        with self._connect() as conn:
            conn.execute("DELETE FROM segments WHERE video_id = ?", (video_id,))
            for seg in segments:
                conn.execute(
                    "INSERT INTO segments (video_id, start_time, end_time, label) VALUES (?, ?, ?, ?)",
                    (video_id, seg["start_time"], seg["end_time"], seg.get("label", ""))
                )

    def get_segments(self, video_id: int) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM segments WHERE video_id = ? ORDER BY start_time",
                (video_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def update_segment_label(self, segment_id: int, label: str):
        with self._connect() as conn:
            conn.execute("UPDATE segments SET label = ? WHERE id = ?", (label, segment_id))
