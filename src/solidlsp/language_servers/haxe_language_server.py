"""Haxe language server integration using vshaxe/haxe-language-server."""

import glob
import hashlib
import logging
import os
import pathlib
import shutil
import tempfile
import threading
import urllib.request
import zipfile

from overrides import override

from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    LSPFileBuffer,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import Hover
from solidlsp.lsp_protocol_handler.lsp_types import DiagnosticSeverity, InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_VSHAXE_VERSION = "2.34.2"
INITIAL_VSHAXE_SHA256 = "104d785e3f7b57a7f3debf520d9751f7e7abf3a7e78d203db1a8ff3dc7ca30e2"
DEFAULT_VSHAXE_VERSION = "2.34.2"
DEFAULT_VSHAXE_SHA256 = "104d785e3f7b57a7f3debf520d9751f7e7abf3a7e78d203db1a8ff3dc7ca30e2"


def _vshaxe_sha(version: str) -> str | None:
    if version == INITIAL_VSHAXE_VERSION:
        return INITIAL_VSHAXE_SHA256
    if version == DEFAULT_VSHAXE_VERSION:
        return DEFAULT_VSHAXE_SHA256
    return None


class HaxeLanguageServer(SolidLanguageServer):
    """Haxe language server integration using vshaxe/haxe-language-server.

    Requires Haxe compiler (3.4.0+) and Node.js.
    """

    _COMPILATION_TIMEOUT = 60.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """Creates a HaxeLanguageServer instance. Use LanguageServer.create() instead."""
        super().__init__(
            config,
            repository_root_path,
            None,
            "haxe",
            solidlsp_settings,
        )

        self._server_ready = threading.Event()
        self._server_ready.set()
        self._active_progress_tokens: set[str] = set()
        self._progress_lock = threading.Lock()

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        # Downloaded from Open VSX (not the VS Code Marketplace) because Open VSX
        # provides stable versioned URLs and SHA256 checksums for integrity verification.

        @override
        def _get_or_install_core_dependency(self) -> str:
            """Find the Haxe Language Server binary."""
            # 1. Check for haxe-language-server in PATH
            system_haxe_ls = shutil.which("haxe-language-server")
            if system_haxe_ls:
                log.info(f"Found system-installed haxe-language-server at {system_haxe_ls}")
                return system_haxe_ls

            # 2. Check VSCode extension locations
            vscode_server_path = self._find_vscode_extension_server()
            if vscode_server_path:
                log.info(f"Found Haxe Language Server in VSCode extension at {vscode_server_path}")
                return vscode_server_path

            # 3. Check resource dir / download from Open VSX
            version = self._custom_settings.get("version", DEFAULT_VSHAXE_VERSION)
            ls_dirname = "haxe-lsp" if version == INITIAL_VSHAXE_VERSION else f"haxe-lsp-{version}"
            haxe_ls_dir = os.path.join(self._ls_resources_dir, ls_dirname)
            server_js_path = os.path.join(haxe_ls_dir, "bin", "server.js")
            if os.path.exists(server_js_path):
                log.info(f"Found Haxe Language Server at {server_js_path}")
                return server_js_path

            if shutil.which("node") is None:
                raise FileNotFoundError(
                    "Haxe Language Server not found and Node.js is not installed (required to run it).\n"
                    "Install options:\n"
                    "  1. Install Node.js and re-run (auto-download will proceed)\n"
                    "  2. Install the vshaxe VSCode extension: code --install-extension nadako.vshaxe\n"
                    "  3. Set ls_path in serena_config.yml under ls_specific_settings.haxe"
                )

            downloaded_path = self._download_from_open_vsx(haxe_ls_dir, version)
            if downloaded_path:
                return downloaded_path

            raise FileNotFoundError(
                "Haxe Language Server not found. Install options:\n"
                "  1. Install the vshaxe VSCode extension: code --install-extension nadako.vshaxe\n"
                "  2. Set ls_path in serena_config.yml under ls_specific_settings.haxe"
            )

        @staticmethod
        def _find_vscode_extension_server() -> str | None:
            """Search for the Haxe language server in VSCode extension directories."""
            search_paths = [
                os.path.expanduser("~/.vscode/extensions/nadako.vshaxe-*/bin/server.js"),
                os.path.expanduser("~/.vscode-server/extensions/nadako.vshaxe-*/bin/server.js"),
                os.path.expanduser("~/.vscode-insiders/extensions/nadako.vshaxe-*/bin/server.js"),
            ]
            for pattern in search_paths:
                matches = sorted(glob.glob(pattern), reverse=True)  # newest version first
                for match in matches:
                    if os.path.isfile(match):
                        return match
            return None

        @classmethod
        def _download_from_open_vsx(cls, target_dir: str, version: str) -> str | None:
            """Download a vshaxe VSIX from Open VSX and extract server.js.
            Verifies the download against a hardcoded SHA256 checksum when using the default version.
            """
            try:
                download_url = f"https://open-vsx.org/api/nadako/vshaxe/{version}/file/nadako.vshaxe-{version}.vsix"
                log.info("Downloading Haxe Language Server v%s from Open VSX...", version)
                vsix_path = os.path.join(tempfile.gettempdir(), "vshaxe.vsix")
                urllib.request.urlretrieve(download_url, vsix_path)

                # Verify SHA256 checksum only when the resolved version is one of our pinned ones (INITIAL or current DEFAULT)
                expected_sha = _vshaxe_sha(version)
                if expected_sha is not None:
                    sha256 = hashlib.sha256()
                    with open(vsix_path, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            sha256.update(chunk)
                    if sha256.hexdigest().lower() != expected_sha:
                        os.remove(vsix_path)
                        raise RuntimeError(
                            f"SHA256 checksum mismatch for vshaxe VSIX. Expected {expected_sha}, "
                            f"got {sha256.hexdigest()}. The file may be corrupted or tampered with."
                        )
                    log.info("SHA256 checksum verified")
                else:
                    log.info("Using custom version %s — skipping SHA256 verification", version)

                # VSIX files are ZIP archives — extract bin/ contents
                bin_dir = os.path.join(target_dir, "bin")
                os.makedirs(bin_dir, exist_ok=True)
                with zipfile.ZipFile(vsix_path, "r") as zf:
                    for entry in zf.namelist():
                        if "/bin/" in entry:
                            filename = entry.split("/bin/", 1)[-1]
                            if filename and ".." not in filename:
                                dest_path = os.path.join(bin_dir, filename)
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                with zf.open(entry) as src, open(dest_path, "wb") as dst:
                                    dst.write(src.read())

                os.remove(vsix_path)

                server_js_path = os.path.join(bin_dir, "server.js")
                if os.path.exists(server_js_path):
                    log.info(f"Haxe Language Server v{version} installed to {server_js_path}")
                    return server_js_path

                log.error("Downloaded VSIX but server.js not found after extraction")
                return None

            except Exception:
                log.exception("Failed to download Haxe Language Server from Open VSX")
                return None

        @override
        def _create_launch_command(self, core_path: str) -> list[str]:
            if core_path.endswith(".js"):
                return ["node", core_path]
            return [core_path, "--stdio"]

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "export",
            "dump",
        ]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """Return initialize params for the Haxe Language Server.

        displayArguments are resolved from user-configured buildFile or auto-discovered .hxml files.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        # 1. Check for user-configured .hxml path
        configured_build_file = self._custom_settings.get("buildFile")
        if configured_build_file:
            log.info(f"Using user-configured Haxe build file: {configured_build_file}")
            display_arguments = [configured_build_file]
        else:
            # 2. Auto-discover .hxml files recursively
            display_arguments = self._discover_hxml_file(repository_absolute_path)

        init_options: dict = {"displayArguments": display_arguments}
        rename_source_folders = self._custom_settings.get("renameSourceFolders")
        if rename_source_folders:
            init_options["renameSourceFolders"] = rename_source_folders

        haxe_path = self._custom_settings.get("haxePath")
        if haxe_path:
            init_options["haxePath"] = haxe_path

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "versionSupport": False,
                        "tagSupport": {"valueSet": [1, 2]},
                        "codeDescriptionSupport": True,
                        "dataSupport": True,
                    },
                    "synchronization": {"dynamicRegistration": True, "didSave": True},
                    "completion": {"completionItem": {"snippetSupport": True}},
                    "definition": {},
                    "references": {},
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "codeAction": {},
                    "rename": {},
                    "signatureHelp": {},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {},
                    "symbol": {},
                },
            },
            "initializationOptions": init_options,
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
        return initialize_params  # type: ignore[return-value]

    @staticmethod
    def _discover_hxml_file(repository_absolute_path: str) -> list[str]:
        """Return the first .hxml file found, filtering out dependency directories.

        For more control, set ``ls_specific_settings.haxe.buildFile`` in ``serena_config.yml``.
        """
        max_depth = 5
        skip_dirs = {"node_modules", "haxe_libraries", ".haxelib", "export", "dump", "bin", ".git", "build"}

        for root, dirs, files in os.walk(repository_absolute_path):
            # Skip dependency/build output directories
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            depth = len(pathlib.Path(root).relative_to(repository_absolute_path).parts)
            if depth > max_depth:
                dirs.clear()
                continue
            for f in files:
                if f.endswith(".hxml") and "haxe_libraries" not in root:
                    hxml_path = os.path.relpath(os.path.join(root, f), repository_absolute_path)
                    log.info(
                        "Auto-discovered Haxe build file: %s. To use a different file, set "
                        "ls_specific_settings.haxe.buildFile in serena_config.yml.",
                        hxml_path,
                    )
                    return [hxml_path]

        log.info("No .hxml file found in project")
        return []

    @override
    def _start_server(self) -> None:
        """Start the Haxe Language Server and wait for initial compilation.

        Uses textDocument/publishDiagnostics as the primary compilation-complete signal
        and $/progress tokens as a secondary signal.
        """

        def diagnostics_handler(params: dict) -> None:
            """Signal compilation complete when diagnostics arrive.
            Defers if progress tokens are still active to avoid a race condition.
            """
            uri = params.get("uri", "unknown")
            diags = params.get("diagnostics", [])
            errors = [d for d in diags if d.get("severity") == DiagnosticSeverity.Error]
            if errors:
                log.warning("Haxe LSP diagnostics for %s: %d errors: %s", uri, len(errors), errors)
            else:
                log.info("Haxe LSP diagnostics for %s: clean (%d total)", uri, len(diags))

            with self._progress_lock:
                if not self._active_progress_tokens:
                    log.info("Haxe LSP: no active progress tokens — signalling compilation complete")
                    self._server_ready.set()
                else:
                    log.info(
                        "Haxe LSP: diagnostics received but %d progress tokens still active — deferring",
                        len(self._active_progress_tokens),
                    )

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def register_capability_handler(params: dict) -> None:
            # Haxe LS sends this but we don't need dynamic capability registration.
            return

        def work_done_progress_create(params: dict) -> dict:
            """Handle window/workDoneProgress/create — clear compilation event until tokens finish."""
            token = str(params.get("token", ""))
            log.debug(f"Haxe LSP workDoneProgress/create: token={token!r}")
            with self._progress_lock:
                self._active_progress_tokens.add(token)
                self._server_ready.clear()
            return {}

        def progress_handler(params: dict) -> None:
            """Track $/progress begin/end to detect when all async compilation work finishes."""
            token = str(params.get("token", ""))
            value = params.get("value", {})
            kind = value.get("kind")
            if kind == "begin":
                title = value.get("title", "")
                log.info(f"Haxe LSP progress [{token}]: started - {title}")
                with self._progress_lock:
                    self._active_progress_tokens.add(token)
                    self._server_ready.clear()
            elif kind == "report":
                pct = value.get("percentage")
                msg = value.get("message", "")
                pct_str = f" ({pct}%)" if pct is not None else ""
                log.debug(f"Haxe LSP progress [{token}]: {msg}{pct_str}")
            elif kind == "end":
                msg = value.get("message", "")
                log.info(f"Haxe LSP progress [{token}]: ended - {msg}")
                with self._progress_lock:
                    self._active_progress_tokens.discard(token)
                    if not self._active_progress_tokens:
                        self._server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", progress_handler)
        self.server.on_notification("textDocument/publishDiagnostics", diagnostics_handler)

        log.info("Starting Haxe server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        self.server.send.initialize(initialize_params)

        self._server_ready.clear()
        self.server.notify.initialized({})

        # LS doesn't properly initialise without a workspace_did_change_configuration notification here.
        config_settings: dict = {}
        haxe_path = self._custom_settings.get("haxePath")
        if haxe_path:
            config_settings["haxePath"] = haxe_path
        self.server.notify.workspace_did_change_configuration({"settings": config_settings})

        log.info("Waiting for Haxe LSP compilation to complete...")
        if self._server_ready.wait(timeout=self._COMPILATION_TIMEOUT):
            log.info("Haxe server compilation completed, server ready")
        else:
            log.warning(
                "Haxe LSP did not signal compilation completion within %.0fs — responses may be incomplete",
                self._COMPILATION_TIMEOUT,
            )

    @override
    def request_hover(self, relative_file_path: str, line: int, column: int, file_buffer: LSPFileBuffer | None = None) -> Hover | None:
        """Request hover info, returning None instead of raising on failure.

        The Haxe language server does not provide hover for all symbol types (e.g. class
        declarations), and may raise errors instead of returning None in those cases.
        """
        try:
            return super().request_hover(relative_file_path, line, column, file_buffer=file_buffer)
        except SolidLSPException:
            log.warning("Hover request failed for %s:%d:%d", relative_file_path, line, column, exc_info=True)
            return None

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5
