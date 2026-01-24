"""
Provides Pascal/Free Pascal specific instantiation of the LanguageServer class using pasls.
Contains various configurations and settings specific to Pascal and Free Pascal.

pasls installation strategy:
1. Use existing pasls from PATH
2. Download prebuilt binary from GitHub releases

Supported platforms for binary download:
- linux-x64, linux-arm64
- osx-x64, osx-arm64
- win-x64

You can pass the following entries in ls_specific_settings["pascal"]:

Environment variables (recommended for CodeTools configuration):
- pp: Path to FPC compiler driver, must be "fpc.exe" (e.g., "D:/laz32/fpc/bin/i386-win32/fpc.exe").
  Do NOT use backend compilers like ppc386.exe or ppcx64.exe - CodeTools queries fpc.exe for
  configuration (fpc -iV, fpc -iTO, etc.). This is the most important setting for hover/navigation.
- fpcdir: Path to FPC source directory (e.g., "D:/laz32/fpcsrc"). Helps CodeTools locate
  standard library sources for better navigation.
- lazarusdir: Path to Lazarus directory (e.g., "D:/laz32/lazarus"). Required for Lazarus
  projects using LCL and other Lazarus components.

Target platform overrides (use only if pp setting is not sufficient):
- fpc_target: Override target OS (e.g., "Win32", "Win64", "Linux"). Sets FPCTARGET env var.
- fpc_target_cpu: Override target CPU (e.g., "i386", "x86_64", "aarch64"). Sets FPCTARGETCPU.

Example configuration in ~/.serena/serena_config.yml:
    ls_specific_settings:
        pascal:
            pp: "D:/laz32/fpc/bin/i386-win32/fpc.exe"
            fpcdir: "D:/laz32/fpcsrc"
            lazarusdir: "D:/laz32/lazarus"
"""

