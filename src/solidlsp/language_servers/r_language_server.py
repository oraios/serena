import logging
import os
import pathlib
import subprocess
import threading

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class RLanguageServer(SolidLanguageServer):
    """R Language Server implementation using the languageserver R package."""

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For R projects, ignore common directories
        return super().is_ignored_dirname(dirname) or dirname in [
            "renv",  # R environment management
            "packrat",  # Legacy R package management
            ".Rproj.user",  # RStudio project files
            "vignettes",  # Package vignettes (often large)
        ]

    @staticmethod
    def _check_r_installation():
        """Check if R and languageserver are available."""
        try:
            # Check R installation
            result = subprocess.run(["R", "--version"], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError("R is not installed or not in PATH")

            # Check languageserver package
            result = subprocess.run(
                ["R", "--vanilla", "--quiet", "--slave", "-e", "if (!require('languageserver', quietly=TRUE)) quit(status=1)"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "R languageserver package is not installed.\nInstall it with: R -e \"install.packages('languageserver')\""
                )

        except FileNotFoundError:
            raise RuntimeError("R is not installed. Please install R from https://www.r-project.org/")

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        # Check R installation
        self._check_r_installation()

        # R command to start language server
        # Use --vanilla for minimal startup and --quiet to suppress all output except LSP
        # Set specific options to improve parsing stability
        r_cmd = 'R --vanilla --quiet --slave -e "options(languageserver.debug_mode = FALSE); languageserver::run()"'

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=r_cmd, cwd=repository_root_path),
            "r",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Initialize params for R Language Server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
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
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
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
        }
        return initialize_params

    def _start_server(self):
        """Start R Language Server process."""

        def window_log_message(msg):
            self.logger.log(f"R LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params):
            return

        def register_capability_handler(params):
            return

        # Register LSP message handlers
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting R Language Server process", logging.INFO)
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        self.logger.log(
            "Sending initialize request to R Language Server",
            logging.INFO,
        )

        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities
        if "completionProvider" in capabilities:
            self.logger.log("R LSP completion provider available", logging.INFO)
        if "definitionProvider" in capabilities:
            self.logger.log("R LSP definition provider available", logging.INFO)

        self.server.notify.initialized({})
        self.completions_available.set()

        # R Language Server is ready after initialization
        self.server_ready.set()

        # Pre-warm the cache by indexing R files to prevent 1+ minute delay on first symbol search
        self._prewarm_cache()

    @override
    def request_document_symbols(
        self, relative_file_path: str, include_body: bool = False
    ) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
        """
        Override document symbol request with R-specific error handling.

        The R languageserver can throw "invalid AST" errors (-32001) when parsing
        certain R files. This method provides graceful fallback to empty results
        rather than crashing.
        """
        try:
            return super().request_document_symbols(relative_file_path, include_body)
        except SolidLSPException as e:
            # Check if this is an AST parsing error (code -32001)
            if "invalid AST" in str(e).lower() or "-32001" in str(e):
                self.logger.log(
                    f"R Language Server AST parsing error for {relative_file_path}: {e}. "
                    f"This often happens with complex R syntax or when the file has "
                    f"constructs that the languageserver cannot parse. Trying fallback method.",
                    logging.WARNING,
                )
                # Try fallback method for better symbol extraction
                return self._extract_r_symbols_fallback(relative_file_path)
            else:
                # Re-raise other types of LSP exceptions
                raise

    def _prewarm_cache(self) -> None:
        """
        Pre-warm the R language server cache by requesting symbols for R files.
        This prevents the 1+ minute delay on first symbol search by doing the
        expensive parsing work during language server initialization.
        """
        try:

            # Find all R files in the project
            r_files = []
            repo_path = pathlib.Path(self.repository_root_path)
            for pattern in ["*.R", "*.r"]:
                r_files.extend(str(p) for p in repo_path.rglob(pattern))

            # Convert to relative paths
            r_files = [os.path.relpath(f, self.repository_root_path) for f in r_files]

            if not r_files:
                return

            self.logger.log(f"Pre-warming R language server cache for {len(r_files)} R files...", logging.INFO)

            cached_count = 0
            # Process first 10 files to balance startup time vs cache coverage
            for r_file in r_files[:10]:
                try:
                    self.logger.log(f"Caching symbols for {r_file}...", logging.DEBUG)
                    self.request_document_symbols(r_file, include_body=False)
                    cached_count += 1
                except Exception as e:
                    self.logger.log(f"Failed to cache symbols for {r_file}: {e}", logging.WARNING)

            self.logger.log(f"R language server cache pre-warming completed: {cached_count}/{len(r_files[:10])} files cached", logging.INFO)

        except Exception as e:
            # Don't fail language server initialization if pre-warming fails
            self.logger.log(f"R language server pre-warming failed: {e}", logging.WARNING)

    def _extract_r_symbols_fallback(
        self, relative_file_path: str
    ) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
        """
        Fallback method to extract R function symbols using regex parsing.

        This is used when the languageserver fails with AST errors.
        Only extracts function definitions for now.
        """
        import re

        symbols = []

        try:
            # Read the file content
            file_path = pathlib.Path(self.repository_root_path) / relative_file_path
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Pattern to match R function definitions
            # Matches: function_name <- function(params) or function_name = function(params)
            function_pattern = r"^\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*<-\s*function\s*\("

            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                match = re.match(function_pattern, line)
                if match:
                    function_name = match.group(1)
                    symbols.append(
                        {
                            "name": function_name,
                            "kind": 12,  # SymbolKind.Function
                            "range": {
                                "start": {"line": line_num - 1, "character": match.start(1)},
                                "end": {"line": line_num - 1, "character": match.end(1)},
                            },
                            "selectionRange": {
                                "start": {"line": line_num - 1, "character": match.start(1)},
                                "end": {"line": line_num - 1, "character": match.end(1)},
                            },
                        }
                    )

            self.logger.log(f"Fallback R symbol extraction found {len(symbols)} function(s) in {relative_file_path}", logging.INFO)

            return symbols, symbols

        except Exception as e:
            self.logger.log(f"Fallback R symbol extraction failed for {relative_file_path}: {e}", logging.WARNING)
            return [], []
