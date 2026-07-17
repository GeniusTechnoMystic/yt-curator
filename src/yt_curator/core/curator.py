"""
Curation engine — high-level operations that combine API calls with DB state.

All destructive operations support ``dry_run=True`` which logs what *would*
happen without executing anything.
"""

from pathlib import Path
from typing import Any

from yt_curator.core.client import YouTubeClient
from yt_curator.core.models import CurationAction, DuplicateGroup, DeadVideoEntry
from yt_curator.db.schema import open_db


class Curator:
    """High-level curation operations backed by the YouTube API + local DB."""

    def __init__(self, client: YouTubeClient | None = None,
                 db_path: Path | None = None) -> None:
        self._client = client
        self.db_path = db_path
        self._log: list[CurationAction] = []
        self._conn = open_db(db_path) if db_path else None

    @property
    def client(self) -> YouTubeClient:
        """Lazy YouTubeClient — only created when needed (i.e. not for dry-runs or reports)."""
        if self._client is None:
            self._client = YouTubeClient(read_only=False)
        return self._client

    @client.setter
    def client(self, value: YouTubeClient) -> None:
        self._client = value

    def close(self) -> None:
        """Close the database connection explicitly."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── Connection helper ──────────────────────────────────────

    def _db(self) -> Any:
        if self._conn is None:
            self._conn = open_db(self.db_path)
        return self._conn

    # ── Reporting ──────────────────────────────────────────────

    def get_playlist_summary(self, playlist_id: str) -> dict | None:
        """Get a playlist's title and video count from the local DB."""
        db = self._db()
        row = db.execute(
            "SELECT id, title, video_count, privacy FROM playlists WHERE id=?",
            (playlist_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_report(self) -> dict:
        """Generate a summary report from the DB."""
        db = self._db()
        playlists = db.execute("SELECT COUNT(*) as c FROM playlists").fetchone()["c"]
        videos = db.execute("SELECT COUNT(*) as c FROM playlist_videos").fetchone()["c"]
        live = db.execute(
            "SELECT COUNT(*) as c FROM playlist_videos WHERE status='live'"
        ).fetchone()["c"]
        deleted = db.execute(
            "SELECT COUNT(*) as c FROM playlist_videos WHERE status='deleted'"
        ).fetchone()["c"]
        private = db.execute(
            "SELECT COUNT(*) as c FROM playlist_videos WHERE status='private'"
        ).fetchone()["c"]
        empty = db.execute(
            "SELECT COUNT(*) as c FROM playlists WHERE video_count=0"
        ).fetchone()["c"]
        dupes = db.execute(
            "SELECT video_id, COUNT(DISTINCT playlist_id) as cnt "
            "FROM playlist_videos GROUP BY video_id HAVING cnt > 1 "
            "ORDER BY cnt DESC"
        ).fetchall()

        return {
            "playlists": playlists,
            "videos": videos,
            "live": live,
            "deleted": deleted,
            "private": private,
            "empty_playlists": empty,
            "duplicate_video_ids": len([r for r in dupes]),
            "top_dupes": [
                {"video_id": r["video_id"], "appearances": r["cnt"]}
                for r in dupes[:20]
            ],
        }

    def get_duplicates(self, min_appearances: int = 2) -> list[DuplicateGroup]:
        """Return videos that appear in multiple playlists."""
        db = self._db()
        # Find dupe video IDs
        dupes = db.execute(
            "SELECT video_id FROM playlist_videos "
            "GROUP BY video_id HAVING COUNT(DISTINCT playlist_id) >= ?",
            (min_appearances,),
        ).fetchall()

        groups: list[DuplicateGroup] = []
        for row in dupes:
            vid = row["video_id"]
            appearances = db.execute(
                "SELECT pv.playlist_id, p.title as playlist_title, pv.position "
                "FROM playlist_videos pv "
                "JOIN playlists p ON p.id = pv.playlist_id "
                "WHERE pv.video_id = ? "
                "ORDER BY p.title",
                (vid,),
            ).fetchall()
            title = appearances[0]["playlist_title"] if appearances else ""
            # Get video title from any playlist_videos row
            vt = db.execute(
                "SELECT title FROM playlist_videos WHERE video_id=? LIMIT 1",
                (vid,),
            ).fetchone()
            video_title = vt["title"] if vt else ""
            groups.append(DuplicateGroup(
                video_id=vid,
                title=video_title,
                appearances=[dict(a) for a in appearances],
                total_count=len(appearances),
            ))
        return groups

    def get_dead_videos(self) -> list[DeadVideoEntry]:
        """Return videos with non-live statuses."""
        db = self._db()
        rows = db.execute(
            "SELECT pv.video_id, pv.title, pv.status, "
            "       pv.playlist_id, p.title as playlist_title "
            "FROM playlist_videos pv "
            "JOIN playlists p ON p.id = pv.playlist_id "
            "WHERE pv.status IN ('deleted', 'private', 'blocked') "
            "ORDER BY pv.status"
        ).fetchall()
        return [
            DeadVideoEntry(
                video_id=r["video_id"],
                title=r["title"],
                status=r["status"],
                playlist_id=r["playlist_id"],
                playlist_title=r["playlist_title"],
            )
            for r in rows
        ]

    # ── Destructive operations ─────────────────────────────────

    def delete_playlist(self, playlist_id: str,
                         dry_run: bool = False) -> CurationAction:
        """Delete a playlist and all its items from the DB + YouTube."""
        db = self._db()
        pl = db.execute("SELECT title FROM playlists WHERE id=?",
                        (playlist_id,)).fetchone()
        title = pl["title"] if pl else "unknown"
        action = CurationAction(
            action="delete_playlist",
            source_playlist=playlist_id,
            playlist_title=title,
            status="pending" if dry_run else "done",
        )
        if not dry_run:
            if pl:
                db.execute("DELETE FROM playlist_videos WHERE playlist_id=?",
                           (playlist_id,))
                db.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))
                db.commit()
            self.client.delete_playlist(playlist_id)
            _log_curation(db, action)
        self._log.append(action)
        return action

    def merge_playlists(self, source_id: str, target_id: str,
                         dry_run: bool = False) -> list[CurationAction]:
        """Move all videos from source playlist into target, then delete source.

        Skips videos already present in the target (by video_id).
        Returns a list of actions performed.
        """
        actions: list[CurationAction] = []
        db = self._db()

        src = db.execute("SELECT title FROM playlists WHERE id=?",
                         (source_id,)).fetchone()
        tgt = db.execute("SELECT title FROM playlists WHERE id=?",
                         (target_id,)).fetchone()
        src_title = src["title"] if src else source_id
        tgt_title = tgt["title"] if tgt else target_id

        # Get existing video IDs in target
        existing = {
            r["video_id"]
            for r in db.execute(
                "SELECT video_id FROM playlist_videos WHERE playlist_id=?",
                (target_id,),
            ).fetchall()
        }

        # Get source videos
        source_videos = db.execute(
            "SELECT video_id, title FROM playlist_videos WHERE playlist_id=?",
            (source_id,),
        ).fetchall()

        moved = 0
        skipped = 0
        for sv in source_videos:
            if sv["video_id"] in existing:
                skipped += 1
                continue
            if not dry_run:
                self.client.add_video_to_playlist(target_id, sv["video_id"])
                db.execute(
                    "DELETE FROM playlist_videos WHERE playlist_id=? AND video_id=?",
                    (source_id, sv["video_id"]),
                )
            moved += 1

        # Delete source playlist
        if not dry_run:
            self.client.delete_playlist(source_id)
            db.execute("DELETE FROM playlists WHERE id=?", (source_id,))
            db.commit()

        action = CurationAction(
            action="merge",
            source_playlist=source_id,
            target_playlist=target_id,
            playlist_title=f"{src_title} → {tgt_title}",
            status="done" if not dry_run else "pending",
            note=f"Moved {moved}, skipped {skipped} (already in target)",
        )
        if not dry_run:
            _log_curation(db, action)
        self._log.append(action)
        actions.append(action)
        return actions

    def remove_dead_videos(self, dry_run: bool = False) -> list[CurationAction]:
        """Remove all dead/private/blocked videos from their playlists."""
        db = self._db()
        dead = db.execute(
            "SELECT pv.video_id, pv.playlist_id, pv.id as item_id "
            "FROM playlist_videos pv "
            "WHERE pv.status IN ('deleted', 'private', 'blocked')"
        ).fetchall()

        actions: list[CurationAction] = []
        for d in dead:
            if not dry_run:
                self.client.remove_video_from_playlist(str(d["item_id"]))
                db.execute(
                    "DELETE FROM playlist_videos WHERE id=?",
                    (d["item_id"],),
                )
            actions.append(CurationAction(
                action="remove_video",
                source_playlist=d["playlist_id"],
                video_id=d["video_id"],
                status="done" if not dry_run else "pending",
                note=f"Removed dead video",
            ))

        if not dry_run and actions:
            db.commit()
            for a in actions:
                _log_curation(db, a)

        self._log.extend(actions)
        return actions

    def deduplicate_playlist(self, playlist_id: str,
                              dry_run: bool = False) -> list[CurationAction]:
        """Remove duplicate videos *within* a single playlist.

        Keeps the first occurrence (lowest position), removes later ones.
        """
        db = self._db()
        # Find duplicates
        dupes = db.execute(
            "SELECT video_id, MIN(position) as keep_pos "
            "FROM playlist_videos "
            "WHERE playlist_id=? "
            "GROUP BY video_id "
            "HAVING COUNT(*) > 1",
            (playlist_id,),
        ).fetchall()

        actions: list[CurationAction] = []
        for d in dupes:
            to_remove = db.execute(
                "SELECT id FROM playlist_videos "
                "WHERE playlist_id=? AND video_id=? AND position > ?",
                (playlist_id, d["video_id"], d["keep_pos"]),
            ).fetchall()
            for row in to_remove:
                if not dry_run:
                    self.client.remove_video_from_playlist(str(row["id"]))
                    db.execute("DELETE FROM playlist_videos WHERE id=?",
                               (row["id"],))
                actions.append(CurationAction(
                    action="remove_duplicate",
                    source_playlist=playlist_id,
                    video_id=d["video_id"],
                    status="done" if not dry_run else "pending",
                    note="Duplicate removed (kept earliest)",
                ))

        if not dry_run and actions:
            db.commit()
            for a in actions:
                _log_curation(db, a)

        self._log.extend(actions)
        return actions


def _log_curation(db: Any, action: CurationAction) -> None:
    """Write an action to the curation_log table."""
    db.execute(
        "INSERT INTO curation_log (action, source_playlist, target_playlist, "
        "video_id, playlist_title, status, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (action.action, action.source_playlist, action.target_playlist,
         action.video_id, action.playlist_title, action.status, action.note),
    )
    db.commit()
