from pathlib import Path

from serena.cloud_sync.hash_util import (
    byte_compare_file_to_stream,
    sha256_bytes,
    sha256_file,
    sha256_stream,
)


def test_sha256_bytes_matches_file(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    body = b"hello serena " * 1024
    p.write_bytes(body)
    assert sha256_bytes(body) == sha256_file(p) == sha256_stream([body])


def test_byte_compare_identical(tmp_path: Path) -> None:
    p = tmp_path / "x.bin"
    body = b"a" * (1024 * 1024 + 7)
    p.write_bytes(body)
    # one-chunk stream
    assert byte_compare_file_to_stream(p, [body])
    # multi-chunk stream
    mid = len(body) // 2
    assert byte_compare_file_to_stream(p, [body[:mid], body[mid:]])


def test_byte_compare_divergent(tmp_path: Path) -> None:
    p = tmp_path / "x.bin"
    p.write_bytes(b"abcdef")
    assert not byte_compare_file_to_stream(p, [b"abcdff"])
    assert not byte_compare_file_to_stream(p, [b"abc"])
    assert not byte_compare_file_to_stream(p, [b"abcdefg"])
