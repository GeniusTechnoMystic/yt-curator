"""
Advanced deduplication engine.

Extends the basic dedup in ``curator.py`` with cross-playlist dedup,
suggestion generation, and AI-assisted merge proposals.
"""

from pathlib import Path
from typing import Any

from yt_curator.core.models import DuplicateGroup
from yt_curator.db.schema import open_db


def find_cross_playlist_duplicates(
    db_path: Path | None = None,
    min_appearances: int = 2,
    max_results: int = 500,
) -> list[DuplicateGroup]:
    """Find all videos appearing in multiple playlists.

    Returns results sorted by number of appearances (most-duplicated first).
    """
    db = open_db(db_path)

    dupes = db.execute(
        "SELECT video_id, COUNT(DISTINCT playlist_id) as cnt "
        "FROM playlist_videos "
        "GROUP BY video_id "
        "HAVING cnt >= ? "
        "ORDER BY cnt DESC "
        "LIMIT ?",
        (min_appearances, max_results),
    ).fetchall()

    groups: list[DuplicateGroup] = []
    for row in dupes:
        vid = row["video_id"]
        appearances = db.execute(
            "SELECT pv.playlist_id, p.title as playlist_title, pv.position "
            "FROM playlist_videos pv "
            "JOIN playlists p ON p.id = pv.playlist_id "
            "WHERE pv.video_id = ? "
            "ORDER BY p.title",
            (vid,),
        ).fetchall()
        vt = db.execute(
            "SELECT title FROM playlist_videos WHERE video_id=? LIMIT 1",
            (vid,),
        ).fetchone()
        video_title = vt["title"] if vt else ""
        groups.append(DuplicateGroup(
            video_id=vid,
            title=video_title,
            appearances=[dict(a) for a in appearances],
            total_count=len(appearances),
        ))

    db.close()
    return groups


def suggest_merge_targets(
    db_path: Path | None = None,
) -> list[dict]:
    """Suggest playlist merge candidates based on title similarity.

    Looks for playlists with similar naming patterns (e.g. "Tech Videos 2020"
    and "Tech Videos 2021") that could be consolidated.

    Returns a list of merge suggestions with confidence scores.
    """
    db = open_db(db_path)
    playlists = db.execute(
        "SELECT id, title, video_count FROM playlists ORDER BY title"
    ).fetchall()

    suggestions: list[dict] = []
    titles = list(playlists)

    # Simple n-gram overlap on normalised titles
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            score = _title_similarity(titles[i]["title"], titles[j]["title"])
            if score >= 0.4:
                suggestions.append({
                    "source": {
                        "id": titles[i]["id"],
                        "title": titles[i]["title"],
                        "video_count": titles[i]["video_count"],
                    },
                    "target": {
                        "id": titles[j]["id"],
                        "title": titles[j]["title"],
                        "video_count": titles[j]["video_count"],
                    },
                    "similarity_score": round(score, 3),
                })

    suggestions.sort(key=lambda s: s["similarity_score"], reverse=True)
    db.close()
    return suggestions[:50]  # top 50


def _title_similarity(a: str, b: str) -> float:
    """Compute simple token overlap similarity between two playlist titles."""
    import re
    tokens_a = set(re.findall(r"\w+", a.lower()))
    tokens_b = set(re.findall(r"\w+", b.lower()))

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    # Weight towards longer titles having more overlap
    jaccard = len(intersection) / len(union) if union else 0.0

    # Bonus for same first word (likely thematic group)
    first_a = a.lower().split()[0] if a.split() else ""
    first_b = b.lower().split()[0] if b.split() else ""
    first_bonus = 0.15 if first_a == first_b and len(first_a) > 2 else 0.0

    return min(jaccard + first_bonus, 1.0)
