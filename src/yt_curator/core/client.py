"""
Low-level YouTube Data API v3 client wrapper.

Handles pagination, error handling, quota tracking, and batching
so the higher layers never deal with raw HTTP or page tokens.
"""

import time
from dataclasses import dataclass
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from yt_curator.core.auth import get_credentials


@dataclass
class QuotaTracker:
    """Tracks API quota unit consumption."""
    read: int = 0
    write: int = 0

    def add(self, cost: int, is_write: bool = False) -> None:
        if is_write:
            self.write += cost
        else:
            self.read += cost

    @property
    def total(self) -> int:
        return self.read + self.write

    def __str__(self) -> str:
        return f"read={self.read} write={self.write} total={self.total}"


class YouTubeClient:
    """Thread-safe wrapper around the YouTube Data API v3."""

    def __init__(self, read_only: bool = False) -> None:
        self.read_only = read_only
        self.quota = QuotaTracker()
        self._service = None

    @property
    def service(self) -> Any:
        """Lazy-build the API service object."""
        if self._service is None:
            creds: Credentials = get_credentials(read_only=self.read_only)
            self._service = build("youtube", "v3", credentials=creds)
        return self._service

    # ── Playlists ──────────────────────────────────────────────

    def list_my_playlists(self) -> list[dict]:
        """Fetch all playlists owned by the authenticated user.

        Handles pagination automatically. Returns raw API items.
        """
        items: list[dict] = []
        request = self.service.playlists().list(
            part="snippet,contentDetails,status",
            mine=True,
            maxResults=50,
        )
        while request is not None:
            self.quota.add(1)  # playlists.list costs 1
            try:
                response = request.execute()
            except HttpError as exc:
                raise RuntimeError(f"YouTube API error: {exc}") from exc
            items.extend(response.get("items", []))
            request = self.service.playlists().list_next(request, response)
        return items

    def get_playlist(self, playlist_id: str) -> dict | None:
        """Get a single playlist by ID."""
        self.quota.add(1)
        try:
            response = self.service.playlists().list(
                part="snippet,contentDetails,status",
                id=playlist_id,
            ).execute()
            items = response.get("items", [])
            return items[0] if items else None
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise RuntimeError(f"YouTube API error: {exc}") from exc

    def create_playlist(self, title: str, description: str = "",
                        privacy: str = "unlisted") -> dict:
        """Create a new playlist."""
        self.quota.add(50, is_write=True)
        body = {
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy},
        }
        try:
            return self.service.playlists().insert(
                part="snippet,status",
                body=body,
            ).execute()
        except HttpError as exc:
            raise RuntimeError(f"Failed to create playlist: {exc}") from exc

    def update_playlist(self, playlist_id: str, title: str | None = None,
                        description: str | None = None,
                        privacy: str | None = None) -> dict:
        """Update playlist metadata."""
        self.quota.add(50, is_write=True)
        # Fetch current first to preserve fields
        existing = self.get_playlist(playlist_id)
        if not existing:
            raise ValueError(f"Playlist {playlist_id} not found")
        if title:
            existing["snippet"]["title"] = title
        if description is not None:
            existing["snippet"]["description"] = description
        if privacy:
            existing["status"]["privacyStatus"] = privacy
        try:
            return self.service.playlists().update(
                part="snippet,status",
                body=existing,
            ).execute()
        except HttpError as exc:
            raise RuntimeError(f"Failed to update playlist: {exc}") from exc

    def delete_playlist(self, playlist_id: str) -> None:
        """Delete a playlist."""
        self.quota.add(50, is_write=True)
        try:
            self.service.playlists().delete(id=playlist_id).execute()
        except HttpError as exc:
            raise RuntimeError(f"Failed to delete playlist: {exc}") from exc

    # ── Playlist Items ─────────────────────────────────────────

    def list_playlist_items(self, playlist_id: str) -> list[dict]:
        """Fetch all items in a playlist (paginated)."""
        items: list[dict] = []
        request = self.service.playlistItems().list(
            part="snippet,contentDetails,status",
            playlistId=playlist_id,
            maxResults=50,
        )
        while request is not None:
            self.quota.add(1)  # playlistItems.list costs 1
            try:
                response = request.execute()
            except HttpError as exc:
                raise RuntimeError(
                    f"Failed to list items in {playlist_id}: {exc}"
                ) from exc
            items.extend(response.get("items", []))
            request = self.service.playlistItems().list_next(request, response)
        return items

    def add_video_to_playlist(self, playlist_id: str, video_id: str,
                               position: int | None = None) -> dict:
        """Add a video to a playlist."""
        self.quota.add(50, is_write=True)
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        }
        if position is not None:
            body["snippet"]["position"] = position
        try:
            return self.service.playlistItems().insert(
                part="snippet",
                body=body,
            ).execute()
        except HttpError as exc:
            raise RuntimeError(
                f"Failed to add {video_id} to {playlist_id}: {exc}"
            ) from exc

    def remove_video_from_playlist(self, playlist_item_id: str) -> None:
        """Remove a specific playlist item entry."""
        self.quota.add(50, is_write=True)
        try:
            self.service.playlistItems().delete(id=playlist_item_id).execute()
        except HttpError as exc:
            raise RuntimeError(
                f"Failed to remove item {playlist_item_id}: {exc}"
            ) from exc

    # ── Videos (status / metadata) ─────────────────────────────

    def get_video_details(self, video_ids: list[str]) -> list[dict]:
        """Fetch metadata and status for up to 50 video IDs at once."""
        items: list[dict] = []
        # Batch in chunks of 50 (API limit)
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]
            self.quota.add(1)
            try:
                response = self.service.videos().list(
                    part="snippet,contentDetails,status,statistics",
                    id=",".join(chunk),
                ).execute()
                items.extend(response.get("items", []))
            except HttpError as exc:
                raise RuntimeError(
                    f"Failed to get video details: {exc}"
                ) from exc
            if i + 50 < len(video_ids):
                time.sleep(0.1)  # gentle rate limiting
        return items
