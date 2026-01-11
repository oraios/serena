"""
Tests for JSON-RPC 2.0 params field handling in LSP protocol.

These tests verify the correct handling of the params field in LSP requests and notifications,
specifically ensuring:
- Void-type methods (shutdown, exit) omit params field entirely
- Methods with explicit params include them unchanged
- Methods with None params receive params: {} for Delphi/FPC compatibility

Reference: JSON-RPC 2.0 spec - params field is optional but must be object/array when present.
"""

from typing import Any

import pytest

from solidlsp.lsp_protocol_handler.server import make_notification, make_request

# =============================================================================
# Shared Assertion Helpers (DRY extraction per AI Panel recommendation)
# =============================================================================


def assert_jsonrpc_structure(
    result: dict[str, Any],
    expected_method: str,
    expected_keys: set[str],
    *,
    expected_id: Any | None = None,
) -> None:
    """Verify JSON-RPC 2.0 structural requirements with 5-point error messages.

    Args:
        result: The dict returned by make_request/make_notification
        expected_method: The method name that should be in the result
        expected_keys: Exact set of keys that should be present
        expected_id: If provided, verify the id field matches (for requests)

    """
    # Verify jsonrpc field
    assert "jsonrpc" in result, (
        f"STRUCTURE ERROR: Missing required 'jsonrpc' field.\n"
        f"Expected: jsonrpc='2.0'\n"
        f"Actual keys: {list(result.keys())}\n"
        f"GUIDANCE: All JSON-RPC 2.0 messages must include jsonrpc field."
    )
    assert result["jsonrpc"] == "2.0", (
        f"STRUCTURE ERROR: Invalid jsonrpc version.\n"
        f"Expected: '2.0'\n"
        f"Actual: {result['jsonrpc']!r}\n"
        f"GUIDANCE: JSON-RPC 2.0 requires jsonrpc='2.0' exactly."
    )

    # Verify method field
    assert "method" in result, (
        f"STRUCTURE ERROR: Missing required 'method' field.\n"
        f"Expected: method='{expected_method}'\n"
        f"Actual keys: {list(result.keys())}\n"
        f"GUIDANCE: All requests/notifications must include method field."
    )
    assert result["method"] == expected_method, (
        f"STRUCTURE ERROR: Method mismatch.\n"
        f"Expected: '{expected_method}'\n"
        f"Actual: {result['method']!r}\n"
        f"GUIDANCE: Method field must match the requested method name."
    )

    # Verify id field if expected (requests only)
    if expected_id is not None:
        assert "id" in result, (
            f"STRUCTURE ERROR: Missing required 'id' field for request.\n"
            f"Expected: id={expected_id!r}\n"
            f"Actual keys: {list(result.keys())}\n"
            f"GUIDANCE: JSON-RPC 2.0 requests must include id field."
        )
        assert result["id"] == expected_id, (
            f"STRUCTURE ERROR: Request ID mismatch.\n"
            f"Expected: {expected_id!r}\n"
            f"Actual: {result['id']!r}\n"
            f"GUIDANCE: Request ID must be preserved exactly as provided."
        )

    # Verify exact key set
    actual_keys = set(result.keys())
    if actual_keys != expected_keys:
        extra = sorted(actual_keys - expected_keys)
        missing = sorted(expected_keys - actual_keys)
        pytest.fail(
            f"STRUCTURE ERROR: Key set mismatch for method '{expected_method}'.\n"
            f"Expected keys: {sorted(expected_keys)}\n"
            f"Actual keys: {sorted(actual_keys)}\n"
            f"Extra keys: {extra}\n"
            f"Missing keys: {missing}\n"
            f"GUIDANCE: Verify key construction logic for Void-type vs normal methods."
        )


def assert_params_omitted(result: dict[str, Any], method: str, req_id: str, input_params: Any = None) -> None:
    """Assert that params field is NOT present (for Void-type methods).

    Args:
        result: The dict returned by make_request/make_notification
        method: Method name for error message context
        req_id: Requirement ID (e.g., 'REQ-1', 'REQ-AI-PANEL-GAP')
        input_params: If provided, shows what params were passed (for explicit params tests)

    """
    if "params" in result:
        input_note = f"\nInput params: {input_params}" if input_params is not None else ""
        pytest.fail(
            f"{req_id} VIOLATED: {method} method MUST omit params field entirely.{input_note}\n"
            f"Expected: No 'params' key in result\n"
            f"Actual: params={result.get('params')!r}\n"
            f"Actual keys: {list(result.keys())}\n"
            f"REASON: HLS/rust-analyzer Void types reject any params field (even empty object).\n"
            f"GUIDANCE: Void-type constraint takes precedence - implementation must omit params entirely."
        )


