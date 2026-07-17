# Test Plan

## Scope

| Module | Test Level | Priority | Depends On |
|--------|-----------|----------|------------|
| `core/models.py` | Unit | P0 | None |
| `core/dedup.py` | Unit | P0 | SQLite DB |
| `db/schema.py` | Unit | P0 | SQLite |
| `core/client.py` | Unit | P0 | None (QuotaTracker) |
| `core/inventory.py` | Unit | P0 | SQLite, YouTubeClient mock |
| `core/curator.py` | Unit | P0 | SQLite, YouTubeClient mock |
| `core/auth.py` | Unit | P1 | File system (token files) |
| `cli/app.py` | Integration | P1 | All core modules |
| `mcp/server.py` | Integration | P1 | All core modules |
| Full inventory scan | Integration | P0 | Real YouTube API + OAuth |

## Test Categories

### Unit Tests (no API needed)

| # | Test | File | What It Verifies |
|---|------|------|-----------------|
| 1 | `test_parse_duration` | `test_inventory.py` | ISO 8601 → seconds (PT1H2M3S, PT30M, PT0S, empty) |
| 2 | `test_title_similarity` | `test_dedup.py` | Token overlap, same-first-word bonus, empty strings, identical strings |
| 3 | `test_quota_tracker` | `test_client.py` | Add read/write, total, str representation |
| 4 | `test_db_schema` | `test_schema.py` | Table creation, index creation, WAL mode, foreign keys |
| 5 | `test_db_crud` | `test_schema.py` | Insert/update playlists, insert/update playlist_videos, cascade delete |
| 6 | `test_curator_report_empty` | `test_curator.py` | Report on empty DB returns zeros |
| 7 | `test_curator_playlist_summary` | `test_curator.py` | `get_playlist_summary()` with existing/missing ID |
| 8 | `test_curator_get_duplicates` | `test_curator.py` | Duplicate detection from seeded DB |
| 9 | `test_curator_get_dead_videos` | `test_curator.py` | Dead video listing from seeded DB |
| 10 | `test_curator_dry_run_merge` | `test_curator.py` | Merge with dry_run=True doesn't call API |
| 11 | `test_curator_dry_run_delete` | `test_curator.py` | Delete with dry_run=True doesn't call API |
| 12 | `test_curator_dry_run_dedup` | `test_curator.py` | Intra-playlist dedup with dry_run=True |
| 13 | `test_curator_dry_run_remove_dead` | `test_curator.py` | Dead video removal with dry_run=True |
| 14 | `test_dedup_find_cross_playlist` | `test_dedup.py` | `find_cross_playlist_duplicates()` |
| 15 | `test_dedup_suggest_merges` | `test_dedup.py` | `suggest_merge_targets()` from seeded DB |
| 16 | `test_models` | `test_models.py` | All dataclasses instantiate correctly |

### Integration Tests (need OAuth + YouTube API)

| # | Test | What It Verifies |
|---|------|-----------------|
| 17 | `test_auth_flow` | `get_credentials()` returns valid Credentials |
| 18 | `test_list_playlists` | `client.list_my_playlists()` returns paginated results |
| 19 | `test_inventory_scan` | Full `scan_all()` returns ScanReport with correct counts |
| 20 | `test_mcp_tools` | All 12 MCP tools respond without errors |

## Test Data

Unit tests create a temporary SQLite database in `tempfile.mktemp()` and seed
it with known data. The seeding pattern:

```python
conn = open_db(tmp_db)
conn.execute("INSERT INTO playlists (id, title, video_count) VALUES (?, ?, ?)",
             ("PL_seeded_a", "Test Playlist A", 3))
# ... more inserts
conn.commit()
db_path = Path(tmp_db)
```

## Running Tests

```bash
# All unit tests
pytest tests/ -v

# With coverage
pytest --cov=yt_curator tests/

# Specific module
pytest tests/test_curator.py -v

# Integration tests (requires OAuth)
pytest tests/ -v -k "integration" --run-integration
```

## CI Pipeline

The `.github/workflows/ci.yml` runs:
- `ruff check src/` — linting
- `mypy src/yt_curator` — type checking
- `pytest -v` — all unit tests
- Python 3.11, 3.12, 3.13 matrix

Integration tests are NOT run in CI (they require real OAuth credentials).