import logging
import os
import pathlib
import shutil
import threading

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, quote_windows_path
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class PascalLanguageServer(SolidLanguageServer):
    """
    Provides Pascal specific instantiation of the LanguageServer class using pasls.
    Contains various configurations and settings specific to Free Pascal and Lazarus.
    """

    PASLS_VERSION = "0.1.0"
    PASLS_RELEASES_URL = "https://github.com/zen010101/pascal-language-server/releases/download"

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a PascalLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        pasls_executable_path = self._setup_runtime_dependencies(solidlsp_settings)

        # Build environment variables for pasls
        # These control CodeTools' configuration and target platform settings
        proc_env: dict[str, str] = {}

        # Read from ls_specific_settings["pascal"]
        from solidlsp.ls_config import Language

        pascal_settings = solidlsp_settings.get_ls_specific_settings(Language.PASCAL)

        # pp: Path to FPC compiler driver (must be fpc.exe, NOT ppc386.exe/ppcx64.exe)
        # CodeTools queries fpc.exe for configuration via "fpc -iV", "fpc -iTO", etc.
        pp = pascal_settings.get("pp", "")
        if pp:
            proc_env["PP"] = pp
            log.info(f"Setting PP={pp} from ls_specific_settings")

        # fpcdir: Path to FPC source directory (e.g., "D:/laz32/fpcsrc")
        fpcdir = pascal_settings.get("fpcdir", "")
        if fpcdir:
            proc_env["FPCDIR"] = fpcdir
            log.info(f"Setting FPCDIR={fpcdir} from ls_specific_settings")

        # lazarusdir: Path to Lazarus directory (e.g., "D:/laz32/lazarus")
        lazarusdir = pascal_settings.get("lazarusdir", "")
        if lazarusdir:
            proc_env["LAZARUSDIR"] = lazarusdir
            log.info(f"Setting LAZARUSDIR={lazarusdir} from ls_specific_settings")

        # fpc_target: Override target OS (e.g., "Win32", "Win64", "Linux")
        fpc_target = pascal_settings.get("fpc_target", "")
        if fpc_target:
            proc_env["FPCTARGET"] = fpc_target
            log.info(f"Setting FPCTARGET={fpc_target} from ls_specific_settings")

        # fpc_target_cpu: Override target CPU (e.g., "i386", "x86_64", "aarch64")
        fpc_target_cpu = pascal_settings.get("fpc_target_cpu", "")
        if fpc_target_cpu:
            proc_env["FPCTARGETCPU"] = fpc_target_cpu
            log.info(f"Setting FPCTARGETCPU={fpc_target_cpu} from ls_specific_settings")

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=pasls_executable_path, cwd=repository_root_path, env=proc_env),
            "pascal",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.completions_available_event = threading.Event()

    @classmethod
    def _setup_runtime_dependencies(cls, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Pascal Language Server (pasls).

        Returns:
            str: The command to start the pasls server

        """
        # Check if pasls is already in PATH
        pasls_in_path = shutil.which("pasls")
        if pasls_in_path:
            log.info(f"Found pasls in PATH: {pasls_in_path}")
            return quote_windows_path(pasls_in_path)

        # Use RuntimeDependencyCollection for download
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Linux (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-linux-x64.tar.gz",
                    platform_id="linux-x64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Linux (arm64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-linux-arm64.tar.gz",
                    platform_id="linux-arm64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for macOS (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-darwin-x64.tar.gz",
                    platform_id="osx-x64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for macOS (arm64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-darwin-arm64.tar.gz",
                    platform_id="osx-arm64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Windows (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/v{cls.PASLS_VERSION}/pasls-win32-x64.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="pasls.exe",
                ),
            ]
        )

        pasls_dir = cls.ls_resources_dir(solidlsp_settings)
        pasls_executable_path = deps.binary_path(pasls_dir)

        if not os.path.exists(pasls_executable_path):
            log.info(f"Downloading pasls to {pasls_dir}...")
            deps.install(pasls_dir)

        assert os.path.exists(pasls_executable_path), f"pasls executable not found at {pasls_executable_path}"
        os.chmod(pasls_executable_path, 0o755)
        log.info(f"Using pasls at: {pasls_executable_path}")

        return quote_windows_path(pasls_executable_path)

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Pascal Language Server.

        pasls (genericptr/pascal-language-server) reads compiler paths from:
        1. Environment variables (PP, FPCDIR, LAZARUSDIR) via TCodeToolsOptions.InitWithEnvironmentVariables
        2. Lazarus config files via GuessCodeToolConfig

        We only pass target OS/CPU in initializationOptions if explicitly set.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        # Build initializationOptions from environment variables
        # pasls reads these to configure CodeTools:
        # - PP: Path to FPC compiler executable
        # - FPCDIR: Path to FPC source directory
        # - LAZARUSDIR: Path to Lazarus directory (only needed for LCL projects)
        # - FPCTARGET: Target OS
        # - FPCTARGETCPU: Target CPU
        initialization_options: dict = {}

        env_vars = ["PP", "FPCDIR", "LAZARUSDIR", "FPCTARGET", "FPCTARGETCPU"]
        for var in env_vars:
            value = os.environ.get(var, "")
            if value:
                initialization_options[var] = value

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "didSave": True,
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
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
                        },
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
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
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True},
                    "configuration": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                    },
                },
            },
            "initializationOptions": initialization_options,
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

        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """
        Starts the Pascal Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def register_capability_handler(params: dict) -> None:
            log.debug(f"Capability registered: {params}")
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            # Mark server as ready when we see initialization messages
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                log.info("Pascal language server ready signal detected")
                self.server_ready.set()
                self.completions_available.set()

        def publish_diagnostics(params: dict) -> None:
            log.debug(f"Diagnostics: {params}")
            return

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", publish_diagnostics)
        self.server.on_notification("$/progress", do_nothing)

        log.info("Starting Pascal server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Pascal server: {init_response}")

        # Verify capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities

        # Check for various capabilities
        if "completionProvider" in capabilities:
            log.info("Pascal server supports code completion")
        if "definitionProvider" in capabilities:
            log.info("Pascal server supports go to definition")
        if "referencesProvider" in capabilities:
            log.info("Pascal server supports find references")
        if "documentSymbolProvider" in capabilities:
            log.info("Pascal server supports document symbols")

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for Pascal language server to be ready...")
        if not self.server_ready.wait(timeout=5.0):
            # pasls may not send explicit ready signals, so we proceed after timeout
            log.info("Timeout waiting for Pascal server ready signal, assuming server is ready")
            self.server_ready.set()
            self.completions_available.set()
        else:
            log.info("Pascal server initialization complete")

    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        Check if a directory should be ignored for Pascal projects.
        Common Pascal/Lazarus directories to ignore.
        """
        ignored_dirs = {
            "lib",
            "backup",
            "__history",
            "__recovery",
            "bin",
            ".git",
            ".svn",
            ".hg",
            "node_modules",
        }
        return dirname.lower() in ignored_dirs
