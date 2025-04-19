"""
This file contains the main interface and the public API for multilspy. 
The abstract class LanguageServer provides a factory method, creator that is 
intended for creating instantiations of language specific clients.
The details of Language Specific configuration are not exposed to the user.
"""

import asyncio
import dataclasses
import hashlib
import json
import logging
import os
import pathlib
import pickle
import re
from site import abs_paths
import threading
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from copy import copy
from typing import Dict, List, Optional, Tuple, Union
from fnmatch import fnmatch
from pathlib import Path, PurePath
from typing import AsyncIterator, Dict, Iterator, List, Optional, Tuple, Union, cast

import pathspec

from serena.text_utils import LineType, MatchedConsecutiveLines, TextLine, search_files, search_text
from . import multilspy_types
from .lsp_protocol_handler import lsp_types as LSPTypes
from .lsp_protocol_handler.lsp_constants import LSPConstants
from .lsp_protocol_handler.lsp_types import SymbolKind
from .lsp_protocol_handler.server import (
    LanguageServerHandler,
    ProcessLaunchInfo,
)
from .multilspy_config import Language, MultilspyConfig
from .multilspy_exceptions import MultilspyException
from .multilspy_utils import PathUtils, FileUtils, TextUtils
from pathlib import PurePath
from typing import AsyncIterator, Iterator, List, Dict, Optional, Union, Tuple
from .multilspy_logger import MultilspyLogger
from .multilspy_utils import FileUtils, PathUtils, TextUtils
from .type_helpers import ensure_all_methods_implemented

# Serena dependencies
# We will need to watch out for circular imports, but it's probably better to not
# move all generic util code from serena into multilspy.
# It does however make sense to integrate many text-related utils into the language server
# since it caches (in-memory) file contents, so we can avoid reading from disk.
# Moreover, the way we want to use the language server (for retrieving actual content),
# it makes sense to have more content-related utils directly in it.


GenericDocumentSymbol = Union[LSPTypes.DocumentSymbol, LSPTypes.SymbolInformation, multilspy_types.UnifiedSymbolInformation]

@dataclasses.dataclass
class LSPFileBuffer:
    """
    This class is used to store the contents of an open LSP file in memory.
    """

    # uri of the file
    uri: str

    # The contents of the file
    contents: str

    # The version of the file
    version: int

    # The language id of the file
    language_id: str

    # reference count of the file
    ref_count: int

    # --------------------------------- MODIFICATIONS BY MISCHA ---------------------------------

    content_hash: str = ""

    def __post_init__(self):
        self.content_hash = hashlib.md5(self.contents.encode('utf-8')).hexdigest()


