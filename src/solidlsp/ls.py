import dataclasses
import hashlib
import json
import logging
import os
import pathlib
import pickle
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from copy import copy
from pathlib import Path, PurePath
from time import sleep
from typing import Self, Union, cast

import pathspec

from serena.text_utils import MatchedConsecutiveLines
from serena.util.file_system import match_path
from solidlsp import ls_types
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_handler import SolidLanguageServerHandler
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_types import UnifiedSymbolInformation
from solidlsp.ls_utils import FileUtils, PathUtils, TextUtils
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler import lsp_types as LSPTypes
from solidlsp.lsp_protocol_handler.lsp_constants import LSPConstants
from solidlsp.lsp_protocol_handler.lsp_types import Definition, DefinitionParams, LocationLink, SymbolKind
from solidlsp.lsp_protocol_handler.server import (
    LSPError,
    ProcessLaunchInfo,
    StringDict,
)
from solidlsp.settings import SolidLSPSettings

GenericDocumentSymbol = Union[LSPTypes.DocumentSymbol, LSPTypes.SymbolInformation, ls_types.UnifiedSymbolInformation]


@dataclasses.dataclass(kw_only=True)
class ReferenceInSymbol:
    """A symbol retrieved when requesting reference to a symbol, together with the location of the reference"""

    symbol: ls_types.UnifiedSymbolInformation
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

    content_hash: str = ""

    def __post_init__(self):
        self.content_hash = hashlib.md5(self.contents.encode("utf-8")).hexdigest()


