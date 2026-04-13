"""Exception hierarchy for the cloud-sync subsystem.

All sync-layer code raises one of these. Providers translate SDK errors into
the appropriate ``ProviderError`` subclass so that business logic never has to
catch ``botocore.exceptions.ClientError`` or ``azure.core.exceptions.*``.
"""
from __future__ import annotations


class CloudSyncError(Exception):
    """Base class for every cloud-sync error."""


class ProviderError(CloudSyncError):
    """Generic provider failure (network, auth, server 5xx). Retryable-or-not
    is indicated by ``retryable`` attribute."""

    def __init__(self, message: str, *, retryable: bool = False,
                 provider_code: str | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.provider_code = provider_code


class ProviderConflictError(ProviderError):
    """Conditional put (``put_object_if_absent``) returned 412 Precondition Failed
    — the object already exists with different content. The sync layer maps this
    to the CONFLICT diff class and preserves both sides."""

    def __init__(self, message: str, *, provider_code: str | None = None) -> None:
        super().__init__(message, retryable=False, provider_code=provider_code)


class CredentialError(CloudSyncError):
    """Credentials missing, malformed, or unsafe (file perms wider than 0600)."""


class ScopeError(CloudSyncError):
    """Tried to sync a path excluded by the hard scope rules (credential files,
    oversize binaries, symlinks, etc)."""
