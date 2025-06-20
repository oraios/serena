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
import threading
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from copy import copy
from pathlib import Path, PurePath
import time
from typing import AsyncIterator, Dict, Iterator, List, Optional, Tuple, Union, cast

import pathspec
import tqdm

from . import multilspy_types
from .lsp_protocol_handler import lsp_types as LSPTypes
from .lsp_protocol_handler.lsp_constants import LSPConstants
from .lsp_protocol_handler.lsp_types import Definition, DefinitionParams, LocationLink, SymbolKind
from .lsp_protocol_handler.server import (
    Error,
    LanguageServerHandler,
    ProcessLaunchInfo,
    StringDict,
)
from .multilspy_config import Language, MultilspyConfig
from .multilspy_exceptions import MultilspyException
from .multilspy_logger import MultilspyLogger
from .multilspy_utils import FileUtils, PathUtils, TextUtils
from .type_helpers import ensure_all_methods_implemented
from .lsp_protocol_handler import lsp_types

# Serena dependencies
# We will need to watch out for circular imports, but it's probably better to not
# move all generic util code from serena into multilspy.
# It does however make sense to integrate many text-related utils into the language server
# since it caches (in-memory) file contents, so we can avoid reading from disk.
# Moreover, the way we want to use the language server (for retrieving actual content),
# it makes sense to have more content-related utils directly in it.
from serena.text_utils import LineType, MatchedConsecutiveLines, TextLine, search_files



GenericDocumentSymbol = Union[LSPTypes.DocumentSymbol, LSPTypes.SymbolInformation, multilspy_types.UnifiedSymbolInformation]

