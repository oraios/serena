import logging
import os
import shutil
from typing import cast

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_utils import PathUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

TERRAFORM_LS_ALLOWED_HOSTS = ("releases.hashicorp.com",)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_TERRAFORM_LS_VERSION = "0.36.5"
INITIAL_TERRAFORM_LS_SHA256_BY_PLATFORM = {
    "osx-arm64": "fee8743aa71fe2d8b0b9b91283b844cfa57d58457306a62e53a8f38d143cec8c",
    "osx-x64": "17c5c480f8eec7e528292565f1c05d5097a41edf7ef8ee2a9f3a18d288a1415a",
    "linux-arm64": "724f45029f32d02d88b1952c7d1526c59fc8cd5dae49e31b9fed676a83f6cae7",
    "linux-x64": "37e645cc54fd03e863157e2a3e773e7a5ff1d6cb3d045e4c20860cac1f550a44",
    "win-x64": "a9223462cac9e1c0e6ba33043fbf9fb4483609b6970b5681a6306b04366698ec",
}
DEFAULT_TERRAFORM_LS_VERSION = "0.36.5"
DEFAULT_TERRAFORM_LS_SHA256_BY_PLATFORM = {
    "osx-arm64": "fee8743aa71fe2d8b0b9b91283b844cfa57d58457306a62e53a8f38d143cec8c",
    "osx-x64": "17c5c480f8eec7e528292565f1c05d5097a41edf7ef8ee2a9f3a18d288a1415a",
    "linux-arm64": "724f45029f32d02d88b1952c7d1526c59fc8cd5dae49e31b9fed676a83f6cae7",
    "linux-x64": "37e645cc54fd03e863157e2a3e773e7a5ff1d6cb3d045e4c20860cac1f550a44",
    "win-x64": "a9223462cac9e1c0e6ba33043fbf9fb4483609b6970b5681a6306b04366698ec",
}


def _terraform_ls_sha(version: str, platform_key: str) -> str | None:
    if version == INITIAL_TERRAFORM_LS_VERSION:
        return INITIAL_TERRAFORM_LS_SHA256_BY_PLATFORM[platform_key]
    if version == DEFAULT_TERRAFORM_LS_VERSION:
        return DEFAULT_TERRAFORM_LS_SHA256_BY_PLATFORM[platform_key]
    return None


