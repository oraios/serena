"""
Provides Apex specific instantiation of the LanguageServer class.
Contains various configurations and settings specific to Salesforce Apex.

Note: This is a minimal implementation as no LSP exists for Apex.
Only basic file operations (read_file) are supported.
"""

import logging

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class ApexLanguageServer(SolidLanguageServer):
    """
    Provides Apex specific instantiation of the LanguageServer class.

    This is a minimal implementation as no Language Server Protocol (LSP) implementation
    exists for Apex. This class allows Apex files to be recognized and basic file
    operations (like read_file) to work, but advanced LSP features like symbol
    navigation, references, and completions are not available.

    Supported file extensions: .cls, .trigger, .apex
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an ApexLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.

        Note: This implementation uses a dummy command since no actual LSP exists for Apex.
        """
        # Use a simple echo command as a placeholder since no actual LSP exists
        # This allows the language server infrastructure to work without actually starting a process
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd="echo 'Apex LSP not available'", cwd=repository_root_path),
            "apex",
            solidlsp_settings,
        )

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        Apex-specific directories to ignore.
        """
        return super().is_ignored_dirname(dirname) or dirname in [
            ".sfdx",
            ".sf",
            "force-app",  # Don't ignore force-app itself, but this is here as an example
        ]

    def _start_server(self) -> None:
        """
        Minimal start_server implementation for Apex.

        Since no actual LSP exists for Apex, this method does nothing.
        The language server will not actually start, but file operations
        will still work through the Project.read_file() method.
        """
        log.info("Apex language server: No LSP available for Apex. Only basic file operations are supported.")
        # Don't actually start any server process
        # The server_started flag will remain False, which is intentional

    @override
    def start(self) -> "ApexLanguageServer":
        """
        Override start to skip the actual server startup since no LSP exists.

        :return: self for method chaining
        """
        log.info(f"Starting Apex language support (no LSP) for {self.repository_root_path}")
        # Don't call _start_server_process() since we don't have an actual server
        # Just mark as started so the infrastructure doesn't complain
        self.server_started = True
        return self