def assert_params_equal(result: dict[str, Any], expected_params: Any, req_id: str) -> None:
    """Assert that params field equals expected value.

    Args:
        result: The dict returned by make_request/make_notification
        expected_params: The exact params value expected
        req_id: Requirement ID for error message context

    """
    if "params" not in result:
        pytest.fail(
            f"{req_id} VIOLATED: params field missing.\n"
            f"Expected: params={expected_params!r}\n"
            f"Actual keys: {list(result.keys())}\n"
            f"GUIDANCE: Non-Void methods must include params field."
        )
    if result["params"] != expected_params:
        pytest.fail(
            f"{req_id} VIOLATED: params value mismatch.\n"
            f"Expected: {expected_params!r}\n"
            f"Actual: {result['params']!r}\n"
            f"GUIDANCE: Params must be included exactly as provided (or {{}} for None)."
        )


class TestMakeNotificationParamsHandling:
    """Test make_notification() params field handling per JSON-RPC 2.0 spec."""

    def test_shutdown_method_omits_params_entirely(self) -> None:
        """REQ-1: Void-type method 'shutdown' MUST omit params field entirely."""
        result = make_notification("shutdown", None)
        assert_jsonrpc_structure(result, "shutdown", {"jsonrpc", "method"})
        assert_params_omitted(result, "shutdown", "REQ-1")

    def test_exit_method_omits_params_entirely(self) -> None:
        """REQ-1: Void-type method 'exit' MUST omit params field entirely."""
        result = make_notification("exit", None)
        assert_jsonrpc_structure(result, "exit", {"jsonrpc", "method"})
        assert_params_omitted(result, "exit", "REQ-1")

    def test_notification_with_explicit_params_dict(self) -> None:
        """REQ-2: Methods with explicit params MUST include them unchanged."""
        test_params = {"uri": "file:///test.py", "languageId": "python"}
        result = make_notification("textDocument/didOpen", test_params)
        assert_jsonrpc_structure(result, "textDocument/didOpen", {"jsonrpc", "method", "params"})
        assert_params_equal(result, test_params, "REQ-2")

    def test_notification_with_explicit_params_list(self) -> None:
        """REQ-2: Methods with explicit params (list) MUST include them unchanged."""
        test_params = ["arg1", "arg2", "arg3"]
        result = make_notification("custom/method", test_params)
        assert_jsonrpc_structure(result, "custom/method", {"jsonrpc", "method", "params"})
        assert_params_equal(result, test_params, "REQ-2")

    def test_notification_with_none_params_sends_empty_dict(self) -> None:
        """REQ-3: Methods with None params MUST send params: {} (Delphi/FPC compat)."""
        result = make_notification("textDocument/didChange", None)
        assert_jsonrpc_structure(result, "textDocument/didChange", {"jsonrpc", "method", "params"})
        assert_params_equal(result, {}, "REQ-3")

    def test_notification_with_empty_dict_params(self) -> None:
        """REQ-2: Explicit empty dict params MUST be included unchanged."""
        result = make_notification("custom/notify", {})
        assert_jsonrpc_structure(result, "custom/notify", {"jsonrpc", "method", "params"})
        assert_params_equal(result, {}, "REQ-2")


