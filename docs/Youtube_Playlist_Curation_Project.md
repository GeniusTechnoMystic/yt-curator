# Youtube Playlist Curation Project Brief

## Overview

A specialized agent for curating, inventorying, deduplicating, merging, and managing YouTube playlists. Designed to fill a gap in the MCP ecosystem where no existing tool handles playlist inventory, dedup, merge, and dead-video detection.

## Architecture

- **CLI** (11 commands): inventory, dedup, merge, diff, dead-video detection, export
- **MCP server** (12 tools, SSE on :39401): programmatic access to all functionality
- **Nix flake**: reproducible build and deployment

## Key Features

- **Inventory**: Scan all playlists for a channel, produce a unified view
- **Deduplication**: Find and remove duplicate videos across playlists
- **Merge**: Combine playlists, handling conflicts gracefully
- **Diff**: Show differences between playlist states
- **Dead video detection**: Identify deleted/unavailable videos
- **Export**: Output to JSON, CSV, or plaintext

## Stack

- Python 3.12+ with Click CLI
- MCP SDK for server mode
- youtube-dl/youtube-dlp for metadata
- Pytest for testing (16 unit tests)

## Usage

```bash
uv sync
yt-curator auth  # browser-based OAuth, one-time
yt-curator inventory
yt-curator serve-mcp --host 0.0.0.0 --port 39401
```

All destructive operations default to `--dry-run` for safety.

## Repository

- GitHub: https://github.com/GeniusTechnoMystic/yt-curator
- License: MIT