import dataclasses
import hashlib
import json
import logging
import os
import pathlib
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from copy import copy
from pathlib import Path, PurePath
from time import sleep
from typing import Self, Union, cast

import pathspec
from sensai.util.pickle import getstate, load_pickle

from serena.text_utils import MatchedConsecutiveLines
from serena.util.file_system import match_path
from solidlsp import ls_types
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_handler import SolidLanguageServerHandler
from solidlsp.ls_types import UnifiedSymbolInformation
from solidlsp.ls_utils import FileUtils, PathUtils, TextUtils
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler import lsp_types as LSPTypes
from solidlsp.lsp_protocol_handler.lsp_constants import LSPConstants
from solidlsp.lsp_protocol_handler.lsp_types import (
    Definition,
    DefinitionParams,
    DocumentSymbol,
    LocationLink,
    RenameParams,
    SymbolInformation,
)
from solidlsp.lsp_protocol_handler.server import (
    LSPError,
    ProcessLaunchInfo,
    StringDict,
)
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.cache import load_cache, save_cache

GenericDocumentSymbol = Union[LSPTypes.DocumentSymbol, LSPTypes.SymbolInformation, ls_types.UnifiedSymbolInformation]
log = logging.getLogger(__name__)


@dataclasses.dataclass(kw_only=True)
class ReferenceInSymbol:
    """A symbol retrieved when requesting reference to a symbol, together with the location of the reference"""

    symbol: ls_types.UnifiedSymbolInformation
    line: int
    character: int


class LSPFileBuffer:
    """
    This class is used to store the contents of an open LSP file in memory.
    """

    def __init__(self, uri: str, contents: str, encoding: str, version: int, language_id: str, ref_count: int) -> None:
        self.uri = uri
        self.contents = contents
        self.version = version
        self.language_id = language_id
        self.ref_count = ref_count
        self.encoding = encoding
        self._content_hash: str | None = None

    @property
    def content_hash(self) -> str:
        if self._content_hash is None:
            self._content_hash = hashlib.md5(self.contents.encode(self.encoding)).hexdigest()
        return self._content_hash

    def split_lines(self) -> list[str]:
        """Splits the contents of the file into lines."""
        return self.contents.split("\n")


class DocumentSymbols:
    # IMPORTANT: Instances of this class are persisted in the high-level document symbol cache

    def __init__(self, root_symbols: list[ls_types.UnifiedSymbolInformation]):
        self.root_symbols = root_symbols
        self._all_symbols: list[ls_types.UnifiedSymbolInformation] | None = None

    def __getstate__(self) -> dict:
        return getstate(DocumentSymbols, self, transient_properties=["_all_symbols"])

    def iter_symbols(self) -> Iterator[ls_types.UnifiedSymbolInformation]:
        """
        Iterate over all symbols in the document symbol tree.
        Yields symbols in a depth-first manner.
        """
        if self._all_symbols is not None:
            yield from self._all_symbols
            return

        def traverse(s: ls_types.UnifiedSymbolInformation) -> Iterator[ls_types.UnifiedSymbolInformation]:
            yield s
            for child in s.get("children", []):
                yield from traverse(child)

        for root_symbol in self.root_symbols:
            yield from traverse(root_symbol)

    def get_all_symbols_and_roots(self) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
        """
        This function returns all symbols in the document as a flat list and the root symbols.
        It exists to facilitate migration from previous versions, where this was the return interface of
        the LS method that obtained document symbols.

        :return: A tuple containing a list of all symbols in the document and a list of root symbols.
        """
        if self._all_symbols is None:
            self._all_symbols = list(self.iter_symbols())
        return self._all_symbols, self.root_symbols


class LanguageServerDependencyProvider(ABC):
    """
    Prepares dependencies for a language server (if any), ultimately enabling the launch command to be constructed
    and optionally providing environment variables that are necessary for the execution.
    """

    def __init__(self, custom_settings: SolidLSPSettings.CustomLSSettings, ls_resources_dir: str):
        self._custom_settings = custom_settings
        self._ls_resources_dir = ls_resources_dir

    @abstractmethod
    def create_launch_command(self) -> list[str] | str:
        """
        Creates the launch command for this language server, potentially downloading and installing dependencies
        beforehand.

        :return: the launch command as a list containing the executable and its arguments (preferred for robustness)
           or the entire command in a single string.
        """

    def create_launch_command_env(self) -> dict[str, str]:
        """
        Provides environment variables to be set when executing the launch command.

        This method is intended to be overridden by subclasses that need to set variables.

        :return: a mapping for variable names to values
        """
        return {}


class LanguageServerDependencyProviderSinglePath(LanguageServerDependencyProvider, ABC):
    """
    Special case of a dependency provider, where there is a single core dependency which provides
    the basis for the launch command.

    The core dependency's path can be overridden by the user in LS-specific settings (SerenaConfig)
    via the key "ls_path". If the user provides the key, the specified path is used directly.
    Otherwise, the provider implementation is called to get or install the core dependency.
    """

    @abstractmethod
    def _get_or_install_core_dependency(self) -> str:
        """
        Gets the language server's core path, potentially installing dependencies beforehand.

        :return: the core dependency's path (e.g. executable, jar, etc.)
        """

    def create_launch_command(self) -> Union[str, list[str]]:
        path = self._custom_settings.get("ls_path", None)
        if path is not None:
            core_path = path
        else:
            core_path = self._get_or_install_core_dependency()
        return self._create_launch_command(core_path)

    @abstractmethod
    def _create_launch_command(self, core_path: str) -> list[str] | str:
        """
        :param core_path: path to the core dependency
        :return: the launch command as a list containing the executable and its arguments (preferred for robustness)
           or the entire command in a single string.
        """


