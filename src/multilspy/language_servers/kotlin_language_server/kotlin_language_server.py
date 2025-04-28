"""
Provides Kotlin specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Kotlin.
"""

import asyncio
import dataclasses
import json
import logging
import os
import stat
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


@dataclasses.dataclass
class KotlinRuntimeDependencyPaths:
    """
    Stores the paths to the runtime dependencies of Kotlin Language Server
    """
    java_path: str
    java_home_path: str
    kotlin_executable_path: str


class KotlinLanguageServer(LanguageServer):
    """
    Provides Kotlin specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Kotlin.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a Kotlin Language Server instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        runtime_dependency_paths = self.setup_runtime_dependencies(logger, config)
        self.runtime_dependency_paths = runtime_dependency_paths
        
        # Create command to execute the Kotlin Language Server script
        cmd = f'"{self.runtime_dependency_paths.kotlin_executable_path}"'
        
        # Set environment variables including JAVA_HOME
        proc_env = {"JAVA_HOME": self.runtime_dependency_paths.java_home_path}
        
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, env=proc_env, cwd=repository_root_path),
            "kotlin",
        )

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> KotlinRuntimeDependencyPaths:
        """
        Setup runtime dependencies for Kotlin Language Server.
        """
        platform_id = PlatformUtils.get_platform_id()

        # Verify platform support
        assert platform_id.value.startswith("win-") or platform_id.value.startswith("linux-") or platform_id.value.startswith("osx-"), "Only Windows, Linux and macOS platforms are supported for Kotlin in multilspy at the moment"

        # Load dependency information
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]
        
        kotlin_dependency = d["runtimeDependency"]
        java_dependency = d["java"][platform_id.value]

        # Setup paths for dependencies
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        os.makedirs(static_dir, exist_ok=True)
        
        # Setup Java paths
        java_dir = os.path.join(static_dir, "java")
        os.makedirs(java_dir, exist_ok=True)
        
        java_home_path = os.path.join(java_dir, java_dependency["java_home_path"])
        java_path = os.path.join(java_dir, java_dependency["java_path"])
        
        # Download and extract Java if not exists
        if not os.path.exists(java_path):
            logger.log(f"Downloading Java for {platform_id.value}...", logging.INFO)
            FileUtils.download_and_extract_archive(
                logger, java_dependency["url"], java_dir, java_dependency["archiveType"]
            )
            # Make Java executable
            if not platform_id.value.startswith("win-"):
                os.chmod(java_path, 0o755)
        
        assert os.path.exists(java_path), f"Java executable not found at {java_path}"
        
        # Setup Kotlin Language Server paths
        kotlin_ls_dir = os.path.join(static_dir, "server")
        
        # Get platform-specific executable script path
        if platform_id.value.startswith("win-"):
            kotlin_script = os.path.join(kotlin_ls_dir, "bin", "kotlin-language-server.bat")
        else:
            kotlin_script = os.path.join(kotlin_ls_dir, "bin", "kotlin-language-server")
        
        # Download and extract Kotlin Language Server if script doesn't exist
        if not os.path.exists(kotlin_script):
            logger.log("Downloading Kotlin Language Server...", logging.INFO)
            FileUtils.download_and_extract_archive(
                logger, kotlin_dependency["url"], static_dir, kotlin_dependency["archiveType"]
            )
            
            # Make script executable on Unix platforms
            if os.path.exists(kotlin_script) and not platform_id.value.startswith("win-"):
                os.chmod(kotlin_script, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        
        # Use script file
        if os.path.exists(kotlin_script):
            kotlin_executable_path = kotlin_script
            logger.log(f"Using Kotlin Language Server script at {kotlin_script}", logging.INFO)
        else:
            raise FileNotFoundError(f"Kotlin Language Server script not found at {kotlin_script}")
        
        return KotlinRuntimeDependencyPaths(
            java_path=java_path,
            java_home_path=java_home_path,
            kotlin_executable_path=kotlin_executable_path
        )

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Kotlin Language Server.
        """
        with open(str(pathlib.PurePath(os.path.dirname(__file__), "initialize_params.json")), "r") as f:
            d: InitializeParams = json.load(f)

        del d["_description"]

        if not os.path.isabs(repository_absolute_path):
            repository_absolute_path = os.path.abspath(repository_absolute_path)

        assert d["processId"] == "os.getpid()"
        d["processId"] = os.getpid()

        assert d["rootPath"] == "repository_absolute_path"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "pathlib.Path(repository_absolute_path).as_uri()"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["initializationOptions"]["workspaceFolders"] == "[pathlib.Path(repository_absolute_path).as_uri()]"
        d["initializationOptions"]["workspaceFolders"] = [pathlib.Path(repository_absolute_path).as_uri()]

        assert (
                d["workspaceFolders"]
                == '[\n            {\n                "uri": pathlib.Path(repository_absolute_path).as_uri(),\n                "name": os.path.basename(repository_absolute_path),\n            }\n        ]'
        )
        d["workspaceFolders"] = [
            {
                "uri": pathlib.Path(repository_absolute_path).as_uri(),
                "name": os.path.basename(repository_absolute_path),
            }
        ]

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["KotlinLanguageServer"]:
        """
        Starts the Kotlin Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        ```
        """
        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        async with super().start_server():
            self.logger.log("Starting Kotlin server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)

            capabilities = init_response["capabilities"]
            assert "textDocumentSync" in capabilities, "Server must support textDocumentSync"
            assert "hoverProvider" in capabilities, "Server must support hover"
            assert "completionProvider" in capabilities, "Server must support code completion"
            assert "signatureHelpProvider" in capabilities, "Server must support signature help"
            assert "definitionProvider" in capabilities, "Server must support go to definition"
            assert "referencesProvider" in capabilities, "Server must support find references"
            assert "documentSymbolProvider" in capabilities, "Server must support document symbols"
            assert "workspaceSymbolProvider" in capabilities, "Server must support workspace symbols"
            assert "semanticTokensProvider" in capabilities, "Server must support semantic tokens"
            
            self.server.notify.initialized({})
            self.completions_available.set()

            yield self

            try:
                await self.server.shutdown()
            except Exception as e:
                self.logger.log(f"Error during Kotlin server shutdown: {str(e)}", logging.WARNING)
            finally:
                await self.server.stop()
