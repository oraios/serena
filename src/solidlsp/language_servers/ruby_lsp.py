import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import threading

from typing_extensions import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class RubyLSP(SolidLanguageServer):
    """
    Provides Ruby specific instantiation of the LanguageServer class using ruby-lsp.
    Contains various configurations and settings specific to Ruby.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a RubyLSP instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        ruby_lsp_executable_path = self._setup_runtime_dependencies(logger, config, repository_root_path)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{ruby_lsp_executable_path}", cwd=repository_root_path),
            "ruby",
            solidlsp_settings,
        )
        self.analysis_complete = threading.Event()
        self.service_ready_event = threading.Event()

        # Set timeout for ruby-lsp requests
        self.set_request_timeout(60.0)  # 60 seconds for initialization and requests

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
        Setup runtime dependencies for ruby-lsp and return the command to start the server.
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
                if major < 3 or (major == 3 and minor < 0):
                    logger.log(f"Warning: Ruby {major}.{minor}.{patch} detected. ruby-lsp works best with Ruby 3.0+", logging.WARNING)

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else "Unknown error"
            raise RuntimeError(
                f"Error checking Ruby installation: {error_msg}. Please ensure Ruby is properly installed and in PATH."
            ) from e
        except FileNotFoundError as e:
            raise RuntimeError(
                "Ruby is not installed or not found in PATH. Please install Ruby using one of these methods:\n"
                "  - Using rbenv: rbenv install 3.2.0 && rbenv global 3.2.0\n"
                "  - Using RVM: rvm install 3.2.0 && rvm use 3.2.0 --default\n"
                "  - Using asdf: asdf install ruby 3.2.0 && asdf global ruby 3.2.0\n"
                "  - System package manager (brew install ruby, apt install ruby, etc.)"
            ) from e

        # Check for Bundler project (Gemfile exists)
        gemfile_path = os.path.join(repository_root_path, "Gemfile")
        gemfile_lock_path = os.path.join(repository_root_path, "Gemfile.lock")
        is_bundler_project = os.path.exists(gemfile_path)

        if is_bundler_project:
            logger.log("Detected Bundler project (Gemfile found)", logging.INFO)

            # Check if bundle command is available
            bundle_path = shutil.which("bundle")
            if not bundle_path:
                # Try common bundle executables
                for bundle_cmd in ["bin/bundle", "bundle"]:
                    bundle_full_path = (
                        os.path.join(repository_root_path, bundle_cmd) if bundle_cmd.startswith("bin/") else shutil.which(bundle_cmd)
                    )
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

            # Check if ruby-lsp is in Gemfile.lock
            ruby_lsp_in_bundle = False
            if os.path.exists(gemfile_lock_path):
                try:
                    with open(gemfile_lock_path) as f:
                        content = f.read()
                        ruby_lsp_in_bundle = "ruby-lsp" in content.lower()
                except Exception as e:
                    logger.log(f"Warning: Could not read Gemfile.lock: {e}", logging.WARNING)

            if ruby_lsp_in_bundle:
                logger.log("Found ruby-lsp in Gemfile.lock", logging.INFO)
                return f"{bundle_path} exec ruby-lsp"
            else:
                logger.log(
                    "ruby-lsp not found in Gemfile.lock. Please add 'gem \"ruby-lsp\"' to your Gemfile and run 'bundle install'",
                    logging.WARNING,
                )
                # Fall through to global installation check

        # Check if ruby-lsp is installed globally
        # First, try to find ruby-lsp in PATH (includes asdf shims)
        ruby_lsp_path = shutil.which("ruby-lsp")
        if ruby_lsp_path:
            logger.log(f"Found ruby-lsp at: {ruby_lsp_path}", logging.INFO)
            return ruby_lsp_path

        # Fallback to gem exec (for non-Bundler projects or when global ruby-lsp not found)
        if not is_bundler_project:
            dependency = {
                "url": "https://rubygems.org/downloads/ruby-lsp-0.17.17.gem",
                "installCommand": "gem install ruby-lsp -v 0.17.17",
                "binaryName": "ruby-lsp",
                "archiveType": "gem",
            }

            try:
                result = subprocess.run(
                    ["gem", "list", "^ruby-lsp$", "-i"], check=False, capture_output=True, text=True, cwd=repository_root_path
                )
                if result.stdout.strip() == "false":
                    logger.log("Installing ruby-lsp...", logging.INFO)
                    subprocess.run(dependency["installCommand"].split(), check=True, capture_output=True, cwd=repository_root_path)

                return "gem exec ruby-lsp"
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                raise RuntimeError(
                    f"Failed to check or install ruby-lsp: {error_msg}\nPlease try installing manually: gem install ruby-lsp"
                ) from e
        else:
            raise RuntimeError(
                "This appears to be a Bundler project, but ruby-lsp is not available. "
                "Please add 'gem \"ruby-lsp\"' to your Gemfile and run 'bundle install'."
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
        if RubyLSP._detect_rails_project(repository_root_path):
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
        Returns the initialize params for the ruby-lsp Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        initialize_params: InitializeParams = {  # type: ignore
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "initializationOptions": {
                "enabledFeatures": {
                    "diagnostics": True,
                    "documentSymbols": True,
                    "foldingRanges": True,
                    "selectionRanges": True,
                    "semanticHighlighting": True,
                    "formatting": True,
                    "codeActions": True,
                },
                "featuresConfiguration": {
                    "inlayHint": {"enableAll": True},
                },
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
        Starts the ruby-lsp Language Server for Ruby
        """

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params):
            return

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting ruby-lsp server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        self.logger.log(f"Sending init params: {json.dumps(initialize_params, indent=4)}", logging.INFO)
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received init response: {init_response}", logging.INFO)

        # ruby-lsp may use different sync modes
        text_sync = init_response["capabilities"].get("textDocumentSync")
        self.logger.log(f"ruby-lsp textDocumentSync mode: {text_sync}", logging.INFO)

        # Accept various sync modes (incremental=2, full=1, none=0)
        if isinstance(text_sync, dict):
            # Some servers return an object instead of just a number
            sync_change = text_sync.get("change", 0)
            assert sync_change in [0, 1, 2], f"Unexpected textDocumentSync change mode: {sync_change}"
        else:
            assert text_sync in [0, 1, 2], f"Unexpected textDocumentSync mode: {text_sync}"

        assert "completionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # ruby-lsp doesn't require special analysis completion waiting like solargraph
        self.logger.log("ruby-lsp server ready", logging.INFO)
        self.analysis_complete.set()
        self.completions_available.set()
