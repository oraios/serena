"""
Provides Swift specific instantiation of the LanguageServer class using SourceKit-LSP.
Contains various configurations and settings specific to Swift.
"""

import asyncio
import json
import logging
import os
import pathlib
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Dict, Any

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
try:
    from multilspy.multilspy_utils import PlatformUtils, PlatformId
except ImportError:
    # Mock if not available
    class PlatformUtils:
        @staticmethod
        def get_platform_id():
            if sys.platform.startswith('darwin'):
                return 'darwin'
            elif sys.platform.startswith('linux'):
                return 'linux'
            elif sys.platform.startswith('win'):
                return 'win'
            return None


class SourceKitLSP(LanguageServer):
    """
    Provides Swift specific instantiation of the LanguageServer class using SourceKit-LSP.
    Contains various configurations and settings specific to Swift.
    """

    @staticmethod
    def _get_sourcekit_lsp_path():
        """Find the sourcekit-lsp executable path, checking multiple locations on macOS."""
        # First try the standard PATH
        sourcekit_path = shutil.which('sourcekit-lsp')
        if sourcekit_path:
            return sourcekit_path
            
        # On macOS, check common Xcode locations for sourcekit-lsp
        if sys.platform == 'darwin':
            # Common locations on macOS
            potential_paths = [
                "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/sourcekit-lsp",
                "/Applications/Xcode.app/Contents/SharedFrameworks/SourceKit.framework/Versions/A/Resources/sourcekit-lsp",
                "/Library/Developer/Toolchains/swift-latest.xctoolchain/usr/bin/sourcekit-lsp",
                os.path.expanduser("~/Library/Developer/Toolchains/swift-latest.xctoolchain/usr/bin/sourcekit-lsp"),
            ]
            
            # Check if Swift toolchain is set via env var
            if "TOOLCHAINS" in os.environ:
                toolchain_id = os.environ["TOOLCHAINS"]
                xcode_toolchain_path = f"/Applications/Xcode.app/Contents/Developer/Toolchains/{toolchain_id}.xctoolchain/usr/bin/sourcekit-lsp"
                potential_paths.append(xcode_toolchain_path)
                
                home_toolchain_path = os.path.expanduser(f"~/Library/Developer/Toolchains/{toolchain_id}.xctoolchain/usr/bin/sourcekit-lsp")
                potential_paths.append(home_toolchain_path)
                
            # Check each potential path
            for path in potential_paths:
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    return path
        
        # Not found
        return None
            
    @staticmethod
    def _get_sourcekit_lsp_version():
        """Get the installed sourcekit-lsp version or None if not found."""
        sourcekit_path = SourceKitLSP._get_sourcekit_lsp_path()
        if not sourcekit_path:
            return None
            
        try:
            result = subprocess.run([sourcekit_path, '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        except subprocess.SubprocessError:
            return None
        return None
        
    @staticmethod
    def _get_swift_version():
        """Get the installed Swift version or None if not found."""
        try:
            result = subprocess.run(['swift', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None
        
    @staticmethod
    def _get_xcode_version():
        """Get the installed Xcode version or None if not found (macOS only)."""
        if os.name == 'posix' and 'darwin' in os.uname().sysname.lower():
            try:
                result = subprocess.run(['xcodebuild', '-version'], capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip()
            except FileNotFoundError:
                pass
        return None

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        """
        Setup runtime dependencies for SourceKit-LSP.
        Returns the command to start the SourceKit-LSP server.
        """
        platform_id = PlatformUtils.get_platform_id() if 'PlatformUtils' in globals() else None
        
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            if "_description" in d:
                del d["_description"]
                
        dependencies = d.get("runtimeDependencies", [])
        
        # Find sourcekit-lsp executable
        sourcekit_path = self._get_sourcekit_lsp_path()
        
        if sourcekit_path:
            logger.log(f"Found sourcekit-lsp at: {sourcekit_path}", logging.INFO)
            
            # Try to get version
            try:
                result = subprocess.run([sourcekit_path, '--version'], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.log(f"sourcekit-lsp version: {result.stdout.strip()}", logging.INFO)
            except Exception as e:
                logger.log(f"Could not get sourcekit-lsp version: {e}", logging.WARNING)
                
            # Check if executable permissions are set (Linux only)
            if os.name != 'nt' and not sys.platform.startswith('darwin'):  # Not Windows and not macOS
                if not os.access(sourcekit_path, os.X_OK):
                    logger.log(f"sourcekit-lsp is not executable, attempting to set permissions", logging.WARNING)
                    try:
                        os.chmod(sourcekit_path, os.stat(sourcekit_path).st_mode | 0o111)  # Add executable permission
                        logger.log(f"Successfully set executable permissions on {sourcekit_path}", logging.INFO)
                    except Exception as e:
                        logger.log(f"Warning: Could not set permissions on sourcekit-lsp: {e}", logging.WARNING)
                        
            return sourcekit_path  # Return full path to executable
        
        # If we reach here, we couldn't find sourcekit-lsp
        # Check for Swift and Xcode to provide better error messages
        swift_version = self._get_swift_version()
        xcode_version = self._get_xcode_version()
        
        error_details = []
        if swift_version:
            logger.log(f"Swift is installed: {swift_version}", logging.INFO)
            error_details.append("Swift is installed but sourcekit-lsp could not be found")
        else:
            error_details.append("Swift is not installed or not in PATH")
            
        if xcode_version:
            logger.log(f"Xcode is installed: {xcode_version}", logging.INFO)
            error_details.append("Xcode is installed but sourcekit-lsp could not be found")
            
        error_msg = "Missing required dependency: sourcekit-lsp\n"
        error_msg += f"Details: {', '.join(error_details)}\n"
        error_msg += "On macOS, install Xcode Command Line Tools with: xcode-select --install\n"
        error_msg += "On Linux, install the Swift toolchain: https://swift.org/download/\n"
        error_msg += "\nSourceKit-LSP should be included with Xcode or the Swift toolchain, but it wasn't found.\n"
        error_msg += "Common locations checked:\n"
        error_msg += "- In PATH environment variable\n"
        error_msg += "- /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/\n"
        error_msg += "- Swift toolchain locations in ~/Library/Developer/Toolchains/\n"
        
        logger.log(error_msg, logging.ERROR)
        raise RuntimeError(error_msg)

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a SourceKitLSP instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        # Setup and verify runtime dependencies
        sourcekit_lsp_path = self.setup_runtime_dependencies(logger, config)
        
        logger.log(f"Initializing SourceKitLSP with executable: {sourcekit_lsp_path}", logging.INFO)
        
        super().__init__(
            config,
            logger,
            repository_root_path,
            # Use sourcekit-lsp in stdio mode with full path
            ProcessLaunchInfo(cmd=sourcekit_lsp_path, cwd=repository_root_path),
            "swift",
        )
        self.server_ready = asyncio.Event()
        self.initialize_searcher_command_available = asyncio.Event()
        self.service_ready_event = asyncio.Event()

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the SourceKit-LSP Language Server.
        """
        # Use initialized params from JSON file like other servers
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r") as f:
            d = json.load(f)

        # Remove description field if present
        if "_description" in d:
            del d["_description"]

        d["processId"] = os.getpid()
        # Replace placeholder values with actual values
        if "rootPath" in d and d["rootPath"] == "$rootPath":
            d["rootPath"] = repository_absolute_path
        else:
            d["rootPath"] = repository_absolute_path

        if "rootUri" in d and d["rootUri"] == "$rootUri":
            d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()
        else:
            d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        # Setup workspace folders
        if "workspaceFolders" not in d:
            d["workspaceFolders"] = [
                {"uri": pathlib.Path(repository_absolute_path).as_uri(), "name": os.path.basename(repository_absolute_path)}
            ]
        else:
            for i, folder in enumerate(d["workspaceFolders"]):
                if "uri" in folder and folder["uri"] == "$uri":
                    d["workspaceFolders"][i]["uri"] = pathlib.Path(repository_absolute_path).as_uri()
                if "name" in folder and folder["name"] == "$name":
                    d["workspaceFolders"][i]["name"] = os.path.basename(repository_absolute_path)

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["SourceKitLSP"]:
        """
        Starts the SourceKit-LSP Language Server, waits for the server to be ready and yields the LanguageServer instance.

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

        async def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        async def lang_status_handler(params):
            if params.get("type") == "ServiceReady" and params.get("message") == "ServiceReady":
                self.service_ready_event.set()

        async def execute_client_command_handler(params):
            return []

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        async def do_nothing(params):
            return

        async def check_experimental_status(params):
            if params.get("quiescent", False) == True:
                self.server_ready.set()
            
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        async with super().start_server():
            self.logger.log("Starting sourcekit-lsp server process", logging.INFO)
            await self.server.start()

            # Send proper initialization parameters
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to sourcekit-lsp server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            
            # Verify server capabilities
            if not init_response or "capabilities" not in init_response:
                error_msg = "sourcekit-lsp server did not return expected capabilities"
                self.logger.log(error_msg, logging.ERROR)
                raise RuntimeError(error_msg)
                
            capabilities = init_response["capabilities"]
            
            # Check text document sync mode
            text_sync = capabilities.get("textDocumentSync")
            if not text_sync:
                self.logger.log("Warning: sourcekit-lsp did not provide textDocumentSync capability", logging.WARNING)
            elif isinstance(text_sync, dict):
                self.logger.log(f"Text document sync mode: {text_sync.get('change', 'undefined')}", logging.DEBUG)
            else:
                self.logger.log(f"Text document sync mode: {text_sync}", logging.DEBUG)
                
            # Check completion provider
            if "completionProvider" not in capabilities:
                self.logger.log("Warning: sourcekit-lsp did not provide completionProvider capability", logging.WARNING)
            else:
                completion_provider = capabilities["completionProvider"]
                trigger_chars = completion_provider.get("triggerCharacters", [])
                self.logger.log(f"Completion provider: {completion_provider}", logging.DEBUG)
                self.logger.log(f"Completion trigger characters: {', '.join(trigger_chars)}", logging.INFO)
                
            # Check for other important capabilities
            important_capabilities = ["definitionProvider", "referencesProvider", "documentSymbolProvider"]
            for capability in important_capabilities:
                if capability not in capabilities:
                    self.logger.log(f"Warning: sourcekit-lsp did not provide {capability} capability", logging.WARNING)
                else:
                    self.logger.log(f"Capability {capability} supported", logging.DEBUG)
                    
            # Log all supported capabilities for reference
            all_capabilities = [key for key in capabilities.keys() if key != "experimental"]
            self.logger.log(f"All supported capabilities: {', '.join(all_capabilities)}", logging.DEBUG)
                
            self.logger.log(f"Received initialize response from sourcekit-lsp server", logging.INFO)

            # Inform server that initialization is complete
            self.server.notify.initialized({})
            
            # Set completions available
            self.completions_available.set()
            
            # For sourcekit-lsp, we assume it's ready immediately after initialization
            # but we can wait for any server status events that might come in
            self.server_ready.set()
            
            # Wait for server to be ready
            try:
                await asyncio.wait_for(self.server_ready.wait(), timeout=2.0)
                self.logger.log("SourceKit-LSP server is ready", logging.INFO)
            except asyncio.TimeoutError:
                # If we timeout, we'll just assume the server is ready
                self.logger.log("Timed out waiting for SourceKit-LSP server ready event, assuming ready", logging.WARNING)

            yield self

            await self.server.shutdown()
            await self.server.stop()
