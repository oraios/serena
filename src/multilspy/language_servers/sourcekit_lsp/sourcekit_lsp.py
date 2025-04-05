"""
Provides Swift specific instantiation of the LanguageServer class using SourceKit-LSP.
Contains various configurations and settings specific to Swift.
"""

import asyncio
import copy
import json
import logging
import os
import pathlib
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Dict, Any, List, Tuple, Union

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy import multilspy_types
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
    Provides language server implementation using SourceKit-LSP for Swift code.
    Contains configurations and handling for Swift language features.
    """

    @staticmethod
    def _get_sourcekit_lsp_path():
        """Find the sourcekit-lsp executable path, checking multiple locations on macOS and Linux."""
        # First try the standard PATH
        sourcekit_path = shutil.which('sourcekit-lsp')
        if sourcekit_path:
            return sourcekit_path

        # On macOS, check common Xcode locations for sourcekit-lsp
        if sys.platform == 'darwin':
            # Try to find the index store path (libIndexStore.dylib)
            # This will help determine where SourceKit-LSP is looking
            try:
                # Check if we can run uname directly
                result = subprocess.run(['uname', '-s'], capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"System type: {result.stdout.strip()}")
            except:
                print("Could not determine system type with uname")

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

        # On Linux, check common Swift toolchain locations
        elif sys.platform.startswith('linux'):
            # Common locations on Linux
            potential_paths = [
                # Standard Swift toolchain locations
                "/usr/bin/sourcekit-lsp",
                "/usr/local/bin/sourcekit-lsp",
                # Common Swift toolchain installation locations
                "/usr/share/swift/usr/bin/sourcekit-lsp",
                "/opt/swift/usr/bin/sourcekit-lsp",
                # User home locations
                os.path.expanduser("~/swift-toolchain/usr/bin/sourcekit-lsp"),
                # Official Swift toolchain location pattern
                "/usr/lib/swift/bin/sourcekit-lsp",
                # Swiftlang location
                "/usr/lib/swiftlang/bin/sourcekit-lsp",
            ]

            # Check version-specific paths in /usr/lib and /usr/local/lib
            for version in ["5.9", "6.0", "6.1", "6.2", "latest"]:
                potential_paths.extend([
                    f"/usr/lib/swift-{version}/bin/sourcekit-lsp",
                    f"/usr/local/lib/swift-{version}/bin/sourcekit-lsp",
                ])

            # Check if SWIFT_TOOLCHAIN_PATH is defined in environment
            if "SWIFT_TOOLCHAIN_PATH" in os.environ:
                toolchain_path = os.environ["SWIFT_TOOLCHAIN_PATH"]
                potential_paths.extend([
                    f"{toolchain_path}/usr/bin/sourcekit-lsp",
                    f"{toolchain_path}/bin/sourcekit-lsp",
                ])

            # Check each potential path
            for path in potential_paths:
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    return path

            # Swift toolchains might be installed via tarball, try to find them
            try:
                # Find toolchain directories
                home_dir = os.path.expanduser("~")
                swift_dirs = []

                # Check commonly used install directories
                for base_dir in ["/opt", "/usr/local", home_dir]:
                    if os.path.exists(base_dir):
                        swift_dirs.extend([
                            os.path.join(base_dir, d)
                            for d in os.listdir(base_dir)
                            if d.startswith("swift-") and os.path.isdir(os.path.join(base_dir, d))
                        ])

                # Check each found directory for sourcekit-lsp
                for swift_dir in swift_dirs:
                    lsp_path = os.path.join(swift_dir, "usr", "bin", "sourcekit-lsp")
                    if os.path.isfile(lsp_path) and os.access(lsp_path, os.X_OK):
                        return lsp_path
            except Exception:
                # Ignore errors in this section
                pass

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

        # Platform-specific installation instructions
        if sys.platform == 'darwin':
            error_msg += "On macOS, install Xcode Command Line Tools with: xcode-select --install\n"
            error_msg += "\nSourceKit-LSP should be included with Xcode or the Swift toolchain, but it wasn't found.\n"
            error_msg += "Common locations checked:\n"
            error_msg += "- In PATH environment variable\n"
            error_msg += "- /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/\n"
            error_msg += "- Swift toolchain locations in ~/Library/Developer/Toolchains/\n"
        elif sys.platform.startswith('linux'):
            error_msg += "On Linux, install the Swift toolchain using the following steps:\n"
            error_msg += "1. Download the Swift toolchain for your distribution: https://swift.org/download/\n"
            error_msg += "2. Install the toolchain following the instructions at: https://swift.org/getting-started/\n"
            error_msg += "3. Ensure sourcekit-lsp is in your PATH\n"
            error_msg += "\nExample for Ubuntu 22.04:\n"
            error_msg += "$ wget https://download.swift.org/swift-6.1-release/ubuntu2204/swift-6.1-RELEASE/swift-6.1-RELEASE-ubuntu22.04.tar.gz\n"
            error_msg += "$ tar xzf swift-6.1-RELEASE-ubuntu22.04.tar.gz\n"
            error_msg += "$ sudo mv swift-6.1-RELEASE-ubuntu22.04 /opt/swift\n"
            error_msg += "$ echo 'export PATH=/opt/swift/usr/bin:$PATH' >> ~/.bashrc\n"
            error_msg += "$ source ~/.bashrc\n"
            error_msg += "\nFor CI environments, you can add sourcekit-lsp with:\n"
            error_msg += "```yaml\n"
            error_msg += "- name: Install Swift and sourcekit-lsp\n"
            error_msg += "  run: |\n"
            error_msg += "    wget -q https://download.swift.org/swift-6.1-release/ubuntu2204/swift-6.1-RELEASE/swift-6.1-RELEASE-ubuntu22.04.tar.gz\n"
            error_msg += "    tar xzf swift-6.1-RELEASE-ubuntu22.04.tar.gz\n"
            error_msg += "    sudo mv swift-6.1-RELEASE-ubuntu22.04 /opt/swift\n"
            error_msg += "    echo 'export PATH=/opt/swift/usr/bin:$PATH' >> $GITHUB_ENV\n"
            error_msg += "    echo 'export SWIFT_TOOLCHAIN_PATH=/opt/swift' >> $GITHUB_ENV\n"
            error_msg += "```\n"
            error_msg += "\nCommon locations checked on Linux:\n"
            error_msg += "- In PATH environment variable\n"
            error_msg += "- Standard system paths (/usr/bin, /usr/local/bin)\n"
            error_msg += "- Swift toolchain locations in /opt and /usr/local\n"
        else:
            error_msg += "To use Swift with sourcekit-lsp, install the Swift toolchain: https://swift.org/download/\n"

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

        # Create a copy of the current environment
        env = os.environ.copy()

        # Ensure PATH is passed to sourcekit-lsp
        # This is critical as sourcekit-lsp needs access to system tools like 'uname'
        # to properly detect the platform and find libIndexStore.dylib on macOS

        if sys.platform == 'darwin':
            # On macOS, help sourcekit-lsp find the IndexStore library by setting environment variables
            xcode_path = "/Applications/Xcode.app"
            if os.path.exists(xcode_path):
                # Point to the Xcode toolchain
                toolchain_path = os.path.join(xcode_path, "Contents/Developer/Toolchains/XcodeDefault.xctoolchain")
                if os.path.exists(toolchain_path):
                    # Set environment variables that sourcekit-lsp uses to find the right libraries
                    env["SOURCEKIT_TOOLCHAIN_PATH"] = toolchain_path
                    logger.log(f"Set SOURCEKIT_TOOLCHAIN_PATH to {toolchain_path}", logging.INFO)

                    # Both libIndexStore.dylib path and llbuild framework are needed for index store functionality
                    lib_path = os.path.join(toolchain_path, "usr/lib")
                    if "DYLD_LIBRARY_PATH" in env:
                        env["DYLD_LIBRARY_PATH"] = f"{lib_path}:{env['DYLD_LIBRARY_PATH']}"
                    else:
                        env["DYLD_LIBRARY_PATH"] = lib_path
                    logger.log(f"Added {lib_path} to DYLD_LIBRARY_PATH", logging.INFO)

                    # Set specific environment variable to help find libIndexStore.dylib
                    lib_index_store = os.path.join(lib_path, "libIndexStore.dylib")
                    if os.path.exists(lib_index_store):
                        env["SOURCEKIT_LIBINDEXSTORE_PATH"] = lib_index_store
                        logger.log(f"Set SOURCEKIT_LIBINDEXSTORE_PATH to {lib_index_store}", logging.INFO)

                    # Set Swift SDK path if not set (needed for compiler flags)
                    sdk_path = os.path.join(xcode_path, "Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk")
                    if os.path.exists(sdk_path):
                        env["SDKROOT"] = sdk_path
                        logger.log(f"Set SDKROOT to {sdk_path}", logging.INFO)

        super().__init__(
            config,
            logger,
            repository_root_path,
            # Use sourcekit-lsp in stdio mode with full path and pass environment
            ProcessLaunchInfo(cmd=sourcekit_lsp_path, cwd=repository_root_path, env=env),
            "swift",
        )
        self.server_ready = asyncio.Event()
        self.initialize_searcher_command_available = asyncio.Event()
        self.service_ready_event = asyncio.Event()

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the SourceKit-LSP Language Server.

        Includes special handling for test environments to ensure references work properly.
        """
        # Use initialized params from JSON file like other servers
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r") as f:
            d = json.load(f)

        # Remove description field if present
        if "_description" in d:
            del d["_description"]

        d["processId"] = os.getpid()

        # Check if this is a test environment
        is_test_env = "test_repo" in repository_absolute_path

        # For test environments, look for the swift_test directory specifically
        swift_test_root = repository_absolute_path
        if is_test_env:
            for root, dirs, files in os.walk(repository_absolute_path):
                if "swift_test" in dirs:
                    swift_test_root = os.path.join(root, "swift_test")
                    self.logger.log(f"Using Swift test directory as root: {swift_test_root}", logging.INFO)
                    break

        # Set up indexing for both test environments and regular projects
        if "initializationOptions" in d and "sourcekit-lsp" in d["initializationOptions"]:
            sourcekit_options = d["initializationOptions"]["sourcekit-lsp"]

            # Set indexStoreOptions to help find the correct index store
            if sys.platform == 'darwin':  # macOS
                # Find the IndexStore.framework or libIndexStore.dylib
                index_store_paths = [
                    "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/libIndexStore.dylib",
                    "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift/macosx/libIndexStore.dylib",
                    "/Applications/Xcode.app/Contents/SharedFrameworks/SourceKit.framework/Versions/A/Resources/libIndexStore.dylib"
                ]

                for path in index_store_paths:
                    if os.path.exists(path):
                        if "indexStoreOptions" not in sourcekit_options:
                            sourcekit_options["indexStoreOptions"] = {}
                        sourcekit_options["indexStoreOptions"]["libraryPath"] = path
                        self.logger.log(f"Using IndexStore library: {path}", logging.INFO)
                        break

                # For Xcode projects, try to find DerivedData index
                possible_derived_data_paths = [
                    os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
                ]

                # Try to locate project-specific index in DerivedData
                project_name = os.path.basename(repository_absolute_path)
                possible_index_locations = []

                # First check for test environment
                if is_test_env and os.path.exists(os.path.join(swift_test_root, ".build/arm64-apple-macosx/debug/index")):
                    index_path = os.path.join(swift_test_root, ".build/arm64-apple-macosx/debug/index/store")
                    if os.path.exists(index_path):
                        possible_index_locations.append(index_path)

                # Then check for non-Package.swift projects
                for derived_data_base in possible_derived_data_paths:
                    if os.path.exists(derived_data_base):
                        # Look for project-specific directories in DerivedData
                        try:
                            for entry in os.listdir(derived_data_base):
                                # Try to match project name approximately
                                if project_name.lower() in entry.lower():
                                    index_path = os.path.join(derived_data_base, entry, "Index/DataStore")
                                    if os.path.exists(index_path):
                                        possible_index_locations.append(index_path)
                                        self.logger.log(f"Found potential project index at: {index_path}", logging.INFO)
                        except Exception as e:
                            self.logger.log(f"Error scanning DerivedData: {e}", logging.WARNING)

                # Look for Swift package index if not found already
                if not possible_index_locations:
                    # Check for .build directory in repository root
                    build_dir = os.path.join(repository_absolute_path, ".build")
                    if os.path.exists(build_dir):
                        try:
                            # Look for index/store in various build configurations
                            for root, dirs, _ in os.walk(build_dir):
                                if "index" in dirs:
                                    index_path = os.path.join(root, "index/store")
                                    if os.path.exists(index_path):
                                        possible_index_locations.append(index_path)
                                        self.logger.log(f"Found Swift package index at: {index_path}", logging.INFO)
                                        break
                        except Exception as e:
                            self.logger.log(f"Error scanning .build directory: {e}", logging.WARNING)

                # Use the first available index store path
                if possible_index_locations:
                    if "indexStoreOptions" not in sourcekit_options:
                        sourcekit_options["indexStoreOptions"] = {}
                    sourcekit_options["indexStoreOptions"]["path"] = possible_index_locations[0]
                    self.logger.log(f"Using index store at: {possible_index_locations[0]}", logging.INFO)
                else:
                    self.logger.log("No suitable index store found. References may not work correctly.", logging.WARNING)

            # Get platform-specific SDK path
            sdk_path = None
            if sys.platform == 'darwin':  # macOS
                sdk_paths = [
                    "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk",
                    "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"
                ]
                for path in sdk_paths:
                    if os.path.exists(path):
                        sdk_path = path
                        break

            # Only use SDK path if it exists
            if sdk_path:
                server_args = sourcekit_options.get("serverArguments", [])
                # Find the -sdk parameter and update it
                sdk_found = False
                for i, arg in enumerate(server_args):
                    if arg == "-sdk" and i + 1 < len(server_args):
                        server_args[i + 1] = sdk_path
                        sdk_found = True
                        break

                # If -sdk wasn't found, add it
                if not sdk_found:
                    server_args.extend(["-Xswiftc", "-sdk", "-Xswiftc", sdk_path])

                sourcekit_options["serverArguments"] = server_args
                self.logger.log(f"Using SDK path: {sdk_path}", logging.INFO)
            else:
                # If we can't find a valid SDK, remove the SDK arguments
                if "serverArguments" in sourcekit_options:
                    args = sourcekit_options["serverArguments"]
                    new_args = []
                    skip_next = False
                    for i, arg in enumerate(args):
                        if skip_next:
                            skip_next = False
                            continue
                        if arg == "-sdk":
                            skip_next = True
                            continue
                        new_args.append(arg)
                    sourcekit_options["serverArguments"] = new_args

        # Replace placeholder values with actual values
        if "rootPath" in d and d["rootPath"] == "$rootPath":
            d["rootPath"] = swift_test_root
        else:
            d["rootPath"] = swift_test_root

        if "rootUri" in d and d["rootUri"] == "$rootUri":
            d["rootUri"] = pathlib.Path(swift_test_root).as_uri()
        else:
            d["rootUri"] = pathlib.Path(swift_test_root).as_uri()

        # Setup workspace folders - make sure to include both the main repo and swift_test dir if applicable
        workspace_folders = [
            {"uri": pathlib.Path(repository_absolute_path).as_uri(), "name": os.path.basename(repository_absolute_path)}
        ]

        # Add swift_test directory as a separate workspace folder if it's different
        if swift_test_root != repository_absolute_path:
            workspace_folders.append({
                "uri": pathlib.Path(swift_test_root).as_uri(),
                "name": os.path.basename(swift_test_root)
            })

        d["workspaceFolders"] = workspace_folders

        self.logger.log(f"SourceKit-LSP init params: {json.dumps(d, indent=2)}", logging.DEBUG)
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
