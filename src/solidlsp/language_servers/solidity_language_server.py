import logging
import os
import pathlib
import subprocess
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class SolidityLanguageServer(SolidLanguageServer):
    """Solidity Language Server implementation using nomicfoundation-solidity-language-server."""

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 3.0  # Solidity projects may need time for contract compilation and indexing

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Solidity projects, ignore common directories
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",  # Node.js dependencies
            "artifacts",  # Hardhat compilation artifacts
            "cache",  # Hardhat cache
            "typechain",  # TypeScript type definitions
            "coverage",  # Coverage reports
            ".openzeppelin",  # OpenZeppelin upgrades
            "deployments",  # Hardhat deploy plugin
            "out",  # Foundry build output
            "lib",  # Foundry dependencies
            "crytic-export",  # Slither exports
        ]

    @staticmethod
    def _check_solidity_installation():
        """Check if nomicfoundation-solidity-language-server and solc are available."""
        try:
            # Check nomicfoundation-solidity-language-server (it doesn't support --version)
            # Instead, check if the executable exists and can be run
            result = subprocess.run(
                ["nomicfoundation-solidity-language-server", "--help"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,  # Don't wait too long
            )
            # The language server will likely error without proper LSP setup, but if it's found, that's good enough
            if result.returncode == 127:  # Command not found on Unix/Linux
                raise RuntimeError(
                    "nomicfoundation-solidity-language-server is not installed or not in PATH.\n"
                    "Install it with: npm install -g @nomicfoundation/solidity-language-server"
                )

            # Check solc compiler
            result = subprocess.run(["solc", "--version"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(
                    "solc (Solidity compiler) is not installed or not in PATH.\n"
                    "Install it with: pip3 install solc-select && solc-select install latest && solc-select use latest"
                )

        except subprocess.TimeoutExpired:
            # If it times out, the command exists but is waiting for input - that's fine
            pass
        except FileNotFoundError as e:
            if "nomicfoundation-solidity-language-server" in str(e):
                raise RuntimeError(
                    "nomicfoundation-solidity-language-server is not installed.\n"
                    "Install it with: npm install -g @nomicfoundation/solidity-language-server"
                )
            if "solc" in str(e):
                raise RuntimeError(
                    "solc is not installed.\n"
                    "Install it with: pip3 install solc-select && solc-select install latest && solc-select use latest"
                )

            raise

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        # Check Solidity installation
        self._check_solidity_installation()

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=["nomicfoundation-solidity-language-server", "--stdio"], cwd=repository_root_path),
            "solidity",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Initialize params for Solidity Language Server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                        "resourceOperations": ["create", "rename", "delete"],
                        "failureHandling": "textOnlyTransactional",
                    },
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True, "symbolKind": {"valueSet": list(range(1, 27))}},
                    "executeCommand": {"dynamicRegistration": True},
                    "configuration": True,
                    "workspaceFolders": True,
                },
                "textDocument": {
                    "publishDiagnostics": {"relatedInformation": True, "versionSupport": False, "tagSupport": {"valueSet": [1, 2]}},
                    "synchronization": {"dynamicRegistration": True, "willSave": True, "willSaveWaitUntil": True, "didSave": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "contextSupport": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
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
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "experimental": {},
            },
            "initializationOptions": {
                "preferences": {"includeCompletionsForModuleExports": True, "includeAutomaticOptionalChainCompletions": True}
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params

    def _start_server(self):
        """Start Solidity Language Server process."""

        def window_log_message(msg):
            self.logger.log(f"Solidity LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params):
            return

        def register_capability_handler(params):
            return

        # Register LSP message handlers
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Solidity Language Server process", logging.INFO)
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        self.logger.log(
            "Sending initialize request to Solidity Language Server",
            logging.INFO,
        )

        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities
        if "completionProvider" in capabilities:
            self.logger.log("Solidity LSP completion provider available", logging.INFO)
        if "definitionProvider" in capabilities:
            self.logger.log("Solidity LSP definition provider available", logging.INFO)
        if "hoverProvider" in capabilities:
            self.logger.log("Solidity LSP hover provider available", logging.INFO)

        self.server.notify.initialized({})
        self.completions_available.set()

        # Solidity Language Server is ready after initialization
        self.server_ready.set()
