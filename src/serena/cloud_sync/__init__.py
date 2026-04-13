"""Serena Cloud Sync — cross-machine sync of memories and configuration.

EXPERIMENTAL in MVP. Additive union semantics: never overwrites divergent content
silently. See docs/cloud-sync-feature-plan.md for the full contract.

The public surface intentionally keeps SDK deps (boto3, azure-storage-blob) out
of the business-logic layer. Concrete provider adapters live under
``serena.cloud_sync.providers``; the abstract seam is ``provider.CloudStorageProvider``.
"""
from serena.cloud_sync.exceptions import (
    CloudSyncError,
    CredentialError,
    ProviderConflictError,
    ProviderError,
    ScopeError,
)
from serena.cloud_sync.provider import CloudStorageProvider, RemoteObjectMeta
from serena.cloud_sync.settings import CloudSyncSettings, ProviderType
from serena.cloud_sync.sync import CloudSyncService, SyncAction, SyncPlan, SyncReport

__all__ = [
    "CloudStorageProvider",
    "CloudSyncError",
    "CloudSyncService",
    "CloudSyncSettings",
    "CredentialError",
    "ProviderConflictError",
    "ProviderError",
    "ProviderType",
    "RemoteObjectMeta",
    "ScopeError",
    "SyncAction",
    "SyncPlan",
    "SyncReport",
]
