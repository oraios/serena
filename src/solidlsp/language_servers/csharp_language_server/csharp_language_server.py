"""
CSharp Language Server using Microsoft.CodeAnalysis.LanguageServer (Official Roslyn-based LSP server)
"""

import json
import logging
import os
import platform
import shutil
import stat
import tarfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import LanguageServerException
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


@dataclass
class RuntimeDependency:
    """Represents a runtime dependency for the C# language server."""

    id: str
    description: str
    platform_id: str
    archive_type: str
    binary_name: str
    package_name: str | None = None
    package_version: str | None = None
    extract_path: str | None = None
    url: str | None = None


# Runtime dependencies configuration
RUNTIME_DEPENDENCIES = [
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Microsoft.CodeAnalysis.LanguageServer for Windows (x64)",
        package_name="Microsoft.CodeAnalysis.LanguageServer.win-x64",
        package_version="5.0.0-1.25329.6",
        platform_id="win-x64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="content/LanguageServer/win-x64",
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Microsoft.CodeAnalysis.LanguageServer for Windows (ARM64)",
        package_name="Microsoft.CodeAnalysis.LanguageServer.win-arm64",
        package_version="5.0.0-1.25329.6",
        platform_id="win-arm64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="content/LanguageServer/win-arm64",
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Microsoft.CodeAnalysis.LanguageServer for macOS (x64)",
        package_name="Microsoft.CodeAnalysis.LanguageServer.osx-x64",
        package_version="5.0.0-1.25329.6",
        platform_id="osx-x64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="content/LanguageServer/osx-x64",
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Microsoft.CodeAnalysis.LanguageServer for macOS (ARM64)",
        package_name="Microsoft.CodeAnalysis.LanguageServer.osx-arm64",
        package_version="5.0.0-1.25329.6",
        platform_id="osx-arm64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="content/LanguageServer/osx-arm64",
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Microsoft.CodeAnalysis.LanguageServer for Linux (x64)",
        package_name="Microsoft.CodeAnalysis.LanguageServer.linux-x64",
        package_version="5.0.0-1.25329.6",
        platform_id="linux-x64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="content/LanguageServer/linux-x64",
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Microsoft.CodeAnalysis.LanguageServer for Linux (ARM64)",
        package_name="Microsoft.CodeAnalysis.LanguageServer.linux-arm64",
        package_version="5.0.0-1.25329.6",
        platform_id="linux-arm64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="content/LanguageServer/linux-arm64",
    ),
    RuntimeDependency(
        id="DotNetRuntime",
        description=".NET 9 Runtime for Windows (x64)",
        url="https://builds.dotnet.microsoft.com/dotnet/Runtime/9.0.6/dotnet-runtime-9.0.6-win-x64.zip",
        platform_id="win-x64",
        archive_type="zip",
        binary_name="dotnet.exe",
    ),
    RuntimeDependency(
        id="DotNetRuntime",
        description=".NET 9 Runtime for Linux (x64)",
        url="https://builds.dotnet.microsoft.com/dotnet/Runtime/9.0.6/dotnet-runtime-9.0.6-linux-x64.tar.gz",
        platform_id="linux-x64",
        archive_type="tar.gz",
        binary_name="dotnet",
    ),
    RuntimeDependency(
        id="DotNetRuntime",
        description=".NET 9 Runtime for macOS (x64)",
        url="https://builds.dotnet.microsoft.com/dotnet/Runtime/9.0.6/dotnet-runtime-9.0.6-osx-x64.tar.gz",
        platform_id="osx-x64",
        archive_type="tar.gz",
        binary_name="dotnet",
    ),
    RuntimeDependency(
        id="DotNetRuntime",
        description=".NET 9 Runtime for macOS (ARM64)",
        url="https://builds.dotnet.microsoft.com/dotnet/Runtime/9.0.6/dotnet-runtime-9.0.6-osx-arm64.tar.gz",
        platform_id="osx-arm64",
        archive_type="tar.gz",
        binary_name="dotnet",
    ),
]


def breadth_first_file_scan(root_dir):
    """
    Perform a breadth-first scan of files in the given directory.
    Yields file paths in breadth-first order.
    """
    queue = [root_dir]
    while queue:
        current_dir = queue.pop(0)
        try:
            for item in os.listdir(current_dir):
                if item.startswith("."):
                    continue
                item_path = os.path.join(current_dir, item)
                if os.path.isdir(item_path):
                    queue.append(item_path)
                elif os.path.isfile(item_path):
                    yield item_path
        except (PermissionError, OSError):
            # Skip directories we can't access
            pass


