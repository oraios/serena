# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional per-connection tool permissions for the Serena MCP server (oraios/serena#1971).

When ``connection_access_tokens`` is configured, HTTP transports require a Bearer token.
A token maps to ``read`` (query tools only) or ``edit`` (all tools). Stdio is unaffected:
a single local client already controls the process.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class ConnectionPermission(str, Enum):
    READ = "read"
    EDIT = "edit"


# Default for stdio / unauthenticated paths: full tool access (previous behaviour).
_CURRENT_PERMISSION: ContextVar[ConnectionPermission] = ContextVar("serena_connection_permission", default=ConnectionPermission.EDIT)


def get_current_permission() -> ConnectionPermission:
    return _CURRENT_PERMISSION.get()


def set_current_permission(permission: ConnectionPermission):
    return _CURRENT_PERMISSION.set(permission)


def reset_current_permission(token) -> None:
    _CURRENT_PERMISSION.reset(token)


class ConnectionAccessControl:
    """
    Maps bearer tokens to connection permissions and resolves the permission of a request.
    """

    def __init__(self, tokens: dict[str, str] | None = None):
        """
        :param tokens: mapping of access token to permission string (``read`` or ``edit``)
        """
        resolved: dict[str, ConnectionPermission] = {}
        for token, permission in (tokens or {}).items():
            if not token or not isinstance(token, str):
                log.warning("Ignoring empty/non-string entry in connection_access_tokens")
                continue
            try:
                resolved[token] = ConnectionPermission(str(permission).strip().lower())
            except ValueError:
                log.warning("Ignoring connection_access_tokens entry with unknown permission %r (expected read|edit)", permission)
        self._tokens = resolved
        self.enabled = bool(self._tokens)

    def permission_for_token(self, token: str | None) -> ConnectionPermission | None:
        """
        :return: the permission for `token`, or None if the token is missing or unknown
        """
        if not token:
            return None
        return self._tokens.get(token)

    @staticmethod
    def extract_bearer_token(headers: Any) -> str | None:
        """
        Extract a bearer token from an HTTP headers mapping (case-insensitive keys).
        """
        if not headers:
            return None
        try:
            items = headers.items() if hasattr(headers, "items") else headers
            for key, value in items:
                if str(key).lower() == "authorization":
                    value = str(value)
                    if value.lower().startswith("bearer "):
                        return value[7:].strip()
                    return None
        except Exception:
            return None
        return None

    def resolve_permission(self, headers: Any) -> ConnectionPermission:
        """
        Resolve the permission for a request carrying `headers`.

        Unknown or missing tokens get no elevated rights: a missing token is treated as
        read-only when access control is enabled, and an unknown token is rejected as
        read-only as well (edit tools will refuse to run). Callers that must hard-fail
        authentication should check :meth:`permission_for_token` first.
        """
        if not self.enabled:
            return ConnectionPermission.EDIT
        token = self.extract_bearer_token(headers)
        permission = self.permission_for_token(token)
        if permission is None:
            log.debug("No valid connection access token; treating connection as read-only")
            return ConnectionPermission.READ
        return permission

    def allows(self, permission: ConnectionPermission, *, can_edit: bool) -> bool:
        """
        Whether a connection with `permission` may invoke a tool with `can_edit` capability.
        """
        if not can_edit:
            return True
        return permission == ConnectionPermission.EDIT
