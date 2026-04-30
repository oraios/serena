"""
Provides SCSS / Sass-specific instantiation of the LanguageServer class using the
``some-sass-language-server`` npm package (https://github.com/wkillerud/some-sass).

Some Sass is the dedicated, actively maintained SCSS LSP. Compared to the generic
``vscode-css-language-server``, it provides full ``@use`` / ``@forward`` workspace
navigation (cross-file go-to-definition and find-references for mixins, functions,
variables, placeholders), SassDoc, and the indented Sass syntax.

Caveats:
    * Cross-file navigation requires the workspace to be configured (the LS scans
      the project root after initialization).
    * Language is registered as experimental.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import threading

from overrides import override

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

DEFAULT_PACKAGE_VERSION = "2.3.8"
LS_BIN_NAME = "some-sass-language-server"


class SomeSassLanguageServer(SolidLanguageServer):
    """
    SCSS / Sass language server (Some Sass by wkillerud).

    ``ls_specific_settings["scss"]`` keys:
        * ``some_sass_version``: version of ``some-sass-language-server`` to install
          (default: ``2.3.8``).
        * ``npm_registry``: optional alternative npm registry URL.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "scss",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules", "dist", "build", "coverage"]

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            assert shutil.which("node") is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            assert shutil.which("npm") is not None, "npm is not installed or isn't in PATH. Please install npm and try again."

            package_version = self._custom_settings.get("some_sass_version", DEFAULT_PACKAGE_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            install_dir = os.path.join(self._ls_resources_dir, "some-sass")
            executable_path = os.path.join(install_dir, "node_modules", ".bin", LS_BIN_NAME)
            if os.name == "nt":
                executable_path += ".cmd"

            version_file = os.path.join(install_dir, ".installed_version")
            expected_version = f"some-sass-language-server@{package_version}"

            needs_install = not os.path.exists(executable_path)
            if not needs_install and os.path.exists(version_file):
                with open(version_file) as f:
                    needs_install = f.read().strip() != expected_version
            elif not needs_install:
                needs_install = True

            if needs_install:
                log.info("Installing %s...", expected_version)
                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="some-sass-language-server",
                            description="Some Sass language server (SCSS / Sass)",
                            command=build_npm_install_command("some-sass-language-server", package_version, npm_registry),
                            platform_id="any",
                        ),
                    ]
                )
                deps.install(install_dir)
                with open(version_file, "w") as f:
                    f.write(expected_version)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(
                    f"{LS_BIN_NAME} executable not found at {executable_path}; npm install of {expected_version} did not produce the expected binary."
                )
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params: dict = {
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
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {
                # See https://wkillerud.github.io/some-sass/user-guide/settings.html
                "somesass": {
                    "workspace": {
                        "loadPaths": [],
                    },
                    "suggest": {
                        "suggestFromUseOnly": False,
                    },
                }
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
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        def do_nothing(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_request("client/registerCapability", lambda _params: None)
        self.server.on_request("workspace/configuration", lambda _params: [{}])

        log.info("Starting some-sass-language-server")
        self.server.start()
        init_params = self._get_initialize_params(self.repository_root_path)
        init_response = self.server.send.initialize(init_params)
        log.debug("Some Sass LS initialize response: %s", init_response)
        assert "completionProvider" in init_response["capabilities"], "Some Sass LSP did not advertise completionProvider"
        self.server.notify.initialized({})
        self.server_ready.set()
