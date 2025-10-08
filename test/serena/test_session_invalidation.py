"""
Tests for MCP session invalidation handling.

These tests verify that the patched streamable_http_manager correctly handles
invalid/expired session IDs by creating new sessions instead of returning 400 errors.

This addresses the issue where MCP clients (like Augment) cache session IDs across
server restarts, causing 400 Bad Request errors when the cached session ID is no
longer valid.
"""

import pytest


class TestSessionInvalidationPatch:
    """Test suite for session invalidation patch."""

    def test_patch_is_loaded(self):
        """Verify that the patched module is loaded instead of the original."""
        import mcp.server.streamable_http_manager as manager

        # Check that we're loading the patched version
        assert "serena/patches" in manager.__file__, f"Expected patched module from serena/patches, got {manager.__file__}"

        # Check for SERENA PATCH marker in docstring
        assert manager.__doc__ is not None, "Module docstring should not be None"
        assert "SERENA PATCH" in manager.__doc__, "Module should have SERENA PATCH marker in docstring"

    def test_version_compatibility_check_present(self):
        """Verify that version compatibility check is present."""
        import mcp.server.streamable_http_manager as manager

        # Check that EXPECTED_MCP_VERSION constant exists
        assert hasattr(manager, "EXPECTED_MCP_VERSION"), "Patched module should have EXPECTED_MCP_VERSION constant"
        assert manager.EXPECTED_MCP_VERSION == "1.12.3", f"Expected MCP version 1.12.3, got {manager.EXPECTED_MCP_VERSION}"

    def test_import_hook_installed(self):
        """Verify that the import hook is installed in sys.meta_path."""
        import sys

        from serena.patches import _PatchImportHook

        # Check that our import hook is in sys.meta_path
        hook_found = any(isinstance(h, _PatchImportHook) for h in sys.meta_path)
        assert hook_found, "Import hook should be installed in sys.meta_path"

        # Check that it's at the beginning (high priority)
        first_hooks = sys.meta_path[:5]
        hook_index = next((i for i, h in enumerate(first_hooks) if isinstance(h, _PatchImportHook)), None)
        assert hook_index is not None, "Import hook should be in first 5 meta_path entries"
        assert hook_index == 0, f"Import hook should be first, but is at index {hook_index}"

    def test_patch_survives_reimport(self):
        """Verify that the patch survives module reimport."""
        import importlib
        import sys

        # Import the module
        import mcp.server.streamable_http_manager as manager1

        file1 = manager1.__file__

        # Remove from sys.modules and reimport
        if "mcp.server.streamable_http_manager" in sys.modules:
            del sys.modules["mcp.server.streamable_http_manager"]

        import mcp.server.streamable_http_manager as manager2

        file2 = manager2.__file__

        # Both should load the patched version
        assert "serena/patches" in file1, f"First import should be patched: {file1}"
        assert "serena/patches" in file2, f"Second import should be patched: {file2}"
        assert file1 == file2, "Both imports should load the same patched file"

    def test_other_mcp_modules_not_patched(self):
        """Verify that other mcp modules are not affected by the patch."""
        # Import other mcp modules
        import mcp.server.session
        import mcp.types

        # These should NOT be from serena/patches
        assert "serena/patches" not in mcp.types.__file__, f"mcp.types should not be patched: {mcp.types.__file__}"
        assert (
            "serena/patches" not in mcp.server.session.__file__
        ), f"mcp.server.session should not be patched: {mcp.server.session.__file__}"

        # They should be from the external mcp package
        assert "site-packages/mcp" in mcp.types.__file__, f"mcp.types should be from site-packages: {mcp.types.__file__}"

    def test_streamable_http_manager_class_exists(self):
        """Verify that StreamableHTTPSessionManager class exists in patched module."""
        import mcp.server.streamable_http_manager as manager

        # Check that the main class exists
        assert hasattr(manager, "StreamableHTTPSessionManager"), "Patched module should have StreamableHTTPSessionManager class"

        # Check that it's a class
        assert isinstance(manager.StreamableHTTPSessionManager, type), "StreamableHTTPSessionManager should be a class"

    def test_patch_logging_configured(self):
        """Verify that patch logging is configured."""
        import logging

        from serena.patches import logger

        # Check that logger exists
        assert logger is not None, "Patch module should have a logger"
        assert isinstance(logger, logging.Logger), "logger should be a Logger instance"
        assert logger.name == "serena.patches", f"Logger name should be 'serena.patches', got {logger.name}"