class LanguageServer:
    """
    The LanguageServer class provides a language agnostic interface to the Language Server Protocol.
    It is used to communicate with Language Servers of different programming languages.
    """

    # To be overridden and extended by subclasses
    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        A language-specific condition for directories that should always be ignored. For example, venv
        in Python and node_modules in JS/TS should be ignored always.
        """
        return dirname.startswith('.')

    @classmethod
    def create(cls, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str, add_gitignore_content_to_config: bool = True) -> "LanguageServer":
        """
        Creates a language specific LanguageServer instance based on the given configuration, and appropriate settings for the programming language.

        If language is Java, then ensure that jdk-17.0.6 or higher is installed, `java` is in PATH, and JAVA_HOME is set to the installation directory.
        If language is JS/TS, then ensure that node (v18.16.0 or higher) is installed and in PATH.

        :param repository_root_path: The root path of the repository.
        :param config: The Multilspy configuration.
        :param logger: The logger to use.
        :param add_gitignore_content_to_config: whether to add the content of the .gitignore file (if any found) to the config, so that
            the paths ignored there are also ignored by the language server

        :return LanguageServer: A language specific LanguageServer instance.
        """
        config = copy(config)  # prevent mutation
        if add_gitignore_content_to_config:
            gitignore_path = os.path.join(repository_root_path, ".gitignore")
            if not os.path.exists(gitignore_path):
                logger.log(
                    f"Should ignore all files in gitignore not not .gitignore found at {gitignore_path}. Skipping.",
                    logging.WARNING
                )
                gitignore_file_content = None
            else:
                if config.gitignore_file_content is not None:
                    raise ValueError(
                        f"Asked to add gitignore content to the config for {repository_root_path=} but there already is a non-empty entry"
                    )
                with open(gitignore_path) as f:
                    gitignore_file_content = f.read()
            config.gitignore_file_content = gitignore_file_content

        if config.code_language == Language.PYTHON:
            from multilspy.language_servers.pyright_language_server.pyright_server import (
                PyrightServer,
            )

            return PyrightServer(config, logger, repository_root_path)
            # It used to be jedi, but pyright is a bit faster, and also more actively maintained
            # Keeping the previous code for reference
            from multilspy.language_servers.jedi_language_server.jedi_server import (
                JediServer,
            )

            return JediServer(config, logger, repository_root_path)
        elif config.code_language == Language.JAVA:
            from multilspy.language_servers.eclipse_jdtls.eclipse_jdtls import (
                EclipseJDTLS,
            )

            return EclipseJDTLS(config, logger, repository_root_path)
        elif config.code_language == Language.KOTLIN:
            from multilspy.language_servers.kotlin_language_server.kotlin_language_server import (
                KotlinLanguageServer,
            )

            return KotlinLanguageServer(config, logger, repository_root_path)
        elif config.code_language == Language.RUST:
            from multilspy.language_servers.rust_analyzer.rust_analyzer import (
                RustAnalyzer,
            )

            return RustAnalyzer(config, logger, repository_root_path)
        elif config.code_language == Language.CSHARP:
            from multilspy.language_servers.omnisharp.omnisharp import OmniSharp

            return OmniSharp(config, logger, repository_root_path)
        elif config.code_language in [Language.TYPESCRIPT, Language.JAVASCRIPT]:
            from multilspy.language_servers.typescript_language_server.typescript_language_server import (
                TypeScriptLanguageServer,
            )
            return TypeScriptLanguageServer(config, logger, repository_root_path)
        elif config.code_language == Language.GO:
            from multilspy.language_servers.gopls.gopls import Gopls

            return Gopls(config, logger, repository_root_path)
        elif config.code_language == Language.RUBY:
            from multilspy.language_servers.solargraph.solargraph import Solargraph

            return Solargraph(config, logger, repository_root_path)
        elif config.code_language == Language.DART:
            from multilspy.language_servers.dart_language_server.dart_language_server import DartLanguageServer

            return DartLanguageServer(config, logger, repository_root_path)
        elif config.code_language == Language.CPP:
            from multilspy.language_servers.clangd_language_server.clangd_language_server import ClangdLanguageServer

            return ClangdLanguageServer(config, logger, repository_root_path)
        else:
            logger.log(f"Language {config.code_language} is not supported", logging.ERROR)
            raise MultilspyException(f"Language {config.code_language} is not supported")

    def __init__(
        self,
        config: MultilspyConfig,
        logger: MultilspyLogger,
        repository_root_path: str,
        process_launch_info: ProcessLaunchInfo,
        language_id: str,
    ):
        """
        Initializes a LanguageServer instance.

        Do not instantiate this class directly. Use `LanguageServer.create` method instead.

        :param config: The Multilspy configuration.
        :param logger: The logger to use.
        :param repository_root_path: The root path of the repository.
        :param process_launch_info: Each language server has a specific command used to start the server.
                    This parameter is the command to launch the language server process.
                    The command must pass appropriate flags to the binary, so that it runs in the stdio mode,
                    as opposed to HTTP, TCP modes supported by some language servers.
        """
        if type(self) == LanguageServer:
            raise MultilspyException(
                "LanguageServer is an abstract class and cannot be instantiated directly. Use LanguageServer.create method instead."
            )

        self.logger = logger
        self.server_started = False
        self.repository_root_path: str = repository_root_path
        self.completions_available = asyncio.Event()

        if config.trace_lsp_communication:

            def logging_fn(source, target, msg):
                self.logger.log(f"LSP: {source} -> {target}: {str(msg)}", logging.DEBUG)

        else:

            def logging_fn(source, target, msg):
                pass

        # cmd is obtained from the child classes, which provide the language specific command to start the language server
        # LanguageServerHandler provides the functionality to start the language server and communicate with it
        self.server: LanguageServerHandler = LanguageServerHandler(
            process_launch_info,
            logger=logging_fn,
            start_independent_lsp_process=config.start_independent_lsp_process,
        )

        self.language_id = language_id
        self.open_file_buffers: Dict[str, LSPFileBuffer] = {}

        # --------------------------------- MODIFICATIONS BY ORAIOS ---------------------------------
        self._document_symbols_cache:  dict[str, Tuple[str, Tuple[List[multilspy_types.UnifiedSymbolInformation], List[multilspy_types.UnifiedSymbolInformation]]]] = {}
        """Maps file paths to a tuple of (file_content_hash, result_of_request_document_symbols)"""
        self.load_cache()
        self._cache_has_changed = bool
        self.language = Language(language_id)

        # Set up the pathspec matcher for the ignored paths
        # for all absolute paths in ignored_paths, convert them to relative paths
        processed_patterns = []
        for pattern in set(config.ignored_paths):
            # Normalize separators (pathspec expects forward slashes)
            pattern = pattern.replace(os.path.sep, '/')
            processed_patterns.append(pattern)
        # Combine explicitly passed patterns with the content of the .gitignore file
        if config.gitignore_file_content is not None:
            for line in config.gitignore_file_content.splitlines():
                if not line.startswith('#') and line.strip() != '':
                    processed_patterns.append(line.strip())

        # Create a pathspec matcher from the processed patterns
        self._ignore_spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern,
            processed_patterns
        )

    def get_ignore_spec(self) -> pathspec.PathSpec:
        """Returns the pathspec matcher for the paths that were configured to be ignored through
        the multilspy config file and the .gitignore file.

        This is is a subset of the full language-specific ignore spec that determines
        which files are relevant for the language server.

        This matcher is useful for operations outside of the language server,
        such as when searching for relevant non-language files in the project.
        """
        return self._ignore_spec

    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True, check_existence: bool = True) -> bool:
        """
        Determine if a path should be ignored based on file type
        and ignore patterns.

        :param relative_path: Relative path to check
        :param ignore_unsupported_files: whether files that are not supported source files should be ignored
        :param check_existence: whether to check if the file exists before checking if it should be ignored;
            if False, the path is assumed to refer to a file, even if it doesn't exist

        :return: True if the path should be ignored, False otherwise
        """
        abs_path = os.path.join(self.repository_root_path, relative_path)
        if not os.path.exists(abs_path):
            if check_existence:
                raise FileNotFoundError(f"File {abs_path} not found, the ignore check cannot be performed")
            is_file = True
        else:
            is_file = os.path.isfile(abs_path)

        # Check file extension if it's a file
        if is_file and ignore_unsupported_files:
            fn_matcher = self.language.get_source_fn_matcher()
            if not fn_matcher.is_relevant_filename(abs_path):
                return True

        # Create normalized path for consistent handling
        rel_path = Path(relative_path)

        # Check each part of the path against always fulfilled ignore conditions
        dir_parts = rel_path.parts
        if is_file:
            dir_parts = dir_parts[:-1]
        for part in dir_parts:
            if not part:  # Skip empty parts (e.g., from leading '/')
                continue
            if self.is_ignored_dirname(part):
                return True

        # Use pathspec for gitignore-style pattern matching
        # Normalize path separators for pathspec (it expects forward slashes)
        normalized_path = str(rel_path).replace(os.path.sep, '/')

        # pathspec can't handle the matching of directories if they don't end with a slash!
        # see https://github.com/cpburnz/python-pathspec/issues/89
        if os.path.isdir(os.path.join(self.repository_root_path, normalized_path)) and not normalized_path.endswith('/'):
            normalized_path = normalized_path + '/'

        # Use the pathspec matcher to check if the path matches any ignore pattern
        if self._ignore_spec.match_file(normalized_path):
            return True

        return False


    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["LanguageServer"]:
        """
        Starts the Language Server and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        ```
        """
        self.server_started = True
        yield self
        self.server_started = False

    # TODO: Add support for more LSP features

    @contextmanager
    def open_file(self, relative_file_path: str) -> Iterator[LSPFileBuffer]:
        """
        Open a file in the Language Server. This is required before making any requests to the Language Server.

        :param relative_file_path: The relative path of the file to open.
        """
        if not self.server_started:
            self.logger.log(
                "open_file called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()

        if uri in self.open_file_buffers:
            assert self.open_file_buffers[uri].uri == uri
            assert self.open_file_buffers[uri].ref_count >= 1

            self.open_file_buffers[uri].ref_count += 1
            yield self.open_file_buffers[uri]
            self.open_file_buffers[uri].ref_count -= 1
        else:
            contents = FileUtils.read_file(self.logger, absolute_file_path)

            version = 0
            self.open_file_buffers[uri] = LSPFileBuffer(uri, contents, version, self.language_id, 1)

            self.server.notify.did_open_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {
                        LSPConstants.URI: uri,
                        LSPConstants.LANGUAGE_ID: self.language_id,
                        LSPConstants.VERSION: 0,
                        LSPConstants.TEXT: contents,
                    }
                }
            )
            yield self.open_file_buffers[uri]
            self.open_file_buffers[uri].ref_count -= 1

        if self.open_file_buffers[uri].ref_count == 0:
            self.server.notify.did_close_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {
                        LSPConstants.URI: uri,
                    }
                }
            )
            del self.open_file_buffers[uri]

    def insert_text_at_position(
        self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str
    ) -> multilspy_types.Position:
        """
        Insert text at the given line and column in the given file and return 
        the updated cursor position after inserting the text.

        :param relative_file_path: The relative path of the file to open.
        :param line: The line number at which text should be inserted.
        :param column: The column number at which text should be inserted.
        :param text_to_be_inserted: The text to insert.
        """
        if not self.server_started:
            self.logger.log(
                "insert_text_at_position called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()

        # Ensure the file is open
        assert uri in self.open_file_buffers

        file_buffer = self.open_file_buffers[uri]
        file_buffer.version += 1
        change_index = TextUtils.get_index_from_line_col(file_buffer.contents, line, column)
        file_buffer.contents = (
            file_buffer.contents[:change_index] + text_to_be_inserted + file_buffer.contents[change_index:]
        )
        self.server.notify.did_change_text_document(
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
        new_l, new_c = TextUtils.get_updated_position_from_line_and_column_and_edit(line, column, text_to_be_inserted)
        return multilspy_types.Position(line=new_l, character=new_c)

    def delete_text_between_positions(
        self,
        relative_file_path: str,
        start: multilspy_types.Position,
        end: multilspy_types.Position,
    ) -> str:
        """
        Delete text between the given start and end positions in the given file and return the deleted text.
        """
        if not self.server_started:
            self.logger.log(
                "insert_text_at_position called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()

        # Ensure the file is open
        assert uri in self.open_file_buffers

        file_buffer = self.open_file_buffers[uri]
        file_buffer.version += 1
        del_start_idx = TextUtils.get_index_from_line_col(file_buffer.contents, start["line"], start["character"])
        del_end_idx = TextUtils.get_index_from_line_col(file_buffer.contents, end["line"], end["character"])
        deleted_text = file_buffer.contents[del_start_idx:del_end_idx]
        file_buffer.contents = file_buffer.contents[:del_start_idx] + file_buffer.contents[del_end_idx:]
        self.server.notify.did_change_text_document(
            {
                LSPConstants.TEXT_DOCUMENT: {
                    LSPConstants.VERSION: file_buffer.version,
                    LSPConstants.URI: file_buffer.uri,
                },
                LSPConstants.CONTENT_CHANGES: [{LSPConstants.RANGE: {"start": start, "end": end}, "text": ""}],
            }
        )
        return deleted_text

    async def request_definition(
        self, relative_file_path: str, line: int, column: int
    ) -> List[multilspy_types.Location]:
        """
        Raise a [textDocument/definition](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_definition) request to the Language Server
        for the symbol at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbol for which definition should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return List[multilspy_types.Location]: A list of locations where the symbol is defined
        """

        if not self.server_started:
            self.logger.log(
                "find_function_definition called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")

        with self.open_file(relative_file_path):
            # sending request to the language server and waiting for response
            response = await self.server.send.definition(
                {
                    LSPConstants.TEXT_DOCUMENT: {
                        LSPConstants.URI: pathlib.Path(
                            str(PurePath(self.repository_root_path, relative_file_path))
                        ).as_uri()
                    },
                    LSPConstants.POSITION: {
                        LSPConstants.LINE: line,
                        LSPConstants.CHARACTER: column,
                    },
                }
            )

        ret: List[multilspy_types.Location] = []
        if isinstance(response, list):
            # response is either of type Location[] or LocationLink[]
            for item in response:
                assert isinstance(item, dict)
                if LSPConstants.URI in item and LSPConstants.RANGE in item:
                    new_item: multilspy_types.Location = {}
                    new_item.update(item)
                    new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
                    new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
                    ret.append(multilspy_types.Location(new_item))
                elif (
                    LSPConstants.ORIGIN_SELECTION_RANGE in item
                    and LSPConstants.TARGET_URI in item
                    and LSPConstants.TARGET_RANGE in item
                    and LSPConstants.TARGET_SELECTION_RANGE in item
                ):
                    new_item: multilspy_types.Location = {}
                    new_item["uri"] = item[LSPConstants.TARGET_URI]
                    new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
                    new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
                    new_item["range"] = item[LSPConstants.TARGET_SELECTION_RANGE]
                    ret.append(multilspy_types.Location(**new_item))
                else:
                    assert False, f"Unexpected response from Language Server: {item}"
        elif isinstance(response, dict):
            # response is of type Location
            assert LSPConstants.URI in response
            assert LSPConstants.RANGE in response

            new_item: multilspy_types.Location = {}
            new_item.update(response)
            new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
            new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
            ret.append(multilspy_types.Location(**new_item))
        elif response is None:
            # Some language servers return None when they cannot find a definition
            # This is expected for certain symbol types like generics or types with incomplete information
            self.logger.log(
                f"Language server returned None for definition request at {relative_file_path}:{line}:{column}",
                logging.WARNING,
            )
        else:
            assert False, f"Unexpected response from Language Server: {response}"

        return ret

    async def request_references(
        self, relative_file_path: str, line: int, column: int
    ) -> List[multilspy_types.Location]:
        """
        Raise a [textDocument/references](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_references) request to the Language Server
        to find references to the symbol at the given line and column in the given file. Wait for the response and return the result.
        Filters out references located in ignored directories.

        :param relative_file_path: The relative path of the file that has the symbol for which references should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return: A list of locations where the symbol is referenced (excluding ignored directories)
        """

        if not self.server_started:
            self.logger.log(
                "request_references called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")


        with self.open_file(relative_file_path):
            # sending request to the language server and waiting for response
            response = await self.server.send.references(
                {
                    "context": {"includeDeclaration": False},
                    "textDocument": {
                        "uri": pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()
                    },
                    "position": {"line": line, "character": column},
                }
            )

        ret: List[multilspy_types.Location] = []
        assert isinstance(response, list), f"Unexpected response from Language Server: {response}"
        for item in response:
            assert isinstance(item, dict)
            assert LSPConstants.URI in item
            assert LSPConstants.RANGE in item

            abs_path = PathUtils.uri_to_path(item[LSPConstants.URI])
            rel_path = Path(abs_path).relative_to(self.repository_root_path)
            if self.is_ignored_path(str(rel_path)):
                self.logger.log(f"Ignoring reference in {rel_path} since it should be ignored", logging.DEBUG)
                continue

            new_item: multilspy_types.Location = {}
            new_item.update(item)
            new_item["absolutePath"] = str(abs_path)
            new_item["relativePath"] = str(rel_path)
            ret.append(multilspy_types.Location(**new_item))

        return ret

    async def request_references_with_content(
        self, relative_file_path: str, line: int, column: int, context_lines_before: int = 0, context_lines_after: int = 0
    ) -> List[MatchedConsecutiveLines]:
        """
        Like request_references, but returns the content of the lines containing the references, not just the locations.

        :param relative_file_path: The relative path of the file that has the symbol for which references should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol
        :param context_lines_before: The number of lines to include in the context before the line containing the reference
        :param context_lines_after: The number of lines to include in the context after the line containing the reference

        :return: A list of MatchedConsecutiveLines objects, one for each reference.
        """
        references = await self.request_references(relative_file_path, line, column)
        return [self.retrieve_content_around_line(ref["relativePath"], ref["range"]["start"]["line"], context_lines_before, context_lines_after) for ref in references]

    def retrieve_full_file_content(self, relative_file_path: str) -> str:
        """
        Retrieve the full content of the given file.
        """
        with self.open_file(relative_file_path) as file_data:
            return file_data.contents

    def retrieve_content_around_line(self, relative_file_path: str, line: int, context_lines_before: int = 0, context_lines_after: int = 0) -> MatchedConsecutiveLines:
        """
        Retrieve the content of the given file around the given line.

        :param relative_file_path: The relative path of the file to retrieve the content from
        :param line: The line number to retrieve the content around
        :param context_lines_before: The number of lines to retrieve before the given line
        :param context_lines_after: The number of lines to retrieve after the given line

        :return MatchedConsecutiveLines: A container with the desired lines.
        """
        with self.open_file(relative_file_path) as file_data:
            file_contents = file_data.contents

        line_contents = file_contents.split("\n")
        start_lineno = max(0, line - context_lines_before)
        end_lineno = min(len(line_contents) - 1, line + context_lines_after)
        # instantiate TextLines with the write LineType
        text_lines: list[TextLine] = []
        # before the line
        for lineno in range(start_lineno, line):
            text_lines.append(TextLine(line_number=lineno, line_content=line_contents[lineno], match_type=LineType.BEFORE_MATCH))
        # the line
        text_lines.append(TextLine(line_number=line, line_content=line_contents[line], match_type=LineType.MATCH))
        # after the line
        for lineno in range(line + 1, end_lineno + 1):
            text_lines.append(TextLine(line_number=lineno, line_content=line_contents[lineno], match_type=LineType.AFTER_MATCH))

        return MatchedConsecutiveLines(lines=text_lines, source_file_path=relative_file_path)


    async def request_completions(
        self, relative_file_path: str, line: int, column: int, allow_incomplete: bool = False
    ) -> List[multilspy_types.CompletionItem]:
        """
        Raise a [textDocument/completion](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_completion) request to the Language Server
        to find completions at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbol for which completions should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return List[multilspy_types.CompletionItem]: A list of completions
        """
        with self.open_file(relative_file_path):
            open_file_buffer = self.open_file_buffers[
                pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()
            ]
            completion_params: LSPTypes.CompletionParams = {
                "position": {"line": line, "character": column},
                "textDocument": {"uri": open_file_buffer.uri},
                "context": {"triggerKind": LSPTypes.CompletionTriggerKind.Invoked},
            }
            response: Union[List[LSPTypes.CompletionItem], LSPTypes.CompletionList, None] = None

            num_retries = 0
            while response is None or (response["isIncomplete"] and num_retries < 30):
                await self.completions_available.wait()
                response: Union[
                    List[LSPTypes.CompletionItem], LSPTypes.CompletionList, None
                ] = await self.server.send.completion(completion_params)
                if isinstance(response, list):
                    response = {"items": response, "isIncomplete": False}
                num_retries += 1

            # TODO: Understand how to appropriately handle `isIncomplete`
            if response is None or (response["isIncomplete"] and not(allow_incomplete)):
                return []

            if "items" in response:
                response = response["items"]

            response: List[LSPTypes.CompletionItem] = response

            # TODO: Handle the case when the completion is a keyword
            items = [item for item in response if item["kind"] != LSPTypes.CompletionItemKind.Keyword]

            completions_list: List[multilspy_types.CompletionItem] = []

            for item in items:
                assert "insertText" in item or "textEdit" in item
                assert "kind" in item
                completion_item = {}
                if "detail" in item:
                    completion_item["detail"] = item["detail"]
                
                if "label" in item:
                    completion_item["completionText"] = item["label"]
                    completion_item["kind"] = item["kind"]
                elif "insertText" in item:
                    completion_item["completionText"] = item["insertText"]
                    completion_item["kind"] = item["kind"]
                elif "textEdit" in item and "newText" in item["textEdit"]:
                    completion_item["completionText"] = item["textEdit"]["newText"]
                    completion_item["kind"] = item["kind"]
                elif "textEdit" in item and "range" in item["textEdit"]:
                    new_dot_lineno, new_dot_colno = (
                        completion_params["position"]["line"],
                        completion_params["position"]["character"],
                    )
                    assert all(
                        (
                            item["textEdit"]["range"]["start"]["line"] == new_dot_lineno,
                            item["textEdit"]["range"]["start"]["character"] == new_dot_colno,
                            item["textEdit"]["range"]["start"]["line"] == item["textEdit"]["range"]["end"]["line"],
                            item["textEdit"]["range"]["start"]["character"]
                            == item["textEdit"]["range"]["end"]["character"],
                        )
                    )
                    
                    completion_item["completionText"] = item["textEdit"]["newText"]
                    completion_item["kind"] = item["kind"]
                elif "textEdit" in item and "insert" in item["textEdit"]:
                    assert False
                else:
                    assert False

                completion_item = multilspy_types.CompletionItem(**completion_item)
                completions_list.append(completion_item)

            return [
                json.loads(json_repr)
                for json_repr in set([json.dumps(item, sort_keys=True) for item in completions_list])
            ]

    async def request_document_symbols(self, relative_file_path: str, include_body: bool = False) -> Tuple[List[multilspy_types.UnifiedSymbolInformation], List[multilspy_types.UnifiedSymbolInformation]]:
        """
        Raise a [textDocument/documentSymbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_documentSymbol) request to the Language Server
        to find symbols in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbols
        :param include_body: whether to include the body of the symbols in the result.
        :return: A list of symbols in the file, and a list of root symbols that represent the tree structure of the symbols.
            Each symbol in hierarchy starting from the roots has a children attribute.
            All symbols will have a location and a children attribute.
        """
        self.logger.log(f"Requesting document symbols for {relative_file_path} for the first time", logging.DEBUG)
        # TODO: it's kinda dumb to not use the cache if include_body is False after include_body was True once
        #   Should be fixed in the future, it's a small performance optimization
        cache_key = f"{relative_file_path}-{include_body}"
        with self.open_file(relative_file_path) as file_data:
            file_hash_and_result = self._document_symbols_cache.get(cache_key)
            if file_hash_and_result is not None:
                file_hash, result = file_hash_and_result
                if file_hash == file_data.content_hash:
                    self.logger.log(f"Returning cached document symbols for {relative_file_path}", logging.DEBUG)
                    return result
                else:
                    self.logger.log(f"Content for {relative_file_path} has changed. Overwriting cache", logging.INFO)


            response = await self.server.send.document_symbol(
                {
                    "textDocument": {
                        "uri": pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()
                    }
                }
            )

        def turn_item_into_symbol_with_children(item: GenericDocumentSymbol):
            item = cast(multilspy_types.UnifiedSymbolInformation, item)
            if "location" not in item:
                absolute_path = os.path.join(self.repository_root_path, relative_file_path)
                uri = pathlib.Path(absolute_path).as_uri()
                assert "range" in item
                tree_location = multilspy_types.Location(
                    uri=uri,
                    range=item['range'],
                    absolutePath=absolute_path,
                    relativePath=relative_file_path,
                )
                item['location'] = tree_location
            if include_body:
                item['body'] = self.retrieve_symbol_body(item)
            item[LSPConstants.CHILDREN] = item.get(LSPConstants.CHILDREN, [])

        flat_all_symbol_list: List[multilspy_types.UnifiedSymbolInformation] = []
        assert isinstance(response, list), f"Unexpected response from Language Server: {response}"
        root_nodes: List[multilspy_types.UnifiedSymbolInformation] = []
        for item in response:
            if "range" not in item and "location" not in item:
                if item["kind"] in [SymbolKind.File, SymbolKind.Module]:
                    ...

            turn_item_into_symbol_with_children(item)
            item = cast(multilspy_types.UnifiedSymbolInformation, item)
            root_nodes.append(item)
            assert isinstance(item, dict)
            assert LSPConstants.NAME in item
            assert LSPConstants.KIND in item

            if LSPConstants.CHILDREN in item:
                # TODO: l_tree should be a list of TreeRepr. Define the following function to return TreeRepr as well
                
                def visit_tree_nodes_and_build_tree_repr(node: GenericDocumentSymbol) -> List[multilspy_types.UnifiedSymbolInformation]:
                    node = cast(multilspy_types.UnifiedSymbolInformation, node)
                    l: List[multilspy_types.UnifiedSymbolInformation] = []
                    turn_item_into_symbol_with_children(node)
                    assert LSPConstants.CHILDREN in node
                    children = node[LSPConstants.CHILDREN]
                    l.append(node)
                    for child in children:
                        l.extend(visit_tree_nodes_and_build_tree_repr(child))
                    return l
                
                flat_all_symbol_list.extend(visit_tree_nodes_and_build_tree_repr(item))
            else:
                flat_all_symbol_list.append(multilspy_types.UnifiedSymbolInformation(**item))

        result = flat_all_symbol_list, root_nodes
        self.logger.log(f"Caching document symbols for {relative_file_path}", logging.DEBUG)
        self._document_symbols_cache[cache_key] = (file_data.content_hash, result)
        self._cache_has_changed = True
        return result
    
    async def request_full_symbol_tree(self, within_relative_path: str | None = None, include_body: bool = False) -> List[multilspy_types.UnifiedSymbolInformation]:
        """
        Will go through all files in the project and build a tree of symbols. Note: this may be slow the first time it is called.

        For each file, a symbol of kind Module (3) will be created. For directories, a symbol of kind Package (4) will be created.
        All symbols will have a children attribute, thereby representing the tree structure of all symbols in the project
        that are within the repository.
        Will ignore directories starting with '.', language-specific defaults
        and user-configured directories (e.g. from .gitignore).

        :param within_relative_path: pass a relative path to only consider symbols within this path.
                If a file is passed, only the symbols within this file will be considered.
                If a directory is passed, all files within this directory will be considered.
        :param include_body: whether to include the body of the symbols in the result.

        :return: A list of root symbols representing the top-level packages/modules in the project.
        """

        if within_relative_path is not None:
            within_abs_path = os.path.join(self.repository_root_path, within_relative_path)
            if not os.path.exists(within_abs_path):
                raise FileNotFoundError(f"File or directory not found: {within_abs_path}")
            if os.path.isfile(within_abs_path):
                if self.is_ignored_path(within_relative_path):
                    self.logger.log(f"You passed a file explicitly, but it is ignored. This is probably an error. File: {within_relative_path}", logging.ERROR)
                    return []
                else:
                    _, root_nodes = await self.request_document_symbols(within_relative_path, include_body=include_body)
                    return root_nodes

        # Helper function to recursively process directories
        async def process_directory(dir_path: str) -> List[multilspy_types.UnifiedSymbolInformation]:
            abs_dir_path = self.repository_root_path if dir_path == "." else os.path.join(self.repository_root_path, dir_path)
            abs_dir_path = os.path.realpath(abs_dir_path)

            if self.is_ignored_path(str(Path(abs_dir_path).relative_to(self.repository_root_path))):
                self.logger.log(f"Skipping directory: {dir_path}\n(because it should be ignored)", logging.DEBUG)
                return []

            result = []
            try:
                items = os.listdir(abs_dir_path)
            except OSError:
                return []

            # Create package symbol for directory
            package_symbol = multilspy_types.UnifiedSymbolInformation( # type: ignore
                name=os.path.basename(abs_dir_path),
                kind=multilspy_types.SymbolKind.Package,
                location=multilspy_types.Location(
                    uri=str(pathlib.Path(abs_dir_path).as_uri()),
                    range={"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                    absolutePath=str(abs_dir_path),
                    relativePath=str(Path(abs_dir_path).resolve().relative_to(self.repository_root_path)),
                ),
                children=[]
            )
            result.append(package_symbol)

            for item in items:
                item_path = os.path.join(abs_dir_path, item)
                abs_item_path = os.path.join(self.repository_root_path, item_path)
                rel_item_path = str(Path(abs_item_path).resolve().relative_to(self.repository_root_path))
                if self.is_ignored_path(rel_item_path):
                    self.logger.log(f"Skipping item: {rel_item_path}\n(because it should be ignored)", logging.DEBUG)
                    continue

                if os.path.isdir(abs_item_path):
                    child_symbols = await process_directory(item_path)
                    package_symbol["children"].extend(child_symbols)

                elif os.path.isfile(abs_item_path):
                    _, root_nodes = await self.request_document_symbols(item_path, include_body=include_body)

                    # TODO: Not sure if this is actually still needed given recent changes to relative path handling
                    def fix_relative_path(nodes: List[multilspy_types.UnifiedSymbolInformation]):
                        for node in nodes:
                            path = Path(node["location"]["relativePath"])
                            if path.is_absolute():
                                try:
                                    path = path.relative_to(self.repository_root_path)
                                    node["location"]["relativePath"] = str(path)
                                except:
                                    pass
                            fix_relative_path(node["children"])

                    fix_relative_path(root_nodes)

                    # Create file symbol
                    file_rel_path = str(Path(abs_item_path).resolve().relative_to(self.repository_root_path))
                    with self.open_file(file_rel_path) as file_data:
                        fileRange = self._get_range_from_file_content(file_data.contents)
                    file_symbol = multilspy_types.UnifiedSymbolInformation( # type: ignore
                        name=os.path.splitext(item)[0],
                        kind=multilspy_types.SymbolKind.File,
                        range=fileRange,
                        selectionRange=fileRange,
                        location=multilspy_types.Location(
                            uri=str(pathlib.Path(abs_item_path).as_uri()),
                            range=fileRange,
                            absolutePath=str(abs_item_path),
                            relativePath=str(Path(abs_item_path).resolve().relative_to(self.repository_root_path)),
                        ),
                        children=root_nodes
                    )

                    package_symbol["children"].append(file_symbol)

            return result

        # Start from the root or the specified directory
        start_path = within_relative_path or "."
        return await process_directory(start_path)

    @staticmethod
    def _get_range_from_file_content(file_content: str) -> multilspy_types.Range:
        """
        Get the range for the given file.
        """
        lines = file_content.split("\n")
        end_line = len(lines)
        end_column = len(lines[-1])
        return multilspy_types.Range(
            start=multilspy_types.Position(line=0, character=0),
            end=multilspy_types.Position(line=end_line, character=end_column)
        )

    async def request_dir_overview(self, relative_dir_path: str) -> dict[str, list[tuple[str, multilspy_types.SymbolKind, int, int]]]:
        """
        An overview of the given directory.

        Maps relative paths of all contained files to info about top-level symbols in the file
        (name, kind, line, column).
        """
        symbol_tree = await self.request_full_symbol_tree(relative_dir_path)
        # Initialize result dictionary
        result: dict[str, list[tuple[str, multilspy_types.SymbolKind, int, int]]] = defaultdict(list)

        # Helper function to process a symbol and its children
        def process_symbol(symbol: multilspy_types.UnifiedSymbolInformation):
            if symbol["kind"] == multilspy_types.SymbolKind.File:
                # For file symbols, process their children (top-level symbols)
                for child in symbol["children"]:
                    assert "location" in child
                    assert "selectionRange" in child
                    path = Path(child["location"]["absolutePath"]).resolve().relative_to(self.repository_root_path)
                    result[str(path)].append((
                        child["name"],
                        child["kind"],
                        child["selectionRange"]["start"]["line"],
                        child["selectionRange"]["start"]["character"]
                    ))
            # For package/directory symbols, process their children
            for child in symbol["children"]:
                process_symbol(child)

        # Process each root symbol
        for root in symbol_tree:
            process_symbol(root)
        return result

    async def request_document_overview(self, relative_file_path: str) -> list[tuple[str, multilspy_types.SymbolKind, int, int]]:
        """
        An overview of the given file.
        Returns the list of tuples (name, kind, line, column) of all top-level symbols in the file.
        """
        _, document_roots = await self.request_document_symbols(relative_file_path)
        return [
            (
                root["name"],
                root["kind"],
                root["selectionRange"]["start"]["line"], # type: ignore
                root["selectionRange"]["start"]["character"] # type: ignore
            )
            for root in document_roots
        ]

    async def request_overview(self, within_relative_path: str) -> dict[str, list[tuple[str, multilspy_types.SymbolKind, int, int]]]:
        """
        An overview of all symbols in the given file or directory.

        :param within_relative_path: the relative path to the file or directory to get the overview of.
        :return: A mapping of all relative paths analyzed to lists of tuples (name, kind, line, column) of all top-level symbols in the corresponding file.
        """
        abs_path = (Path(self.repository_root_path) / within_relative_path).resolve()
        if not abs_path.exists():
            raise FileNotFoundError(f"File or directory not found: {abs_path}")

        if abs_path.is_file():
            symbols_overview = await self.request_document_overview(within_relative_path)
            return {within_relative_path: symbols_overview}
        else:
            return await self.request_dir_overview(within_relative_path)

    async def request_hover(self, relative_file_path: str, line: int, column: int) -> Union[multilspy_types.Hover, None]:
        """
        Raise a [textDocument/hover](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_hover) request to the Language Server
        to find the hover information at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the hover information
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return None
        """
        with self.open_file(relative_file_path):
            response = await self.server.send.hover(
                {
                    "textDocument": {
                        "uri": pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()
                    },
                    "position": {
                        "line": line,
                        "character": column,
                    },
                }
            )
        
        if response is None:
            return None

        assert isinstance(response, dict)

        return multilspy_types.Hover(**response)

    # ----------------------------- FROM HERE ON MODIFICATIONS BY MISCHA --------------------

    def retrieve_symbol_body(self, symbol: multilspy_types.UnifiedSymbolInformation | LSPTypes.DocumentSymbol | LSPTypes.SymbolInformation) -> str:
        """
        Load the body of the given symbol. If the body is already contained in the symbol, just return it.
        """
        existing_body = symbol.get("body", None)
        if existing_body:
            return existing_body

        assert "location" in symbol
        symbol_start_line = symbol["location"]["range"]["start"]["line"]
        symbol_end_line = symbol["location"]["range"]["end"]["line"]
        assert "relativePath" in symbol["location"]
        symbol_file = self.retrieve_full_file_content(symbol["location"]["relativePath"])
        symbol_lines = symbol_file.split("\n")
        symbol_body = "\n".join(symbol_lines[symbol_start_line:symbol_end_line+1])

        # remove leading indentation
        symbol_start_column = symbol["location"]["range"]["start"]["character"]
        symbol_body = symbol_body[symbol_start_column:]
        return symbol_body


    async def request_parsed_files(self) -> list[str]:
        """
        Retrieves relative paths of all files analyzed by the Language Server.

        This is slow, as it finds all files by finding all symbols.

        This seems to be the only way, the LSP does not provide any endpoints for listing project files."""
        if not self.server_started:
            self.logger.log(
                "request_parsed_files called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")
        # TODO: this worked in jedi, but pyright and basedpyright return nothing...
        # I don't know why
        # params = LSPTypes.WorkspaceSymbolParams(query="")  # Empty query returns all symbols
        # symbols = await self.server.send.workspace_symbol(params) or []

        # Thus, instead of calling all symbols, we hack this and use the symbol tree instead, which
        # seems to work in all these language servers
        # walk through all children recursively, find all symbols of type Module and collect their relative paths
        roots = await self.request_full_symbol_tree()
        paths = []
        def collect_module_files(symbol):
            if symbol["kind"] == multilspy_types.SymbolKind.File:
                assert "location" in symbol
                paths.append(symbol["location"]["relativePath"])

            elif symbol["kind"] == multilspy_types.SymbolKind.Package:
                for child in symbol["children"]:
                    collect_module_files(child)

        for root in roots:
            collect_module_files(root)

        return paths


    async def search_files_for_pattern(
        self,
        pattern: re.Pattern | str,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
    ) -> list[MatchedConsecutiveLines]:
        """
        Search for a pattern across all files analyzed by the Language Server.

        :param pattern: Regular expression pattern to search for, either as a compiled Pattern or string
        :param context_lines_before: Number of lines of context to include before each match
        :param context_lines_after: Number of lines of context to include after each match
        :param paths_include_glob: Glob pattern to filter which files to include in the search
        :param paths_exclude_glob: Glob pattern to filter which files to exclude from the search. Takes precedence over paths_include_glob.
        :return: List of matched consecutive lines with context
        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        relative_file_paths = await self.request_parsed_files()
        return search_files(
            relative_file_paths,
            pattern,
            file_reader=self.retrieve_full_file_content,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            paths_include_glob=paths_include_glob,
            paths_exclude_glob=paths_exclude_glob
        )

    async def request_referencing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_imports: bool = True,
        include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
    ) -> List[multilspy_types.UnifiedSymbolInformation]:
        """
        Finds all symbols that reference the symbol at the given location.
        This is similar to request_references but filters to only include symbols
        (functions, methods, classes, etc.) that reference the target symbol.

        :param relative_file_path: The relative path to the file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column number.
        :param include_imports: whether to also include imports as references.
            Unfortunately, the LSP does not have an import type, so the references corresponding to imports
            will not be easily distinguishable from definitions.
        :param include_self: whether to include the references that is the "input symbol" itself.
            Only has an effect if the relative_file_path, line and column point to a symbol, for example a definition.
        :param include_body: whether to include the body of the symbols in the result.
        :param include_file_symbols: whether to include references that are file symbols. This
            is often a fallback mechanism for when the reference cannot be resolved to a symbol.
        :return: List of symbols that reference the target symbol.
        """
        if not self.server_started:
            self.logger.log(
                "request_referencing_symbols called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")

        # First, get all references to the symbol
        references = await self.request_references(relative_file_path, line, column)
        if not references:
            return []

        # For each reference, find the containing symbol
        result = []
        incoming_symbol = None
        for ref in references:
            ref_path = ref["relativePath"]
            ref_line = ref["range"]["start"]["line"]
            ref_col = ref["range"]["start"]["character"]

            with self.open_file(ref_path) as file_data:
                # Get the containing symbol for this reference
                containing_symbol = await self.request_containing_symbol(
                    ref_path, ref_line, ref_col, include_body=include_body
                )
                if containing_symbol is None:
                    # TODO: HORRIBLE HACK! I don't know how to do it better for now...
                    # THIS IS BOUND TO BREAK IN MANY CASES! IT IS ALSO SPECIFIC TO PYTHON!
                    # Background:
                    # When a variable is used to change something, like
                    #
                    # instance = MyClass()
                    # instance.status = "new status"
                    #
                    # we can't find the containing symbol for the reference to `status`
                    # since there is no container on the line of the reference
                    # The hack is to try to find a variable symbol in the containing module
                    # by using the text of the reference to find the variable name (In a very heuristic way)
                    # and then look for a symbol with that name and kind Variable
                    ref_text = file_data.contents.split("\n")[ref_line]
                    if "." in ref_text:
                        containing_symbol_name = ref_text.split(".")[0]
                        all_symbols, _ = await self.request_document_symbols(ref_path)
                        for symbol in all_symbols:
                            if symbol["name"] == containing_symbol_name and symbol["kind"] == multilspy_types.SymbolKind.Variable:
                                containing_symbol = copy(symbol)
                                containing_symbol["location"] = ref
                                containing_symbol["range"] = ref["range"]
                                break

                # We failed retrieving the symbol, falling back to creating a file symbol
                if containing_symbol is None and include_file_symbols:
                    self.logger.log(
                        f"Could not find containing symbol for {ref_path}:{ref_line}:{ref_col}. Returning file symbol instead",
                        logging.WARNING
                    )
                    fileRange = self._get_range_from_file_content(file_data.contents)
                    location = multilspy_types.Location(
                        uri=str(pathlib.Path(os.path.join(self.repository_root_path, ref_path)).as_uri()),
                        range=fileRange,
                        absolutePath=str(os.path.join(self.repository_root_path, ref_path)),
                        relativePath=ref_path,
                    )
                    name = os.path.splitext(os.path.basename(ref_path))[0]

                    if include_body:
                        body = self.retrieve_full_file_content(ref_path)
                    else:
                        body = ""

                    containing_symbol = multilspy_types.UnifiedSymbolInformation(
                        kind=multilspy_types.SymbolKind.File,
                        range=fileRange,
                        selectionRange=fileRange,
                        location=location,
                        name=name,
                        children=[],
                        body=body,
                    )
                if containing_symbol is None or not include_file_symbols and containing_symbol["kind"] == multilspy_types.SymbolKind.File:
                    continue

                assert "location" in containing_symbol
                assert "selectionRange" in containing_symbol

                # Checking for self-reference
                if (
                    containing_symbol["location"]["relativePath"] == relative_file_path
                    and containing_symbol["selectionRange"]["start"]["line"] == ref_line
                    and containing_symbol["selectionRange"]["start"]["character"] == ref_col
                ):
                    incoming_symbol = containing_symbol
                    if include_self:
                        result.append(containing_symbol)
                        continue
                    else:
                        self.logger.log(f"Found self-reference for {incoming_symbol['name']}, skipping it since {include_self=}", logging.DEBUG)
                        continue

                # checking whether reference is an import
                # This is neither really safe nor elegant, but if we don't do it,
                # there is no way to distinguish between definitions and imports as import is not a symbol-type
                # and we get the type referenced symbol resulting from imports...
                if (not include_imports \
                    and incoming_symbol is not None \
                    and containing_symbol["name"] == incoming_symbol["name"] \
                    and containing_symbol["kind"] == incoming_symbol["kind"] \
                ):
                    self.logger.log(
                        f"Found import of referenced symbol {incoming_symbol['name']}" 
                        f"in {containing_symbol['location']['relativePath']}, skipping",
                        logging.DEBUG
                    )
                    continue

                result.append(containing_symbol)

        return result

    async def request_containing_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: Optional[int] = None,
        strict: bool = False,
        include_body: bool = False,
    ) -> multilspy_types.UnifiedSymbolInformation | None:
        """
        Finds the first symbol containing the position for the given file.
        For Python, container symbols are considered to be those with kinds corresponding to
        functions, methods, or classes (typically: Function (12), Method (6), Class (5)).

        The method operates as follows:
          - Request the document symbols for the file.
          - Filter symbols to those that start at or before the given line.
          - From these, first look for symbols whose range contains the (line, column).
          - If one or more symbols contain the position, return the one with the greatest starting position
            (i.e. the innermost container).
          - If none (strictly) contain the position, return the symbol with the greatest starting position
            among those above the given line.
          - If no container candidates are found, return None.

        :param relative_file_path: The relative path to the Python file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column (also called character). If not passed, the lookup will be based
            only on the line.
        :param strict: If True, the position must be strictly within the range of the symbol.
            Setting to True is useful for example for finding the parent of a symbol, as with strict=False,
            and the line pointing to a symbol itself, the containing symbol will be the symbol itself
            (and not the parent).
        :param include_body: Whether to include the body of the symbol in the result.
        :return: The container symbol (if found) or None.
        """
        # checking if the line is empty, unfortunately ugly and duplicating code, but I don't want to refactor
        with self.open_file(relative_file_path):
            absolute_file_path = str(
                PurePath(self.repository_root_path, relative_file_path)
            )
            content = FileUtils.read_file(self.logger, absolute_file_path)
            if content.split("\n")[line].strip() == "":
                self.logger.log(
                    f"Passing empty lines to request_container_symbol is currently not supported, {relative_file_path=}, {line=}",
                    logging.ERROR,
                )
                return None

        symbols, _ = await self.request_document_symbols(relative_file_path)

        # make jedi and pyright api compatible
        # the former has no location, the later has no range
        # we will just always add location of the desired format to all symbols
        for symbol in symbols:
            if "location" not in symbol:
                range = symbol["range"]
                location = multilspy_types.Location(
                    uri=f"file:/{absolute_file_path}",
                    range=range,
                    absolutePath=absolute_file_path,
                    relativePath=relative_file_path,
                )
                symbol["location"] = location
            else:
                location = symbol["location"]
                assert "range" in location
                location["absolutePath"] = absolute_file_path
                location["relativePath"] = relative_file_path
                location["uri"] = Path(absolute_file_path).as_uri()

        # Allowed container kinds, currently only for Python
        container_symbol_kinds = {
            multilspy_types.SymbolKind.Method,
            multilspy_types.SymbolKind.Function,
            multilspy_types.SymbolKind.Class
        }

        def is_position_in_range(line: int, range_d: multilspy_types.Range) -> bool:
            start = range_d["start"]
            end = range_d["end"]

            column_condition = True
            if strict:
                line_condition = end["line"] >= line > start["line"]
                if column is not None:
                    column_condition = column > start["character"]
            else:
                line_condition = end["line"] >= line >= start["line"]
                if column is not None:
                    column_condition = column >= start["character"]
            return line_condition and column_condition

        # Only consider containers that are not one-liners (otherwise we may get imports)
        candidate_containers = [
            s for s in symbols if s["kind"] in container_symbol_kinds and s["location"]["range"]["start"]["line"] != s["location"]["range"]["end"]["line"]
        ]
        var_containers = [
            s for s in symbols if s["kind"] == multilspy_types.SymbolKind.Variable
        ]
        candidate_containers.extend(var_containers)

        if not candidate_containers:
            return None

        # From the candidates, find those whose range contains the given position.
        containing_symbols = []
        for symbol in candidate_containers:
            s_range = symbol["location"]["range"]
            if not is_position_in_range(line, s_range):
                continue
            containing_symbols.append(symbol)

        if containing_symbols:
            # Return the one with the greatest starting position (i.e. the innermost container).
            containing_symbol = max(containing_symbols, key=lambda s: s["location"]["range"]["start"]["line"])
            if include_body:
                containing_symbol["body"] = self.retrieve_symbol_body(containing_symbol)
            return containing_symbol
        else:
            return None

    async def request_container_of_symbol(self, symbol: multilspy_types.UnifiedSymbolInformation, include_body: bool = False) -> multilspy_types.UnifiedSymbolInformation | None:
        """
        Finds the container of the given symbol if there is one.

        :param symbol: The symbol to find the container of.
        :param include_body: whether to include the body of the symbol in the result.
        """
        assert "location" in symbol
        return await self.request_containing_symbol(
            symbol["location"]["relativePath"],
            symbol["location"]["range"]["start"]["line"],
            symbol["location"]["range"]["start"]["character"],
            strict=True,
            include_body=include_body,
        )

    async def request_defining_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_body: bool = False,
    ) -> Optional[multilspy_types.UnifiedSymbolInformation]:
        """
        Finds the symbol that defines the symbol at the given location.

        This method first finds the definition of the symbol at the given position,
        then retrieves the full symbol information for that definition.

        :param relative_file_path: The relative path to the file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column number.
        :param include_body: whether to include the body of the symbol in the result.
        :return: The symbol information for the definition, or None if not found.
        """
        if not self.server_started:
            self.logger.log(
                "request_defining_symbol called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")

        # Get the definition location(s)
        definitions = await self.request_definition(relative_file_path, line, column)
        if not definitions:
            return None

        # Use the first definition location
        definition = definitions[0]
        def_path = definition["relativePath"]
        def_line = definition["range"]["start"]["line"]
        def_col = definition["range"]["start"]["character"]

        # Find the symbol at or containing this location
        defining_symbol = await self.request_containing_symbol(
            def_path, def_line, def_col, strict=False, include_body=include_body
        )

        return defining_symbol

    @property
    def _cache_path(self) -> Path:
        return Path(self.repository_root_path) / ".serena" / "cache" / "document_symbols_cache.pkl"

    def save_cache(self):
        if self._cache_has_changed:
            self.logger.log(f"Saving updated document symbols cache to {self._cache_path}", logging.INFO)
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(self._cache_path, "wb") as f:
                    pickle.dump(self._document_symbols_cache, f)
            except Exception as e:
                self.logger.log(
                        f"Failed to save document symbols cache to {self._cache_path}: {e}. "
                        "Note: this may have resulted in a corrupted cache file.", logging.ERROR
                    )

    def load_cache(self):
        if not self._cache_path.exists():
            return
        self.logger.log(f"Loading document symbols cache from {self._cache_path}", logging.INFO)
        with open(self._cache_path, "rb") as f:
            try:
                self._document_symbols_cache = pickle.load(f)
            except Exception as e:
                # cache often becomes corrupt, so just skip loading it
                self.logger.log(
                        f"Failed to load document symbols cache from {self._cache_path}: {e}. Possible cause: the cache file is corrupted. " 
                        "Check for any errors related to saving the cache in the logs.",
                        logging.ERROR
                    )


    async def request_workspace_symbol(self, query: str) -> Union[List[multilspy_types.UnifiedSymbolInformation], None]:
        """
        Raise a [workspace/symbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_symbol) request to the Language Server
        to find symbols across the whole workspace. Wait for the response and return the result.

        :param query: The query string to filter symbols by

        :return Union[List[multilspy_types.UnifiedSymbolInformation], None]: A list of matching symbols
        """
        response = await self.server.send.workspace_symbol({"query": query})
        if response is None:
            return None

        assert isinstance(response, list)

        ret: List[multilspy_types.UnifiedSymbolInformation] = []
        for item in response:
            assert isinstance(item, dict)

            assert LSPConstants.NAME in item
            assert LSPConstants.KIND in item
            assert LSPConstants.LOCATION in item

            ret.append(multilspy_types.UnifiedSymbolInformation(**item))

        return ret

@ensure_all_methods_implemented(LanguageServer)
class SyncLanguageServer:
    """
    The SyncLanguageServer class provides a language agnostic interface to the Language Server Protocol.
    It is used to communicate with Language Servers of different programming languages.
    """

    def __init__(self, language_server: LanguageServer, timeout: Optional[int] = None):
        """
        :param language_server: the async language server being wrapped
        :param timeout: the timeout, in seconds, to use for requests to the language server.
        """
        self.language_server = language_server
        self.loop = None
        self.loop_thread = None
        self.timeout = timeout

        self._server_context = None

        # start project folder watchdog
        from .watchdog import ProjectFolderWatchdog
        self.watchdog = ProjectFolderWatchdog(self)

    @classmethod
    def create(
        cls, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str, add_gitignore_content_to_config=True,
        timeout: Optional[int] = None
    ) -> "SyncLanguageServer":
        """
        Creates a language specific LanguageServer instance based on the given configuration, and appropriate settings for the programming language.

        If language is Java, then ensure that jdk-17.0.6 or higher is installed, `java` is in PATH, and JAVA_HOME is set to the installation directory.

        :param repository_root_path: The root path of the repository (must be absolute).
        :param config: The Multilspy configuration.
        :param logger: The logger to use.
        :param add_gitignore_content_to_config: whether to add the content of the .gitignore file (if any found) to the config, so that
            the paths ignored there are also ignored by the language server
        :param timeout: the timeout, in seconds, to use for requests; if None, use no timeout

        :return SyncLanguageServer: A language specific LanguageServer instance.
        """
        return SyncLanguageServer(LanguageServer.create(config, logger, repository_root_path, add_gitignore_content_to_config=add_gitignore_content_to_config), timeout=timeout)

    @contextmanager
    def open_file(self, relative_file_path: str) -> Iterator[LSPFileBuffer]:
        """
        Open a file in the Language Server. This is required before making any requests to the Language Server.

        :param relative_file_path: The relative path of the file to open.
        """
        with self.language_server.open_file(relative_file_path) as file_buffer:
            yield file_buffer

    def insert_text_at_position(
        self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str
    ) -> multilspy_types.Position:
        """
        Insert text at the given line and column in the given file and return 
        the updated cursor position after inserting the text.

        :param relative_file_path: The relative path of the file to open.
        :param line: The line number at which text should be inserted.
        :param column: The column number at which text should be inserted.
        :param text_to_be_inserted: The text to insert.
        """
        return self.language_server.insert_text_at_position(relative_file_path, line, column, text_to_be_inserted)

    def delete_text_between_positions(
        self,
        relative_file_path: str,
        start: multilspy_types.Position,
        end: multilspy_types.Position,
    ) -> str:
        """
        Delete text between the given start and end positions in the given file and return the deleted text.
        """
        return self.language_server.delete_text_between_positions(relative_file_path, start, end)
   
    @contextmanager
    def start_server(self) -> Iterator["SyncLanguageServer"]:
        """
        Starts the language server process and connects to it.

        :return: None
        """
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.loop_thread.start()
        ctx = self.language_server.start_server()
        asyncio.run_coroutine_threadsafe(ctx.__aenter__(), loop=self.loop).result()
        yield self
        asyncio.run_coroutine_threadsafe(ctx.__aexit__(None, None, None), loop=self.loop).result()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join()

    def request_definition(self, file_path: str, line: int, column: int) -> List[multilspy_types.Location]:
        """
        Raise a [textDocument/definition](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_definition) request to the Language Server
        for the symbol at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbol for which definition should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return List[multilspy_types.Location]: A list of locations where the symbol is defined
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_definition(file_path, line, column), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_references(self, file_path: str, line: int, column: int) -> List[multilspy_types.Location]:
        """
        Raise a [textDocument/references](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_references) request to the Language Server
        to find references to the symbol at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbol for which references should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return List[multilspy_types.Location]: A list of locations where the symbol is referenced
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_references(file_path, line, column), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_references_with_content(
        self, relative_file_path: str, line: int, column: int, context_lines_before: int = 0, context_lines_after: int = 0
    ) -> List[MatchedConsecutiveLines]:
        """
        Like request_references, but returns the content of the lines containing the references, not just the locations.

        :param relative_file_path: The relative path of the file that has the symbol for which references should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol
        :param context_lines_before: The number of lines to include in the context before the line containing the reference
        :param context_lines_after: The number of lines to include in the context after the line containing the reference

        :return: A list of MatchedConsecutiveLines objects, one for each reference.
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_references_with_content(relative_file_path, line, column, context_lines_before, context_lines_after), self.loop
        ).result()
        return result

    def request_completions(
        self, relative_file_path: str, line: int, column: int, allow_incomplete: bool = False
    ) -> List[multilspy_types.CompletionItem]:
        """
        Raise a [textDocument/completion](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_completion) request to the Language Server
        to find completions at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbol for which completions should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return List[multilspy_types.CompletionItem]: A list of completions
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_completions(relative_file_path, line, column, allow_incomplete),
            self.loop,
        ).result(timeout=self.timeout)
        return result

    def request_document_symbols(self, relative_file_path: str, include_body: bool = False) -> Tuple[List[multilspy_types.UnifiedSymbolInformation], List[multilspy_types.UnifiedSymbolInformation]]:
        """
        Raise a [textDocument/documentSymbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_documentSymbol) request to the Language Server
        to find symbols in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbols
        :param include_body: whether to include the body of the symbols in the result.
        :return: A list of symbols in the file, and a list of root symbols that represent the tree structure of the symbols. Each symbol in hierarchy starting from the roots has a children attribute.
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_document_symbols(relative_file_path, include_body), self.loop
        ).result()
        return result

    def request_full_symbol_tree(self, within_relative_path: str | None = None, include_body: bool = False) -> List[multilspy_types.UnifiedSymbolInformation]:
        """
        Will go through all files in the project and build a tree of symbols. Note: this may be slow the first time it is called.

        For each file, a symbol of kind Module (3) will be created. For directories, a symbol of kind Package (4) will be created.
        All symbols will have a children attribute, thereby representing the tree structure of all symbols in the project
        that are within the repository.
        Will ignore directories starting with '.', language-specific defaults
        and user-configured directories (e.g. from .gitignore).

        :param within_relative_path: pass a relative path to only consider symbols within this path.
            If a file is passed, only the symbols within this file will be considered.
            If a directory is passed, all files within this directory will be considered.
            If None, the entire codebase will be considered.
        :param include_body: whether to include the body of the symbols in the result.

        :return: A list of root symbols representing the top-level packages/modules in the project.
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_full_symbol_tree(within_relative_path, include_body), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_dir_overview(self, relative_dir_path: str) -> dict[str, list[tuple[str, multilspy_types.SymbolKind, int, int]]]:
        """
        An overview of the given directory.

        Maps relative paths of all contained files to info about top-level symbols in the file
        (name, kind, line, column).
        """
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_dir_overview(relative_dir_path), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_document_overview(self, relative_file_path: str) -> list[tuple[str, multilspy_types.SymbolKind, int, int]]:
        """
        An overview of the given file.

        Returns the list of tuples (name, kind, line, column) of all top-level symbols in the file.
        """
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_document_overview(relative_file_path), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_overview(self, within_relative_path: str) -> dict[str, list[tuple[str, multilspy_types.SymbolKind, int, int]]]:
        """
        An overview of all symbols in the given file or directory.

        :param within_relative_path: the relative path to the file or directory to get the overview of.
        :return: A mapping of all relative paths analyzed to lists of tuples (name, kind, line, column) of all top-level symbols in the corresponding file.
        """
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_overview(within_relative_path), self.loop
        ).result()
        return result

    def request_hover(self, relative_file_path: str, line: int, column: int) -> Union[multilspy_types.Hover, None]:
        """
        Raise a [textDocument/hover](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_hover) request to the Language Server
        to find the hover information at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the hover information
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return None
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_hover(relative_file_path, line, column), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_workspace_symbol(self, query: str) -> Union[List[multilspy_types.UnifiedSymbolInformation], None]:
        """
        Raise a [workspace/symbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_symbol) request to the Language Server
        to find symbols across the whole workspace. Wait for the response and return the result.

        :param query: The query string to filter symbols by

        :return Union[List[multilspy_types.UnifiedSymbolInformation], None]: A list of matching symbols
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_workspace_symbol(query), self.loop
        ).result(timeout=self.timeout)
        return result

    # ----------------------------- FROM HERE ON MODIFICATIONS BY MISCHA --------------------

    def retrieve_symbol_body(self, symbol: multilspy_types.UnifiedSymbolInformation) -> str:
        """
        Load the body of the given symbol. If the body is already contained in the symbol, just return it.

        :param symbol: The symbol to retrieve the body of.
        :return: The body of the symbol.
        """
        return self.language_server.retrieve_symbol_body(symbol)

    def request_parsed_files(self) -> list[str]:
        """This is slow, as it finds all files by finding all symbols.

        This seems to be the only way, the LSP does not provide any endpoints for listing project files."""
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_parsed_files(), self.loop
        ).result()
        return result

    def request_referencing_symbols(
        self, relative_file_path: str, line: int, column: int,
        include_imports: bool = True, include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
    ) -> List[multilspy_types.UnifiedSymbolInformation]:
        """
        Finds all symbols that reference the symbol at the given location.
        This is similar to request_references but filters to only include symbols
        (functions, methods, classes, etc.) that reference the target symbol.

        :param relative_file_path: The relative path to the file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column number.
        :param include_imports: whether to also include imports as references.
            Unfortunately, the LSP does not have an import type, so the references corresponding to imports
            will not be easily distinguishable from definitions.
        :param include_self: whether to include the references that is the "input symbol" itself.
            Only has an effect if the relative_file_path, line and column point to a symbol, for example a definition.
        :param include_body: whether to include the body of the symbols in the result.
        :param include_file_symbols: whether to include references that are file symbols. This
            is often a fallback mechanism for when the reference cannot be resolved to a symbol.
        :return: List of symbols that reference the target symbol.
        """
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_referencing_symbols(
                relative_file_path,
                line,
                column,
                include_imports=include_imports,
                include_self=include_self,
                include_body=include_body,
                include_file_symbols=include_file_symbols,
            ),
            self.loop
        ).result(timeout=self.timeout)
        return result

    def request_containing_symbol(
        self, relative_file_path: str, line: int,
        column: Optional[int] = None, strict: bool = False,
        include_body: bool = False,
    ) -> multilspy_types.UnifiedSymbolInformation | None:
        """
        Finds the first symbol containing the position for the given file.
        For Python, container symbols are considered to be those with kinds corresponding to
        functions, methods, or classes (typically: Function (12), Method (6), Class (5)).

        The method operates as follows:
          - Request the document symbols for the file.
          - Filter symbols to those that start at or before the given line.
          - From these, first look for symbols whose range contains the (line, column).
          - If one or more symbols contain the position, return the one with the greatest starting position
            (i.e. the innermost container).
          - If none (strictly) contain the position, return the symbol with the greatest starting position
            among those above the given line.
          - If no container candidates are found, return None.

        :param relative_file_path: The relative path to the Python file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column (also called character). If not passed, the lookup will be based
            only on the line.
        :param strict: If True, the position must be strictly within the range of the symbol.
            Setting to true is useful for example for finding the parent of a symbol, as with strict=False,
            and the line pointing to a symbol itself, the containing symbol will be the symbol itself
            (and not the parent).
        :param include_body: whether to include the body of the symbol in the result.
        :return: The container symbol (if found) or None.
        """
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_containing_symbol(relative_file_path, line, column=column, strict=strict, include_body=include_body), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_container_of_symbol(self, symbol: multilspy_types.UnifiedSymbolInformation, include_body: bool = False) -> multilspy_types.UnifiedSymbolInformation | None:
        """
        Finds the container of the given symbol if there is one.

        :param symbol: The symbol to find the container of.
        :param include_body: whether to include the body of the symbol in the result.
        """
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_container_of_symbol(symbol, include_body=include_body), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_defining_symbol(
        self, relative_file_path: str, line: int, column: int,
        include_body: bool = False,
    ) -> Optional[multilspy_types.UnifiedSymbolInformation]:
        """
        Finds the symbol that defines the symbol at the given location.

        This method first finds the definition of the symbol at the given position,
        then retrieves the full symbol information for that definition.

        :param relative_file_path: The relative path to the file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column number.
        :param include_body: whether to include the body of the symbol in the result.
        :return: The symbol information for the definition, or None if not found.
        """
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_defining_symbol(relative_file_path, line, column, include_body=include_body), self.loop
        ).result(timeout=self.timeout)
        return result

    def retrieve_full_file_content(self, relative_file_path: str) -> str:
        """
        Retrieve the full content of the given file.
        """
        return self.language_server.retrieve_full_file_content(relative_file_path)

    def retrieve_content_around_line(self, relative_file_path: str, line: int, context_lines_before: int = 0, context_lines_after: int = 0) -> MatchedConsecutiveLines:
        """
        Retrieve the content of the given file around the given line.

        :param relative_file_path: The relative path of the file to retrieve the content from
        :param line: The line number to retrieve the content around
        :param context_lines_before: The number of lines to retrieve before the given line
        :param context_lines_after: The number of lines to retrieve after the given line
        :return MatchedConsecutiveLines: A container with the desired lines.
        """
        return self.language_server.retrieve_content_around_line(relative_file_path, line, context_lines_before, context_lines_after)

    def search_files_for_pattern(
        self,
        pattern: re.Pattern | str,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
    ) -> list[MatchedConsecutiveLines]:
        """
        Search for a pattern across all files analyzed by the Language Server.

        :param pattern: Regular expression pattern to search for, either as a compiled Pattern or string
        :param context_lines_before: Number of lines of context to include before each match
        :param context_lines_after: Number of lines of context to include after each match
        :param paths_include_glob: Glob pattern to filter which files to include in the search
        :param paths_exclude_glob: Glob pattern to filter which files to exclude from the search. Takes precedence over paths_include_glob.
        :return: List of matched consecutive lines with context
        """
        assert self.loop
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.search_files_for_pattern(pattern, context_lines_before, context_lines_after, paths_include_glob, paths_exclude_glob), self.loop
        ).result(timeout=self.timeout)
        return result

    def start(self) -> "SyncLanguageServer":
        """
        Starts the language server process and connects to it. Call shutdown when ready.

        :return: self for method chaining
        """
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.loop_thread.start()
        self._server_context = self.language_server.start_server()
        asyncio.run_coroutine_threadsafe(self._server_context.__aenter__(), loop=self.loop).result()
        return self

    def is_running(self) -> bool:
        """
        Check if the language server is running.
        """
        return self.loop is not None and self.loop_thread is not None and self.loop_thread.is_alive()

    def stop(self) -> None:
        """
        Shuts down the language server process and cleans up resources.

        If the language server is not running, this method will log a warning and do nothing.
        """
        del self.watchdog

        if not self.is_running():
            self.language_server.logger.log("Language server not running, skipping shutdown.", logging.INFO)
            return

        assert self.loop
        asyncio.run_coroutine_threadsafe(self._server_context.__aexit__(None, None, None), loop=self.loop).result()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join()
        self.loop = None
        self.loop_thread = None
        self.save_cache()

    def save_cache(self):
        """
        Save the cache to a file.
        """
        self.language_server.save_cache()

    def load_cache(self):
        """
        Load the cache from a file.
        """
        self.language_server.load_cache()

    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        A language-specific condition for directories that should be ignored always. For example, venv
        in Python and node_modules in JS/TS should be ignored always.
        """
        return self.language_server.is_ignored_dirname(dirname)

    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True, check_existence: bool = True) -> bool:
        """
        Whether the given path should be ignored.
        """
        return self.language_server.is_ignored_path(relative_path, ignore_unsupported_files=ignore_unsupported_files,
            check_existence=check_existence)

    def get_ignore_spec(self) -> pathspec.PathSpec:
        """Returns the pathspec matcher for the paths that were configured to be ignored through
        the multilspy config file and the .gitignore file.

        This is is a subset of the full language-specific ignore spec that determines
        which files are relevant for the language server.

        This matcher is useful for operations outside of the language server,
        such as when searching for relevant non-language files in the project.
        """
        return self.language_server.get_ignore_spec()
