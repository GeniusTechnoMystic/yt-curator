# YouTube Playlist Curation Engine

**Project Brief | v0.1 | Telos Systems | Danny Poulson | July 2026**

---

## 1. Executive Summary

Automate the inventory, analysis, and bulk curation of ~900+ YouTube playlists accumulated over ~20 years of account activity. The system uses the YouTube Data API v3 (via a Google Cloud Platform project) to list every playlist and its contents, then apply programmatic curation operations — deduplication, dead-video detection, bulk moves/merges/deletions, tagging, and AI-assisted reorganisation — that are impossible to do by hand through YouTube's web UI.

The primary delivery is a CLI tool (Hermes-integrated) and a project report that maps the full capability space, quota budget, and build phases. The user can choose to proceed with implementation from this blueprint.

---

## 2. Problem / Opportunity

| Factor | Detail |
| :-- | :-- |
| **Scale** | ~900+ playlists across 20 years of YouTube usage |
| **Manual burden** | YouTube's UI has no bulk operations — every playlist must be opened individually |
| **Degradation** | Dead videos (deleted, private, region-blocked) accumulate silently |
| **Duplication** | Same video added to multiple playlists over the years, no easy cross-reference |
| **Organisational drift** | Topic boundaries shift; playlists that made sense in 2010 don't map to current interests |
| **No export** | YouTube offers no native "export all playlist data" feature |

---

## 3. What's Possible with YouTube Data API v3

### 3.1 API Capability Matrix

| Operation | Endpoint | Quota Cost | Auth Required |
| :-- | :-- | :-: | :-: |
| List all playlists on my channel | `playlists.list?mine=true` | 1 | OAuth 2.0 |
| Get playlist metadata (title, desc, privacy) | `playlists.list?id=PLxxx` | 1 | OAuth 2.0 |
| List all videos in a playlist | `playlistItems.list?playlistId=PLxxx` | 1 per page | API key (public) / OAuth (private) |
| Create a new playlist | `playlists.insert` | 50 | OAuth 2.0 |
| Update playlist metadata | `playlists.update` | 50 | OAuth 2.0 |
| Delete a playlist | `playlists.delete` | 50 | OAuth 2.0 |
| Add video to playlist | `playlistItems.insert` | 50 | OAuth 2.0 |
| Move/reorder video in playlist | `playlistItems.update` (position field) | 50 | OAuth 2.0 |
| Remove video from playlist | `playlistItems.delete` | 50 | OAuth 2.0 |
| Search for videos | `search.list` | 1 (100/day budget) | API key |
| Get video stats (views, likes) | `videos.list?part=statistics` | 1 | API key |
| Check video availability | `videos.list?part=status` | 1 | API key |

### 3.2 What's Blocked / Limited

| Restriction | Detail |
| :-- | :-- |
| **Watch Later & History** | Cannot be read or modified via the API |
| **Liked Videos playlist** | Can list but cannot write |
| **search.list quota** | Separate 100-call/day bucket (not from the 10k pool) |
| **Bulk operations** | No native batch endpoints — each insert/update/delete is a separate call |
| **Rate limit** | Soft — enforced via quota exhaustion, not per-second caps |

### 3.3 Quota Budget for a Full Curation Run

Default allocation: **10,000 units/day** + 100 search.list calls/day + 100 videos.insert calls/day

**Read phase (one-time inventory)** — ~2,000 units:

| Step | Calls | Unit Cost | Total |
| :-- | :-: | :-: | :-: |
| List all playlists (mine) | 1 | 1 | 1 |
| Pagination for 900 playlists (50/page = 18 pages) | 18 | 1 | 18 |
| List playlistItems per playlist (avg ~30 videos, 1 page) | 900 | 1 | 900 |
| Pagination for larger playlists (say ~200 extra pages total) | 200 | 1 | 200 |
| videos.list for status/stats (50 IDs per call, ~6000 total vids) | 120 | 1 | 120 |
| **Read total** | | | **~1,239** |

**Curation phase (write operations)** — budget-dependent, ~50 per operation:

| Action | Per-call cost | 100 operations | 500 operations |
| :-- | :-: | :-: | :-: |
| Delete dead/empty playlists | 50 | 5,000 | 25,000 |
| Merge playlists (move all items + delete source) | 50+50 | 10,000 | 50,000 |
| Add videos to new curated playlists | 50 | 5,000 | 25,000 |
| Remove duplicates | 50 | 5,000 | 25,000 |

**Takeaway**: A full inventory read costs ~1,200 units — well within the 10k daily budget. Heavy write operations will consume 5k+ units per 100 operations, meaning a major curation pass spans multiple days unless a quota increase is granted.

**Quota Increase**: Google's standard form allows requests up to 100k-1M units/day for legitimate use cases. Several Reddit reports confirm 100k grants for playlist tools.

---

## 4. Architecture Options

### 4.1 Direct Python CLI (Recommended for v1)

