"""
Data models for yt-curator.

Plain dataclasses used across all layers — CLI, MCP, and library API.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Playlist:
    """A YouTube playlist."""
    id: str
    title: str
    description: str = ""
    privacy: Literal["public", "unlisted", "private"] = "public"
    video_count: int = 0
    channel_id: str = ""
    channel_title: str = ""
    created_at: str = ""
    updated_at: str = ""
    etag: str = ""
    last_scanned: str = ""


@dataclass
class PlaylistVideo:
    """A single video entry within a playlist."""
    playlist_id: str
    video_id: str
    position: int = 0
    title: str = ""
    channel_id: str = ""
    channel_title: str = ""
    published_at: str = ""
    duration_seconds: int = 0
    status: Literal["live", "deleted", "private", "blocked", "unknown"] = "unknown"
    added_at: str = ""
    etag: str = ""


@dataclass
class CurationAction:
    """A curation operation that was (or will be) performed."""
    action: str  # delete_playlist / merge / move / create / remove_video
    source_playlist: str = ""
    target_playlist: str = ""
    video_id: str = ""
    playlist_title: str = ""
    status: Literal["pending", "done", "rolled_back", "error"] = "done"
    note: str = ""


@dataclass
class DuplicateGroup:
    """A video that appears in multiple playlists."""
    video_id: str
    title: str
    appearances: list[dict] = field(default_factory=list)  # [{playlist_id, playlist_title, position}]
    total_count: int = 0

    @property
    def playlist_names(self) -> list[str]:
        return [a["playlist_title"] for a in self.appearances]


@dataclass
class DeadVideoEntry:
    """A video that is no longer available."""
    video_id: str
    title: str
    status: str  # deleted / private / blocked
    playlist_id: str
    playlist_title: str


@dataclass
class ScanReport:
    """Summary of a full inventory scan."""
    total_playlists: int = 0
    total_videos: int = 0
    live_videos: int = 0
    deleted_videos: int = 0
    private_videos: int = 0
    blocked_videos: int = 0
    unknown_videos: int = 0
    empty_playlists: int = 0
    duplicate_video_ids: list[str] = field(default_factory=list)
    quota_used_read: int = 0
    quota_used_write: int = 0
