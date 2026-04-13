"""Azurite-backed round-trip for the Azure provider.

Skipped unless ``AZURITE_CONNECTION_STRING`` is set. The default Azurite
development connection string is:
    DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=...
but this test only consumes account/key/endpoint-suffix separately.
"""
from __future__ import annotations

import os

import pytest

from serena.cloud_sync.exceptions import ProviderConflictError
from serena.cloud_sync.settings import AzureSettings

pytestmark = pytest.mark.skipif(
    not os.environ.get("AZURITE_ACCOUNT"),
    reason="set AZURITE_ACCOUNT/AZURITE_KEY/AZURITE_ENDPOINT_SUFFIX to run",
)


@pytest.fixture
def azure_provider():
    try:
        from serena.cloud_sync.providers.azure import AzureBlobProvider
    except ImportError:  # pragma: no cover
        pytest.skip("azure-storage-blob not installed")
    settings = AzureSettings(
        account_name=os.environ["AZURITE_ACCOUNT"],
        account_key=os.environ["AZURITE_KEY"],
        container=os.environ.get("AZURITE_CONTAINER", "serena-sync-test"),
        endpoint_suffix=os.environ.get("AZURITE_ENDPOINT_SUFFIX", "core.windows.net"),
    )
    provider = AzureBlobProvider(settings)
    # Ensure container exists
    try:
        provider._service.create_container(settings.container)
    except Exception:
        pass
    yield provider
    provider.close()


def test_roundtrip(azure_provider) -> None:
    key = "serena-test/azure-rt.md"
    body = b"hello azure" * 10
    import hashlib
    sha = hashlib.sha256(body).hexdigest()
    assert azure_provider.put_object_if_absent(key, body, sha) is True
    assert azure_provider.put_object_if_absent(key, body, sha) is False
    assert azure_provider.get_object(key) == body
    meta = azure_provider.head_object(key)
    assert meta is not None
    assert meta.sha256 == sha
    azure_provider.delete_object(key)


def test_conflict(azure_provider) -> None:
    key = "serena-test/azure-conflict.md"
    import hashlib
    azure_provider.put_object_if_absent(key, b"A", hashlib.sha256(b"A").hexdigest())
    with pytest.raises(ProviderConflictError):
        azure_provider.put_object_if_absent(key, b"B", hashlib.sha256(b"B").hexdigest())
    azure_provider.delete_object(key)
