"""
Provides Ruby specific instantiation of the LanguageServer class using Solargraph.
Contains various configurations and settings specific to Ruby.
"""

import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class Solargraph(SolidLanguageServer):
    """
    Provides Ruby specific instantiation of the LanguageServer class using Solargraph.
    Contains various configurations and settings specific to Ruby.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a Solargraph instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        solargraph_executable_path = self._setup_runtime_dependencies(logger, config, repository_root_path)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{solargraph_executable_path} stdio", cwd=repository_root_path),
            "ruby",
            solidlsp_settings,
        )
        # Override internal language enum for file matching (excludes .erb files)
        # while keeping LSP languageId as "ruby" for protocol compliance
        from solidlsp.ls_config import Language

        self.language = Language.RUBY_SOLARGRAPH
        self.analysis_complete = threading.Event()
        self.service_ready_event = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()

        # Set timeout for Solargraph requests - Bundler environments may need more time
        self.set_request_timeout(120.0)  # 120 seconds for initialization and requests

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        ruby_ignored_dirs = [
            "vendor",  # Ruby vendor directory
            ".bundle",  # Bundler cache
            "tmp",  # Temporary files
            "log",  # Log files
            "coverage",  # Test coverage reports
            ".yardoc",  # YARD documentation cache
            "doc",  # Generated documentation
            "node_modules",  # Node modules (for Rails with JS)
            "storage",  # Active Storage files (Rails)
        ]
        return super().is_ignored_dirname(dirname) or dirname in ruby_ignored_dirs

    @staticmethod
    def _setup_runtime_dependencies(logger: LanguageServerLogger, config: LanguageServerConfig, repository_root_path: str) -> str:
        """
        Setup runtime dependencies for Solargraph and return the command to start the server.
        """
        # Check if Ruby is installed
        try:
            result = subprocess.run(["ruby", "--version"], check=True, capture_output=True, cwd=repository_root_path, text=True)
            ruby_version = result.stdout.strip()
            logger.log(f"Ruby version: {ruby_version}", logging.INFO)

            # Extract version number for compatibility checks
            version_match = re.search(r"ruby (\d+)\.(\d+)\.(\d+)", ruby_version)
            if version_match:
                major, minor, patch = map(int, version_match.groups())
                if major < 2 or (major == 2 and minor < 6):
                    logger.log(f"Warning: Ruby {major}.{minor}.{patch} detected. Solargraph works best with Ruby 2.6+", logging.WARNING)

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else "Unknown error"
            raise RuntimeError(
                f"Error checking Ruby installation: {error_msg}. Please ensure Ruby is properly installed and in PATH."
            ) from e
        except FileNotFoundError as e:
            raise RuntimeError(
                "Ruby is not installed or not found in PATH. Please install Ruby using one of these methods:\n"
                "  - Using rbenv: rbenv install 3.0.0 && rbenv global 3.0.0\n"
                "  - Using RVM: rvm install 3.0.0 && rvm use 3.0.0 --default\n"
                "  - Using asdf: asdf install ruby 3.0.0 && asdf global ruby 3.0.0\n"
                "  - System package manager (brew install ruby, apt install ruby, etc.)"
            ) from e

        # Helper function for Windows-compatible executable search
        def find_executable_with_extensions(executable_name: str) -> str | None:
            """Find executable with Windows-specific extensions if on Windows."""
            import platform

            if platform.system() == "Windows":
                for ext in [".bat", ".cmd", ".exe"]:
                    path = shutil.which(f"{executable_name}{ext}")
                    if path:
                        return path
                return shutil.which(executable_name)
            else:
                return shutil.which(executable_name)

        # Check for Bundler project (Gemfile exists)
        gemfile_path = os.path.join(repository_root_path, "Gemfile")
        gemfile_lock_path = os.path.join(repository_root_path, "Gemfile.lock")
        is_bundler_project = os.path.exists(gemfile_path)

        if is_bundler_project:
            logger.log("Detected Bundler project (Gemfile found)", logging.INFO)

            # Check if bundle command is available
            bundle_path = find_executable_with_extensions("bundle")
            if not bundle_path:
                # Try common bundle executables
                for bundle_cmd in ["bin/bundle", "bundle"]:
                    if bundle_cmd.startswith("bin/"):
                        bundle_full_path = os.path.join(repository_root_path, bundle_cmd)
                    else:
                        bundle_full_path = find_executable_with_extensions(bundle_cmd)
                    if bundle_full_path and os.path.exists(bundle_full_path):
                        bundle_path = bundle_full_path if bundle_cmd.startswith("bin/") else bundle_cmd
                        break

            if not bundle_path:
                raise RuntimeError(
                    "Bundler project detected but 'bundle' command not found. Please install Bundler:\n"
                    "  - gem install bundler\n"
                    "  - Or use your Ruby version manager's bundler installation\n"
                    "  - Ensure the bundle command is in your PATH"
                )

            # Check if solargraph is in Gemfile.lock
            solargraph_in_bundle = False
            if os.path.exists(gemfile_lock_path):
                try:
                    with open(gemfile_lock_path) as f:
                        content = f.read()
                        solargraph_in_bundle = "solargraph" in content.lower()
                except Exception as e:
                    logger.log(f"Warning: Could not read Gemfile.lock: {e}", logging.WARNING)

            if solargraph_in_bundle:
                logger.log("Found solargraph in Gemfile.lock", logging.INFO)
                return f"{bundle_path} exec solargraph"
            else:
                logger.log(
                    "solargraph not found in Gemfile.lock. Please add 'gem \"solargraph\"' to your Gemfile and run 'bundle install'",
                    logging.WARNING,
                )
                # Fall through to global installation check

        # Check if solargraph is installed globally
        # First, try to find solargraph in PATH (includes asdf shims) with Windows support
        solargraph_path = find_executable_with_extensions("solargraph")
        if solargraph_path:
            logger.log(f"Found solargraph at: {solargraph_path}", logging.INFO)
            return solargraph_path

        # Fallback to gem exec (for non-Bundler projects or when global solargraph not found)
        if not is_bundler_project:
            runtime_dependencies = [
                {
                    "url": "https://rubygems.org/downloads/solargraph-0.51.1.gem",
                    "installCommand": "gem install solargraph -v 0.51.1",
                    "binaryName": "solargraph",
                    "archiveType": "gem",
                }
            ]

            dependency = runtime_dependencies[0]
            try:
                result = subprocess.run(
                    ["gem", "list", "^solargraph$", "-i"], check=False, capture_output=True, text=True, cwd=repository_root_path
                )
                if result.stdout.strip() == "false":
                    logger.log("Installing Solargraph...", logging.INFO)
                    subprocess.run(dependency["installCommand"].split(), check=True, capture_output=True, cwd=repository_root_path)

                return "gem exec solargraph"
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                raise RuntimeError(
                    f"Failed to check or install Solargraph: {error_msg}\nPlease try installing manually: gem install solargraph"
                ) from e
        else:
            raise RuntimeError(
                "This appears to be a Bundler project, but solargraph is not available. "
                "Please add 'gem \"solargraph\"' to your Gemfile and run 'bundle install'."
            )

    @staticmethod
    def _detect_rails_project(repository_root_path: str) -> bool:
        """
        Detect if this is a Rails project by checking for Rails-specific files.
        """
        rails_indicators = [
            "config/application.rb",
            "config/environment.rb",
            "app/controllers/application_controller.rb",
            "Rakefile",
        ]

        for indicator in rails_indicators:
            if os.path.exists(os.path.join(repository_root_path, indicator)):
                return True

        # Check for Rails in Gemfile
        gemfile_path = os.path.join(repository_root_path, "Gemfile")
        if os.path.exists(gemfile_path):
            try:
                with open(gemfile_path) as f:
                    content = f.read().lower()
                    if "gem 'rails'" in content or 'gem "rails"' in content:
                        return True
            except Exception:
                pass

        return False

    @staticmethod
    def _get_ruby_exclude_patterns(repository_root_path: str) -> list[str]:
        """
        Get Ruby and Rails-specific exclude patterns for better performance.
        """
        base_patterns = [
            "**/vendor/**",  # Ruby vendor directory (similar to node_modules)
            "**/.bundle/**",  # Bundler cache
            "**/tmp/**",  # Temporary files
            "**/log/**",  # Log files
            "**/coverage/**",  # Test coverage reports
            "**/.yardoc/**",  # YARD documentation cache
            "**/doc/**",  # Generated documentation
            "**/.git/**",  # Git directory
            "**/node_modules/**",  # Node modules (for Rails with JS)
            "**/public/assets/**",  # Rails compiled assets
        ]

        # Add Rails-specific patterns if this is a Rails project
        if Solargraph._detect_rails_project(repository_root_path):
            rails_patterns = [
                "**/public/packs/**",  # Webpacker output
                "**/public/webpack/**",  # Webpack output
                "**/storage/**",  # Active Storage files
                "**/tmp/cache/**",  # Rails cache
                "**/tmp/pids/**",  # Process IDs
                "**/tmp/sessions/**",  # Session files
                "**/tmp/sockets/**",  # Socket files
                "**/db/*.sqlite3",  # SQLite databases
            ]
            base_patterns.extend(rails_patterns)

        return base_patterns

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Solargraph Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        exclude_patterns = Solargraph._get_ruby_exclude_patterns(repository_absolute_path)

        initialize_params: InitializeParams = {  # type: ignore
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "initializationOptions": {
                "exclude": exclude_patterns,
            },
            "capabilities": {
                "workspace": {
                    "workspaceEdit": {"documentChanges": True},
                },
                "textDocument": {
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
            },
            "trace": "verbose",
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params

    def _start_server(self):
        """
        Starts the Solargraph Language Server for Ruby
        """

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        def lang_status_handler(params):
            self.logger.log(f"LSP: language/status: {params}", logging.INFO)
            if params.get("type") == "ServiceReady" and params.get("message") == "Service is ready.":
                self.logger.log("Solargraph service is ready.", logging.INFO)
                self.analysis_complete.set()
                self.completions_available.set()

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        self.logger.log("Starting solargraph server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        self.logger.log(f"Sending init params: {json.dumps(initialize_params, indent=4)}", logging.INFO)
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received init response: {init_response}", logging.INFO)
        assert init_response["capabilities"]["textDocumentSync"] == 2
        assert "completionProvider" in init_response["capabilities"]
        assert init_response["capabilities"]["completionProvider"] == {
            "resolveProvider": True,
            "triggerCharacters": [".", ":", "@"],
        }
        self.server.notify.initialized({})

        # Wait for Solargraph to complete its initial workspace analysis
        # This prevents issues by ensuring background tasks finish
        self.logger.log("Waiting for Solargraph to complete initial workspace analysis...", logging.INFO)
        if self.analysis_complete.wait(timeout=60.0):
            self.logger.log("Solargraph initial analysis complete, server ready", logging.INFO)
        else:
            self.logger.log("Timeout waiting for Solargraph analysis completion, proceeding anyway", logging.WARNING)
            # Fallback: assume analysis is complete after timeout
            self.analysis_complete.set()
            self.completions_available.set()
