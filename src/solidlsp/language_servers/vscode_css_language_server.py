"""
Provides CSS-specific instantiation of the LanguageServer class using
``vscode-css-language-server`` from the ``vscode-langservers-extracted`` npm
package (the same language server VS Code uses).

By default, the original :pypi:`vscode-langservers-extracted` package is installed
(stable, widely used). Users can opt into the actively-maintained 2026 fork
``@t1ckbase/vscode-langservers-extracted`` (or any other source) by overriding
``vscode_langservers_package`` and ``vscode_langservers_version`` in
``ls_specific_settings.css``. Both packages expose the same ``vscode-css-language-server``
binary name under ``node_modules/.bin``, so no code changes are needed to switch.

Note: ``vscode-css-language-server`` natively understands ``.scss`` and ``.less`` too,
but Serena routes ``.scss``/``.sass`` files to the dedicated
:class:`~solidlsp.language_servers.some_sass_language_server.SomeSassLanguageServer`
which provides materially better cross-file ``@use``/``@forward`` navigation.

Caveats:
    * In-file selectors/rules are returned as document symbols.
    * Cross-file ``@import`` navigation is limited.
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

DEFAULT_PACKAGE_NAME = "vscode-langservers-extracted"
DEFAULT_PACKAGE_VERSION = "4.10.0"
LS_BIN_NAME = "vscode-css-language-server"


class VsCodeCssLanguageServer(SolidLanguageServer):
    """
    CSS language server (Microsoft, extracted from VS Code).

    ``ls_specific_settings["css"]`` keys:
        * ``vscode_langservers_package``: npm package providing the binary
          (default: ``vscode-langservers-extracted``).
        * ``vscode_langservers_version``: version of the package to install
          (default: ``4.10.0``).
        * ``npm_registry``: optional alternative npm registry URL.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "css",
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

            package_name = self._custom_settings.get("vscode_langservers_package", DEFAULT_PACKAGE_NAME)
            package_version = self._custom_settings.get("vscode_langservers_version", DEFAULT_PACKAGE_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            install_dir = os.path.join(self._ls_resources_dir, "vscode-langservers")
            executable_path = os.path.join(install_dir, "node_modules", ".bin", LS_BIN_NAME)
            if os.name == "nt":
                executable_path += ".cmd"

            version_file = os.path.join(install_dir, ".installed_version")
            expected_version = f"{package_name}@{package_version}"

            needs_install = not os.path.exists(executable_path)
            if not needs_install and os.path.exists(version_file):
                with open(version_file) as f:
                    needs_install = f.read().strip() != expected_version
            elif not needs_install:
                needs_install = True

            if needs_install:
                log.info("Installing %s for CSS language server...", expected_version)
                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id=package_name,
                            description=f"{package_name} (provides {LS_BIN_NAME})",
                            command=build_npm_install_command(package_name, package_version, npm_registry),
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
                "provideFormatter": False,
                "handledSchemas": ["file"],
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
        # vscode-css-language-server requests workspace/configuration during init
        self.server.on_request("workspace/configuration", lambda _params: [{}])

        log.info("Starting vscode-css-language-server")
        self.server.start()
        init_params = self._get_initialize_params(self.repository_root_path)
        init_response = self.server.send.initialize(init_params)
        log.debug("CSS LS initialize response: %s", init_response)
        assert "completionProvider" in init_response["capabilities"], "CSS LSP did not advertise completionProvider"
        self.server.notify.initialized({})
        self.server_ready.set()
