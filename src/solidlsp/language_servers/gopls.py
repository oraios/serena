import logging
import os
import pathlib
import subprocess
from typing import Any, cast

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class Gopls(SolidLanguageServer):
    """
    Provides Go specific instantiation of the LanguageServer class using gopls.
    """

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

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Go Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
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

        return cast(InitializeParams, initialize_params)

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
    def _cache_context_fingerprint(self) -> str | None:
        """
        Compute a deterministic fingerprint of the Go build context.

        The fingerprint includes gopls_settings and selected env vars that affect symbol discovery.
        """
        import hashlib
        import json

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

        # Return None only when BOTH settings and env subset are effectively empty.
        if gopls_settings is None and not env_subset:
            return None

        fingerprint_data: dict[str, object] = {"env": env_subset}
        if gopls_settings is not None:
            fingerprint_data["gopls_settings"] = gopls_settings

        canonical_json = self._canonical_json_or_raise(json, fingerprint_data)

        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]

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
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # gopls server is typically ready immediately after initialization
        # (no need to wait for events)
