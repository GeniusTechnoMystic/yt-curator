"""Credential-free regressions for conservative mutation defaults."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from yt_curator.core.client import YouTubeClient
from yt_curator.core.curator import Curator


@pytest.mark.parametrize("dry_run", [True, False])
def test_self_merge_rejected_without_side_effects(tmp_path: Path, dry_run: bool) -> None:
    client = MagicMock(spec=YouTubeClient)
    cur = Curator(client=client, db_path=tmp_path / "inventory.db")
    try:
        db = cur._db()
        db.execute("INSERT INTO playlists(id, title) VALUES ('source', 'Source')")
        db.commit()
        with pytest.raises(ValueError, match="must differ"):
            cur.merge_playlists("source", "source", dry_run=dry_run)
        assert client.mock_calls == []
        assert cur.get_playlist_summary("source") is not None
    finally:
        cur.close()


@pytest.mark.parametrize("operation", [
    "delete_playlist", "merge_playlists",
    "remove_dead_videos", "deduplicate_playlist",
])
def test_core_mutations_default_to_dry_run(tmp_path: Path, operation: str) -> None:
    client = MagicMock(spec=YouTubeClient)
    cur = Curator(client=client, db_path=tmp_path / "inventory.db")
    try:
        db = cur._db()
        db.executescript("""
            INSERT INTO playlists(id, title) VALUES ('source', 'Source'), ('target', 'Target');
            INSERT INTO playlist_videos(playlist_id, video_id, position, status)
            VALUES ('source', 'video', 0, 'deleted');
        """)
        db.commit()
        before = (list(map(tuple, db.execute("SELECT * FROM playlists ORDER BY id"))),
                  list(map(tuple, db.execute("SELECT * FROM playlist_videos ORDER BY id"))))
        args = {"delete_playlist": ("source",), "merge_playlists": ("source", "target"),
                "remove_dead_videos": (), "deduplicate_playlist": ("source",)}
        getattr(cur, operation)(*args[operation])
        after = (list(map(tuple, db.execute("SELECT * FROM playlists ORDER BY id"))),
                 list(map(tuple, db.execute("SELECT * FROM playlist_videos ORDER BY id"))))
        assert after == before
        assert client.mock_calls == []
    finally:
        cur.close()
