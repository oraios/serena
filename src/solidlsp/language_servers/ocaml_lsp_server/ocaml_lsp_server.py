"""
Provides OCaml and Reason specific instantiation of the SolidLanguageServer class. Contains various configurations and settings specific to OCaml and Reason.
"""

import json
import logging
import os
import pathlib
import platform
import shutil
import stat
import subprocess
import threading
from typing import Any

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import subprocess_kwargs


class OcamlLanguageServer(SolidLanguageServer):
    """
    Provides OCaml and Reason specific instantiation of the SolidLanguageServer class. Contains various configurations and settings specific to OCaml and Reason.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates an OcamlLanguageServer instance. This class is not meant to be instantiated directly. Use SolidLanguageServer.create() instead.
        """
        ocaml_lsp_executable_path = self._setup_runtime_dependencies(logger, repository_root_path)
        logger.log(f"Using ocaml-lsp-server at: {ocaml_lsp_executable_path}", logging.INFO)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=ocaml_lsp_executable_path, cwd=repository_root_path),
            "ocaml",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _find_executable_with_extensions(self, executable_name: str) -> str | None:
        """
        Find executable with Windows-specific extensions (.bat, .cmd, .exe) if on Windows.
        Returns the full path to the executable or None if not found.
        """
        if platform.system() == "Windows":
            # Try Windows-specific extensions first
            for ext in [".bat", ".cmd", ".exe"]:
                path = shutil.which(f"{executable_name}{ext}")
                if path:
                    return path
            # Fall back to default search
            return shutil.which(executable_name)
        else:
            # Unix systems
            return shutil.which(executable_name)

    def _setup_runtime_dependencies(self, logger: LanguageServerLogger, repository_root_path: str) -> str:
        """
        Setup runtime dependencies for ocaml-lsp (supports both OCaml and Reason).
        """
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json")) as f:
            d = json.load(f)
            del d["_description"]

        dependency = d["runtimeDependencies"][0]

        # Check if OPAM is installed
        try:
            result = subprocess.run(
                ["opam", "--version"], check=True, capture_output=True, text=True, cwd=repository_root_path, **subprocess_kwargs()
            )
            opam_version = result.stdout.strip()
            logger.log(f"OPAM version: {opam_version}", logging.INFO)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Error checking for OPAM installation: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("OPAM is not installed. Please install OPAM before continuing.")

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
            if "# No matches found" in result.stdout:
                logger.log("Installing ocaml-lsp-server...", logging.INFO)
                subprocess.run(
                    dependency["installCommand"].split(), check=True, capture_output=True, cwd=repository_root_path, **subprocess_kwargs()
                )

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to check or install ocaml-lsp-server: {e.stderr}")

        try:
            # Find the path to the ocaml-lsp-server executable using cross-platform approach
            if platform.system() == "Windows":
                # Use 'where' command on Windows instead of 'which'
                result = subprocess.run(
                    ["opam", "exec", "--", "where", "ocamllsp"],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=repository_root_path,
                    **subprocess_kwargs(),
                )
                # Windows 'where' may return multiple paths, take the first one
                executable_path = result.stdout.strip().split("\n")[0]
            else:
                # Use 'which' command on Unix systems
                result = subprocess.run(
                    ["opam", "exec", "--", "which", "ocamllsp"],
                    check=True,
                    capture_output=True,
                    text=True,
                    cwd=repository_root_path,
                    **subprocess_kwargs(),
                )
                executable_path = result.stdout.strip()

            # If the simple approach fails, try alternative methods
            if not executable_path or not os.path.exists(executable_path):
                # Fallback 1: Try to find using shutil.which with extensions
                alt_path = self._find_executable_with_extensions("ocamllsp")
                if alt_path:
                    executable_path = alt_path
                else:
                    # Fallback 2: Construct path directly from OPAM bin directory
                    result = subprocess.run(
                        ["opam", "var", "bin"], check=True, capture_output=True, text=True, cwd=repository_root_path, **subprocess_kwargs()
                    )
                    opam_bin = result.stdout.strip()
                    executable_name = "ocamllsp.exe" if platform.system() == "Windows" else "ocamllsp"
                    executable_path = os.path.join(opam_bin, executable_name)

            if not os.path.exists(executable_path):
                raise RuntimeError(f"ocaml-lsp-server executable not found at {executable_path}")

            # Ensure the executable has the right permissions (skip on Windows as chmod behaves differently)
            if platform.system() != "Windows":
                os.chmod(executable_path, os.stat(executable_path).st_mode | stat.S_IEXEC)

            logger.log(f"Executable found ocaml-lsp-server. Path: {executable_path}", logging.INFO)

            return executable_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to find the executable ocaml-lsp-server: {e.stderr}")

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the OCaml Language Server (supports both OCaml and Reason).
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json")) as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        assert d["rootPath"] == "$rootPath"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "$rootUri"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["uri"] == "$uri"
        d["workspaceFolders"][0]["uri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["name"] == "$name"
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    def _start_server(self) -> None:
        """
        Starts the OCaml Language Server (supports both OCaml and Reason)
        """

        def register_capability_handler(params: Any) -> None:
            assert "registrations" in params
            return

        def lang_status_handler(params: dict[str, Any]) -> None:
            if params.get("type") == "ServiceReady" and params.get("message") == "ServiceReady":
                self.server_ready.set()

        def do_nothing(params: Any) -> None:
            return

        def window_log_message(msg: dict[str, Any]) -> None:
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)
            # Set server ready when we receive certain message indicating server is ready
            if "initialization done" in msg.get("message", "").lower():
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting OCaml LSP server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Verify expected capabilities - OCaml LSP may have different capabilities than Rust
        text_doc_sync = init_response["capabilities"]["textDocumentSync"]
        if isinstance(text_doc_sync, dict):
            assert text_doc_sync["change"] == 2
        assert "completionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        self.server_ready.set()
