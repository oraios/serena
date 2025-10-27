"""
Comprehensive integration tests for LSPManager (polyglot support).

Tests prove that Serena's LSPManager can:
1. Manage multiple language servers simultaneously (Python, Rust, Haskell, TypeScript)
2. Route files to the correct LSP based on file extension
3. Start LSPs lazily (on-demand) or eagerly (all at once)
4. Gracefully handle LSP failures (one failure doesn't crash the project)
5. Perform symbol operations within each language
6. Demonstrate cross-language reference limitations

Test Repository Structure:
- python/calculator.py: Python Calculator class and helper functions
- rust/src/lib.rs: Rust Calculator struct and helper functions
- haskell/src/Calculator.hs: Haskell Calculator data type and functions (our calling card!)
- typescript/calculator.ts: TypeScript Calculator class and helper functions

All 4 languages implement the same Calculator interface to demonstrate:
- Polyglot routing works correctly
- Cross-language references don't work (inherent LSP limitation)
"""

import sys
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig
from serena.lsp_manager import LSPManager
from solidlsp.ls_config import Language
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


@pytest.fixture
def polyglot_test_repo():
    """Path to polyglot test repository with 4 languages."""
    return Path(__file__).parent.parent.parent / "resources" / "repos" / "polyglot" / "test_repo"


@pytest.fixture
def project_config(polyglot_test_repo):
    """Project configuration for polyglot test repository."""
    return ProjectConfig(
        project_name="polyglot_test_repo",
        languages=[Language.PYTHON, Language.RUST, Language.HASKELL, Language.TYPESCRIPT],
        encoding="utf-8",
    )


@pytest.fixture
def lsp_logger():
    """Logger for language server operations."""
    return LanguageServerLogger()


@pytest.fixture
def lsp_settings():
    """SolidLSP settings."""
    return SolidLSPSettings()




@pytest.mark.polyglot
@pytest.mark.skipif(sys.platform == "win32", reason="Multi-LSP not fully tested on Windows")
class TestSyncWrapperEventLoopSafety:
    """
    Test sync wrapper event loop safety (H1 from AI Panel).
    
    Per AI Panel Turn 1 feedback: Sync wrappers must detect running event loops
    and raise clear RuntimeError to prevent nested event loop bugs.
    """

    def test_sync_wrapper_works_from_sync_context(
        self, polyglot_test_repo, project_config, lsp_logger, lsp_settings
    ):
        """get_language_server_for_file_sync should work when called from sync context."""
        manager = LSPManager(
            languages=[Language.PYTHON],
            project_root=str(polyglot_test_repo),
            config=project_config,
            logger=lsp_logger,
            settings=lsp_settings,
        )

        # Call from synchronous context (no event loop running)
        lsp = manager.get_language_server_for_file_sync("python/calculator.py")
        
        # Should work fine
        assert lsp is not None
        
        # Cleanup
        manager.shutdown_all_sync()

    def test_sync_wrapper_raises_from_async_context(
        self, polyglot_test_repo, project_config, lsp_logger, lsp_settings
    ):
        """get_language_server_for_file_sync should raise RuntimeError when called from async context."""
        import asyncio
        
        manager = LSPManager(
            languages=[Language.PYTHON],
            project_root=str(polyglot_test_repo),
            config=project_config,
            logger=lsp_logger,
            settings=lsp_settings,
        )

        # Create an async function that calls the sync wrapper
        async def call_sync_from_async():
            # This should raise RuntimeError
            return manager.get_language_server_for_file_sync("python/calculator.py")
        
        # Run it and expect RuntimeError
        with pytest.raises(RuntimeError, match="Cannot call get_language_server_for_file_sync.*from async context"):
            asyncio.run(call_sync_from_async())

    def test_sync_wrapper_error_message_guides_to_async_api(
        self, polyglot_test_repo, project_config, lsp_logger, lsp_settings
    ):
        """Error message should guide user to use async version instead."""
        import asyncio
        
        manager = LSPManager(
            languages=[Language.PYTHON],
            project_root=str(polyglot_test_repo),
            config=project_config,
            logger=lsp_logger,
            settings=lsp_settings,
        )

        # Create an async function that calls the sync wrapper
        async def call_sync_from_async():
            return manager.get_language_server_for_file_sync("python/calculator.py")
        
        # Capture the error
        with pytest.raises(RuntimeError) as exc_info:
            asyncio.run(call_sync_from_async())
        
        # Verify error message mentions async alternative
        error_message = str(exc_info.value)
        assert "Use get_language_server_for_file() instead" in error_message

    def test_shutdown_all_sync_works_from_sync_context(
        self, polyglot_test_repo, project_config, lsp_logger, lsp_settings
    ):
        """shutdown_all_sync should work when called from sync context."""
        manager = LSPManager(
            languages=[Language.PYTHON],
            project_root=str(polyglot_test_repo),
            config=project_config,
            logger=lsp_logger,
            settings=lsp_settings,
        )

        # Start and shutdown from sync context
        lsp = manager.get_language_server_for_file_sync("python/calculator.py")
        assert lsp is not None
        
        # Should work fine
        manager.shutdown_all_sync()

    def test_shutdown_all_sync_raises_from_async_context(
        self, polyglot_test_repo, project_config, lsp_logger, lsp_settings
    ):
        """shutdown_all_sync should raise RuntimeError when called from async context."""
        import asyncio
        
        manager = LSPManager(
            languages=[Language.PYTHON],
            project_root=str(polyglot_test_repo),
            config=project_config,
            logger=lsp_logger,
            settings=lsp_settings,
        )

        # Create an async function that calls the sync wrapper
        async def call_shutdown_sync_from_async():
            # Start LSP first
            await manager.start_all(lazy=True)
            # This should raise RuntimeError
            manager.shutdown_all_sync()
        
        # Run it and expect RuntimeError
        with pytest.raises(RuntimeError, match="Cannot call shutdown_all_sync.*from async context"):
            asyncio.run(call_shutdown_sync_from_async())
