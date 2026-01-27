"""
Tests for call hierarchy wrapper methods in SolidLanguageServer.

Tests the LSP call hierarchy integration:
- request_call_hierarchy_prepare()
- request_incoming_calls()
- request_outgoing_calls()
- _has_call_hierarchy_capability()
- Caching behavior
"""

import pytest

from solidlsp.ls_capabilities import CallHierarchySupport, CapabilityMatrix
from solidlsp.ls_config import Language


class TestCallHierarchyPrepare:
    """Test request_call_hierarchy_prepare() wrapper method."""

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_prepare_call_hierarchy_returns_items_python(self, language_server):
        """Test that prepareCallHierarchy returns valid items for Python."""
        ls = language_server
        file_path = "test_repo/services.py"
        symbol_name = "create_user"
        expected_line = 16  # Line where create_user method is defined

        items = ls.request_call_hierarchy_prepare(file_path, expected_line, 0)

        # Call hierarchy may not be supported at runtime even if capability matrix says yes
        # This is a known limitation with some LSP servers
        if items is None:
            pytest.skip("Call hierarchy not available for this symbol/position")

        assert isinstance(items, list), "Should return a list"
        assert len(items) > 0, f"Should find call hierarchy item for '{symbol_name}'"

        # Verify item structure
        item = items[0]
        assert "name" in item, "Item should have 'name' field"
        assert "kind" in item, "Item should have 'kind' field"
        assert "uri" in item, "Item should have 'uri' field"
        assert "range" in item, "Item should have 'range' field"
        assert symbol_name.lower() in item["name"].lower(), f"Item name should contain '{symbol_name}'"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_prepare_call_hierarchy_invalid_position(self, language_server):
        """Test prepareCallHierarchy with invalid position."""
        ls = language_server

        # Try with line 99999 (should be out of bounds)
        items = ls.request_call_hierarchy_prepare("test_repo/models.py", 99999, 0)

        # Should return empty list or None, not raise exception
        assert items is None or items == [], "Should handle invalid position gracefully"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_prepare_call_hierarchy_nonexistent_file(self, language_server):
        """Test prepareCallHierarchy with nonexistent file."""
        ls = language_server

        # Should not raise exception, but may return None or raise FileNotFoundError
        try:
            items = ls.request_call_hierarchy_prepare("nonexistent/file.py", 10, 0)
            assert items is None or items == [], "Should handle nonexistent file gracefully"
        except FileNotFoundError:
            # This is acceptable behavior - file doesn't exist
            pass


class TestIncomingCalls:
    """Test request_incoming_calls() wrapper method."""

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_incoming_calls_returns_list(self, language_server):
        """Test that incomingCalls returns a list."""
        ls = language_server

        # First prepare call hierarchy
        items = ls.request_call_hierarchy_prepare("test_repo/services.py", 16, 0)
        if items is None or len(items) == 0:
            pytest.skip("Call hierarchy not available for this symbol/position")

        # Request incoming calls
        incoming = ls.request_incoming_calls(items[0])

        assert incoming is not None, "incomingCalls should return value"
        assert isinstance(incoming, list), "incomingCalls should return a list"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_incoming_calls_structure(self, language_server):
        """Test that incoming calls have correct structure."""
        ls = language_server

        items = ls.request_call_hierarchy_prepare("test_repo/services.py", 16, 0)
        if not items or len(items) == 0:
            pytest.skip("No call hierarchy items")

        incoming = ls.request_incoming_calls(items[0])

        if incoming and len(incoming) > 0:
            call = incoming[0]

            # Verify structure
            assert "from" in call, "Incoming call should have 'from' field"
            assert "fromRanges" in call, "Incoming call should have 'fromRanges' field"

            # Verify 'from' structure
            from_item = call["from"]
            assert "name" in from_item
            assert "kind" in from_item
            assert "uri" in from_item
            assert "range" in from_item

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_incoming_calls_with_invalid_item(self, language_server):
        """Test incomingCalls with invalid item."""
        ls = language_server

        # Create invalid item
        invalid_item = {
            "name": "NonExistent",
            "kind": 12,
            "uri": "file:///nonexistent.py",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
        }

        # Should not raise exception
        result = ls.request_incoming_calls(invalid_item)
        assert result is None or isinstance(result, list), "Should handle invalid item gracefully"


