"""
MCP server for yt-curator.

Exposes all curation operations as MCP tools so that Hermes, Claude Desktop,
or any MCP client can manage YouTube playlists conversationally.

Run in stdio mode (default, for Claude Desktop / Hermes):
    yt-curator serve-mcp

Run in SSE mode (for gateway registration):
    yt-curator serve-mcp --host 0.0.0.0 --port 39401
"""

import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from yt_curator.core.auth import get_credentials, has_valid_token, TOKEN_FILE, CLIENT_SECRET_FILE
from yt_curator.core.client import YouTubeClient
from yt_curator.core.inventory import scan_all
from yt_curator.core.curator import Curator
from yt_curator.core.dedup import find_cross_playlist_duplicates, suggest_merge_targets

# Create MCP server
mcp = FastMCP(
    "yt-curator",
    instructions="YouTube playlist curation engine — inventory, deduplicate, merge, clean, and reorganise playlists",
)


# ── Shared helpers ─────────────────────────────────────────────

def _curator(db_path: str | None = None) -> Curator:
    """Get a Curator instance, ensuring auth is set up."""
    db = Path(db_path) if db_path else None
    return Curator(db_path=db)


def _format_playlist(item: dict) -> str:
    """Format a playlist item dict as a readable string."""
    snippet = item.get("snippet", {})
    status = item.get("status", {})
    content = item.get("contentDetails", {})
    return (
        f"• {snippet.get('title', 'Untitled')} (`{item['id']}`)\n"
        f"  {snippet.get('description', '')[:120]}\n"
        f"  Videos: {content.get('itemCount', '?')}  |  "
        f"Privacy: {status.get('privacyStatus', '?')}"
    )


# ── Tools ──────────────────────────────────────────────────────

@mcp.tool()
def list_playlists(db_path: str | None = None) -> str:
    """List all playlists in the inventory database.

    Run ``scan_inventory()`` first if the database is empty.
    """
    cur = _curator(db_path)
    db = cur._db()
    rows = db.execute(
        "SELECT id, title, video_count, privacy FROM playlists ORDER BY title"
    ).fetchall()

    if not rows:
        return "No playlists in database. Run `scan_inventory()` first."

    lines = [f"Found {len(rows)} playlists:\n"]
    for r in rows:
        icon = {"public": "🌐", "unlisted": "🔗", "private": "🔒"}
        lines.append(
            f"  {icon.get(r['privacy'], '•')} {r['title']} "
            f"(`{r['id']}`) — {r['video_count']} videos"
        )
    return "\n".join(lines)


@mcp.tool()
def get_playlist_contents(playlist_id: str, db_path: str | None = None) -> str:
    """List all videos in a specific playlist."""
    cur = _curator(db_path)
    db = cur._db()
    pl = db.execute(
        "SELECT title FROM playlists WHERE id=?", (playlist_id,)
    ).fetchone()

    videos = db.execute(
        "SELECT video_id, title, status, position, channel_title "
        "FROM playlist_videos WHERE playlist_id=? "
        "ORDER BY position",
        (playlist_id,),
    ).fetchall()

    title = pl["title"] if pl else playlist_id
    if not videos:
        return f"Playlist \"{title}\" is empty or not scanned yet."

    lines = [f"\"{title}\" ({len(videos)} videos):\n"]
    for v in videos:
        status_icon = {
            "live": "✅", "deleted": "💀", "private": "🔒",
            "blocked": "🚫", "unknown": "❓",
        }
        lines.append(
            f"  {status_icon.get(v['status'], '•')} {v['title'][:80]} "
            f"(`{v['video_id']}`) — {v['status']}"
        )
    return "\n".join(lines)


@mcp.tool()
def scan_inventory(read_only: bool = False, db_path: str | None = None) -> str:
    """Run a full inventory scan: list all playlists, all items, check video status.

    This is the primary data-collection command. Run this first before any
    curation operations. Uses the YouTube Data API — consumes ~1,200 quota units
    for a typical 900-playlist account.
    """
    if not has_valid_token():
        return (
            "OAuth token not found. Run `auth_setup()` first, or use the CLI:\n"
            f"  yt-curator auth\n"
            f"(needs client_secret.json at {CLIENT_SECRET_FILE})"
        )

    client = YouTubeClient(read_only=read_only)
    db = Path(db_path) if db_path else None
    report = scan_all(client, db_path=db)

    return (
        f"## Inventory Complete\n\n"
        f"| Metric | Count |\n"
        f"|--------|------:|\n"
        f"| Playlists scanned | {report.total_playlists} |\n"
        f"| Videos found | {report.total_videos} |\n"
        f"| **Live** | **{report.live_videos}** ✅ |\n"
        f"| Deleted | {report.deleted_videos} 💀 |\n"
        f"| Private | {report.private_videos} 🔒 |\n"
        f"| Empty playlists | {report.empty_playlists} |\n"
        f"| Cross-playlist duplicates | {len(report.duplicate_video_ids)} |\n"
        f"| Quota consumed | {client.quota} |\n"
    )


