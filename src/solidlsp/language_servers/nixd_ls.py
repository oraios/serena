# type: ignore
"""
Provides Nix specific instantiation of the LanguageServer class using nixd (Nix Language Server).

Note: Windows is not supported as Nix itself doesn't support Windows natively.
"""

import json
import logging
import platform
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.dependency_provider import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import subprocess_run

log = logging.getLogger(__name__)


class NixLanguageServer(SolidLanguageServer):
    """
    Provides Nix specific instantiation of the LanguageServer class using nixd.
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        """Provides the nixd launch command and managed dependency fallback."""

        @staticmethod
        def _get_nixd_path() -> str | None:
            """Return an existing nixd executable path, if one can be found."""
            nixd_path = shutil.which("nixd")
            if nixd_path:
                return nixd_path

            home = Path.home()
            possible_paths = [
                home / ".local" / "bin" / "nixd",
                home / ".serena" / "language_servers" / "nixd" / "nixd",
                home / ".nix-profile" / "bin" / "nixd",
                Path("/usr/local/bin/nixd"),
                Path("/run/current-system/sw/bin/nixd"),
                Path("/opt/homebrew/bin/nixd"),
                Path("/usr/local/opt/nixd/bin/nixd"),
            ]

            if platform.system() == "Windows":
                possible_paths.extend(
                    [
                        home / "AppData" / "Local" / "nixd" / "nixd.exe",
                        home / ".serena" / "language_servers" / "nixd" / "nixd.exe",
                    ]
                )

            for path in possible_paths:
                if path.exists():
                    return str(path)

            return None

        @staticmethod
        def _install_nixd_with_nix() -> str | None:
            """Install nixd through Nix and return the resulting executable path."""
            if not shutil.which("nix"):
                return None

            log.info("Installing nixd using nix... This may take a few minutes.")
            try:
                result = subprocess_run(
                    ["nix", "profile", "install", "github:nix-community/nixd"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=600,
                )

                if result.returncode == 0:
                    nixd_path = shutil.which("nixd")
                    if nixd_path:
                        log.info("Successfully installed nixd at: %s", nixd_path)
                        return nixd_path
                else:
                    result = subprocess_run(
                        ["nix-env", "-iA", "nixpkgs.nixd"],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=600,
                    )
                    if result.returncode == 0:
                        nixd_path = shutil.which("nixd")
                        if nixd_path:
                            log.info("Successfully installed nixd at: %s", nixd_path)
                            return nixd_path
                    log.error("Failed to install nixd: %s", result.stderr)

            except subprocess.TimeoutExpired:
                log.error("Nix install timed out after 10 minutes")
            except Exception:
                log.exception("Error installing nixd with nix")

            return None

        def _get_or_install_core_dependency(self) -> str:
            """Return a working nixd path, installing nixd when necessary."""
            if not shutil.which("nix"):
                log.error("Nix is not installed. nixd requires Nix to function properly.")
                raise RuntimeError("Nix is required for nixd. Please install Nix from https://nixos.org/download.html")

            nixd_path = self._get_nixd_path()
            if not nixd_path:
                log.info("nixd not found. Attempting to install...")
                nixd_path = self._install_nixd_with_nix()

            if not nixd_path:
                raise RuntimeError(
                    "nixd (Nix Language Server) is not installed.\n"
                    "Please install nixd using one of the following methods:\n"
                    "  - Using Nix flakes: nix profile install github:nix-community/nixd\n"
                    "  - From nixpkgs: nix-env -iA nixpkgs.nixd\n"
                    "  - On macOS with Homebrew: brew install nixd\n\n"
                    "After installation, make sure 'nixd' is in your PATH."
                )

            try:
                result = subprocess_run([nixd_path, "--version"], capture_output=True, text=True, check=False, timeout=5)
                if result.returncode != 0:
                    raise RuntimeError(f"nixd failed to run: {result.stderr}")
            except Exception as exc:
                raise RuntimeError(f"Failed to verify nixd installation: {exc}") from exc

            return nixd_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            """Return the nixd stdio launch command."""
            return [core_path]

    def _extend_nix_symbol_range_to_include_semicolon(
        self, symbol: ls_types.UnifiedSymbolInformation, file_content: str
    ) -> ls_types.UnifiedSymbolInformation:
        """
        Extend symbol range to include trailing semicolon for Nix attribute symbols.

        nixd provides ranges that exclude semicolons (expression-level), but serena needs
        statement-level ranges that include semicolons for proper replacement.
        """
        range_info = symbol["range"]
        end_line = range_info["end"]["line"]
        end_char = range_info["end"]["character"]

        # Split file content into lines
        lines = file_content.split("\n")
        if end_line >= len(lines):
            return symbol

        line = lines[end_line]

        # Check if there's a semicolon immediately after the current range end
        if end_char < len(line) and line[end_char] == ";":
            # Extend range to include the semicolon
            new_range = {"start": range_info["start"], "end": {"line": end_line, "character": end_char + 1}}

            # Create modified symbol with extended range
            extended_symbol = symbol.copy()
            extended_symbol["range"] = new_range

            # CRITICAL: Also update the location.range if it exists
            if extended_symbol.get("location"):
                location = extended_symbol["location"].copy()
                if "range" in location:
                    location["range"] = new_range.copy()
                extended_symbol["location"] = location

            return extended_symbol

        return symbol

    @override
    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        # Override to extend Nix symbol ranges to include trailing semicolons.
        # nixd provides expression-level ranges (excluding semicolons) but serena needs
        # statement-level ranges (including semicolons) for proper symbol replacement.

        # Get symbols from parent implementation
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)

        # Get file content for range extension
        file_content = self.language_server.retrieve_full_file_content(relative_file_path)

        # Extend ranges for all symbols recursively
        def extend_symbol_and_children(symbol: ls_types.UnifiedSymbolInformation) -> ls_types.UnifiedSymbolInformation:
            # Extend this symbol's range
            extended = self._extend_nix_symbol_range_to_include_semicolon(symbol, file_content)

            # Extend children recursively
            if extended.get("children"):
                extended["children"] = [extend_symbol_and_children(child) for child in extended["children"]]

            return extended

        # Apply range extension to all symbols
        extended_root_symbols = [extend_symbol_and_children(sym) for sym in document_symbols.root_symbols]

        return DocumentSymbols(extended_root_symbols)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Nix projects, we should ignore:
        # - result: nix build output symlinks
        # - result-*: multiple build outputs
        # - .direnv: direnv cache
        return super().is_ignored_dirname(dirname) or dirname in ["result", ".direnv"] or dirname.startswith("result-")

    @staticmethod
    def _create_default_nixd_settings() -> dict[str, Any]:
        """Return the default settings sent to nixd."""
        return {
            "nixpkgs": {"expr": "import <nixpkgs> { }"},
            "formatting": {"command": ["nixpkgs-fmt"]},
            "options": {
                "enable": True,
                "target": {
                    "installable": "",
                },
            },
        }

    @classmethod
    def _load_nixd_settings(cls, custom_settings: SolidLSPSettings.CustomLSSettings) -> dict[str, Any]:
        """Load nixd settings from ``config_path`` or return the built-in defaults.

        :param custom_settings: Nix-specific language-server settings.
        :return: The value of the nixd configuration section.
        :raises ValueError: If ``config_path`` or its JSON document has an invalid shape.
        :raises RuntimeError: If the configuration file cannot be read.
        """
        config_path_value = custom_settings.get("config_path")
        if config_path_value is None:
            return cls._create_default_nixd_settings()
        if not isinstance(config_path_value, str) or not config_path_value.strip():
            raise ValueError("ls_specific_settings.nix.config_path must be a non-empty absolute path")

        config_path = Path(config_path_value).expanduser()
        if not config_path.is_absolute():
            raise ValueError(f"ls_specific_settings.nix.config_path must be absolute: {config_path_value!r}")

        try:
            with config_path.open(encoding="utf-8") as config_file:
                settings = json.load(config_file)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in nixd configuration file '{config_path}': {exc.msg} (line {exc.lineno}, column {exc.colno})"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"Failed to read nixd configuration file '{config_path}': {exc}") from exc

        if not isinstance(settings, dict):
            raise ValueError(
                f"Invalid nixd configuration file '{config_path}': expected a JSON object containing the value of the 'nixd' section"
            )
        return settings

    @staticmethod
    def _resolve_nixd_configuration_section(settings: dict[str, Any], section: object) -> Any:
        """Resolve a ``nixd`` configuration section from the effective settings."""
        if section == "nixd":
            return deepcopy(settings)
        if not isinstance(section, str) or not section.startswith("nixd."):
            return {}

        value: Any = settings
        for key in section.removeprefix("nixd.").split("."):
            if not key or not isinstance(value, dict) or key not in value:
                return {}
            value = value[key]
        return deepcopy(value)

    @classmethod
    def _get_workspace_configuration(cls, params: object, settings: dict[str, Any]) -> list[Any]:
        """Return configuration values matching each requested item in order."""
        if not isinstance(params, dict):
            return []

        items = params.get("items", [])
        if not isinstance(items, list):
            return []

        return [
            cls._resolve_nixd_configuration_section(settings, item.get("section") if isinstance(item, dict) else None) for item in items
        ]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        custom_settings = solidlsp_settings.get_ls_specific_settings(config.ls_id)
        self._nixd_settings = self._load_nixd_settings(custom_settings)

        super().__init__(config, repository_root_path, None, "nix", solidlsp_settings)
        self.request_id = 0

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        """Create the provider that resolves the nixd launch command."""
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialize params for nixd.
        """
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "",
                                    "quickfix",
                                    "refactor",
                                    "refactor.extract",
                                    "refactor.inline",
                                    "refactor.rewrite",
                                    "source",
                                    "source.organizeImports",
                                ]
                            }
                        },
                    },
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "configuration": True,
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
            },
            "initializationOptions": deepcopy(self._nixd_settings),
        }
        return initialize_params

    def _start_server(self):
        """Start nixd server process"""
        initialize_params = self._create_initialize_params()
        nixd_settings = initialize_params.get("initializationOptions", {})
        if not isinstance(nixd_settings, dict):
            nixd_settings = {}

        def register_capability_handler(params):
            return

        def workspace_configuration_handler(params):
            return self._get_workspace_configuration(params, nixd_settings)

        def window_log_message(msg):
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting nixd server process")
        self.server.start()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # nixd server is typically ready immediately after initialization
