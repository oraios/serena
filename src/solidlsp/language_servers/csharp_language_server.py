"""
CSharp Language Server using Roslyn Language Server (Official Roslyn-based LSP server from NuGet.org)
"""

import logging
import os
import platform
import shutil
import threading
from collections.abc import Hashable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from overrides import override

from serena.util.dotnet import DotNETUtil
from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LSPFileBuffer,
    RawDocumentSymbol,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import Hover
from solidlsp.ls_utils import FileUtils, PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams, InitializeResult
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

NUGET_ALLOWED_HOSTS = ("www.nuget.org", "nuget.org", "globalcdn.nuget.org")
DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION = "5.5.0-2.26078.4"

_RUNTIME_DEPENDENCIES = [
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Roslyn Language Server for Windows (x64)",
        package_name="roslyn-language-server.win-x64",
        package_version=DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION,
        url=f"https://www.nuget.org/api/v2/package/roslyn-language-server.win-x64/{DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION}",
        platform_id="win-x64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="tools/net10.0/win-x64",
        sha256="7f3d4119e75305399e6faa81a68240b33c48b94ad523a904594abd00db95572a",
        allowed_hosts=NUGET_ALLOWED_HOSTS,
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Roslyn Language Server for Windows (ARM64)",
        package_name="roslyn-language-server.win-arm64",
        package_version=DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION,
        url=f"https://www.nuget.org/api/v2/package/roslyn-language-server.win-arm64/{DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION}",
        platform_id="win-arm64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="tools/net10.0/win-arm64",
        sha256="0fe3381c4340a7494a5242c3d0c8be1af6ef0802de8b458f947cebca76fd26bc",
        allowed_hosts=NUGET_ALLOWED_HOSTS,
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Roslyn Language Server for macOS (x64)",
        package_name="roslyn-language-server.osx-x64",
        package_version=DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION,
        url=f"https://www.nuget.org/api/v2/package/roslyn-language-server.osx-x64/{DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION}",
        platform_id="osx-x64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="tools/net10.0/osx-x64",
        sha256="c8de61a88c65150e12f561a2659f70b59d27a7465865136a1de950d2ef826c6d",
        allowed_hosts=NUGET_ALLOWED_HOSTS,
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Roslyn Language Server for macOS (ARM64)",
        package_name="roslyn-language-server.osx-arm64",
        package_version=DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION,
        url=f"https://www.nuget.org/api/v2/package/roslyn-language-server.osx-arm64/{DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION}",
        platform_id="osx-arm64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="tools/net10.0/osx-arm64",
        sha256="995207c14e01dafa71e84080a7eb1f045a697b0c3bb468077bb3809b69bdf456",
        allowed_hosts=NUGET_ALLOWED_HOSTS,
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Roslyn Language Server for Linux (x64)",
        package_name="roslyn-language-server.linux-x64",
        package_version=DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION,
        url=f"https://www.nuget.org/api/v2/package/roslyn-language-server.linux-x64/{DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION}",
        platform_id="linux-x64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="tools/net10.0/linux-x64",
        sha256="1aad25de456d637a1eee993ca0d569a1b78d711744ccb36410a3a20250a48aa6",
        allowed_hosts=NUGET_ALLOWED_HOSTS,
    ),
    RuntimeDependency(
        id="CSharpLanguageServer",
        description="Roslyn Language Server for Linux (ARM64)",
        package_name="roslyn-language-server.linux-arm64",
        package_version=DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION,
        url=f"https://www.nuget.org/api/v2/package/roslyn-language-server.linux-arm64/{DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION}",
        platform_id="linux-arm64",
        archive_type="nupkg",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="tools/net10.0/linux-arm64",
        sha256="a7dd49bbc0e25d0e2968ae31ec5f3c774373866db51f3500fcea0ac320e2bbc1",
        allowed_hosts=NUGET_ALLOWED_HOSTS,
    ),
]


def _runtime_dependencies_for_version(version: str) -> list[RuntimeDependency]:
    """Return the Roslyn LS runtime dependencies for the configured version."""
    default_version = version == DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION
    result: list[RuntimeDependency] = []
    for dependency in _RUNTIME_DEPENDENCIES:
        assert dependency.package_version is not None
        assert dependency.url is not None
        result.append(
            replace(
                dependency,
                package_version=version,
                url=dependency.url.replace(dependency.package_version, version),
                sha256=dependency.sha256 if default_version else None,
            )
        )
    return result