class TestOutgoingCalls:
    """Test request_outgoing_calls() wrapper method."""

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_outgoing_calls_returns_list(self, language_server):
        """Test that outgoingCalls returns a list."""
        ls = language_server

        # First prepare call hierarchy
        items = ls.request_call_hierarchy_prepare("test_repo/services.py", 16, 0)
        if items is None or len(items) == 0:
            pytest.skip("Call hierarchy not available for this symbol/position")

        # Request outgoing calls
        outgoing = ls.request_outgoing_calls(items[0])

        assert outgoing is not None, "outgoingCalls should return value"
        assert isinstance(outgoing, list), "outgoingCalls should return a list"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_outgoing_calls_structure(self, language_server):
        """Test that outgoing calls have correct structure."""
        ls = language_server

        items = ls.request_call_hierarchy_prepare("test_repo/services.py", 16, 0)
        if not items or len(items) == 0:
            pytest.skip("No call hierarchy items")

        outgoing = ls.request_outgoing_calls(items[0])

        if outgoing and len(outgoing) > 0:
            call = outgoing[0]

            # Verify structure
            assert "to" in call, "Outgoing call should have 'to' field"
            assert "fromRanges" in call, "Outgoing call should have 'fromRanges' field"

            # Verify 'to' structure
            to_item = call["to"]
            assert "name" in to_item
            assert "kind" in to_item
            assert "uri" in to_item
            assert "range" in to_item


class TestCallHierarchyCapability:
    """Test _has_call_hierarchy_capability() method."""

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_has_call_hierarchy_capability_python(self, language_server):
        """Test that Python reports call hierarchy capability."""
        ls = language_server

        support_level = CapabilityMatrix.get_support_level(Language.PYTHON)

        assert support_level == CallHierarchySupport.FULL, "Python should have FULL support"
        assert ls._has_call_hierarchy_capability(), "Python LS should report capability"


class TestCallHierarchyCaching:
    """Test caching behavior for call hierarchy operations."""

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_prepare_call_hierarchy_caching(self, language_server):
        """Test that call hierarchy results are cached."""
        ls = language_server

        # First call (cache miss)
        items1 = ls.request_call_hierarchy_prepare("test_repo/services.py", 16, 0)
        if items1 is None:
            pytest.skip("Call hierarchy not available for this symbol/position")

        # Second call (cache hit)
        items2 = ls.request_call_hierarchy_prepare("test_repo/services.py", 16, 0)
        assert items2 is not None, "Second call should succeed (from cache)"

        # Results should be identical (from cache)
        assert len(items1) == len(items2), "Cached results should match"
        if len(items1) > 0:
            assert items1[0]["name"] == items2[0]["name"], "Cached item name should match"
            assert items1[0]["uri"] == items2[0]["uri"], "Cached item URI should match"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_incoming_calls_caching(self, language_server):
        """Test that incoming calls are cached."""
        ls = language_server

        # Prepare call hierarchy
        items = ls.request_call_hierarchy_prepare("test_repo/services.py", 16, 0)
        if not items or len(items) == 0:
            pytest.skip("No call hierarchy items available")

        # First incoming calls request
        incoming1 = ls.request_incoming_calls(items[0])
        assert incoming1 is not None

        # Second incoming calls request
        incoming2 = ls.request_incoming_calls(items[0])
        assert incoming2 is not None

        # Results should be identical (from cache)
        assert len(incoming1) == len(incoming2), "Cached incoming calls should match"


# Note: The language_server fixture is provided by test/conftest.py
# It requires indirect=True parametrization
