"""
Provides SCSS / Sass / CSS instantiation of the LanguageServer class using the
``some-sass-language-server`` npm package (https://github.com/wkillerud/some-sass).

Some Sass is the dedicated, actively maintained SCSS LSP. It also accepts plain
``.css`` files via the same ``vscode-css-languageservice`` engine that powers
Microsoft's standalone CSS LS — so Serena routes ``.scss`` / ``.sass`` / ``.css``
through this single server.

Compared to the generic ``vscode-css-language-server`` server, Some Sass also
provides full ``@use`` / ``@forward`` workspace navigation (cross-file
go-to-definition and find-references for mixins, functions, variables,
placeholders), SassDoc, and the indented Sass syntax.

Caveats:
    * Cross-file Sass navigation requires the workspace to be configured (the LS
      scans the project root after initialization).
    * For ``.css`` files, every ``somesass.css.*.enabled`` toggle defaults to
      ``false`` upstream; we flip them on at initialization. See
      ``SOMESASS_CSS_FEATURES`` below for the full set.
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

# Every ``somesass.css.*.enabled`` toggle (per the upstream package.json
# ``contributes.configuration``) defaults to false in some-sass — meaning a request
# for ``.css`` files would be hard-gated off at the top of every handler. Flipping
# the full set on at initialization is what makes plain CSS usable through Some Sass.
# We deliberately leave ``diagnostics.lint.enabled`` off because the lint rules are
# opinionated (vendor prefixes, empty rules, etc.) and would be noisy on user code.
SOMESASS_CSS_FEATURES: dict[str, dict[str, object]] = {
    "codeAction": {"enabled": True},
    "colors": {"enabled": True},
    "completion": {"enabled": True},
    "definition": {"enabled": True},
    "diagnostics": {"enabled": True, "lint": {"enabled": False}},
    "documentSymbols": {"enabled": True},
    "foldingRanges": {"enabled": True},
    "highlights": {"enabled": True},
    "hover": {"enabled": True},
    "links": {"enabled": True},
    "references": {"enabled": True},
    "rename": {"enabled": True},
    "selectionRanges": {"enabled": True},
    "signatureHelp": {"enabled": True},
    "workspaceSymbol": {"enabled": True},
}

SOMESASS_INIT_OPTIONS: dict[str, object] = {
    # See https://wkillerud.github.io/some-sass/user-guide/settings.html
    "somesass": {
        "css": SOMESASS_CSS_FEATURES,
        "workspace": {"loadPaths": []},
        "suggest": {"suggestFromUseOnly": False},
    },
}


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

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        # Some Sass switches behavior off the LSP languageId in its
        # ``languageConfiguration()`` selector, picking the matching
        # ``LanguageServerConfiguration.{css,sass,scss}`` slice. Sending the wrong id
        # for plain CSS would route the file to the SCSS parser and skip the
        # ``somesass.css.*`` feature gate entirely.
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".sass":
            return "sass"
        if ext == ".css":
            return "css"
        return "scss"

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules", "dist", "build", "coverage"]

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            assert shutil.which("node") is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            assert shutil.which("npm") is not None, "npm is not installed or isn't in PATH. Please install npm and try again."

            package_version = self._custom_settings.get("some_sass_version", DEFAULT_PACKAGE_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            ls_dirname = f"some-sass-{package_version}"
            install_dir = os.path.join(self._ls_resources_dir, ls_dirname)
            executable_path = os.path.join(install_dir, "node_modules", ".bin", LS_BIN_NAME)
            if os.name == "nt":
                executable_path += ".cmd"

            if not os.path.exists(executable_path):
                expected_version = f"some-sass-language-server@{package_version}"
                log.info("Installing %s...", expected_version)
                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="some-sass-language-server",
                            description="Some Sass language server (SCSS / Sass / CSS)",
                            command=build_npm_install_command("some-sass-language-server", package_version, npm_registry),
                            platform_id="any",
                        ),
                    ]
                )
                deps.install(install_dir)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(
                    f"{LS_BIN_NAME} executable not found at {executable_path}; "
                    f"npm install of some-sass-language-server@{package_version} did not produce the expected binary."
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
            "initializationOptions": SOMESASS_INIT_OPTIONS,
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
    def _handle_workspace_configuration(params: dict) -> list[dict]:
        # Some Sass calls workspace/configuration after init to fetch ``somesass`` and
        # ``editor`` sections. The LSP contract is one entry per requested item, in order.
        # We respond with our pinned somesass slice for the somesass section and an empty
        # dict for everything else (currently only ``editor``).
        items = params.get("items", []) if isinstance(params, dict) else []
        somesass_section = SOMESASS_INIT_OPTIONS["somesass"]
        result: list[dict] = []
        for item in items:
            section = (item or {}).get("section") if isinstance(item, dict) else None
            if section == "somesass":
                result.append(somesass_section)  # type: ignore[arg-type]
            else:
                # ``editor`` is the only other section Some Sass currently asks for; an unknown
                # section means upstream added a new config slice we should consider supplying.
                if section not in (None, "editor"):
                    log.debug("workspace/configuration: unknown section %r; responding with empty dict", section)
                result.append({})
        return result or [{}]

    def _start_server(self) -> None:
        def do_nothing(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_request("client/registerCapability", lambda _params: None)
        self.server.on_request("workspace/configuration", self._handle_workspace_configuration)

        log.info("Starting some-sass-language-server")
        self.server.start()
        init_params = self._get_initialize_params(self.repository_root_path)
        init_response = self.server.send.initialize(init_params)
        log.debug("Some Sass LS initialize response: %s", init_response)
        assert "completionProvider" in init_response["capabilities"], "Some Sass LSP did not advertise completionProvider"
        self.server.notify.initialized({})
        self.server_ready.set()