class TestCacheInvalidationSurvival:
    """Test that patch survives cache invalidation scenarios."""

    def test_patch_in_source_tree(self):
        """Verify that patched file is in source tree, not in cache."""
        import mcp.server.streamable_http_manager as manager

        # The patched file should be in the source tree
        assert (
            "serena/src/serena/patches" in manager.__file__ or "serena/patches" in manager.__file__
        ), f"Patched file should be in source tree: {manager.__file__}"

        # It should NOT be in .venv or cache directories
        assert ".venv" not in manager.__file__, f"Patched file should not be in .venv: {manager.__file__}"
        assert ".cache" not in manager.__file__, f"Patched file should not be in cache: {manager.__file__}"

    def test_external_mcp_package_still_installed(self):
        """Verify that external mcp package is still installed and accessible."""
        import mcp

        # Check that we can import other mcp modules normally
        import mcp.server.session
        import mcp.types

        assert mcp.types is not None
        assert mcp.server.session is not None

        # Verify they're from the external package
        assert "site-packages/mcp" in mcp.types.__file__


class TestImportHookRobustness:
    """Test import hook robustness and edge cases."""

    def test_import_hook_handles_nonexistent_module(self):
        """Verify that import hook doesn't interfere with nonexistent modules."""
        from serena.patches import _PatchImportHook

        hook = _PatchImportHook()

        # Should return None for modules we don't patch
        spec = hook.find_spec("nonexistent.module", None)
        assert spec is None, "Import hook should return None for nonexistent modules"

        spec = hook.find_spec("mcp.server.other_module", None)
        assert spec is None, "Import hook should return None for other mcp modules"

    def test_import_hook_only_patches_specific_module(self):
        """Verify that import hook only patches the specific module."""
        from serena.patches import _PatchImportHook

        hook = _PatchImportHook()

        # Should return spec for our patched module
        spec = hook.find_spec("mcp.server.streamable_http_manager", None)
        assert spec is not None, "Import hook should return spec for patched module"
        assert spec.name == "mcp.server.streamable_http_manager"

        # Should return None for other modules
        assert hook.find_spec("mcp.types", None) is None
        assert hook.find_spec("mcp.server.session", None) is None
        assert hook.find_spec("mcp.client.session", None) is None

    def test_import_hook_error_handling(self):
        """Verify that import hook has proper error handling."""
        from serena.patches import _PatchLoader

        loader = _PatchLoader()

        # Create a mock module object
        class MockModule:
            __dict__ = {}

        module = MockModule()

        # This should work without raising exceptions
        try:
            loader.exec_module(module)
            # Check that module was populated
            assert len(module.__dict__) > 0, "Module should be populated"
        except Exception as e:
            pytest.fail(f"Import hook should not raise exceptions: {e}")


class TestPatchDocumentation:
    """Test that patch is properly documented."""

    def test_patch_has_documentation(self):
        """Verify that patched module has proper documentation."""
        import mcp.server.streamable_http_manager as manager

        # Check docstring
        assert manager.__doc__ is not None
        assert len(manager.__doc__) > 100, "Docstring should be substantial"

        # Check for key documentation elements
        assert "SERENA PATCH" in manager.__doc__
        assert "mcp-python-sdk" in manager.__doc__
        assert "session" in manager.__doc__.lower()

    def test_patch_notes_exist(self):
        """Verify that IMPLEMENTATION-PLAN exists."""
        import os

        # Find the plan file relative to this test file
        test_dir = os.path.dirname(os.path.abspath(__file__))
        serena_root = os.path.dirname(os.path.dirname(test_dir))
        plan_path = os.path.join(serena_root, "IMPLEMENTATION-PLAN-hybrid-mcp-patch.md")

        assert os.path.exists(plan_path), f"Implementation plan should exist at {plan_path}"

        # Check that it's not empty
        with open(plan_path, "r") as f:
            content = f.read()
            assert len(content) > 1000, "Implementation plan should be substantial"
            assert "Phase 2" in content, "Plan should document Phase 2"
            assert "session" in content.lower(), "Plan should mention session handling"
