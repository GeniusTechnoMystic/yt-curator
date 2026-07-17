# Architecture

## Overview

yt-curator is a three-headed tool:

```
┌──────────────────────────────────────────────────────────────┐
│                        yt-curator                            │
│                                                              │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │  CLI (Click)  │  │  MCP (FastMCP) │  │  Python Library  │  │
│  │  11 commands  │  │   12 tools     │  │  import yt_curator│  │
│  └──────┬───────┘  └───────┬────────┘  └────────┬─────────┘  │
│         │                  │                     │            │
│         └──────────┬───────┴─────────────────────┘            │
│                    │                                          │
│           ┌────────▼────────┐                                 │
│           │   Core Layer    │                                 │
│           │  ┌──────────┐   │                                 │
│           │  │  auth.py │   │  OAuth 2.0 → Google API         │
│           │  ├──────────┤   │                                 │
│           │  │ client.py│   │  YouTube Data API v3 wrapper    │
│           │  ├──────────┤   │                                 │
│           │  │inventory │   │  Scan → SQLite                  │
│           │  ├──────────┤   │                                 │
│           │  │ curator  │   │  Merge, delete, dedup           │
│           │  ├──────────┤   │                                 │
│           │  │  dedup   │   │  Cross-playlist + suggestions   │
│           │  └──────────┘   │                                 │
│           └────────┬────────┘                                 │
│                    │                                          │
│           ┌────────▼────────┐                                 │
│           │  SQLite DB      │  ~/.config/yt-curator/inventory  │
│           │  3 tables       │                                 │
│           └─────────────────┘                                 │
└──────────────────────────────────────────────────────────────┘
```

## Data Flow

### Inventory Scan
```
YouTube API                     SQLite DB
──────────                     ──────────
playlists.list(mine=true)  →   playlists table
  ↓ (paginated)
playlistItems.list(pid)    →   playlist_videos table
  ↓ (paginated, for each playlist)
videos.list(ids)           →   playlist_videos.status update
                              (live / private / deleted / blocked)
                              ↓
                          playlist_videos.duration_seconds update
```

### Curation Operation (e.g. Merge)
```
User Input                    SQLite DB                  YouTube API
──────────                    ──────────                 ──────────
merge(source, target)
  └─ dry_run=True  →  read source + target videos  →  (no API call)
  └─ dry_run=False →  read source videos            →  playlistItems.insert
                                                       for each video
                       delete from playlist_videos
                       delete source playlist        →  playlists.delete
                       log to curation_log
```

## Key Design Decisions

### 1. SQLite as Materialised View
The local DB is a cached replica of YouTube's playlist data. This lets us run
complex queries (duplicate detection, dead video analysis, merge suggestions)
without consuming API quota. The DB is disposable — it can be rebuilt at any
time with `yt-curator inventory`.

### 2. Quota Budgeting
The QuotaTracker in `client.py` counts every API call. The inventory scan
costs ~1,200 units (of 10,000/day). Each write operation costs 50 units.
This transparency lets users plan their curation sessions.

### 3. Lazy Auth
`YouTubeClient` only calls `get_credentials()` when the service property is
first accessed. `Curator.client` is lazily created. This means dry-run and
report-only operations never trigger OAuth.

### 4. Dry-Run by Default
Every destructive operation (`merge_playlists`, `delete_playlist`,
`remove_dead_videos`, `deduplicate_playlist`) defaults to `dry_run=True`.
When a user explicitly sets `dry_run=False`, the tool:
1. Executes the API calls
2. Updates the local DB
3. Logs the action to the `curation_log` table
4. Returns the result

### 5. Print-Free Core
The core library uses Python's `logging` module. The CLI uses `rich.console`
for user-facing output. The MCP server returns strings. This separation means
the core can be used programmatically without stdout pollution.

## Error Handling Strategy

| Error Type | Handling |
|-----------|----------|
| Network error / API timeout | Propagated as `RuntimeError` from `client.py` |
| Quota exceeded | Propagated as HTTP 403 from YouTube API — user sees the error message |
| Playlist not found (404) | Returns `None` from `get_playlist()` |
| OAuth token expired | Auto-refreshed in `auth.py` |
| OAuth token missing | Clear error message with setup instructions |
| DB constraint violation | Propagated (shouldn't occur — UNIQUE constraints are defensive) |

## Security Model

- **OAuth 2.0**, not API keys — scoped to `youtube` + `youtube.force-ssl`
- Token file stored at `~/.config/yt-curator/token.json` with `chmod 600`
- `client_secret.json` never committed to version control
- All write operations require explicit user confirmation (dry-run or `--force`)

## Concurrency

The SQLite database uses WAL mode (`PRAGMA journal_mode=WAL`) for concurrent
reads. The curator operations are single-threaded and sequential — each API
call waits for the previous one. For large operations (merging 900 playlists),
the process is intentionally slow to avoid YouTube rate limits.