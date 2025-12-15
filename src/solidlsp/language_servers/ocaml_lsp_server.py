"""
Provides OCaml and Reason specific instantiation of the SolidLanguageServer class.
Contains various configurations and settings specific to OCaml and Reason.
"""

import logging
import os
import pathlib
import platform
import re
import shutil
import stat
import subprocess
import threading
from typing import Any

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import subprocess_kwargs

log = logging.getLogger(__name__)


class OcamlLanguageServer(SolidLanguageServer):
    """
    Provides OCaml and Reason specific instantiation of the SolidLanguageServer class.
    Contains various configurations and settings specific to OCaml and Reason.
    """

    _ocaml_version: tuple[int, int, int]
    _index_built: bool

    @staticmethod
    def _ensure_opam_installed() -> None:
        """Ensure OPAM is installed and available."""
        opam_path = shutil.which("opam")
        if opam_path is None:
            raise RuntimeError(
                "OPAM is not installed or not in PATH.\n"
                "Please install OPAM from: https://opam.ocaml.org/doc/Install.html\n\n"
                "Installation instructions:\n"
                "  - macOS: brew install opam\n"
                "  - Ubuntu/Debian: sudo apt install opam\n"
                "  - Fedora: sudo dnf install opam\n"
                "  - Windows: https://fdopen.github.io/opam-repository-mingw/installation/\n\n"
                "After installation, initialize OPAM with: opam init"
            )

    @staticmethod
    def _detect_ocaml_version(repository_root_path: str) -> tuple[int, int, int]:
        """
        Detect and return the OCaml version as a tuple (major, minor, patch).
        Also checks for version compatibility with ocaml-lsp-server.
        Returns (0, 0, 0) if version cannot be determined.
        """
        try:
            result = subprocess.run(
                ["opam", "exec", "--", "ocaml", "-version"],
                check=True,
                capture_output=True,
                text=True,
                cwd=repository_root_path,
                **subprocess_kwargs(),
            )
            version_match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout)
            if version_match:
                major = int(version_match.group(1))
                minor = int(version_match.group(2))
                patch = int(version_match.group(3))
                version_tuple = (major, minor, patch)
                version_str = f"{major}.{minor}.{patch}"
                log.info(f"OCaml version: {version_str}")

                if version_tuple == (5, 1, 0):
                    raise RuntimeError(
                        f"OCaml {version_str} is incompatible with ocaml-lsp-server.\n"
                        "Please use OCaml < 5.1 or >= 5.1.1.\n"
                        "Consider creating a new opam switch:\n"
                        "  opam switch create <name> ocaml-base-compiler.4.14.2"
                    )
                return version_tuple
        except subprocess.CalledProcessError as e:
            log.warning(f"Could not check OCaml version: {e.stderr}")
        except FileNotFoundError:
            log.warning("OCaml not found in PATH, version check skipped")
        return (0, 0, 0)

    @staticmethod
    def _ensure_ocaml_lsp_installed(repository_root_path: str) -> str:
        """
        Ensure ocaml-lsp-server is installed and return the executable path.
        Raises RuntimeError with helpful message if not installed.
        """
        # Check if ocaml-lsp-server is installed
        try:
            result = subprocess.run(
                ["opam", "list", "-i", "ocaml-lsp-server"],
                check=False,
                capture_output=True,
                text=True,
                cwd=repository_root_path,
                **subprocess_kwargs(),
            )
            if "ocaml-lsp-server" not in result.stdout or "# No matches found" in result.stdout:
                raise RuntimeError(
                    "ocaml-lsp-server is not installed.\n\n"
                    "Please install it with:\n"
                    "  opam install ocaml-lsp-server\n\n"
                    "Note: ocaml-lsp-server requires OCaml < 5.1 or >= 5.1.1 (OCaml 5.1.0 is not supported).\n"
                    "If you have OCaml 5.1.0, create a new opam switch with a compatible version:\n"
                    "  opam switch create <name> ocaml-base-compiler.4.14.2\n"
                    "  opam switch <name>\n"
                    "  eval $(opam env)\n"
                    "  opam install ocaml-lsp-server\n\n"
                    "For more information: https://github.com/ocaml/ocaml-lsp"
                )
            log.info("ocaml-lsp-server is installed")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to check ocaml-lsp-server installation: {e.stderr}")

        # Find the executable path
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["opam", "exec", "--", "where", "ocamllsp"],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=repository_root_path,
                    **subprocess_kwargs(),
                )
                executable_path = result.stdout.strip().split("\n")[0]
            else:
                result = subprocess.run(
                    ["opam", "exec", "--", "which", "ocamllsp"],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=repository_root_path,
                    **subprocess_kwargs(),
                )
                executable_path = result.stdout.strip()

            if not os.path.exists(executable_path):
                raise RuntimeError(f"ocaml-lsp-server executable not found at {executable_path}")

            if platform.system() != "Windows":
                os.chmod(executable_path, os.stat(executable_path).st_mode | stat.S_IEXEC)

            return executable_path

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to find ocaml-lsp-server executable.\n"
                f"Command failed: {e.cmd}\n"
                f"Return code: {e.returncode}\n"
                f"Stderr: {e.stderr}\n\n"
                "This usually means ocaml-lsp-server is not installed or not in PATH.\n"
                "Try:\n"
                "  1. Check opam switch: opam switch show\n"
                "  2. Install ocaml-lsp-server: opam install ocaml-lsp-server\n"
                "  3. Ensure opam env is activated: eval $(opam env)"
            )

    @property
    def supports_cross_file_references(self) -> bool:
        """
        Check if this OCaml environment supports cross-file references.

        Cross-file references require OCaml >= 5.2 with project-wide occurrences.
        Full requirements:
        - OCaml 5.2+
        - merlin >= 5.1-502 (provides ocaml-index tool)
        - dune >= 3.16.0
        - Index built via `dune build @ocaml-index`
        - For best results: `dune build -w` running (enables dune RPC)

        Note: Even when this returns True, cross-file refs may not work in all
        cases. The LSP server needs dune's RPC server (via -w flag) to be fully
        aware of the index. Without watch mode, cross-file refs are best-effort.

        See: https://discuss.ocaml.org/t/ann-project-wide-occurrences-in-merlin-and-lsp/14847
        """
        return self._ocaml_version >= (5, 2, 0)

    @staticmethod
    def _build_ocaml_index_static(repository_root_path: str) -> bool:
        """
        Build the OCaml index for project-wide occurrences.
        This enables cross-file reference finding on OCaml 5.2+.
        Must be called BEFORE starting the LSP server.
        Returns True if successful, False otherwise.
        """
        log.info("Building OCaml index for cross-file references (dune build @ocaml-index)...")
        try:
            result = subprocess.run(
                ["opam", "exec", "--", "dune", "build", "@ocaml-index"],
                cwd=repository_root_path,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                **subprocess_kwargs(),
            )
            if result.returncode == 0:
                log.info("OCaml index built successfully")
                return True
            else:
                log.warning(f"Failed to build OCaml index: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            log.warning("OCaml index build timed out after 120 seconds")
            return False
        except FileNotFoundError:
            log.warning("opam not found, cannot build OCaml index")
            return False
        except Exception as e:
            log.warning(f"Error building OCaml index: {e}")
            return False

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an OcamlLanguageServer instance.
        This class is not meant to be instantiated directly. Use SolidLanguageServer.create() instead.
        """
        # Ensure dependencies are available
        self._ensure_opam_installed()

        # Detect OCaml version for feature gating
        self._ocaml_version = self._detect_ocaml_version(repository_root_path)
        self._index_built = False

        # Build OCaml index BEFORE starting server (required for cross-file refs on OCaml 5.2+)
        if self._ocaml_version >= (5, 2, 0):
            self._index_built = self._build_ocaml_index_static(repository_root_path)

        # Verify ocaml-lsp-server is installed (we don't need the path, just validation)
        self._ensure_ocaml_lsp_installed(repository_root_path)

        # Use opam exec to run ocamllsp - this ensures correct opam environment
        # which is required for project-wide occurrences (cross-file references) to work
        ocaml_lsp_cmd = ["opam", "exec", "--", "ocamllsp", "--fallback-read-dot-merlin"]
        log.info(f"Using ocaml-lsp-server via: {' '.join(ocaml_lsp_cmd)}")

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=ocaml_lsp_cmd, cwd=repository_root_path),
            "ocaml",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """Define language-specific directories to ignore for OCaml projects."""
        return super().is_ignored_dirname(dirname) or dirname in ["_build", "_opam", ".opam"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the OCaml Language Server.
        Supports both OCaml and Reason.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "Serena", "version": "0.1.0"},
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "workspace": {
                    "workspaceFolders": True,
                    "configuration": True,
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                        "didSave": True,
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "formatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
            },
            "trace": "verbose",
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """
        Starts the OCaml Language Server (supports both OCaml and Reason)
        """

        def register_capability_handler(params: Any) -> None:
            if "registrations" in params:
                for registration in params.get("registrations", []):
                    method = registration.get("method", "")
                    log.info(f"OCaml LSP registered capability: {method}")
            return

        def lang_status_handler(params: dict[str, Any]) -> None:
            if params.get("type") == "ServiceReady" and params.get("message") == "ServiceReady":
                self.server_ready.set()

        def do_nothing(params: Any) -> None:
            return

        def window_log_message(msg: dict[str, Any]) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            if "initialization done" in msg.get("message", "").lower():
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting OCaml LSP server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify expected capabilities
        capabilities = init_response.get("capabilities", {})
        log.info(f"OCaml LSP capabilities: {list(capabilities.keys())}")

        text_doc_sync = capabilities.get("textDocumentSync")
        if isinstance(text_doc_sync, dict):
            assert text_doc_sync.get("change") == 2, "Expected incremental sync"
        assert "completionProvider" in capabilities, "Expected completion support"

        self.server.notify.initialized({})
        self.completions_available.set()
        self.server_ready.set()

        log.info("OCaml Language Server initialized successfully")
