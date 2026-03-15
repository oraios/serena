"""
COBOL Language Server implementation for Serena.

This module provides integration with a COBOL language server
supporting .cob, .cbl, and .cobol file extensions.
"""

import logging
import os
import shutil
from typing import Any

from solidlsp.language_servers.common import (
    RuntimeDependency,
    RuntimeDependencyCollection,
)
from solidlsp.ls import LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_process import ProcessLaunchInfo
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams

log = logging.getLogger(__name__)


class CobolLanguageServer(SolidLanguageServer):
    """
    COBOL Language Server implementation.
    
    Supports COBOL file extensions: .cob, .cbl, .cobol, .CBL, .COB
    
    Configuration:
    --------------
    You can specify a custom path to the COBOL language server executable
    using the 'ls_path' setting in your Serena configuration:
    
    ```yaml
    language_servers:
      cobol:
        ls_path: '/path/to/cobol-language-server'
    ```
    
    Supported Language Servers:
    ---------------------------
    - IBM Z Open Editor language server
    - Eclipse Che4z COBOL Language Support
    - Other LSP-compliant COBOL language servers
    """

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        """Handles COBOL language server dependencies and launch command."""

        def _get_or_install_core_dependency(self) -> str:
            """
            Get or install the COBOL language server.
            
            Returns:
                Path to the COBOL language server executable
            """
            # First, check if user provided a custom path via ls_path setting
            custom_path = self._custom_settings.get("ls_path")
            if custom_path and os.path.exists(custom_path):
                log.info(f"Using custom COBOL language server at: {custom_path}")
                return custom_path
            
            # Check for system-installed COBOL language server
            # Common names for COBOL language servers
            possible_commands = [
                "cobol-language-server",
                "cobol-lsp",
                "che4z-lsp-for-cobol",
            ]
            
            for cmd in possible_commands:
                system_path = shutil.which(cmd)
                if system_path:
                    log.info(f"Found system-installed COBOL language server: {system_path}")
                    return system_path
            
            # If no system installation found, check for IBM Z Open Editor
            vscode_extensions = os.path.expanduser("~/.vscode/extensions")
            if os.path.exists(vscode_extensions):
                # Look for IBM Z Open Editor extension
                for ext_dir in os.listdir(vscode_extensions):
                    if "ibm.zopeneditor" in ext_dir.lower():
                        ext_path = os.path.join(vscode_extensions, ext_dir)
                        # Look for language server JAR or executable
                        # This is a placeholder - actual path depends on extension structure
                        possible_paths = [
                            os.path.join(ext_path, "server", "cobol-language-server.jar"),
                            os.path.join(ext_path, "bin", "cobol-language-server"),
                        ]
                        for path in possible_paths:
                            if os.path.exists(path):
                                log.info(f"Found COBOL language server in Z Open Editor: {path}")
                                return path
            
            # If still not found, provide helpful error message
            raise FileNotFoundError(
                "COBOL language server not found. Please install one of the following:\n\n"
                "1. IBM Z Open Editor (VSCode extension):\n"
                "   Install from VSCode Marketplace: 'IBM Z Open Editor'\n\n"
                "2. Eclipse Che4z COBOL Language Support:\n"
                "   Install from VSCode Marketplace: 'COBOL Language Support'\n\n"
                "3. Or specify a custom path in your Serena configuration:\n"
                "   language_servers:\n"
                "     cobol:\n"
                "       ls_path: '/path/to/your/cobol-language-server'\n"
            )

        def _create_launch_command(self, core_path: str) -> list[str] | str:
            """
            Create the launch command for the COBOL language server.
            
            Args:
                core_path: Path to the COBOL language server executable or JAR
            
            Returns:
                Command to launch the language server
            """
            # Handle Java-based language servers (like IBM Z Open Editor)
            if core_path.endswith(".jar"):
                java_path = shutil.which("java")
                if not java_path:
                    raise RuntimeError(
                        "Java is required to run the COBOL language server but was not found in PATH"
                    )
                return [java_path, "-jar", core_path, "--stdio"]
            
            # Handle executable-based language servers
            return [core_path, "--stdio"]

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize the COBOL language server."""
        super().__init__(
            *args,
            language_id="cobol",
            process_launch_info=None,  # Will be created via _create_dependency_provider
            **kwargs,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProviderSinglePath:
        """Create the dependency provider for the COBOL language server."""
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _get_initialize_params(self) -> InitializeParams:
        """
        Get initialization parameters for the COBOL language server.
        
        Returns:
            LSP initialization parameters
        """
        return {
            "processId": os.getpid(),
            "rootUri": self._path_to_uri(self.repository_root_path),
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "didSave": True,
                        "dynamicRegistration": False,
                    },
                    "completion": {"completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "documentSymbol": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                },
                "workspace": {
                    "symbol": {"dynamicRegistration": False},
                    "workspaceFolders": True,
                },
            },
            "workspaceFolders": [
                {
                    "uri": self._path_to_uri(self.repository_root_path),
                    "name": os.path.basename(self.repository_root_path),
                }
            ],
        }

    def _start_server(self) -> None:
        """
        Start the COBOL language server and wait for it to be ready.
        """
        log.info("Starting COBOL language server process")
        self.server.start()
        
        log.info("Sending initialize request to COBOL language server")
        initialize_params = self._get_initialize_params()
        init_response = self.server.send.initialize(initialize_params)
        
        log.info("Received initialize response from COBOL language server")
        log.debug(f"Server capabilities: {init_response.get('capabilities', {})}")
        
        # Send initialized notification
        self.server.notify.initialized({})
        
        log.info("COBOL language server initialized successfully")
        
        # Verify essential capabilities
        capabilities = init_response.get("capabilities", {})
        if "textDocumentSync" not in capabilities:
            log.warning("COBOL language server does not advertise textDocumentSync")
        if "documentSymbolProvider" not in capabilities:
            log.warning("COBOL language server does not advertise documentSymbolProvider")