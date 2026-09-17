# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional per-connection tool permissions for the Serena MCP server (oraios/serena#1971).

When ``connection_access_tokens`` is configured, HTTP transports require a Bearer token.
A token maps to ``read`` (query tools only) or ``edit`` (all tools). Stdio is unaffected:
a single local client already controls the process.

Permissions are enforced **per tool call** from the request that carries the call. The
MCP tool list itself is process-global (one ``FastMCP`` instance serves all connections),
so it cannot safely differ per connection without SDK-level auth; read-only clients still
see editing tools in ``tools/list`` but every editing call is rejected server-side.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class ConnectionPermission(str, Enum):
    READ = "read"
    EDIT = "edit"


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

    @staticmethod
    def headers_from_mcp_context(mcp_ctx: Any) -> Any:
        """
        Best-effort extraction of HTTP headers from a FastMCP ``Context``.

        Returns None when the transport is not HTTP or the SDK does not expose a request
        (e.g. stdio, or an SDK version without ``request_context.request``).
        """
        if mcp_ctx is None:
            return None
        try:
            request_ctx = getattr(mcp_ctx, "request_context", None)
            if request_ctx is None:
                return None
            request = getattr(request_ctx, "request", None)
            if request is None:
                return None
            return getattr(request, "headers", None)
        except Exception:
            return None

    def resolve_permission(self, headers: Any) -> ConnectionPermission | None:
        """
        Resolve the permission for a request carrying `headers`.

        :return: the permission for a valid token, or None when the token is missing or
            unknown. Callers must treat None as *no access* (oraios/serena#1971: missing,
            invalid or revoked tokens must not grant access).
        """
        if not self.enabled:
            return ConnectionPermission.EDIT
        token = self.extract_bearer_token(headers)
        return self.permission_for_token(token)

    def allows(self, permission: ConnectionPermission | None, *, can_edit: bool) -> bool:
        """
        Whether a connection with `permission` may invoke a tool with `can_edit` capability.

        When access control is disabled, everything is allowed. When enabled, a None
        permission (no/invalid token) allows nothing (oraios/serena#1971).
        """
        if not self.enabled:
            return True
        if permission is None:
            return False
        if not can_edit:
            return True
        return permission == ConnectionPermission.EDIT

    def permission_for_mcp_context(self, mcp_ctx: Any) -> ConnectionPermission | None:
        """
        Resolve permission from an MCP tool-call context.
        """
        return self.resolve_permission(self.headers_from_mcp_context(mcp_ctx))