@dataclasses.dataclass(kw_only=True)
class ReferenceInSymbol:
    """A symbol retrieved when requesting reference to a symbol, together with the location of the reference"""
    symbol: multilspy_types.UnifiedSymbolInformation
    line: int
    character: int
    
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
    def create(cls, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str) -> "LanguageServer":
        """
        Creates a language specific LanguageServer instance based on the given configuration, and appropriate settings for the programming language.

        If language is Java, then ensure that jdk-17.0.6 or higher is installed, `java` is in PATH, and JAVA_HOME is set to the installation directory.
        If language is JS/TS, then ensure that node (v18.16.0 or higher) is installed and in PATH.

        :param repository_root_path: The root path of the repository.
        :param config: The Multilspy configuration.
        :param logger: The logger to use.
        :return LanguageServer: A language specific LanguageServer instance.
        """
        if config.code_language == Language.PYTHON:
            from multilspy.language_servers.pyright_language_server.pyright_server import (
                PyrightServer,
            )

            return PyrightServer(config, logger, repository_root_path)
            # It used to be jedi, but pyright is a bit faster, and also more actively maintained
            # Keeping the previous code for reference
            # from multilspy.language_servers.jedi_language_server.jedi_server import (
            #     JediServer,
            # )

            # return JediServer(config, logger, repository_root_path)
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
        elif config.code_language == Language.PHP:
            from multilspy.language_servers.intelephense.intelephense import Intelephense

            return Intelephense(config, logger, repository_root_path)
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
        self.repository_root_path: str = repository_root_path
        self.logger.log(f"Creating language server instance for {repository_root_path=} with {language_id=} and process launch info: {process_launch_info}", logging.DEBUG)
        
        self.language_id = language_id
        self.open_file_buffers: Dict[str, LSPFileBuffer] = {}
        self.language = Language(language_id)
        
        # load cache first to prevent any racing conditions due to asyncio stuff
        self._document_symbols_cache:  dict[str, Tuple[str, Tuple[List[multilspy_types.UnifiedSymbolInformation], List[multilspy_types.UnifiedSymbolInformation]]]] = {}
        """Maps file paths to a tuple of (file_content_hash, result_of_request_document_symbols)"""
        self._cache_lock = threading.Lock()
        self._cache_has_changed: bool = False
        self.load_cache()

        self.server_started = False
        self.completions_available = asyncio.Event()
        if config.trace_lsp_communication:
            def logging_fn(source: str, target: str, msg: StringDict | str):
                self.logger.log(f"LSP: {source} -> {target}: {str(msg)[:90]}...", self.logger.logger.level)
        else:
            logging_fn = None
            

        # cmd is obtained from the child classes, which provide the language specific command to start the language server
        # LanguageServerHandler provides the functionality to start the language server and communicate with it
        self.logger.log(f"Creating language server instance with {language_id=} and process launch info: {process_launch_info}", logging.DEBUG)
        self.server = LanguageServerHandler(
            process_launch_info,
            logger=logging_fn,
            start_independent_lsp_process=config.start_independent_lsp_process,
        )


        # Set up the pathspec matcher for the ignored paths
        # for all absolute paths in ignored_paths, convert them to relative paths
        processed_patterns = []
        for pattern in set(config.ignored_paths):
            # Normalize separators (pathspec expects forward slashes)
            pattern = pattern.replace(os.path.sep, '/')
            processed_patterns.append(pattern)
        self.logger.log(f"Processing {len(processed_patterns)} ignored paths from the config", logging.DEBUG)

        # Create a pathspec matcher from the processed patterns
        self._ignore_spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern,
            processed_patterns
        )

    def get_ignore_spec(self) -> pathspec.PathSpec:
        """Returns the pathspec matcher for the paths that were configured to be ignored through
        the multilspy config.

        This is is a subset of the full language-specific ignore spec that determines
        which files are relevant for the language server.

        This matcher is useful for operations outside of the language server,
        such as when searching for relevant non-language files in the project.
        """
        return self._ignore_spec

    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True) -> bool:
        """
        Determine if a path should be ignored based on file type
        and ignore patterns.

        :param relative_path: Relative path to check
        :param ignore_unsupported_files: whether files that are not supported source files should be ignored

        :return: True if the path should be ignored, False otherwise
        """
        abs_path = os.path.join(self.repository_root_path, relative_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File {abs_path} not found, the ignore check cannot be performed")

        # Check file extension if it's a file
        is_file = os.path.isfile(abs_path)
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
        if self.get_ignore_spec().match_file(normalized_path):
            return True

        return False
    
    async def _shutdown(self, timeout: float = 5.0):
        """
        A robust shutdown process designed to terminate cleanly on all platforms, including Windows,
        by explicitly closing all I/O pipes.
        """
        if not self.server.is_running():
            self.logger.log("Server process not running, skipping shutdown.", logging.DEBUG)
            return

        self.logger.log(f"Initiating final robust shutdown with a {timeout}s timeout...", logging.INFO)
        process = self.server.process
        reader_tasks = list(self.server.tasks.values())

        # --- Main Shutdown Logic ---
        try:
            # Stage 1: Graceful Termination Request
            # Send LSP shutdown and close stdin to signal no more input.
            try:
                await asyncio.wait_for(self.server.shutdown(), timeout=2.0)
                if process.stdin and not process.stdin.is_closing():
                    process.stdin.close()
            except Exception:
                pass # Ignore errors here, we are proceeding to terminate anyway.

            # Stage 2: Terminate and Concurrently Drain stdout/stderr
            process.terminate()
            
            # Wait for the process to exit AND for the output pipes to be drained.
            # The reader tasks will exit when they hit EOF.
            await asyncio.wait_for(
                asyncio.gather(process.wait(), *reader_tasks),
                timeout=timeout - 2.0
            )
            self.logger.log("Process terminated and output pipes drained.", logging.INFO)

        except asyncio.TimeoutError:
            # Stage 3: Forceful Kill
            self.logger.log("Graceful termination failed. Forcefully killing process...", logging.WARNING)
            if self.server.is_running():
                try:
                    process.kill()
                    # Wait for the killed process to be reaped by the OS.
                    await process.wait()
                except Exception as e:
                    self.logger.log(f"Error during forceful kill: {e}", logging.ERROR)
        
        except Exception as e:
            self.logger.log(f"An unexpected error occurred during shutdown logic: {e}", logging.ERROR)

        finally:
            # === STAGE 4: EXPLICIT TASK & PIPE CLEANUP ===
            self.logger.log("Performing final task cancellation and pipe handle cleanup...", logging.DEBUG)
            
            # 1. Cancel any lingering reader tasks.
            for task in reader_tasks:
                if not task.done():
                    task.cancel()
            # Wait for cancellations to complete.
            await asyncio.gather(*reader_tasks, return_exceptions=True)
            self.server.tasks = {}

            # 2. Explicitly close each pipe to release OS handles.
            for pipe in [process.stdin, process.stdout, process.stderr]:
                if pipe and hasattr(pipe, 'is_closing') and not pipe.is_closing():
                    try:
                        pipe.close()
                    except Exception:
                        pass
            
            # 3. Null out the process object in the handler.
            self.server.process = None
            self.logger.log("Shutdown sequence fully finished.", logging.DEBUG)

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["LanguageServer"]:
        """
        Starts the Language Server and yields the LanguageServer instance.
        """
        self.server_started = True
        try:
            yield self
        finally:
            self.server_started = False
            await self._shutdown()
    
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

        new_contents, new_l, new_c = TextUtils.insert_text_at_position(file_buffer.contents, line, column, text_to_be_inserted)
        file_buffer.contents = new_contents
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
        new_contents, deleted_text = TextUtils.delete_text_between_positions(file_buffer.contents, start_line=start["line"], start_col=start["character"], end_line=end["line"], end_col=end["character"])
        file_buffer.contents = new_contents
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

    async def _send_definition_request(self, definition_params: DefinitionParams) -> Union[Definition, List[LocationLink], None]:
        return await self.server.send.definition(definition_params)
    
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
            definition_params = cast(DefinitionParams, {
                LSPConstants.TEXT_DOCUMENT: {
                    LSPConstants.URI: pathlib.Path(
                        str(PurePath(self.repository_root_path, relative_file_path))
                    ).as_uri()
                },
                LSPConstants.POSITION: {
                    LSPConstants.LINE: line,
                    LSPConstants.CHARACTER: column,
                },
            })
            response = await self._send_definition_request(definition_params)

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

    # Some LS cause problems with this, so the call is isolated from the rest to allow overriding in subclasses
    async def _send_references_request(self, relative_file_path: str, line: int, column: int) -> List[lsp_types.Location] | None:
        return await self.server.send.references(
            {
                "textDocument": {"uri": PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))},
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": False},
            }
        )

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
            try:
                response = await self._send_references_request(relative_file_path, line=line, column=column)
            except Exception as e:
                # Catch LSP internal error (-32603) and raise a more informative exception
                if isinstance(e, Error) and getattr(e, 'code', None) == -32603:
                    raise RuntimeError(
                        f"LSP internal error (-32603) when requesting references for {relative_file_path}:{line}:{column}. "
                        "This often occurs when requesting references for a symbol not referenced in the expected way. "
                    ) from e
                raise
        if response is None:
            return []

        ret: List[multilspy_types.Location] = []
        assert isinstance(response, list), f"Unexpected response from Language Server (expected list, got {type(response)}): {response}"
        for item in response:
            assert isinstance(item, dict), f"Unexpected response from Language Server (expected dict, got {type(item)}): {item}"
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
        return MatchedConsecutiveLines.from_file_contents(file_contents, line=line, context_lines_before=context_lines_before, context_lines_after=context_lines_after, source_file_path=relative_file_path)


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
            All symbols will have a location, a children, and a parent attribute,
            where the parent attribute is None for root symbols.
            Note that this is slightly different from the call to request_full_symbol_tree,
            where the parent attribute will be the file symbol which in turn may have a package symbol as parent.
            If you need a symbol tree that contains file symbols as well, you should use `request_full_symbol_tree` instead.
        """
        # TODO: it's kinda dumb to not use the cache if include_body is False after include_body was True once
        #   Should be fixed in the future, it's a small performance optimization
        cache_key = f"{relative_file_path}-{include_body}"
        with self.open_file(relative_file_path) as file_data:
            with self._cache_lock:
                file_hash_and_result = self._document_symbols_cache.get(cache_key)
                if file_hash_and_result is not None:
                    file_hash, result = file_hash_and_result
                    if file_hash == file_data.content_hash:
                        self.logger.log(f"Returning cached document symbols for {relative_file_path}", logging.DEBUG)
                        return result
                    else:
                        self.logger.log(f"Content for {relative_file_path} has changed. Will overwrite in-memory cache", logging.DEBUG)
                else:
                    self.logger.log(f"No cache hit for symbols with {include_body=} in {relative_file_path}", logging.DEBUG)

            self.logger.log(f"Requesting document symbols for {relative_file_path} from the Language Server", logging.DEBUG)
            response = await self.server.send.document_symbol(
                {
                    "textDocument": {
                        "uri": pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()
                    }
                }
            )
            self.logger.log(f"Received {len(response) if response is not None else None} document symbols for {relative_file_path} from the Language Server", logging.DEBUG)

        def turn_item_into_symbol_with_children(item: GenericDocumentSymbol):
            item = cast(multilspy_types.UnifiedSymbolInformation, item)
            absolute_path = os.path.join(self.repository_root_path, relative_file_path)
            
            # handle missing entries in location
            if "location" not in item:
                uri = pathlib.Path(absolute_path).as_uri()
                assert "range" in item
                tree_location = multilspy_types.Location(
                    uri=uri,
                    range=item['range'],
                    absolutePath=absolute_path,
                    relativePath=relative_file_path,
                )
                item['location'] = tree_location
            location = item["location"]
            if "absolutePath" not in location:
                location["absolutePath"] = absolute_path
            if "relativePath" not in location:
                location["relativePath"] = relative_file_path
            if include_body:
                item['body'] = self.retrieve_symbol_body(item)
            # handle missing selectionRange
            if "selectionRange" not in item:
                if "range" in item:
                    item["selectionRange"] = item["range"]
                else:
                    item["selectionRange"] = item["location"]["range"]
            children = item.get(LSPConstants.CHILDREN, [])
            for child in children:
                child["parent"] = item
            item[LSPConstants.CHILDREN] = children

        flat_all_symbol_list: List[multilspy_types.UnifiedSymbolInformation] = []
        assert isinstance(response, list), f"Unexpected response from Language Server: {response}"
        root_nodes: List[multilspy_types.UnifiedSymbolInformation] = []
        for root_item in response:
            if "range" not in root_item and "location" not in root_item:
                if root_item["kind"] in [SymbolKind.File, SymbolKind.Module]:
                    ...

            # mutation is more convenient than creating a new dict,
            # so we cast and rename the var after the mutating call to turn_item_into_symbol_with_children
            # which turned and item into a "symbol"
            turn_item_into_symbol_with_children(root_item)
            root_symbol = cast(multilspy_types.UnifiedSymbolInformation, root_item)
            root_symbol["parent"] = None
            
            root_nodes.append(root_symbol)
            assert isinstance(root_symbol, dict)
            assert LSPConstants.NAME in root_symbol
            assert LSPConstants.KIND in root_symbol

            if LSPConstants.CHILDREN in root_symbol:
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
                
                flat_all_symbol_list.extend(visit_tree_nodes_and_build_tree_repr(root_symbol))
            else:
                flat_all_symbol_list.append(multilspy_types.UnifiedSymbolInformation(**root_symbol))

        result = flat_all_symbol_list, root_nodes
        self.logger.log(f"Caching document symbols for {relative_file_path}", logging.DEBUG)
        with self._cache_lock:
            self._document_symbols_cache[cache_key] = (file_data.content_hash, result)
            self._cache_has_changed = True
        return result

    async def request_full_symbol_tree(self, within_relative_path: str | None = None, include_body: bool = False) -> List[multilspy_types.UnifiedSymbolInformation]:
        """
        Will go through all files in the project or within a relative path and build a tree of symbols. 
        Note: this may be slow the first time it is called, especially if `within_relative_path` is not used to restrict the search.

        For each file, a symbol of kind File (2) will be created. For directories, a symbol of kind Package (4) will be created.
        All symbols will have a children attribute, thereby representing the tree structure of all symbols in the project
        that are within the repository.
        All symbols except the root packages will have a parent attribute.
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
        async def process_directory(rel_dir_path: str) -> List[multilspy_types.UnifiedSymbolInformation]:
            abs_dir_path = self.repository_root_path if rel_dir_path == "." else os.path.join(self.repository_root_path, rel_dir_path)
            abs_dir_path = os.path.realpath(abs_dir_path)

            if self.is_ignored_path(str(Path(abs_dir_path).relative_to(self.repository_root_path))):
                self.logger.log(f"Skipping directory: {rel_dir_path}\n(because it should be ignored)", logging.DEBUG)
                return []

            result = []
            try:
                contained_dir_or_file_names = os.listdir(abs_dir_path)
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

            for contained_dir_or_file_name in contained_dir_or_file_names:
                contained_dir_or_file_abs_path = os.path.join(abs_dir_path, contained_dir_or_file_name)
                contained_dir_or_file_rel_path = str(Path(contained_dir_or_file_abs_path).resolve().relative_to(self.repository_root_path))
                if self.is_ignored_path(contained_dir_or_file_rel_path):
                    self.logger.log(f"Skipping item: {contained_dir_or_file_rel_path}\n(because it should be ignored)", logging.DEBUG)
                    continue

                if os.path.isdir(contained_dir_or_file_abs_path):
                    child_symbols = await process_directory(contained_dir_or_file_rel_path)
                    package_symbol["children"].extend(child_symbols)
                    for child in child_symbols:
                        child["parent"] = package_symbol
                        
                elif os.path.isfile(contained_dir_or_file_abs_path):
                    _, file_root_nodes = await self.request_document_symbols(contained_dir_or_file_rel_path, include_body=include_body)
                    
                    # Create file symbol, link with children
                    file_rel_path = str(Path(contained_dir_or_file_abs_path).resolve().relative_to(self.repository_root_path))
                    with self.open_file(file_rel_path) as file_data:
                        fileRange = self._get_range_from_file_content(file_data.contents)
                    file_symbol = multilspy_types.UnifiedSymbolInformation( # type: ignore
                        name=os.path.splitext(contained_dir_or_file_name)[0],
                        kind=multilspy_types.SymbolKind.File,
                        range=fileRange,
                        selectionRange=fileRange,
                        location=multilspy_types.Location(
                            uri=str(pathlib.Path(contained_dir_or_file_abs_path).as_uri()),
                            range=fileRange,
                            absolutePath=str(contained_dir_or_file_abs_path),
                            relativePath=str(Path(contained_dir_or_file_abs_path).resolve().relative_to(self.repository_root_path)),
                        ),
                        children=file_root_nodes,
                        parent=package_symbol,
                    )
                    for child in file_root_nodes:
                        child["parent"] = file_symbol

                    # Link file symbol with package
                    package_symbol["children"].append(file_symbol)

                    # TODO: Not sure if this is actually still needed given recent changes to relative path handling
                    def fix_relative_path(nodes: List[multilspy_types.UnifiedSymbolInformation]):
                        for node in nodes:
                            if "location" in node and "relativePath" in node["location"]:
                                path = Path(node["location"]["relativePath"])
                                if path.is_absolute():
                                    try:
                                        path = path.relative_to(self.repository_root_path)
                                        node["location"]["relativePath"] = str(path)
                                    except Exception:
                                        pass
                            if "children" in node:
                                fix_relative_path(node["children"])

                    fix_relative_path(file_root_nodes)

            return result

        # Start from the root or the specified directory
        start_rel_path = within_relative_path or "."
        return await process_directory(start_rel_path)

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
        result = []
        for root in document_roots:
            try:
                result.append(
                   ( root["name"],
                    root["kind"],
                    root["selectionRange"]["start"]["line"],
                    root["selectionRange"]["start"]["character"],)
                )
            except KeyError as e:
                raise KeyError(
                    f"Could not process symbol of name {root.get('name', 'unknown')} in {relative_file_path=}"
                ) from e
        return result

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
    
    async def request_signature_help(self, relative_file_path: str, line: int, column: int) -> Union[multilspy_types.SignatureHelp, None]:
        """
        Raise a [textDocument/signatureHelp](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_signatureHelp) request to the Language Server
        to find the signature help information at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the signature help information
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return: SignatureHelp object or None
        """
        with self.open_file(relative_file_path):
            response = await self.server.send.signature_help(
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

        return multilspy_types.SignatureHelp(**response)
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
        """Retrieves relative paths of all files analyzed by the Language Server."""
        if not self.server_started:
            self.logger.log(
                "request_parsed_files called before Language Server started",
                logging.ERROR,
            )
            raise MultilspyException("Language Server not started")
        rel_file_paths = []
        for root, dirs, files in os.walk(self.repository_root_path):
            dirs[:] = [d for d in dirs if not self.is_ignored_path(os.path.join(root, d))]
            for file in files:
                rel_file_path = os.path.relpath(os.path.join(root, file), start=self.repository_root_path)
                if not self.is_ignored_path(rel_file_path):
                    rel_file_paths.append(rel_file_path)
        return rel_file_paths

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
    ) -> List[ReferenceInSymbol]:
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
        :return: List of objects containing the symbol and the location of the reference.
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
                        result.append(ReferenceInSymbol(symbol=containing_symbol, line=ref_line, character=ref_col))
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

                result.append(ReferenceInSymbol(symbol=containing_symbol, line=ref_line, character=ref_col))

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
                if column is not None and line == start["line"]:
                    column_condition = column > start["character"]
            else:
                line_condition = end["line"] >= line >= start["line"]
                if column is not None and line == start["line"]:
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
        Finds the container of the given symbol if there is one. If the parent attribute is present, the parent is returned
        without further searching.

        :param symbol: The symbol to find the container of.
        :param include_body: whether to include the body of the symbol in the result.
        :return: The container of the given symbol or None if no container is found.
        """
        if "parent" in symbol:
            return symbol["parent"]
        assert "location" in symbol, f"Symbol {symbol} has no location and no parent attribute"
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
    def cache_path(self) -> Path:
        """
        The path to the cache file for the document symbols.
        """
        return Path(self.repository_root_path) / ".serena" / "cache" / self.language_id / "document_symbols_cache_v20-05-25.pkl"

    async def index_repository(self, progress_bar: bool = True, save_after_n_files: int = 10) -> None:
        """Will go through the entire repository and "index" all files, meaning save their symbols to the cache.

        :param progress_bar: Whether to show a progress bar while indexing the repository.
        :param save_after_n_files: How many files to process before saving a checkpoint of the cache.
        """
        parsed_files = await self.request_parsed_files()
        files_processed = 0
        pbar = tqdm.tqdm(parsed_files, disable=not progress_bar)
        for relative_file_path in pbar:
            pbar.set_description(f"Indexing ({os.path.basename(relative_file_path)})")
            await self.request_document_symbols(relative_file_path, include_body=False)
            await self.request_document_symbols(relative_file_path, include_body=True)
            files_processed += 1
            if files_processed % save_after_n_files == 0:
                self.save_cache()
        self.save_cache()

    def save_cache(self):
        with self._cache_lock:
            if not self._cache_has_changed:
                self.logger.log("No changes to document symbols cache, skipping save", logging.DEBUG)
                return

            self.logger.log(f"Saving updated document symbols cache to {self.cache_path}", logging.INFO)
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(self.cache_path, "wb") as f:
                    pickle.dump(self._document_symbols_cache, f)
                self._cache_has_changed = False
            except Exception as e:
                self.logger.log(
                    f"Failed to save document symbols cache to {self.cache_path}: {e}. "
                    "Note: this may have resulted in a corrupted cache file.",
                    logging.ERROR,
                )

    def load_cache(self):
        if not self.cache_path.exists():
            return

        with self._cache_lock:
            self.logger.log(f"Loading document symbols cache from {self.cache_path}", logging.INFO)
            try:
                with open(self.cache_path, "rb") as f:
                    self._document_symbols_cache = pickle.load(f)
                self.logger.log(f"Loaded {len(self._document_symbols_cache)} document symbols from cache.", logging.INFO)   
            except Exception as e:
                # cache often becomes corrupt, so just skip loading it
                self.logger.log(
                    f"Failed to load document symbols cache from {self.cache_path}: {e}. Possible cause: the cache file is corrupted. "
                    "Check for any errors related to saving the cache in the logs.",
                    logging.ERROR,
                )


    async def request_workspace_symbol(self, query: str) -> Union[List[multilspy_types.UnifiedSymbolInformation], None]:
        """
        Raise a [workspace/symbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_symbol) request to the Language Server
        to find symbols across the whole workspace. Wait for the response and return the result.

        :param query: The query string to filter symbols by

        :return: A list of matching symbols
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

    def __init__(self, language_server: LanguageServer, timeout: Optional[float] = None):
        """
        :param language_server: the async language server being wrapped
        :param timeout: the timeout, in seconds, to use for requests to the language server.
        """
        self.language_server = language_server
        self.loop = None
        self.loop_thread = None
        self.timeout = timeout

        self._server_context = None
        
        self._shutdown_lock = threading.Lock()
        self._is_shutting_down = False

    @property
    def cache_path(self) -> Path:
        """
        The path to the cache file for the document symbols.
        """
        return self.language_server.cache_path

    @classmethod
    def create(
        cls, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str,
        timeout: Optional[float] = None
    ) -> "SyncLanguageServer":
        """
        Creates a language specific LanguageServer instance based on the given configuration, and appropriate settings for the programming language.

        If language is Java, then ensure that jdk-17.0.6 or higher is installed, `java` is in PATH, and JAVA_HOME is set to the installation directory.

        :param repository_root_path: The root path of the repository (must be absolute).
        :param config: The Multilspy configuration.
        :param logger: The logger to use.
        :param timeout: the timeout, in seconds, to use for requests; if None, use no timeout

        :return SyncLanguageServer: A language specific LanguageServer instance.
        """
        return SyncLanguageServer(LanguageServer.create(config, logger, repository_root_path), timeout=timeout)

    @property
    def repository_root_path(self) -> str:
        return self.language_server.repository_root_path
    
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
        self.start()
        yield self
        self.language_server.logger.log("SyncLS Startup: exiting LS context", logging.DEBUG)
        self.stop()

    def request_definition(self, file_path: str, line: int, column: int) -> List[multilspy_types.Location]:
        """
        Raise a [textDocument/definition](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_definition) request to the Language Server
        for the symbol at the given line and column in the given file. Wait for the response and return the result.

        :param file_path: The path of the file relative to the repository root.
        :param line: The line number (zero-indexed).
        :param column: The column number (zero-indexed).

        :return: A list of Locations defining the symbol.
        """
        if not self.is_running():
            raise RuntimeError("Language server is not running. Cannot make requests to a stopped language server.")
            
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_definition(file_path, line, column), self.loop
        ).result(timeout=self.timeout)
        return result

    def request_references(self, file_path: str, line: int, column: int) -> List[multilspy_types.Location]:
        """
        Raises a [textDocument/references](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_references) request to the Language Server
        for the symbol at the given line and column in the given file. Wait for the response and return the result.

        :param file_path: The path of the file relative to the repository root.
        :param line: The line number (zero-indexed).
        :param column: The column number (zero-indexed).

        :return: A list of Locations referencing the symbol.
        """
        if not self.is_running():
            raise RuntimeError("Language server is not running. Cannot make requests to a stopped language server.")
            
        try:
            result = asyncio.run_coroutine_threadsafe(
                self.language_server.request_references(file_path, line, column), self.loop
            ).result(timeout=self.timeout)
        except Exception as e:
            from multilspy.lsp_protocol_handler.server import Error
            if isinstance(e, Error) and getattr(e, 'code', None) == -32603:
                raise RuntimeError(
                    f"LSP internal error (-32603) when requesting references for {file_path}:{line}:{column}. "
                    "This often occurs when requesting references for a symbol not referenced in the expected way. "
                ) from e
            raise
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
        if not self.is_running():
            raise RuntimeError("Language server is not running. Cannot make requests to a stopped language server.")
        
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
        if not self.is_running():
            raise RuntimeError("Language server is not running. Cannot make requests to a stopped language server.")
            
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

    def request_signature_help(self, relative_file_path: str, line: int, column: int) -> Union[multilspy_types.SignatureHelp, None]:
        """
        Raise a [textDocument/signatureHelp](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_signatureHelp) request to the Language Server
        to find the signature help information at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the signature help information
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return: SignatureHelp object or None
        """
        result = asyncio.run_coroutine_threadsafe(
            self.language_server.request_signature_help(relative_file_path, line, column), self.loop
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
        """Retrieves relative paths of all files analyzed by the Language Server."""
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
    ) -> List[ReferenceInSymbol]:
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
        :return: List of objects containing the symbol and the location of the reference.
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

    def index_repository(self, progress_bar: bool = True, timeout: float | None = None, save_after_n_files: int = 10) -> None:
        """
        Will go through the entire repository and "index" all files, meaning save their symbols to the cache.

        :param progress_bar: Whether to show a progress bar while indexing the repository.
        :param save_after_n_files: How many files to process before saving a checkpoint of the cache.
        :param timeout: since this operation can take a long time, the default timeout (the attribute of the LS instance) is not used.
            If you want to provide a timeout for indexing, you can pass it here explicitly.
        :return:
        """
        assert self.loop
        asyncio.run_coroutine_threadsafe(
            self.language_server.index_repository(progress_bar=progress_bar, save_after_n_files=save_after_n_files), self.loop
        ).result(timeout=timeout)

    def start(self) -> "SyncLanguageServer":
        """
        Starts the language server process and connects to it. Call shutdown when ready.

        :return: self for method chaining
        """
        self.language_server.logger.log(f"Starting language server with language {self.language_server.language} for {self.language_server.repository_root_path}", logging.INFO)
        self.language_server.logger.log("Creating new event loop", logging.DEBUG)
        self.loop = asyncio.new_event_loop()
        self.language_server.logger.log("Creating new thread for event loop", logging.DEBUG)
        self.loop_thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.loop_thread.start()
        self.language_server.logger.log("Starting server (async) context", logging.DEBUG)
        self._server_context = self.language_server.start_server()
        self.language_server.logger.log("Entering server context", logging.DEBUG)
        asyncio.run_coroutine_threadsafe(self._server_context.__aenter__(), loop=self.loop).result(timeout=self.timeout)
        return self

    def is_running(self) -> bool:
        """
        Check if the language server is running.
        """
        return self.loop is not None and self.loop_thread is not None and self.loop_thread.is_alive()
    
    async def _shutdown_and_stop_loop(self):
        """A coroutine that performs the full shutdown and then stops the event loop."""
        try:
            if self._server_context:
                await self._server_context.__aexit__(None, None, None)
        except Exception as e:
            self.language_server.logger.log(f"Exception during async shutdown: {e}", logging.ERROR)
        finally:
            # Clean up tasks but DON'T stop the loop from here
            # Let the main thread handle loop stopping to avoid coroutine deadlocks
            if self.loop and self.loop.is_running():
                current_task = asyncio.current_task(self.loop)
                pending_tasks = [task for task in asyncio.all_tasks(self.loop) 
                               if not task.done() and task is not current_task]
                
                if pending_tasks:
                    self.language_server.logger.log(f"Cancelling {len(pending_tasks)} pending tasks", logging.DEBUG)
                    for task in pending_tasks:
                        try:
                            task.cancel()
                        except Exception:
                            pass
                
                self.language_server.logger.log("Async shutdown tasks completed, returning to main thread", logging.DEBUG)
                # Note: NOT calling loop.stop() here - let main thread do it

    def stop(self, shutdown_timeout: float = 2.0) -> None:
        """
        Stops the language server and robustly cleans up all associated resources,
        including the asyncio event loop, to prevent hangs on process exit.
        """
        # 1. Use a lock and flag to make the shutdown call thread-safe and idempotent,
        # ensuring the shutdown logic runs only once.
        with self._shutdown_lock:
            if self._is_shutting_down:
                self.language_server.logger.log("Already shutting down or stopped, skipping", logging.DEBUG)
                return
            self._is_shutting_down = True
    
        if not self.is_running():
            self.language_server.logger.log("Language server is not running, skipping", logging.DEBUG)
            return
    
        self.language_server.logger.log("Initiating server shutdown...", logging.INFO)
        self.save_cache()
        
        # Detect platform to choose shutdown strategy
        is_windows = os.name == "nt"
        
        if not is_windows:
            # 2. Graceful shutdown for Linux/Unix - try proper async cleanup first
            self.language_server.logger.log("Starting graceful shutdown", logging.INFO)
            shutdown_future = None
            if self.loop and self.loop.is_running():
                shutdown_future = asyncio.run_coroutine_threadsafe(self._shutdown_and_stop_loop(), self.loop)
            
            # 3. Wait for the background thread to exit
            if self.loop_thread:
                self.language_server.logger.log("Waiting for event loop thread to exit", logging.INFO)
                self.loop_thread.join(timeout=shutdown_timeout)
                if self.loop_thread.is_alive():
                    self.language_server.logger.log("Event loop thread did not terminate within timeout", logging.WARNING)
            
            # 4. Wait for the shutdown coroutine to complete if it was scheduled
            if shutdown_future:
                self.language_server.logger.log("Waiting for async shutdown to complete", logging.INFO)
                try:
                    shutdown_future.result(timeout=shutdown_timeout)
                    self.language_server.logger.log("Graceful async shutdown completed", logging.DEBUG)
                except Exception as e:
                    self.language_server.logger.log(f"Async shutdown failed: {e}", logging.WARNING)
            
            # 5. Close the loop properly after graceful shutdown
            if self.loop and not self.loop.is_closed():
                self.language_server.logger.log("Closing event loop", logging.INFO)
                try:
                    self.loop.close()
                    self.language_server.logger.log("Event loop closed successfully", logging.DEBUG)
                except Exception as e:
                    self.language_server.logger.log(f"Event loop close failed: {e}", logging.WARNING)
        
        else:
            # WINDOWS NUCLEAR OPTION: Skip graceful shutdown - go straight to nuclear
            # Windows IocpProactor has too many issues with proper cleanup
            self.language_server.logger.log("Windows detected - using nuclear shutdown to prevent zombies", logging.WARNING)
            
            # Force stop the loop immediately without waiting for async cleanup
            if self.loop and self.loop.is_running():
                try:
                    self.loop.call_soon_threadsafe(lambda: setattr(self.loop, '_stopping', True))
                    self.loop.call_soon_threadsafe(self.loop.stop)
                except Exception:
                    pass
                
                # Force mark loop as closed IMMEDIATELY to prevent zombies
                try:
                    if hasattr(self.loop, '_closed'):
                        self.loop._closed = True
                    if hasattr(self.loop, '_stopping'):
                        self.loop._stopping = True
                    if hasattr(self.loop, '_ready'):
                        self.loop._ready.clear()
                except Exception:
                    pass
            
            # Give thread minimal time to exit, then abandon it
            if self.loop_thread:
                self.loop_thread.join(timeout=1.0)  # Only 1 second on Windows
                if self.loop_thread.is_alive():
                    self.language_server.logger.log("Thread stuck - abandoning to prevent GC deadlock", logging.WARNING)
    
        # 6. Null out everything immediately - same for both platforms
        self.loop = None
        self.loop_thread = None
        self._server_context = None
        self._is_shutting_down = False
        
        shutdown_type = "Nuclear" if is_windows else "Graceful"
        self.language_server.logger.log(f"{shutdown_type} shutdown complete - all references cleared", logging.INFO)

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

    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True) -> bool:
        """
        Whether the given path should be ignored.
        """
        return self.language_server.is_ignored_path(relative_path, ignore_unsupported_files=ignore_unsupported_files)

    def get_ignore_spec(self) -> pathspec.PathSpec:
        """Returns the pathspec matcher for the paths that were configured to be ignored through
        the multilspy config.

        This is is a subset of the full language-specific ignore spec that determines
        which files are relevant for the language server.

        This matcher is useful for operations outside of the language server,
        such as when searching for relevant non-language files in the project.
        """
        return self.language_server.get_ignore_spec()
