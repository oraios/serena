# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional per-connection tool permissions for the Serena MCP server (oraios/serena#1971).

When ``connection_access_tokens`` is configured, HTTP transports require a Bearer token
verified by the MCP SDK's ``TokenVerifier`` protocol (the token checker the issue asks the
host application to supply — not a Serena login system). A token maps to ``read`` (query
tools only) or ``edit`` (all tools) and is carried as an OAuth scope on the verified
``AccessToken``. Stdio is unaffected: a single local client already controls the process.

Missing or invalid tokens are rejected by the SDK auth middleware before any tool runs.
Editing tools additionally require the ``edit`` scope on every call. The MCP tool list
itself is process-global (one ``FastMCP`` instance serves all connections), so it cannot
safely differ per connection without per-session tool managers; read-only clients still
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

    @property
    def scope(self) -> str:
        return self.value


class SerenaTokenVerifier:
    """
    MCP SDK ``TokenVerifier`` over Serena's configured bearer tokens (oraios/serena#1971).

    Implements only the verifier protocol; token issuance/revocation stays with the
    application that writes ``connection_access_tokens`` (revoke by removing the entry and
    restarting, or by reloading config in a host that supports it).
    """

    def __init__(self, tokens: dict[str, ConnectionPermission]):
        self._tokens = dict(tokens)

    async def verify_token(self, token: str):
        """
        :return: an ``AccessToken`` carrying the permission as a scope, or None if unknown
        """
        from mcp.server.auth.provider import AccessToken

        permission = self._tokens.get(token)
        if permission is None:
            return None
        return AccessToken(
            token=token,
            client_id="serena-connection",
            scopes=[permission.scope],
            subject=permission.value,
        )


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

    @property
    def token_verifier(self) -> SerenaTokenVerifier:
        """Verifier for the MCP SDK auth middleware."""
        return SerenaTokenVerifier(self._tokens)

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

    @staticmethod
    def permission_from_access_token_scopes() -> ConnectionPermission | None:
        """
        Read the permission from the MCP SDK's per-request auth context (scopes set by
        :class:`SerenaTokenVerifier`).
        """
        try:
            from mcp.server.auth.middleware.auth_context import get_access_token

            access_token = get_access_token()
        except Exception:
            return None
        if access_token is None:
            return None
        scopes = list(getattr(access_token, "scopes", ()) or ())
        if ConnectionPermission.EDIT.scope in scopes:
            return ConnectionPermission.EDIT
        if ConnectionPermission.READ.scope in scopes:
            return ConnectionPermission.READ
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

        Prefers the SDK auth context (TokenVerifier scopes). Falls back to parsing the
        request ``Authorization`` header when middleware did not run (e.g. a transport
        that did not go through ``RequireAuthMiddleware``).
        """
        if not self.enabled:
            return ConnectionPermission.EDIT
        from_scopes = self.permission_from_access_token_scopes()
        if from_scopes is not None:
            return from_scopes
        return self.resolve_permission(self.headers_from_mcp_context(mcp_ctx))