class SolidLanguageServer(ABC):
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
        return dirname.startswith(".")

    @classmethod
    def ls_resources_dir(cls, solidlsp_settings: SolidLSPSettings, mkdir: bool = True) -> str:
        """
        Returns the directory where the language server resources are downloaded.
        This is used to store language server binaries, configuration files, etc.
        """
        result = os.path.join(solidlsp_settings.ls_resources_dir, cls.__name__)

        # Migration of previously downloaded LS resources that were downloaded to a subdir of solidlsp instead of to the user's home
        pre_migration_ls_resources_dir = os.path.join(os.path.dirname(__file__), "language_servers", "static", cls.__name__)
        if os.path.exists(pre_migration_ls_resources_dir):
            if os.path.exists(result):
                # if the directory already exists, we just remove the old resources
                shutil.rmtree(result, ignore_errors=True)
            else:
                # move old resources to the new location
                shutil.move(pre_migration_ls_resources_dir, result)
        if mkdir:
            os.makedirs(result, exist_ok=True)
        return result

    @classmethod
    def create(
        cls,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        timeout: float | None = None,
        solidlsp_settings: SolidLSPSettings | None = None,
    ) -> "SolidLanguageServer":
        """
        Creates a language specific LanguageServer instance based on the given configuration, and appropriate settings for the programming language.

        If language is Java, then ensure that jdk-17.0.6 or higher is installed, `java` is in PATH, and JAVA_HOME is set to the installation directory.
        If language is JS/TS, then ensure that node (v18.16.0 or higher) is installed and in PATH.

        :param repository_root_path: The root path of the repository.
        :param config: The Multilspy configuration.
        :param logger: The logger to use.
        :param timeout: the timeout for requests to the language server. If None, no timeout will be used.
        :return LanguageServer: A language specific LanguageServer instance.
        """
        ls: SolidLanguageServer
        if solidlsp_settings is None:
            solidlsp_settings = SolidLSPSettings()

        if config.code_language == Language.PYTHON:
            from solidlsp.language_servers.pyright_server import (
                PyrightServer,
            )

            ls = PyrightServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)
        elif config.code_language == Language.PYTHON_JEDI:
            from solidlsp.language_servers.jedi_server import JediServer

            ls = JediServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)
        elif config.code_language == Language.JAVA:
            from solidlsp.language_servers.eclipse_jdtls import (
                EclipseJDTLS,
            )

            ls = EclipseJDTLS(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.KOTLIN:
            from solidlsp.language_servers.kotlin_language_server import (
                KotlinLanguageServer,
            )

            ls = KotlinLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.RUST:
            from solidlsp.language_servers.rust_analyzer import (
                RustAnalyzer,
            )

            ls = RustAnalyzer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.CSHARP:
            from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer

            ls = CSharpLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)
        elif config.code_language == Language.CSHARP_OMNISHARP:
            from solidlsp.language_servers.omnisharp import OmniSharp

            ls = OmniSharp(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)
        elif config.code_language == Language.TYPESCRIPT:
            from solidlsp.language_servers.typescript_language_server import (
                TypeScriptLanguageServer,
            )

            ls = TypeScriptLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)
        elif config.code_language == Language.TYPESCRIPT_VTS:
            # VTS based Language Server implementation, need to experiment to see if it improves performance
            from solidlsp.language_servers.vts_language_server import VtsLanguageServer

            ls = VtsLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)
        elif config.code_language == Language.GO:
            from solidlsp.language_servers.gopls import Gopls

            ls = Gopls(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.RUBY:
            from solidlsp.language_servers.ruby_lsp import RubyLsp

            ls = RubyLsp(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.RUBY_SOLARGRAPH:
            from solidlsp.language_servers.solargraph import Solargraph

            ls = Solargraph(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.DART:
            from solidlsp.language_servers.dart_language_server import DartLanguageServer

            ls = DartLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.CPP:
            from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer

            ls = ClangdLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.PHP:
            from solidlsp.language_servers.intelephense import Intelephense

            ls = Intelephense(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.CLOJURE:
            from solidlsp.language_servers.clojure_lsp import ClojureLSP

            ls = ClojureLSP(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.ELIXIR:
            from solidlsp.language_servers.elixir_tools.elixir_tools import ElixirTools

            ls = ElixirTools(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.TERRAFORM:
            from solidlsp.language_servers.terraform_ls import TerraformLS

            ls = TerraformLS(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.SWIFT:
            from solidlsp.language_servers.sourcekit_lsp import SourceKitLSP

            ls = SourceKitLSP(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.BASH:
            from solidlsp.language_servers.bash_language_server import BashLanguageServer

            ls = BashLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.ZIG:
            from solidlsp.language_servers.zls import ZigLanguageServer

            ls = ZigLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.NIX:
            from solidlsp.language_servers.nixd_ls import NixLanguageServer

            ls = NixLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.LUA:
            from solidlsp.language_servers.lua_ls import LuaLanguageServer

            ls = LuaLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        elif config.code_language == Language.ERLANG:
            from solidlsp.language_servers.erlang_language_server import ErlangLanguageServer

            ls = ErlangLanguageServer(config, logger, repository_root_path, solidlsp_settings=solidlsp_settings)

        else:
            logger.log(f"Language {config.code_language} is not supported", logging.ERROR)
            raise SolidLSPException(f"Language {config.code_language} is not supported")

        ls.set_request_timeout(timeout)
        return ls

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        process_launch_info: ProcessLaunchInfo,
        language_id: str,
        solidlsp_settings: SolidLSPSettings,
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
        self._solidlsp_settings = solidlsp_settings
        self.logger = logger
        self.repository_root_path: str = repository_root_path
        self.logger.log(
            f"Creating language server instance for {repository_root_path=} with {language_id=} and process launch info: {process_launch_info}",
            logging.DEBUG,
        )

        self.language_id = language_id
        self.open_file_buffers: dict[str, LSPFileBuffer] = {}
        self.language = Language(language_id)

        # load cache first to prevent any racing conditions due to asyncio stuff
        self._document_symbols_cache: dict[
            str, tuple[str, tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]]
        ] = {}
        """Maps file paths to a tuple of (file_content_hash, result_of_request_document_symbols)"""
        self._cache_lock = threading.Lock()
        self._cache_has_changed: bool = False
        self.load_cache()

        self.server_started = False
        self.completions_available = threading.Event()
        if config.trace_lsp_communication:

            def logging_fn(source: str, target: str, msg: StringDict | str):
                self.logger.log(f"LSP: {source} -> {target}: {msg!s}", self.logger.logger.level)

        else:
            logging_fn = None

        # cmd is obtained from the child classes, which provide the language specific command to start the language server
        # LanguageServerHandler provides the functionality to start the language server and communicate with it
        self.logger.log(
            f"Creating language server instance with {language_id=} and process launch info: {process_launch_info}", logging.DEBUG
        )
        self.server = SolidLanguageServerHandler(
            process_launch_info,
            logger=logging_fn,
            start_independent_lsp_process=config.start_independent_lsp_process,
        )

        # Set up the pathspec matcher for the ignored paths
        # for all absolute paths in ignored_paths, convert them to relative paths
        processed_patterns = []
        for pattern in set(config.ignored_paths):
            # Normalize separators (pathspec expects forward slashes)
            pattern = pattern.replace(os.path.sep, "/")
            processed_patterns.append(pattern)
        self.logger.log(f"Processing {len(processed_patterns)} ignored paths from the config", logging.DEBUG)

        # Create a pathspec matcher from the processed patterns
        self._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, processed_patterns)

        self._server_context = None
        self._request_timeout: float | None = None

        self._has_waited_for_cross_file_references = False

    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Meant to be overridden by subclasses for LS that don't have a reliable "finished initializing" signal.

        LS may return incomplete results on calls to `request_references` (only references found in the same file),
        if the LS is not fully initialized yet.
        """
        return 0

    def set_request_timeout(self, timeout: float | None) -> None:
        """
        :param timeout: the timeout, in seconds, for requests to the language server.
        """
        self.server.set_request_timeout(timeout)

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

        return match_path(relative_path, self.get_ignore_spec(), root_path=self.repository_root_path)

    def _shutdown(self, timeout: float = 5.0):
        """
        A robust shutdown process designed to terminate cleanly on all platforms, including Windows,
        by explicitly closing all I/O pipes.
        """
        if not self.server.is_running():
            self.logger.log("Server process not running, skipping shutdown.", logging.DEBUG)
            return

        self.logger.log(f"Initiating final robust shutdown with a {timeout}s timeout...", logging.INFO)
        process = self.server.process

        # --- Main Shutdown Logic ---
        # Stage 1: Graceful Termination Request
        # Send LSP shutdown and close stdin to signal no more input.
        try:
            self.logger.log("Sending LSP shutdown request...", logging.DEBUG)
            # Use a thread to timeout the LSP shutdown call since it can hang
            shutdown_thread = threading.Thread(target=self.server.shutdown)
            shutdown_thread.daemon = True
            shutdown_thread.start()
            shutdown_thread.join(timeout=2.0)  # 2 second timeout for LSP shutdown

            if shutdown_thread.is_alive():
                self.logger.log("LSP shutdown request timed out, proceeding to terminate...", logging.DEBUG)
            else:
                self.logger.log("LSP shutdown request completed.", logging.DEBUG)

            if process.stdin and not process.stdin.is_closing():
                process.stdin.close()
            self.logger.log("Stage 1 shutdown complete.", logging.DEBUG)
        except Exception as e:
            self.logger.log(f"Exception during graceful shutdown: {e}", logging.DEBUG)
            # Ignore errors here, we are proceeding to terminate anyway.

        # Stage 2: Terminate and Wait for Process to Exit
        self.logger.log(f"Terminating process {process.pid}, current status: {process.poll()}", logging.DEBUG)
        process.terminate()

        # Stage 3: Wait for process termination with timeout
        try:
            self.logger.log(f"Waiting for process {process.pid} to terminate...", logging.DEBUG)
            exit_code = process.wait(timeout=timeout)
            self.logger.log(f"Language server process terminated successfully with exit code {exit_code}.", logging.INFO)
        except subprocess.TimeoutExpired:
            # If termination failed, forcefully kill the process
            self.logger.log(f"Process {process.pid} termination timed out, killing process forcefully...", logging.WARNING)
            process.kill()
            try:
                exit_code = process.wait(timeout=2.0)
                self.logger.log(f"Language server process killed successfully with exit code {exit_code}.", logging.INFO)
            except subprocess.TimeoutExpired:
                self.logger.log(f"Process {process.pid} could not be killed within timeout.", logging.ERROR)
        except Exception as e:
            self.logger.log(f"Error during process shutdown: {e}", logging.ERROR)

    @contextmanager
    def start_server(self) -> Iterator["SolidLanguageServer"]:
        self.start()
        yield self
        self.stop()

    def _start_server_process(self) -> None:
        self.server_started = True
        self._start_server()

    @abstractmethod
    def _start_server(self):
        pass

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
            raise SolidLSPException("Language Server not started")

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

    def insert_text_at_position(self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str) -> ls_types.Position:
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
            raise SolidLSPException("Language Server not started")

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
        return ls_types.Position(line=new_l, character=new_c)

    def delete_text_between_positions(
        self,
        relative_file_path: str,
        start: ls_types.Position,
        end: ls_types.Position,
    ) -> str:
        """
        Delete text between the given start and end positions in the given file and return the deleted text.
        """
        if not self.server_started:
            self.logger.log(
                "insert_text_at_position called before Language Server started",
                logging.ERROR,
            )
            raise SolidLSPException("Language Server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()

        # Ensure the file is open
        assert uri in self.open_file_buffers

        file_buffer = self.open_file_buffers[uri]
        file_buffer.version += 1
        new_contents, deleted_text = TextUtils.delete_text_between_positions(
            file_buffer.contents, start_line=start["line"], start_col=start["character"], end_line=end["line"], end_col=end["character"]
        )
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

    def _send_definition_request(self, definition_params: DefinitionParams) -> Definition | list[LocationLink] | None:
        return self.server.send.definition(definition_params)

    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
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
                "request_definition called before Language Server started",
                logging.ERROR,
            )
            raise SolidLSPException("Language Server not started")

        with self.open_file(relative_file_path):
            # sending request to the language server and waiting for response
            definition_params = cast(
                DefinitionParams,
                {
                    LSPConstants.TEXT_DOCUMENT: {
                        LSPConstants.URI: pathlib.Path(str(PurePath(self.repository_root_path, relative_file_path))).as_uri()
                    },
                    LSPConstants.POSITION: {
                        LSPConstants.LINE: line,
                        LSPConstants.CHARACTER: column,
                    },
                },
            )
            response = self._send_definition_request(definition_params)

        ret: list[ls_types.Location] = []
        if isinstance(response, list):
            # response is either of type Location[] or LocationLink[]
            for item in response:
                assert isinstance(item, dict)
                if LSPConstants.URI in item and LSPConstants.RANGE in item:
                    new_item: ls_types.Location = {}
                    new_item.update(item)
                    new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
                    new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
                    ret.append(ls_types.Location(new_item))
                elif LSPConstants.TARGET_URI in item and LSPConstants.TARGET_RANGE in item and LSPConstants.TARGET_SELECTION_RANGE in item:
                    new_item: ls_types.Location = {}
                    new_item["uri"] = item[LSPConstants.TARGET_URI]
                    new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
                    new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
                    new_item["range"] = item[LSPConstants.TARGET_SELECTION_RANGE]
                    ret.append(ls_types.Location(**new_item))
                else:
                    assert False, f"Unexpected response from Language Server: {item}"
        elif isinstance(response, dict):
            # response is of type Location
            assert LSPConstants.URI in response
            assert LSPConstants.RANGE in response

            new_item: ls_types.Location = {}
            new_item.update(response)
            new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
            new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
            ret.append(ls_types.Location(**new_item))
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
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[lsp_types.Location] | None:
        return self.server.send.references(
            {
                "textDocument": {"uri": PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))},
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": False},
            }
        )

    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
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
            raise SolidLSPException("Language Server not started")

        if not self._has_waited_for_cross_file_references:
            # Some LS require waiting for a while before they can return cross-file references.
            # This is a workaround for such LS that don't have a reliable "finished initializing" signal.
            sleep(self._get_wait_time_for_cross_file_referencing())
            self._has_waited_for_cross_file_references = True

        with self.open_file(relative_file_path):
            try:
                response = self._send_references_request(relative_file_path, line=line, column=column)
            except Exception as e:
                # Catch LSP internal error (-32603) and raise a more informative exception
                if isinstance(e, LSPError) and getattr(e, "code", None) == -32603:
                    raise RuntimeError(
                        f"LSP internal error (-32603) when requesting references for {relative_file_path}:{line}:{column}. "
                        "This often occurs when requesting references for a symbol not referenced in the expected way. "
                    ) from e
                raise
        if response is None:
            return []

        ret: list[ls_types.Location] = []
        assert isinstance(response, list), f"Unexpected response from Language Server (expected list, got {type(response)}): {response}"
        for item in response:
            assert isinstance(item, dict), f"Unexpected response from Language Server (expected dict, got {type(item)}): {item}"
            assert LSPConstants.URI in item
            assert LSPConstants.RANGE in item

            abs_path = PathUtils.uri_to_path(item[LSPConstants.URI])
            if not Path(abs_path).is_relative_to(self.repository_root_path):
                self.logger.log(
                    "Found a reference in a path outside the repository, probably the LS is parsing things in installed packages or in the standardlib! "
                    f"Path: {abs_path}. This is a bug but we currently simply skip these references.",
                    logging.WARNING,
                )
                continue

            rel_path = Path(abs_path).relative_to(self.repository_root_path)
            if self.is_ignored_path(str(rel_path)):
                self.logger.log(f"Ignoring reference in {rel_path} since it should be ignored", logging.DEBUG)
                continue

            new_item: ls_types.Location = {}
            new_item.update(item)
            new_item["absolutePath"] = str(abs_path)
            new_item["relativePath"] = str(rel_path)
            ret.append(ls_types.Location(**new_item))

        return ret

    def request_text_document_diagnostics(self, relative_file_path: str) -> list[ls_types.Diagnostic]:
        """
        Raise a [textDocument/diagnostic](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_diagnostic) request to the Language Server
        to find diagnostics for the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file to retrieve diagnostics for

        :return: A list of diagnostics for the file
        """
        if not self.server_started:
            self.logger.log(
                "request_text_document_diagnostics called before Language Server started",
                logging.ERROR,
            )
            raise SolidLSPException("Language Server not started")

        with self.open_file(relative_file_path):
            response = self.server.send.text_document_diagnostic(
                {
                    LSPConstants.TEXT_DOCUMENT: {
                        LSPConstants.URI: pathlib.Path(str(PurePath(self.repository_root_path, relative_file_path))).as_uri()
                    }
                }
            )

        if response is None:
            return []

        assert isinstance(response, dict), f"Unexpected response from Language Server (expected list, got {type(response)}): {response}"
        ret: list[ls_types.Diagnostic] = []
        for item in response["items"]:
            new_item: ls_types.Diagnostic = {
                "uri": pathlib.Path(str(PurePath(self.repository_root_path, relative_file_path))).as_uri(),
                "severity": item["severity"],
                "message": item["message"],
                "range": item["range"],
                "code": item["code"],
            }
            ret.append(ls_types.Diagnostic(new_item))

        return ret

    def retrieve_full_file_content(self, file_path: str) -> str:
        """
        Retrieve the full content of the given file.
        """
        if os.path.isabs(file_path):
            file_path = os.path.relpath(file_path, self.repository_root_path)
        with self.open_file(file_path) as file_data:
            return file_data.contents

    def retrieve_content_around_line(
        self, relative_file_path: str, line: int, context_lines_before: int = 0, context_lines_after: int = 0
    ) -> MatchedConsecutiveLines:
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
        return MatchedConsecutiveLines.from_file_contents(
            file_contents,
            line=line,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            source_file_path=relative_file_path,
        )

    def request_completions(
        self, relative_file_path: str, line: int, column: int, allow_incomplete: bool = False
    ) -> list[ls_types.CompletionItem]:
        """
        Raise a [textDocument/completion](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_completion) request to the Language Server
        to find completions at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbol for which completions should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return List[multilspy_types.CompletionItem]: A list of completions
        """
        with self.open_file(relative_file_path):
            open_file_buffer = self.open_file_buffers[pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()]
            completion_params: LSPTypes.CompletionParams = {
                "position": {"line": line, "character": column},
                "textDocument": {"uri": open_file_buffer.uri},
                "context": {"triggerKind": LSPTypes.CompletionTriggerKind.Invoked},
            }
            response: list[LSPTypes.CompletionItem] | LSPTypes.CompletionList | None = None

            num_retries = 0
            while response is None or (response["isIncomplete"] and num_retries < 30):
                self.completions_available.wait()
                response: list[LSPTypes.CompletionItem] | LSPTypes.CompletionList | None = self.server.send.completion(completion_params)
                if isinstance(response, list):
                    response = {"items": response, "isIncomplete": False}
                num_retries += 1

            # TODO: Understand how to appropriately handle `isIncomplete`
            if response is None or (response["isIncomplete"] and not (allow_incomplete)):
                return []

            if "items" in response:
                response = response["items"]

            response = cast(list[LSPTypes.CompletionItem], response)

            # TODO: Handle the case when the completion is a keyword
            items = [item for item in response if item["kind"] != LSPTypes.CompletionItemKind.Keyword]

            completions_list: list[ls_types.CompletionItem] = []

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
                            item["textEdit"]["range"]["start"]["character"] == item["textEdit"]["range"]["end"]["character"],
                        )
                    )

                    completion_item["completionText"] = item["textEdit"]["newText"]
                    completion_item["kind"] = item["kind"]
                elif "textEdit" in item and "insert" in item["textEdit"]:
                    assert False
                else:
                    assert False

                completion_item = ls_types.CompletionItem(**completion_item)
                completions_list.append(completion_item)

            return [json.loads(json_repr) for json_repr in set(json.dumps(item, sort_keys=True) for item in completions_list)]

    def request_document_symbols(
        self, relative_file_path: str, include_body: bool = False
    ) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
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
            response = self.server.send.document_symbol(
                {"textDocument": {"uri": pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()}}
            )
            if response is None:
                self.logger.log(
                    f"Received None response from the Language Server for document symbols in {relative_file_path}. "
                    f"This means the language server can't understand this file (possibly due to syntax errors). It may also be due to a bug or misconfiguration of the LS. "
                    f"Returning empty list",
                    logging.WARNING,
                )
                return [], []
            assert isinstance(response, list), f"Unexpected response from Language Server: {response}"
            self.logger.log(
                f"Received {len(response)} document symbols for {relative_file_path} from the Language Server",
                logging.DEBUG,
            )

        def turn_item_into_symbol_with_children(item: GenericDocumentSymbol):
            item = cast(ls_types.UnifiedSymbolInformation, item)
            absolute_path = os.path.join(self.repository_root_path, relative_file_path)

            # handle missing entries in location
            if "location" not in item:
                uri = pathlib.Path(absolute_path).as_uri()
                assert "range" in item
                tree_location = ls_types.Location(
                    uri=uri,
                    range=item["range"],
                    absolutePath=absolute_path,
                    relativePath=relative_file_path,
                )
                item["location"] = tree_location
            location = item["location"]
            if "absolutePath" not in location:
                location["absolutePath"] = absolute_path
            if "relativePath" not in location:
                location["relativePath"] = relative_file_path
            if include_body:
                item["body"] = self.retrieve_symbol_body(item)
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

        flat_all_symbol_list: list[ls_types.UnifiedSymbolInformation] = []
        root_nodes: list[ls_types.UnifiedSymbolInformation] = []
        for root_item in response:
            if "range" not in root_item and "location" not in root_item:
                if root_item["kind"] in [SymbolKind.File, SymbolKind.Module]:
                    ...

            # mutation is more convenient than creating a new dict,
            # so we cast and rename the var after the mutating call to turn_item_into_symbol_with_children
            # which turned and item into a "symbol"
            turn_item_into_symbol_with_children(root_item)
            root_symbol = cast(ls_types.UnifiedSymbolInformation, root_item)
            root_symbol["parent"] = None

            root_nodes.append(root_symbol)
            assert isinstance(root_symbol, dict)
            assert LSPConstants.NAME in root_symbol
            assert LSPConstants.KIND in root_symbol

            if LSPConstants.CHILDREN in root_symbol:
                # TODO: l_tree should be a list of TreeRepr. Define the following function to return TreeRepr as well

                def visit_tree_nodes_and_build_tree_repr(node: GenericDocumentSymbol) -> list[ls_types.UnifiedSymbolInformation]:
                    node = cast(ls_types.UnifiedSymbolInformation, node)
                    l: list[ls_types.UnifiedSymbolInformation] = []
                    turn_item_into_symbol_with_children(node)
                    assert LSPConstants.CHILDREN in node
                    children = node[LSPConstants.CHILDREN]
                    l.append(node)
                    for child in children:
                        l.extend(visit_tree_nodes_and_build_tree_repr(child))
                    return l

                flat_all_symbol_list.extend(visit_tree_nodes_and_build_tree_repr(root_symbol))
            else:
                flat_all_symbol_list.append(ls_types.UnifiedSymbolInformation(**root_symbol))

        result = flat_all_symbol_list, root_nodes
        self.logger.log(f"Caching document symbols for {relative_file_path}", logging.DEBUG)
        with self._cache_lock:
            self._document_symbols_cache[cache_key] = (file_data.content_hash, result)
            self._cache_has_changed = True
        return result

    def request_full_symbol_tree(
        self, within_relative_path: str | None = None, include_body: bool = False
    ) -> list[ls_types.UnifiedSymbolInformation]:
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
                    self.logger.log(
                        f"You passed a file explicitly, but it is ignored. This is probably an error. File: {within_relative_path}",
                        logging.ERROR,
                    )
                    return []
                else:
                    _, root_nodes = self.request_document_symbols(within_relative_path, include_body=include_body)
                    return root_nodes

        # Helper function to recursively process directories
        def process_directory(rel_dir_path: str) -> list[ls_types.UnifiedSymbolInformation]:
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
            package_symbol = ls_types.UnifiedSymbolInformation(  # type: ignore
                name=os.path.basename(abs_dir_path),
                kind=ls_types.SymbolKind.Package,
                location=ls_types.Location(
                    uri=str(pathlib.Path(abs_dir_path).as_uri()),
                    range={"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                    absolutePath=str(abs_dir_path),
                    relativePath=str(Path(abs_dir_path).resolve().relative_to(self.repository_root_path)),
                ),
                children=[],
            )
            result.append(package_symbol)

            for contained_dir_or_file_name in contained_dir_or_file_names:
                contained_dir_or_file_abs_path = os.path.join(abs_dir_path, contained_dir_or_file_name)
                contained_dir_or_file_rel_path = str(Path(contained_dir_or_file_abs_path).resolve().relative_to(self.repository_root_path))
                if self.is_ignored_path(contained_dir_or_file_rel_path):
                    self.logger.log(f"Skipping item: {contained_dir_or_file_rel_path}\n(because it should be ignored)", logging.DEBUG)
                    continue

                if os.path.isdir(contained_dir_or_file_abs_path):
                    child_symbols = process_directory(contained_dir_or_file_rel_path)
                    package_symbol["children"].extend(child_symbols)
                    for child in child_symbols:
                        child["parent"] = package_symbol

                elif os.path.isfile(contained_dir_or_file_abs_path):
                    _, file_root_nodes = self.request_document_symbols(contained_dir_or_file_rel_path, include_body=include_body)

                    # Create file symbol, link with children
                    file_rel_path = str(Path(contained_dir_or_file_abs_path).resolve().relative_to(self.repository_root_path))
                    with self.open_file(file_rel_path) as file_data:
                        fileRange = self._get_range_from_file_content(file_data.contents)
                    file_symbol = ls_types.UnifiedSymbolInformation(  # type: ignore
                        name=os.path.splitext(contained_dir_or_file_name)[0],
                        kind=ls_types.SymbolKind.File,
                        range=fileRange,
                        selectionRange=fileRange,
                        location=ls_types.Location(
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
                    def fix_relative_path(nodes: list[ls_types.UnifiedSymbolInformation]):
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
        return process_directory(start_rel_path)

    @staticmethod
    def _get_range_from_file_content(file_content: str) -> ls_types.Range:
        """
        Get the range for the given file.
        """
        lines = file_content.split("\n")
        end_line = len(lines)
        end_column = len(lines[-1])
        return ls_types.Range(start=ls_types.Position(line=0, character=0), end=ls_types.Position(line=end_line, character=end_column))

    def request_dir_overview(self, relative_dir_path: str) -> dict[str, list[UnifiedSymbolInformation]]:
        """
        :return: A mapping of all relative paths analyzed to lists of top-level symbols in the corresponding file.
        """
        symbol_tree = self.request_full_symbol_tree(relative_dir_path)
        # Initialize result dictionary
        result: dict[str, list[UnifiedSymbolInformation]] = defaultdict(list)

        # Helper function to process a symbol and its children
        def process_symbol(symbol: ls_types.UnifiedSymbolInformation):
            if symbol["kind"] == ls_types.SymbolKind.File:
                # For file symbols, process their children (top-level symbols)
                for child in symbol["children"]:
                    path = Path(child["location"]["absolutePath"]).resolve().relative_to(self.repository_root_path)
                    result[str(path)].append(child)
            # For package/directory symbols, process their children
            for child in symbol["children"]:
                process_symbol(child)

        # Process each root symbol
        for root in symbol_tree:
            process_symbol(root)
        return result

    def request_document_overview(self, relative_file_path: str) -> list[UnifiedSymbolInformation]:
        """
        :return: the top-level symbols in the given file.
        """
        _, document_roots = self.request_document_symbols(relative_file_path)
        return document_roots

    def request_overview(self, within_relative_path: str) -> dict[str, list[UnifiedSymbolInformation]]:
        """
        An overview of all symbols in the given file or directory.

        :param within_relative_path: the relative path to the file or directory to get the overview of.
        :return: A mapping of all relative paths analyzed to lists of top-level symbols in the corresponding file.
        """
        abs_path = (Path(self.repository_root_path) / within_relative_path).resolve()
        if not abs_path.exists():
            raise FileNotFoundError(f"File or directory not found: {abs_path}")

        if abs_path.is_file():
            symbols_overview = self.request_document_overview(within_relative_path)
            return {within_relative_path: symbols_overview}
        else:
            return self.request_dir_overview(within_relative_path)

    def request_hover(self, relative_file_path: str, line: int, column: int) -> ls_types.Hover | None:
        """
        Raise a [textDocument/hover](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_hover) request to the Language Server
        to find the hover information at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the hover information
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return None
        """
        with self.open_file(relative_file_path):
            response = self.server.send.hover(
                {
                    "textDocument": {"uri": pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()},
                    "position": {
                        "line": line,
                        "character": column,
                    },
                }
            )

        if response is None:
            return None

        assert isinstance(response, dict)

        return ls_types.Hover(**response)

    def retrieve_symbol_body(self, symbol: ls_types.UnifiedSymbolInformation | LSPTypes.DocumentSymbol | LSPTypes.SymbolInformation) -> str:
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
        symbol_body = "\n".join(symbol_lines[symbol_start_line : symbol_end_line + 1])

        # remove leading indentation
        symbol_start_column = symbol["location"]["range"]["start"]["character"]
        symbol_body = symbol_body[symbol_start_column:]
        return symbol_body

    def request_referencing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_imports: bool = True,
        include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
    ) -> list[ReferenceInSymbol]:
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
            raise SolidLSPException("Language Server not started")

        # First, get all references to the symbol
        references = self.request_references(relative_file_path, line, column)
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
                containing_symbol = self.request_containing_symbol(ref_path, ref_line, ref_col, include_body=include_body)
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
                        all_symbols, _ = self.request_document_symbols(ref_path)
                        for symbol in all_symbols:
                            if symbol["name"] == containing_symbol_name and symbol["kind"] == ls_types.SymbolKind.Variable:
                                containing_symbol = copy(symbol)
                                containing_symbol["location"] = ref
                                containing_symbol["range"] = ref["range"]
                                break

                # We failed retrieving the symbol, falling back to creating a file symbol
                if containing_symbol is None and include_file_symbols:
                    self.logger.log(
                        f"Could not find containing symbol for {ref_path}:{ref_line}:{ref_col}. Returning file symbol instead",
                        logging.WARNING,
                    )
                    fileRange = self._get_range_from_file_content(file_data.contents)
                    location = ls_types.Location(
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

                    containing_symbol = ls_types.UnifiedSymbolInformation(
                        kind=ls_types.SymbolKind.File,
                        range=fileRange,
                        selectionRange=fileRange,
                        location=location,
                        name=name,
                        children=[],
                        body=body,
                    )
                if containing_symbol is None or (not include_file_symbols and containing_symbol["kind"] == ls_types.SymbolKind.File):
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
                    self.logger.log(f"Found self-reference for {incoming_symbol['name']}, skipping it since {include_self=}", logging.DEBUG)
                    continue

                # checking whether reference is an import
                # This is neither really safe nor elegant, but if we don't do it,
                # there is no way to distinguish between definitions and imports as import is not a symbol-type
                # and we get the type referenced symbol resulting from imports...
                if (
                    not include_imports
                    and incoming_symbol is not None
                    and containing_symbol["name"] == incoming_symbol["name"]
                    and containing_symbol["kind"] == incoming_symbol["kind"]
                ):
                    self.logger.log(
                        f"Found import of referenced symbol {incoming_symbol['name']}"
                        f"in {containing_symbol['location']['relativePath']}, skipping",
                        logging.DEBUG,
                    )
                    continue

                result.append(ReferenceInSymbol(symbol=containing_symbol, line=ref_line, character=ref_col))

        return result

    def request_containing_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int | None = None,
        strict: bool = False,
        include_body: bool = False,
    ) -> ls_types.UnifiedSymbolInformation | None:
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
            absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
            content = FileUtils.read_file(self.logger, absolute_file_path)
            if content.split("\n")[line].strip() == "":
                self.logger.log(
                    f"Passing empty lines to request_container_symbol is currently not supported, {relative_file_path=}, {line=}",
                    logging.ERROR,
                )
                return None

        symbols, _ = self.request_document_symbols(relative_file_path)

        # make jedi and pyright api compatible
        # the former has no location, the later has no range
        # we will just always add location of the desired format to all symbols
        for symbol in symbols:
            if "location" not in symbol:
                range = symbol["range"]
                location = ls_types.Location(
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
        container_symbol_kinds = {ls_types.SymbolKind.Method, ls_types.SymbolKind.Function, ls_types.SymbolKind.Class}

        def is_position_in_range(line: int, range_d: ls_types.Range) -> bool:
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
            s
            for s in symbols
            if s["kind"] in container_symbol_kinds and s["location"]["range"]["start"]["line"] != s["location"]["range"]["end"]["line"]
        ]
        var_containers = [s for s in symbols if s["kind"] == ls_types.SymbolKind.Variable]
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

    def request_container_of_symbol(
        self, symbol: ls_types.UnifiedSymbolInformation, include_body: bool = False
    ) -> ls_types.UnifiedSymbolInformation | None:
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
        return self.request_containing_symbol(
            symbol["location"]["relativePath"],
            symbol["location"]["range"]["start"]["line"],
            symbol["location"]["range"]["start"]["character"],
            strict=True,
            include_body=include_body,
        )

    def request_defining_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_body: bool = False,
    ) -> ls_types.UnifiedSymbolInformation | None:
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
            raise SolidLSPException("Language Server not started")

        # Get the definition location(s)
        definitions = self.request_definition(relative_file_path, line, column)
        if not definitions:
            return None

        # Use the first definition location
        definition = definitions[0]
        def_path = definition["relativePath"]
        def_line = definition["range"]["start"]["line"]
        def_col = definition["range"]["start"]["character"]

        # Find the symbol at or containing this location
        defining_symbol = self.request_containing_symbol(def_path, def_line, def_col, strict=False, include_body=include_body)

        return defining_symbol

    @property
    def cache_path(self) -> Path:
        """
        The path to the cache file for the document symbols.
        """
        return Path(self.repository_root_path) / ".serena" / "cache" / self.language_id / "document_symbols_cache_v23-06-25.pkl"

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

    def request_workspace_symbol(self, query: str) -> list[ls_types.UnifiedSymbolInformation] | None:
        """
        Raise a [workspace/symbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_symbol) request to the Language Server
        to find symbols across the whole workspace. Wait for the response and return the result.

        :param query: The query string to filter symbols by

        :return: A list of matching symbols
        """
        response = self.server.send.workspace_symbol({"query": query})
        if response is None:
            return None

        assert isinstance(response, list)

        ret: list[ls_types.UnifiedSymbolInformation] = []
        for item in response:
            assert isinstance(item, dict)

            assert LSPConstants.NAME in item
            assert LSPConstants.KIND in item
            assert LSPConstants.LOCATION in item

            ret.append(ls_types.UnifiedSymbolInformation(**item))

        return ret

    def start(self) -> "SolidLanguageServer":
        """
        Starts the language server process and connects to it. Call shutdown when ready.

        :return: self for method chaining
        """
        self.logger.log(
            f"Starting language server with language {self.language_server.language} for {self.language_server.repository_root_path}",
            logging.INFO,
        )
        self._server_context = self._start_server_process()
        return self

    def stop(self, shutdown_timeout: float = 2.0) -> None:
        self._shutdown(timeout=shutdown_timeout)

    @property
    def language_server(self) -> Self:
        return self

    def is_running(self) -> bool:
        return self.server.is_running()
