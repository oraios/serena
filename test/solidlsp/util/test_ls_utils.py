from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from solidlsp.ls_utils import FileUtils


class _FakeResponse:
    def __init__(self, payload: bytes, final_url: str) -> None:
        self.status_code = 200
        self.headers = {"content-encoding": "gzip"}
        self.url = final_url
        self._payload = payload

    def iter_content(self, chunk_size: int = 1):
        for offset in range(0, len(self._payload), chunk_size):
            yield self._payload[offset : offset + chunk_size]

    def close(self) -> None:
        return None


def test_download_file_verified_writes_decoded_response_body(tmp_path: Path) -> None:
    """Gzip-encoded transfer bodies should be written as decoded payload bytes."""
    payload = b"PK\x03\x04zip-content"
    target_path = tmp_path / "downloaded.vsix"
    final_url = "https://marketplace.visualstudio.com/example.vsix"

    with patch(
        "solidlsp.ls_utils.requests.get",
        return_value=_FakeResponse(payload, final_url),
    ):
        FileUtils.download_file_verified(
            "https://marketplace.visualstudio.com/example.vsix",
            str(target_path),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            allowed_hosts=("marketplace.visualstudio.com",),
        )

    assert target_path.read_bytes() == payload
