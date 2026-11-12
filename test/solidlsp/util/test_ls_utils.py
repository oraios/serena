from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import FileUtils, PlatformId, PlatformUtils, TextUtils


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


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        pytest.param("FreeBSD", "amd64", PlatformId.FREEBSD_x64, id="freebsd-amd64"),
        pytest.param("FreeBSD", "arm64", PlatformId.FREEBSD_arm64, id="freebsd-arm64"),
    ],
)
def test_get_platform_id_freebsd(system: str, machine: str, expected: PlatformId) -> None:
    """FreeBSD should resolve to a freebsd platform id."""
    with (
        patch("solidlsp.ls_utils.platform.system", return_value=system),
        patch("solidlsp.ls_utils.platform.machine", return_value=machine),
        patch("solidlsp.ls_utils.platform.architecture", return_value=("64bit",)),
    ):
        assert PlatformUtils.get_platform_id() is expected


def test_get_platform_id_freebsd_i386_raises() -> None:
    """32-bit FreeBSD was deprecated with the release of FreeBSD 15.0 and must fail with the standard error."""
    with (
        patch("solidlsp.ls_utils.platform.system", return_value="FreeBSD"),
        patch("solidlsp.ls_utils.platform.machine", return_value="i386"),
        patch("solidlsp.ls_utils.platform.architecture", return_value=("32bit",)),
    ):
        with pytest.raises(SolidLSPException, match="Unknown platform"):
            PlatformUtils.get_platform_id()


def test_get_platform_id_unknown_platform_still_raises() -> None:
    """Platforms without an explicit mapping must keep failing explicitly."""
    with (
        patch("solidlsp.ls_utils.platform.system", return_value="SunOS"),
        patch("solidlsp.ls_utils.platform.machine", return_value="i86pc"),
        patch("solidlsp.ls_utils.platform.architecture", return_value=("64bit",)),
    ):
        with pytest.raises(SolidLSPException):
            PlatformUtils.get_platform_id()


# U+10400 (the LSP spec's own example character for this, see Position's docstring) is one
# Python code point but, like every character outside the Basic Multilingual Plane, 2 UTF-16
# code units (a surrogate pair). LSP `character` offsets are defined in UTF-16 code units;
# TextUtils otherwise indexes by code point.
_ASTRAL_LINE = "\U00010400AB"


@pytest.mark.parametrize(
    ("utf16_offset", "expected_codepoint_offset"),
    [
        (0, 0),  # before the astral character: no conversion needed
        (2, 1),  # right after it (it occupies units 0-1): 1 code point consumed
        (3, 2),  # after it and "A"
        (4, 3),  # end of line
    ],
)
def test_utf16_offset_to_codepoint_offset_astral_character(utf16_offset: int, expected_codepoint_offset: int) -> None:
    assert TextUtils.utf16_offset_to_codepoint_offset(_ASTRAL_LINE, utf16_offset) == expected_codepoint_offset


@pytest.mark.parametrize("codepoint_offset", [0, 1, 2, 3])
def test_utf16_codepoint_round_trip_astral_character(codepoint_offset: int) -> None:
    """Codepoint -> utf16 -> codepoint must be the identity for any offset that lands on a real character boundary."""
    utf16_offset = TextUtils.codepoint_offset_to_utf16_offset(_ASTRAL_LINE, codepoint_offset)
    assert TextUtils.utf16_offset_to_codepoint_offset(_ASTRAL_LINE, utf16_offset) == codepoint_offset


def test_utf16_offset_to_codepoint_offset_no_astral_characters_is_identity() -> None:
    """Without any character outside the BMP, UTF-16 and code-point offsets coincide."""
    line = "plain ascii line"
    for offset in range(len(line) + 1):
        assert TextUtils.utf16_offset_to_codepoint_offset(line, offset) == offset
        assert TextUtils.codepoint_offset_to_utf16_offset(line, offset) == offset


def test_utf16_offset_to_codepoint_offset_empty_line() -> None:
    assert TextUtils.utf16_offset_to_codepoint_offset("", 0) == 0
