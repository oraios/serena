"""
Provides Haxe specific instantiation of the LanguageServer class.
Uses the vshaxe/haxe-language-server (https://github.com/vshaxe/haxe-language-server),
which is an LSP implementation that delegates to the Haxe compiler for analysis.

Requires Node.js and the Haxe compiler (3.4.0+) to be installed.

You can pass the following entries in ls_specific_settings["haxe"]:
    - ls_path: Path to a pre-built server.js (from vshaxe or VS Code extension)
    - build_file: Path to the .hxml build file for display arguments (default: auto-detected)
    - haxe_executable: Path to the Haxe compiler executable (default: "haxe" from PATH)
"""

import glob
import logging
import os
import pathlib
import shutil
import threading
from typing import cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
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
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "haxe",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> "HaxeLanguageServer.DependencyProvider":
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

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
                        description="Install npm dependencies",
                        command=["npm", "ci"],
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
        """Auto-detect a .hxml build file in the project root."""
        hxml_files = glob.glob(os.path.join(self.repository_root_path, "*.hxml"))
        if len(hxml_files) == 1:
            return os.path.relpath(hxml_files[0], self.repository_root_path)
        if len(hxml_files) > 1:
            # Prefer common names
            for preferred in ["build.hxml", "compile.hxml", "all.hxml"]:
                candidate = os.path.join(self.repository_root_path, preferred)
                if os.path.exists(candidate):
                    return preferred
            log.warning(
                f"Multiple .hxml files found in project root: {[os.path.basename(f) for f in hxml_files]}. "
                "Set 'build_file' in ls_specific_settings to specify which one to use."
            )
        return None

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
            },
            "settings": {
                "haxe": {
                    "executable": haxe_executable,
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

    def _start_server(self) -> None:
        """Starts the Haxe Language Server and waits for it to be ready."""
        server_ready = threading.Event()

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def on_diagnostics(params: dict) -> None:
            log.info("LSP: Received diagnostics notification, server is ready")
            server_ready.set()

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", on_diagnostics)

        log.info("Starting Haxe server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify expected capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities, "Haxe LS did not report textDocumentSync capability"
        assert "completionProvider" in capabilities, "Haxe LS did not report completionProvider capability"

        self.server.notify.initialized({})
        log.info("Haxe server initialized, waiting for workspace to be ready...")

        if server_ready.wait(timeout=30.0):
            log.info("Haxe server workspace scan completed")
        else:
            log.warning("Timeout waiting for Haxe workspace scan, proceeding anyway")

        log.info("Haxe server ready")

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 2.0
