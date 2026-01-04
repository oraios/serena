import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Reversible
from contextlib import contextmanager
from typing import TYPE_CHECKING, Generic, Optional, TypeVar, cast

from serena.symbol import JetBrainsSymbol, LanguageServerSymbol, LanguageServerSymbolRetriever, PositionInFile, Symbol
from solidlsp import SolidLanguageServer, ls_types
from solidlsp.ls import LSPFileBuffer
from solidlsp.ls_utils import PathUtils, TextUtils

from .constants import DEFAULT_SOURCE_FILE_ENCODING
from .project import Project
from .tools.jetbrains_plugin_client import JetBrainsPluginClient

if TYPE_CHECKING:
    from .agent import SerenaAgent


log = logging.getLogger(__name__)
TSymbol = TypeVar("TSymbol", bound=Symbol)


class CodeEditor(Generic[TSymbol], ABC):
    def __init__(self, project_root: str, agent: Optional["SerenaAgent"] = None) -> None:
        self.project_root = project_root
        self.agent = agent

        # set encoding based on active project, if available
        encoding = DEFAULT_SOURCE_FILE_ENCODING
        if agent is not None:
            project = agent.get_active_project()
            if project is not None:
                encoding = project.project_config.encoding
        self.encoding = encoding

    class EditedFile(ABC):
        def __init__(self, relative_path: str) -> None:
            self.relative_path = relative_path

        @abstractmethod
        def get_contents(self) -> str:
            """
            :return: the contents of the file.
            """

        @abstractmethod
        def set_contents(self, contents: str) -> None:
            """
            Fully resets the contents of the file.

            :param contents: the new contents
            """

        @abstractmethod
        def delete_text_between_positions(self, start_pos: PositionInFile, end_pos: PositionInFile) -> None:
            pass

        @abstractmethod
        def insert_text_at_position(self, pos: PositionInFile, text: str) -> None:
            pass

    @contextmanager
    def _open_file_context(self, relative_path: str) -> Iterator["CodeEditor.EditedFile"]:
        """
        Context manager for opening a file
        """
        raise NotImplementedError("This method must be overridden for each subclass")

    @contextmanager
    def edited_file_context(self, relative_path: str) -> Iterator["CodeEditor.EditedFile"]:
        """
        Context manager for editing a file.
        """
        with self._open_file_context(relative_path) as edited_file:
            yield edited_file
            # save the file
            self._save_edited_file(edited_file)

    def _save_edited_file(self, edited_file: "CodeEditor.EditedFile") -> None:
        abs_path = os.path.join(self.project_root, edited_file.relative_path)
        with open(abs_path, "w", encoding=self.encoding) as f:
            f.write(edited_file.get_contents())

    @abstractmethod
    def _find_unique_symbol(self, name_path: str, relative_file_path: str) -> TSymbol:
        """
        Finds the unique symbol with the given name in the given file.
        If no such symbol exists, raises a ValueError.

        :param name_path: the name path
        :param relative_file_path: the relative path of the file in which to search for the symbol.
        :return: the unique symbol
        """

    def replace_body(self, name_path: str, relative_file_path: str, body: str) -> None:
        """
        Replaces the body of the symbol with the given name_path in the given file.

        :param name_path: the name path of the symbol to replace.
        :param relative_file_path: the relative path of the file in which the symbol is defined.
        :param body: the new body
        """
        symbol = self._find_unique_symbol(name_path, relative_file_path)
        start_pos = symbol.get_body_start_position_or_raise()
        end_pos = symbol.get_body_end_position_or_raise()

        with self.edited_file_context(relative_file_path) as edited_file:
            # make sure the replacement adds no additional newlines (before or after) - all newlines
            # and whitespace before/after should remain the same, so we strip it entirely
            body = body.strip()

            edited_file.delete_text_between_positions(start_pos, end_pos)
            edited_file.insert_text_at_position(start_pos, body)

    @staticmethod
    def _count_leading_newlines(text: Iterable) -> int:
        cnt = 0
        for c in text:
            if c == "\n":
                cnt += 1
            elif c == "\r":
                continue
            else:
                break
        return cnt

    @classmethod
    def _count_trailing_newlines(cls, text: Reversible) -> int:
        return cls._count_leading_newlines(reversed(text))

    def insert_after_symbol(self, name_path: str, relative_file_path: str, body: str) -> None:
        """
        Inserts content after the symbol with the given name in the given file.
        """
        symbol = self._find_unique_symbol(name_path, relative_file_path)

        # make sure body always ends with at least one newline
        if not body.endswith("\n"):
            body += "\n"

        pos = symbol.get_body_end_position_or_raise()

        # start at the beginning of the next line
        col = 0
        line = pos.line + 1

        # make sure a suitable number of leading empty lines is used (at least 0/1 depending on the symbol type,
        # otherwise as many as the caller wanted to insert)
        original_leading_newlines = self._count_leading_newlines(body)
        body = body.lstrip("\r\n")
        min_empty_lines = 0
        if symbol.is_neighbouring_definition_separated_by_empty_line():
            min_empty_lines = 1
        num_leading_empty_lines = max(min_empty_lines, original_leading_newlines)
        if num_leading_empty_lines:
            body = ("\n" * num_leading_empty_lines) + body

        # make sure the one line break succeeding the original symbol, which we repurposed as prefix via
        # `line += 1`, is replaced
        body = body.rstrip("\r\n") + "\n"

        with self.edited_file_context(relative_file_path) as edited_file:
            edited_file.insert_text_at_position(PositionInFile(line, col), body)

    def insert_before_symbol(self, name_path: str, relative_file_path: str, body: str) -> None:
        """
        Inserts content before the symbol with the given name in the given file.
        """
        symbol = self._find_unique_symbol(name_path, relative_file_path)
        symbol_start_pos = symbol.get_body_start_position_or_raise()

        # insert position is the start of line where the symbol is defined
        line = symbol_start_pos.line
        col = 0

        original_trailing_empty_lines = self._count_trailing_newlines(body) - 1

        # ensure eol is present at end
        body = body.rstrip() + "\n"

        # add suitable number of trailing empty lines after the body (at least 0/1 depending on the symbol type,
        # otherwise as many as the caller wanted to insert)
        min_trailing_empty_lines = 0
        if symbol.is_neighbouring_definition_separated_by_empty_line():
            min_trailing_empty_lines = 1
        num_trailing_newlines = max(min_trailing_empty_lines, original_trailing_empty_lines)
        body += "\n" * num_trailing_newlines

        # apply edit
        with self.edited_file_context(relative_file_path) as edited_file:
            edited_file.insert_text_at_position(PositionInFile(line=line, col=col), body)

    def insert_at_line(self, relative_path: str, line: int, content: str) -> None:
        """
        Inserts content at the given line in the given file.

        :param relative_path: the relative path of the file in which to insert content
        :param line: the 0-based index of the line to insert content at
        :param content: the content to insert
        """
        with self.edited_file_context(relative_path) as edited_file:
            edited_file.insert_text_at_position(PositionInFile(line, 0), content)

    def delete_lines(self, relative_path: str, start_line: int, end_line: int) -> None:
        """
        Deletes lines in the given file.

        :param relative_path: the relative path of the file in which to delete lines
        :param start_line: the 0-based index of the first line to delete (inclusive)
        :param end_line: the 0-based index of the last line to delete (inclusive)
        """
        start_col = 0
        end_line_for_delete = end_line + 1
        end_col = 0
        with self.edited_file_context(relative_path) as edited_file:
            start_pos = PositionInFile(line=start_line, col=start_col)
            end_pos = PositionInFile(line=end_line_for_delete, col=end_col)
            edited_file.delete_text_between_positions(start_pos, end_pos)

    def delete_symbol(self, name_path: str, relative_file_path: str) -> None:
        """
        Deletes the symbol with the given name in the given file.
        """
        symbol = self._find_unique_symbol(name_path, relative_file_path)
        start_pos = symbol.get_body_start_position_or_raise()
        end_pos = symbol.get_body_end_position_or_raise()
        with self.edited_file_context(relative_file_path) as edited_file:
            edited_file.delete_text_between_positions(start_pos, end_pos)

    @abstractmethod
    def rename_symbol(self, name_path: str, relative_file_path: str, new_name: str) -> str:
        """
        Renames the symbol with the given name throughout the codebase.

        :param name_path: the name path of the symbol to rename
        :param relative_file_path: the relative path of the file containing the symbol
        :param new_name: the new name for the symbol
        :return: a status message
        """


