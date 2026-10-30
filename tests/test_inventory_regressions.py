"""Inventory safety regressions; no credentials or external services required."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from yt_curator.core.inventory import scan_all
from yt_curator.db.schema import open_db


def playlist_item(item_id: str, video_id: str, position: int) -> dict[str, Any]:
    return {
        "id": item_id,
        "snippet": {
            "title": video_id,
            "position": position,
            "resourceId": {"videoId": video_id},
        },
        "contentDetails": {},
    }


class FakeInventoryClient:
    def __init__(self, items: list[dict[str, Any]], missing: bool = False) -> None:
        self.items = items
        self.missing = missing
        self.quota = SimpleNamespace(read=0, write=0)

    def list_my_playlists(self) -> list[dict[str, Any]]:
        return [{
            "id": "PL_test",
            "snippet": {"title": "Test"},
            "contentDetails": {"itemCount": len(self.items)},
            "status": {"privacyStatus": "private"},
        }]

    def list_playlist_items(self, playlist_id: str) -> list[dict[str, Any]]:
        assert playlist_id == "PL_test"
        return self.items

    def get_video_details(self, video_ids: list[str]) -> list[dict[str, Any]]:
        if self.missing:
            return []
        return [{
            "id": video_id,
            "status": {"privacyStatus": "public", "uploadStatus": "processed"},
            "contentDetails": {"duration": "PT1M"},
        } for video_id in video_ids]


def test_scan_preserves_repeated_occurrences(tmp_path: Path) -> None:
    path = tmp_path / "inventory.db"
    client = FakeInventoryClient([
        playlist_item("remote_a", "same_video", 0),
        playlist_item("remote_b", "same_video", 1),
    ])
    scan_all(client, db_path=path)  # type: ignore[arg-type]
    conn = open_db(path)
    try:
        rows = conn.execute("SELECT * FROM playlist_videos ORDER BY position").fetchall()
        assert len(rows) == 2
        assert [row["position"] for row in rows] == [0, 1]
        count = conn.execute("SELECT video_count FROM playlists").fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_scan_persists_remote_item_identity(tmp_path: Path) -> None:
    path = tmp_path / "inventory.db"
    client = FakeInventoryClient([playlist_item("remote_a", "video_a", 0)])
    scan_all(client, db_path=path)  # type: ignore[arg-type]
    conn = open_db(path)
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(playlist_videos)")}
        assert "playlist_item_id" in columns
        row = conn.execute("SELECT playlist_item_id FROM playlist_videos").fetchone()
        assert row[0] == "remote_a"
    finally:
        conn.close()


def test_complete_rescan_reconciles_removed_membership(tmp_path: Path) -> None:
    path = tmp_path / "inventory.db"
    client = FakeInventoryClient([
        playlist_item("remote_a", "video_a", 0),
        playlist_item("remote_b", "video_b", 1),
    ])
    scan_all(client, db_path=path)  # type: ignore[arg-type]
    client.items = [playlist_item("remote_b", "video_b", 0)]
    scan_all(client, db_path=path)  # type: ignore[arg-type]
    conn = open_db(path)
    try:
        rows = conn.execute("SELECT video_id FROM playlist_videos").fetchall()
        assert [row[0] for row in rows] == ["video_b"]
    finally:
        conn.close()


def test_omitted_video_details_are_not_proof_of_deletion(tmp_path: Path) -> None:
    path = tmp_path / "inventory.db"
    client = FakeInventoryClient([playlist_item("remote_a", "video_a", 0)], missing=True)
    scan_all(client, db_path=path)  # type: ignore[arg-type]
    conn = open_db(path)
    try:
        status = conn.execute("SELECT status FROM playlist_videos").fetchone()[0]
        assert status in {"unknown", "unavailable"}
    finally:
        conn.close()
