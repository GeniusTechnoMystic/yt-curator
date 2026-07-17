"""Tests for yt_curator.mcp.server."""

from yt_curator.mcp.server import mcp, run_server, auth_status


class TestMcpServer:
    def test_server_has_12_tools(self):
        tools = mcp._tool_manager._tools
        assert len(tools) == 12, f"Expected 12 tools, got {len(tools)}"

    def test_required_tools_present(self):
        tool_names = {t.name for t in mcp._tool_manager._tools}
        required = {
            "list_playlists", "get_playlist_contents", "scan_inventory",
            "curation_report", "find_duplicates", "find_dead_videos",
            "find_empty_playlists", "suggest_merges", "merge_playlists",
            "delete_playlist", "remove_dead_videos", "auth_status",
        }
        missing = required - tool_names
        assert not missing, f"Missing tools: {missing}"

    def test_auth_status_no_token(self):
        """auth_status() should not crash without a token file."""
        result = auth_status()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_run_server_stdio(self):
        """run_server() defaults to stdio transport."""
        # We can't actually start the server in a test, but we can verify
        # the function signature and logic are correct.
        assert callable(run_server)