class LanguageServerCodeEditor(CodeEditor[LanguageServerSymbol]):
    def __init__(self, symbol_retriever: LanguageServerSymbolRetriever, agent: Optional["SerenaAgent"] = None):
        super().__init__(project_root=symbol_retriever.get_root_path(), agent=agent)
        self._symbol_retriever = symbol_retriever

    def _get_language_server(self, relative_path: str) -> SolidLanguageServer:
        return self._symbol_retriever.get_language_server(relative_path)

    class EditedFile(CodeEditor.EditedFile):
        def __init__(self, lang_server: SolidLanguageServer, relative_path: str, file_buffer: LSPFileBuffer):
            super().__init__(relative_path)
            self._lang_server = lang_server
            self._file_buffer = file_buffer

        def get_contents(self) -> str:
            return self._file_buffer.contents

        def set_contents(self, contents: str) -> None:
            self._file_buffer.contents = contents

        def delete_text_between_positions(self, start_pos: PositionInFile, end_pos: PositionInFile) -> None:
            self._lang_server.delete_text_between_positions(self.relative_path, start_pos.to_lsp_position(), end_pos.to_lsp_position())

        def insert_text_at_position(self, pos: PositionInFile, text: str) -> None:
            self._lang_server.insert_text_at_position(self.relative_path, pos.line, pos.col, text)

        def apply_text_edits(self, text_edits: list[ls_types.TextEdit]) -> None:
            return self._lang_server.apply_text_edits_to_file(self.relative_path, text_edits)

    @contextmanager
    def _open_file_context(self, relative_path: str) -> Iterator["CodeEditor.EditedFile"]:
        lang_server = self._get_language_server(relative_path)
        with lang_server.open_file(relative_path) as file_buffer:
            yield self.EditedFile(lang_server, relative_path, file_buffer)

    def _get_code_file_content(self, relative_path: str) -> str:
        """Get the content of a file using the language server."""
        lang_server = self._get_language_server(relative_path)
        return lang_server.language_server.retrieve_full_file_content(relative_path)

    def _find_unique_symbol(self, name_path: str, relative_file_path: str) -> LanguageServerSymbol:
        return self._symbol_retriever.find_unique(name_path, within_relative_path=relative_file_path)

    def _relative_path_from_uri(self, uri: str) -> str:
        return os.path.relpath(PathUtils.uri_to_path(uri), self.project_root)

    class EditOperation(ABC):
        @abstractmethod
        def apply(self) -> None:
            pass

    class EditOperationFileTextEdits(EditOperation):
        def __init__(self, code_editor: "LanguageServerCodeEditor", file_uri: str, text_edits: list[ls_types.TextEdit]):
            self._code_editor = code_editor
            self._relative_path = code_editor._relative_path_from_uri(file_uri)
            self._text_edits = text_edits

        def apply(self) -> None:
            with self._code_editor.edited_file_context(self._relative_path) as edited_file:
                edited_file = cast(LanguageServerCodeEditor.EditedFile, edited_file)
                edited_file.apply_text_edits(self._text_edits)

    class EditOperationRenameFile(EditOperation):
        def __init__(self, code_editor: "LanguageServerCodeEditor", old_uri: str, new_uri: str):
            self._code_editor = code_editor
            self._old_relative_path = code_editor._relative_path_from_uri(old_uri)
            self._new_relative_path = code_editor._relative_path_from_uri(new_uri)

        def apply(self) -> None:
            old_abs_path = os.path.join(self._code_editor.project_root, self._old_relative_path)
            new_abs_path = os.path.join(self._code_editor.project_root, self._new_relative_path)
            os.rename(old_abs_path, new_abs_path)

    def _workspace_edit_to_edit_operations(self, workspace_edit: ls_types.WorkspaceEdit) -> list["LanguageServerCodeEditor.EditOperation"]:
        operations: list[LanguageServerCodeEditor.EditOperation] = []

        if "changes" in workspace_edit:
            for uri, edits in workspace_edit["changes"].items():
                operations.append(self.EditOperationFileTextEdits(self, uri, edits))

        if "documentChanges" in workspace_edit:
            for change in workspace_edit["documentChanges"]:
                if "textDocument" in change and "edits" in change:
                    operations.append(self.EditOperationFileTextEdits(self, change["textDocument"]["uri"], change["edits"]))
                elif "kind" in change:
                    if change["kind"] == "rename":
                        operations.append(self.EditOperationRenameFile(self, change["oldUri"], change["newUri"]))
                    else:
                        raise ValueError(f"Unhandled document change kind: {change}; Please report to Serena developers.")
                else:
                    raise ValueError(f"Unhandled document change format: {change}; Please report to Serena developers.")

        return operations

    def _apply_workspace_edit(self, workspace_edit: ls_types.WorkspaceEdit) -> int:
        """
        Applies a WorkspaceEdit

        :param workspace_edit: the edit to apply
        :return: number of edit operations applied
        """
        operations = self._workspace_edit_to_edit_operations(workspace_edit)
        for operation in operations:
            operation.apply()
        return len(operations)

    def rename_symbol(self, name_path: str, relative_file_path: str, new_name: str) -> str:
        symbol = self._find_unique_symbol(name_path, relative_file_path)
        if not symbol.location.has_position_in_file():
            raise ValueError(f"Symbol '{name_path}' does not have a valid position in file for renaming")

        # After has_position_in_file check, line and column are guaranteed to be non-None
        assert symbol.location.line is not None
        assert symbol.location.column is not None

        lang_server = self._get_language_server(relative_file_path)
        rename_result = lang_server.request_rename_symbol_edit(
            relative_file_path=relative_file_path, line=symbol.location.line, column=symbol.location.column, new_name=new_name
        )
        if rename_result is None:
            raise ValueError(
                f"Language server for {lang_server.language_id} returned no rename edits for symbol '{name_path}'. "
                f"The symbol might not support renaming."
            )
        num_changes = self._apply_workspace_edit(rename_result)

        if num_changes == 0:
            raise ValueError(
                f"Renaming symbol '{name_path}' to '{new_name}' resulted in no changes being applied; renaming may not be supported."
            )

        msg = f"Successfully renamed '{name_path}' to '{new_name}' ({num_changes} changes applied)"
        return msg


