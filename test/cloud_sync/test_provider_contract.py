"""Provider-contract assertions that don't require a real backend.

Guards two lazy-loading / structural invariants:
 1. Importing ``serena.cloud_sync`` does NOT import boto3 or azure SDKs.
 2. Azure provider module uploads with ContentSettings inline on the upload
    call (not via a follow-up ``set_http_headers``), matching the plan.
"""
from __future__ import annotations

import importlib
import sys


def test_importing_cloud_sync_does_not_load_sdks() -> None:
    # Fresh import
    for m in list(sys.modules):
        if m.startswith(("boto3", "botocore", "azure")):
            sys.modules.pop(m, None)
    for m in list(sys.modules):
        if m.startswith("serena.cloud_sync"):
            sys.modules.pop(m, None)
    importlib.import_module("serena.cloud_sync")
    # boto3 + azure are NOT in sys.modules until a provider is built
    # boto3 may be pulled by factory.build_provider, but plain import should not.
    loaded = [m for m in sys.modules if m.startswith(("boto3", "botocore", "azure"))]
    assert not loaded, f"cloud_sync import eagerly loaded SDKs: {loaded}"


def test_azure_provider_uses_content_settings_inline() -> None:
    """Lexical check: Azure provider calls upload_blob with content_settings=
    in the same call (not a follow-up set_http_headers). This keeps metadata
    and body atomic from the backend's perspective."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "src/serena/cloud_sync/providers/azure.py"
    body = src.read_text()
    assert "upload_blob" in body
    assert "content_settings=ContentSettings" in body
    assert "set_http_headers" not in body, (
        "Azure adapter should set content-type in upload_blob(content_settings=...) "
        "not via a follow-up set_http_headers call"
    )


def test_content_type_propagates_to_provider() -> None:
    """Ensure CloudStorageProvider's content_type param is forwarded by put_object."""
    from .fakes import FakeCloudProvider
    p = FakeCloudProvider()
    p.put_object("k", b"data", "sha", content_type="text/markdown")
    assert p.last_content_type["k"] == "text/markdown"
    p.put_object_if_absent("k2", b"data2", "sha2", content_type="application/yaml")
    assert p.last_content_type["k2"] == "application/yaml"
