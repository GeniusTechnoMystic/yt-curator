"""
SQLite schema for yt-curator inventory database.

Stores a local replica of all playlist metadata and item contents so
curation operations can run without repeated API calls.
"""

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS playlists (
    id              TEXT PRIMARY KEY,          -- PL_xxxxxxxxxx
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    privacy         TEXT DEFAULT 'public',     -- public / unlisted / private
    video_count     INTEGER DEFAULT 0,
    channel_id      TEXT DEFAULT '',
    channel_title   TEXT DEFAULT '',
    created_at      TEXT,                      -- ISO 8601
    updated_at      TEXT,
    etag            TEXT DEFAULT '',
    last_scanned    TEXT DEFAULT ''            -- when we last verified this
);

CREATE TABLE IF NOT EXISTS playlist_videos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id     TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    video_id        TEXT NOT NULL,             -- xxxxxxxxxxx
    position        INTEGER DEFAULT 0,
    title           TEXT DEFAULT '',
    channel_id      TEXT DEFAULT '',
    channel_title   TEXT DEFAULT '',
    published_at    TEXT DEFAULT '',
    duration_seconds INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'unknown',    -- live / deleted / private / blocked / unknown
    added_at        TEXT DEFAULT '',           -- when added to the playlist
    etag            TEXT DEFAULT '',
    UNIQUE(playlist_id, video_id)
);

CREATE TABLE IF NOT EXISTS curation_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action          TEXT NOT NULL,             -- delete_playlist / merge / move / create / remove_video
    source_playlist TEXT DEFAULT '',
    target_playlist TEXT DEFAULT '',
    video_id        TEXT DEFAULT '',
    playlist_title  TEXT DEFAULT '',
    status          TEXT DEFAULT 'done',       -- pending / done / rolled_back / error
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    note            TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_pv_video    ON playlist_videos(video_id);
CREATE INDEX IF NOT EXISTS idx_pv_playlist ON playlist_videos(playlist_id);
CREATE INDEX IF NOT EXISTS idx_pv_status   ON playlist_videos(status);
CREATE INDEX IF NOT EXISTS idx_cl_action   ON curation_log(action);
CREATE INDEX IF NOT EXISTS idx_cl_time     ON curation_log(timestamp);
"""


def get_db_path(db_dir: Path | None = None) -> Path:
    """Return path to the inventory database."""
    if db_dir is None:
        db_dir = Path.home() / ".config" / "yt-curator"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "inventory.db"


def open_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (and initialise) the inventory database."""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
