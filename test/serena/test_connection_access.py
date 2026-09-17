# SPDX-License-Identifier: GPL-3.0-or-later

from types import SimpleNamespace

from serena.connection_access import ConnectionAccessControl, ConnectionPermission


def test_disabled_when_no_tokens():
    ac = ConnectionAccessControl({})
    assert ac.enabled is False
    # access control off: everything allowed, including without headers
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
    # missing / invalid token: no permission at all (must not grant access)
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
