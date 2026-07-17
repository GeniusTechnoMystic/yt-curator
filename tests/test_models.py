"""Tests for yt_curator.core.models."""

from yt_curator.core import (
    Playlist, PlaylistVideo, CurationAction,
    DuplicateGroup, DeadVideoEntry, ScanReport,
)


class TestPlaylist:
    def test_minimal(self):
        p = Playlist(id="PL_test", title="Test")
        assert p.id == "PL_test"
        assert p.title == "Test"
        assert p.privacy == "public"
        assert p.video_count == 0

    def test_full(self):
        p = Playlist(
            id="PL_full", title="Full", description="A full playlist",
            privacy="unlisted", video_count=42, channel_id="UC_xxx",
            channel_title="Test Channel", created_at="2020-01-01T00:00:00Z",
            updated_at="2020-06-01T00:00:00Z", etag="abc123",
            last_scanned="2026-07-18T00:00:00Z",
        )
        assert p.privacy == "unlisted"
        assert p.video_count == 42
        assert p.channel_title == "Test Channel"


class TestPlaylistVideo:
    def test_minimal(self):
        pv = PlaylistVideo(playlist_id="PL_test", video_id="abc123")
        assert pv.playlist_id == "PL_test"
        assert pv.video_id == "abc123"
        assert pv.status == "unknown"

    def test_full(self):
        pv = PlaylistVideo(
            playlist_id="PL_test", video_id="abc123", position=1,
            title="Test Video", channel_id="UC_xxx", channel_title="TC",
            published_at="2020-01-01", duration_seconds=120,
            status="live", added_at="2020-02-01", etag="def456",
        )
        assert pv.duration_seconds == 120
        assert pv.status == "live"


class TestCurationAction:
    def test_minimal(self):
        ca = CurationAction(action="delete_playlist")
        assert ca.action == "delete_playlist"
        assert ca.status == "done"

    def test_pending(self):
        ca = CurationAction(action="merge", status="pending")
        assert ca.status == "pending"


class TestDuplicateGroup:
    def test_empty(self):
        dg = DuplicateGroup(video_id="abc123", title="Test")
        assert dg.total_count == 0
        assert dg.playlist_names == []

    def test_with_appearances(self):
        dg = DuplicateGroup(
            video_id="abc123", title="Test",
            appearances=[
                {"playlist_id": "PL_a", "playlist_title": "A", "position": 1},
                {"playlist_id": "PL_b", "playlist_title": "B", "position": 2},
            ],
            total_count=2,
        )
        assert dg.total_count == 2
        assert dg.playlist_names == ["A", "B"]


class TestDeadVideoEntry:
    def test_basic(self):
        dve = DeadVideoEntry(
            video_id="abc123", title="Dead Vid",
            status="deleted", playlist_id="PL_a", playlist_title="My List",
        )
        assert dve.status == "deleted"
        assert dve.playlist_title == "My List"


class TestScanReport:
    def test_empty(self):
        sr = ScanReport()
        assert sr.total_playlists == 0
        assert sr.duplicate_video_ids == []

    def test_partial(self):
        sr = ScanReport(
            total_playlists=10, total_videos=500,
            live_videos=400, deleted_videos=100,
        )
        assert sr.total_playlists == 10
        assert sr.live_videos == 400
        assert sr.deleted_videos == 100