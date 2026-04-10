"""
Provides Haxe specific instantiation of the LanguageServer class.
Uses the vshaxe/haxe-language-server (https://github.com/vshaxe/haxe-language-server),
which is an LSP implementation that delegates to the Haxe compiler for analysis.

Requires Node.js and the Haxe compiler (3.4.0+) to be installed.

You can pass the following entries in ls_specific_settings["haxe"]:
    - ls_path: Path to a pre-built server.js (from vshaxe or VS Code extension)
    - build_file: Path to the .hxml build file for display arguments (default: auto-detected)
    - haxe_executable: Path to the Haxe compiler executable (default: "haxe" from PATH)
    - working_directory: Subdirectory to use as the Haxe compiler's CWD (default: project root)
"""

import glob
import logging
import os
import pathlib
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import LanguageServerDependencyProviderSinglePath, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_process import ProcessLaunchInfo
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)


class HaxeLanguageServer(SolidLanguageServer):
    """
    Provides Haxe specific instantiation of the LanguageServer class.

    The Haxe Language Server requires:
    - Node.js (to run server.js)
    - Haxe compiler 3.4.0+ (the LS delegates to it for analysis)
    - A .hxml build file for project context (cross-file features, completion)

    You can pass the following entries in ls_specific_settings["haxe"]:
        - ls_path: Path to a pre-built server.js
        - build_file: Path to the .hxml build file (default: auto-detected from project root)
        - haxe_executable: Path to the Haxe compiler (default: "haxe" from PATH)
        - working_directory: Subdirectory to use as the Haxe compiler's working directory.
            When the serena project root is a parent of the actual Haxe project (e.g. a monorepo),
            set this to the subdirectory containing the hxml build files (e.g. "desktop").
            Hxml relative paths (-cp, includes) will resolve relative to this directory.
            If not set, defaults to the repository root.
    """

    @property
    def _haxe_cwd(self) -> str:
        """The working directory for the Haxe compiler and LS.

        When working_directory is set, returns repo_root/working_directory.
        Otherwise returns repo_root. This affects hxml path resolution,
        the LS rootUri, and the compiler process CWD.
        """
        wd = self._custom_settings.get("working_directory")
        if wd:
            return os.path.normpath(os.path.join(self.repository_root_path, wd))
        return self.repository_root_path

    def _create_dependency_provider(self) -> "HaxeLanguageServer.DependencyProvider":
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def _create_process_launch_info(self) -> ProcessLaunchInfo:
        """Override to use _haxe_cwd as the process working directory."""
        assert self._dependency_provider is not None
        cmd = self._dependency_provider.create_launch_command()
        env = self._dependency_provider.create_launch_command_env()
        return ProcessLaunchInfo(cmd=cmd, cwd=self._haxe_cwd, env=env)

    @contextmanager
    @override
    def open_file(self, relative_file_path: str, open_in_ls: bool = True) -> Iterator[LSPFileBuffer]:
        """Override to never send didOpen to the Haxe LS.

        The Haxe LS triggers a recompilation on didOpen, which causes subsequent
        requests (hover, references) to return empty results. The LS can handle
        requests without files being opened — it uses its own file system access.
        We still read the file locally for serena's caching and symbol parsing.
        """
        with super().open_file(relative_file_path, open_in_ls=False) as fb:
            yield fb

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "export",
            "bin",
            "dump",
            "node_modules",
        ]

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Locate or build the Haxe Language Server (server.js).

            Resolution order:
            1. User-provided ls_path (handled by base class)
            2. Previously built server.js in the resources directory
            3. server.js bundled with the VS Code extension (nadako.vshaxe)
            4. Build from source (requires Haxe + lix + Node.js)
            """
            # Check if already built in resources dir
            haxe_ls_dir = os.path.join(self._ls_resources_dir, "haxe-lsp")
            server_js_path = os.path.join(haxe_ls_dir, "haxe-language-server", "bin", "server.js")

            if os.path.exists(server_js_path):
                log.info(f"Found existing Haxe Language Server at {server_js_path}")
                return server_js_path

            # Try to find server.js from the VS Code extension
            vscode_server = self._find_vscode_extension_server()
            if vscode_server:
                log.info(f"Found Haxe Language Server from VS Code extension at {vscode_server}")
                return vscode_server

            # Build from source
            return self._build_from_source(haxe_ls_dir, server_js_path)

        @staticmethod
        def _find_vscode_extension_server() -> str | None:
            """Try to locate server.js from the vshaxe VS Code extension."""
            extensions_dir = os.path.join(pathlib.Path.home(), ".vscode", "extensions")
            if not os.path.isdir(extensions_dir):
                return None

            # Look for nadako.vshaxe-* or vshaxe.haxe-* directories
            for pattern in ["nadako.vshaxe-*", "vshaxe.haxe-*"]:
                matches = glob.glob(os.path.join(extensions_dir, pattern))
                if matches:
                    # Use the most recent version (sorted alphabetically, last is newest)
                    matches.sort()
                    server_path = os.path.join(matches[-1], "bin", "server.js")
                    if os.path.exists(server_path):
                        return server_path
            return None

        @staticmethod
        def _build_from_source(haxe_ls_dir: str, server_js_path: str) -> str:
            """Clone and build the Haxe Language Server from source."""
            is_node_installed = shutil.which("node") is not None
            assert is_node_installed, "node is not installed or isn't in PATH. Please install Node.js and try again."
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."
            is_haxe_installed = shutil.which("haxe") is not None
            assert is_haxe_installed, (
                "haxe is not installed or isn't in PATH. "
                "The Haxe Language Server requires the Haxe compiler (3.4.0+). "
                "Please install Haxe (https://haxe.org/download/) and try again, "
                "or provide the path to a pre-built server.js via ls_path in ls_specific_settings."
            )

            repo_dir = os.path.join(haxe_ls_dir, "haxe-language-server")

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="haxe-language-server-clone",
                        description="Clone haxe-language-server repository",
                        command=["git", "clone", "--depth", "1", "https://github.com/vshaxe/haxe-language-server.git", repo_dir],
                        platform_id="any",
                    ),
                ]
            )

            if not os.path.isdir(repo_dir):
                log.info("Cloning haxe-language-server repository...")
                deps.install(haxe_ls_dir)

            install_deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="haxe-language-server-npm-install",
                        description="Install npm dependencies (without postinstall scripts)",
                        command=["npm", "install", "--ignore-scripts"],
                        platform_id="any",
                    ),
                ]
            )

            lix_download_deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="haxe-language-server-lix-download",
                        description="Download Haxe libraries via lix",
                        command=["npx", "lix", "download"],
                        platform_id="any",
                    ),
                ]
            )

            build_deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="haxe-language-server-build",
                        description="Build haxe-language-server",
                        command=["npx", "lix", "run", "vshaxe-build", "-t", "language-server"],
                        platform_id="any",
                    ),
                ]
            )

            log.info("Installing npm dependencies for haxe-language-server...")
            install_deps.install(repo_dir)
            log.info("Downloading Haxe libraries via lix...")
            lix_download_deps.install(repo_dir)
            log.info("Building haxe-language-server...")
            build_deps.install(repo_dir)

            if not os.path.exists(server_js_path):
                raise FileNotFoundError(
                    f"haxe-language-server server.js not found at {server_js_path} after build. "
                    "The build may have failed. You can provide a pre-built server.js via ls_path in ls_specific_settings."
                )

            log.info(f"Haxe Language Server built successfully at {server_js_path}")
            return server_js_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return ["node", core_path]

    def _find_hxml_file(self) -> str | None:
        """Auto-detect a .hxml build file in the Haxe working directory."""
        hxml_files = glob.glob(os.path.join(self._haxe_cwd, "*.hxml"))
        if len(hxml_files) == 1:
            return os.path.relpath(hxml_files[0], self._haxe_cwd)
        if len(hxml_files) > 1:
            # Prefer common names
            for preferred in ["build.hxml", "compile.hxml", "all.hxml"]:
                candidate = os.path.join(self._haxe_cwd, preferred)
                if os.path.exists(candidate):
                    return preferred
            log.warning(
                f"Multiple .hxml files found in project root: {[os.path.basename(f) for f in hxml_files]}. "
                "Set 'build_file' in ls_specific_settings to specify which one to use."
            )
        return None

    def _parse_hxml_classpaths(self, hxml_rel_path: str, visited: set[str] | None = None) -> list[str]:
        """Recursively parse an hxml file and its includes, extracting -cp entries.

        Returns a list of classpath strings as they appear in the hxml files
        (relative to the Haxe working directory or absolute).
        """
        if visited is None:
            visited = set()

        hxml_abs = os.path.normpath(os.path.join(self._haxe_cwd, hxml_rel_path))
        if hxml_abs in visited or not os.path.isfile(hxml_abs):
            return []
        visited.add(hxml_abs)

        classpaths: list[str] = []

        with open(hxml_abs, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue

                # Extract -cp / --class-path entries
                cp = None
                if line.startswith("-cp "):
                    cp = line[4:].strip()
                elif line.startswith("--class-path "):
                    cp = line[13:].strip()

                if cp is not None:
                    classpaths.append(cp)
                    continue

                # Follow hxml includes (lines like ./build/haxe/build-desktop.hxml)
                # Haxe resolves include paths relative to the working directory (project root),
                # not relative to the hxml file containing the include.
                if line.endswith(".hxml") and not line.startswith("-"):
                    classpaths.extend(self._parse_hxml_classpaths(line, visited))

        return classpaths

    def _get_external_classpaths(self) -> list[str]:
        """Get resolved absolute paths for classpaths outside the repository root.

        Parses the configured hxml build file chain and returns directories that
        are part of the Haxe compilation but outside the serena project root.
        """
        build_file = self._custom_settings.get("build_file", self._find_hxml_file())
        if not build_file:
            return []

        raw_classpaths = self._parse_hxml_classpaths(build_file)
        external: list[str] = []
        seen: set[str] = set()

        for cp in raw_classpaths:
            abs_cp = os.path.normpath(os.path.join(self._haxe_cwd, cp))
            if not os.path.isdir(abs_cp):
                continue
            abs_cp = os.path.realpath(abs_cp)
            if abs_cp in seen:
                continue
            seen.add(abs_cp)

            # Skip if already under repo root
            try:
                pathlib.Path(abs_cp).relative_to(self.repository_root_path)
                continue
            except ValueError:
                pass

            external.append(abs_cp)

        # Remove paths that are subdirectories of other external paths to avoid duplicate scanning
        filtered: list[str] = []
        for path in external:
            is_subdir = any(pathlib.Path(path).is_relative_to(other) for other in external if other != path)
            if not is_subdir:
                filtered.append(path)

        if filtered:
            log.info("External Haxe classpaths detected: %s", filtered)
        return filtered

    @override
    def request_full_symbol_tree(self, within_relative_path: str | None = None) -> list["ls_types.UnifiedSymbolInformation"]:
        """Override to also scan external classpath directories for symbols.

        The base class only walks files under the repository root. For Haxe projects,
        source files often live in sibling directories (e.g. ../shared/src) defined via
        -cp in the hxml build file. This override includes those external directories
        in the symbol tree so that find_symbol can discover them.
        """
        # Get the normal in-repo symbol tree
        result = super().request_full_symbol_tree(within_relative_path)

        # Only add external classpaths for full-project scans or when no specific path is given
        if within_relative_path is not None and within_relative_path != "":
            # Check if the path points to an external classpath directory
            within_abs = os.path.join(self.repository_root_path, within_relative_path)
            if os.path.exists(within_abs):
                return result
            # Path doesn't exist in repo — might be an absolute external path
            if os.path.isabs(within_relative_path) and os.path.exists(within_relative_path):
                return self._scan_external_directory(within_relative_path)
            return result

        # Full scan: also scan external classpaths
        for ext_path in self._get_external_classpaths():
            try:
                ext_symbols = self._scan_external_directory(ext_path)
                result.extend(ext_symbols)
            except Exception as e:
                log.warning("Error scanning external classpath %s: %s", ext_path, e)

        return result

    def _scan_external_directory(self, abs_dir_path: str) -> list["ls_types.UnifiedSymbolInformation"]:
        """Scan an external directory for Haxe symbols.

        Uses absolute paths as identifiers since these files are outside the repo root.
        """
        abs_dir_path = os.path.realpath(abs_dir_path)
        if not os.path.isdir(abs_dir_path):
            return []

        result: list[ls_types.UnifiedSymbolInformation] = []

        def process_ext_dir(abs_path: str) -> list[ls_types.UnifiedSymbolInformation]:
            try:
                entries = os.listdir(abs_path)
            except OSError:
                return []

            dir_result: list[ls_types.UnifiedSymbolInformation] = []

            package_symbol = ls_types.UnifiedSymbolInformation(  # type: ignore
                name=os.path.basename(abs_path),
                kind=ls_types.SymbolKind.Package,
                location=ls_types.Location(
                    uri=str(pathlib.Path(abs_path).as_uri()),
                    range={"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                    absolutePath=abs_path,
                    relativePath=abs_path,
                ),
                children=[],
            )
            dir_result.append(package_symbol)

            for entry in entries:
                entry_abs = os.path.join(abs_path, entry)

                if os.path.isdir(entry_abs):
                    if entry.startswith(".") or self.is_ignored_dirname(entry):
                        continue
                    child_symbols = process_ext_dir(entry_abs)
                    package_symbol["children"].extend(child_symbols)
                    for child in child_symbols:
                        child["parent"] = package_symbol

                elif os.path.isfile(entry_abs) and entry.endswith(".hx"):
                    try:
                        # Use absolute path as the "relative" path — this works because
                        # os.path.join(repo_root, absolute_path) returns absolute_path
                        file_path_key = entry_abs
                        with self._open_file_context(file_path_key, open_in_ls=False) as file_data:
                            document_symbols = self.request_document_symbols(file_path_key, file_data)
                            file_root_nodes = document_symbols.root_symbols

                            file_range = self._get_range_from_file_content(file_data.contents)
                            file_symbol = ls_types.UnifiedSymbolInformation(  # type: ignore
                                name=os.path.splitext(entry)[0],
                                kind=ls_types.SymbolKind.File,
                                range=file_range,
                                selectionRange=file_range,
                                location=ls_types.Location(
                                    uri=str(pathlib.Path(entry_abs).as_uri()),
                                    range=file_range,
                                    absolutePath=entry_abs,
                                    relativePath=entry_abs,
                                ),
                                children=file_root_nodes,
                                parent=package_symbol,
                            )
                            for child in file_root_nodes:
                                child["parent"] = file_symbol

                        package_symbol["children"].append(file_symbol)
                    except Exception as e:
                        log.debug("Error scanning external file %s: %s", entry_abs, e)

            return dir_result

        result = process_ext_dir(abs_dir_path)
        return result

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """Returns the initialize params for the Haxe Language Server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        build_file = self._custom_settings.get("build_file", self._find_hxml_file())
        haxe_executable = self._custom_settings.get("haxe_executable", shutil.which("haxe") or "haxe")

        display_arguments = [build_file] if build_file else []
        if not display_arguments:
            log.warning(
                "No .hxml build file configured or detected. The Haxe Language Server requires a build file "
                "for cross-file features. Set 'build_file' in ls_specific_settings['haxe']."
            )

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {
                "displayArguments": display_arguments,
                "displayServerConfig": {
                    "path": haxe_executable,
                    "arguments": [],
                    "useSocket": False,
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return cast(InitializeParams, initialize_params)

    # Timeout for waiting on dynamic capability registration during startup
    READY_TIMEOUT = 30.0

    # Timeout for waiting on the Haxe compiler to finish its initial compilation
    # when a cross-file feature (e.g., references) is first requested.
    # Large Haxe projects can take many minutes for the initial compilation pass.
    # Set to 0 to disable waiting (references will return empty until the compiler is ready).
    COMPILER_READY_TIMEOUT = 600.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "haxe",
            solidlsp_settings,
        )
        self._diagnostics_received = threading.Event()
        self._refactor_cache_ready = threading.Event()

    def _start_server(self) -> None:
        """Starts the Haxe Language Server and waits for it to be ready.

        The Haxe LS reports minimal capabilities in its initialize response
        (textDocumentSync, formatting, folding, color, inlayHints). Features like
        completion, definition, references, and document symbols are registered
        dynamically via client/registerCapability after initialization.
        We wait for both dynamic capability registration and diagnostics before
        declaring the server ready.
        """
        capabilities_ready = threading.Event()

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            message = msg.get("message", "")
            if "[RefactorCache] detected classpaths" in message:
                log.info("LSP: RefactorCache ready — compiler has indexed the project")
                self._refactor_cache_ready.set()

        def on_diagnostics(params: dict) -> None:
            log.info("LSP: Received diagnostics notification")
            self._diagnostics_received.set()

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                method = registration["method"]
                log.info(f"LSP: Haxe LS registered dynamic capability: {method}")
                if method == "textDocument/references":
                    capabilities_ready.set()

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", on_diagnostics)
        self.server.on_request("client/registerCapability", register_capability_handler)

        log.info("Starting Haxe server process (cwd=%s)", self._haxe_cwd)
        self.server.start()
        initialize_params = self._get_initialize_params(self._haxe_cwd)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # The Haxe LS reports only static capabilities here; dynamic ones
        # (completion, definition, references, documentSymbol) are registered
        # via client/registerCapability after initialized notification.
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities, "Haxe LS did not report textDocumentSync capability"

        self.server.notify.initialized({})

        # The Haxe LS requires a workspace/didChangeConfiguration notification
        # to trigger the display server (compiler) startup. Without this,
        # features like references, definition, and completion won't work.
        # See: https://github.com/vshaxe/vshaxe/issues/359
        build_file = self._custom_settings.get("build_file", self._find_hxml_file())
        haxe_executable = self._custom_settings.get("haxe_executable", shutil.which("haxe") or "haxe")
        display_arguments = [build_file] if build_file else []
        self.server.send_notification(
            "workspace/didChangeConfiguration",
            {
                "settings": {
                    "haxe": {
                        "executable": haxe_executable,
                        "displayArguments": display_arguments,
                    },
                },
            },
        )
        log.info("Sent workspace/didChangeConfiguration to trigger Haxe display server")
        log.info("Haxe server initialized, waiting for dynamic capabilities and workspace scan...")

        # Wait for dynamic capability registration (references, etc.)
        # This is fast (~1s) — the LS registers capabilities right after initialization.
        if capabilities_ready.wait(timeout=self.READY_TIMEOUT):
            log.info("Haxe server dynamic capabilities registered")
        else:
            log.warning("Timeout waiting for Haxe dynamic capability registration, proceeding anyway")

        # IMPORTANT: Do NOT wait for diagnostics or compiler completion here.
        # The Haxe LS queues requests (like textDocument/references) that arrive
        # while the compiler is still performing its initial compilation, and
        # responds with full results once compilation finishes. However, requests
        # sent AFTER compilation finishes get quick but incomplete (empty) responses.
        # By not blocking startup, we allow tool calls to send requests while the
        # compiler is still working, which produces correct results.

        log.info("Haxe server ready")

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Don't wait before sending references requests.

        The Haxe LS queues references requests that arrive while the compiler is
        still performing its initial compilation, and responds once ready. If we
        wait until after compilation and then send the request, the LS returns
        empty results immediately. So we must NOT wait — just send the request
        and let the LS handle the timing internally.
        """
        return 0.0

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list["ls_types.Location"]:
        """Override to skip opening the file before sending references.

        The Haxe LS does not require a didOpen notification before handling
        textDocument/references. Sending didOpen triggers a recompilation that
        can interfere with the references response (returning empty results).
        By sending the references request directly (without didOpen), the LS
        uses its existing compilation state and returns correct results.
        """
        if not self.server_started:
            raise Exception("Language Server not started")

        # Send references request directly WITHOUT opening the file
        original_timeout = self.server._request_timeout
        try:
            self.server._request_timeout = max(original_timeout or 0, self.COMPILER_READY_TIMEOUT)
            response = self._send_references_request(relative_file_path, line=line, column=column)
        finally:
            self.server._request_timeout = original_timeout

        if response is None:
            return []

        ret = []
        for item in response:
            abs_path = PathUtils.uri_to_path(item["uri"])
            if not pathlib.Path(abs_path).is_relative_to(self.repository_root_path):
                log.info("Reference outside repo root: %s (including with absolute path)", abs_path)
                rel_path = pathlib.Path(abs_path)
            else:
                rel_path = pathlib.Path(abs_path).relative_to(self.repository_root_path)

            if self.is_ignored_path(str(rel_path)):
                continue

            new_item = dict(item)
            new_item["absolutePath"] = str(abs_path)
            new_item["relativePath"] = str(rel_path)
            ret.append(ls_types.Location(**new_item))  # type: ignore
        return ret

    @override
    def request_hover(
        self, relative_file_path: str, line: int, column: int, file_buffer: LSPFileBuffer | None = None
    ) -> ls_types.Hover | None:
        """Override to skip opening the file before sending hover request.

        Same issue as references: sending didOpen triggers a recompilation that
        causes the hover response to be empty. The Haxe LS can handle hover
        requests without the file being opened.
        """
        if not self.server_started:
            raise Exception("Language Server not started")

        uri = PathUtils.path_to_uri(os.path.join(self.repository_root_path, relative_file_path))

        # Wait for the compiler to finish its initial compilation before sending hover.
        # Unlike references (which the LS queues during compilation), hover returns null
        # immediately if the compiler isn't ready. We must wait for RefactorCache first.
        if not self._refactor_cache_ready.is_set():
            log.info("Waiting for Haxe compiler before hover request...")
            self._refactor_cache_ready.wait(timeout=self.COMPILER_READY_TIMEOUT)

        response = self.server.send.hover(
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
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