class JetBrainsCodeEditor(CodeEditor[JetBrainsSymbol]):
    def __init__(self, project: Project, agent: Optional["SerenaAgent"] = None) -> None:
        self._project = project
        super().__init__(project_root=project.project_root, agent=agent)

    class EditedFile(CodeEditor.EditedFile):
        def __init__(self, relative_path: str, project: Project):
            super().__init__(relative_path)
            path = os.path.join(project.project_root, relative_path)
            log.info("Editing file: %s", path)
            with open(path, encoding=project.project_config.encoding) as f:
                self._content = f.read()

        def get_contents(self) -> str:
            return self._content

        def set_contents(self, contents: str) -> None:
            self._content = contents

        def delete_text_between_positions(self, start_pos: PositionInFile, end_pos: PositionInFile) -> None:
            self._content, _ = TextUtils.delete_text_between_positions(
                self._content, start_pos.line, start_pos.col, end_pos.line, end_pos.col
            )

        def insert_text_at_position(self, pos: PositionInFile, text: str) -> None:
            self._content, _, _ = TextUtils.insert_text_at_position(self._content, pos.line, pos.col, text)

    @contextmanager
    def _open_file_context(self, relative_path: str) -> Iterator["CodeEditor.EditedFile"]:
        yield self.EditedFile(relative_path, self._project)

    def _save_edited_file(self, edited_file: "CodeEditor.EditedFile") -> None:
        super()._save_edited_file(edited_file)
        with JetBrainsPluginClient.from_project(self._project) as client:
            client.refresh_file(edited_file.relative_path)

    def _find_unique_symbol(self, name_path: str, relative_file_path: str) -> JetBrainsSymbol:
        with JetBrainsPluginClient.from_project(self._project) as client:
            result = client.find_symbol(name_path, relative_path=relative_file_path, include_body=False, depth=0, include_location=True)
            symbols = result["symbols"]
            if not symbols:
                raise ValueError(f"No symbol with name {name_path} found in file {relative_file_path}")
            if len(symbols) > 1:
                raise ValueError(
                    f"Found multiple {len(symbols)} symbols with name {name_path} in file {relative_file_path}. "
                    "They are: \n " + json.dumps(symbols, indent=2)
                )
            return JetBrainsSymbol(symbols[0], self._project)

    def rename_symbol(self, name_path: str, relative_file_path: str, new_name: str) -> str:
        with JetBrainsPluginClient.from_project(self._project) as client:
            client.rename_symbol(
                name_path=name_path,
                relative_path=relative_file_path,
                new_name=new_name,
                rename_in_comments=False,
                rename_in_text_occurrences=False,
            )
            return "Success"
