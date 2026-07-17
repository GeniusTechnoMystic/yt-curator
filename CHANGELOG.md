# Changelog

All notable changes to yt-curator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-07-18

### Added

- **CLI** — 11 Click commands: `auth`, `inventory`, `report`, `find-dupes`,
  `find-dead`, `merge`, `dedup`, `delete`, `serve-mcp`
- **MCP Server** — 12 FastMCP tools: `list_playlists`, `get_playlist_contents`,
  `scan_inventory`, `curation_report`, `find_duplicates`, `find_dead_videos`,
  `find_empty_playlists`, `suggest_merges`, `merge_playlists`, `delete_playlist`,
  `remove_dead_videos`, `auth_status`
- **Core Library** — Auth, YouTube client, inventory scanner, curation engine,
  dedup engine, data models
- **SQLite Schema** — 3 tables (playlists, playlist_videos, curation_log) with
  5 indexes, WAL mode, foreign keys
- **Inventory Scan** — Three-pass scanner: all playlists → all items → video
  status (live/deleted/private/blocked) with duration extraction
- **Curation Operations** — Merge playlists, delete playlists, remove dead
  videos, intra-playlist dedup — all with `--dry-run` mode
- **Duplicate Detection** — Cross-playlist duplicate finder with
  min-appearances filter; title-similarity merge suggestion engine
- **Nix Flake** — `flake.nix` with dev shell, package build, NixOS module
- **NixOS Module** — `services.yt-curator` with user/group, state directory,
  MCP server systemd service, sops-nix credential support
- **Documentation** — README, ARCHITECTURE, CONTRIBUTING, CHANGELOG, project
  brief, CI workflow
- **License** — MIT

### Fixed

- inventory.py: `print()` → `logging` for non-interference with MCP
- inventory.py: Proper video status detection (private, blocked, deleted)
- inventory.py: Fix `updated_at` field mapping (playlists lack separate
  updatedAt; use publishedAt)
- inventory.py: Remove unused `time` import
- curator.py: Lazy `YouTubeClient` creation (no OAuth for dry-runs/reports)
- curator.py: Add `close()` method, `get_playlist_summary()` public API
- curator.py: Remove unused `datetime` import
- cli/app.py: Use `get_playlist_summary()` instead of leaked `_db()`
- mcp/server.py: `run_server()` uses function params not `sys.argv`
- auth.py: `has_valid_token()` respects `read_only` parameter
- dedup.py: Remove dead code (unused variable assignment)