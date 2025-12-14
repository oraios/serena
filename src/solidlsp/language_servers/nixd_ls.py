# type: ignore
"""
Provides Nix specific instantiation of the LanguageServer class using nixd (Nix Language Server).

Note: Windows is not supported as Nix itself doesn't support Windows natively.
"""

import logging
import os
import pathlib
import platform
import shutil
import subprocess
import threading
from pathlib import Path

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class NixLanguageServer(SolidLanguageServer):
    """
    Provides Nix specific instantiation of the LanguageServer class using nixd.
    """

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
    def _get_nixd_version():
        """Get the installed nixd version or None if not found."""
        try:
            result = subprocess.run(["nixd", "--version"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                # nixd outputs version like: nixd 2.0.0
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _check_nixd_installed():
        """Check if nixd is installed in the system."""
        return shutil.which("nixd") is not None

    @staticmethod
    def _get_nixd_path():
        """Get the path to nixd executable."""
        # First check if it's in PATH
        nixd_path = shutil.which("nixd")
        if nixd_path:
            return nixd_path

        # Check common installation locations
        home = Path.home()
        possible_paths = [
            home / ".local" / "bin" / "nixd",
            home / ".serena" / "language_servers" / "nixd" / "nixd",
            home / ".nix-profile" / "bin" / "nixd",
            Path("/usr/local/bin/nixd"),
            Path("/run/current-system/sw/bin/nixd"),  # NixOS system profile
            Path("/opt/homebrew/bin/nixd"),  # Homebrew on Apple Silicon
            Path("/usr/local/opt/nixd/bin/nixd"),  # Homebrew on Intel Mac
        ]

        # Add Windows-specific paths
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
    def _install_nixd_with_nix():
        """Install nixd using nix if available."""
        # Check if nix is available
        if not shutil.which("nix"):
            return None

        print("Installing nixd using nix... This may take a few minutes.")
        try:
            # Try to install nixd using nix profile
            result = subprocess.run(
                ["nix", "profile", "install", "github:nix-community/nixd"],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,  # 10 minute timeout for building
            )

            if result.returncode == 0:
                # Check if nixd is now in PATH
                nixd_path = shutil.which("nixd")
                if nixd_path:
                    print(f"Successfully installed nixd at: {nixd_path}")
                    return nixd_path
            else:
                # Try nix-env as fallback
                result = subprocess.run(
                    ["nix-env", "-iA", "nixpkgs.nixd"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=600,
                )
                if result.returncode == 0:
                    nixd_path = shutil.which("nixd")
                    if nixd_path:
                        print(f"Successfully installed nixd at: {nixd_path}")
                        return nixd_path
                print(f"Failed to install nixd: {result.stderr}")

        except subprocess.TimeoutExpired:
            print("Nix install timed out after 10 minutes")
        except Exception as e:
            print(f"Error installing nixd with nix: {e}")

        return None

    @staticmethod
    def _setup_runtime_dependency():
        """
        Check if required Nix runtime dependencies are available.
        Attempts to install nixd if not present.
        """
        # First check if Nix is available (nixd needs it at runtime)
        if not shutil.which("nix"):
            print("WARNING: Nix is not installed. nixd requires Nix to function properly.")
            raise RuntimeError("Nix is required for nixd. Please install Nix from https://nixos.org/download.html")

        nixd_path = NixLanguageServer._get_nixd_path()

        if not nixd_path:
            print("nixd not found. Attempting to install...")

            # Try to install with nix if available
            nixd_path = NixLanguageServer._install_nixd_with_nix()

            if not nixd_path:
                raise RuntimeError(
                    "nixd (Nix Language Server) is not installed.\n"
                    "Please install nixd using one of the following methods:\n"
                    "  - Using Nix flakes: nix profile install github:nix-community/nixd\n"
                    "  - From nixpkgs: nix-env -iA nixpkgs.nixd\n"
                    "  - On macOS with Homebrew: brew install nixd\n\n"
                    "After installation, make sure 'nixd' is in your PATH."
                )

        # Verify nixd works
        try:
            result = subprocess.run([nixd_path, "--version"], capture_output=True, text=True, check=False, timeout=5)
            if result.returncode != 0:
                raise RuntimeError(f"nixd failed to run: {result.stderr}")
        except Exception as e:
            raise RuntimeError(f"Failed to verify nixd installation: {e}")

        return nixd_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        nixd_path = self._setup_runtime_dependency()

        super().__init__(config, repository_root_path, ProcessLaunchInfo(cmd=nixd_path, cwd=repository_root_path), "nix", solidlsp_settings)
        self.server_ready = threading.Event()
        self.request_id = 0
        # Cache flake detection and configuration
        self._is_flake_project = self._detect_flake_project(repository_root_path)
        self._nixd_options_config = self._build_options_config(repository_root_path, self._is_flake_project)

    @staticmethod
    def _detect_flake_project(repository_path: str) -> bool:
        """
        Detect if the repository is a flake-based Nix project.

        A flake project is identified by the presence of a flake.nix file
        at the repository root.

        Args:
            repository_path: Absolute path to the repository root

        Returns:
            True if flake.nix exists at the repository root

        """
        flake_path = Path(repository_path) / "flake.nix"
        return flake_path.exists()

    @staticmethod
    def _build_options_config(repository_path: str, is_flake: bool) -> dict:
        """
        Build the nixd options configuration based on project type.

        For flake-based projects, uses builtins.getFlake expressions that
        provide better completions for flake-specific configurations.
        For non-flake projects, uses traditional import expressions.

        Supports option providers:
        - nixos: NixOS system options (auto-detects first nixosConfiguration)
        - home-manager: Home Manager options (when integrated with NixOS)

        Note: flake-parts is intentionally excluded by default because most
        flakes don't use it, and including it causes errors. Users who use
        flake-parts can configure this manually in their editor settings.

        See: https://github.com/nix-community/nixd/blob/main/nixd/docs/configuration.md

        Args:
            repository_path: Absolute path to the repository root
            is_flake: Whether this is a flake-based project

        Returns:
            Dictionary of option providers with their Nix expressions

        """
        if is_flake:
            # Flake-based expressions provide better completions for flake projects
            # These use builtins.getFlake which evaluates the local flake
            #
            # We use a let-binding to:
            # 1. Get the flake once
            # 2. Auto-detect the first nixosConfiguration name (no hardcoded hostname)
            #
            # The expression uses `builtins.head (builtins.attrNames ...)` to get
            # the first available configuration name dynamically.
            flake_let = f"let flake = builtins.getFlake (builtins.toString {repository_path}); "
            first_config = "hostname = builtins.head (builtins.attrNames flake.nixosConfigurations); "

            return {
                # NixOS options from flake's first nixosConfiguration
                # Auto-detects the configuration name using builtins.attrNames
                "nixos": {"expr": f"{flake_let}{first_config}in flake.nixosConfigurations.${{hostname}}.options"},
                # Home-manager options when used as a NixOS module
                # Provides completions for home.* options
                # Uses the same auto-detected hostname
                "home-manager": {
                    "expr": f"{flake_let}{first_config}in flake.nixosConfigurations.${{hostname}}.options.home-manager.users.type.getSubOptions []"
                },
            }
        else:
            # Traditional non-flake expressions
            # These work without a flake.nix and use the system's nixpkgs
            return {
                "nixos": {"expr": "(import <nixpkgs/nixos> { configuration = {}; }).options"},
                # Home-manager options for non-flake setups
                "home-manager": {
                    "expr": "(import <nixpkgs/nixos> { configuration = {}; }).options.home-manager.users.type.getSubOptions []"
                },
            }

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for nixd.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
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
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
            "initializationOptions": {
                # nixd specific options
                # See: https://github.com/nix-community/nixd/blob/main/nixd/docs/configuration.md
                "nixpkgs": {"expr": "import <nixpkgs> { }"},
                "formatting": {"command": ["nixfmt"]},  # or ["alejandra"] or ["nixpkgs-fmt"]
                # Options providers are configured dynamically based on project type
                # (flake vs non-flake) in workspace_configuration_handler
                # Default here provides basic NixOS completions
                "options": {
                    "nixos": {"expr": "(import <nixpkgs/nixos> { configuration = {}; }).options"},
                    "home-manager": {
                        "expr": "(import <nixpkgs/nixos> { configuration = {}; }).options.home-manager.users.type.getSubOptions []"
                    },
                },
                "diagnostic": {"suppress": []},
            },
        }
        return initialize_params

    def _start_server(self):
        """Start nixd server process"""

        def register_capability_handler(params):
            return

        def window_log_message(msg):
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params):
            return

        # Use closure to capture self for accessing cached config
        cached_options = self._nixd_options_config
        is_flake = self._is_flake_project

        def workspace_configuration_handler(params):
            """
            Handle workspace/configuration requests from nixd.

            nixd sends workspace/configuration requests to fetch settings for
            specific configuration sections. This handler returns appropriate
            configuration for each requested section.

            For flake-based projects, returns enhanced options configuration
            including NixOS, home-manager, and flake-parts providers.
            For non-flake projects, returns standard NixOS and home-manager options.

            Args:
                params: Configuration request parameters containing 'items' array
                        with scopeUri and section for each requested config

            Returns:
                List of configuration objects, one for each requested item

            See: https://github.com/nix-community/nixd/blob/main/nixd/docs/configuration.md

            """
            items = params.get("items", [])
            result = []

            for item in items:
                section = item.get("section", "")

                if section == "nixd.nixpkgs":
                    # Nixpkgs expression for evaluation
                    result.append({"expr": "import <nixpkgs> { }"})
                elif section == "nixd.formatting":
                    # Formatting command - nixfmt, alejandra, or nixpkgs-fmt
                    result.append({"command": ["nixfmt"]})
                elif section == "nixd.options":
                    # Options providers configured based on project type
                    # Flake projects get: nixos, home-manager, flake-parts
                    # Non-flake projects get: nixos, home-manager
                    result.append(cached_options)
                elif section == "nixd.diagnostic":
                    # Diagnostic suppression settings
                    result.append({"suppress": []})
                elif section == "nixd":
                    # Full nixd configuration
                    result.append(
                        {
                            "nixpkgs": {"expr": "import <nixpkgs> { }"},
                            "formatting": {"command": ["nixfmt"]},
                            "options": cached_options,
                            "diagnostic": {"suppress": []},
                        }
                    )
                else:
                    # Unknown section - return empty config
                    result.append({})

            log.debug(f"workspace/configuration response for {[i.get('section') for i in items]}: flake={is_flake}")
            return result

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)

        log.info("Starting nixd server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        # nixd server is typically ready immediately after initialization
        self.server_ready.set()
        self.server_ready.wait()
