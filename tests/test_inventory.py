"""Tests for yt_curator.core.inventory."""

from yt_curator.core.inventory import _parse_duration


class TestParseDuration:
    def test_full(self):
        assert _parse_duration("PT1H2M3S") == 3723

    def test_minutes_only(self):
        assert _parse_duration("PT30M") == 1800

    def test_seconds_only(self):
        assert _parse_duration("PT5S") == 5

    def test_hours_only(self):
        assert _parse_duration("PT2H") == 7200

    def test_zero(self):
        assert _parse_duration("PT0S") == 0

    def test_empty_string(self):
        assert _parse_duration("") == 0

    def test_malformed(self):
        assert _parse_duration("not-a-duration") == 0