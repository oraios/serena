from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

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


# A file that cannot be decoded with the project encoding, forcing read_file's
# charset_normalizer fallback. The accented characters make the bytes invalid UTF-8,
# and the content is long enough for encoding detection to be reliable.
_CP1252_LINES = [
    "# -*- coding: cp1252 -*-",
    "# Author: José Fernández",
    "# Copyright (c) 2019 Müller & Söhne GmbH.",
    "",
    "import os",
    "",
    "",
    "class ConfiguracionBasica:",
    '    """Clase de configuración para el módulo de facturación."""',
    "",
    "    def __init__(self, nombre, valor=None):",
    "        self.nombre = nombre",
    "        self.valor = valor",
    "",
    "    def describir(self):",
    '        return f"{self.nombre}: {self.valor}"',
]


def test_read_file_fallback_normalizes_crlf(tmp_path: Path) -> None:
    """The charset_normalizer fallback should apply universal newlines, just like the primary path."""
    file_path = tmp_path / "config_cp1252.py"
    file_path.write_bytes(("\r\n".join(_CP1252_LINES) + "\r\n").encode("cp1252"))

    # guard against a vacuous test: the fixture must actually force the fallback
    with pytest.raises(UnicodeDecodeError):
        file_path.read_text(encoding="utf-8")

    content = FileUtils.read_file(str(file_path), "utf-8")

    assert "José Fernández" in content, "fallback should decode the file as cp1252"
    assert "\r" not in content
    assert content.splitlines() == _CP1252_LINES


def test_read_file_fallback_normalizes_lone_cr(tmp_path: Path) -> None:
    """Old-style lone CR separators should be normalized by the fallback as well."""
    file_path = tmp_path / "lone_cr_cp1252.py"
    file_path.write_bytes(("\r".join(_CP1252_LINES) + "\r").encode("cp1252"))

    content = FileUtils.read_file(str(file_path), "utf-8")

    assert "\r" not in content
    assert content.splitlines() == _CP1252_LINES


def test_read_file_primary_path_normalizes_crlf(tmp_path: Path) -> None:
    """Control: the primary open() path already normalizes; both paths must agree."""
    lines = ["import os", "", "def f():", "    return 1"]
    file_path = tmp_path / "config_utf8.py"
    file_path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))

    content = FileUtils.read_file(str(file_path), "utf-8")

    assert "\r" not in content
    assert content.splitlines() == lines
