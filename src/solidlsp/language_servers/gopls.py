import hashlib
import json
import logging
import os
import re
import subprocess
from collections.abc import Hashable
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, RawDocumentSymbol, SolidLanguageServer, SymbolBodyFactory
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class Gopls(SolidLanguageServer):
    """
    Provides Go specific instantiation of the LanguageServer class using gopls.
    """

    # matches a line prefix that consists solely of a leading `type`/`var`/`const` declaration
    # keyword (with optional indentation and the whitespace before the declared identifier).
    # gopls reports the symbol range of such single declarations starting at the identifier,
    # i.e. after the keyword, whereas `func` declarations include the `func` keyword.
    _LEADING_DECL_KEYWORD_RE = re.compile(r"(?P<indent>\s*)(?:type|var|const)\s+")

    @classmethod
    def supports_implementation_request(cls) -> bool:
        return True

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Go projects, we should ignore:
        # - vendor: third-party dependencies vendored into the project
        # - node_modules: if the project has JavaScript components
        # - dist/build: common output directories
        return super().is_ignored_dirname(dirname) or dirname in ["vendor", "node_modules", "dist", "build"]

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """Classify gopls stderr output to avoid false-positive errors."""
        line_lower = line.lower()

        # File discovery messages that are not actual errors
        if any(
            [
                "discover.go:" in line_lower,
                "walker.go:" in line_lower,
                "walking of {file://" in line_lower,
                "bus: -> discover" in line_lower,
            ]
        ):
            return logging.DEBUG

        return SolidLanguageServer._determine_log_level(line)

    @staticmethod
    def _get_go_version() -> str | None:
        """Get the installed Go version or None if not found."""
        try:
            result = subprocess.run(["go", "version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _get_gopls_version() -> str | None:
        """Get the installed gopls version or None if not found."""
        try:
            result = subprocess.run(["gopls", "version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _setup_runtime_dependency() -> bool:
        """
        Check if required Go runtime dependencies are available.
        Raises RuntimeError with helpful message if dependencies are missing.
        """
        go_version = Gopls._get_go_version()
        if not go_version:
            raise RuntimeError(
                "Go is not installed. Please install Go from https://golang.org/doc/install and make sure it is added to your PATH."
            )

        gopls_version = Gopls._get_gopls_version()
        if not gopls_version:
            raise RuntimeError(
                "Found a Go version but gopls is not installed.\n"
                "Please install gopls as described in https://pkg.go.dev/golang.org/x/tools/gopls#section-readme\n\n"
                "After installation, make sure it is added to your PATH (it might be installed in a different location than Go)."
            )

        return True

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        self._setup_runtime_dependency()

        super().__init__(config, repository_root_path, ProcessLaunchInfo(cmd="gopls", cwd=repository_root_path), "go", solidlsp_settings)
        self.request_id = 0

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialize params for the Go Language Server.
        """
        initialize_params: dict = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "workspace": {"workspaceFolders": True, "didChangeConfiguration": {"dynamicRegistration": True}},
            },
        }

        # Apply gopls-specific settings via initializationOptions
        # Serena applies gopls settings at initialization time via initializationOptions
        # (Access settings directly to avoid extra INFO logging from CustomLSSettings.get.)
        gopls_settings = self._custom_settings.settings.get("gopls_settings")
        if gopls_settings:
            gopls_settings = self._validate_gopls_settings_dict(gopls_settings)

            # Validate JSON-serializability early: initializationOptions is sent over JSON-RPC.
            import json

            self._canonical_json_or_raise(json, gopls_settings)

            # Log keys only (and at DEBUG) to avoid leaking sensitive values and to reduce startup noise.
            log.debug("Applying gopls settings via initializationOptions: keys=%s", list(gopls_settings.keys()))
            initialize_params["initializationOptions"] = gopls_settings

        return initialize_params

    def _validate_gopls_settings_dict(self, gopls_settings: object) -> dict:
        if not isinstance(gopls_settings, dict):
            raise TypeError(
                f"gopls_settings must be a dict, got {type(gopls_settings).__name__}. "
                "Expected structure: {'buildFlags': ['-tags=foo'], 'env': {...}, ...}"
            )

        return gopls_settings

    def _canonical_json_or_raise(self, json_module: Any, data: object) -> str:
        try:
            return json_module.dumps(data, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "gopls_settings must be JSON-serializable (json.dumps). Use JSON-compatible values (dict/list/str/int/float/bool/null) and prefer string keys."
            ) from exc

    # Environment variables that influence Go build context and affect cached symbols.
    _CACHE_CONTEXT_ENV_KEYS = ("GOFLAGS", "GOOS", "GOARCH", "CGO_ENABLED")

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable:
        normalize_symbol_name_version = 1
        request_document_symbols_impl_version = 2
        return normalize_symbol_name_version, request_document_symbols_impl_version

    @override
    def _raw_document_symbols_cache_fingerprint(self) -> Hashable:
        gopls_settings_raw = self._custom_settings.settings.get("gopls_settings")

        gopls_settings: dict | None
        if gopls_settings_raw is None:
            gopls_settings = None
        else:
            # Treat an explicitly empty dict the same as not providing settings at all.
            gopls_settings = self._validate_gopls_settings_dict(gopls_settings_raw) or None

        # Only include env vars that are set to a non-empty value.
        env_subset: dict[str, str] = {}
        for key in self._CACHE_CONTEXT_ENV_KEYS:
            value = os.environ.get(key)
            if value:
                env_subset[key] = value

        # Version processed symbols even when the build context itself is empty.
        if gopls_settings is None and not env_subset:
            return None
        else:
            fingerprint_data: dict[str, object] = {
                "env": env_subset,
            }
            if gopls_settings is not None:
                fingerprint_data["gopls_settings"] = gopls_settings
            canonical_json = self._canonical_json_or_raise(json, fingerprint_data)
            return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]

    @override
    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        return symbol["name"].rsplit(".", 1)[-1]

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        # Override to extend single `type`/`var`/`const` declaration ranges to include the leading
        # keyword. gopls excludes the keyword from such ranges (unlike `func` declarations), which
        # causes replace_symbol_body to drop the keyword from the symbol body and replacement range;
        # a natural keyword-inclusive round-trip edit would then corrupt the file (e.g. `type Foo`
        # becomes `type type Foo`). See _extend_go_symbol_range_to_include_leading_keyword.
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)
        if not document_symbols.root_symbols:
            return document_symbols

        # obtain the file lines and a body factory to recompute the bodies of extended symbols
        with self._open_file_context(relative_file_path, file_buffer, open_in_ls=False) as file_data:
            file_lines = file_data.split_lines()
            body_factory = SymbolBodyFactory(file_data)

            # extend ranges recursively, operating on copies so the cached symbols are not mutated.
            # Children keep their `parent` back-pointer aimed at the original (un-extended) node;
            # this is intentional and safe, because ancestor traversal only reads name/kind/overload
            # index (see Symbol.iter_ancestors), none of which the extension changes. Rebinding the
            # back-pointers would force a deep copy of every extended subtree for no observable gain.
            def extend_symbol_and_children(symbol: ls_types.UnifiedSymbolInformation) -> ls_types.UnifiedSymbolInformation:
                extended = self._extend_go_symbol_range_to_include_leading_keyword(symbol, file_lines, body_factory)
                children = symbol.get("children")
                if children:
                    if extended is symbol:
                        extended = symbol.copy()
                    extended["children"] = [extend_symbol_and_children(child) for child in children]
                return extended

            extended_root_symbols = [extend_symbol_and_children(sym) for sym in document_symbols.root_symbols]

        return DocumentSymbols(extended_root_symbols)

    def _extend_go_symbol_range_to_include_leading_keyword(
        self,
        symbol: ls_types.UnifiedSymbolInformation,
        file_lines: list[str],
        body_factory: SymbolBodyFactory,
    ) -> ls_types.UnifiedSymbolInformation:
        """
        Extend a Go symbol's body range to include a leading `type`/`var`/`const` keyword.

        gopls reports the range of a single `type`/`var`/`const` declaration starting at the
        declared identifier (after the keyword), whereas the range of a `func` declaration includes
        the `func` keyword. This asymmetry makes :meth:`replace_symbol_body` omit the keyword from
        both the displayed body and the replacement range, so re-supplying the keyword in an edit
        corrupts the file (e.g. ``type Foo`` becomes ``type type Foo``).

        :param symbol: the symbol whose range may be extended.
        :param file_lines: the lines of the file in which the symbol is defined.
        :param body_factory: the factory used to recompute the symbol body from the extended range.
        :return: a copy of the symbol with an extended range, or the original symbol if no leading
            keyword precedes the identifier on the start line (e.g. for funcs or for grouped
            declarations such as ``var ( ... )`` whose keyword sits on a separate line).
        """
        # determine whether only a declaration keyword precedes the identifier on the start line
        range_info = symbol["range"]
        start_line = range_info["start"]["line"]
        start_char = range_info["start"]["character"]
        if start_line >= len(file_lines):
            return symbol
        prefix = file_lines[start_line][:start_char]
        match = self._LEADING_DECL_KEYWORD_RE.fullmatch(prefix)
        if match is None:
            return symbol

        # extend the range start back to the keyword (excluding indentation), updating both the
        # symbol range and its location range so the replacement range covers the keyword
        new_start = ls_types.Position(line=start_line, character=len(match.group("indent")))
        extended = symbol.copy()
        extended["range"] = ls_types.Range(start=new_start, end=range_info["end"])
        location = extended.get("location")
        if location:
            location = location.copy()
            if "range" in location:
                location["range"] = ls_types.Range(start=new_start, end=location["range"]["end"])
            extended["location"] = location

        # recompute the body from the now-extended location range so the displayed body stays
        # consistent with the replacement range; the stale body must be removed first, since the
        # factory returns an existing SymbolBody as-is and otherwise reads the updated location range
        extended.pop("body", None)
        extended["body"] = body_factory.create_symbol_body(extended)
        return extended

    def _start_server(self) -> None:
        """Start gopls server process"""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting gopls server process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # gopls server is typically ready immediately after initialization
        # (no need to wait for events)
