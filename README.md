# yt-curator 🎬🧹

**YouTube playlist curation engine** — inventory, deduplicate, merge, clean up, and reorganise thousands of playlists spanning 20 years.

```
┌────────────────────────────────────────────────────┐
│                   yt-curator                        │
│                                                     │
│  ┌─────────┐  ┌─────────┐  ┌────────────────────┐  │
│  │   CLI   │  │   MCP   │  │  Python Library    │  │
│  │  (Click)│  │ (FastMCP)│  │  (import yt_curator)│  │
│  └────┬────┘  └────┬────┘  └─────────┬──────────┘  │
│       │            │                 │              │
│       └──────┬─────┘─────────────────┘              │
│              │                                      │
│     ┌────────▼────────┐                             │
│     │  YouTube Data   │                             │
│     │   API v3 + OAuth│                             │
│     │  + Local SQLite │                             │
│     └─────────────────┘                             │
└────────────────────────────────────────────────────┘
```

## Features

- **Full inventory** — scan all your playlists and every video in them into a local SQLite database
- **Dead video detection** — find deleted, private, and blocked videos across all playlists
- **Cross-playlist deduplication** — find every video that appears in 2+ playlists
- **Intra-playlist dedup** — remove duplicate copies within a single playlist
- **Merge playlists** — move all videos from one playlist into another, then delete the source
- **Bulk delete** — remove empty or unwanted playlists
- **Merge suggestions** — AI-free title-similarity analysis to find consolidation candidates
- **Privacy audit** — see which playlists are public vs private
- **Dry-run everything** — all destructive operations preview before executing

## Three Interfaces

### 1. CLI (`yt-curator`)

```bash
# OAuth setup (one-time)
yt-curator auth

# Full inventory scan
yt-curator inventory

# Reports
yt-curator report
yt-curator find-dupes
yt-curator find-dead

# Curation (try --dry-run first!)
yt-curator merge PL_source_id PL_target_id --dry-run
yt-curator dedup PL_playlist_id --dry-run
yt-curator delete PL_playlist_id --dry-run

# Start MCP server
yt-curator serve-mcp
```

### 2. MCP Server (`yt-curator-mcp`)

Register as a backend for any MCP client (Claude Desktop, Hermes, Cursor, etc.).

**stdio mode** (default — plug-and-play with Claude Desktop):
```json
{
  "mcpServers": {
    "yt-curator": {
      "command": "yt-curator",
      "args": ["serve-mcp"]
    }
  }
}
```

**SSE mode** (register with the mcp-gateway):
```bash
yt-curator serve-mcp --host 0.0.0.0 --port 39401
```

Then add to your gateway config:
```yaml
backends:
  - name: yt-curator
    type: sse
    url: http://127.0.0.1:39401
```

**Available MCP tools:**

| Tool | Description |
| :-- | :-- |
| `list_playlists()` | List all playlists in the inventory DB |
| `get_playlist_contents(id)` | List all videos in a specific playlist with status |
| `scan_inventory()` | **Full scan** — all playlists, items, and video status |
| `curation_report()` | Summary stats from inventory |
| `find_duplicates(min=2)` | Cross-playlist duplicate detection |
| `find_dead_videos()` | Dead/private/blocked videos |
| `find_empty_playlists()` | Zero-video playlists |
| `suggest_merges()` | Title-similarity merge candidates |
| `merge_playlists(src, dst, dry_run=True)` | Merge with dry-run mode |
| `delete_playlist(id, dry_run=True)` | Delete with dry-run mode |
| `remove_dead_videos(dry_run=True)` | Bulk dead video removal |
| `auth_status()` | Check OAuth credentials |

### 3. Python Library (`import yt_curator`)

```python
from yt_curator.core.client import YouTubeClient
from yt_curator.core.inventory import scan_all

client = YouTubeClient()
report = scan_all(client)
print(f"Scanned {report.total_playlists} playlists")
```

## Quota Budget

YouTube Data API v3 default: **10,000 units/day** (free).

| Operation | Cost per call | Your 900-playlist scan |
| :--------- | :-----------: | :--------------------: |
| `playlists.list` | 1 | ~18 calls |
| `playlistItems.list` | 1 | ~900 calls |
| `videos.list` (status check) | 1 | ~120 calls |
| `playlists.insert` / `.update` | 50 | per operation |
| `playlistItems.insert` / `.delete` | 50 | per operation |
| **Full inventory scan** | | **~1,200 units** ✅ |

A full scan uses ~12% of your daily quota, leaving 8,800 units for curation
writes (about 175 write operations per day).

## Setup

### One-time: Google Cloud + OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **YouTube Data API v3**
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download `client_secret.json`
4. Save it to `~/.config/yt-curator/client_secret.json`
5. Run `yt-curator auth` — opens a browser for Google login

> **Tip for headless servers**: Run `yt-curator auth` once on a desktop machine
> with a browser, then copy `~/.config/yt-curator/token.json` to the server.

## NixOS Module

Add yt-curator to your flake inputs:

```nix
{
  inputs.yt-curator = {
    url = "github:telos-systems/yt-curator";
    inputs.nixpkgs.follows = "nixpkgs";
  };
}
```

Then enable the module:

```nix
{
  imports = [ yt-curator.nixosModules.default ];

  services.yt-curator = {
    enable = true;
    mcpServer.enable = true;
    mcpServer.port = 39401;

    credentials.clientSecretPath = config.sops.secrets."yt-curator/client_secret".path;
  };
}
```

Or use the flake directly:

```bash
nix run github:telos-systems/yt-curator -- inventory
nix run github:telos-systems/yt-curator#mcp -- serve-mcp
```

## Project Structure

```
yt-curator/
├── src/yt_curator/
│   ├── __init__.py          # Package entry
│   ├── cli/app.py           # Click CLI (11 commands)
│   ├── mcp/server.py        # FastMCP server (12 tools)
│   ├── core/
│   │   ├── auth.py          # OAuth 2.0 + token storage
│   │   ├── client.py        # YouTube API client wrapper
│   │   ├── inventory.py     # Full scan → SQLite
│   │   ├── curator.py       # Merge, delete, dedup operations
│   │   ├── dedup.py         # Cross-playlist dedup + suggestions
│   │   └── __init__.py      # Data models (dataclasses)
│   └── db/schema.py         # SQLite schema
├── nix/module.nix           # NixOS module
├── flake.nix                # Nix flake
├── pyproject.toml           # Python project metadata
├── LICENSE                  # MIT
└── README.md
```

## Why This Exists

YouTube's web UI has no bulk operations. If you have 900+ playlists accumulated
over 20 years, there's no way to:
- Find which videos are dead across all playlists
- See which videos appear in 10 different playlists
- Merge similar playlists
- Delete 50 empty playlists in one go

Existing MCP servers for YouTube are read-only analytics tools or basic CRUD
wrappers. None do inventory, dedup, merge, or bulk curation. This fills that gap.

## Roadmap

- [x] Core: inventory, dedup, merge, delete, dead video removal
- [x] CLI: 11 commands with --dry-run
- [x] MCP server: 12 tools (stdio + SSE)
- [x] Nix flake + NixOS module
- [ ] AI-assisted reorganisation (local LLM via Ollama)
- [ ] Playlist-as-code (declarative YAML → desired state)
- [ ] GitHub release + PyPI publish
- [ ] Scheduled inventory drift detection (weekly cron)

## License

MIT © 2026 Telos Systems / Danny Poulson