@mcp.tool()
def curation_report(db_path: str | None = None) -> str:
    """Generate a summary report from the inventory database.

    Shows playlist/video counts, dead videos, duplicates, and empty playlists.
    Requires that ``scan_inventory()`` has been run first.
    """
    cur = _curator(db_path)
    r = cur.get_report()
    dead_count = r["deleted"] + r["private"]

    return (
        f"## Curation Report\n\n"
        f"| Metric | Count |\n"
        f"|--------|------:|\n"
        f"| Total playlists | {r['playlists']} |\n"
        f"| Total videos | {r['videos']} |\n"
        f"| **Live** | **{r['live']}** ✅ |\n"
        f"| Deleted | {r['deleted']} 💀 |\n"
        f"| Private | {r['private']} 🔒 |\n"
        f"| Empty playlists | {r['empty_playlists']} |\n"
        f"| Cross-playlist duplicates | {r['duplicate_video_ids']} |\n\n"
        f"{'⚠️  ' if dead_count else ''}"
        f"Action items: {dead_count} dead videos, "
        f"{r['empty_playlists']} empty playlists, "
        f"{r['duplicate_video_ids']} cross-duplicates"
    )


@mcp.tool()
def find_duplicates(min_appearances: int = 2, db_path: str | None = None) -> str:
    """Find videos that appear in multiple playlists.

    Args:
        min_appearances: Minimum number of playlists a video must appear in
            (default: 2, meaning any duplication at all).
    """
    groups = find_cross_playlist_duplicates(
        Path(db_path) if db_path else None,
        min_appearances=min_appearances,
    )

    if not groups:
        return "✅ No cross-playlist duplicates found."

    lines = [f"### Cross-Playlist Duplicates (≥{min_appearances} appearances)\n"]
    for g in groups[:25]:
        names = ", ".join(g.playlist_names[:4])
        if len(g.playlist_names) > 4:
            names += f" …(+{len(g.playlist_names) - 4})"
        lines.append(
            f"- {g.title[:80]} (`{g.video_id}`)\n"
            f"  Appears in {g.total_count} playlists: {names}"
        )
    if len(groups) > 25:
        lines.append(f"\n… and {len(groups) - 25} more.")
    return "\n".join(lines)


@mcp.tool()
def find_dead_videos(db_path: str | None = None) -> str:
    """Find deleted, private, or blocked videos across all playlists."""
    cur = _curator(db_path)
    dead = cur.get_dead_videos()

    if not dead:
        return "✅ No dead videos found."

    counts = {}
    for d in dead:
        counts[d.status] = counts.get(d.status, 0) + 1

    lines = [
        f"### Dead Videos ({len(dead)} total)\n",
        f"- Deleted: {counts.get('deleted', 0)} 💀",
        f"- Private: {counts.get('private', 0)} 🔒",
        f"- Blocked: {counts.get('blocked', 0)} 🚫\n",
    ]
    for d in dead[:20]:
        lines.append(
            f"- [{d.status}] {d.title[:70]} in \"{d.playlist_title[:40]}\""
        )
    if len(dead) > 20:
        lines.append(f"\n… and {len(dead) - 20} more.")
    lines.append("\nUse `remove_dead_videos(dry_run=True)` to preview removal.")
    return "\n".join(lines)


@mcp.tool()
def find_empty_playlists(db_path: str | None = None) -> str:
    """Find playlists with 0 videos."""
    cur = _curator(db_path)
    db = cur._db()
    rows = db.execute(
        "SELECT id, title FROM playlists WHERE video_count = 0 ORDER BY title"
    ).fetchall()

    if not rows:
        return "✅ No empty playlists found."

    lines = [f"### Empty Playlists ({len(rows)})\n"]
    for r in rows[:30]:
        lines.append(f"- {r['title']} (`{r['id']}`)")
    if len(rows) > 30:
        lines.append(f"\n… and {len(rows) - 30} more.")
    return "\n".join(lines)


@mcp.tool()
def suggest_merges(db_path: str | None = None) -> str:
    """Suggest playlist merge candidates based on title similarity.

    Useful for consolidating fragmented playlists (e.g. "Tech 2020" + "Tech 2021").
    """
    suggestions = suggest_merge_targets(Path(db_path) if db_path else None)

    if not suggestions:
        return "No strong merge candidates found."

    lines = [f"### Suggested Merges ({len(suggestions)} candidates)\n"]
    for s in suggestions[:15]:
        lines.append(
            f"- (score: {s['similarity_score']:.0%}) "
            f"\"{s['source']['title']}\" ({s['source']['video_count']} videos) "
            f"→ \"{s['target']['title']}\" ({s['target']['video_count']} videos)"
        )
    if len(suggestions) > 15:
        lines.append(f"\n… and {len(suggestions) - 15} more.")
    return "\n".join(lines)


