# SPDX-License-Identifier: GPL-3.0-or-later

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from serena.connection_access import ConnectionAccessControl, ConnectionPermission


def test_disabled_when_no_tokens():
    ac = ConnectionAccessControl({})
    assert ac.enabled is False
    assert ac.allows(None, can_edit=True)
    assert ac.resolve_permission({}) == ConnectionPermission.EDIT


def test_token_maps_to_permission():
    ac = ConnectionAccessControl({"r1": "read", "w1": "edit"})
    assert ac.enabled
    assert ac.permission_for_token("r1") == ConnectionPermission.READ
    assert ac.permission_for_token("w1") == ConnectionPermission.EDIT
    assert ac.permission_for_token("nope") is None


def test_resolve_permission_from_bearer_header():
    ac = ConnectionAccessControl({"r1": "read", "w1": "edit"})
    assert ac.resolve_permission({"Authorization": "Bearer r1"}) == ConnectionPermission.READ
    assert ac.resolve_permission({"authorization": "bearer w1"}) == ConnectionPermission.EDIT
    assert ac.resolve_permission({}) is None
    assert ac.resolve_permission({"Authorization": "Bearer unknown"}) is None
    assert ac.resolve_permission({"Authorization": "Basic abc"}) is None


def test_missing_token_denies_all_tools_when_enabled():
    ac = ConnectionAccessControl({"r1": "read", "w1": "edit"})
    assert not ac.allows(None, can_edit=False)
    assert not ac.allows(None, can_edit=True)
    assert ac.allows(ConnectionPermission.READ, can_edit=False)
    assert not ac.allows(ConnectionPermission.READ, can_edit=True)
    assert ac.allows(ConnectionPermission.EDIT, can_edit=True)


def test_headers_from_mcp_context():
    ac = ConnectionAccessControl({"r1": "read"})
    headers = {"Authorization": "Bearer r1"}
    ctx = SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers=headers)))
    assert ac.permission_for_mcp_context(ctx) == ConnectionPermission.READ
    assert ac.permission_for_mcp_context(None) is None
    assert ac.permission_for_mcp_context(SimpleNamespace()) is None
    assert ac.permission_for_mcp_context(SimpleNamespace(request_context=None)) is None


def test_token_verifier_scopes_and_rejects_unknown():
    import asyncio

    ac = ConnectionAccessControl({"r1": "read", "w1": "edit"})
    verifier = ac.token_verifier
    tok = asyncio.run(verifier.verify_token("r1"))
    assert tok is not None
    assert tok.scopes == ["read"]
    tok = asyncio.run(verifier.verify_token("w1"))
    assert tok.scopes == ["edit"]
    assert asyncio.run(verifier.verify_token("nope")) is None


def test_permission_from_access_token_scopes(monkeypatch):
    from serena.connection_access import ConnectionAccessControl, ConnectionPermission

    class FakeToken:
        def __init__(self, scopes):
            self.scopes = scopes

    monkeypatch.setattr(
        "mcp.server.auth.middleware.auth_context.get_access_token",
        lambda: FakeToken(["edit"]),
    )
    assert ConnectionAccessControl.permission_from_access_token_scopes() == ConnectionPermission.EDIT

    monkeypatch.setattr(
        "mcp.server.auth.middleware.auth_context.get_access_token",
        lambda: FakeToken(["read"]),
    )
    assert ConnectionAccessControl.permission_from_access_token_scopes() == ConnectionPermission.READ

    monkeypatch.setattr(
        "mcp.server.auth.middleware.auth_context.get_access_token",
        lambda: None,
    )
    assert ConnectionAccessControl.permission_from_access_token_scopes() is None


def test_permission_for_mcp_context_prefers_scopes(monkeypatch):
    from serena.connection_access import ConnectionAccessControl, ConnectionPermission

    class FakeToken:
        scopes = ["edit"]

    monkeypatch.setattr(
        "mcp.server.auth.middleware.auth_context.get_access_token",
        lambda: FakeToken(),
    )
    ac = ConnectionAccessControl({"r1": "read"})
    # scopes win even if headers say read-only
    ctx = SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers={"Authorization": "Bearer r1"})))
    assert ac.permission_for_mcp_context(ctx) == ConnectionPermission.EDIT


def test_headers_from_starlette_request_headers_case_insensitive():
    # Starlette Headers behave like a mapping with case-insensitive keys
    class FakeHeaders:
        def items(self):
            return [("authorization", "Bearer w1")]

    ac = ConnectionAccessControl({"w1": "edit"})
    assert ac.extract_bearer_token(FakeHeaders()) == "w1"


def test_invalid_yaml_permission_entries_ignored():
    ac = ConnectionAccessControl({"ok": "read", "bad": "admin", "": "edit"})
    assert ac.enabled
    assert ac.permission_for_token("ok") == ConnectionPermission.READ
    assert ac.permission_for_token("bad") is None


def _make_tool_mock(name: str, can_edit: bool, result: str = "ok"):
    from mcp.server.mcpserver.utilities.func_metadata import func_metadata

    def apply(name_path: str, relative_path: str = "", body: str = "") -> str:
        return result

    tool = MagicMock()
    tool.get_name.return_value = name
    tool.get_apply_docstring.return_value = f"Doc for {name}."
    tool.get_apply_fn_metadata.return_value = func_metadata(apply, structured_output=False)
    tool.agent.get_context.return_value.tool_description_overrides = {}
    tool.can_edit.return_value = can_edit
    tool.apply_ex.return_value = result
    return tool


def _make_mcp_tool(name: str, can_edit: bool, ac: ConnectionAccessControl | None, result: str = "ok"):
    from serena.mcp import SerenaFastMCPTool

    return SerenaFastMCPTool(
        _make_tool_mock(name, can_edit, result),
        openai_tool_compatible=False,
        structured_output=False,
        access_control=ac,
    )


def _ctx(token: str | None):
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers=headers)))


def test_execute_fn_rejects_edit_on_read_token():
    from mcp.server.mcpserver.exceptions import ToolError

    ac = ConnectionAccessControl({"r1": "read", "w1": "edit"})
    mcp_tool = _make_mcp_tool("replace_symbol_body", True, ac)

    with pytest.raises(ToolError, match="edit permission"):
        mcp_tool.fn(name_path="x", relative_path="y", body="z", mcp_ctx=_ctx("r1"))

    with pytest.raises(ToolError, match="access token"):
        mcp_tool.fn(name_path="x", relative_path="y", body="z", mcp_ctx=_ctx(None))

    assert mcp_tool.fn(name_path="x", relative_path="y", body="z", mcp_ctx=_ctx("w1")) == "ok"


def test_execute_fn_allows_read_tools_on_read_token():
    ac = ConnectionAccessControl({"r1": "read"})
    mcp_tool = _make_mcp_tool("find_symbol", False, ac, result="found")
    assert mcp_tool.fn(name_path="x", mcp_ctx=_ctx("r1")) == "found"


def test_execute_fn_skips_check_when_access_control_disabled():
    mcp_tool = _make_mcp_tool("replace_symbol_body", True, None)
    assert mcp_tool.fn(name_path="x", body="y", relative_path="z") == "ok"