```
┌─────────────────────────────────────────────┐
│               Hermes Agent                    │
│  ┌─────────────────────────────────────┐     │
│  │  youtube-playlist-curator CLI       │     │
│  │  (Python + google-api-python-client)│     │
│  │                                     │     │
│  │  Commands:                          │     │
│  │  inventory      — full scan & save  │     │
│  │  report         — summary stats     │     │
│  │  find-dead      — detect dead vids  │     │
│  │  find-dupes     — cross-playlist    │     │
│  │  merge          — combine PList B→A │     │
│  │  delete         — bulk delete       │     │
│  │  tag            — add vids to list  │     │
│  │  suggest        — AI reorg proposal │     │
│  └──────────────┬──────────────────────┘     │
│                 │                              │
│  OAuth 2.0 ─────┤  google-auth-oauthlib        │
└─────────────────┼────────────────────────────┘
                  │
     ┌────────────▼────────────┐
     │   Google Cloud Project   │
     │   (YouTube Data API v3)  │
     └─────────────────────────┘
```

### 4.2 MCP Server Option (Hermes-native)

Build a dedicated MCP backend (`mcp-server-youtube-playlists`) that exposes playlist curation as MCP tools. Hermes can then invoke these tools directly from any conversation:

```
Available tools (via MCP):
- yt_list_playlists()           → full inventory
- yt_playlist_contents(id)      → all videos in playlist
- yt_check_video_status(ids)    → live/dead/private
- yt_move_video(src, dst, vid)  → move between playlists
- yt_merge_playlists(src, dst)  → merge + cleanup
- yt_delete_playlist(id)        → delete with confirmation
- yt_create_playlist(title)     → new empty playlist
- yt_find_duplicates()          → cross-playlist dupes
- yt_curation_report()          → summary stats
```

This is the more architecturally aligned option given your existing MCP gateway infrastructure (16 backends on :39400) — the playlist curator becomes backend #17.

### 4.3 Comparison

| Criteria | Python CLI | MCP Server |
| :-- | :-: | :-: |
| Build time | 1-2 days | 2-3 days |
| Hermes integraton | Manual (terminal) | Native (tools) |
| Auth handling | OAuth file per run | Token storage in config |
| Reusability | Standalone | Any MCP client |
| Complexity | Low | Medium |

---

## 5. Curation Workflows (Feature Ideas)

### 5.1 Automated Inventory
- Full scan of all playlists → local SQLite database
- Schema: playlists (id, title, description, video_count, privacy, created), playlist_videos (playlist_id, video_id, position, added_at, title, channel, duration, status)

### 5.2 Dead Video Detection
- Check status of every video across all playlists
- Report: deleted, private, blocked, available
- Option: remove dead videos from playlists or flag for review

### 5.3 Cross-Playlist Deduplication
- Identify videos appearing in 2+ playlists
- Options: remove from all but one, create a consolidated "Duplicates" playlist, report for manual triage

### 5.4 Empty / Stale Playlist Cleanup
- Find playlists with 0 videos, playlists untouched in 5+ years, or single-video playlists
- Batch delete with confirmation

### 5.5 AI-Assisted Reorganisation
- Analyse video titles, descriptions, and channel metadata via local LLM (Ollama)
- Suggest topic clusters: "These 14 playlists about quantum physics could merge into 3"
- Suggest titles for merged playlists
- Output: proposed reorganisation plan (user approves before execution)

### 5.6 Privacy Audit
- List all playlists sorted by privacy status (public / unlisted / private)
- Identify accidentally-public personal playlists
- Bulk set to private

### 5.7 Backup / Export
- Export full inventory to JSON/CSV/Markdown
- Option: archive playlist structure to git repo for version control
- "Playlist-as-code" — declarative YAML defining desired playlist structure

---

## 6. GCP Setup Requirements

| Step | Detail |
| :-- | :-- |
| **1. Create GCP project** | `youtube-playlist-curator` (or similar) |
| **2. Enable API** | YouTube Data API v3 |
| **3. Configure OAuth consent** | External / Testing scope — needs: `https://www.googleapis.com/auth/youtube`, `https://www.googleapis.com/auth/youtube.force-ssl` |
| **4. Create OAuth 2.0 credentials** | Desktop app type → download client_secret.json |
| **5. First auth flow** | Runs locally via browser, stores refresh_token for headless later use |
| **6. (Optional) API key** | For read-only public-data calls without OAuth |
| **7. Request quota increase** | Submit via GCP Quotas page — reference legitimate playlist management use case |

**OAuth Scopes needed:**
- `youtube.readonly` — inventory scan (minimal scope)
- `youtube` — write operations (create/edit/delete playlists and items)
- `youtube.force-ssl` — required for API calls that modify data

---

## 7. Existing Tools & References

| Tool | What It Does | Limitations |
| :-- | :-- | :-- |
| **UnTube** (Django) | Web-based playlist manager with bulk operations | Third-party service; needs deployment |
| **yt-dlp** | Dump playlist metadata, download videos | Read-only; no write operations to YouTube |
| **Tubular** | YouTube API CLI tool (Node.js) | Read-focused; limited write capability |
| **google-api-python-client** | Official Python library | Not a tool — the SDK we'd use |
| **Youtube Playlist Manager** (various GH repos) | Single-purpose scripts | Often abandoned, no bulk dedup |

