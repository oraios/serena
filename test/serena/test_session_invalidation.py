"""
Tests for MCP session invalidation handling.

These tests verify that the patched streamable_http_manager correctly handles
invalid/expired session IDs by creating new sessions instead of returning 400 errors.

This addresses the issue where MCP clients (like Augment) cache session IDs across
server restarts, causing 400 Bad Request errors when the cached session ID is no
longer valid.
"""

import importlib
import os

import pytest


# Fixtures for common setup
@pytest.fixture
def patched_manager():
    """Import and return the patched streamable_http_manager module."""
    import mcp.server.streamable_http_manager as manager

    return manager


@pytest.fixture
def import_hook():
    """Return a new instance of the patch import hook."""
    from serena.patches import _PatchImportHook

    return _PatchImportHook()


@pytest.fixture
def patch_loader():
    """Return a new instance of the patch loader."""
    from serena.patches import _PatchLoader

    return _PatchLoader()


@pytest.fixture
def serena_root():
    """Return the Serena project root directory."""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(test_dir))


class TestSessionInvalidationPatch:
    """Test suite for session invalidation patch."""

    def test_patch_is_loaded(self, patched_manager):
        """Verify that the patched module is loaded instead of the original."""
        assert (
            "serena/patches" in patched_manager.__file__
        ), f"Patched module should be loaded from serena/patches, got {patched_manager.__file__}"

        assert patched_manager.__doc__ is not None, "Module docstring should not be None"
        assert "SERENA PATCH" in patched_manager.__doc__, "Module should have SERENA PATCH marker in docstring"

    def test_version_compatibility_check_present(self, patched_manager):
        """Verify that version compatibility check is present."""
        assert hasattr(patched_manager, "EXPECTED_MCP_VERSION"), "Patched module should have EXPECTED_MCP_VERSION constant"
        assert patched_manager.EXPECTED_MCP_VERSION == "1.12.3", f"Expected MCP version 1.12.3, got {patched_manager.EXPECTED_MCP_VERSION}"

    def test_import_hook_installed(self):
        """Verify that the import hook is installed in sys.meta_path."""
        import sys

        from serena.patches import _PatchImportHook

        hook_found = any(isinstance(h, _PatchImportHook) for h in sys.meta_path)
        assert hook_found, "Import hook should be installed in sys.meta_path"

        # Check that it's at the beginning (high priority)
        first_hooks = sys.meta_path[:5]
        hook_index = next((i for i, h in enumerate(first_hooks) if isinstance(h, _PatchImportHook)), None)
        assert hook_index is not None, "Import hook should be in first 5 meta_path entries"
        assert hook_index == 0, f"Import hook should be first, but is at index {hook_index}"

    def test_patch_survives_reimport(self, patched_manager, monkeypatch):
        """Verify that the patch survives module reimport."""
        import sys

        file1 = patched_manager.__file__

        # Remove from sys.modules and reimport (using monkeypatch for cleanup)
        monkeypatch.delitem(sys.modules, "mcp.server.streamable_http_manager", raising=False)

        import mcp.server.streamable_http_manager as manager2

        file2 = manager2.__file__

        # Both should load the patched version
        assert "serena/patches" in file1, f"First import should be patched: {file1}"
        assert "serena/patches" in file2, f"Second import should be patched: {file2}"
        assert file1 == file2, "Both imports should load the same patched file"

    @pytest.mark.parametrize(
        "module_name,should_be_patched",
        [
            ("mcp.types", False),
            ("mcp.server.session", False),
            ("mcp.server.streamable_http_manager", True),
        ],
    )
    def test_module_patch_status(self, module_name, should_be_patched):
        """Verify that only the target module is patched."""
        module = importlib.import_module(module_name)
        is_patched = "serena/patches" in module.__file__

        assert is_patched == should_be_patched, (
            f"Module {module_name} patch status incorrect: "
            f"expected {'patched' if should_be_patched else 'not patched'}, "
            f"got {'patched' if is_patched else 'not patched'} (file: {module.__file__})"
        )

        # Non-patched modules should be from site-packages
        if not should_be_patched:
            assert (
                "site-packages/mcp" in module.__file__
            ), f"Non-patched module {module_name} should be from site-packages, got {module.__file__}"

    def test_streamable_http_manager_class_exists(self, patched_manager):
        """Verify that StreamableHTTPSessionManager class exists in patched module."""
        assert hasattr(patched_manager, "StreamableHTTPSessionManager"), "Patched module should have StreamableHTTPSessionManager class"
        assert isinstance(patched_manager.StreamableHTTPSessionManager, type), "StreamableHTTPSessionManager should be a class"

    def test_patch_logging_configured(self):
        """Verify that patch logging is configured."""
        import logging

        from serena.patches import logger

        assert logger is not None, "Patch module should have a logger"
        assert isinstance(logger, logging.Logger), "logger should be a Logger instance"
        assert logger.name == "serena.patches", f"Logger name should be 'serena.patches', got {logger.name}"