def find_solution_or_project_file(root_dir) -> str | None:
    """
    Find the first .sln file in breadth-first order.
    If no .sln file is found, look for a .csproj file.
    """
    sln_file = None
    csproj_file = None

    for filename in breadth_first_file_scan(root_dir):
        if filename.endswith(".sln") and sln_file is None:
            sln_file = filename
        elif filename.endswith(".csproj") and csproj_file is None:
            csproj_file = filename

        # If we found a .sln file, return it immediately
        if sln_file:
            return sln_file

    # If no .sln file was found, return the first .csproj file
    return csproj_file


class CSharpLanguageServer(SolidLanguageServer):
    """
    Provides C# specific instantiation of the LanguageServer class using Microsoft.CodeAnalysis.LanguageServer.
    This is the official Roslyn-based language server from Microsoft.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """
        Creates a CSharpLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        dotnet_path, language_server_path, cache_dir = self._ensure_server_installed(logger, config)

        # Find solution or project file
        solution_or_project = find_solution_or_project_file(repository_root_path)

        # Create log directory
        log_dir = cache_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Build command using dotnet directly
        cmd = [dotnet_path, language_server_path, "--logLevel=Information", f"--extensionLogDirectory={log_dir}", "--stdio"]

        # The language server will discover the solution/project from the workspace root
        if solution_or_project:
            logger.log(f"Found solution/project file: {solution_or_project}", logging.INFO)
        else:
            logger.log("No .sln or .csproj file found, language server will attempt auto-discovery", logging.WARNING)

        logger.log(f"Language server command: {' '.join(cmd)}", logging.DEBUG)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "csharp",
        )

        self.initialization_complete = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["bin", "obj", "packages", ".vs"]

    def _ensure_server_installed(self, logger: LanguageServerLogger, config: LanguageServerConfig) -> tuple[str, str, Path]:
        """
        Ensure .NET runtime and Microsoft.CodeAnalysis.LanguageServer are available.
        Returns a tuple of (dotnet_path, language_server_dll_path, cache_dir).
        """
        # Determine platform runtime ID
        runtime_id = self._get_runtime_id()

        # Set up cache directory
        cache_dir = Path.home() / ".cache" / "serena" / "language-servers" / "csharp"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Get runtime dependencies for this platform
        lang_server_dep, dotnet_runtime_dep = self._get_runtime_dependencies(runtime_id)

        # Ensure .NET runtime is available
        dotnet_path = self._ensure_dotnet_runtime(logger, cache_dir, dotnet_runtime_dep)

        # Ensure language server is available
        server_dll_path = self._ensure_language_server(logger, cache_dir, lang_server_dep)

        return dotnet_path, server_dll_path, cache_dir

    def _get_runtime_id(self) -> str:
        """Determine the runtime ID based on the platform."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "windows":
            return "win-x64" if machine in ["amd64", "x86_64"] else "win-arm64"
        elif system == "darwin":
            return "osx-x64" if machine in ["x86_64"] else "osx-arm64"
        elif system == "linux":
            return "linux-x64" if machine in ["x86_64", "amd64"] else "linux-arm64"
        else:
            raise LanguageServerException(f"Unsupported platform: {system} {machine}")

    def _get_runtime_dependencies(self, runtime_id: str) -> tuple[RuntimeDependency, RuntimeDependency]:
        """Get the language server and .NET runtime dependencies for the platform."""
        lang_server_dep = None
        dotnet_runtime_dep = None

        for dep in RUNTIME_DEPENDENCIES:
            if dep.id == "CSharpLanguageServer" and dep.platform_id == runtime_id:
                lang_server_dep = dep
            elif dep.id == "DotNetRuntime" and dep.platform_id == runtime_id:
                dotnet_runtime_dep = dep

        if not lang_server_dep:
            raise LanguageServerException(f"No C# language server dependency found for platform {runtime_id}")
        if not dotnet_runtime_dep:
            raise LanguageServerException(f"No .NET runtime dependency found for platform {runtime_id}")

        return lang_server_dep, dotnet_runtime_dep

    def _ensure_dotnet_runtime(self, logger: LanguageServerLogger, cache_dir: Path, runtime_dep: RuntimeDependency) -> str:
        """Ensure .NET runtime is available and return the dotnet executable path."""
        # Check if dotnet is already available in system
        system_dotnet = shutil.which("dotnet")
        if system_dotnet:
            # Check if it's .NET 9
            try:
                import subprocess

                result = subprocess.run([system_dotnet, "--list-runtimes"], capture_output=True, text=True, check=True)
                if "Microsoft.NETCore.App 9." in result.stdout:
                    logger.log("Found system .NET 9 runtime", logging.INFO)
                    return system_dotnet
            except subprocess.CalledProcessError:
                pass

        # Download .NET 9 runtime using config
        return self._ensure_dotnet_runtime_from_config(logger, cache_dir, runtime_dep)

    def _ensure_language_server(self, logger: LanguageServerLogger, cache_dir: Path, lang_server_dep: RuntimeDependency) -> str:
        """Ensure language server is available and return the DLL path."""
        package_name = lang_server_dep.package_name
        package_version = lang_server_dep.package_version

        server_dir = cache_dir / f"{package_name}.{package_version}"
        server_dll = server_dir / lang_server_dep.binary_name

        if server_dll.exists():
            logger.log(f"Using cached Microsoft.CodeAnalysis.LanguageServer from {server_dll}", logging.INFO)
            return str(server_dll)

        # Download and install the language server
        logger.log(f"Downloading {package_name} version {package_version}...", logging.INFO)
        package_path = self._download_nuget_package_direct(logger, package_name, package_version, cache_dir)

        # Extract and install
        self._extract_language_server(lang_server_dep, package_path, server_dir)

        if not server_dll.exists():
            raise LanguageServerException("Microsoft.CodeAnalysis.LanguageServer.dll not found after extraction")

        # Make executable on Unix systems
        if platform.system().lower() != "windows":
            server_dll.chmod(server_dll.stat().st_mode | stat.S_IEXEC)

        logger.log(f"Successfully installed Microsoft.CodeAnalysis.LanguageServer to {server_dll}", logging.INFO)
        return str(server_dll)

    def _extract_language_server(self, lang_server_dep: RuntimeDependency, package_path: Path, server_dir: Path) -> None:
        """Extract language server files from downloaded package."""
        extract_path = lang_server_dep.extract_path or "lib/net9.0"
        source_dir = package_path / extract_path

        if not source_dir.exists():
            # Try alternative locations
            for possible_dir in [
                package_path / "tools" / "net9.0" / "any",
                package_path / "lib" / "net9.0",
                package_path / "contentFiles" / "any" / "net9.0",
            ]:
                if possible_dir.exists():
                    source_dir = possible_dir
                    break
            else:
                raise LanguageServerException(f"Could not find language server files in package. Searched in {package_path}")

        # Copy files to cache directory
        server_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, server_dir, dirs_exist_ok=True)

    def _download_nuget_package_direct(
        self, logger: LanguageServerLogger, package_name: str, package_version: str, cache_dir: Path
    ) -> Path:
        """
        Download a NuGet package directly from the Azure NuGet feed.
        Returns the path to the extracted package directory.
        """
        azure_feed_url = "https://pkgs.dev.azure.com/azure-public/vside/_packaging/vs-impl/nuget/v3/index.json"

        # Create temporary directory for package download
        temp_dir = cache_dir / "temp_downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # First, get the service index from the Azure feed
            logger.log("Fetching NuGet service index from Azure feed...", logging.DEBUG)
            with urllib.request.urlopen(azure_feed_url) as response:
                service_index = json.loads(response.read().decode())

            # Find the package base address (for downloading packages)
            package_base_address = None
            for resource in service_index.get("resources", []):
                if resource.get("@type") == "PackageBaseAddress/3.0.0":
                    package_base_address = resource.get("@id")
                    break

            if not package_base_address:
                raise LanguageServerException("Could not find package base address in Azure NuGet feed")

            # Construct the download URL for the specific package
            package_id_lower = package_name.lower()
            package_version_lower = package_version.lower()
            package_url = f"{package_base_address.rstrip('/')}/{package_id_lower}/{package_version_lower}/{package_id_lower}.{package_version_lower}.nupkg"

            logger.log(f"Downloading package from: {package_url}", logging.DEBUG)

            # Download the .nupkg file
            nupkg_file = temp_dir / f"{package_name}.{package_version}.nupkg"
            urllib.request.urlretrieve(package_url, nupkg_file)

            # Extract the .nupkg file (it's just a zip file)
            package_extract_dir = temp_dir / f"{package_name}.{package_version}"
            package_extract_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(nupkg_file, "r") as zip_ref:
                zip_ref.extractall(package_extract_dir)

            # Clean up the nupkg file
            nupkg_file.unlink()

            logger.log(f"Successfully downloaded and extracted {package_name} version {package_version}", logging.INFO)
            return package_extract_dir

        except Exception as e:
            raise LanguageServerException(
                f"Failed to download package {package_name} version {package_version} from Azure NuGet feed: {e}"
            ) from e

    def _ensure_dotnet_runtime_from_config(self, logger: LanguageServerLogger, cache_dir: Path, runtime_dep: RuntimeDependency) -> str:
        """
        Ensure .NET 9 runtime is available using runtime dependency configuration.
        Returns the path to the dotnet executable.
        """
        # Check if dotnet is already available in system
        system_dotnet = shutil.which("dotnet")
        if system_dotnet:
            # Check if it's .NET 9
            try:
                import subprocess

                result = subprocess.run([system_dotnet, "--list-runtimes"], capture_output=True, text=True, check=True)
                if "Microsoft.NETCore.App 9." in result.stdout:
                    logger.log("Found system .NET 9 runtime", logging.INFO)
                    return system_dotnet
            except subprocess.CalledProcessError:
                pass

        # Download .NET 9 runtime using config
        dotnet_dir = cache_dir / "dotnet-runtime-9.0"
        dotnet_exe = dotnet_dir / runtime_dep.binary_name

        if dotnet_exe.exists():
            logger.log(f"Using cached .NET runtime from {dotnet_exe}", logging.INFO)
            return str(dotnet_exe)

        # Download .NET runtime
        logger.log("Downloading .NET 9 runtime...", logging.INFO)
        dotnet_dir.mkdir(parents=True, exist_ok=True)

        url = runtime_dep.url
        archive_type = runtime_dep.archive_type

        # Download the runtime
        download_path = dotnet_dir / f"dotnet-runtime.{archive_type}"
        try:
            logger.log(f"Downloading from {url}", logging.DEBUG)
            urllib.request.urlretrieve(url, download_path)

            # Extract the archive
            if archive_type == "zip":
                with zipfile.ZipFile(download_path, "r") as zip_ref:
                    zip_ref.extractall(dotnet_dir)
            else:
                # tar.gz
                with tarfile.open(download_path, "r:gz") as tar_ref:
                    tar_ref.extractall(dotnet_dir)

            # Remove the archive
            download_path.unlink()

            # Make dotnet executable on Unix
            if platform.system().lower() != "windows":
                dotnet_exe.chmod(dotnet_exe.stat().st_mode | stat.S_IEXEC)

            logger.log(f"Successfully installed .NET 9 runtime to {dotnet_exe}", logging.INFO)
            return str(dotnet_exe)

        except Exception as e:
            raise LanguageServerException(f"Failed to download .NET 9 runtime from {url}: {e}") from e

    def _get_initialize_params(self) -> InitializeParams:
        """
        Returns the initialize params for the Microsoft.CodeAnalysis.LanguageServer.
        """
        root_uri = PathUtils.path_to_uri(self.repository_root_path)
        root_name = os.path.basename(self.repository_root_path)
        return cast(
            InitializeParams,
            {
                "workspaceFolders": [{"uri": root_uri, "name": root_name}],
                "processId": os.getpid(),
                "rootPath": self.repository_root_path,
                "rootUri": root_uri,
                "capabilities": {
                    "window": {
                        "workDoneProgress": True,
                        "showMessage": {"messageActionItem": {"additionalPropertiesSupport": True}},
                        "showDocument": {"support": True},
                    },
                    "workspace": {
                        "applyEdit": True,
                        "workspaceEdit": {"documentChanges": True},
                        "didChangeConfiguration": {"dynamicRegistration": True},
                        "didChangeWatchedFiles": {"dynamicRegistration": True},
                        "symbol": {
                            "dynamicRegistration": True,
                            "symbolKind": {
                                "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
                            },
                        },
                        "executeCommand": {"dynamicRegistration": True},
                        "configuration": True,
                        "workspaceFolders": True,
                        "workDoneProgress": True,
                    },
                    "textDocument": {
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
                            "completionItemKind": {
                                "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
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
                        "definition": {"dynamicRegistration": True},
                        "references": {"dynamicRegistration": True},
                        "documentHighlight": {"dynamicRegistration": True},
                        "documentSymbol": {
                            "dynamicRegistration": True,
                            "symbolKind": {
                                "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
                            },
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
                        "codeLens": {"dynamicRegistration": True},
                        "formatting": {"dynamicRegistration": True},
                        "rangeFormatting": {"dynamicRegistration": True},
                        "onTypeFormatting": {"dynamicRegistration": True},
                        "rename": {"dynamicRegistration": True},
                        "publishDiagnostics": {"relatedInformation": True},
                        "foldingRange": {"dynamicRegistration": True, "rangeLimit": 5000, "lineFoldingOnly": True},
                    },
                },
            },
        )

    def _start_server(self):
        def do_nothing(params):
            return

        def window_log_message(msg):
            """Log messages from the language server."""
            message_text = msg.get("message", "")
            level = msg.get("type", 4)  # Default to Log level

            # Map LSP message types to Python logging levels
            level_map = {1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG}  # Error  # Warning  # Info  # Log

            self.logger.log(f"LSP: {message_text}", level_map.get(level, logging.DEBUG))

            # Also print important messages to console
            if level <= 3:  # Error, Warning, or Info
                print(f"C# Language Server: {message_text}")

        def handle_progress(params):
            """Handle progress notifications from the language server."""
            token = params.get("token", "")
            value = params.get("value", {})

            # Log raw progress for debugging
            self.logger.log(f"Progress notification received: {params}", logging.DEBUG)

            # Handle different progress notification types
            kind = value.get("kind")

            if kind == "begin":
                title = value.get("title", "Operation in progress")
                message = value.get("message", "")
                percentage = value.get("percentage")

                if percentage is not None:
                    self.logger.log(f"Progress [{token}]: {title} - {message} ({percentage}%)", logging.INFO)
                    print(f"C# Language Server: {title} - {message} ({percentage}%)")
                else:
                    self.logger.log(f"Progress [{token}]: {title} - {message}", logging.INFO)
                    print(f"C# Language Server: {title} - {message}")

            elif kind == "report":
                message = value.get("message", "")
                percentage = value.get("percentage")

                if percentage is not None:
                    self.logger.log(f"Progress [{token}]: {message} ({percentage}%)", logging.INFO)
                    if percentage % 10 == 0:  # Print every 10%
                        print(f"C# Language Server: {message} ({percentage}%)")
                elif message:
                    self.logger.log(f"Progress [{token}]: {message}", logging.INFO)

            elif kind == "end":
                message = value.get("message", "Operation completed")
                self.logger.log(f"Progress [{token}]: {message}", logging.INFO)
                print(f"C# Language Server: {message}")

        def handle_workspace_configuration(params):
            """Handle workspace/configuration requests from the server."""
            items = params.get("items", [])
            result = []

            for item in items:
                section = item.get("section", "")

                # Provide default values based on the configuration section
                if section.startswith(("dotnet", "csharp")):
                    # Default configuration for C# settings
                    if "enable" in section or "show" in section or "suppress" in section or "navigate" in section:
                        # Boolean settings
                        result.append(False)
                    elif "scope" in section:
                        # Scope settings - use appropriate enum values
                        if "analyzer_diagnostics_scope" in section:
                            result.append("openFiles")  # BackgroundAnalysisScope
                        elif "compiler_diagnostics_scope" in section:
                            result.append("openFiles")  # CompilerDiagnosticsScope
                        else:
                            result.append("openFiles")
                    elif section == "dotnet_member_insertion_location":
                        # ImplementTypeInsertionBehavior enum
                        result.append("with_other_members_of_the_same_kind")
                    elif section == "dotnet_property_generation_behavior":
                        # ImplementTypePropertyGenerationBehavior enum
                        result.append("prefer_throwing_properties")
                    elif "location" in section or "behavior" in section:
                        # Other enum settings - return null to avoid parsing errors
                        result.append(None)
                    else:
                        # Default for other dotnet/csharp settings
                        result.append(None)
                elif section == "tab_width" or section == "indent_size":
                    # Tab and indent settings
                    result.append(4)
                elif section == "insert_final_newline":
                    # Editor settings
                    result.append(True)
                else:
                    # Unknown configuration - return null
                    result.append(None)

            return result

        def handle_work_done_progress_create(params):
            """Handle work done progress create requests."""
            # Just acknowledge the request
            return

        def handle_register_capability(params):
            """Handle client/registerCapability requests."""
            # Just acknowledge the request - we don't need to track these for now
            return

        # Set up notification handlers
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", handle_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request("workspace/configuration", handle_workspace_configuration)
        self.server.on_request("window/workDoneProgress/create", handle_work_done_progress_create)
        self.server.on_request("client/registerCapability", handle_register_capability)

        self.logger.log("Starting Microsoft.CodeAnalysis.LanguageServer process", logging.INFO)

        try:
            self.server.start()
        except Exception as e:
            self.logger.log(f"Failed to start language server process: {e}", logging.ERROR)
            raise LanguageServerException(f"Failed to start C# language server: {e}")

        # Send initialization
        initialize_params = self._get_initialize_params()

        self.logger.log("Sending initialize request to language server", logging.INFO)
        try:
            init_response = self.server.send.initialize(initialize_params)
            self.logger.log(f"Received initialize response: {init_response}", logging.DEBUG)
        except Exception as e:
            raise LanguageServerException(f"Failed to initialize C# language server for {self.repository_root_path}: {e}") from e

        # Apply diagnostic capabilities
        self._force_pull_diagnostics(init_response)

        # Verify required capabilities
        capabilities = init_response.get("capabilities", {})
        required_capabilities = [
            "textDocumentSync",
            "definitionProvider",
            "referencesProvider",
            "documentSymbolProvider",
        ]
        missing = [cap for cap in required_capabilities if cap not in capabilities]
        if missing:
            raise RuntimeError(
                f"Language server is missing required capabilities: {', '.join(missing)}. "
                "Initialization failed. Please ensure the correct version of Microsoft.CodeAnalysis.LanguageServer is installed and the .NET runtime is working."
            )

        # Complete initialization
        self.server.notify.initialized({})

        # Open solution and project files
        self._open_solution_and_projects()

        self.initialization_complete.set()
        self.completions_available.set()

        self.logger.log(
            "Microsoft.CodeAnalysis.LanguageServer initialized and ready\n"
            "Waiting for language server to index project files...\n"
            "This may take a while for large projects",
            logging.INFO,
        )

    def _force_pull_diagnostics(self, init_response: dict) -> None:
        """
        Apply the diagnostic capabilities hack.
        Forces the server to support pull diagnostics.
        """
        capabilities = init_response.get("capabilities", {})
        diagnostic_provider = capabilities.get("diagnosticProvider", {})

        # Add the diagnostic capabilities hack
        if isinstance(diagnostic_provider, dict):
            diagnostic_provider.update(
                {
                    "interFileDependencies": True,
                    "workDoneProgress": True,
                    "workspaceDiagnostics": True,
                }
            )
            self.logger.log("Applied diagnostic capabilities hack for better C# diagnostics", logging.DEBUG)

    def _open_solution_and_projects(self) -> None:
        """
        Open solution and project files using notifications.
        """
        # Find solution file
        solution_file = None
        for filename in breadth_first_file_scan(self.repository_root_path):
            if filename.endswith(".sln"):
                solution_file = filename
                break

        # Send solution/open notification if solution file found
        if solution_file:
            solution_uri = PathUtils.path_to_uri(solution_file)
            self.server.notify.send_notification("solution/open", {"solution": solution_uri})
            self.logger.log(f"Opened solution file: {solution_file}", logging.INFO)

        # Find and open project files
        project_files = []
        for filename in breadth_first_file_scan(self.repository_root_path):
            if filename.endswith(".csproj"):
                project_files.append(filename)

        # Send project/open notifications for each project file
        if project_files:
            project_uris = [PathUtils.path_to_uri(project_file) for project_file in project_files]
            self.server.notify.send_notification("project/open", {"projects": project_uris})
            self.logger.log(f"Opened project files: {project_files}", logging.DEBUG)
