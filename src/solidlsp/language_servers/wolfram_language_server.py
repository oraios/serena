"""Wolfram Language server integration using the official WolframResearch LSPServer paclet."""

import glob
import logging
import os
import platform
import shutil

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

WOLFRAM_PATH_ENV_VAR = "WOLFRAM_PATH"


class WolframLanguageServer(SolidLanguageServer):
    """
    Wolfram Language server using the official WolframResearch LSPServer paclet
    (https://github.com/WolframResearch/LSPServer), which is bundled with Wolfram
    installations and communicates via stdio.

    Requires Wolfram Mathematica 13.0+ or Wolfram Engine 12.1+.
    The WolframKernel executable is discovered via the ``ls_path`` entry in
    ``ls_specific_settings.wolfram``, the ``WOLFRAM_PATH`` environment variable
    (pointing to the executable or the installation directory), the system PATH,
    or common installation locations.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "wolfram", solidlsp_settings)

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Discover the WolframKernel executable.

            :return: path to the WolframKernel executable
            :raises FileNotFoundError: if WolframKernel cannot be found
            """
            return _find_wolfram_kernel()

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "-noprompt", "-noinit", "-run", 'Needs["LSPServer`"];LSPServer`StartServer[]']

    def _create_base_initialize_params(self) -> dict:
        return {
            "capabilities": {
                "workspace": {"workspaceFolders": True},
                "textDocument": {
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "formatting": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
            },
        }

    def _start_server(self) -> None:
        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"Wolfram LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Wolfram LSPServer process")
        self.server.start()

        initialize_params = self._create_initialize_params()
        init_response = self.server.send.initialize(initialize_params)

        log.info(f"Wolfram LSP capabilities: {list(init_response.get('capabilities', {}).keys())}")

        self.server.notify.initialized({})
        log.info("Wolfram LSPServer initialized and ready.")


def _find_wolfram_kernel() -> str:
    """Find the WolframKernel executable via WOLFRAM_PATH, the system PATH, or common install locations."""
    # 1. WOLFRAM_PATH environment variable (executable or installation directory)
    env_path = os.environ.get(WOLFRAM_PATH_ENV_VAR)
    if env_path:
        if os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            log.info(f"Using WolframKernel from {WOLFRAM_PATH_ENV_VAR}: {env_path}")
            return env_path
        kernel_in_dir = _find_kernel_in_install_dir(env_path)
        if kernel_in_dir:
            log.info(f"Using WolframKernel from {WOLFRAM_PATH_ENV_VAR} directory: {kernel_in_dir}")
            return kernel_in_dir

    # 2. System PATH
    kernel_path = shutil.which("WolframKernel")
    if kernel_path:
        log.info(f"Using WolframKernel from PATH: {kernel_path}")
        return kernel_path

    # 3. Common installation locations
    system = platform.system()
    search_locations: list[str] = []

    if system == "Darwin":
        search_locations = [
            "/Applications/Mathematica.app/Contents/MacOS/WolframKernel",
            "/Applications/Wolfram.app/Contents/MacOS/WolframKernel",
            "/Applications/Wolfram Engine.app/Contents/MacOS/WolframKernel",
        ]
        for pattern in [
            "/Applications/Mathematica*.app/Contents/MacOS/WolframKernel",
            "/Applications/Wolfram*.app/Contents/MacOS/WolframKernel",
        ]:
            search_locations.extend(sorted(glob.glob(pattern), reverse=True))

    elif system == "Linux":
        search_locations = [
            "/usr/local/bin/WolframKernel",
            "/usr/bin/WolframKernel",
        ]
        for pattern in [
            "/usr/local/Wolfram/Mathematica/*/Executables/WolframKernel",
            "/usr/local/Wolfram/WolframEngine/*/Executables/WolframKernel",
            "/opt/Wolfram/Mathematica/*/Executables/WolframKernel",
        ]:
            search_locations.extend(sorted(glob.glob(pattern), reverse=True))

    elif system == "Windows":
        for pattern in [
            "C:\\Program Files\\Wolfram Research\\Mathematica\\*\\WolframKernel.exe",
            "C:\\Program Files\\Wolfram Research\\Wolfram Engine\\*\\WolframKernel.exe",
        ]:
            search_locations.extend(sorted(glob.glob(pattern), reverse=True))

    for location in search_locations:
        if os.path.isfile(location) and os.access(location, os.X_OK):
            log.info(f"Found WolframKernel at: {location}")
            return location

    raise FileNotFoundError(
        "WolframKernel not found. Please either:\n"
        f"1. Set the {WOLFRAM_PATH_ENV_VAR} environment variable to your Wolfram installation\n"
        "2. Add WolframKernel to your system PATH\n"
        "3. Configure ls_path in ls_specific_settings.wolfram\n"
        "4. Install Wolfram Mathematica (13.0+) or Wolfram Engine (12.1+) from https://www.wolfram.com/"
    )


def _find_kernel_in_install_dir(install_dir: str) -> str | None:
    """Try to locate WolframKernel within a Wolfram installation directory."""
    system = platform.system()

    if system == "Darwin":
        candidates = [
            os.path.join(install_dir, "Contents", "MacOS", "WolframKernel"),
            os.path.join(install_dir, "MacOS", "WolframKernel"),
        ]
    elif system == "Windows":
        candidates = [
            os.path.join(install_dir, "WolframKernel.exe"),
        ]
    else:
        candidates = [
            os.path.join(install_dir, "Executables", "WolframKernel"),
            os.path.join(install_dir, "WolframKernel"),
        ]

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None
