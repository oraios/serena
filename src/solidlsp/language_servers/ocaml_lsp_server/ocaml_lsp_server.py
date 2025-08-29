"""
Provides OCaml and Reason specific instantiation of the SolidLanguageServer class. Contains various configurations and settings specific to OCaml and Reason.
"""

import json
import logging
import os
import pathlib
import platform
import re
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

        # Configure OCaml LSP server with .merlin file support
        ocaml_lsp_cmd = [ocaml_lsp_executable_path, "--fallback-read-dot-merlin"]

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=ocaml_lsp_cmd, cwd=repository_root_path),
            "ocaml",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

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

        # Check OCaml version compatibility
        try:
            ocaml_version_result = subprocess.run(
                ["opam", "exec", "--", "ocaml", "-version"],
                check=True,
                capture_output=True,
                text=True,
                cwd=repository_root_path,
                **subprocess_kwargs(),
            )
            version_match = re.search(r"(\d+\.\d+\.\d+)", ocaml_version_result.stdout)
            if version_match:
                version = version_match.group(1)
                logger.log(f"OCaml version: {version}", logging.INFO)
                if version == "5.1.0":
                    raise RuntimeError(
                        f"OCaml {version} is incompatible with ocaml-lsp-server. "
                        "Please use OCaml < 5.1 or >= 5.1.1. "
                        "Consider creating a new opam switch: 'opam switch create <name> ocaml-base-compiler.4.14.2'"
                    )
        except subprocess.CalledProcessError as e:
            logger.log(f"Warning: Could not check OCaml version: {e.stderr}", logging.WARNING)
        except FileNotFoundError:
            logger.log("Warning: OCaml not found in PATH, version check skipped", logging.WARNING)

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
                error_msg = (
                    "ocaml-lsp-server is not installed. Please install it manually:\n"
                    f"  {dependency['installCommand']}\n\n"
                    "Note: ocaml-lsp-server requires OCaml < 5.1 or >= 5.1.1 (OCaml 5.1.0 is not supported).\n"
                    "If you have OCaml 5.1.0, create a new opam switch with a compatible version:\n"
                    "  opam switch create <name> ocaml-base-compiler.4.14.2\n"
                    "  opam switch <name>\n"
                    "  eval $(opam env)\n"
                    f"  {dependency['installCommand']}"
                )
                logger.log(error_msg, logging.ERROR)
                raise RuntimeError(error_msg)
            logger.log("ocaml-lsp-server is installed", logging.INFO)

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to check ocaml-lsp-server installation: {e.stderr}")

        try:
            # Find the path to the ocaml-lsp-server executable using platform-specific commands
            if platform.system() == "Windows":
                # Windows uses 'where' command
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
                # Unix systems use 'which' command
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

            # Ensure the executable has the right permissions (skip on Windows as chmod behaves differently)
            if platform.system() != "Windows":
                os.chmod(executable_path, os.stat(executable_path).st_mode | stat.S_IEXEC)

            return executable_path
        except subprocess.CalledProcessError as e:
            error_details = f"Command failed: {e.cmd}\nReturn code: {e.returncode}\nStderr: {e.stderr}"
            logger.log(f"Failed to locate ocaml-lsp-server executable. {error_details}", logging.ERROR)

            # Provide helpful diagnostics
            try:
                # Check if opam switch is properly set
                switch_result = subprocess.run(
                    ["opam", "switch", "show"],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=repository_root_path,
                    **subprocess_kwargs(),
                )
                logger.log(f"Current opam switch: {switch_result.stdout.strip()}", logging.INFO)

                # Check what's installed in current switch
                list_result = subprocess.run(
                    ["opam", "list", "-i"],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=repository_root_path,
                    **subprocess_kwargs(),
                )
                installed_packages = list_result.stdout
                if "ocaml-lsp-server" in installed_packages:
                    logger.log("ocaml-lsp-server appears to be installed but not in PATH", logging.ERROR)
                else:
                    logger.log("ocaml-lsp-server not found in installed packages", logging.ERROR)

            except Exception as diag_error:
                logger.log(f"Could not gather diagnostic information: {diag_error}", logging.WARNING)

            raise RuntimeError(
                f"Failed to find ocaml-lsp-server executable. {error_details}\n"
                "This usually means ocaml-lsp-server is not installed or not in PATH. "
                "Try: 1) Check opam switch, 2) Install ocaml-lsp-server, 3) Ensure opam env is activated."
            )

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
