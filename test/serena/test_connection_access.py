# SPDX-License-Identifier: GPL-3.0-or-later

from serena.connection_access import ConnectionAccessControl, ConnectionPermission


def test_disabled_when_no_tokens():
    ac = ConnectionAccessControl({})
    assert ac.enabled is False
    assert ac.resolve_permission({}) == ConnectionPermission.EDIT
    assert ac.allows(ConnectionPermission.EDIT, can_edit=True)


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
    # missing / invalid token is treated as read-only when AC is enabled
    assert ac.resolve_permission({}) == ConnectionPermission.READ
    assert ac.resolve_permission({"Authorization": "Bearer unknown"}) == ConnectionPermission.READ


def test_allows_gates_edit_tools_only():
    ac = ConnectionAccessControl({"r1": "read"})
    assert ac.allows(ConnectionPermission.READ, can_edit=False)
    assert not ac.allows(ConnectionPermission.READ, can_edit=True)
    assert ac.allows(ConnectionPermission.EDIT, can_edit=True)
