"""
yt-curator CLI — YouTube playlist curation from the terminal.

Usage:
    yt-curator auth           — set up OAuth credentials
    yt-curator inventory      — full playlist scan into local DB
    yt-curator report         — summary of inventory
    yt-curator find-dupes     — cross-playlist duplicates
    yt-curator find-dead      — dead/private/blocked videos
    yt-curator merge <src> <dst>  — merge two playlists
    yt-curator dedup <id>     — remove intra-playlist duplicates
    yt-curator delete <id>    — delete a playlist
    yt-curator serve-mcp      — start the MCP server
"""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from yt_curator.core.auth import (
    get_credentials,
    has_valid_token,
    TOKEN_FILE,
    CLIENT_SECRET_FILE,
    CONFIG_DIR,
)
from yt_curator.core.client import YouTubeClient
from yt_curator.core.inventory import scan_all
from yt_curator.core.curator import Curator

console = Console()


# ── Helpers ────────────────────────────────────────────────────

def _require_auth():
    """Ensure valid OAuth token exists, guiding the user if not."""
    if not has_valid_token():
        if not CLIENT_SECRET_FILE.exists():
            console.print(
                "[red]No OAuth credentials found.[/red]\n\n"
                "1. Go to https://console.cloud.google.com/apis/credentials\n"
                "2. Create a project, enable YouTube Data API v3\n"
                "3. Create OAuth 2.0 credentials (Desktop app type)\n"
                "4. Download client_secret.json and save to:\n"
                f"   [bold]{CLIENT_SECRET_FILE}[/bold]\n"
                "5. Run: [bold]yt-curator auth[/bold]"
            )
            raise click.Abort()
        console.print("No valid token found. Running OAuth flow...")
        get_credentials()


# ── CLI Group ──────────────────────────────────────────────────

@click.group()
@click.version_option(version="0.1.0", prog_name="yt-curator")
def cli():
    """yt-curator: YouTube playlist curation engine.

    Inventory, analyse, deduplicate, merge, and clean up your
    YouTube playlists — even 900+ of them spanning 20 years.
    """


# ── auth ───────────────────────────────────────────────────────

@cli.command()
@click.option("--read-only", is_flag=True, help="Only request read scope")
def auth(read_only: bool):
    """Set up OAuth 2.0 credentials for YouTube API access.

    First run: opens a browser for Google login. Subsequent runs
    reuse the stored refresh token in ~/.config/yt-curator/token.json.
    """
    if not CLIENT_SECRET_FILE.exists():
        console.print(
            "[yellow]Step 1: Download your client_secret.json[/yellow]\n"
            "Go to Google Cloud Console → APIs & Services → Credentials\n"
            "→ Create Credentials → OAuth client ID → Desktop application\n"
            "Download the JSON and save it to:\n"
            f"  [bold]{CLIENT_SECRET_FILE}[/bold]\n"
        )
        if not click.confirm("Continue after saving the file?", default=True):
            return

    console.print("Opening browser for Google authentication...")
    creds = get_credentials(read_only=read_only)
    scope_label = "read-only" if read_only else "read/write"
    console.print(
        f"[green]✓[/green] Token saved to [bold]{TOKEN_FILE}[/bold]\n"
        f"  Scope: {scope_label}\n"
        f"  Expires: {creds.expiry}"
    )


# ── inventory ──────────────────────────────────────────────────

@cli.command()
@click.option("--db", type=click.Path(path_type=Path),
              help="Path to inventory database (default: ~/.config/yt-curator/inventory.db)")
@click.option("--read-only/--write", default=False,
              help="Use read-only OAuth scope")
def inventory(db: Path | None, read_only: bool):
    """Scan all playlists and items into the local database.

    Runs three passes:
    1. List all playlists → SQLite
    2. List all playlist items → SQLite
    3. Batch-check video status (live/deleted/private)
    """
    _require_auth()
    client = YouTubeClient(read_only=read_only)
    report = scan_all(client, db_path=db)

    console.print(Panel(
        f"[bold]Inventory Complete[/bold]\n\n"
        f"  Playlists scanned:  {report.total_playlists}\n"
        f"  Videos found:       {report.total_videos}\n"
        f"  Live videos:        [green]{report.live_videos}[/green]\n"
        f"  Deleted videos:     [red]{report.deleted_videos}[/red]\n"
        f"  Private videos:     [yellow]{report.private_videos}[/yellow]\n"
        f"  Empty playlists:    {report.empty_playlists}\n"
        f"  Cross-playlist dupes: {len(report.duplicate_video_ids)}\n"
        f"  Quota used:         {client.quota}",
        title="📊 Results",
    ))


# ── report ─────────────────────────────────────────────────────

@cli.command()
@click.option("--db", type=click.Path(path_type=Path))
def report(db: Path | None):
    """Show a summary report from the inventory database."""
    cur = Curator(db_path=db)
    r = cur.get_report()
    if r["playlists"] == 0:
        console.print("[yellow]No inventory data. Run 'yt-curator inventory' first.[/yellow]")
        return

    table = Table(title="Inventory Report")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right", style="bold")

    table.add_row("Total playlists", str(r["playlists"]))
    table.add_row("Total videos", str(r["videos"]))
    table.add_row("Live", f"[green]{r['live']}[/green]")
    table.add_row("Deleted", f"[red]{r['deleted']}[/red]")
    table.add_row("Private", f"[yellow]{r['private']}[/yellow]")
    table.add_row("Empty playlists", str(r["empty_playlists"]))
    table.add_row("Duplicated (cross-playlist)", str(r["duplicate_video_ids"]))

    console.print(table)

    if r["top_dupes"]:
        console.print("\n[bold]Top Duplicates:[/bold]")
        for d in r["top_dupes"][:10]:
            console.print(f"  {d['video_id']} — appears in {d['appearances']} playlists")


