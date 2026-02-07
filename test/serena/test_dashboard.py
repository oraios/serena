"""
Tests for the dashboard API, specifically the news display logic.
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from serena.dashboard import SerenaDashboardAPI


class TestNewsDisplayLogic:
    """Test the news display logic with installation date filtering."""

    def test_get_installation_date_id_existing_dir(self):
        """Test getting installation date from an existing directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Get the installation date ID
            with patch("serena.dashboard.SerenaPaths") as mock_paths:
                mock_paths_instance = MagicMock()
                mock_paths_instance.serena_user_home_dir = temp_dir
                mock_paths.return_value = mock_paths_instance

                result = SerenaDashboardAPI._get_installation_date_id()

                # Should return a valid YYYYMMDD format integer
                assert isinstance(result, int)
                assert 20000101 <= result <= 99991231  # Valid date range
                
                # Should match today's or recent date (since we just created the directory)
                result_str = str(result)
                assert len(result_str) == 8
                year = int(result_str[0:4])
                month = int(result_str[4:6])
                day = int(result_str[6:8])
                assert 2020 <= year <= 2030  # Reasonable year range
                assert 1 <= month <= 12
                assert 1 <= day <= 31

    def test_get_installation_date_id_nonexistent_dir(self):
        """Test getting installation date when directory doesn't exist yet."""
        with patch("serena.dashboard.SerenaPaths") as mock_paths:
            mock_paths_instance = MagicMock()
            mock_paths_instance.serena_user_home_dir = "/nonexistent/path/that/does/not/exist"
            mock_paths.return_value = mock_paths_instance

            result = SerenaDashboardAPI._get_installation_date_id()

            # Should return today's date
            today = datetime.now()
            expected = int(today.strftime("%Y%m%d"))
            assert result == expected

    def test_news_filtering_by_installation_date(self):
        """Test that news items are filtered based on installation date."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock news directory with some news files
            news_dir = Path(temp_dir) / "news"
            news_dir.mkdir()

            # Create news files with dates before and after a simulated installation date
            old_news_file = news_dir / "20250101.html"
            recent_news_file = news_dir / "20260201.html"
            future_news_file = news_dir / "20260301.html"

            old_news_file.write_text("<div>Old news</div>")
            recent_news_file.write_text("<div>Recent news</div>")
            future_news_file.write_text("<div>Future news</div>")

            # Mock the installation date to be 2026-02-01
            with patch.object(SerenaDashboardAPI, "_get_installation_date_id", return_value=20260201):
                # Create mocks for the API
                mock_memory_log_handler = MagicMock()
                mock_agent = MagicMock()
                mock_tool_usage_stats = MagicMock()

                api = SerenaDashboardAPI(
                    memory_log_handler=mock_memory_log_handler,
                    tool_names=[],
                    agent=mock_agent,
                    tool_usage_stats=mock_tool_usage_stats,
                )

                # Mock SERENA_DASHBOARD_DIR to point to our temp directory
                with patch("serena.dashboard.SERENA_DASHBOARD_DIR", temp_dir):
                    # Mock SerenaPaths to return a non-existent news snippet file
                    # so all news items are considered unread
                    with patch("serena.dashboard.SerenaPaths") as mock_paths:
                        mock_paths_instance = MagicMock()
                        mock_paths_instance.news_snippet_id_file = os.path.join(temp_dir, "nonexistent.txt")
                        mock_paths.return_value = mock_paths_instance

                        # Get the client
                        client = api._app.test_client()
                        response = client.get("/news_snippet_ids")
                        data = response.get_json()

                        # Should only include news from 20260201 onwards (not 20250101)
                        assert data["status"] == "success"
                        news_ids = data["news_snippet_ids"]
                        assert 20250101 not in news_ids  # Old news filtered out
                        assert 20260201 in news_ids  # Recent news included
                        assert 20260301 in news_ids  # Future news included

    def test_news_filtering_with_read_status(self):
        """Test that news items respect both installation date and read status."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock news directory
            news_dir = Path(temp_dir) / "news"
            news_dir.mkdir()

            # Create news files
            (news_dir / "20260201.html").write_text("<div>News 1</div>")
            (news_dir / "20260202.html").write_text("<div>News 2</div>")
            (news_dir / "20260203.html").write_text("<div>News 3</div>")

            # Create a news snippet file marking 20260201 as read
            news_snippet_file = Path(temp_dir) / "last_read_news_snippet_id.txt"
            news_snippet_file.write_text("20260201")

            # Mock the installation date to be 2026-02-01
            with patch.object(SerenaDashboardAPI, "_get_installation_date_id", return_value=20260201):
                # Create mocks for the API
                mock_memory_log_handler = MagicMock()
                mock_agent = MagicMock()
                mock_tool_usage_stats = MagicMock()

                api = SerenaDashboardAPI(
                    memory_log_handler=mock_memory_log_handler,
                    tool_names=[],
                    agent=mock_agent,
                    tool_usage_stats=mock_tool_usage_stats,
                )

                # Mock SERENA_DASHBOARD_DIR and SerenaPaths
                with patch("serena.dashboard.SERENA_DASHBOARD_DIR", temp_dir):
                    with patch("serena.dashboard.SerenaPaths") as mock_paths:
                        mock_paths_instance = MagicMock()
                        mock_paths_instance.news_snippet_id_file = str(news_snippet_file)
                        mock_paths.return_value = mock_paths_instance

                        # Get the client
                        client = api._app.test_client()
                        response = client.get("/news_snippet_ids")
                        data = response.get_json()

                        # Should only include unread news after installation date
                        assert data["status"] == "success"
                        news_ids = data["news_snippet_ids"]
                        assert 20260201 not in news_ids  # Read
                        assert 20260202 in news_ids  # Unread and after installation
                        assert 20260203 in news_ids  # Unread and after installation