class SolidLanguageServer(ABC):
    """
    The LanguageServer class provides a language agnostic interface to the Language Server Protocol.
    It is used to communicate with Language Servers of different programming languages.
    """

    CACHE_FOLDER_NAME = "cache"
    RAW_DOCUMENT_SYMBOLS_CACHE_VERSION = 1
    """
    global version identifier for raw symbol caches; an LS-specific version is defined separately and combined with this.
    This should be incremented whenever there is a change in the way raw document symbols are stored.
    If the result of a language server changes in a way that affects the raw document symbols,
    the LS-specific version should be incremented instead.
    """
    RAW_DOCUMENT_SYMBOL_CACHE_FILENAME = "raw_document_symbols.pkl"
    RAW_DOCUMENT_SYMBOL_CACHE_FILENAME_LEGACY_FALLBACK = "document_symbols_cache_v23-06-25.pkl"
    DOCUMENT_SYMBOL_CACHE_VERSION = 3
    DOCUMENT_SYMBOL_CACHE_FILENAME = "document_symbols.pkl"

    # To be overridden and extended by subclasses
    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        A language-specific condition for directories that should always be ignored. For example, venv
        in Python and node_modules in JS/TS should be ignored always.
        """
        return dirname.startswith(".")

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """
        Classify a stderr line from the language server to determine appropriate logging level.

        Language servers may emit informational messages to stderr that contain words like "error"
        but are not actual errors. Subclasses can override this method to filter out known
        false-positive patterns specific to their language server.

        :param line: The stderr line to classify
        :return: A logging level (logging.DEBUG, logging.INFO, logging.WARNING, or logging.ERROR)
        """
        line_lower = line.lower()

        # Default classification: treat lines with "error" or "exception" as ERROR level
        if "error" in line_lower or "exception" in line_lower or line.startswith("E["):
            return logging.ERROR
        else:
            return logging.INFO

    @classmethod
    def get_language_enum_instance(cls) -> Language:
        return Language.from_ls_class(cls)

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
        repository_root_path: str,
        timeout: float | None = None,
        solidlsp_settings: SolidLSPSettings | None = None,
    ) -> "SolidLanguageServer":
        """
        Creates a language specific LanguageServer instance based on the given configuration, and appropriate settings for the programming language.

        If language is Java, then ensure that jdk-17.0.6 or higher is installed, `java` is in PATH, and JAVA_HOME is set to the installation directory.
        If language is JS/TS, then ensure that node (v18.16.0 or higher) is installed and in PATH.

        :param repository_root_path: The root path of the repository.
        :param config: language server configuration.
        :param logger: The logger to use.
        :param timeout: the timeout for requests to the language server. If None, no timeout will be used.
        :param solidlsp_settings: additional settings
        :return LanguageServer: A language specific LanguageServer instance.
        """
        ls: SolidLanguageServer
        if solidlsp_settings is None:
            solidlsp_settings = SolidLSPSettings()

        # Ensure repository_root_path is absolute to avoid issues with file URIs
        repository_root_path = os.path.abspath(repository_root_path)

        ls_class = config.code_language.get_ls_class()
        # For now, we assume that all language server implementations have the same signature of the constructor
        # (which, unfortunately, differs from the signature of the base class).
        # If this assumption is ever violated, we need branching logic here.
        ls = ls_class(config, repository_root_path, solidlsp_settings)  # type: ignore
        ls.set_request_timeout(timeout)
        return ls

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        process_launch_info: ProcessLaunchInfo | None,
        language_id: str,
        solidlsp_settings: SolidLSPSettings,
        cache_version_raw_document_symbols: Hashable = 1,
    ):
        """
        Initializes a LanguageServer instance.

        Do not instantiate this class directly. Use `LanguageServer.create` method instead.

        :param config: the global SolidLSP configuration.
        :param repository_root_path: the root path of the repository.
        :param process_launch_info: (DEPRECATED - implement _create_dependency_provider instead)
            the command used to start the actual language server.
            The command must pass appropriate flags to the binary, so that it runs in the stdio mode,
            as opposed to HTTP, TCP modes supported by some language servers.
        :param cache_version_raw_document_symbols: the version, for caching, of the raw document symbols coming
            from this specific language server. This should be incremented by subclasses calling this constructor
            whenever the format of the raw document symbols changes (typically because the language server
            improves/fixes its output).
        """
        self._solidlsp_settings = solidlsp_settings
        lang = self.get_language_enum_instance()
        self._custom_settings = solidlsp_settings.get_ls_specific_settings(lang)
        self._ls_resources_dir = self.ls_resources_dir(solidlsp_settings)
        log.debug(f"Custom config (LS-specific settings) for {lang}: {self._custom_settings}")
        self._encoding = config.encoding
        self.repository_root_path: str = repository_root_path

        log.debug(
            f"Creating language server instance for {repository_root_path=} with {language_id=} and process launch info: {process_launch_info}"
        )

        self.language_id = language_id
        self.open_file_buffers: dict[str, LSPFileBuffer] = {}
        self.language = Language(language_id)

        # initialise symbol caches
        self.cache_dir = (
            Path(self.repository_root_path) / self._solidlsp_settings.project_data_relative_path / self.CACHE_FOLDER_NAME / self.language_id
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # * raw document symbols cache
        self._ls_specific_raw_document_symbols_cache_version = cache_version_raw_document_symbols
        self._raw_document_symbols_cache: dict[str, tuple[str, list[DocumentSymbol] | list[SymbolInformation] | None]] = {}
        """maps relative file paths to a tuple of (file_content_hash, raw_root_symbols)"""
        self._raw_document_symbols_cache_is_modified: bool = False
        self._load_raw_document_symbols_cache()
        # * high-level document symbols cache
        self._document_symbols_cache: dict[str, tuple[str, DocumentSymbols]] = {}
        """maps relative file paths to a tuple of (file_content_hash, document_symbols)"""
        self._document_symbols_cache_is_modified: bool = False
        self._load_document_symbols_cache()

        self.server_started = False
        self.completions_available = threading.Event()
        if config.trace_lsp_communication:

            def logging_fn(source: str, target: str, msg: StringDict | str) -> None:
                log.debug(f"LSP: {source} -> {target}: {msg!s}")

        else:
            logging_fn = None  # type: ignore

        # create the LanguageServerHandler, which provides the functionality to start the language server and communicate with it,
        # preparing the launch command beforehand
        self._dependency_provider: LanguageServerDependencyProvider | None = None
        if process_launch_info is None:
            self._dependency_provider = self._create_dependency_provider()
            process_launch_info = self._create_process_launch_info()
        log.debug(f"Creating language server instance with {language_id=} and process launch info: {process_launch_info}")
        self.server = SolidLanguageServerHandler(
            process_launch_info,
            language=self.language,
            determine_log_level=self._determine_log_level,
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
        log.debug(f"Processing {len(processed_patterns)} ignored paths from the config")

        # Create a pathspec matcher from the processed patterns
        self._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, processed_patterns)

        self._request_timeout: float | None = None

        self._has_waited_for_cross_file_references = False

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        """
        Creates the dependency provider for this language server.

        Subclasses should override this method to provide their specific dependency provider.
        This method is only called if process_launch_info is not passed to __init__.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _create_dependency_provider() or pass process_launch_info to __init__()"
        )

    def _create_process_launch_info(self) -> ProcessLaunchInfo:
        assert self._dependency_provider is not None
        cmd = self._dependency_provider.create_launch_command()
        env = self._dependency_provider.create_launch_command_env()
        return ProcessLaunchInfo(cmd=cmd, cwd=self.repository_root_path, env=env)

    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Meant to be overridden by subclasses for LS that don't have a reliable "finished initializing" signal.

        LS may return incomplete results on calls to `request_references` (only references found in the same file),
        if the LS is not fully initialized yet.
        """
        return 2

    def set_request_timeout(self, timeout: float | None) -> None:
        """
        :param timeout: the timeout, in seconds, for requests to the language server.
        """
        self.server.set_request_timeout(timeout)

    def get_ignore_spec(self) -> pathspec.PathSpec:
        """
        Returns the pathspec matcher for the paths that were configured to be ignored through
        the language server configuration.

        This is a subset of the full language-specific ignore spec that determines
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

    def _shutdown(self, timeout: float = 5.0) -> None:
        """
        A robust shutdown process designed to terminate cleanly on all platforms, including Windows,
        by explicitly closing all I/O pipes.
        """
        if not self.server.is_running():
            log.debug("Server process not running, skipping shutdown.")
            return

        log.info(f"Initiating final robust shutdown with a {timeout}s timeout...")
        process = self.server.process
        if process is None:
            log.debug("Server process is None, cannot shutdown.")
            return

        # --- Main Shutdown Logic ---
        # Stage 1: Graceful Termination Request
        # Send LSP shutdown and close stdin to signal no more input.
        try:
            log.debug("Sending LSP shutdown request...")
            # Use a thread to timeout the LSP shutdown call since it can hang
            shutdown_thread = threading.Thread(target=self.server.shutdown)
            shutdown_thread.daemon = True
            shutdown_thread.start()
            shutdown_thread.join(timeout=2.0)  # 2 second timeout for LSP shutdown

            if shutdown_thread.is_alive():
                log.debug("LSP shutdown request timed out, proceeding to terminate...")
            else:
                log.debug("LSP shutdown request completed.")

            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            log.debug("Stage 1 shutdown complete.")
        except Exception as e:
            log.debug(f"Exception during graceful shutdown: {e}")
            # Ignore errors here, we are proceeding to terminate anyway.

        # Stage 2: Terminate and Wait for Process to Exit
        log.debug(f"Terminating process {process.pid}, current status: {process.poll()}")
        process.terminate()

        # Stage 3: Wait for process termination with timeout
        try:
            log.debug(f"Waiting for process {process.pid} to terminate...")
            exit_code = process.wait(timeout=timeout)
            log.info(f"Language server process terminated successfully with exit code {exit_code}.")
        except subprocess.TimeoutExpired:
            # If termination failed, forcefully kill the process
            log.warning(f"Process {process.pid} termination timed out, killing process forcefully...")
            process.kill()
            try:
                exit_code = process.wait(timeout=2.0)
                log.info(f"Language server process killed successfully with exit code {exit_code}.")
            except subprocess.TimeoutExpired:
                log.error(f"Process {process.pid} could not be killed within timeout.")
        except Exception as e:
            log.error(f"Error during process shutdown: {e}")

    @contextmanager
    def start_server(self) -> Iterator["SolidLanguageServer"]:
        self.start()
        yield self
        self.stop()

    def _start_server_process(self) -> None:
        self.server_started = True
        self._start_server()

    @abstractmethod
    def _start_server(self) -> None:
        pass

    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """Return the language ID for a file.

        Override in subclasses to return file-specific language IDs.
        Default implementation returns self.language_id.
        """
        return self.language_id

    @contextmanager
    def open_file(self, relative_file_path: str) -> Iterator[LSPFileBuffer]:
        """
        Open a file in the Language Server. This is required before making any requests to the Language Server.

        :param relative_file_path: The relative path of the file to open.
        """
        if not self.server_started:
            log.error("open_file called before Language Server started")
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
            contents = FileUtils.read_file(absolute_file_path, self._encoding)

            version = 0
            language_id = self._get_language_id_for_file(relative_file_path)
            self.open_file_buffers[uri] = LSPFileBuffer(
                uri=uri, contents=contents, encoding=self._encoding, version=version, language_id=language_id, ref_count=1
            )

            self.server.notify.did_open_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                        LSPConstants.LANGUAGE_ID: language_id,
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
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                    }
                }
            )
            del self.open_file_buffers[uri]

    @contextmanager
    def _open_file_context(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> Iterator[LSPFileBuffer]:
        """
        Internal context manager to open a file, optionally reusing an existing file buffer.

        :param relative_file_path: the relative path of the file to open.
        :param file_buffer: an optional existing file buffer to reuse.
        """
        if file_buffer is not None:
            yield file_buffer
        else:
            with self.open_file(relative_file_path) as fb:
                yield fb

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
            log.error("insert_text_at_position called before Language Server started")
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
                LSPConstants.TEXT_DOCUMENT: {  # type: ignore
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
            log.error("insert_text_at_position called before Language Server started")
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
                LSPConstants.TEXT_DOCUMENT: {  # type: ignore
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

        :return: the list of locations where the symbol is defined
        """
        if not self.server_started:
            log.error("request_definition called before language server started")
            raise SolidLSPException("Language Server not started")

        if not self._has_waited_for_cross_file_references:
            # Some LS require waiting for a while before they can return cross-file definitions.
            # This is a workaround for such LS that don't have a reliable "finished initializing" signal.
            sleep(self._get_wait_time_for_cross_file_referencing())
            self._has_waited_for_cross_file_references = True

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
                    new_item: dict = {}
                    new_item.update(item)
                    new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
                    new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
                    ret.append(ls_types.Location(**new_item))  # type: ignore
                elif LSPConstants.TARGET_URI in item and LSPConstants.TARGET_RANGE in item and LSPConstants.TARGET_SELECTION_RANGE in item:
                    new_item: dict = {}  # type: ignore
                    new_item["uri"] = item[LSPConstants.TARGET_URI]  # type: ignore
                    new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
                    new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
                    new_item["range"] = item[LSPConstants.TARGET_SELECTION_RANGE]  # type: ignore
                    ret.append(ls_types.Location(**new_item))  # type: ignore
                else:
                    assert False, f"Unexpected response from Language Server: {item}"
        elif isinstance(response, dict):
            # response is of type Location
            assert LSPConstants.URI in response
            assert LSPConstants.RANGE in response

            new_item: dict = {}  # type: ignore
            new_item.update(response)
            new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
            new_item["relativePath"] = PathUtils.get_relative_path(new_item["absolutePath"], self.repository_root_path)
            ret.append(ls_types.Location(**new_item))  # type: ignore
        elif response is None:
            # Some language servers return None when they cannot find a definition
            # This is expected for certain symbol types like generics or types with incomplete information
            log.warning(f"Language server returned None for definition request at {relative_file_path}:{line}:{column}")
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
            log.error("request_references called before Language Server started")
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

            abs_path = PathUtils.uri_to_path(item[LSPConstants.URI])  # type: ignore
            if not Path(abs_path).is_relative_to(self.repository_root_path):
                log.warning(
                    "Found a reference in a path outside the repository, probably the LS is parsing things in installed packages or in the standardlib! "
                    f"Path: {abs_path}. This is a bug but we currently simply skip these references."
                )
                continue

            rel_path = Path(abs_path).relative_to(self.repository_root_path)
            if self.is_ignored_path(str(rel_path)):
                log.debug("Ignoring reference in %s since it should be ignored", rel_path)
                continue

            new_item: dict = {}
            new_item.update(item)
            new_item["absolutePath"] = str(abs_path)
            new_item["relativePath"] = str(rel_path)
            ret.append(ls_types.Location(**new_item))  # type: ignore

        return ret

    def request_text_document_diagnostics(self, relative_file_path: str) -> list[ls_types.Diagnostic]:
        """
        Raise a [textDocument/diagnostic](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_diagnostic) request to the Language Server
        to find diagnostics for the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file to retrieve diagnostics for

        :return: A list of diagnostics for the file
        """
        if not self.server_started:
            log.error("request_text_document_diagnostics called before Language Server started")
            raise SolidLSPException("Language Server not started")

        with self.open_file(relative_file_path):
            response = self.server.send.text_document_diagnostic(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: pathlib.Path(str(PurePath(self.repository_root_path, relative_file_path))).as_uri()
                    }
                }
            )

        if response is None:
            return []  # type: ignore

        assert isinstance(response, dict), f"Unexpected response from Language Server (expected list, got {type(response)}): {response}"
        ret: list[ls_types.Diagnostic] = []
        for item in response["items"]:  # type: ignore
            new_item: ls_types.Diagnostic = {
                "uri": pathlib.Path(str(PurePath(self.repository_root_path, relative_file_path))).as_uri(),
                "severity": item["severity"],
                "message": item["message"],
                "range": item["range"],
                "code": item["code"],  # type: ignore
            }
            ret.append(ls_types.Diagnostic(**new_item))

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

        :return: A list of completions
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
            while response is None or (response["isIncomplete"] and num_retries < 30):  # type: ignore
                self.completions_available.wait()
                response = self.server.send.completion(completion_params)
                if isinstance(response, list):
                    response = {"items": response, "isIncomplete": False}
                num_retries += 1

            # TODO: Understand how to appropriately handle `isIncomplete`
            if response is None or (response["isIncomplete"] and not allow_incomplete):  # type: ignore
                return []

            if "items" in response:
                response = response["items"]  # type: ignore

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
                    completion_item["kind"] = item["kind"]  # type: ignore
                elif "insertText" in item:  # type: ignore
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

                completion_item = ls_types.CompletionItem(**completion_item)  # type: ignore
                completions_list.append(completion_item)

            return [json.loads(json_repr) for json_repr in set(json.dumps(item, sort_keys=True) for item in completions_list)]

    def _request_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
        """
        Sends a [documentSymbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_documentSymbol)
        request to the language server to find symbols in the given file - or returns a cached result if available.

        :param relative_file_path: the relative path of the file that has the symbols.
        :param file_data: the file data buffer, if already opened. If None, the file will be opened in this method.
        :return: the list of root symbols in the file.
        """

        def get_cached_raw_document_symbols(cache_key: str, fd: LSPFileBuffer) -> list[SymbolInformation] | list[DocumentSymbol] | None:
            file_hash_and_result = self._raw_document_symbols_cache.get(cache_key)
            if file_hash_and_result is not None:
                file_hash, result = file_hash_and_result
                if file_hash == fd.content_hash:
                    log.debug("Returning cached raw document symbols for %s", relative_file_path)
                    return result
                else:
                    log.debug("Document content for %s has changed (raw symbol cache is not up-to-date)", relative_file_path)
            else:
                log.debug("No cache hit for raw document symbols symbols in %s", relative_file_path)
            return None

        def get_raw_document_symbols(fd: LSPFileBuffer) -> list[SymbolInformation] | list[DocumentSymbol] | None:
            # check for cached result
            cache_key = relative_file_path
            response = get_cached_raw_document_symbols(cache_key, fd)
            if response is not None:
                return response

            # no cached result, query language server
            log.debug(f"Requesting document symbols for {relative_file_path} from the Language Server")
            response = self.server.send.document_symbol(
                {"textDocument": {"uri": pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()}}
            )

            # update cache
            self._raw_document_symbols_cache[cache_key] = (fd.content_hash, response)
            self._raw_document_symbols_cache_is_modified = True

            return response

        if file_data is not None:
            return get_raw_document_symbols(file_data)
        else:
            with self.open_file(relative_file_path) as opened_file_data:
                return get_raw_document_symbols(opened_file_data)

    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        """
        Retrieves the collection of symbols in the given file

        :param relative_file_path: The relative path of the file that has the symbols
        :param file_buffer: an optional file buffer if the file is already opened.
        :return: the collection of symbols in the file.
            All contained symbols will have a location, children, and a parent attribute,
            where the parent attribute is None for root symbols.
            Note that this is slightly different from the call to request_full_symbol_tree,
            where the parent attribute will be the file symbol which in turn may have a package symbol as parent.
            If you need a symbol tree that contains file symbols as well, you should use `request_full_symbol_tree` instead.
        """
        with self._open_file_context(relative_file_path, file_buffer) as file_data:
            # check if the desired result is cached
            cache_key = relative_file_path
            file_hash_and_result = self._document_symbols_cache.get(cache_key)
            if file_hash_and_result is not None:
                file_hash, document_symbols = file_hash_and_result
                if file_hash == file_data.content_hash:
                    log.debug("Returning cached document symbols for %s", relative_file_path)
                    return document_symbols
                else:
                    log.debug("Cached document symbol content for %s has changed", relative_file_path)
            else:
                log.debug("No cache hit for document symbols in %s", relative_file_path)

            # no cached result: request the root symbols from the language server
            root_symbols = self._request_document_symbols(relative_file_path, file_data)

            if root_symbols is None:
                log.warning(
                    f"Received None response from the Language Server for document symbols in {relative_file_path}. "
                    f"This means the language server can't understand this file (possibly due to syntax errors). It may also be due to a bug or misconfiguration of the LS. "
                    f"Returning empty list",
                )
                return DocumentSymbols([])

            assert isinstance(root_symbols, list), f"Unexpected response from Language Server: {root_symbols}"
            log.debug("Received %d root symbols for %s from the language server", len(root_symbols), relative_file_path)

            file_lines = file_data.split_lines()

            def convert_to_unified_symbol(original_symbol_dict: GenericDocumentSymbol) -> ls_types.UnifiedSymbolInformation:
                """
                Converts the given symbol dictionary to the unified representation, ensuring
                that all required fields are present (except 'children' which is handled separately).

                :param original_symbol_dict: the item to augment
                :return: the augmented item (new object)
                """
                # noinspection PyInvalidCast
                item = cast(ls_types.UnifiedSymbolInformation, dict(original_symbol_dict))
                absolute_path = os.path.join(self.repository_root_path, relative_file_path)

                # handle missing location and path entries
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
                    location["absolutePath"] = absolute_path  # type: ignore
                if "relativePath" not in location:
                    location["relativePath"] = relative_file_path  # type: ignore

                if "body" not in item:
                    item["body"] = self.retrieve_symbol_body(item, file_lines=file_lines)

                # handle missing selectionRange
                if "selectionRange" not in item:
                    if "range" in item:
                        item["selectionRange"] = item["range"]
                    else:
                        item["selectionRange"] = item["location"]["range"]

                return item

            def convert_symbols_with_common_parent(
                symbols: list[DocumentSymbol] | list[SymbolInformation] | list[UnifiedSymbolInformation],
                parent: ls_types.UnifiedSymbolInformation | None,
            ) -> list[ls_types.UnifiedSymbolInformation]:
                """
                Converts the given symbols into UnifiedSymbolInformation with proper parent-child relationships,
                adding overload indices for symbols with the same name under the same parent.
                """
                total_name_counts: dict[str, int] = defaultdict(lambda: 0)
                for symbol in symbols:
                    total_name_counts[symbol["name"]] += 1
                name_counts: dict[str, int] = defaultdict(lambda: 0)
                unified_symbols = []
                for symbol in symbols:
                    usymbol = convert_to_unified_symbol(symbol)
                    if total_name_counts[usymbol["name"]] > 1:
                        usymbol["overload_idx"] = name_counts[usymbol["name"]]
                    name_counts[usymbol["name"]] += 1
                    usymbol["parent"] = parent
                    if "children" in usymbol:
                        usymbol["children"] = convert_symbols_with_common_parent(usymbol["children"], usymbol)  # type: ignore
                    else:
                        usymbol["children"] = []  # type: ignore
                    unified_symbols.append(usymbol)
                return unified_symbols

            unified_root_symbols = convert_symbols_with_common_parent(root_symbols, None)
            document_symbols = DocumentSymbols(unified_root_symbols)

            # update cache
            log.debug("Updating cached document symbols for %s", relative_file_path)
            self._document_symbols_cache[cache_key] = (file_data.content_hash, document_symbols)
            self._document_symbols_cache_is_modified = True

            return document_symbols

    def request_full_symbol_tree(self, within_relative_path: str | None = None) -> list[ls_types.UnifiedSymbolInformation]:
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
        :return: A list of root symbols representing the top-level packages/modules in the project.
        """
        if within_relative_path is not None:
            within_abs_path = os.path.join(self.repository_root_path, within_relative_path)
            if not os.path.exists(within_abs_path):
                raise FileNotFoundError(f"File or directory not found: {within_abs_path}")
            if os.path.isfile(within_abs_path):
                if self.is_ignored_path(within_relative_path):
                    log.error("You passed a file explicitly, but it is ignored. This is probably an error. File: %s", within_relative_path)
                    return []
                else:
                    root_nodes = self.request_document_symbols(within_relative_path).root_symbols
                    return root_nodes

        # Helper function to recursively process directories
        def process_directory(rel_dir_path: str) -> list[ls_types.UnifiedSymbolInformation]:
            abs_dir_path = self.repository_root_path if rel_dir_path == "." else os.path.join(self.repository_root_path, rel_dir_path)
            abs_dir_path = os.path.realpath(abs_dir_path)

            if self.is_ignored_path(str(Path(abs_dir_path).relative_to(self.repository_root_path))):
                log.debug("Skipping directory: %s (because it should be ignored)", rel_dir_path)
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

                # obtain relative path
                try:
                    contained_dir_or_file_rel_path = str(
                        Path(contained_dir_or_file_abs_path).resolve().relative_to(self.repository_root_path)
                    )
                except ValueError as e:
                    # Typically happens when the path is not under the repository root (e.g., symlink pointing outside)
                    log.warning(
                        "Skipping path %s; likely outside of the repository root %s [cause: %s]",
                        contained_dir_or_file_abs_path,
                        self.repository_root_path,
                        e,
                    )
                    continue

                if self.is_ignored_path(contained_dir_or_file_rel_path):
                    log.debug("Skipping item: %s (because it should be ignored)", contained_dir_or_file_rel_path)
                    continue

                if os.path.isdir(contained_dir_or_file_abs_path):
                    child_symbols = process_directory(contained_dir_or_file_rel_path)
                    package_symbol["children"].extend(child_symbols)
                    for child in child_symbols:
                        child["parent"] = package_symbol

                elif os.path.isfile(contained_dir_or_file_abs_path):
                    with self._open_file_context(contained_dir_or_file_rel_path) as file_data:
                        document_symbols = self.request_document_symbols(contained_dir_or_file_rel_path, file_data)
                        file_root_nodes = document_symbols.root_symbols

                        # Create file symbol, link with children
                        file_range = self._get_range_from_file_content(file_data.contents)
                        file_symbol = ls_types.UnifiedSymbolInformation(  # type: ignore
                            name=os.path.splitext(contained_dir_or_file_name)[0],
                            kind=ls_types.SymbolKind.File,
                            range=file_range,
                            selectionRange=file_range,
                            location=ls_types.Location(
                                uri=str(pathlib.Path(contained_dir_or_file_abs_path).as_uri()),
                                range=file_range,
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
                    def fix_relative_path(nodes: list[ls_types.UnifiedSymbolInformation]) -> None:
                        for node in nodes:
                            if "location" in node and "relativePath" in node["location"]:
                                path = Path(node["location"]["relativePath"])  # type: ignore
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
        def process_symbol(symbol: ls_types.UnifiedSymbolInformation) -> None:
            if symbol["kind"] == ls_types.SymbolKind.File:
                # For file symbols, process their children (top-level symbols)
                for child in symbol["children"]:
                    # Handle cross-platform path resolution (fixes Docker/macOS path issues)
                    absolute_path = Path(child["location"]["absolutePath"]).resolve()
                    repository_root = Path(self.repository_root_path).resolve()

                    # Try pathlib first, fallback to alternative approach if paths are incompatible
                    try:
                        path = absolute_path.relative_to(repository_root)
                    except ValueError:
                        # If paths are from different roots (e.g., /workspaces vs /Users),
                        # use the relativePath from location if available, or extract from absolutePath
                        if "relativePath" in child["location"] and child["location"]["relativePath"]:
                            path = Path(child["location"]["relativePath"])
                        else:
                            # Extract relative path by finding common structure
                            # Example: /workspaces/.../test_repo/file.py -> test_repo/file.py
                            path_parts = absolute_path.parts

                            # Find the last common part or use a fallback
                            if "test_repo" in path_parts:
                                test_repo_idx = path_parts.index("test_repo")
                                path = Path(*path_parts[test_repo_idx:])
                            else:
                                # Last resort: use filename only
                                path = Path(absolute_path.name)
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
        return self.request_document_symbols(relative_file_path).root_symbols

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
        """
        with self.open_file(relative_file_path):
            uri = pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()
            return self._request_hover(uri, line, column)

    def _request_hover(self, uri: str, line: int, column: int) -> ls_types.Hover | None:
        """
        Internal method that performs the actual hover request.
        The file must already be open when calling this method.
        Subclasses can override this to customize hover behavior (e.g., retries).

        :param uri: The URI of the file
        :param line: The line number of the symbol
        :param column: The column number of the symbol
        """
        response = self.server.send.hover(
            {
                "textDocument": {"uri": uri},
                "position": {
                    "line": line,
                    "character": column,
                },
            }
        )

        if response is None:
            return None

        assert isinstance(response, dict)
        contents = response.get("contents")
        if not contents:
            return None
        if isinstance(contents, dict) and not contents.get("value"):
            return None
        return ls_types.Hover(**response)  # type: ignore

    def request_signature_help(self, relative_file_path: str, line: int, column: int) -> ls_types.SignatureHelp | None:
        """
        Raise a [textDocument/signatureHelp](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_signatureHelp)
        request to the Language Server to find the signature help at the given line and column in the given file.
        Note: contrary to `hover`, this only returns something on the position of a *call* and not on a symbol definition.
        This means for Serena's purposes, this method is not particularly useful. The result is also fairly verbose (but well structured).

        :param relative_file_path: The relative path of the file that has the signature help
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return None
        """
        with self.open_file(relative_file_path):
            response = self.server.send.signature_help(
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

        return ls_types.SignatureHelp(**response)  # type: ignore

    def retrieve_symbol_body(
        self,
        symbol: ls_types.UnifiedSymbolInformation | LSPTypes.SymbolInformation,
        file_lines: list[str] | None = None,
        file_buffer: LSPFileBuffer | None = None,
    ) -> str:
        """
        Load the body of the given symbol. If the body is already contained in the symbol, just return it.
        """
        existing_body = symbol.get("body", None)
        if existing_body:
            return str(existing_body)

        assert "location" in symbol
        symbol_start_line = symbol["location"]["range"]["start"]["line"]
        symbol_end_line = symbol["location"]["range"]["end"]["line"]
        assert "relativePath" in symbol["location"]
        if file_lines is None:
            with self._open_file_context(symbol["location"]["relativePath"], file_buffer) as f:  # type: ignore
                file_lines = f.split_lines()
        symbol_body = "\n".join(file_lines[symbol_start_line : symbol_end_line + 1])

        # remove leading indentation
        symbol_start_column = symbol["location"]["range"]["start"]["character"]  # type: ignore
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
            log.error("request_referencing_symbols called before Language Server started")
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
            assert ref_path is not None
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
                        document_symbols = self.request_document_symbols(ref_path)
                        for symbol in document_symbols.iter_symbols():
                            if symbol["name"] == containing_symbol_name and symbol["kind"] == ls_types.SymbolKind.Variable:
                                containing_symbol = copy(symbol)
                                containing_symbol["location"] = ref
                                containing_symbol["range"] = ref["range"]
                                break

                # We failed retrieving the symbol, falling back to creating a file symbol
                if containing_symbol is None and include_file_symbols:
                    log.warning(f"Could not find containing symbol for {ref_path}:{ref_line}:{ref_col}. Returning file symbol instead")
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
                    log.debug(f"Found self-reference for {incoming_symbol['name']}, skipping it since {include_self=}")
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
                    log.debug(
                        f"Found import of referenced symbol {incoming_symbol['name']}"
                        f"in {containing_symbol['location']['relativePath']}, skipping"
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
            content = FileUtils.read_file(absolute_file_path, self._encoding)
            if content.split("\n")[line].strip() == "":
                log.error(f"Passing empty lines to request_container_symbol is currently not supported, {relative_file_path=}, {line=}")
                return None

        document_symbols = self.request_document_symbols(relative_file_path)

        # make jedi and pyright api compatible
        # the former has no location, the later has no range
        # we will just always add location of the desired format to all symbols
        for symbol in document_symbols.iter_symbols():
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
            for s in document_symbols.iter_symbols()
            if s["kind"] in container_symbol_kinds and s["location"]["range"]["start"]["line"] != s["location"]["range"]["end"]["line"]
        ]
        var_containers = [s for s in document_symbols.iter_symbols() if s["kind"] == ls_types.SymbolKind.Variable]
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
            symbol["location"]["relativePath"],  # type: ignore
            symbol["location"]["range"]["start"]["line"],
            symbol["location"]["range"]["start"]["character"],
            strict=True,
            include_body=include_body,
        )

    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        """
        Select the preferred definition from a list of definitions.

        When multiple definitions are returned (e.g., both source and type definitions),
        this method determines which one to use. The base implementation simply returns
        the first definition.

        Subclasses can override this method to implement language-specific preferences.
        For example, TypeScript/Vue servers may prefer source files over .d.ts type
        definition files.

        :param definitions: A non-empty list of definition locations.
        :return: The preferred definition location.
        """
        return definitions[0]

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
            log.error("request_defining_symbol called before language server started")
            raise SolidLSPException("Language Server not started")

        # Get the definition location(s)
        definitions = self.request_definition(relative_file_path, line, column)
        if not definitions:
            return None

        # Select the preferred definition (subclasses can override _get_preferred_definition)
        definition = self._get_preferred_definition(definitions)
        def_path = definition["relativePath"]
        assert def_path is not None
        def_line = definition["range"]["start"]["line"]
        def_col = definition["range"]["start"]["character"]

        # Find the symbol at or containing this location
        defining_symbol = self.request_containing_symbol(def_path, def_line, def_col, strict=False, include_body=include_body)

        return defining_symbol

    def _cache_context_fingerprint(self) -> Hashable | None:
        """
        Return a fingerprint of any language-server-specific context that affects cached results.

        Subclasses may override to provide a deterministic value that changes when cached results
        would be invalidated (e.g., build flags, environment variables).

        The value must be hashable and safe for inclusion in cache version tuples.
        Returns None if no context-specific fingerprint is needed.
        """
        return None

    def _document_symbols_cache_version(self) -> Hashable:
        """
        Return the version for the document symbols cache.

        Incorporates cache context fingerprint if provided by the language server.
        """
        fingerprint = self._cache_context_fingerprint()
        if fingerprint is not None:
            return (self.DOCUMENT_SYMBOL_CACHE_VERSION, fingerprint)
        return self.DOCUMENT_SYMBOL_CACHE_VERSION

    def _save_raw_document_symbols_cache(self) -> None:
        cache_file = self.cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME

        if not self._raw_document_symbols_cache_is_modified:
            log.debug("No changes to raw document symbols cache, skipping save")
            return

        log.info("Saving updated raw document symbols cache to %s", cache_file)
        try:
            save_cache(str(cache_file), self._raw_document_symbols_cache_version(), self._raw_document_symbols_cache)
            self._raw_document_symbols_cache_is_modified = False
        except Exception as e:
            log.error(
                "Failed to save raw document symbols cache to %s: %s. Note: this may have resulted in a corrupted cache file.",
                cache_file,
                e,
            )

    def _raw_document_symbols_cache_version(self) -> tuple[Hashable, ...]:
        base_version: tuple[Hashable, ...] = (self.RAW_DOCUMENT_SYMBOLS_CACHE_VERSION, self._ls_specific_raw_document_symbols_cache_version)
        fingerprint = self._cache_context_fingerprint()
        if fingerprint is not None:
            return (*base_version, fingerprint)
        return base_version

    def _load_raw_document_symbols_cache(self) -> None:
        cache_file = self.cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME

        if not cache_file.exists():
            # check for legacy cache to load to migrate
            legacy_cache_file = self.cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME_LEGACY_FALLBACK
            if legacy_cache_file.exists():
                try:
                    legacy_cache: dict[
                        str, tuple[str, tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]]
                    ] = load_pickle(legacy_cache_file)
                    log.info("Migrating legacy document symbols cache with %d entries", len(legacy_cache))
                    num_symbols_migrated = 0
                    migrated_cache = {}
                    for cache_key, (file_hash, (all_symbols, root_symbols)) in legacy_cache.items():
                        if cache_key.endswith("-True"):  # include_body=True
                            new_cache_key = cache_key[:-5]
                            migrated_cache[new_cache_key] = (file_hash, root_symbols)
                            num_symbols_migrated += len(all_symbols)
                    log.info("Migrated %d document symbols from legacy cache", num_symbols_migrated)
                    self._raw_document_symbols_cache = migrated_cache  # type: ignore
                    self._raw_document_symbols_cache_is_modified = True
                    self._save_raw_document_symbols_cache()
                    legacy_cache_file.unlink()
                    return
                except Exception as e:
                    log.error("Error during cache migration: %s", e)
                    return

        # load existing cache (if any)
        if cache_file.exists():
            log.info("Loading document symbols cache from %s", cache_file)
            try:
                saved_cache = load_cache(str(cache_file), self._raw_document_symbols_cache_version())
                if saved_cache is not None:
                    self._raw_document_symbols_cache = saved_cache
                    log.info(f"Loaded {len(self._raw_document_symbols_cache)} entries from raw document symbols cache.")
            except Exception as e:
                # cache can become corrupt, so just skip loading it
                log.warning(
                    "Failed to load raw document symbols cache from %s (%s); Ignoring cache.",
                    cache_file,
                    e,
                )

    def _save_document_symbols_cache(self) -> None:
        cache_file = self.cache_dir / self.DOCUMENT_SYMBOL_CACHE_FILENAME

        if not self._document_symbols_cache_is_modified:
            log.debug("No changes to document symbols cache, skipping save")
            return

        log.info("Saving updated document symbols cache to %s", cache_file)
        try:
            save_cache(str(cache_file), self._document_symbols_cache_version(), self._document_symbols_cache)
            self._document_symbols_cache_is_modified = False
        except Exception as e:
            log.error(
                "Failed to save document symbols cache to %s: %s. Note: this may have resulted in a corrupted cache file.",
                cache_file,
                e,
            )

    def _load_document_symbols_cache(self) -> None:
        cache_file = self.cache_dir / self.DOCUMENT_SYMBOL_CACHE_FILENAME
        if cache_file.exists():
            log.info("Loading document symbols cache from %s", cache_file)
            try:
                saved_cache = load_cache(str(cache_file), self._document_symbols_cache_version())
                if saved_cache is not None:
                    self._document_symbols_cache = saved_cache
                    log.info(f"Loaded {len(self._document_symbols_cache)} entries from document symbols cache.")
            except Exception as e:
                # cache can become corrupt, so just skip loading it
                log.warning(
                    "Failed to load document symbols cache from %s (%s); Ignoring cache.",
                    cache_file,
                    e,
                )

    def save_cache(self) -> None:
        self._save_raw_document_symbols_cache()
        self._save_document_symbols_cache()

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

            ret.append(ls_types.UnifiedSymbolInformation(**item))  # type: ignore

        return ret

    def request_rename_symbol_edit(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        new_name: str,
    ) -> ls_types.WorkspaceEdit | None:
        """
        Retrieve a WorkspaceEdit for renaming the symbol at the given location to the new name.
        Does not apply the edit, just retrieves it. In order to actually rename the symbol, call apply_workspace_edit.

        :param relative_file_path: The relative path to the file containing the symbol
        :param line: The 0-indexed line number of the symbol
        :param column: The 0-indexed column number of the symbol
        :param new_name: The new name for the symbol
        :return: A WorkspaceEdit containing the changes needed to rename the symbol, or None if rename is not supported
        """
        params = RenameParams(
            textDocument=ls_types.TextDocumentIdentifier(
                uri=pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()
            ),
            position=ls_types.Position(line=line, character=column),
            newName=new_name,
        )

        return self.server.send.rename(params)

    def apply_text_edits_to_file(self, relative_path: str, edits: list[ls_types.TextEdit]) -> None:
        """
        Apply a list of text edits to a file.

        :param relative_path: The relative path of the file to edit
        :param edits: List of TextEdit dictionaries to apply
        """
        with self.open_file(relative_path):
            # Sort edits by position (latest first) to avoid position shifts
            sorted_edits = sorted(edits, key=lambda e: (e["range"]["start"]["line"], e["range"]["start"]["character"]), reverse=True)

            for edit in sorted_edits:
                start_pos = ls_types.Position(line=edit["range"]["start"]["line"], character=edit["range"]["start"]["character"])
                end_pos = ls_types.Position(line=edit["range"]["end"]["line"], character=edit["range"]["end"]["character"])

                # Delete the old text and insert the new text
                self.delete_text_between_positions(relative_path, start_pos, end_pos)
                self.insert_text_at_position(relative_path, start_pos["line"], start_pos["character"], edit["newText"])

    def start(self) -> "SolidLanguageServer":
        """
        Starts the language server process and connects to it. Call shutdown when ready.

        :return: self for method chaining
        """
        log.info(f"Starting language server with language {self.language_server.language} for {self.language_server.repository_root_path}")
        self._start_server_process()
        return self

    def stop(self, shutdown_timeout: float = 2.0) -> None:
        """
        Stops the language server process.
        This function never raises an exception (any exceptions during shutdown are logged).

        :param shutdown_timeout: time, in seconds, to wait for the server to shutdown gracefully before killing it
        """
        try:
            self._shutdown(timeout=shutdown_timeout)
        except Exception as e:
            log.warning(f"Exception while shutting down language server: {e}")

    @property
    def language_server(self) -> Self:
        return self

    @property
    def handler(self) -> SolidLanguageServerHandler:
        """Access the underlying language server handler.

        Useful for advanced operations like sending custom commands
        or registering notification handlers.
        """
        return self.server

    def is_running(self) -> bool:
        return self.server.is_running()