# ── find-dupes ─────────────────────────────────────────────────

@cli.command(name="find-dupes")
@click.option("--db", type=click.Path(path_type=Path))
@click.option("--min", "min_appearances", default=2, type=int,
              help="Minimum playlist appearances (default: 2)")
def find_dupes(db: Path | None, min_appearances: int):
    """List videos that appear in multiple playlists."""
    cur = Curator(db_path=db)
    dupes = cur.get_duplicates(min_appearances=min_appearances)

    if not dupes:
        console.print("[green]No cross-playlist duplicates found![/green]")
        return

    table = Table(title=f"Cross-Playlist Duplicates (≥{min_appearances} appearances)")
    table.add_column("Video ID", style="dim")
    table.add_column("Title")
    table.add_column("Appearances", justify="right")
    table.add_column("In Playlists")

    for d in dupes[:30]:
        names = ", ".join(d.playlist_names[:3])
        if len(d.playlist_names) > 3:
            names += f" …and {len(d.playlist_names) - 3} more"
        table.add_row(
            d.video_id[:20],
            d.title[:60],
            str(d.total_count),
            names[:80],
        )

    console.print(table)
    if len(dupes) > 30:
        console.print(f"[dim]… and {len(dupes) - 30} more (use --limit to see more)[/dim]")


# ── find-dead ──────────────────────────────────────────────────

@cli.command(name="find-dead")
@click.option("--db", type=click.Path(path_type=Path))
def find_dead(db: Path | None):
    """List dead / private / blocked videos in your playlists."""
    cur = Curator(db_path=db)
    dead = cur.get_dead_videos()

    if not dead:
        console.print("[green]No dead videos found![/green]")
        return

    table = Table(title=f"Dead Videos ({len(dead)} total)")
    table.add_column("Status")
    table.add_column("Video ID")
    table.add_column("Title")
    table.add_column("Playlist")

    for entry in dead[:40]:
        colour = {"deleted": "red", "private": "yellow", "blocked": "red"}
        table.add_row(
            f"[{colour.get(entry.status)}]{entry.status}[/]",
            entry.video_id[:20],
            entry.title[:60],
            entry.playlist_title[:40],
        )

    console.print(table)
    if len(dead) > 40:
        console.print(f"[dim]… and {len(dead) - 40} more[/dim]")


# ── merge ──────────────────────────────────────────────────────

@cli.command()
@click.argument("source")
@click.argument("target")
@click.option("--db", type=click.Path(path_type=Path))
@click.option("--dry-run", is_flag=True, help="Show what would happen without executing")
def merge(source: str, target: str, db: Path | None, dry_run: bool):
    """Move all videos from SOURCE playlist into TARGET, then delete SOURCE."""
    _require_auth()
    cur = Curator(db_path=db)
    label = "[yellow]DRY RUN[/yellow] " if dry_run else ""
    console.print(f"{label}Merging [cyan]{source}[/cyan] → [cyan]{target}[/cyan]")
    actions = cur.merge_playlists(source, target, dry_run=dry_run)
    for a in actions:
        console.print(f"  {a.note}")
    console.print("[green]Done.[/green]")


# ── dedup ──────────────────────────────────────────────────────

@cli.command()
@click.argument("playlist_id")
@click.option("--db", type=click.Path(path_type=Path))
@click.option("--dry-run", is_flag=True)
def dedup(playlist_id: str, db: Path | None, dry_run: bool):
    """Remove duplicate videos within a single playlist.

    Keeps the first occurrence (lowest position) and removes later copies.
    """
    _require_auth()
    cur = Curator(db_path=db)
    label = "[yellow]DRY RUN[/yellow] " if dry_run else ""
    console.print(f"{label}Deduplicating playlist [cyan]{playlist_id}[/cyan]")
    actions = cur.deduplicate_playlist(playlist_id, dry_run=dry_run)
    console.print(f"  {len(actions)} duplicate(s) {'would be' if dry_run else ''} removed")
    if not dry_run and actions:
        console.print("[green]Done.[/green]")


# ── delete ─────────────────────────────────────────────────────

@cli.command()
@click.argument("playlist_id")
@click.option("--db", type=click.Path(path_type=Path))
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option("--dry-run", is_flag=True)
def delete(playlist_id: str, db: Path | None, force: bool, dry_run: bool):
    """Delete a playlist and all its contents."""
    cur = Curator(db_path=db)
    pl = cur.get_playlist_summary(playlist_id)

    if pl:
        console.print(f"Playlist: [bold]{pl['title']}[/bold] ({pl['video_count']} videos)")
    else:
        console.print(f"Playlist ID: [bold]{playlist_id}[/bold] (not in local DB)")

    if dry_run:
        console.print("[yellow]DRY RUN — would have deleted this playlist[/yellow]")
        return

    if not force:
        click.confirm("Delete this playlist?", abort=True)

    _require_auth()
    cur.client = YouTubeClient()
    action = cur.delete_playlist(playlist_id)
    console.print(f"[red]Deleted[/red] playlist {action.playlist_title}")


# ── serve-mcp ──────────────────────────────────────────────────

@cli.command(name="serve-mcp")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=39401, show_default=True, type=int,
              help="Port for the MCP server (default 39401, adjacent to mcp-gateway on 39400)")
def serve_mcp(host: str, port: int):
    """Start the MCP server (stdio or SSE mode).

    In stdio mode (the default), run as:
        yt-curator serve-mcp

    In SSE mode (for gateway registration):
        yt-curator serve-mcp --host 0.0.0.0 --port 39401
    """
    from yt_curator.mcp.server import run_server
    run_server(host=host, port=port)


if __name__ == "__main__":
    cli()