class TestMakeRequestParamsHandling:
    """Test make_request() params field handling per JSON-RPC 2.0 spec."""

    def test_shutdown_request_omits_params_entirely(self) -> None:
        """REQ-1: Void-type method 'shutdown' MUST omit params field entirely (requests)."""
        result = make_request("shutdown", request_id=1, params=None)
        assert_jsonrpc_structure(result, "shutdown", {"jsonrpc", "method", "id"}, expected_id=1)
        assert_params_omitted(result, "shutdown", "REQ-1")

    def test_request_with_explicit_params_dict(self) -> None:
        """REQ-2: Requests with explicit params MUST include them unchanged."""
        test_params = {"textDocument": {"uri": "file:///test.py"}, "position": {"line": 10, "character": 5}}
        result = make_request("textDocument/hover", request_id=42, params=test_params)
        assert_jsonrpc_structure(result, "textDocument/hover", {"jsonrpc", "method", "id", "params"}, expected_id=42)
        assert_params_equal(result, test_params, "REQ-2")

    def test_request_with_none_params_sends_empty_dict(self) -> None:
        """REQ-3: Requests with None params MUST send params: {} (Delphi/FPC compat)."""
        result = make_request("workspace/configuration", request_id=100, params=None)
        assert_jsonrpc_structure(result, "workspace/configuration", {"jsonrpc", "method", "id", "params"}, expected_id=100)
        assert_params_equal(result, {}, "REQ-3")

    def test_request_id_preservation(self) -> None:
        """Verify request_id is correctly included in result (string ID)."""
        test_id = "unique-request-123"
        result = make_request("custom/request", request_id=test_id, params={"key": "value"})
        assert_jsonrpc_structure(result, "custom/request", {"jsonrpc", "method", "id", "params"}, expected_id=test_id)

    def test_request_with_explicit_params_list(self) -> None:
        """REQ-2: Requests with explicit params (list) MUST include them unchanged."""
        test_params = [1, 2, 3]
        result = make_request("custom/sum", request_id=99, params=test_params)
        assert_jsonrpc_structure(result, "custom/sum", {"jsonrpc", "method", "id", "params"}, expected_id=99)
        assert_params_equal(result, test_params, "REQ-2")


class TestVoidMethodsExhaustive:
    """Test all methods that should be treated as Void-type (no params)."""

    def test_shutdown_request_ignores_explicit_params_dict(self) -> None:
        """REQ-AI-PANEL-GAP: shutdown MUST omit params even when caller explicitly provides params."""
        explicit_params = {"key": "value", "another": "param"}
        result = make_request("shutdown", request_id=1, params=explicit_params)
        assert_jsonrpc_structure(result, "shutdown", {"jsonrpc", "method", "id"}, expected_id=1)
        assert_params_omitted(result, "shutdown", "REQ-AI-PANEL-GAP", input_params=explicit_params)

    def test_exit_notification_ignores_explicit_params(self) -> None:
        """REQ-AI-PANEL-GAP: exit MUST omit params even when caller explicitly provides params."""
        explicit_params = {"unexpected": "params"}
        result = make_notification("exit", explicit_params)
        assert_jsonrpc_structure(result, "exit", {"jsonrpc", "method"})
        assert_params_omitted(result, "exit", "REQ-AI-PANEL-GAP", input_params=explicit_params)

    def test_only_shutdown_and_exit_are_void_methods(self) -> None:
        """REQ-BOUNDARY: Verify EXACTLY shutdown/exit are Void-type - no more, no less."""
        # Positive verification: shutdown and exit MUST omit params
        shutdown_notif = make_notification("shutdown", None)
        exit_notif = make_notification("exit", None)
        shutdown_req = make_request("shutdown", 1, None)

        assert "params" not in shutdown_notif, "shutdown notification should omit params"
        assert "params" not in exit_notif, "exit notification should omit params"
        assert "params" not in shutdown_req, "shutdown request should omit params"

        # Negative verification: other methods MUST include params (even when None -> {})
        non_void_methods = [
            "initialize",
            "initialized",
            "textDocument/didOpen",
            "textDocument/didChange",
            "textDocument/didClose",
            "workspace/didChangeConfiguration",
            "workspace/didChangeWatchedFiles",
        ]

        for method in non_void_methods:
            result_notif = make_notification(method, None)
            result_req = make_request(method, 1, None)

            if "params" not in result_notif:
                pytest.fail(
                    f"BOUNDARY VIOLATION: '{method}' notification treated as Void-type.\n"
                    f"Expected: params field present (should be {{}})\n"
                    f"Actual keys: {list(result_notif.keys())}\n"
                    f"GUIDANCE: Only 'shutdown' and 'exit' should omit params field."
                )
            assert_params_equal(result_notif, {}, f"REQ-3 ({method} notification)")

            if "params" not in result_req:
                pytest.fail(
                    f"BOUNDARY VIOLATION: '{method}' request treated as Void-type.\n"
                    f"Expected: params field present (should be {{}})\n"
                    f"Actual keys: {list(result_req.keys())}\n"
                    f"GUIDANCE: Only 'shutdown' and 'exit' should omit params field."
                )
            assert_params_equal(result_req, {}, f"REQ-3 ({method} request)")
