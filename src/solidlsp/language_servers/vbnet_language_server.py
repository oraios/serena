"""
VB.NET Language Server using Roslyn Language Server (GitHub: LaunchCG/roslyn-vbnet-languageserver)
"""

import logging
import os
import platform
import threading
from collections.abc import Hashable, Iterable
from pathlib import Path
from typing import Any, cast

from overrides import override

from serena.util.dotnet import DotNETUtil
from solidlsp.ls import LanguageServerDependencyProvider, LSPFileBuffer, RawDocumentSymbol, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import Hover
from solidlsp.ls_utils import FileUtils, PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeResult
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

_VBNET_VERSION = "v1.1.0"
_VBNET_BASE_URL = f"https://github.com/LaunchCG/roslyn-vbnet-languageserver/releases/download/{_VBNET_VERSION}"

_RUNTIME_DEPENDENCIES = [
    RuntimeDependency(
        id="VBNetLanguageServer",
        description="Roslyn VB.NET Language Server for Windows (x64)",
        package_name="roslyn-vbnet-win-x64",
        package_version="1.1.0",
        url=f"{_VBNET_BASE_URL}/roslyn-vbnet-win-x64.zip",
        platform_id="win-x64",
        archive_type="zip",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="LanguageServer",
    ),
    RuntimeDependency(
        id="VBNetLanguageServer",
        description="Roslyn VB.NET Language Server for Windows (ARM64)",
        package_name="roslyn-vbnet-win-arm64",
        package_version="1.1.0",
        url=f"{_VBNET_BASE_URL}/roslyn-vbnet-win-arm64.zip",
        platform_id="win-arm64",
        archive_type="zip",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="LanguageServer",
    ),
    RuntimeDependency(
        id="VBNetLanguageServer",
        description="Roslyn VB.NET Language Server for macOS (x64)",
        package_name="roslyn-vbnet-osx-x64",
        package_version="1.1.0",
        url=f"{_VBNET_BASE_URL}/roslyn-vbnet-osx-x64.tar.gz",
        platform_id="osx-x64",
        archive_type="gztar",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="LanguageServer",
    ),
    RuntimeDependency(
        id="VBNetLanguageServer",
        description="Roslyn VB.NET Language Server for macOS (ARM64)",
        package_name="roslyn-vbnet-osx-arm64",
        package_version="1.1.0",
        url=f"{_VBNET_BASE_URL}/roslyn-vbnet-osx-arm64.tar.gz",
        platform_id="osx-arm64",
        archive_type="gztar",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="LanguageServer",
    ),
    RuntimeDependency(
        id="VBNetLanguageServer",
        description="Roslyn VB.NET Language Server for Linux (x64)",
        package_name="roslyn-vbnet-linux-x64",
        package_version="1.1.0",
        url=f"{_VBNET_BASE_URL}/roslyn-vbnet-linux-x64.tar.gz",
        platform_id="linux-x64",
        archive_type="gztar",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="LanguageServer",
    ),
    RuntimeDependency(
        id="VBNetLanguageServer",
        description="Roslyn VB.NET Language Server for Linux (ARM64)",
        package_name="roslyn-vbnet-linux-arm64",
        package_version="1.1.0",
        url=f"{_VBNET_BASE_URL}/roslyn-vbnet-linux-arm64.tar.gz",
        platform_id="linux-arm64",
        archive_type="gztar",
        binary_name="Microsoft.CodeAnalysis.LanguageServer.dll",
        extract_path="LanguageServer",
    ),
]


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
            pass


def find_solution_or_project_file(root_dir: str) -> str | None:
    """
    Find the first .sln or .slnx file in breadth-first order.
    If no solution file is found, look for a .vbproj file.
    """
    sln_file = None
    vbproj_file = None

    for filename in breadth_first_file_scan(root_dir):
        if filename.endswith((".sln", ".slnx")) and sln_file is None:
            sln_file = filename
        elif filename.endswith((".vbproj", ".csproj")) and vbproj_file is None:
            vbproj_file = filename

        if sln_file:
            return sln_file

    return vbproj_file


