"""Tests for yt_curator.db.schema."""

import tempfile
import os
from pathlib import Path

from yt_curator.db.schema import open_db, get_db_path


class TestSchema:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.conn = open_db(self.tmp)

    def teardown_method(self):
        self.conn.close()
        os.unlink(self.tmp)

    def _tables(self):
        return [
            r["name"] for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]

    def test_tables_created(self):
        tables = self._tables()
        assert "playlists" in tables
        assert "playlist_videos" in tables
        assert "curation_log" in tables

    def test_indexes_created(self):
        indexes = [
            r["name"] for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
            ).fetchall()
        ]
        assert "idx_pv_video" in indexes
        assert "idx_pv_playlist" in indexes
        assert "idx_pv_status" in indexes
        assert "idx_cl_action" in indexes
        assert "idx_cl_time" in indexes

    def test_playlist_crud(self):
        """Insert, read, update, and delete a playlist."""
        self.conn.execute(
            "INSERT INTO playlists (id, title, video_count, privacy) "
            "VALUES (?, ?, ?, ?)",
            ("PL_test", "Test Playlist", 5, "public"),
        )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM playlists WHERE id=?", ("PL_test",)
        ).fetchone()
        assert row["title"] == "Test Playlist"
        assert row["video_count"] == 5

        # Update
        self.conn.execute(
            "UPDATE playlists SET video_count=? WHERE id=?",
            (10, "PL_test"),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT video_count FROM playlists WHERE id=?", ("PL_test",)
        ).fetchone()
        assert row["video_count"] == 10

    def test_playlist_video_crud(self):
        """Insert a playlist video, verify cascade delete."""
        self.conn.execute(
            "INSERT INTO playlists (id, title) VALUES (?, ?)",
            ("PL_test", "Test"),
        )
        self.conn.execute(
            "INSERT INTO playlist_videos (playlist_id, video_id, position, title) "
            "VALUES (?, ?, ?, ?)",
            ("PL_test", "vid123", 1, "Video 1"),
        )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM playlist_videos WHERE video_id=?", ("vid123",)
        ).fetchone()
        assert row["playlist_id"] == "PL_test"
        assert row["position"] == 1

        # Cascade delete
        self.conn.execute("DELETE FROM playlists WHERE id=?", ("PL_test",))
        self.conn.commit()
        remaining = self.conn.execute(
            "SELECT COUNT(*) as c FROM playlist_videos WHERE video_id=?", ("vid123",)
        ).fetchone()
        assert remaining["c"] == 0

    def test_unique_video_per_playlist(self):
        """A video can only appear once per playlist."""
        self.conn.execute(
            "INSERT INTO playlists (id, title) VALUES (?, ?)",
            ("PL_test", "Test"),
        )
        self.conn.execute(
            "INSERT INTO playlist_videos (playlist_id, video_id, position) "
            "VALUES (?, ?, ?)",
            ("PL_test", "vid123", 1),
        )
        import sqlite3
        try:
            self.conn.execute(
                "INSERT INTO playlist_videos (playlist_id, video_id, position) "
                "VALUES (?, ?, ?)",
                ("PL_test", "vid123", 2),
            )
            assert False, "Should have raised IntegrityError"
        except sqlite3.IntegrityError:
            pass  # Expected

    def test_curation_log(self):
        self.conn.execute(
            "INSERT INTO curation_log (action, source_playlist, note) "
            "VALUES (?, ?, ?)",
            ("delete_playlist", "PL_test", "Test deletion"),
        )
        row = self.conn.execute(
            "SELECT * FROM curation_log WHERE action=?", ("delete_playlist",)
        ).fetchone()
        assert row["source_playlist"] == "PL_test"
        assert row["note"] == "Test deletion"
        assert row["timestamp"]  # Should have default value


class TestGetDbPath:
    def test_default_path(self):
        path = get_db_path()
        assert path.name == "inventory.db"
        assert ".config" in str(path)
        assert "yt-curator" in str(path)

    def test_custom_dir(self):
        path = get_db_path(Path("/tmp/custom"))
        assert path.parent == Path("/tmp/custom")
        assert path.name == "inventory.db"