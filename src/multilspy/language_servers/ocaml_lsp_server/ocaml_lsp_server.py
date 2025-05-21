"""
Provides OCaml specific instantiation of the LanguageServer class. Contains various configurations and settings specific to OCaml.
"""

import asyncio
import json
import logging
import os
import stat
import subprocess
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import FileUtils
from multilspy.multilspy_utils import PlatformUtils


class OcamlLSPServer(LanguageServer):
    """
    Provides OCaml specific instantiation of the LanguageServer class. Contains various configurations and settings specific to OCaml.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates an OcamlLSPServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        ocaml_lsp_executable_path = self.setup_runtime_dependencies(logger, config, repository_root_path)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=ocaml_lsp_executable_path, cwd=repository_root_path),
            "ocaml",
        )
        self.server_ready = asyncio.Event()

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig, repository_root_path: str) -> str:
        """
        Setup runtime dependencies for ocaml-lsp.
        """
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        dependency = d["runtimeDependencies"][0]

        # Check if OPAM is installed
        try:
            result = subprocess.run(["opam", "--version"], check=True, capture_output=True, text=True, cwd=repository_root_path)
            opam_version = result.stdout.strip()
            logger.log(f"OPAM version: {opam_version}", logging.INFO)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Error checking for OPAM installation: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("OPAM is not installed. Please install OPAM before continuing.")

        # Check if ocaml-lsp-server is installed
        try:
            result = subprocess.run(["opam", "list", "-i", "ocaml-lsp-server"], check=False, capture_output=True, text=True, cwd=repository_root_path)
            if "# No matches found" in result.stdout:
                logger.log("Installing ocaml-lsp-server...", logging.INFO)
                subprocess.run(dependency["installCommand"].split(), check=True, capture_output=True, cwd=repository_root_path)

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to check or install ocaml-lsp-server: {e.stderr}")

        try:
            # Find the path to the ocaml-lsp-server executable
            result = subprocess.run(["opam", "exec", "--", "which", "ocamllsp"], check=True, capture_output=True, text=True, cwd=repository_root_path)
            executable_path = result.stdout.strip()
            
            if not os.path.exists(executable_path):
                raise RuntimeError(f"ocaml-lsp-server executable not found at {executable_path}")
            
            # Ensure the executable has the right permissions
            os.chmod(executable_path, os.stat(executable_path).st_mode | stat.S_IEXEC)

            logger.log(f"Executeable found ocaml-lsp-server. Path: {executable_path}", logging.INFO)

            return executable_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to find the executable ocaml-lsp-server: {e.stderr}")


    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the OCaml Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r") as f:
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

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["OcamlLSPServer"]:
        """
        Starts the OCaml Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        """

        async def register_capability_handler(params):
            assert "registrations" in params
            return

        async def lang_status_handler(params):
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        async def do_nothing(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)
            # Set server ready when we receive certain message indicating server is ready
            if "initialization done" in msg.get("message", "").lower():
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        async with super().start_server():
            self.logger.log("Starting OCaml LSP server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            
            # Verify expected capabilities
            assert init_response["capabilities"]["textDocumentSync"]["change"] == 2
            assert "completionProvider" in init_response["capabilities"]
            
            self.server.notify.initialized({})
            self.completions_available.set()

            self.server_ready.set()
            await self.server_ready.wait()

            yield self
            
            print("$$$$$$$$ Start Shutdown")
            # await self.server.shutdown()
            await asyncio.wait_for(self.server.shutdown(), timeout=5.0)


            print("$$$$$$$$ End Shutdown")
            print("$$$$$$$$ Start Stop")
            await self.server.stop()
            print("$$$$$$$$ End Stop")