class TestCacheInvalidationSurvival:
    """Test that patch survives cache invalidation scenarios."""

    def test_patch_in_source_tree(self, patched_manager):
        """Verify that patched file is in source tree, not in cache."""
        assert (
            "serena/patches" in patched_manager.__file__
        ), f"Patched file should be in source tree (serena/patches), got {patched_manager.__file__}"

        assert ".venv" not in patched_manager.__file__, f"Patched file should not be in .venv, got {patched_manager.__file__}"
        assert ".cache" not in patched_manager.__file__, f"Patched file should not be in cache, got {patched_manager.__file__}"

    @pytest.mark.parametrize("module_name", ["mcp.types", "mcp.server.session"])
    def test_external_mcp_modules_accessible(self, module_name):
        """Verify that external mcp package modules are still accessible."""
        module = importlib.import_module(module_name)

        assert module is not None, f"Module {module_name} should be importable"
        assert (
            "site-packages/mcp" in module.__file__
        ), f"Module {module_name} should be from external package (site-packages), got {module.__file__}"


class TestImportHookRobustness:
    """Test import hook robustness and edge cases."""

    @pytest.mark.parametrize(
        "module_name,should_return_spec",
        [
            ("nonexistent.module", False),
            ("mcp.server.other_module", False),
            ("mcp.types", False),
            ("mcp.server.session", False),
            ("mcp.client.session", False),
            ("mcp.server.streamable_http_manager", True),
        ],
    )
    def test_import_hook_selectivity(self, import_hook, module_name, should_return_spec):
        """Verify that import hook only returns spec for the target module."""
        spec = import_hook.find_spec(module_name, None)

        if should_return_spec:
            assert spec is not None, f"Import hook should return spec for {module_name}"
            assert spec.name == module_name, f"Spec name should match module name: {module_name}"
        else:
            assert spec is None, f"Import hook should return None for {module_name}"

    def test_import_hook_error_handling(self, patch_loader):
        """Verify that import hook has proper error handling."""

        # Create a mock module object
        class MockModule:
            __dict__ = {}

        module = MockModule()

        # This should work without raising exceptions
        try:
            patch_loader.exec_module(module)
            assert len(module.__dict__) > 0, "Module should be populated after exec_module"
        except Exception as e:
            pytest.fail(f"Import hook should not raise exceptions during normal operation: {e}")


class TestPatchDocumentation:
    """Test that patch is properly documented."""

    @pytest.mark.parametrize(
        "doc_element",
        ["SERENA PATCH", "mcp-python-sdk", "session"],
    )
    def test_patch_has_required_documentation(self, patched_manager, doc_element):
        """Verify that patched module has required documentation elements."""
        assert patched_manager.__doc__ is not None, "Module should have docstring"
        assert len(patched_manager.__doc__) > 100, "Docstring should be substantial (>100 chars)"

        # Check for specific documentation element (case-insensitive for 'session')
        if doc_element.lower() == "session":
            assert doc_element in patched_manager.__doc__.lower(), f"Docstring should mention '{doc_element}' (case-insensitive)"
        else:
            assert doc_element in patched_manager.__doc__, f"Docstring should contain '{doc_element}'"

    def test_implementation_plan_exists(self, serena_root):
        """Verify that IMPLEMENTATION-PLAN exists and is substantial."""
        plan_path = os.path.join(serena_root, "IMPLEMENTATION-PLAN-hybrid-mcp-patch.md")

        assert os.path.exists(plan_path), f"Implementation plan should exist at {plan_path}"

        with open(plan_path) as f:
            content = f.read()

        assert len(content) > 1000, "Implementation plan should be substantial (>1000 chars)"
        assert "Phase 2" in content, "Plan should document Phase 2"
        assert "session" in content.lower(), "Plan should mention session handling"
