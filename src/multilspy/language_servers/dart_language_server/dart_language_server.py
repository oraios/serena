from contextlib import asynccontextmanager
import logging
import os
import pathlib
import shutil
import stat
from typing import AsyncIterator
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
import json
from multilspy.multilspy_utils import FileUtils, PlatformUtils


class DartLanguageServer(LanguageServer):
    """
    Provides Dart specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Dart.
    """

    def __init__(self, config, logger, repository_root_path):
        """
        Creates a DartServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """

        executable_path = self.setup_runtime_dependencies(logger)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=executable_path, cwd=repository_root_path),
            "dart",
        )

    def setup_runtime_dependencies(self, logger: "MultilspyLogger") -> str:
        platform_id = PlatformUtils.get_platform_id()

        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = d["runtimeDependencies"]
        runtime_dependencies = [
            dependency for dependency in runtime_dependencies if dependency["platformId"] == platform_id.value
        ]

        assert len(runtime_dependencies) == 1
        dependency = runtime_dependencies[0]

        dart_ls_dir = os.path.join(os.path.dirname(__file__), "static", "dart-language-server")
        dart_executable_path = os.path.join(dart_ls_dir, dependency["binaryName"])

        if not os.path.exists(dart_ls_dir):
            os.makedirs(dart_ls_dir)
            FileUtils.download_and_extract_archive(
                logger, dependency["url"], dart_ls_dir, dependency["archiveType"]
            )


        assert os.path.exists(dart_executable_path)
        os.chmod(dart_executable_path, stat.S_IEXEC)

        return f"{dart_executable_path} language-server --client-id multilspy.dart --client-version 1.2"


    def _get_initialize_params(self, repository_absolute_path: str):
        """
        Returns the initialize params for the Dart Language Server.
        """
        with open(
            os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r"
        ) as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        assert d["rootPath"] == "$rootPath"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "$rootUri"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["uri"] == "$uri"
        d["workspaceFolders"][0]["uri"] = pathlib.Path(
            repository_absolute_path
        ).as_uri()

        assert d["workspaceFolders"][0]["name"] == "$name"
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["DartLanguageServer"]:
        """
        Start the language server and yield when the server is ready.
        """

        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def check_experimental_status(params):
            pass

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request(
            "workspace/executeClientCommand", execute_client_command_handler
        )
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification(
            "experimental/serverStatus", check_experimental_status
        )

        async with super().start_server():
            self.logger.log(
                "Starting dart-language-server server process", logging.INFO
            )
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)
            self.logger.log(
                "Sending initialize request to dart-language-server",
                logging.DEBUG,
            )
            init_response = await self.server.send_request(
                "initialize", initialize_params
            )
            self.logger.log(
                f"Received initialize response from dart-language-server: {init_response}",
                logging.INFO,
            )

            self.server.notify.initialized({})

            yield self

            await self.server.shutdown()
            await self.server.stop()