def breadth_first_file_scan(root_dir: str) -> Iterable[str]:
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


def find_solution_or_project_file(root_dir: str) -> str | None:
    """
    Find the first .sln or .slnx file in breadth-first order.
    If no solution file is found, look for a .csproj file.
    """
    sln_file = None
    csproj_file = None

    for filename in breadth_first_file_scan(root_dir):
        if filename.endswith((".sln", ".slnx")) and sln_file is None:
            sln_file = filename
        elif filename.endswith(".csproj") and csproj_file is None:
            csproj_file = filename

        # If we found a solution file, return it immediately
        if sln_file:
            return sln_file

    # If no solution file was found, return the first .csproj file
    return csproj_file


class CSharpLanguageServer(SolidLanguageServer):
    """
    Provides C# specific instantiation of the LanguageServer class using the official Roslyn-based
    language server from NuGet.org.

    You can pass a list of runtime dependency overrides in ls_specific_settings["csharp"]["runtime_dependencies"].
    This is a list of dicts, each containing at least the "id" key, and optionally "platform_id" to uniquely
    identify the dependency to override.

    You can also set `csharp_language_server_version` in ``ls_specific_settings["csharp"]`` to override
    the pinned Roslyn Language Server package version Serena downloads by default.

    Example - Override Roslyn Language Server URL:
    ```
        {
            "id": "CSharpLanguageServer",
            "platform_id": "win-x64",
            "url": "https://example.com/custom-roslyn-server.nupkg"
        }
    ```

    See the `_RUNTIME_DEPENDENCIES` variable above for the available dependency ids and platform_ids.

    Note: .NET runtime (version 10+) is required and installed automatically via Microsoft's official install
    scripts. If you have a custom .NET installation, ensure 'dotnet' is available in PATH with version 10 or higher.
    """

    @classmethod
    def supports_implementation_request(cls) -> bool:
        return True

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a CSharpLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(config, repository_root_path, None, "csharp", solidlsp_settings)
        # Cache for original Roslyn symbol names with type annotations
        # Key: (relative_file_path, line, character) -> Value: original name
        self._original_symbol_names: dict[tuple[str, int, int], str] = {}

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir, self._solidlsp_settings, self.repository_root_path)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["bin", "obj", "packages", ".vs"]

    @override
    def request_hover(self, relative_file_path: str, line: int, column: int, file_buffer: LSPFileBuffer | None = None) -> Hover | None:
        """
        Override to inject original Roslyn symbol names (with type annotations) into hover responses.

        When hovering over a symbol whose name was normalized, we prepend the original
        full name (e.g., 'Add(int, int) : int') to the hover content.
        """
        hover = super().request_hover(relative_file_path, line, column, file_buffer=file_buffer)

        if hover is None:
            return None

        # Check if we have an original name for this position
        original_name = self._original_symbol_names.get((relative_file_path, line, column))

        if original_name and "contents" in hover:
            contents = hover["contents"]
            if isinstance(contents, dict) and "value" in contents:
                # Prepend the original full name with type information to the hover content
                prefix = f"**{original_name}**\n\n---\n\n"
                contents["value"] = prefix + contents["value"]

        return hover

    def _document_symbols_cache_fingerprint(self) -> Hashable | None:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        # Roslyn 5.5.0+ returns symbol names with type annotations:
        #  - Properties: "Name : string"
        #  - Methods: "Add(int, int) : int"
        #
        # This method:
        #  1. Normalizes names to base form ("Name", "Add")
        #  2. Caches original names for rich information display
        #  3. Populates LSP spec's 'detail' field with type/signature info
        original_name = symbol["name"]

        # Extract base name and type/signature info
        normalized_name, type_info = self._extract_base_name_and_type(original_name)

        # Store original name if it was normalized
        if original_name != normalized_name:
            sel_range = symbol.get("selectionRange")
            if sel_range:
                start = sel_range.get("start")  # type: ignore
                if start and "line" in start and "character" in start:
                    line = start["line"]
                    char = start["character"]
                    cache_key = (relative_file_path, line, char)
                    self._original_symbol_names[cache_key] = original_name

            # Populate 'detail' field with type/signature information (for UnifiedSymbolInformation)
            if type_info and "detail" not in symbol:
                symbol["detail"] = type_info  # type: ignore

        return normalized_name

    @staticmethod
    def _extract_base_name_and_type(roslyn_name: str) -> tuple[str, str]:
        """
        Extract base name and type/signature information from Roslyn symbol names.

        Examples:
            "Name : string" -> ("Name", ": string")
            "Add(int, int) : int" -> ("Add", "(int, int) : int")
            "ToString()" -> ("ToString", "()")
            "SimpleMethod" -> ("SimpleMethod", "")

        Returns:
            Tuple of (base_name, type_info)

        """
        # Check for property pattern: "Name : Type"
        if " : " in roslyn_name and "(" not in roslyn_name:
            base_name, type_part = roslyn_name.split(" : ", 1)
            return base_name.strip(), f": {type_part.strip()}"

        # Check for method pattern: "MethodName(params) : ReturnType"
        if "(" in roslyn_name:
            paren_idx = roslyn_name.index("(")
            base_name = roslyn_name[:paren_idx].strip()
            signature = roslyn_name[paren_idx:].strip()
            return base_name, signature

        # No type annotation
        return roslyn_name, ""

    class DependencyProvider(LanguageServerDependencyProvider):
        def __init__(
            self,
            custom_settings: SolidLSPSettings.CustomLSSettings,
            ls_resources_dir: str,
            solidlsp_settings: SolidLSPSettings,
            repository_root_path: str,
        ):
            super().__init__(custom_settings, ls_resources_dir)
            self._solidlsp_settings = solidlsp_settings
            self._repository_root_path = repository_root_path
            self._dotnet_path, self._language_server_path = self._ensure_server_installed()

        def create_launch_command(self) -> list[str]:
            # Find solution or project file
            solution_or_project = find_solution_or_project_file(self._repository_root_path)

            # Create log directory
            log_dir = Path(self._ls_resources_dir) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            # Build command using dotnet directly
            cmd = [self._dotnet_path, self._language_server_path, "--logLevel=Information", f"--extensionLogDirectory={log_dir}", "--stdio"]

            # The language server will discover the solution/project from the workspace root
            if solution_or_project:
                log.info(f"Found solution/project file: {solution_or_project}")
            else:
                log.warning("No .sln/.slnx or .csproj file found, language server will attempt auto-discovery")

            log.debug(f"Language server command: {' '.join(cmd)}")

            return cmd

        def _ensure_server_installed(self) -> tuple[str, str]:
            """
            Ensure .NET runtime and Microsoft.CodeAnalysis.LanguageServer are available.
            Returns a tuple of (dotnet_path, language_server_dll_path).
            """
            runtime_dependency_overrides = cast(list[dict[str, Any]], self._custom_settings.get("runtime_dependencies", []))

            # Filter out deprecated DotNetRuntime overrides and warn users
            filtered_overrides = []
            for dep_override in runtime_dependency_overrides:
                if dep_override.get("id") == "DotNetRuntime":
                    log.warning(
                        "The 'DotNetRuntime' runtime_dependencies override is no longer supported. "
                        ".NET is now installed automatically via Microsoft's official install scripts. "
                        "Please remove this override from your configuration."
                    )
                else:
                    filtered_overrides.append(dep_override)

            log.debug("Resolving runtime dependencies")
            csharp_language_server_version = self._custom_settings.get(
                "csharp_language_server_version", DEFAULT_CSHARP_LANGUAGE_SERVER_VERSION
            )

            runtime_dependencies = RuntimeDependencyCollection(
                _runtime_dependencies_for_version(csharp_language_server_version),
                overrides=filtered_overrides,
            )

            log.debug(
                f"Available runtime dependencies: {runtime_dependencies.get_dependencies_for_current_platform}",
            )

            # Find the dependencies for our platform
            lang_server_dep = runtime_dependencies.get_single_dep_for_current_platform("CSharpLanguageServer")
            dotnet_path = self._ensure_dotnet_runtime()
            server_dll_path = self._ensure_language_server(lang_server_dep)

            return dotnet_path, server_dll_path

        def _ensure_dotnet_runtime(self) -> str:
            """Ensure .NET runtime is available and return the dotnet executable path."""
            return DotNETUtil("10.0", allow_higher_version=True).get_dotnet_path_or_raise()

        def _ensure_language_server(self, lang_server_dep: RuntimeDependency) -> str:
            """Ensure language server is available and return the DLL path."""
            package_name = lang_server_dep.package_name
            package_version = lang_server_dep.package_version

            server_dir = Path(self._ls_resources_dir) / f"{package_name}.{package_version}"
            assert lang_server_dep.binary_name is not None
            server_dll = server_dir / lang_server_dep.binary_name

            if server_dll.exists():
                log.info(f"Using cached Roslyn Language Server from {server_dll}")
                return str(server_dll)

            # Download and install the language server
            log.info(f"Downloading {package_name} version {package_version} from NuGet.org...")
            package_path = self._download_nuget_package(lang_server_dep)

            # Extract and install
            self._extract_language_server(lang_server_dep, package_path, server_dir)

            if not server_dll.exists():
                raise SolidLSPException("Roslyn Language Server DLL not found after extraction")

            # Make executable on Unix systems
            if platform.system().lower() != "windows":
                server_dll.chmod(0o755)

            log.info(f"Successfully installed Roslyn Language Server to {server_dll}")
            return str(server_dll)

        @staticmethod
        def _extract_language_server(lang_server_dep: RuntimeDependency, package_path: Path, server_dir: Path) -> None:
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
                    raise SolidLSPException(f"Could not find language server files in package. Searched in {package_path}")

            # Copy files to cache directory
            server_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, server_dir, dirs_exist_ok=True)

        def _download_nuget_package(self, dependency: RuntimeDependency) -> Path:
            """
            Download a NuGet package from NuGet.org and extract it.
            Returns the path to the extracted package directory.
            """
            package_name = dependency.package_name
            package_version = dependency.package_version
            url = dependency.url

            if url is None:
                raise SolidLSPException(f"No URL specified for package {package_name} version {package_version}")

            temp_dir = Path(self._ls_resources_dir) / "temp_downloads"
            temp_dir.mkdir(parents=True, exist_ok=True)

            try:
                log.debug(f"Downloading package from: {url}")
                package_extract_dir = temp_dir / f"{package_name}.{package_version}"
                FileUtils.download_and_extract_archive_verified(
                    url,
                    str(package_extract_dir),
                    "zip",
                    expected_sha256=dependency.sha256,
                    allowed_hosts=dependency.allowed_hosts,
                )

                log.info(f"Successfully downloaded and extracted {package_name} version {package_version} from NuGet.org")
                return package_extract_dir

            except Exception as e:
                raise SolidLSPException(f"Failed to download package {package_name} version {package_version} from NuGet.org: {e}") from e

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
                            "symbolKind": {"valueSet": list(range(1, 27))},
                        },
                        "executeCommand": {"dynamicRegistration": True},
                        "configuration": True,
                        "workspaceFolders": True,
                        "workDoneProgress": True,
                    },
                    "textDocument": {
                        "synchronization": {"dynamicRegistration": True, "willSave": True, "willSaveWaitUntil": True, "didSave": True},
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
                        "documentSymbol": {
                            "dynamicRegistration": True,
                            "symbolKind": {"valueSet": list(range(1, 27))},
                            "hierarchicalDocumentSymbolSupport": True,
                        },
                    },
                },
            },
        )

    def _start_server(self) -> None:
        indexing_complete = threading.Event()

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            """Log messages from the language server."""
            message_text = msg.get("message", "")
            level = msg.get("type", 4)  # Default to Log level

            # Map LSP message types to Python logging levels
            level_map = {1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG}  # Error  # Warning  # Info  # Log

            log.log(level_map.get(level, logging.DEBUG), f"LSP: {message_text}")

        def handle_progress(params: dict) -> None:
            """Handle progress notifications from the language server."""
            token = params.get("token", "")
            value = params.get("value", {})

            # Log raw progress for debugging
            log.debug(f"Progress notification received: {params}")

            # Handle different progress notification types
            kind = value.get("kind")

            if kind == "begin":
                title = value.get("title", "Operation in progress")
                message = value.get("message", "")
                percentage = value.get("percentage")

                if percentage is not None:
                    log.debug(f"Progress [{token}]: {title} - {message} ({percentage}%)")
                else:
                    log.info(f"Progress [{token}]: {title} - {message}")

            elif kind == "report":
                message = value.get("message", "")
                percentage = value.get("percentage")

                if percentage is not None:
                    log.info(f"Progress [{token}]: {message} ({percentage}%)")
                elif message:
                    log.info(f"Progress [{token}]: {message}")

            elif kind == "end":
                message = value.get("message", "Operation completed")
                log.info(f"Progress [{token}]: {message}")

        def handle_workspace_configuration(params: dict) -> list:
            """Handle workspace/configuration requests from the server."""
            items = params.get("items", [])
            result: list[Any] = []

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

        def handle_work_done_progress_create(params: dict) -> None:
            """Handle work done progress create requests."""
            # Just acknowledge the request
            return

        def handle_register_capability(params: dict) -> None:
            """Handle client/registerCapability requests."""
            # Just acknowledge the request - we don't need to track these for now
            return

        def handle_project_needs_restore(params: dict) -> None:
            return

        def handle_workspace_indexing_complete(params: dict) -> None:
            indexing_complete.set()

        # Set up notification handlers
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", handle_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("workspace/projectInitializationComplete", handle_workspace_indexing_complete)
        self.server.on_request("workspace/configuration", handle_workspace_configuration)
        self.server.on_request("window/workDoneProgress/create", handle_work_done_progress_create)
        self.server.on_request("client/registerCapability", handle_register_capability)
        self.server.on_request("workspace/_roslyn_projectNeedsRestore", handle_project_needs_restore)

        log.info("Starting Microsoft.CodeAnalysis.LanguageServer process")

        try:
            self.server.start()
        except Exception as e:
            log.info(f"Failed to start language server process: {e}", logging.ERROR)
            raise SolidLSPException(f"Failed to start C# language server: {e}")

        # Send initialization
        initialize_params = self._get_initialize_params()

        log.info("Sending initialize request to language server")
        try:
            init_response = self.server.send.initialize(initialize_params)
            log.info(f"Received initialize response: {init_response}")
        except Exception as e:
            raise SolidLSPException(f"Failed to initialize C# language server for {self.repository_root_path}: {e}") from e

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

        log.info(
            "Microsoft.CodeAnalysis.LanguageServer initialized and ready\n"
            "Waiting for language server to index project files...\n"
            "This may take a while for large projects"
        )

        if indexing_complete.wait(30):  # Wait up to 30 seconds for indexing
            log.info("Indexing complete")
        else:
            log.warning("Timeout waiting for indexing to complete, proceeding anyway")

    def _force_pull_diagnostics(self, init_response: dict | InitializeResult) -> None:
        """
        Apply the diagnostic capabilities hack.
        Forces the server to support pull diagnostics.
        """
        capabilities = init_response.get("capabilities", {})
        diagnostic_provider: Any = capabilities.get("diagnosticProvider", {})

        # Add the diagnostic capabilities hack
        if isinstance(diagnostic_provider, dict):
            diagnostic_provider.update(
                {
                    "interFileDependencies": True,
                    "workDoneProgress": True,
                    "workspaceDiagnostics": True,
                }
            )
            log.debug("Applied diagnostic capabilities hack for better C# diagnostics")

    def _open_solution_and_projects(self) -> None:
        """
        Open solution and project files using notifications.
        """
        # Find solution file (.sln or .slnx)
        solution_file = None
        for filename in breadth_first_file_scan(self.repository_root_path):
            if filename.endswith((".sln", ".slnx")):
                solution_file = filename
                break

        # Send solution/open notification if solution file found
        if solution_file:
            solution_uri = PathUtils.path_to_uri(solution_file)
            self.server.notify.send_notification("solution/open", {"solution": solution_uri})
            log.debug(f"Opened solution file: {solution_file}")

        # Find and open project files
        project_files = []
        for filename in breadth_first_file_scan(self.repository_root_path):
            if filename.endswith(".csproj"):
                project_files.append(filename)

        # Send project/open notifications for each project file
        if project_files:
            project_uris = [PathUtils.path_to_uri(project_file) for project_file in project_files]
            self.server.notify.send_notification("project/open", {"projects": project_uris})
            log.debug(f"Opened project files: {project_files}")

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 2
