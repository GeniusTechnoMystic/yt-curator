"""Tests for yt_curator.core.curator."""

import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock

from yt_curator.core.curator import Curator
from yt_curator.core.client import YouTubeClient
from yt_curator.db.schema import open_db


class TestCuratorEmpty:
    """Tests against an empty database."""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.cur = Curator(db_path=self.tmp)

    def teardown_method(self):
        self.cur.close()
        os.unlink(self.tmp)

    def test_report_empty(self):
        r = self.cur.get_report()
        assert r["playlists"] == 0
        assert r["videos"] == 0
        assert r["live"] == 0
        assert r["empty_playlists"] == 0

    def test_playlist_summary_missing(self):
        assert self.cur.get_playlist_summary("PL_nonexistent") is None

    def test_get_duplicates_empty(self):
        assert self.cur.get_duplicates() == []

    def test_get_dead_videos_empty(self):
        assert self.cur.get_dead_videos() == []


class TestCuratorSeeded:
    """Tests against a seeded database with known data."""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.conn = open_db(self.tmp)
        self._seed()
        self.conn.close()
        self.cur = Curator(db_path=self.tmp)

    def teardown_method(self):
        self.cur.close()
        try:
            os.unlink(self.tmp)
        except PermissionError:
            pass

    def _seed(self):
        """Seed 3 playlists with 8 videos, some dead, some duplicated."""
        self.conn.executescript("""
            INSERT INTO playlists (id, title, video_count) VALUES
                ('PL_a', 'Active Playlist', 3),
                ('PL_b', 'Dead Collection', 3),
                ('PL_c', 'Solo Playlist', 2);

            INSERT INTO playlist_videos (playlist_id, video_id, position, title, status) VALUES
                ('PL_a', 'vid1', 1, 'Video 1', 'live'),
                ('PL_a', 'vid2', 2, 'Video 2', 'live'),
                ('PL_a', 'vid3', 3, 'Video 3', 'live'),
                ('PL_b', 'vid1', 1, 'Video 1', 'live'),       -- duplicate of PL_a.vid1
                ('PL_b', 'vid4', 2, 'Video 4', 'deleted'),    -- dead
                ('PL_b', 'vid5', 3, 'Video 5', 'private'),    -- private
                ('PL_c', 'vid1', 1, 'Video 1', 'live'),       -- duplicate in 3 playlists
                ('PL_c', 'vid6', 2, 'Video 6', 'blocked');    -- blocked
        """)
        self.conn.commit()

    def test_report(self):
        r = self.cur.get_report()
        assert r["playlists"] == 3
        assert r["videos"] == 8
        assert r["live"] == 5
        assert r["deleted"] == 1
        assert r["private"] == 1
        assert r["duplicate_video_ids"] == 1  # vid1 appears in 3 playlists

    def test_playlist_summary_found(self):
        s = self.cur.get_playlist_summary("PL_a")
        assert s is not None
        assert s["title"] == "Active Playlist"

    def test_get_duplicates(self):
        dupes = self.cur.get_duplicates(min_appearances=2)
        assert len(dupes) == 1
        assert dupes[0].video_id == "vid1"
        assert dupes[0].total_count == 3

    def test_get_duplicates_min_3(self):
        dupes = self.cur.get_duplicates(min_appearances=3)
        assert len(dupes) == 1  # vid1 appears in all 3
        assert dupes[0].total_count == 3

    def test_get_dead_videos(self):
        dead = self.cur.get_dead_videos()
        assert len(dead) == 3  # vid4 (deleted), vid5 (private), vid6 (blocked)
        statuses = {d.status for d in dead}
        assert "deleted" in statuses
        assert "private" in statuses
        assert "blocked" in statuses


class TestCuratorDryRun:
    """Tests that dry-run operations don't call the YouTube API."""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.conn = open_db(self.tmp)
        self.conn.executescript("""
            INSERT INTO playlists (id, title, video_count) VALUES
                ('PL_a', 'Source', 2),
                ('PL_b', 'Target', 0);
            INSERT INTO playlist_videos (playlist_id, video_id, position, title, status) VALUES
                ('PL_a', 'vid1', 1, 'Video 1', 'live'),
                ('PL_a', 'vid2', 2, 'Video 2', 'live');
        """)
        self.conn.commit()
        self.conn.close()

        # Create a mock client that raises if called
        self.mock_client = MagicMock(spec=YouTubeClient)
        self.cur = Curator(client=self.mock_client, db_path=self.tmp)

    def teardown_method(self):
        self.cur.close()
        os.unlink(self.tmp)

    def test_dry_run_delete_does_not_call_api(self):
        result = self.cur.delete_playlist("PL_a", dry_run=True)
        assert result.status == "pending"
        self.mock_client.delete_playlist.assert_not_called()

    def test_dry_run_merge_does_not_call_api(self):
        results = self.cur.merge_playlists("PL_a", "PL_b", dry_run=True)
        assert len(results) == 1
        assert results[0].status == "pending"
        self.mock_client.add_video_to_playlist.assert_not_called()
        self.mock_client.delete_playlist.assert_not_called()

    def test_dry_run_dedup_does_not_call_api(self):
        # Add a duplicate within PL_a
        self.cur._db().execute(
            "INSERT INTO playlist_videos (playlist_id, video_id, position, title, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("PL_a", "vid1", 3, "Video 1 copy", "live"),
        )
        self.cur._db().commit()

        results = self.cur.deduplicate_playlist("PL_a", dry_run=True)
        assert len(results) == 1  # Should find 1 duplicate to remove
        assert results[0].status == "pending"
        self.mock_client.remove_video_from_playlist.assert_not_called()

    def test_dry_run_remove_dead_does_not_call_api(self):
        self.cur._db().execute(
            "UPDATE playlist_videos SET status='deleted' WHERE video_id='vid2'"
        )
        self.cur._db().commit()

        results = self.cur.remove_dead_videos(dry_run=True)
        assert len(results) == 1
        self.mock_client.remove_video_from_playlist.assert_not_called()