@mcp.tool()
def merge_playlists(source_id: str, target_id: str,
                     dry_run: bool = True, db_path: str | None = None) -> str:
    """Move all videos from the SOURCE playlist into the TARGET, then delete SOURCE.

    Skips videos already present in the target. By default runs in dry_run mode —
    set dry_run=False to actually execute.

    Args:
        source_id: Playlist ID to move videos from (e.g. PL...)
        target_id: Playlist ID to move videos into
        dry_run: If True (default), only preview; set False to execute
    """
    cur = _curator(db_path)
    actions = cur.merge_playlists(source_id, target_id, dry_run=dry_run)

    label = "🔍 DRY RUN — would have" if dry_run else "✅"
    lines = [f"{label} merged:"]
    for a in actions:
        lines.append(f"  {a.note}")

    if dry_run:
        lines.append("\nRun again with `dry_run=False` to execute.")
    return "\n".join(lines)


@mcp.tool()
def delete_playlist(playlist_id: str, dry_run: bool = True,
                     db_path: str | None = None) -> str:
    """Delete a playlist and all its contents.

    By default runs in dry_run mode — set dry_run=False to actually delete.

    Args:
        playlist_id: The YouTube playlist ID to delete (e.g. PL...)
        dry_run: If True (default), only preview; set False to execute
    """
    cur = _curator(db_path)
    db = cur._db()
    pl = db.execute(
        "SELECT title, video_count FROM playlists WHERE id=?",
        (playlist_id,),
    ).fetchone()

    title = pl["title"] if pl else playlist_id
    vids = pl["video_count"] if pl else "?"

    if dry_run:
        return (
            f"🔍 DRY RUN — would delete:\n"
            f"  \"{title}\" ({vids} videos)\n"
            f"  ID: {playlist_id}\n\n"
            f"Run again with `dry_run=False` to execute."
        )

    if not has_valid_token():
        return "OAuth token not found. Run `auth_setup()` first."
    cur.client = YouTubeClient()
    action = cur.delete_playlist(playlist_id)
    return f"✅ Deleted playlist \"{action.playlist_title}\""


@mcp.tool()
def remove_dead_videos(dry_run: bool = True, db_path: str | None = None) -> str:
    """Remove all dead/private/blocked videos from their playlists.

    By default runs in dry_run mode — set dry_run=False to actually remove.

    Args:
        dry_run: If True (default), only preview; set False to execute
    """
    if not has_valid_token() and not dry_run:
        return "OAuth token not found. Run `auth_setup()` first."

    cur = _curator(db_path)
    actions = cur.remove_dead_videos(dry_run=dry_run)

    if not actions:
        return "No dead videos to remove."

    label = "🔍 DRY RUN — would remove" if dry_run else "✅ Removed"
    return f"{label} {len(actions)} dead video(s) from their playlists."


@mcp.tool()
def auth_status() -> str:
    """Check whether OAuth credentials are configured and valid."""
    status_parts = []
    if CLIENT_SECRET_FILE.exists():
        status_parts.append(f"✅ client_secret.json found at {CLIENT_SECRET_FILE}")
    else:
        status_parts.append(f"❌ client_secret.json not found at {CLIENT_SECRET_FILE}")

    if TOKEN_FILE.exists():
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), None)
            if creds.valid:
                status_parts.append("✅ Token is valid")
            elif creds.expired and creds.refresh_token:
                status_parts.append("⚠️  Token expired (can be refreshed)")
            else:
                status_parts.append("❌ Token invalid")
        except Exception:
            status_parts.append("❌ Token file corrupt")
    else:
        status_parts.append("❌ No token file")

    return "\n".join(status_parts)


# ── Server runner ──────────────────────────────────────────────

def run_server(host: str = "127.0.0.1", port: int = 39401) -> None:
    """Start the MCP server."""
    if "--help" in sys.argv or "-h" in sys.argv:
        print(
            "yt-curator MCP server\n\n"
            "Usage:\n"
            "  yt-curator serve-mcp              # stdio mode (default)\n"
            "  yt-curator serve-mcp --host 0.0.0.0 --port 39401  # SSE mode\n\n"
            "When run via `yt-curator serve-mcp`, the CLI handles argument parsing.\n"
            "The `yt-curator-mcp` console script always runs in stdio mode.\n"
        )
        return

    # SSE mode: host or port provided (from CLI parsing)
    if "--host" in sys.argv or "--port" in sys.argv:
        print(f"Starting yt-curator MCP server on {host}:{port}", file=sys.stderr)
        mcp.run(transport="sse", host=host, port=port)
    else:
        # stdio mode — for Claude Desktop, Hermes, etc.
        mcp.run(transport="stdio")


def main() -> None:
    """Entry point for yt-curator-mcp console script."""
    run_server()


if __name__ == "__main__":
    main()