class TerraformLS(SolidLanguageServer):
    """
    Provides Terraform specific instantiation of the LanguageServer class using terraform-ls.

    You can pass the following entries in ``ls_specific_settings["terraform"]``:
        - terraform_ls_version: Override the pinned terraform-ls version downloaded
          by Serena (default: the bundled Serena version).
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [".terraform", "terraform.tfstate.d"]

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """Classify terraform-ls stderr output to avoid false-positive errors."""
        line_lower = line.lower()

        # File discovery messages that are not actual errors
        if any(
            [
                "discover.go:" in line_lower,
                "walker.go:" in line_lower,
                "walking of {file://" in line_lower,
                "bus: -> discover" in line_lower,
            ]
        ):
            return logging.DEBUG

        # Known informational messages from terraform-ls that contain "error" but aren't errors
        # Note: pattern match is flexible to handle file paths between keywords
        if any(
            [
                "loading module metadata returned error:" in line_lower and "state not changed" in line_lower,
                "incoming notification for" in line_lower,
            ]
        ):
            return logging.DEBUG

        return SolidLanguageServer._determine_log_level(line)

    @staticmethod
    def _ensure_tf_command_available() -> None:
        log.debug("Starting terraform version detection...")

        # 1. Try to find terraform using shutil.which
        terraform_cmd = shutil.which("terraform")
        if terraform_cmd is not None:
            log.debug(f"Found terraform via shutil.which: {terraform_cmd}")
            return

        # TODO: is this needed?
        # 2. Fallback to TERRAFORM_CLI_PATH (set by hashicorp/setup-terraform action)
        if not terraform_cmd:
            terraform_cli_path = os.environ.get("TERRAFORM_CLI_PATH")
            if terraform_cli_path:
                log.debug(f"Trying TERRAFORM_CLI_PATH: {terraform_cli_path}")
                # TODO: use binary name from runtime dependencies if we keep this code
                if os.name == "nt":
                    terraform_binary = os.path.join(terraform_cli_path, "terraform.exe")
                else:
                    terraform_binary = os.path.join(terraform_cli_path, "terraform")
                if os.path.exists(terraform_binary):
                    terraform_cmd = terraform_binary
                    log.debug(f"Found terraform via TERRAFORM_CLI_PATH: {terraform_cmd}")
                    return

        raise RuntimeError(
            "Terraform executable not found, please ensure Terraform is installed."
            "See https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli for instructions."
        )

    @classmethod
    def _setup_runtime_dependencies(cls, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for terraform-ls.
        Downloads and installs terraform-ls if not already present.
        """
        cls._ensure_tf_command_available()
        terraform_settings = solidlsp_settings.get_ls_specific_settings(Language.TERRAFORM)
        terraform_ls_version = terraform_settings.get("terraform_ls_version", DEFAULT_TERRAFORM_LS_VERSION)
        platform_id = PlatformUtils.get_platform_id()
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="TerraformLS",
                    description="terraform-ls for macOS (ARM64)",
                    url=f"https://releases.hashicorp.com/terraform-ls/{terraform_ls_version}/terraform-ls_{terraform_ls_version}_darwin_arm64.zip",
                    platform_id="osx-arm64",
                    archive_type="zip",
                    binary_name="terraform-ls",
                    sha256=_terraform_ls_sha(terraform_ls_version, "osx-arm64"),
                    allowed_hosts=TERRAFORM_LS_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="TerraformLS",
                    description="terraform-ls for macOS (x64)",
                    url=f"https://releases.hashicorp.com/terraform-ls/{terraform_ls_version}/terraform-ls_{terraform_ls_version}_darwin_amd64.zip",
                    platform_id="osx-x64",
                    archive_type="zip",
                    binary_name="terraform-ls",
                    sha256=_terraform_ls_sha(terraform_ls_version, "osx-x64"),
                    allowed_hosts=TERRAFORM_LS_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="TerraformLS",
                    description="terraform-ls for Linux (ARM64)",
                    url=f"https://releases.hashicorp.com/terraform-ls/{terraform_ls_version}/terraform-ls_{terraform_ls_version}_linux_arm64.zip",
                    platform_id="linux-arm64",
                    archive_type="zip",
                    binary_name="terraform-ls",
                    sha256=_terraform_ls_sha(terraform_ls_version, "linux-arm64"),
                    allowed_hosts=TERRAFORM_LS_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="TerraformLS",
                    description="terraform-ls for Linux (x64)",
                    url=f"https://releases.hashicorp.com/terraform-ls/{terraform_ls_version}/terraform-ls_{terraform_ls_version}_linux_amd64.zip",
                    platform_id="linux-x64",
                    archive_type="zip",
                    binary_name="terraform-ls",
                    sha256=_terraform_ls_sha(terraform_ls_version, "linux-x64"),
                    allowed_hosts=TERRAFORM_LS_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="TerraformLS",
                    description="terraform-ls for Windows (x64)",
                    url=f"https://releases.hashicorp.com/terraform-ls/{terraform_ls_version}/terraform-ls_{terraform_ls_version}_windows_amd64.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="terraform-ls.exe",
                    sha256=_terraform_ls_sha(terraform_ls_version, "win-x64"),
                    allowed_hosts=TERRAFORM_LS_ALLOWED_HOSTS,
                ),
            ]
        )
        dependency = deps.get_single_dep_for_current_platform()

        # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
        install_dir = (
            cls.ls_resources_dir(solidlsp_settings)
            if terraform_ls_version == INITIAL_TERRAFORM_LS_VERSION
            else os.path.join(cls.ls_resources_dir(solidlsp_settings), f"terraform-ls-{terraform_ls_version}")
        )
        terraform_ls_executable_path = deps.binary_path(install_dir)
        if not os.path.exists(terraform_ls_executable_path):
            log.info(f"Downloading terraform-ls from {dependency.url}")
            deps.install(install_dir)

        assert os.path.exists(terraform_ls_executable_path), f"terraform-ls executable not found at {terraform_ls_executable_path}"

        # Make the executable file executable on Unix-like systems
        if platform_id.value != "win-x64":
            os.chmod(terraform_ls_executable_path, 0o755)

        return terraform_ls_executable_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a TerraformLS instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        terraform_ls_executable_path = self._setup_runtime_dependencies(solidlsp_settings)

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{terraform_ls_executable_path} serve", cwd=repository_root_path),
            "terraform",
            solidlsp_settings,
        )
        self.request_id = 0

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Terraform Language Server.
        """
        root_uri = PathUtils.path_to_uri(repository_absolute_path)
        result = {
            "processId": os.getpid(),
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "workspace": {"workspaceFolders": True, "didChangeConfiguration": {"dynamicRegistration": True}},
            },
            "workspaceFolders": [
                {
                    "name": os.path.basename(repository_absolute_path),
                    "uri": root_uri,
                }
            ],
        }
        return cast(InitializeParams, result)

    def _start_server(self) -> None:
        """Start terraform-ls server process"""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting terraform-ls server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # terraform-ls server is typically ready immediately after initialization
