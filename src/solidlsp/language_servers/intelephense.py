"""
Provides PHP specific instantiation of the LanguageServer class using Intelephense.
"""

import json
import logging
import os
import pathlib
import shutil
import subprocess
from time import sleep

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import DefinitionParams, InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


class Intelephense(SolidLanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using Intelephense.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For PHP projects, we should ignore:
        # - vendor: third-party dependencies managed by Composer
        # - node_modules: if the project has JavaScript components
        # - cache: commonly used for caching
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules", "vendor", "cache"]

    def setup_runtime_dependencies(self, logger: LanguageServerLogger, config: LanguageServerConfig) -> str:
        """
        Setup runtime dependencies for Intelephense.
        """
        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
            PlatformId.WIN_x64,
            PlatformId.WIN_arm64,
        ]
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for multilspy PHP at the moment"

        with open(os.path.join(os.path.dirname(__file__), "intelephense", "runtime_dependencies.json"), encoding="utf-8") as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = d.get("runtimeDependencies", [])
        intelephense_ls_dir = os.path.join(os.path.dirname(__file__), "static", "php-lsp")

        # Verify both node and npm are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        # Install intelephense if not already installed
        if not os.path.exists(intelephense_ls_dir):
            os.makedirs(intelephense_ls_dir, exist_ok=True)
            for dependency in runtime_dependencies:
                # Windows doesn't support the 'user' parameter and doesn't have pwd module
                if PlatformUtils.get_platform_id().value.startswith("win"):
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        cwd=intelephense_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    # On Unix-like systems, run as non-root user
                    import pwd

                    user = pwd.getpwuid(os.getuid()).pw_name
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        user=user,
                        cwd=intelephense_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

        intelephense_executable_path = os.path.join(intelephense_ls_dir, "node_modules", ".bin", "intelephense")
        assert os.path.exists(intelephense_executable_path), "intelephense executable not found. Please install intelephense and try again."

        return f"{intelephense_executable_path} --stdio"

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        # Setup runtime dependencies before initializing
        intelephense_cmd = self.setup_runtime_dependencies(logger, config)

        super().__init__(config, logger, repository_root_path, ProcessLaunchInfo(cmd=intelephense_cmd, cwd=repository_root_path), "php")
        self.request_id = 0

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the TypeScript Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "intelephense", "initialize_params.json"), encoding="utf-8") as f:
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

    def _start_server(self):
        """Start Intelephense server process"""

        def register_capability_handler(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Intelephense server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(
            "After sent initialize params",
            logging.INFO,
        )

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        # Intelephense server is typically ready immediately after initialization
        # TODO: This is probably incorrect; the server does send an initialized notification, which we could wait for!

    @override
    # For some reason, the LS may need longer to process this, so we just retry
    def _send_references_request(self, relative_file_path: str, line: int, column: int):
        # TODO: The LS doesn't return references contained in other files if it doesn't sleep. This is
        #   despite the LS having processed requests already. I don't know what causes this, but sleeping
        #   one second helps. It may be that sleeping only once is enough but that's hard to reliably test.
        # May be related to the time it takes to read the files or something like that.
        # The sleeping doesn't seem to be needed on all systems
        sleep(1)
        return super()._send_references_request(relative_file_path, line, column)

    @override
    def _send_definition_request(self, definition_params: DefinitionParams):
        # TODO: same as above, also only a problem if the definition is in another file
        sleep(1)
        return super()._send_definition_request(definition_params)
