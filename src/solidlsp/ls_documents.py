"""
Open document management (Phase 3 deep module).

This module owns:
- LSPFileBuffer (in-memory open file state + didOpen/didClose notifications)
- refcounted open_file / _open_file_context
- text mutations (insert / delete / apply) + didChange notifications
- content retrieval (retrieve_full_file_content)

The facade (SolidLanguageServer) retains narrow policy hooks and all public
`request_*` / `open_file` / mutation entry points as thin delegations. It
provides a minimal TextDocumentNotifier so that buffers and this manager do
not hold a broad reference to the facade just to send LSP notifications.

Backward-compatible re-export of LSPFileBuffer from solidlsp.ls is provided
so that call sites in serena (symbol.py, code_editor.py) and language servers
require no source changes.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import TextUtils
from solidlsp.lsp_protocol_handler.lsp_constants import LSPConstants

if TYPE_CHECKING:
    from solidlsp.ls import SolidLanguageServer

log = logging.getLogger(__name__)


class TextDocumentNotifier(Protocol):
    """Narrow interface for document synchronization notifications.

    Implementations forward to the low-level LSP interface (e.g. server.notify.*).
    This avoids giving LSPFileBuffer / OpenDocuments a broad reference to SolidLanguageServer.
    """

    # Accept Any to be structurally compatible with the concrete LspNotification
    # implementation, which is typed with stricter TypedDicts at the call site.
    def did_open_text_document(self, params: Any) -> None: ...
    def did_close_text_document(self, params: Any) -> None: ...
    def did_change_text_document(self, params: Any) -> None: ...


class LSPFileBuffer:
    """This class is used to store the contents of an open LSP file in memory.

    It is owned by OpenDocuments after Phase 3. It receives a narrow notifier
    for didOpen/didClose instead of a full language server back-reference.
    The optional `owner` is retained only for backward compatibility with code
    that reads `buffer.language_server` (e.g. some tests and serena adapters).
    """

    def __init__(
        self,
        abs_path: Path,
        uri: str,
        encoding: str,
        version: int,
        language_id: str,
        ref_count: int,
        *,
        notifier: TextDocumentNotifier | None = None,
        owner: "SolidLanguageServer | None" = None,
        open_in_ls: bool = True,
    ) -> None:
        self.abs_path = abs_path
        self.uri = uri
        # Retained for compatibility; notifications use the narrow notifier.
        self.language_server = owner
        self._read_file_modified_date: float | None = None
        self._contents: str | None = None
        self.version = version
        self.language_id = language_id
        self.ref_count = ref_count
        self.encoding = encoding
        self._content_hash: str | None = None
        self._is_open_in_ls = False
        self._notifier = notifier
        if open_in_ls:
            self._open_in_ls()

    def _open_in_ls(self) -> None:
        """Open the file in the language server if it is not already open."""
        if self._is_open_in_ls:
            return
        self._is_open_in_ls = True
        if self._notifier is not None:
            self._notifier.did_open_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {
                        LSPConstants.URI: self.uri,
                        LSPConstants.LANGUAGE_ID: self.language_id,
                        LSPConstants.VERSION: 0,
                        LSPConstants.TEXT: self.contents,
                    }
                }
            )

    def close(self) -> None:
        if self._is_open_in_ls:
            if self._notifier is not None:
                self._notifier.did_close_text_document({LSPConstants.TEXT_DOCUMENT: {LSPConstants.URI: self.uri}})
            self._is_open_in_ls = False

    def ensure_open_in_ls(self) -> None:
        """Ensure that the file is opened in the language server."""
        self._open_in_ls()

    @property
    def contents(self) -> str:
        file_modified_date = self.abs_path.stat().st_mtime

        # if contents are cached, check if they are stale (file modification since last read) and invalidate if so
        if self._contents is not None:
            assert self._read_file_modified_date is not None
            if file_modified_date > self._read_file_modified_date:
                self._contents = None

        if self._contents is None:
            self._read_file_modified_date = file_modified_date
            self._contents = FileUtils.read_file(str(self.abs_path), self.encoding)
            self._content_hash = None

        return self._contents

    @contents.setter
    def contents(self, new_contents: str) -> None:
        """Sets new contents for the file buffer (in-memory change only).
        Persistence of the change to disk must be handled separately.
        """
        self._contents = new_contents
        self._content_hash = None

    @property
    def content_hash(self) -> str:
        if self._content_hash is None:
            self._content_hash = __import__("hashlib").md5(self.contents.encode(self.encoding)).hexdigest()
        return self._content_hash

    def split_lines(self) -> list[str]:
        """Splits the contents of the file into lines."""
        return self.contents.split("\n")


# Local import to avoid circulars at module load for the contents property above.
from solidlsp.ls_utils import FileUtils


class OpenDocuments:
    """Owns open file buffers, refcounted contexts, mutations, and document sync notifications.

    It is a collaborator of SolidLanguageServer. The facade provides narrow
    callables for workspace/language-id decisions and a TextDocumentNotifier
    for LSP notifications. This keeps the documents concern deep and the
    facade surface unchanged.
    """

    def __init__(
        self,
        *,
        root_path: str,
        encoding: str,
        resolve_uri: Callable[[str], str],
        get_language_id: Callable[[str], str],
        path_contains_dots: Callable[[str], bool],
        is_server_started: Callable[[], bool],
        notifier: TextDocumentNotifier,
        owner: "SolidLanguageServer | None" = None,
    ) -> None:
        self._root_path = root_path
        self._encoding = encoding
        self._resolve_uri = resolve_uri
        self._get_language_id = get_language_id
        self._path_contains_dots = path_contains_dots
        self._is_server_started = is_server_started
        self._notifier = notifier
        self._owner = owner
        self._buffers: dict[str, LSPFileBuffer] = {}

    @property
    def buffers(self) -> dict[str, LSPFileBuffer]:
        """The live map of URI -> LSPFileBuffer (for backward-compat attribute access on the facade)."""
        return self._buffers

    def _check_started(self) -> None:
        if not self._is_server_started():
            log.error("open file called before Language Server started")
            raise SolidLSPException("Language Server not started")

    @contextmanager
    def open_file(self, relative_file_path: str, open_in_ls: bool = True) -> Iterator[LSPFileBuffer]:
        """Open a file in the Language Server. Required before making requests.

        Mirrors the original SolidLanguageServer.open_file behavior and protocol.
        """
        self._check_started()

        absolute_file_path = Path(self._root_path, relative_file_path)
        if self._path_contains_dots(relative_file_path):
            absolute_file_path = absolute_file_path.resolve()
        uri = self._resolve_uri(relative_file_path)

        if uri in self._buffers:
            fb = self._buffers[uri]
            assert fb.uri == uri
            assert fb.ref_count >= 1

            fb.ref_count += 1
            if open_in_ls:
                fb.ensure_open_in_ls()
        else:
            version = 0
            language_id = self._get_language_id(relative_file_path)
            fb = LSPFileBuffer(
                abs_path=absolute_file_path,
                uri=uri,
                encoding=self._encoding,
                version=version,
                language_id=language_id,
                ref_count=1,
                notifier=self._notifier,
                owner=self._owner,
                open_in_ls=open_in_ls,
            )
            self._buffers[uri] = fb

        try:
            yield fb
        finally:
            fb.ref_count -= 1
            if fb.ref_count == 0:
                fb.close()
                del self._buffers[uri]

    @contextmanager
    def _open_file_context(
        self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None, open_in_ls: bool = True
    ) -> Iterator[LSPFileBuffer]:
        """Internal context manager to open a file, optionally reusing an existing file buffer."""
        self._check_started()
        if file_buffer is not None:
            expected_uri = self._resolve_uri(relative_file_path)
            assert file_buffer.uri == expected_uri, f"Inconsistency between provided {file_buffer.uri=} and {expected_uri=}"
            if open_in_ls:
                file_buffer.ensure_open_in_ls()
            yield file_buffer
        else:
            with self.open_file(relative_file_path, open_in_ls=open_in_ls) as fb:
                yield fb

    def insert_text_at_position(self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str) -> dict[str, int]:
        """Insert text at the given line and column. Returns the updated cursor position."""
        self._check_started()
        uri = self._resolve_uri(relative_file_path)

        # Ensure the file is open (mirrors original assertion behavior)
        assert uri in self._buffers

        file_buffer = self._buffers[uri]
        file_buffer.version += 1

        new_contents, new_l, new_c = TextUtils.insert_text_at_position(file_buffer.contents, line, column, text_to_be_inserted)
        file_buffer.contents = new_contents

        self._notifier.did_change_text_document(
            {
                LSPConstants.TEXT_DOCUMENT: {
                    LSPConstants.VERSION: file_buffer.version,
                    LSPConstants.URI: file_buffer.uri,
                },
                LSPConstants.CONTENT_CHANGES: [
                    {
                        LSPConstants.RANGE: {
                            "start": {"line": line, "character": column},
                            "end": {"line": line, "character": column},
                        },
                        "text": text_to_be_inserted,
                    }
                ],
            }
        )
        return {"line": new_l, "character": new_c}

    def delete_text_between_positions(
        self,
        relative_file_path: str,
        start: dict[str, int] | Any,
        end: dict[str, int] | Any,
    ) -> str:
        """Delete text between the given start and end positions. Returns the deleted text."""
        self._check_started()
        uri = self._resolve_uri(relative_file_path)

        assert uri in self._buffers

        file_buffer = self._buffers[uri]
        file_buffer.version += 1
        new_contents, deleted_text = TextUtils.delete_text_between_positions(
            file_buffer.contents,
            start_line=start["line"],
            start_col=start["character"],
            end_line=end["line"],
            end_col=end["character"],
        )
        file_buffer.contents = new_contents

        self._notifier.did_change_text_document(
            {
                LSPConstants.TEXT_DOCUMENT: {
                    LSPConstants.VERSION: file_buffer.version,
                    LSPConstants.URI: file_buffer.uri,
                },
                LSPConstants.CONTENT_CHANGES: [{LSPConstants.RANGE: {"start": start, "end": end}, "text": ""}],
            }
        )
        return deleted_text

    def apply_text_edits_to_file(self, relative_path: str, edits: list[Any]) -> None:
        """Apply a list of text edits to a file (sorted reverse, in-memory + notifications)."""
        with self.open_file(relative_path):
            # Sort edits by position (latest first) to avoid position shifts
            # Accept list[Any] (e.g. list[ls_types.TextEdit] from facade) and read keys.
            sorted_edits = sorted(edits, key=lambda e: (e["range"]["start"]["line"], e["range"]["start"]["character"]), reverse=True)
            for edit in sorted_edits:
                start_pos = {"line": edit["range"]["start"]["line"], "character": edit["range"]["start"]["character"]}
                end_pos = {"line": edit["range"]["end"]["line"], "character": edit["range"]["end"]["character"]}
                self.delete_text_between_positions(relative_path, start_pos, end_pos)
                self.insert_text_at_position(relative_path, start_pos["line"], start_pos["character"], edit["newText"])

    def retrieve_full_file_content(self, file_path: str) -> str:
        """Retrieve the full content of the given file (relative or absolute)."""
        if os.path.isabs(file_path):
            file_path = os.path.relpath(file_path, self._root_path)
        with self.open_file(file_path) as file_data:
            return file_data.contents

    def register_permanent_buffer(self, relative_file_path: str) -> LSPFileBuffer:
        """Register a buffer that is kept open for the language server lifetime.

        Used by additional workspace activation paths. The buffer is not
        auto-closed when refcount would reach zero from this path.
        """
        self._check_started()
        absolute_file_path = Path(self._root_path, relative_file_path)
        if self._path_contains_dots(relative_file_path):
            absolute_file_path = absolute_file_path.resolve()
        uri = self._resolve_uri(relative_file_path)

        if uri in self._buffers:
            fb = self._buffers[uri]
            fb.ref_count += 1
            fb.ensure_open_in_ls()
            return fb

        language_id = self._get_language_id(relative_file_path)
        fb = LSPFileBuffer(
            abs_path=absolute_file_path,
            uri=uri,
            encoding=self._encoding,
            version=0,
            language_id=language_id,
            ref_count=1,
            notifier=self._notifier,
            owner=self._owner,
            open_in_ls=True,
        )
        self._buffers[uri] = fb
        return fb