class VBNetLanguageServer(SolidLanguageServer):
    """
    Provides VB.NET specific instantiation of the LanguageServer class using a Roslyn-based
    language server downloaded from GitHub (LaunchCG/roslyn-vbnet-languageserver).

    You can pass a list of runtime dependency overrides in ls_specific_settings["vbnet"]["runtime_dependencies"].
    This is a list of dicts, each containing at least the "id" key, and optionally "platform_id" to uniquely
    identify the dependency to override.

    Example - Override VB.NET Language Server URL:
    ```
        {
            "id": "VBNetLanguageServer",
            "platform_id": "win-x64",
            "url": "https://example.com/custom-vbnet-server.zip"
        }
    ```

    See the `_RUNTIME_DEPENDENCIES` variable above for the available dependency ids and platform_ids.

    Note: .NET runtime (version 10+) is required and installed automatically via Microsoft's official install
    scripts. If you have a custom .NET installation, ensure 'dotnet' is available in PATH with version 10 or higher.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, None, "vbnet", solidlsp_settings)
        self._original_symbol_names: dict[tuple[str, int, int], str] = {}

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir, self._solidlsp_settings, self.repository_root_path)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["bin", "obj", "packages", ".vs"]

    @override
    def request_hover(self, relative_file_path: str, line: int, column: int, file_buffer: LSPFileBuffer | None = None) -> Hover | None:
        hover = super().request_hover(relative_file_path, line, column, file_buffer=file_buffer)

        if hover is None:
            return None

        original_name = self._original_symbol_names.get((relative_file_path, line, column))

        if original_name and "contents" in hover:
            contents = hover["contents"]
            if isinstance(contents, dict) and "value" in contents:
                prefix = f"**{original_name}**\n\n---\n\n"
                contents["value"] = prefix + contents["value"]

        return hover

    def _document_symbols_cache_fingerprint(self) -> Hashable | None:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        original_name = symbol.get("name") or ""

        normalized_name, type_info = self._extract_base_name_and_type(original_name)

        if original_name != normalized_name:
            sel_range = symbol.get("selectionRange")
            if sel_range:
                start = sel_range.get("start")
                if start and "line" in start and "character" in start:
                    line = start["line"]
                    char = start["character"]
                    cache_key = (relative_file_path, line, char)
                    self._original_symbol_names[cache_key] = original_name

            if type_info and "detail" not in symbol:
                symbol["detail"] = type_info  # type: ignore

        return normalized_name

    @staticmethod
    def _extract_base_name_and_type(roslyn_name: str) -> tuple[str, str]:
        if " : " in roslyn_name and "(" not in roslyn_name:
            base_name, type_part = roslyn_name.split(" : ", 1)
            return base_name.strip(), f": {type_part.strip()}"

        if "(" in roslyn_name:
            paren_idx = roslyn_name.index("(")
            base_name = roslyn_name[:paren_idx].strip()
            signature = roslyn_name[paren_idx:].strip()
            return base_name, signature

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
            solution_or_project = find_solution_or_project_file(self._repository_root_path)

            log_dir = Path(self._ls_resources_dir) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            cmd = [self._dotnet_path, self._language_server_path, "--logLevel=Information", f"--extensionLogDirectory={log_dir}", "--stdio"]

            if solution_or_project:
                log.info(f"Found solution/project file: {solution_or_project}")
            else:
                log.warning("No .sln/.slnx or .vbproj file found, language server will attempt auto-discovery")

            log.debug(f"Language server command: {' '.join(cmd)}")

            return cmd

        def _ensure_server_installed(self) -> tuple[str, str]:
            runtime_dependency_overrides = cast(list[dict[str, Any]], self._custom_settings.get("runtime_dependencies", []))

            runtime_dependencies = RuntimeDependencyCollection(
                _RUNTIME_DEPENDENCIES,
                overrides=runtime_dependency_overrides,
            )

            lang_server_dep = runtime_dependencies.get_single_dep_for_current_platform("VBNetLanguageServer")
            dotnet_path = self._ensure_dotnet_runtime()
            server_dll_path = self._ensure_language_server(lang_server_dep)

            return dotnet_path, server_dll_path

        def _ensure_dotnet_runtime(self) -> str:
            return DotNETUtil("10.0", allow_higher_version=True).get_dotnet_path_or_raise()

        def _ensure_language_server(self, lang_server_dep: RuntimeDependency) -> str:
            package_name = lang_server_dep.package_name
            package_version = lang_server_dep.package_version

            server_dir = Path(self._ls_resources_dir) / f"{package_name}.{package_version}"
            assert lang_server_dep.binary_name is not None
            dll_dir = server_dir / lang_server_dep.extract_path if lang_server_dep.extract_path else server_dir
            server_dll = dll_dir / lang_server_dep.binary_name

            if server_dll.exists():
                log.info(f"Using cached VB.NET Language Server from {server_dll}")
                return str(server_dll)

            url = lang_server_dep.url
            if url is None:
                raise SolidLSPException(f"No URL specified for package {package_name} version {package_version}")

            log.info(f"Downloading {package_name} version {package_version} from GitHub...")
            archive_type = lang_server_dep.archive_type or "zip"
            FileUtils.download_and_extract_archive(url, str(server_dir), archive_type)

            if not server_dll.exists():
                raise SolidLSPException("VB.NET Language Server DLL not found after extraction")

            if platform.system().lower() != "windows":
                server_dll.chmod(0o755)

            log.info(f"Successfully installed VB.NET Language Server to {server_dll}")
            return str(server_dll)

    def _create_base_initialize_params(self) -> dict:
        return {
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
        }

    def _start_server(self) -> None:
        indexing_complete = threading.Event()

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            message_text = msg.get("message", "")
            level = msg.get("type", 4)

            level_map = {1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG}

            log.log(level_map.get(level, logging.DEBUG), f"LSP: {message_text}")

        def handle_progress(params: dict) -> None:
            token = params.get("token", "")
            value = params.get("value", {})

            log.debug(f"Progress notification received: {params}")

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
            items = params.get("items", [])
            result: list[Any] = []

            for item in items:
                section = item.get("section", "")

                if section.startswith(("dotnet", "visualbasic", "csharp")):
                    if "enable" in section or "show" in section or "suppress" in section or "navigate" in section:
                        result.append(False)
                    elif "scope" in section:
                        if "analyzer_diagnostics_scope" in section:
                            result.append("openFiles")
                        elif "compiler_diagnostics_scope" in section:
                            result.append("openFiles")
                        else:
                            result.append("openFiles")
                    elif section == "dotnet_member_insertion_location":
                        result.append("with_other_members_of_the_same_kind")
                    elif section == "dotnet_property_generation_behavior":
                        result.append("prefer_throwing_properties")
                    elif "location" in section or "behavior" in section:
                        result.append(None)
                    else:
                        result.append(None)
                elif section == "tab_width" or section == "indent_size":
                    result.append(4)
                elif section == "insert_final_newline":
                    result.append(True)
                else:
                    result.append(None)

            return result

        def handle_work_done_progress_create(params: dict) -> None:
            return

        def handle_register_capability(params: dict) -> None:
            return

        def handle_project_needs_restore(params: dict) -> None:
            return

        def handle_workspace_indexing_complete(params: dict) -> None:
            indexing_complete.set()

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", handle_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("workspace/projectInitializationComplete", handle_workspace_indexing_complete)
        self.server.on_request("workspace/configuration", handle_workspace_configuration)
        self.server.on_request("window/workDoneProgress/create", handle_work_done_progress_create)
        self.server.on_request("client/registerCapability", handle_register_capability)
        self.server.on_request("workspace/_roslyn_projectNeedsRestore", handle_project_needs_restore)

        log.info("Starting Microsoft.CodeAnalysis.LanguageServer process for VB.NET")

        try:
            self.server.start()
        except Exception as e:
            log.info(f"Failed to start language server process: {e}", logging.ERROR)
            raise SolidLSPException(f"Failed to start VB.NET language server: {e}")

        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request to language server")
        try:
            init_response = self.server.send.initialize(initialize_params)
            log.info(f"Received initialize response: {init_response}")
        except Exception as e:
            raise SolidLSPException(f"Failed to initialize VB.NET language server for {self.repository_root_path}: {e}") from e

        self._force_pull_diagnostics(init_response)

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

        self.server.notify.initialized({})

        self._open_solution_and_projects()

        log.info(
            "Microsoft.CodeAnalysis.LanguageServer (VB.NET) initialized and ready\n"
            "Waiting for language server to index project files...\n"
            "This may take a while for large projects"
        )

        if indexing_complete.wait(30):
            log.info("Indexing complete")
        else:
            log.warning("Timeout waiting for indexing to complete, proceeding anyway")

    def _force_pull_diagnostics(self, init_response: dict | InitializeResult) -> None:
        capabilities = init_response.get("capabilities", {})
        diagnostic_provider: Any = capabilities.get("diagnosticProvider", {})

        if isinstance(diagnostic_provider, dict):
            diagnostic_provider.update(
                {
                    "interFileDependencies": True,
                    "workDoneProgress": True,
                    "workspaceDiagnostics": True,
                }
            )
            log.debug("Applied diagnostic capabilities hack for better VB.NET diagnostics")

    def _open_solution_and_projects(self) -> None:
        solution_file = None
        for filename in breadth_first_file_scan(self.repository_root_path):
            if filename.endswith((".sln", ".slnx")):
                solution_file = filename
                break

        if solution_file:
            solution_uri = PathUtils.path_to_uri(solution_file)
            self.server.notify.send_notification("solution/open", {"solution": solution_uri})
            log.debug(f"Opened solution file: {solution_file}")

        project_files = []
        for filename in breadth_first_file_scan(self.repository_root_path):
            if filename.endswith((".vbproj", ".csproj")):
                project_files.append(filename)

        if project_files:
            project_uris = [PathUtils.path_to_uri(project_file) for project_file in project_files]
            self.server.notify.send_notification("project/open", {"projects": project_uris})
            log.debug(f"Opened project files: {project_files}")

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 2
