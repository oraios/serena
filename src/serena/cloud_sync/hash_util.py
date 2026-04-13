"""SHA-256 helpers used as the byte-equivalent compare primitive."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO, Iterable

CHUNK_SIZE = 1024 * 1024  # 1 MiB


def sha256_file(path: str | Path) -> str:
    """Compute hex sha256 of a file via chunked reads."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_stream(chunks: Iterable[bytes]) -> str:
    h = hashlib.sha256()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


def byte_compare_file_to_stream(path: str | Path, chunks: Iterable[bytes]) -> bool:
    """Paranoid byte-by-byte compare between a local file and a remote byte stream.

    Returns True if the local file is byte-identical to the concatenation of
    ``chunks``. Short-circuits on the first divergence for efficiency.
    """
    with open(path, "rb") as fh:
        remaining = b""
        for rchunk in chunks:
            while rchunk:
                if not remaining:
                    remaining = fh.read(len(rchunk))
                    if not remaining:
                        return False
                n = min(len(remaining), len(rchunk))
                if remaining[:n] != rchunk[:n]:
                    return False
                remaining = remaining[n:]
                rchunk = rchunk[n:]
        if fh.read(1):
            return False
    return True


def _stream_file(fh: BinaryIO) -> Iterable[bytes]:
    while True:
        chunk = fh.read(CHUNK_SIZE)
        if not chunk:
            return
        yield chunk
