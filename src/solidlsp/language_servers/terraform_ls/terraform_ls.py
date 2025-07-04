import json
import logging
import os
import pathlib
import subprocess
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


class TerraformLS(SolidLanguageServer):
    """
    Provides Terraform specific instantiation of the LanguageServer class using terraform-ls.
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Terraform projects, we should ignore:
        # - .terraform: Terraform working directory with providers and modules
        # - terraform.tfstate.d: Terraform workspace state directories
        # - .git: Version control
        # - node_modules: If the project has JavaScript components
        return super().is_ignored_dirname(dirname) or dirname in [".terraform", "terraform.tfstate.d", "node_modules"]

    @staticmethod
    def _get_terraform_version():
        """Get the installed Terraform version or None if not found."""
        import os
        import shutil
        
        print("DEBUG: Starting terraform version detection...")
        
        # 1. Try to find terraform using shutil.which (standard Python way)
        terraform_cmd = shutil.which("terraform")
        if terraform_cmd:
            print(f"DEBUG: Found terraform via shutil.which: {terraform_cmd}")
        else:
            print("DEBUG: terraform not found via shutil.which")
        
        # 2. Fallback to TERRAFORM_CLI_PATH (set by hashicorp/setup-terraform action)
        if not terraform_cmd:
            terraform_cli_path = os.environ.get('TERRAFORM_CLI_PATH')
            if terraform_cli_path:
                print(f"DEBUG: Trying TERRAFORM_CLI_PATH: {terraform_cli_path}")
                terraform_exe = os.path.join(terraform_cli_path, "terraform.exe")
                if os.path.exists(terraform_exe):
                    terraform_cmd = terraform_exe
                    print(f"DEBUG: Found terraform via TERRAFORM_CLI_PATH: {terraform_cmd}")
                else:
                    print(f"DEBUG: terraform.exe not found at {terraform_exe}")
            else:
                print("DEBUG: TERRAFORM_CLI_PATH not set")
        
        # 3. Try to run the terraform command if found
        if terraform_cmd:
            try:
                print(f"DEBUG: Attempting to run: {terraform_cmd} version (with 15s timeout)")
                result = subprocess.run(
                    [terraform_cmd, "version"], 
                    capture_output=True, 
                    text=True, 
                    check=False, 
                    timeout=15  # CRITICAL: 15 second timeout to prevent hangs
                )
                if result.returncode == 0:
                    print(f"DEBUG: terraform version command succeeded")
                    return result.stdout.strip()
                else:
                    print(f"DEBUG: terraform version command failed with return code {result.returncode}")
                    print(f"DEBUG: stderr: {result.stderr}")
            except subprocess.TimeoutExpired:
                print("ERROR: terraform version command timed out after 15 seconds")
            except (FileNotFoundError, OSError) as e:
                print(f"DEBUG: Failed to run terraform command: {e}")
        else:
            print("DEBUG: No terraform executable found")
        
        return None

    @staticmethod
    def _get_terraform_ls_version():
        """Get the installed terraform-ls version or None if not found."""
        import shutil
        
        print("DEBUG: Starting terraform-ls version detection...")
        
        # Try to find terraform-ls using shutil.which (standard Python way)
        terraform_ls_cmd = shutil.which("terraform-ls")
        
        if terraform_ls_cmd:
            print(f"DEBUG: Found terraform-ls via shutil.which: {terraform_ls_cmd}")
            try:
                print(f"DEBUG: Attempting to run: {terraform_ls_cmd} version (with 15s timeout)")
                result = subprocess.run(
                    [terraform_ls_cmd, "version"], 
                    capture_output=True, 
                    text=True, 
                    check=False, 
                    timeout=15  # CRITICAL: 15 second timeout to prevent hangs
                )
                if result.returncode == 0:
                    print(f"DEBUG: terraform-ls version command succeeded")
                    return result.stdout.strip()
                else:
                    print(f"DEBUG: terraform-ls version command failed with return code {result.returncode}")
                    print(f"DEBUG: stderr: {result.stderr}")
            except subprocess.TimeoutExpired:
                print("ERROR: terraform-ls version command timed out after 15 seconds")
            except (FileNotFoundError, OSError) as e:
                print(f"DEBUG: Failed to run terraform-ls command: {e}")
        else:
            print("DEBUG: terraform-ls not found via shutil.which")
        
        return None

    @classmethod
    def setup_runtime_dependency(cls):
        """
        Check if required Terraform runtime dependencies are available.
        Raises RuntimeError with helpful message if dependencies are missing.
        """
        terraform_version = cls._get_terraform_version()
        if not terraform_version:
            raise RuntimeError(
                "Terraform is not installed. Please install Terraform from https://www.terraform.io/downloads and make sure it is added to your PATH."
            )

        terraform_ls_version = cls._get_terraform_ls_version()
        if not terraform_ls_version:
            raise RuntimeError(
                "Found a Terraform version but terraform-ls is not installed.\n"
                "Please install terraform-ls from https://github.com/hashicorp/terraform-ls/releases\n\n"
                "After installation, make sure it is added to your PATH."
            )

        return True

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        self.setup_runtime_dependency()

        # Find the correct terraform-ls executable using the same logic as version check
        terraform_ls_cmd = self._find_terraform_ls_executable()

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=terraform_ls_cmd, cwd=repository_root_path),
            "terraform",
        )
        self.server_ready = threading.Event()
        self.request_id = 0

    @staticmethod
    def _find_terraform_ls_executable():
        """Find the terraform-ls executable that actually works."""
        import shutil
        
        print("DEBUG: Finding terraform-ls executable for ProcessLaunchInfo...")
        
        # Try to find terraform-ls using shutil.which (standard Python way)
        terraform_ls_cmd = shutil.which("terraform-ls")
        
        # If found, verify it works by running version command
        if terraform_ls_cmd:
            print(f"DEBUG: Found terraform-ls candidate: {terraform_ls_cmd}")
            try:
                print(f"DEBUG: Verifying terraform-ls works (with 15s timeout)")
                result = subprocess.run(
                    [terraform_ls_cmd, "version"], 
                    capture_output=True, 
                    text=True, 
                    check=False, 
                    timeout=15  # CRITICAL: 15 second timeout to prevent hangs
                )
                if result.returncode == 0:
                    print(f"DEBUG: terraform-ls verification succeeded, using: {terraform_ls_cmd}")
                    return terraform_ls_cmd
                else:
                    print(f"DEBUG: terraform-ls verification failed with return code {result.returncode}")
            except subprocess.TimeoutExpired:
                print("ERROR: terraform-ls verification timed out after 15 seconds")
            except (FileNotFoundError, OSError) as e:
                print(f"DEBUG: Failed to verify terraform-ls: {e}")
        else:
            print("DEBUG: terraform-ls not found via shutil.which")
        
        # Fallback to default if nothing works (will likely fail later, but better than crashing here)
        print("DEBUG: Using fallback terraform-ls command")
        return "terraform-ls"

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Terraform Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), encoding="utf-8") as f:
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

    def _start_server(self):
        """Start terraform-ls server process"""

        def register_capability_handler(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting terraform-ls server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        # terraform-ls server is typically ready immediately after initialization
        self.server_ready.set()
        self.server_ready.wait()
