"""
Provides C# specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C#.
"""

import json
import logging
import os
import pathlib
import threading
from collections.abc import Iterable

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import DotnetVersion, FileUtils, PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


def breadth_first_file_scan(root: str) -> Iterable[str]:
    """
    This function was obtained from https://stackoverflow.com/questions/49654234/is-there-a-breadth-first-search-option-available-in-os-walk-or-equivalent-py
    It traverses the directory tree in breadth first order.
    """
    dirs = [root]
    # while we has dirs to scan
    while dirs:
        next_dirs = []
        for parent in dirs:
            # scan each dir
            for f in os.listdir(parent):
                # if there is a dir, then save for next ittr
                # if it  is a file then yield it (we'll return later)
                ff = os.path.join(parent, f)
                if os.path.isdir(ff):
                    next_dirs.append(ff)
                else:
                    yield ff

        # once we've done all the current dirs then
        # we set up the next itter as the child dirs
        # from the current itter.
        dirs = next_dirs


def find_least_depth_sln_file(root_dir: str) -> str | None:
    for filename in breadth_first_file_scan(root_dir):
        if filename.endswith(".sln"):
            return filename
    return None


class OmniSharp(SolidLanguageServer):
    """
    Provides C# specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C#.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an OmniSharp instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        omnisharp_executable_path, dll_path = self._setup_runtime_dependencies(config, solidlsp_settings)

        slnfilename = find_least_depth_sln_file(repository_root_path)
        if slnfilename is None:
            log.error("No *.sln file found in repository")
            raise SolidLSPException("No SLN file found in repository")

        cmd = " ".join(
            [
                omnisharp_executable_path,
                "-lsp",
                "--encoding",
                "ascii",
                "-z",
                "-s",
                f'"{slnfilename}"',
                "--hostPID",
                str(os.getpid()),
                "DotNet:enablePackageRestore=false",
                "--loglevel",
                "trace",
                "--plugin",
                dll_path,
                "FileOptions:SystemExcludeSearchPatterns:0=**/.git",
                "FileOptions:SystemExcludeSearchPatterns:1=**/.svn",
                "FileOptions:SystemExcludeSearchPatterns:2=**/.hg",
                "FileOptions:SystemExcludeSearchPatterns:3=**/CVS",
                "FileOptions:SystemExcludeSearchPatterns:4=**/.DS_Store",
                "FileOptions:SystemExcludeSearchPatterns:5=**/Thumbs.db",
                "RoslynExtensionsOptions:EnableAnalyzersSupport=true",
                "FormattingOptions:EnableEditorConfigSupport=true",
                "RoslynExtensionsOptions:EnableImportCompletion=true",
                "Sdk:IncludePrereleases=true",
                "RoslynExtensionsOptions:AnalyzeOpenDocumentsOnly=true",
                "formattingOptions:useTabs=false",
                "formattingOptions:tabSize=4",
                "formattingOptions:indentationSize=4",
            ]
        )
        super().__init__(config, repository_root_path, ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path), "csharp", solidlsp_settings)

        self.server_ready = threading.Event()
        self.definition_available = threading.Event()
        self.references_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["bin", "obj"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Omnisharp Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "omnisharp", "initialize_params.json"), encoding="utf-8") as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        assert d["rootPath"] == "$rootPath"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "$rootUri"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["uri"] == "$uri"
        d["workspaceFolders"][0]["uri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["name"] == "$name"
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> tuple[str, str]:
        """
        Setup runtime dependencies for OmniSharp.
        """
        platform_id = PlatformUtils.get_platform_id()
        dotnet_version = PlatformUtils.get_dotnet_version()

        with open(os.path.join(os.path.dirname(__file__), "omnisharp", "runtime_dependencies.json"), encoding="utf-8") as f:
            d = json.load(f)
            del d["_description"]

        assert platform_id in [
            PlatformId.LINUX_x64,
            PlatformId.WIN_x64,
        ], f"Only linux-x64 and win-x64 platform is supported at the moment but got {platform_id=}"
        assert dotnet_version in [
            DotnetVersion.V6,
            DotnetVersion.V7,
            DotnetVersion.V8,
            DotnetVersion.V9,
        ], f"Only dotnet version 6-9 are supported at the moment but got {dotnet_version=}"

        # TODO: Do away with this assumption
        # Currently, runtime binaries are not available for .Net 7 and .Net 8. Hence, we assume .Net 6 runtime binaries to be compatible with .Net 7, .Net 8
        if dotnet_version in [DotnetVersion.V7, DotnetVersion.V8, DotnetVersion.V9]:
            dotnet_version = DotnetVersion.V6

        runtime_dependencies = d["runtimeDependencies"]
        runtime_dependencies = [dependency for dependency in runtime_dependencies if dependency["platformId"] == platform_id.value]
        runtime_dependencies = [
            dependency
            for dependency in runtime_dependencies
            if "dotnet_version" not in dependency or dependency["dotnet_version"] == dotnet_version.value
        ]
        assert len(runtime_dependencies) == 2
        runtime_dependencies = {
            runtime_dependencies[0]["id"]: runtime_dependencies[0],
            runtime_dependencies[1]["id"]: runtime_dependencies[1],
        }

        assert "OmniSharp" in runtime_dependencies
        assert "RazorOmnisharp" in runtime_dependencies

        omnisharp_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "OmniSharp")
        if not os.path.exists(omnisharp_ls_dir):
            os.makedirs(omnisharp_ls_dir)
            FileUtils.download_and_extract_archive(runtime_dependencies["OmniSharp"]["url"], omnisharp_ls_dir, "zip")
        omnisharp_executable_path = os.path.join(omnisharp_ls_dir, runtime_dependencies["OmniSharp"]["binaryName"])
        assert os.path.exists(omnisharp_executable_path)
        os.chmod(omnisharp_executable_path, 0o755)

        razor_omnisharp_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "RazorOmnisharp")
        if not os.path.exists(razor_omnisharp_ls_dir):
            os.makedirs(razor_omnisharp_ls_dir)
            FileUtils.download_and_extract_archive(runtime_dependencies["RazorOmnisharp"]["url"], razor_omnisharp_ls_dir, "zip")
        razor_omnisharp_dll_path = os.path.join(razor_omnisharp_ls_dir, runtime_dependencies["RazorOmnisharp"]["dll_path"])
        assert os.path.exists(razor_omnisharp_dll_path)

        return omnisharp_executable_path, razor_omnisharp_dll_path

    def _start_server(self) -> None:
        """
        Starts the Omnisharp Language Server
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "textDocument/definition":
                    self.definition_available.set()
                if registration["method"] == "textDocument/references":
                    self.references_available.set()
                if registration["method"] == "textDocument/completion":
                    self.completions_available.set()

        def lang_status_handler(params: dict) -> None:
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            # if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
            #     self.service_ready_event.set()
            pass

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def check_experimental_status(params: dict) -> None:
            if params["quiescent"] is True:
                self.server_ready.set()

        def workspace_configuration_handler(params: dict) -> list[dict]:
            # TODO: We do not know the appropriate way to handle this request. Should ideally contact the OmniSharp dev team
            return [
                {
                    "RoslynExtensionsOptions": {
                        "EnableDecompilationSupport": False,
                        "EnableAnalyzersSupport": True,
                        "EnableImportCompletion": True,
                        "EnableAsyncCompletion": False,
                        "DocumentAnalysisTimeoutMs": 30000,
                        "DiagnosticWorkersThreadCount": 18,
                        "AnalyzeOpenDocumentsOnly": True,
                        "InlayHintsOptions": {
                            "EnableForParameters": False,
                            "ForLiteralParameters": False,
                            "ForIndexerParameters": False,
                            "ForObjectCreationParameters": False,
                            "ForOtherParameters": False,
                            "SuppressForParametersThatDifferOnlyBySuffix": False,
                            "SuppressForParametersThatMatchMethodIntent": False,
                            "SuppressForParametersThatMatchArgumentName": False,
                            "EnableForTypes": False,
                            "ForImplicitVariableTypes": False,
                            "ForLambdaParameterTypes": False,
                            "ForImplicitObjectCreation": False,
                        },
                        "LocationPaths": None,
                    },
                    "FormattingOptions": {
                        "OrganizeImports": False,
                        "EnableEditorConfigSupport": True,
                        "NewLine": "\n",
                        "UseTabs": False,
                        "TabSize": 4,
                        "IndentationSize": 4,
                        "SpacingAfterMethodDeclarationName": False,
                        "SeparateImportDirectiveGroups": False,
                        "SpaceWithinMethodDeclarationParenthesis": False,
                        "SpaceBetweenEmptyMethodDeclarationParentheses": False,
                        "SpaceAfterMethodCallName": False,
                        "SpaceWithinMethodCallParentheses": False,
                        "SpaceBetweenEmptyMethodCallParentheses": False,
                        "SpaceAfterControlFlowStatementKeyword": True,
                        "SpaceWithinExpressionParentheses": False,
                        "SpaceWithinCastParentheses": False,
                        "SpaceWithinOtherParentheses": False,
                        "SpaceAfterCast": False,
                        "SpaceBeforeOpenSquareBracket": False,
                        "SpaceBetweenEmptySquareBrackets": False,
                        "SpaceWithinSquareBrackets": False,
                        "SpaceAfterColonInBaseTypeDeclaration": True,
                        "SpaceAfterComma": True,
                        "SpaceAfterDot": False,
                        "SpaceAfterSemicolonsInForStatement": True,
                        "SpaceBeforeColonInBaseTypeDeclaration": True,
                        "SpaceBeforeComma": False,
                        "SpaceBeforeDot": False,
                        "SpaceBeforeSemicolonsInForStatement": False,
                        "SpacingAroundBinaryOperator": "single",
                        "IndentBraces": False,
                        "IndentBlock": True,
                        "IndentSwitchSection": True,
                        "IndentSwitchCaseSection": True,
                        "IndentSwitchCaseSectionWhenBlock": True,
                        "LabelPositioning": "oneLess",
                        "WrappingPreserveSingleLine": True,
                        "WrappingKeepStatementsOnSingleLine": True,
                        "NewLinesForBracesInTypes": True,
                        "NewLinesForBracesInMethods": True,
                        "NewLinesForBracesInProperties": True,
                        "NewLinesForBracesInAccessors": True,
                        "NewLinesForBracesInAnonymousMethods": True,
                        "NewLinesForBracesInControlBlocks": True,
                        "NewLinesForBracesInAnonymousTypes": True,
                        "NewLinesForBracesInObjectCollectionArrayInitializers": True,
                        "NewLinesForBracesInLambdaExpressionBody": True,
                        "NewLineForElse": True,
                        "NewLineForCatch": True,
                        "NewLineForFinally": True,
                        "NewLineForMembersInObjectInit": True,
                        "NewLineForMembersInAnonymousTypes": True,
                        "NewLineForClausesInQuery": True,
                    },
                    "FileOptions": {
                        "SystemExcludeSearchPatterns": [
                            "**/node_modules/**/*",
                            "**/bin/**/*",
                            "**/obj/**/*",
                            "**/.git/**/*",
                            "**/.git",
                            "**/.svn",
                            "**/.hg",
                            "**/CVS",
                            "**/.DS_Store",
                            "**/Thumbs.db",
                        ],
                        "ExcludeSearchPatterns": [],
                    },
                    "RenameOptions": {
                        "RenameOverloads": False,
                        "RenameInStrings": False,
                        "RenameInComments": False,
                    },
                    "ImplementTypeOptions": {
                        "InsertionBehavior": 0,
                        "PropertyGenerationBehavior": 0,
                    },
                    "DotNetCliOptions": {"LocationPaths": None},
                    "Plugins": {"LocationPaths": None},
                }
            ]

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", self._handle_publish_diagnostics)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)

        log.info("Starting OmniSharp server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        self.server.notify.initialized({})
        with open(os.path.join(os.path.dirname(__file__), "omnisharp", "workspace_did_change_configuration.json"), encoding="utf-8") as f:
            self.server.notify.workspace_did_change_configuration({"settings": json.load(f)})
        assert "capabilities" in init_response
        if "definitionProvider" in init_response["capabilities"] and init_response["capabilities"]["definitionProvider"]:
            self.definition_available.set()
        if "referencesProvider" in init_response["capabilities"] and init_response["capabilities"]["referencesProvider"]:
            self.references_available.set()

        self.definition_available.wait()
        self.references_available.wait()
