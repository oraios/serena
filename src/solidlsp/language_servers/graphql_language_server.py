"""
Provides GraphQL support via the ``graphql-language-service-cli`` npm package
(https://github.com/graphql/graphql-language-service), whose ``graphql-lsp`` binary
implements the Language Server Protocol.

The server resolves schema/operation relationships through graphql-config: it looks
for a ``.graphqlrc.yml`` / ``graphql.config.{yml,yaml,json,js,ts}`` (or a ``graphql``
key in ``package.json``) at the workspace root to learn where the schema and the
GraphQL documents live.

Caveats:
    * ``graphql-language-service-cli`` declares ``graphql`` as a *peer* dependency, so we
      install both packages into the managed directory.
    * A graphql-config file at the workspace root is *required*, not merely helpful for
      cross-file navigation: ``graphql-language-service-server`` never sets its internal
      "initialized" flag without one, and every request handler (documentSymbol, hover,
      definition, completion, workspaceSymbol) short-circuits to an empty result while that
      flag is unset -- including document symbols for a single, self-contained file. Only
      syntax highlighting (which Serena does not use) keeps working in that case. The
      server logs "graphql-config error, only highlighting is enabled" when this happens;
      we detect that message to fail fast instead of waiting out the full startup timeout.
    * Language is registered as experimental.
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
from collections.abc import Hashable

from overrides import override

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# graphql-language-service-cli provides the `graphql-lsp` binary.
DEFAULT_PACKAGE_VERSION = "3.5.0"
# `graphql` is a peer dependency of graphql-language-service-cli and must be installed alongside it.
DEFAULT_GRAPHQL_VERSION = "16.9.0"
LS_BIN_NAME = "graphql-lsp"

# graphql-config resolution order at the workspace root (mirrors what graphql-language-service-server
# looks for; see module docstring). Checked in this order and the first match wins, same as cosmiconfig.
_GRAPHQL_CONFIG_FILENAMES = (
    ".graphqlrc",
    ".graphqlrc.yml",
    ".graphqlrc.yaml",
    ".graphqlrc.json",
    ".graphqlrc.js",
    ".graphqlrc.ts",
    "graphql.config.yml",
    "graphql.config.yaml",
    "graphql.config.json",
    "graphql.config.js",
    "graphql.config.ts",
    "package.json",
)


class GraphQLLanguageServer(SolidLanguageServer):
    """
    GraphQL language server using ``graphql-language-service-cli`` (``graphql-lsp``).

    ``ls_specific_settings["graphql"]`` keys:
        * ``graphql_language_service_version``: version of ``graphql-language-service-cli``
          to install (default: ``3.5.0``).
        * ``graphql_version``: version of the peer ``graphql`` package (default: ``16.9.0``).
        * ``npm_registry``: optional alternative npm registry URL.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "graphql",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        # Set from the window/logMessage handler when the server reports it found no
        # graphql-config; guards the final startup log message (see _start_server).
        self._graphql_config_missing = False

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules"]

    @override
    def _raw_document_symbols_cache_fingerprint(self) -> Hashable | None:
        # Whether (and how) a graphql-config file resolves at the workspace root changes every
        # request handler's behavior (see module docstring) without changing the content of any
        # single *.graphql file. The default content-hash-keyed cache has no way to see that, so
        # adding, editing or removing the config would otherwise keep serving results computed
        # before the change indefinitely -- across restarts -- until an affected file's own
        # content happens to change. Fingerprint the resolved config file's content so the cache
        # invalidates whenever it appears, changes or disappears.
        for filename in _GRAPHQL_CONFIG_FILENAMES:
            path = os.path.join(self.repository_root_path, filename)
            try:
                with open(path, "rb") as f:
                    content = f.read()
            except OSError:
                continue
            if filename == "package.json" and b'"graphql"' not in content:
                # package.json is only a graphql-config if it has a "graphql" key; otherwise it's
                # not a match and we keep looking (cosmiconfig's own resolution behaves the same way).
                continue
            return (filename, hashlib.sha256(content).hexdigest())
        return None

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            assert shutil.which("node") is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            assert shutil.which("npm") is not None, "npm is not installed or isn't in PATH. Please install npm and try again."

            package_version = self._custom_settings.get("graphql_language_service_version", DEFAULT_PACKAGE_VERSION)
            graphql_version = self._custom_settings.get("graphql_version", DEFAULT_GRAPHQL_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            ls_dirname = f"graphql-lsp-{package_version}"
            install_dir = os.path.join(self._ls_resources_dir, ls_dirname)
            executable_path = os.path.join(install_dir, "node_modules", ".bin", LS_BIN_NAME)
            if os.name == "nt":
                executable_path += ".cmd"

            if not os.path.exists(executable_path):
                log.info("Installing graphql-language-service-cli@%s (with graphql@%s)...", package_version, graphql_version)
                deps = RuntimeDependencyCollection(
                    [
                        # graphql (the peer dependency) is installed first so the CLI's peer requirement
                        # is already satisfied when it is added.
                        RuntimeDependency(
                            id="graphql",
                            description="graphql (peer dependency of graphql-language-service-cli)",
                            command=build_npm_install_command("graphql", graphql_version, npm_registry),
                            platform_id="any",
                        ),
                        RuntimeDependency(
                            id="graphql-language-service-cli",
                            description="GraphQL language server (graphql-lsp)",
                            command=build_npm_install_command("graphql-language-service-cli", package_version, npm_registry),
                            platform_id="any",
                        ),
                    ]
                )
                deps.install(install_dir)

            if not os.path.exists(executable_path):
                raise FileNotFoundError(
                    f"{LS_BIN_NAME} executable not found at {executable_path}; "
                    f"npm install of graphql-language-service-cli@{package_version} did not produce the expected binary."
                )
            return executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # `server -m stream` runs the LSP over stdio (stdin/stdout).
            return [core_path, "server", "-m", "stream"]

    def _create_base_initialize_params(self) -> dict:
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
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
        }
        return initialize_params

    @staticmethod
    def _handle_workspace_configuration(params: dict) -> list[dict]:
        # graphql-language-service-server issues workspace/configuration after initialize to
        # fetch its ``graphql-config`` settings. The LSP contract requires one response entry
        # per requested item; leaving it unanswered stops the server from building its schema
        # cache, which makes documentSymbol / definition come back empty. We reply with an
        # empty settings object per item so the server falls back to the on-disk
        # ``.graphqlrc`` / ``graphql.config.*`` it discovers at the workspace root.
        items = params.get("items", []) if isinstance(params, dict) else []
        return [{} for _ in items] or [{}]

    def _start_server(self) -> None:
        def do_nothing(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)
            text = str(msg.get("message", ""))
            lower = text.lower()
            # graphql-language-service-server builds its schema/document caches asynchronously
            # (triggered by the workspace/didChangeConfiguration we send below) and only sets
            # its internal `_isInitialized` flag once they are ready. Until then documentSymbol
            # requests short-circuit to []. It logs this exact line when the caches are ready,
            # so we use it as the readiness signal.
            if "caches initialized" in lower:
                self.server_ready.set()
            # Without a graphql-config file at the workspace root, the server logs this exact
            # warning and *never* sets `_isInitialized` -- "caches initialized" above will
            # therefore never arrive, and (contrary to what one might expect) every request
            # handler, including documentSymbol for a single self-contained file, short-circuits
            # to an empty result until that flag is set. Treat this as an immediate negative
            # readiness signal instead of waiting out the full startup timeout for a signal that
            # will provably never come.
            elif "graphql-config error" in lower:
                self._graphql_config_missing = True
                log.warning(
                    "GraphQL language server found no graphql-config (.graphqlrc.yml / "
                    "graphql.config.{yml,yaml,json,js,ts}) at the workspace root; document "
                    "symbols, hover, go-to-definition, completion and workspace symbols will all "
                    "return empty results until one is added. Server message: %s",
                    text,
                )
                self.server_ready.set()

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_request("client/registerCapability", lambda _params: None)
        self.server.on_request("workspace/configuration", self._handle_workspace_configuration)

        log.info("Starting graphql-language-service-cli (graphql-lsp)")
        self.server.start()
        init_params = self._create_initialize_params()
        init_response = self.server.send.initialize(init_params)
        log.debug("GraphQL LS initialize response: %s", init_response)
        assert "completionProvider" in init_response["capabilities"], "GraphQL LSP did not advertise completionProvider"
        self.server.notify.initialized({})

        # Eagerly trigger cache initialization: the server (re)builds its caches on
        # workspace/didChangeConfiguration without needing any file to be opened first.
        # Doing this here — and waiting for the readiness log — avoids a race where the
        # very first documentSymbol request arrives before the caches exist and returns [].
        self.server.notify.workspace_did_change_configuration({"settings": {}})
        if not self.server_ready.wait(timeout=30.0):
            log.warning("Timed out waiting for GraphQL language server caches to initialize; proceeding anyway")
            self.server_ready.set()
        elif not self._graphql_config_missing:
            log.info("GraphQL language server caches initialized")
