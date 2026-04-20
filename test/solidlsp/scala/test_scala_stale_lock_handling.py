"""
Tests for ScalaLanguageServer stale lock detection and handling modes.

These tests verify the ScalaLanguageServer's behavior when detecting stale Metals locks.
They use mocking to avoid requiring an actual Scala project or Metals server.
"""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from _pytest.logging import LogCaptureFixture

from solidlsp.language_servers.scala_language_server import ScalaLanguageServer
from solidlsp.ls_config import Language
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.metals_db_utils import MetalsDbStatus, MetalsLockInfo

pytestmark = pytest.mark.scala


class TestStaleLockHandling:
    """Tests for ScalaLanguageServer stale lock detection and handling modes."""

    @pytest.fixture
    def sample_lock_info(self, tmp_path: Path) -> MetalsLockInfo:
        """Create a sample MetalsLockInfo for testing."""
        lock_path = tmp_path / ".metals" / "metals.mv.db.lock.db"
        return MetalsLockInfo(
            pid=12345,
            port=9092,
            lock_path=lock_path,
            is_stale=True,
            raw_content="SERVER:localhost:9092:12345",
        )

    @pytest.fixture
    def mock_setup_dependencies(self) -> Any:
        """Mock _setup_runtime_dependencies to avoid needing Java/Coursier."""
        return patch.object(
            ScalaLanguageServer,
            "_setup_runtime_dependencies",
            return_value=["/fake/metals"],
        )

    def test_auto_clean_mode_cleans_stale_lock(
        self,
        tmp_path: Path,
        sample_lock_info: MetalsLockInfo,
        mock_setup_dependencies: Any,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test AUTO_CLEAN mode removes stale lock and proceeds."""
        cleanup_mock = MagicMock(return_value=True)

        with (
            patch(
                "solidlsp.util.metals_db_utils.check_metals_db_status",
                return_value=(MetalsDbStatus.STALE_LOCK, sample_lock_info),
            ),
            patch(
                "solidlsp.util.metals_db_utils.cleanup_stale_lock",
                cleanup_mock,
            ),
            mock_setup_dependencies,
            patch.object(ScalaLanguageServer, "__init__", lambda self, *args, **kwargs: None),
        ):
            # Create instance without calling __init__
            ls = object.__new__(ScalaLanguageServer)
            settings = SolidLSPSettings(ls_specific_settings={Language.SCALA: {"on_stale_lock": "auto-clean"}})

            # Call the method under test
            ls._check_metals_db_status(str(tmp_path), settings)

            # Verify cleanup was called
            cleanup_mock.assert_called_once_with(sample_lock_info.lock_path)

    def test_warn_mode_logs_warning_without_cleanup(
        self,
        tmp_path: Path,
        sample_lock_info: MetalsLockInfo,
        mock_setup_dependencies: Any,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test WARN mode logs warning but does not clean up."""
        cleanup_mock = MagicMock(return_value=True)

        with (
            patch(
                "solidlsp.util.metals_db_utils.check_metals_db_status",
                return_value=(MetalsDbStatus.STALE_LOCK, sample_lock_info),
            ),
            patch(
                "solidlsp.util.metals_db_utils.cleanup_stale_lock",
                cleanup_mock,
            ),
            mock_setup_dependencies,
            caplog.at_level(logging.WARNING),
        ):
            ls = object.__new__(ScalaLanguageServer)
            settings = SolidLSPSettings(ls_specific_settings={Language.SCALA: {"on_stale_lock": "warn"}})

            ls._check_metals_db_status(str(tmp_path), settings)

            # Verify cleanup was NOT called
            cleanup_mock.assert_not_called()

            # Verify warning was logged
            assert any("Stale Metals lock detected" in record.message for record in caplog.records)

    def test_fail_mode_raises_exception(
        self,
        tmp_path: Path,
        sample_lock_info: MetalsLockInfo,
        mock_setup_dependencies: Any,
    ) -> None:
        """Test FAIL mode raises MetalsStaleLockError."""
        from solidlsp.ls_exceptions import MetalsStaleLockError

        with (
            patch(
                "solidlsp.util.metals_db_utils.check_metals_db_status",
                return_value=(MetalsDbStatus.STALE_LOCK, sample_lock_info),
            ),
            mock_setup_dependencies,
            pytest.raises(MetalsStaleLockError) as exc_info,
        ):
            ls = object.__new__(ScalaLanguageServer)
            settings = SolidLSPSettings(ls_specific_settings={Language.SCALA: {"on_stale_lock": "fail"}})

            ls._check_metals_db_status(str(tmp_path), settings)

        assert str(sample_lock_info.lock_path) in str(exc_info.value)

    def test_active_instance_logs_info_when_enabled(
        self,
        tmp_path: Path,
        mock_setup_dependencies: Any,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test ACTIVE_INSTANCE logs info message when log_multi_instance_notice is true."""
        active_lock_info = MetalsLockInfo(
            pid=99999,
            port=9092,
            lock_path=tmp_path / ".metals" / "metals.mv.db.lock.db",
            is_stale=False,
            raw_content="SERVER:localhost:9092:99999",
        )

        with (
            patch(
                "solidlsp.util.metals_db_utils.check_metals_db_status",
                return_value=(MetalsDbStatus.ACTIVE_INSTANCE, active_lock_info),
            ),
            mock_setup_dependencies,
            caplog.at_level(logging.INFO),
        ):
            ls = object.__new__(ScalaLanguageServer)
            settings = SolidLSPSettings(
                ls_specific_settings={
                    Language.SCALA: {
                        "on_stale_lock": "auto-clean",
                        "log_multi_instance_notice": True,
                    }
                }
            )

            ls._check_metals_db_status(str(tmp_path), settings)

            # Verify info about multi-instance was logged
            assert any("Another Metals instance detected" in record.message for record in caplog.records)

    def test_active_instance_silent_when_notice_disabled(
        self,
        tmp_path: Path,
        mock_setup_dependencies: Any,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test ACTIVE_INSTANCE does not log when log_multi_instance_notice is false."""
        active_lock_info = MetalsLockInfo(
            pid=99999,
            port=9092,
            lock_path=tmp_path / ".metals" / "metals.mv.db.lock.db",
            is_stale=False,
            raw_content="SERVER:localhost:9092:99999",
        )

        with (
            patch(
                "solidlsp.util.metals_db_utils.check_metals_db_status",
                return_value=(MetalsDbStatus.ACTIVE_INSTANCE, active_lock_info),
            ),
            mock_setup_dependencies,
            caplog.at_level(logging.INFO),
        ):
            ls = object.__new__(ScalaLanguageServer)
            settings = SolidLSPSettings(
                ls_specific_settings={
                    Language.SCALA: {
                        "on_stale_lock": "auto-clean",
                        "log_multi_instance_notice": False,
                    }
                }
            )

            ls._check_metals_db_status(str(tmp_path), settings)

            # Verify no multi-instance message was logged
            assert not any("Another Metals instance detected" in record.message for record in caplog.records)

    def test_no_database_proceeds_silently(
        self,
        tmp_path: Path,
        mock_setup_dependencies: Any,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test NO_DATABASE status proceeds without any special handling."""
        with (
            patch(
                "solidlsp.util.metals_db_utils.check_metals_db_status",
                return_value=(MetalsDbStatus.NO_DATABASE, None),
            ),
            mock_setup_dependencies,
            caplog.at_level(logging.DEBUG),
        ):
            ls = object.__new__(ScalaLanguageServer)
            settings = SolidLSPSettings(ls_specific_settings={Language.SCALA: {"on_stale_lock": "auto-clean"}})

            # Should complete without error
            ls._check_metals_db_status(str(tmp_path), settings)

            # No stale lock or multi-instance messages
            assert not any("Stale" in record.message for record in caplog.records)
            assert not any("Another Metals instance" in record.message for record in caplog.records)

    def test_no_lock_proceeds_silently(
        self,
        tmp_path: Path,
        mock_setup_dependencies: Any,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test NO_LOCK status proceeds without any special handling."""
        with (
            patch(
                "solidlsp.util.metals_db_utils.check_metals_db_status",
                return_value=(MetalsDbStatus.NO_LOCK, None),
            ),
            mock_setup_dependencies,
            caplog.at_level(logging.DEBUG),
        ):
            ls = object.__new__(ScalaLanguageServer)
            settings = SolidLSPSettings(ls_specific_settings={Language.SCALA: {"on_stale_lock": "auto-clean"}})

            # Should complete without error
            ls._check_metals_db_status(str(tmp_path), settings)

            # No stale lock or multi-instance messages
            assert not any("Stale" in record.message for record in caplog.records)
            assert not any("Another Metals instance" in record.message for record in caplog.records)
