"""Tests for yt_curator.core.client."""

from yt_curator.core.client import QuotaTracker


class TestQuotaTracker:
    def test_empty(self):
        q = QuotaTracker()
        assert q.read == 0
        assert q.write == 0
        assert q.total == 0

    def test_add_read(self):
        q = QuotaTracker()
        q.add(1)
        assert q.read == 1
        assert q.total == 1

    def test_add_write(self):
        q = QuotaTracker()
        q.add(50, is_write=True)
        assert q.write == 50
        assert q.total == 50

    def test_mixed(self):
        q = QuotaTracker()
        q.add(1)
        q.add(1)
        q.add(50, is_write=True)
        q.add(50, is_write=True)
        assert q.read == 2
        assert q.write == 100
        assert q.total == 102

    def test_str(self):
        q = QuotaTracker()
        q.add(1)
        q.add(50, is_write=True)
        s = str(q)
        assert "read=1" in s
        assert "write=50" in s
        assert "total=51" in s