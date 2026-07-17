# Contributing to yt-curator

## Development Setup

```bash
# Clone the repo
git clone https://github.com/GeniusTechnoMystic/yt-curator
cd yt-curator

# Install dependencies
uv sync --group dev

# Activate the virtual environment
source .venv/bin/activate
```

## Project Structure

```
src/yt_curator/
├── cli/app.py          # Click CLI — 11 commands
├── mcp/server.py       # FastMCP server — 12 tools
├── core/
│   ├── auth.py         # OAuth 2.0 with refresh-token storage
│   ├── client.py       # YouTube API wrapper (paginated, quota-tracked)
│   ├── inventory.py    # Full scan → SQLite (3 passes)
│   ├── curator.py      # Merge, delete, dedup, dead-removal operations
│   ├── dedup.py        # Cross-playlist dedup + title-similarity merge suggestions
│   └── models.py       # 6 dataclasses (Playlist, PlaylistVideo, etc.)
└── db/schema.py        # SQLite schema (3 tables, 5 indexes)
```

## Dependency Graph

```
auth.py  ←  client.py  ←  inventory.py
         ←  client.py  ←  curator.py  ←  cli/app.py
                                       ←  mcp/server.py
         ←  dedup.py   ←  mcp/server.py
```

- `auth.py` has no internal dependencies
- `client.py` depends on `auth.py`
- `inventory.py` depends on `client.py` + `db/schema.py`
- `curator.py` depends on `client.py` + `db/schema.py`
- `dedup.py` depends on `db/schema.py`
- `cli/app.py` depends on all core modules
- `mcp/server.py` depends on all core modules

## Coding Standards

- **Python 3.11+** — use `str | None` not `Optional[str]`
- **Type annotations** everywhere — strict mypy mode
- **No bare `print()`** — use `logging.getLogger()` in core, `rich.console` in CLI
- **All destructive operations** have a `dry_run: bool = True` parameter
- **Docstrings** on every public function and class (Google style)
- **Tests** go in `tests/` — pytest with `pytest-cov`
- **Imports** sorted via ruff (isort-compatible)
- **Line length** 100 chars

## Before Submitting a PR

```bash
# Format and lint
ruff check src/

# Type check
mypy src/yt_curator

# Run tests
pytest -v

# Check coverage
pytest --cov=yt_curator
```

## Architecture Decisions

### SQLite as the Single Source of Truth
After a full inventory scan, all curation operations work from the local DB.
The YouTube API is only called to execute write operations (merge, delete, etc.)
or to refresh the inventory. This minimises quota consumption and enables
offline analysis.

### Dry-Run First
Every destructive operation defaults to `dry_run=True`. The user must explicitly
opt in to execution. This prevents accidental data loss and builds confidence
in the tool before applying changes.

### Layered Auth
OAuth 2.0 tokens are stored in `~/.config/yt-curator/token.json` with `chmod 600`.
The `yt-curator auth` command handles the initial browser-based flow; subsequent
runs use the stored refresh token automatically. For headless servers, run `auth`
once on a desktop then copy the token file.

## Release Process

1. Update `__version__` in `src/yt_curator/__init__.py`
2. Update `CHANGELOG.md`
3. Tag the release: `git tag v0.1.0 && git push --tags`
4. Build: `uv build`
5. Publish: `uv publish`