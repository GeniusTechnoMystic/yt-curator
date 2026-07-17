"""
Inventory scanner — full playlist + item scan into SQLite.

Orchestrates the YouTube API calls to enumerate every playlist and
every video, then persists into the local DB for offline curation.
"""

import logging
from datetime import datetime

logger = logging.getLogger("yt-curator.inventory")
from pathlib import Path
from typing import Any

from yt_curator.core.client import YouTubeClient
from yt_curator.core.models import Playlist, PlaylistVideo, ScanReport
from yt_curator.db.schema import open_db


def scan_all(client: YouTubeClient, db_path: str | Path | None = None) -> ScanReport:
    """Full inventory scan: all playlists → all items → video status.

    Returns a ScanReport with counts and duplicate info.
    """
    conn = open_db(db_path)
    report = ScanReport()

    # ── 1. Fetch all playlists ──
    logger.info("Fetching all playlists...")
    raw_playlists = client.list_my_playlists()
    report.total_playlists = len(raw_playlists)

    for item in raw_playlists:
        _upsert_playlist(conn, item)

    # ── 2. Fetch all playlist items ──
    logger.info("Fetching items for %d playlists...", len(raw_playlists))
    all_video_ids: set[str] = set()
    cursor = conn.execute("SELECT id FROM playlists")
    playlist_rows = cursor.fetchall()

    for idx, row in enumerate(playlist_rows):
        pid = row["id"]
        items = client.list_playlist_items(pid)
        video_ids_in_playlist: set[str] = set()
        for pl_item in items:
            video_id = _upsert_playlist_item(conn, pid, pl_item)
            if video_id:
                video_ids_in_playlist.add(video_id)
                all_video_ids.add(video_id)
                report.total_videos += 1
        # Track playlists with no videos
        if not video_ids_in_playlist:
            report.empty_playlists += 1

        # Also update video_count from reality
        conn.execute(
            "UPDATE playlists SET video_count = ? WHERE id = ?",
            (len(video_ids_in_playlist), pid),
        )

        if (idx + 1) % 50 == 0:
            logger.info("  ... scanned %d/%d playlists", idx + 1, len(playlist_rows))
            conn.commit()

    conn.commit()
    logger.info("  ... scanned %d playlists total", len(playlist_rows))

    # ── 3. Check video status ──
    report = _check_video_statuses(client, conn, report, list(all_video_ids))

    # ── 4. Find duplicates ──
    report = _find_duplicates_in_db(conn, report)

    # Update last_scanned
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE playlists SET last_scanned = ?", (now,))
    conn.commit()
    conn.close()

    report.quota_used_read = client.quota.read
    report.quota_used_write = client.quota.write
    return report


def _upsert_playlist(conn: Any, item: dict) -> None:
    """Insert or update a playlist row."""
    sid = item.get("snippet", {})
    cd = item.get("contentDetails", {})
    st = item.get("status", {})
    conn.execute(
        """
        INSERT INTO playlists (id, title, description, privacy, video_count,
                               channel_id, channel_title, created_at, updated_at, etag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, description=excluded.description,
            privacy=excluded.privacy, video_count=excluded.video_count,
            channel_id=excluded.channel_id, channel_title=excluded.channel_title,
            updated_at=excluded.updated_at, etag=excluded.etag
        """,
        (
            item["id"],
            sid.get("title", ""),
            sid.get("description", ""),
            st.get("privacyStatus", "public"),
            cd.get("itemCount", 0),
            sid.get("channelId", ""),
            sid.get("channelTitle", ""),
            sid.get("publishedAt", ""),      # created_at: playlist snippet.publishedAt
            sid.get("publishedAt", ""),      # updated_at: playlists only have publishedAt, not separate updatedAt
            item.get("etag", ""),
        ),
    )


def _upsert_playlist_item(conn: Any, playlist_id: str, item: dict) -> str | None:
    """Insert or update a playlist video row. Returns the video_id or None."""
    sid = item.get("snippet", {})
    cd = item.get("contentDetails", {})
    rid = sid.get("resourceId", {})
    video_id = rid.get("videoId")

    if not video_id:
        return None

    conn.execute(
        """
        INSERT INTO playlist_videos (playlist_id, video_id, position, title,
                                     channel_id, channel_title, published_at, added_at, etag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(playlist_id, video_id) DO UPDATE SET
            position=excluded.position, title=excluded.title,
            channel_id=excluded.channel_id, channel_title=excluded.channel_title,
            added_at=excluded.added_at, etag=excluded.etag
        """,
        (
            playlist_id,
            video_id,
            sid.get("position", 0),
            sid.get("title", ""),
            sid.get("videoOwnerChannelId", ""),
            sid.get("videoOwnerChannelTitle", ""),
            cd.get("videoPublishedAt", ""),
            sid.get("publishedAt", ""),
            item.get("etag", ""),
        ),
    )
    return video_id


def _check_video_statuses(
    client: YouTubeClient, conn: Any, report: ScanReport, video_ids: list[str]
) -> ScanReport:
    """Batch-check video status and update the DB."""
    logger.info("Checking status for %d videos...", len(video_ids))

    if not video_ids:
        return report

    batch_size = 50
    for i in range(0, len(video_ids), batch_size):
        chunk = video_ids[i:i + batch_size]
        details = client.get_video_details(chunk)
        found_ids = {d["id"] for d in details}

        # Check actual status for returned videos (live, private, blocked)
        for d in details:
            vid = d["id"]
            dur_sec = _parse_duration(
                d.get("contentDetails", {}).get("duration", "PT0S")
            )
            vstatus = d.get("status", {})
            privacy = vstatus.get("privacyStatus", "public")
            upload_status = vstatus.get("uploadStatus", "processed")
            if privacy == "private":
                actual_status = "private"
                report.private_videos += 1
            elif upload_status == "rejected":
                actual_status = "blocked"
                report.blocked_videos += 1
            else:
                actual_status = "live"
                report.live_videos += 1
            conn.execute(
                "UPDATE playlist_videos SET status=?, duration_seconds=? WHERE video_id=?",
                (actual_status, dur_sec, vid),
            )

        # Videos NOT returned by the API are genuinely deleted
        missing = set(chunk) - found_ids
        for vid in missing:
            report.deleted_videos += 1
            conn.execute(
                "UPDATE playlist_videos SET status='deleted' WHERE video_id=?",
                (vid,),
            )

        if (i + batch_size) % 500 == 0:
            logger.info("  ... checked %d/%d videos", min(i + batch_size, len(video_ids)), len(video_ids))
            conn.commit()

    conn.commit()
    return report


def _find_duplicates_in_db(conn: Any, report: ScanReport) -> ScanReport:
    """Find video_ids that appear in more than one playlist."""
    cursor = conn.execute(
        """
        SELECT video_id, title, COUNT(DISTINCT playlist_id) as cnt
        FROM playlist_videos
        GROUP BY video_id
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 1000
        """
    )
    rows = cursor.fetchall()
    report.duplicate_video_ids = [r["video_id"] for r in rows]
    return report


def _parse_duration(iso_duration: str) -> int:
    """Convert ISO 8601 duration (PT1H2M3S) to seconds."""
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return 0
    h, m, s = [int(g) if g else 0 for g in match.groups()]
    return h * 3600 + m * 60 + s
