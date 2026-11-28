"""
Provides GraphQL support via the ``graphql-language-service-cli`` npm package
(https://github.com/graphql/graphql-language-service), whose ``graphql-lsp`` binary
implements the Language Server Protocol.

The server resolves schema/operation relationships through graphql-config: it searches the
workspace root (and then its parent directories) for a ``.graphqlrc*`` / ``graphql.config.*``
file (or a ``graphql`` key in ``package.json``) to learn where the schema and the GraphQL
documents live.

Caveats:
    * ``graphql-language-service-cli`` declares ``graphql`` as a *peer* dependency, so we
      install both packages into the managed directory.
    * A usable graphql-config file is *required*, not merely helpful for cross-file
      navigation: ``graphql-language-service-server`` never sets its internal "initialized"
      flag without one, and every request handler (documentSymbol, hover, definition,
      completion, workspaceSymbol) short-circuits to an empty result while that flag is
      unset -- including document symbols for a single, self-contained file. Only syntax
      highlighting (which Serena does not use) keeps working in that case. The server logs
      "graphql-config error, only highlighting is enabled" when this happens; we detect that
      message to fail fast instead of waiting out the full startup timeout.
    * That same "graphql-config error" line is also logged in a much milder situation: the
      config loaded and the caches came up, but the schema it points at does not fully
      resolve (e.g. it uses a directive that the server declares programmatically and that
      is never declared in SDL). Requests are served normally then -- document symbols come
      back -- while the schema-backed features are degraded. The server does not distinguish
      the two cases in its message, so we branch on whether the caches ever initialized.
    * The server reports document symbols as a flat list; the hierarchy is reconstructed
      on the client side (see :class:`GraphQLLanguageServer._SymbolTreeBuilder`).
    * The server advertises full text document synchronization and treats the text of any
      change as the entire new contents of the file.
    * The server tests whether a document is a graphql-config file by matching its URI against
      the patterns in :attr:`GraphQLLanguageServer._CONFIG_FILE_URI_PATTERN`, so a document
      whose path merely contains such a name (e.g. a directory named ``graphql_config``) is
      mistaken for a config file: opening it reloads the server's whole configuration and
      its own contents are never read. Such documents are therefore re-sent as a change after
      being opened, which the server processes without that test.
    * Language is registered as experimental.
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import bisect
import logging
import os
import re
import shutil
import threading
from typing import cast

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.lsp_protocol_handler.lsp_constants import LSPConstants
from solidlsp.lsp_protocol_handler.lsp_types import DocumentSymbol, ErrorCodes, Position, Range, SymbolInformation
from solidlsp.lsp_protocol_handler.server import LSPError
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# graphql-language-service-cli provides the `graphql-lsp` binary.
DEFAULT_PACKAGE_VERSION = "3.5.0"
# `graphql` is a peer dependency of graphql-language-service-cli and must be installed alongside it.
DEFAULT_GRAPHQL_VERSION = "16.9.0"
LS_BIN_NAME = "graphql-lsp"


class GraphQLLanguageServer(SolidLanguageServer):
    """
    GraphQL language server using ``graphql-language-service-cli`` (``graphql-lsp``).

    ``ls_specific_settings["graphql"]`` keys:
        * ``graphql_language_service_version``: version of ``graphql-language-service-cli``
          to install (default: ``3.5.0``).
        * ``graphql_version``: version of the peer ``graphql`` package (default: ``16.9.0``).
        * ``npm_registry``: optional alternative npm registry URL.
    """

    _CONFIG_FILE_URI_PATTERN = re.compile("graphql.config|graphqlrc|graphqlconfig")
    """
    the patterns which the server searches for in a document's URI in order to determine whether the document is
    a graphql-config file. They are regular expressions, so the "." matches any character.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "graphql",
            solidlsp_settings,
            cache_version_raw_document_symbols=2,
        )
        self.server_ready = threading.Event()
        # Set from the window/logMessage handler when the server reports it found no
        # graphql-config; guards the final startup log message (see _start_server).
        self._graphql_config_unusable = False
        self._schema_degradation_reported = False
        self._config_file_uri_collision_reported = False

    @override
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules"]

    @override
    def _requires_full_text_document_sync(self) -> bool:
        return True

    @override
    def _handle_file_opened_in_ls(self, file_buffer: LSPFileBuffer) -> None:
        if not self._CONFIG_FILE_URI_PATTERN.search(file_buffer.uri):
            return

        # warning about the cost of the workaround (once per session)
        if not self._config_file_uri_collision_reported:
            self._config_file_uri_collision_reported = True
            log.warning(
                "The path of %s contains a name which the GraphQL language server mistakes for a graphql-config "
                "file name (pattern: %s). Serena works around this, but every time such a file is opened, the "
                "server reloads its entire configuration and project files, which is slow for large projects. "
                "Rename the directory concerned to avoid this.",
                file_buffer.abs_path,
                self._CONFIG_FILE_URI_PATTERN.pattern,
            )

        # re-sending the contents as a change makes the server parse and cache the document
        file_buffer.version += 1
        self.server.notify.did_change_text_document(
            {  # ty: ignore[invalid-argument-type]  # dict built from LSPConstants keys; shape matches the TypedDict
                LSPConstants.TEXT_DOCUMENT: {
                    LSPConstants.URI: file_buffer.uri,
                    LSPConstants.VERSION: file_buffer.version,
                },
                LSPConstants.CONTENT_CHANGES: [{LSPConstants.TEXT: file_buffer.contents}],
            }
        )

    @override
    def _request_raw_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
        with self._open_file_context(relative_file_path, file_buffer=file_data) as file_buffer:
            symbols = super()._request_raw_document_symbols(relative_file_path, file_buffer)
            if not symbols or "location" not in symbols[0]:
                return symbols
            return self._SymbolTreeBuilder(file_buffer.contents).build(cast(list[SymbolInformation], symbols))

    @override
    def _request_hover(self, file_buffer: LSPFileBuffer, line: int, column: int) -> ls_types.Hover | None:
        # The server builds the schema for every hover request and fails the request with an internal error
        # if the schema does not resolve (see module docstring); this is a lack of hover information, which
        # was already reported to the user at startup, not a failure of the caller's operation.
        try:
            return super()._request_hover(file_buffer, line, column)
        except SolidLSPException as e:
            if isinstance(e.cause, LSPError) and e.cause.code == ErrorCodes.InternalError:
                log.debug("GraphQL language server could not provide hover information: %s", e.cause)
                return None
            raise

    class _SymbolTreeBuilder:
        """
        Builder of the hierarchical document symbols of a GraphQL document from the flat list of symbols reported for it.

        The server reports each node of the document's outline (definitions, fields, arguments, enum values, selections
        and fragment spreads) as a ``SymbolInformation`` whose range spans the node's entire source text, so the nesting
        of the nodes is given by the containment of their ranges. (The ``containerName`` cannot serve for this: it is
        unset for the selections of anonymous operations, and it does not disambiguate between equally named parents.)
        A symbol's range starts with the description of the definition, if any, and the name is located among the
        tokens following it.

        Positions are treated as character offsets within lines, as everywhere in Serena.
        """

        _LINE_BREAK = re.compile(r"\r\n|[\n\r]")
        _LEADING_DESCRIPTION = re.compile(r'\s*(?:"""(?:\\"""|(?!""")[\s\S])*"""|"(?:\\.|[^"\\\n\r])*")')
        _IGNORED_TOKENS = re.compile(r"(?:[ \t\n\r,\ufeff]|#[^\n\r]*)*")
        """
        the source text which is insignificant between tokens: whitespace, commas and comments.
        """
        _TOKEN = re.compile(r"(?P<name>[_A-Za-z][_0-9A-Za-z]*)|\.\.\.|\S")
        _MAX_TOKENS_UP_TO_NAME = 3
        """
        the maximum number of tokens from the start of a symbol's source text (after its description) up to and including
        its name: the name is preceded by at most an alias and its colon (alternatively, by the keyword of a definition
        or the dots of a fragment spread).
        """

        def __init__(self, contents: str):
            """
            :param contents: the contents of the document, as seen by the server when computing the symbols.
            """
            self._contents = contents
            self._line_starts = [0] + [m.end() for m in self._LINE_BREAK.finditer(contents)]

        def build(self, symbols: list[SymbolInformation]) -> list[DocumentSymbol]:
            """
            :param symbols: the symbols reported by the server, in any order.
            :return: the root symbols, each with its descendants, ordered by their position in the document.
            """
            # parents before their children: by start position, and, for equal starts, enclosing ranges first
            nodes = sorted(
                (self._to_document_symbol(symbol) for symbol in symbols),
                key=lambda s: (self._key(s["range"]["start"]), tuple(-x for x in self._key(s["range"]["end"]))),
            )

            # attach each node to the innermost preceding node enclosing it
            roots: list[DocumentSymbol] = []
            enclosing_nodes: list[DocumentSymbol] = []
            for node in nodes:
                while enclosing_nodes and not self._contains(enclosing_nodes[-1]["range"], node["range"]):
                    enclosing_nodes.pop()
                siblings = enclosing_nodes[-1]["children"] if enclosing_nodes else roots
                siblings.append(node)
                enclosing_nodes.append(node)
            return roots

        def _to_document_symbol(self, symbol: SymbolInformation) -> DocumentSymbol:
            symbol_range = symbol["location"]["range"]
            return DocumentSymbol(
                name=symbol["name"],
                kind=symbol["kind"],
                range=symbol_range,
                selectionRange=self._locate_name(symbol["name"], symbol_range),
                children=[],
            )

        def _locate_name(self, name: str, symbol_range: Range) -> Range:
            """
            :return: the range of the given symbol name within the given symbol range, or the symbol range itself if the
                name is not found in it (as for anonymous operations, which are reported under a placeholder name).
            """
            start = self._offset(symbol_range["start"])
            end = self._offset(symbol_range["end"])

            # skip the description preceding the name of a definition
            description = self._LEADING_DESCRIPTION.match(self._contents, start, end)
            if description is not None:
                start = description.end()

            # read the leading tokens, which include the name
            tokens: list[re.Match[str]] = []
            while len(tokens) < self._MAX_TOKENS_UP_TO_NAME:
                start = cast(re.Match[str], self._IGNORED_TOKENS.match(self._contents, start, end)).end()
                token = self._TOKEN.match(self._contents, start, end)
                if token is None:
                    break
                tokens.append(token)
                start = token.end()

            # select the name tokens that can be the symbol's name: a name directly following another name is
            # the name of a definition (following its keyword), which may be equal to the keyword
            name_tokens = [token for token in tokens if token.group("name") is not None]
            if len(tokens) >= 2 and tokens[0] in name_tokens and tokens[1] in name_tokens:
                name_tokens = [tokens[1]]

            for token in name_tokens:
                if token.group() == name:
                    return Range(start=self._position(token.start()), end=self._position(token.end()))
            return symbol_range

        def _offset(self, position: Position) -> int:
            line = min(position["line"], len(self._line_starts) - 1)
            return min(self._line_starts[line] + position["character"], len(self._contents))

        def _position(self, offset: int) -> Position:
            line = bisect.bisect_right(self._line_starts, offset) - 1
            return Position(line=line, character=offset - self._line_starts[line])

        @staticmethod
        def _key(position: Position) -> tuple[int, int]:
            return position["line"], position["character"]

        @classmethod
        def _contains(cls, outer: Range, inner: Range) -> bool:
            return cls._key(outer["start"]) <= cls._key(inner["start"]) and cls._key(inner["end"]) <= cls._key(outer["end"])

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            assert shutil.which("node") is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            assert shutil.which("npm") is not None, "npm is not installed or isn't in PATH. Please install npm and try again."

            package_version = self._custom_settings.get("graphql_language_service_version", DEFAULT_PACKAGE_VERSION)
            graphql_version = self._custom_settings.get("graphql_version", DEFAULT_GRAPHQL_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            # both versions identify the installation, so that changing either one results in a new installation
            ls_dirname = f"graphql-lsp-{package_version}-graphql-{graphql_version}"
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
            # The server logs this for two quite different situations, and does not say which:
            # there is no graphql-config at the workspace root at all, or there is one but it
            # cannot be loaded (e.g. the schema it points at uses a directive that is only
            # declared programmatically on the server side and never in SDL). What separates
            # them observably is whether the caches ever came up, so branch on that rather than
            # asserting a cause we cannot know.
            elif "graphql-config error" in lower:
                if self.server_ready.is_set():
                    # The caches were built, so requests are being served: document symbols for a
                    # single file still come back. This message arrives later, from the server's
                    # background workspace scan, and means the schema could not be fully resolved,
                    # so the features that need it (hover, go-to-definition, completion, workspace
                    # symbols) are degraded. The server repeats it whenever a file is processed.
                    if self._schema_degradation_reported:
                        log.debug("GraphQL language server still cannot load the graphql-config schema: %s", text)
                        return
                    self._schema_degradation_reported = True
                    log.warning(
                        "GraphQL language server could not load the graphql-config schema. Document "
                        "symbols still work, but hover, go-to-definition, completion and workspace "
                        "symbols need the resolved schema and will be degraded. Fix what the server "
                        "reports below (a directive used in the SDL but never declared in it is a "
                        "common cause). Server message: %s",
                        text,
                    )
                else:
                    # The caches never came up. In this state the server *never* sets its internal
                    # `_isInitialized` flag, so "caches initialized" will not arrive and (contrary
                    # to what one might expect) every request handler, including documentSymbol for
                    # a single self-contained file, short-circuits to an empty result. Treat this as
                    # an immediate negative readiness signal instead of waiting out the full startup
                    # timeout for a signal that will provably never come.
                    self._graphql_config_unusable = True
                    log.warning(
                        "GraphQL language server could not use a graphql-config (.graphqlrc.yml / "
                        "graphql.config.{yml,yaml,json,js,ts}) at the workspace root -- either there "
                        "is none, or it failed to load -- and its caches never initialized. In this "
                        "state document symbols, hover, go-to-definition, completion and workspace "
                        "symbols all return empty results. Server message: %s",
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
        elif not self._graphql_config_unusable:
            log.info("GraphQL language server caches initialized")
