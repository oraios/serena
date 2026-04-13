"""Factory that instantiates the right concrete provider from settings.

This is the only module other than ``providers/*`` that's allowed to pull in
SDK-dependent concrete classes.
"""
from __future__ import annotations

from serena.cloud_sync.provider import CloudStorageProvider
from serena.cloud_sync.settings import CloudSyncSettings, ProviderType


def build_provider(settings: CloudSyncSettings) -> CloudStorageProvider:
    p = settings.provider
    if p is ProviderType.R2:
        from serena.cloud_sync.providers.r2 import R2Provider
        assert settings.r2 is not None
        return R2Provider(settings.r2)
    if p is ProviderType.S3:
        from serena.cloud_sync.providers.s3 import S3Provider
        assert settings.s3 is not None
        return S3Provider(settings.s3)
    if p is ProviderType.AZURE:
        from serena.cloud_sync.providers.azure import AzureBlobProvider
        assert settings.azure is not None
        return AzureBlobProvider(settings.azure)
    raise ValueError(f"unknown provider: {p!r}")
