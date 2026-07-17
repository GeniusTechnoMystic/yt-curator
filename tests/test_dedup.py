"""Tests for yt_curator.core.dedup."""

import tempfile
import os
from pathlib import Path

from yt_curator.core.dedup import (
    _title_similarity,
    find_cross_playlist_duplicates,
    suggest_merge_targets,
)
from yt_curator.db.schema import open_db


class TestTitleSimilarity:
    def test_identical(self):
        assert _title_similarity("Hello World", "Hello World") == 1.0

    def test_similar_years(self):
        score = _title_similarity("Tech Videos 2020", "Tech Videos 2021")
        assert score > 0.4
        assert score < 1.0

    def test_unrelated(self):
        assert _title_similarity("Music", "Cooking") == 0.0

    def test_empty_first(self):
        assert _title_similarity("", "Anything") == 0.0

    def test_empty_second(self):
        self.skipTest = lambda: None
        result = _title_similarity("Anything", "")
        assert result == 0.0

    def test_same_first_word(self):
        score = _title_similarity("Python Tutorials 2020", "Python Tutorials 2021")
        # Should get jaccard overlap + first-word bonus
        assert score > 0.5

    def test_case_insensitive(self):
        score = _title_similarity("tech videos", "Tech Videos")
        assert score == 1.0


class TestCrossPlaylistDuplicates:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.conn = open_db(self.tmp)
        self._seed_data()

    def teardown_method(self):
        self.conn.close()
        os.unlink(self.tmp)

    def _seed_data(self):
        # Two playlists
        self.conn.execute(
            "INSERT INTO playlists (id, title) VALUES (?, ?)",
            ("PL_a", "Playlist A"),
        )
        self.conn.execute(
            "INSERT INTO playlists (id, title) VALUES (?, ?)",
            ("PL_b", "Playlist B"),
        )
        self.conn.execute(
            "INSERT INTO playlists (id, title) VALUES (?, ?)",
            ("PL_c", "Playlist C"),
        )
        # Videos: vid1 appears in A and B (duplicate), vid2 only in A, vid3 only in B
        for vid, pos, pl in [("vid1", 1, "PL_a"), ("vid2", 2, "PL_a"),
                              ("vid1", 1, "PL_b"), ("vid3", 2, "PL_b"),
                              ("vid4", 1, "PL_c")]:
            self.conn.execute(
                "INSERT INTO playlist_videos (playlist_id, video_id, position, title) "
                "VALUES (?, ?, ?, ?)",
                (pl, vid, pos, f"Video {vid}"),
            )
        self.conn.commit()

    def test_finds_duplicates(self):
        result = find_cross_playlist_duplicates(db_path=Path(self.tmp))
        assert len(result) == 1  # Only vid1 appears in >1 playlist
        assert result[0].video_id == "vid1"
        assert result[0].total_count == 2

    def test_min_appearances_filters(self):
        # With min_appearances=3, no results
        result = find_cross_playlist_duplicates(
            db_path=Path(self.tmp), min_appearances=3
        )
        assert len(result) == 0

    def test_max_results_limits(self):
        # Add another dupe
        self.conn.execute(
            "INSERT INTO playlist_videos (playlist_id, video_id, position, title) "
            "VALUES (?, ?, ?, ?)",
            ("PL_c", "vid1", 2, "Video vid1"),
        )
        self.conn.commit()
        result = find_cross_playlist_duplicates(
            db_path=Path(self.tmp), max_results=1
        )
        assert len(result) == 1

    def test_empty_db(self):
        empty_tmp = tempfile.mktemp(suffix=".db")
        result = find_cross_playlist_duplicates(db_path=Path(empty_tmp))
        assert result == []
        os.unlink(empty_tmp)


class TestSuggestMergeTargets:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.conn = open_db(self.tmp)
        self._seed_data()

    def teardown_method(self):
        self.conn.close()
        os.unlink(self.tmp)

    def _seed_data(self):
        titles = [
            ("PL_1", "Tech Videos 2020", 10),
            ("PL_2", "Tech Videos 2021", 15),
            ("PL_3", "Music", 20),
            ("PL_4", "Tech Videos 2022", 8),
            ("PL_5", "Cooking", 5),
        ]
        for pid, title, count in titles:
            self.conn.execute(
                "INSERT INTO playlists (id, title, video_count) VALUES (?, ?, ?)",
                (pid, title, count),
            )
        self.conn.commit()

    def test_suggests_similar(self):
        suggestions = suggest_merge_targets(db_path=Path(self.tmp))
        # The 3 Tech Videos playlists should be suggested as merges
        tech_suggestions = [
            s for s in suggestions
            if "Tech Videos" in s["source"]["title"]
        ]
        assert len(tech_suggestions) >= 2

    def test_top_scores_first(self):
        suggestions = suggest_merge_targets(db_path=Path(self.tmp))
        if suggestions:
            assert suggestions[0]["similarity_score"] >= suggestions[-1]["similarity_score"]

    def test_empty_db(self):
        empty_tmp = tempfile.mktemp(suffix=".db")
        suggestions = suggest_merge_targets(db_path=Path(empty_tmp))
        assert suggestions == []
        os.unlink(empty_tmp)