None of these address the full 900+ playlist curation problem out of the box. A purpose-built tool is justified.

---

## 8. Data Model (SQLite)

```sql
CREATE TABLE playlists (
    id TEXT PRIMARY KEY,         -- PL_xxxxxxxxxx
    title TEXT NOT NULL,
    description TEXT,
    privacy TEXT,                -- public / unlisted / private
    video_count INTEGER,
    channel_id TEXT,
    channel_title TEXT,
    created_at TEXT,             -- ISO 8601
    updated_at TEXT,
    etag TEXT,
    last_scanned TEXT
);

CREATE TABLE playlist_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id TEXT NOT NULL REFERENCES playlists(id),
    video_id TEXT NOT NULL,      -- xxxxxxxxxxx
    position INTEGER,
    title TEXT,
    channel_id TEXT,
    channel_title TEXT,
    published_at TEXT,
    duration_seconds INTEGER,
    status TEXT,                 -- live / deleted / private / blocked
    added_at TEXT,               -- when it was added to playlist
    etag TEXT,
    UNIQUE(playlist_id, video_id)
);

CREATE TABLE curation_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,                 -- delete_playlist / move_video / merge / etc
    source_playlist_id TEXT,
    target_playlist_id TEXT,
    video_id TEXT,
    timestamp TEXT,
    status TEXT,                 -- pending / done / rolled_back
    note TEXT
);

CREATE INDEX idx_pv_video ON playlist_videos(video_id);
CREATE INDEX idx_pv_playlist ON playlist_videos(playlist_id);
```

---

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
| :-- | :-: | :-: | :-- |
| **Quota exhaustion mid-scan** | Medium | Medium | Save progress; resume from cursor; run inventory as multiple daily passes |
| **OAuth token expiry** | Low | High | Store refresh token; auto-refresh; test token validity before runs |
| **Accidental mass deletion** | Low | Critical | All destructive operations are --dry-run first; confirmation prompt; trash-pile playlist (move instead of delete) |
| **YouTube API deprecation** | Low | Medium | Abstract API layer; version-lock client library |
| **Rate limit on quota increase request** | Medium | Low | 10k/day supports read-only fine; writes can be spread across days |
| **Video count >> estimate** | Medium | Low | Pagination handles arbitrary playlist sizes; 50 items/page |

---

## 10. Recommended Build Phases

### Phase 0 — Scoping & Auth Setup (2-4 hours)
- [ ] Create GCP project, enable YouTube API, configure OAuth
- [ ] Run first OAuth flow, capture refresh token
- [ ] Quick inventory test: list all 900+ playlists (single API call)
- [ ] Save result to JSON, count total videos

### Phase 1 — Full Inventory (4-6 hours)
- [ ] Build inventory CLI: scan all playlists + all items → SQLite
- [ ] Check video status (live/dead/private) via videos.list batch
- [ ] Generate summary report: total playlists, total videos, dead count, dupe count

### Phase 2 — Curative Operations (6-10 hours)
- [ ] Implement: delete empty playlists, bulk delete playlists
- [ ] Implement: move videos between playlists, merge playlists
- [ ] Implement: cross-playlist deduplication
- [ ] Implement: dead video removal
- [ ] All with --dry-run mode

### Phase 3 — Intelligence Layer (8-12 hours)
- [ ] LLM-based reorganisation suggestions (local Ollama)
- [ ] Topic clustering of existing playlists
- [ ] Auto-generated suggested merges
- [ ] Privacy audit & bulk fix

### Phase 4 — MCP Server (4-6 hours)
- [ ] Package as MCP backend server
- [ ] Register with MCP gateway
- [ ] Full tool surface: list/contents/move/merge/delete/create

### Phase 5 — Optional Polish
- [ ] "Playlist-as-code" — declarative YAML → desired state enforcement
- [ ] Git-backed version history of playlist structure
- [ ] Scheduled inventory drift detection (cronjob)
- [ ] Notion integration for curation review board

---

## 11. Estimated Resource Requirements

| Resource | Cost |
| :-- | :-- |
| GCP project | Free (no charge for API usage within quota) |
| Quota increase request | Free (takes 1-3 days for approval) |
| Python libraries | Free (google-api-python-client, google-auth-oauthlib, sqlite3 stdlib) |
| Storage | ~10MB for 900 playlists × 30 videos × metadata |
| Time (initial build) | ~24-34 hours total across all phases |
| Ongoing | ~1,200 units/day for weekly re-scans; free-tier sufficient |

---

## 12. Next Steps

1. **Do you want to pursue this?** If yes, the immediate next step is creating the GCP project and OAuth credentials.
2. **Do you remember the original conversation?** The idea doesn't appear in any indexed session or chat archive I searched. It may have been in a session that was deleted before the chat archive extraction pipeline ran, or in a platform I haven't indexed (e.g., early Claude, Copilot, or Perplexity chats).
3. **Shall I save this as a project skill?** Once you decide on the approach (CLI vs MCP), I can create a `youtube-playlist-curation` skill with the exact build commands and pitfalls documented.

---

*Generated by Hermes | Telos Systems | July 2026*
