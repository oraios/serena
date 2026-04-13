"""Typed settings for cloud-sync providers.

Values are loaded from the credentials env file by ``credentials.load_env_settings``.
Pydantic is used for validation + masked JSON output.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ProviderType(str, Enum):
    R2 = "r2"
    S3 = "s3"
    AZURE = "azure"


DEFAULT_ROOT_PREFIX = "serena-sync/"
MAX_OBJECT_SIZE_BYTES = 5 * 1024 * 1024
"""Hard per-object cap. Memory/config files are tiny; anything larger is almost
certainly out of scope for sync."""


class R2Settings(BaseModel):
    account_id: str = Field(..., min_length=1)
    access_key_id: str = Field(..., min_length=1)
    secret_access_key: str = Field(..., min_length=1)
    bucket: str = Field(..., min_length=1)
    endpoint_url: str | None = Field(
        default=None,
        description="Defaults to https://<account_id>.r2.cloudflarestorage.com when omitted.",
    )

    def resolved_endpoint(self) -> str:
        if self.endpoint_url:
            return self.endpoint_url.rstrip("/")
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


class S3Settings(BaseModel):
    access_key_id: str = Field(..., min_length=1)
    secret_access_key: str = Field(..., min_length=1)
    bucket: str = Field(..., min_length=1)
    region: str = Field(default="us-east-1")
    endpoint_url: str | None = Field(
        default=None,
        description=(
            "Optional override for S3-compatible backends (MinIO, Ceph RGW, "
            "SeaweedFS). Leave empty for AWS S3."
        ),
    )

    def resolved_endpoint(self) -> str | None:
        if not self.endpoint_url:
            return None
        return self.endpoint_url.rstrip("/")


class AzureSettings(BaseModel):
    account_name: str = Field(..., min_length=1)
    account_key: str = Field(..., min_length=1)
    container: str = Field(..., min_length=1)
    endpoint_suffix: str = Field(default="core.windows.net")


class CloudSyncSettings(BaseModel):
    provider: ProviderType
    root_prefix: str = Field(default=DEFAULT_ROOT_PREFIX)
    r2: R2Settings | None = None
    s3: S3Settings | None = None
    azure: AzureSettings | None = None

    @field_validator("root_prefix")
    @classmethod
    def _normalize_prefix(cls, v: str) -> str:
        # Always POSIX-style, trailing slash exactly once.
        v = v.strip().replace("\\", "/").lstrip("/")
        if not v:
            v = DEFAULT_ROOT_PREFIX
        if not v.endswith("/"):
            v += "/"
        return v

    def active_provider_settings(self) -> R2Settings | S3Settings | AzureSettings:
        if self.provider is ProviderType.R2:
            if self.r2 is None:
                raise ValueError("provider=r2 but [r2] settings missing")
            return self.r2
        if self.provider is ProviderType.S3:
            if self.s3 is None:
                raise ValueError("provider=s3 but [s3] settings missing")
            return self.s3
        if self.provider is ProviderType.AZURE:
            if self.azure is None:
                raise ValueError("provider=azure but [azure] settings missing")
            return self.azure
        raise AssertionError(f"unknown provider: {self.provider!r}")

    def masked(self) -> dict:
        """Masked dict for dashboard responses. Secret values become ``****<last4>``."""
        def mask(v: str | None) -> str:
            if not v:
                return ""
            if len(v) <= 4:
                return "****"
            return "****" + v[-4:]

        d: dict = {"provider": self.provider.value, "root_prefix": self.root_prefix}
        if self.r2:
            d["r2"] = {
                "account_id": self.r2.account_id,
                "access_key_id": mask(self.r2.access_key_id),
                "secret_access_key": mask(self.r2.secret_access_key),
                "bucket": self.r2.bucket,
                "endpoint_url": self.r2.endpoint_url,
            }
        if self.s3:
            d["s3"] = {
                "access_key_id": mask(self.s3.access_key_id),
                "secret_access_key": mask(self.s3.secret_access_key),
                "bucket": self.s3.bucket,
                "region": self.s3.region,
                "endpoint_url": self.s3.endpoint_url,
            }
        if self.azure:
            d["azure"] = {
                "account_name": self.azure.account_name,
                "account_key": mask(self.azure.account_key),
                "container": self.azure.container,
                "endpoint_suffix": self.azure.endpoint_suffix,
            }
        return d
