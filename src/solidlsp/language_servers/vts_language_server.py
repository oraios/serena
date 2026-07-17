"""
Language Server implementation for TypeScript/JavaScript using https://github.com/yioneko/vtsls,
which provides TypeScript language server functionality via VSCode's TypeScript extension
(contrary to typescript-language-server, which uses the TypeScript compiler directly).
"""

import logging
import os
import shutil
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_VTSLS_VERSION = "0.2.9"
DEFAULT_VTSLS_VERSION = "0.2.9"


class VtsLanguageServer(SolidLanguageServer):
    """
    Provides TypeScript specific instantiation of the LanguageServer class using vtsls.

    Supported entries in ``ls_specific_settings["typescript_vts"]``:
        - ``vtsls_version``: version of ``@vtsls/language-server`` to install (default: ``"0.2.9"``).
        - ``npm_registry``: custom npm registry for the managed install.
        - ``initialization_options``: optional dict forwarded verbatim as LSP
          ``initializationOptions``. Useful for Yarn PnP projects, e.g.::

              initialization_options:
                typescript:
                  tsdk: "project/.yarn/sdks/typescript/lib"
                vtsls:
                  autoUseWorkspaceTsdk: true

          See https://github.com/yioneko/vtsls/issues/169 for the PnP recipe.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a VtsLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        vts_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=vts_lsp_executable_path, cwd=repository_root_path),
            "typescript",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
        ]

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for VTS Language Server and return the command to start the server.
        """
        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
            PlatformId.WIN_x64,
            PlatformId.WIN_arm64,
        ]
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for vtsls at the moment"
        vts_config = solidlsp_settings.get_ls_specific_settings(Language.TYPESCRIPT_VTS)
        vtsls_version = vts_config.get("vtsls_version", DEFAULT_VTSLS_VERSION)
        npm_registry = vts_config.get("npm_registry")

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="vtsls",
                    description="vtsls language server package",
                    command=build_npm_install_command("@vtsls/language-server", vtsls_version, npm_registry),
                    platform_id="any",
                ),
            ]
        )
        # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
        ls_dirname = "vts-lsp" if vtsls_version == INITIAL_VTSLS_VERSION else f"vts-lsp-{vtsls_version}"
        vts_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), ls_dirname)
        vts_executable_path = os.path.join(vts_ls_dir, "vtsls")

        # Verify both node and npm are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        # Install vtsls if not already installed
        if not os.path.exists(vts_ls_dir):
            os.makedirs(vts_ls_dir, exist_ok=True)
            deps.install(vts_ls_dir)

        vts_executable_path = os.path.join(vts_ls_dir, "node_modules", ".bin", "vtsls")

        assert os.path.exists(vts_executable_path), "vtsls executable not found. Please install @vtsls/language-server and try again."
        return f"{vts_executable_path} --stdio"

    @property
    def _initialization_options(self) -> dict:
        """
        Validated user-provided ``initializationOptions``.

        :raises ValueError: if ``ls_specific_settings.typescript_vts.initialization_options``
            is set to a value that is not a dict.
        """
        opts = self._custom_settings.get("initialization_options")
        if opts is None:
            return {}
        if not isinstance(opts, dict):
            raise ValueError(f"ls_specific_settings.typescript_vts.initialization_options must be a dict, got {type(opts).__name__}")
        return opts

    def _create_base_initialize_params(self) -> dict:
        """
        Returns the initialize params for the VTS Language Server.

        If ``initialization_options`` is set in ``ls_specific_settings["typescript_vts"]``,
        it is forwarded verbatim as LSP ``initializationOptions``.
        """
        initialize_params: dict = {
            "locale": "en",
            "initializationOptions": {
                "preferences": {
                    "disableAutomaticTypingAcquisition": True,
                },
            },
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
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "configuration": True,  # This might be needed for vtsls
                },
            },
        }

        if self._initialization_options:
            log.info("Forwarding user-provided initializationOptions to vtsls: %s", self._initialization_options)
            initialize_params["initializationOptions"] = self._initialization_options

        return initialize_params

    def _start_server(self) -> None:
        """
        Starts the VTS Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        ```
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params: dict) -> list:
            return []

        init_options = self._initialization_options

        def workspace_configuration_handler(params: dict) -> list[object]:
            # vtsls pulls settings for sections like "typescript", "vtsls", "javascript".
            # Return the matching sub-dicts from the user-provided initialization_options.
            return [init_options.get(item.get("section", ""), {}) for item in params["items"]]

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def check_experimental_status(params: dict) -> None:
            """
            Also listen for experimental/serverStatus as a backup signal
            """
            if params.get("quiescent") is True:
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting VTS server process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # VTS-specific capability checks
        # Be more flexible with capabilities since vtsls might have different structure
        log.debug(f"VTS init response capabilities: {init_response['capabilities']}")

        # Basic checks to ensure essential capabilities are present
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]

        # Log the actual values for debugging
        log.debug(f"textDocumentSync: {init_response['capabilities']['textDocumentSync']}")
        log.debug(f"completionProvider: {init_response['capabilities']['completionProvider']}")

        self.server.notify.initialized({})

        # vtsls also reads settings via workspace/didChangeConfiguration (in addition
        # to initializationOptions and workspace/configuration pulls). Push the same
        # user-provided settings on all three channels for maximum compatibility,
        # e.g. so that `typescript.tsdk` is honoured for Yarn PnP projects.
        if init_options:
            self.server.notify.workspace_did_change_configuration({"settings": init_options})

        if self.server_ready.wait(timeout=1.0):
            log.info("VTS server is ready")
        else:
            log.info("Timeout waiting for VTS server to become ready, proceeding anyway")
            # Fallback: assume server is ready after timeout
            self.server_ready.set()

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 1
