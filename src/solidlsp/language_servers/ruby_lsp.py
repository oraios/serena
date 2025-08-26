"""
Ruby LSP Language Server implementation using Shopify's ruby-lsp.
Provides modern Ruby language server capabilities with improved performance.
"""

import json
import logging
import os
import pathlib
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


class RubyLsp(SolidLanguageServer):
    """
    Provides Ruby specific instantiation of the LanguageServer class using ruby-lsp.
    Contains various configurations and settings specific to Ruby with modern LSP features.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a RubyLsp instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        ruby_lsp_executable = self._setup_runtime_dependencies(logger, config, repository_root_path)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=ruby_lsp_executable, cwd=repository_root_path),
            "ruby",
            solidlsp_settings,
        )
        self.analysis_complete = threading.Event()
        self.service_ready_event = threading.Event()

        # Set timeout for ruby-lsp requests - ruby-lsp is fast
        self.set_request_timeout(30.0)  # 30 seconds for initialization and requests

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """Override to ignore Ruby-specific directories that cause performance issues."""
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
            "public/packs",  # Webpacker output
            "public/webpack",  # Webpack output
            "public/assets",  # Rails compiled assets
        ]
        return super().is_ignored_dirname(dirname) or dirname in ruby_ignored_dirs

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Override to provide optimal wait time for ruby-lsp cross-file reference resolution.

        ruby-lsp typically initializes quickly, but may need a brief moment
        for cross-file analysis in larger projects.
        """
        return 0.5  # 500ms should be sufficient for ruby-lsp

    @staticmethod
    def _find_executable_with_extensions(executable_name: str) -> str | None:
        """
        Find executable with Windows-specific extensions (.bat, .cmd, .exe) if on Windows.
        Returns the full path to the executable or None if not found.
        """
        import platform

        if platform.system() == "Windows":
            # Try Windows-specific extensions first
            for ext in [".bat", ".cmd", ".exe"]:
                path = shutil.which(f"{executable_name}{ext}")
                if path:
                    return path
            # Fall back to default search
            return shutil.which(executable_name)
        else:
            # Unix systems
            return shutil.which(executable_name)

    @staticmethod
    def _setup_runtime_dependencies(logger: LanguageServerLogger, config: LanguageServerConfig, repository_root_path: str) -> list[str]:
        """
        Setup runtime dependencies for ruby-lsp and return the command list to start the server.
        Installation strategy: Bundler project > global ruby-lsp > gem install ruby-lsp
        """
        # Check if Ruby is installed
        try:
            result = subprocess.run(["ruby", "--version"], check=True, capture_output=True, cwd=repository_root_path, text=True)
            ruby_version = result.stdout.strip()
            logger.log(f"Ruby version: {ruby_version}", logging.INFO)

            # Extract version number for compatibility checks
            import re

            version_match = re.search(r"ruby (\d+)\.(\d+)\.(\d+)", ruby_version)
            if version_match:
                major, minor, patch = map(int, version_match.groups())
                if major < 2 or (major == 2 and minor < 6):
                    logger.log(f"Warning: Ruby {major}.{minor}.{patch} detected. ruby-lsp works best with Ruby 2.6+", logging.WARNING)

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if isinstance(e.stderr, str) else e.stderr.decode() if e.stderr else "Unknown error"
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

        # Check for Bundler project (Gemfile exists)
        gemfile_path = os.path.join(repository_root_path, "Gemfile")
        gemfile_lock_path = os.path.join(repository_root_path, "Gemfile.lock")
        is_bundler_project = os.path.exists(gemfile_path)

        if is_bundler_project:
            logger.log("Detected Bundler project (Gemfile found)", logging.INFO)

            # Check if bundle command is available using Windows-compatible search
            bundle_path = RubyLsp._find_executable_with_extensions("bundle")
            if not bundle_path:
                # Try common bundle executables
                for bundle_cmd in ["bin/bundle", "bundle"]:
                    if bundle_cmd.startswith("bin/"):
                        bundle_full_path = os.path.join(repository_root_path, bundle_cmd)
                    else:
                        bundle_full_path = RubyLsp._find_executable_with_extensions(bundle_cmd)
                    if bundle_full_path and os.path.exists(bundle_full_path):
                        bundle_path = bundle_full_path if bundle_cmd.startswith("bin/") else bundle_cmd
                        break

            if not bundle_path:
                logger.log(
                    "Bundler project detected but 'bundle' command not found. Falling back to global ruby-lsp installation.",
                    logging.WARNING,
                )
            else:
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
                    return [bundle_path, "exec", "ruby-lsp"]
                else:
                    logger.log(
                        "ruby-lsp not found in Gemfile.lock. Consider adding 'gem \"ruby-lsp\"' to your Gemfile for better compatibility.",
                        logging.INFO,
                    )
                    # Fall through to global installation check

        # Check if ruby-lsp is available globally using Windows-compatible search
        ruby_lsp_path = RubyLsp._find_executable_with_extensions("ruby-lsp")
        if ruby_lsp_path:
            logger.log(f"Found ruby-lsp at: {ruby_lsp_path}", logging.INFO)
            return [ruby_lsp_path]

        # Try to install ruby-lsp globally
        logger.log("ruby-lsp not found, attempting to install globally...", logging.INFO)
        try:
            subprocess.run(["gem", "install", "ruby-lsp"], check=True, capture_output=True, cwd=repository_root_path)
            logger.log("Successfully installed ruby-lsp globally", logging.INFO)
            # Find the newly installed ruby-lsp executable
            ruby_lsp_path = RubyLsp._find_executable_with_extensions("ruby-lsp")
            return [ruby_lsp_path] if ruby_lsp_path else ["ruby-lsp"]
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if isinstance(e.stderr, str) else e.stderr.decode() if e.stderr else str(e)
            if is_bundler_project:
                raise RuntimeError(
                    f"Failed to install ruby-lsp globally: {error_msg}\n"
                    "For Bundler projects, please add 'gem \"ruby-lsp\"' to your Gemfile and run 'bundle install'.\n"
                    "Alternatively, install globally: gem install ruby-lsp"
                ) from e
            raise RuntimeError(f"Failed to install ruby-lsp: {error_msg}\nPlease try installing manually: gem install ruby-lsp") from e

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
            "**/vendor/**",  # Ruby vendor directory
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
        if RubyLsp._detect_rails_project(repository_root_path):
            base_patterns.extend(
                [
                    "**/app/assets/builds/**",  # Rails 7+ CSS builds
                    "**/storage/**",  # Active Storage
                    "**/public/packs/**",  # Webpacker
                    "**/public/webpack/**",  # Webpack
                ]
            )

        return base_patterns

    def _get_initialize_params(self) -> InitializeParams:
        """
        Returns ruby-lsp specific initialization parameters.
        """
        exclude_patterns = self._get_ruby_exclude_patterns(self.repository_root_path)

        initialize_params = {
            "processId": os.getpid(),
            "rootPath": self.repository_root_path,
            "rootUri": pathlib.Path(self.repository_root_path).as_uri(),
            "capabilities": {
                "workspace": {
                    "workspaceEdit": {"documentChanges": True},
                    "configuration": True,
                },
                "textDocument": {
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                        }
                    },
                },
            },
            "initializationOptions": {
                # ruby-lsp enables all features by default, so we don't need to specify enabledFeatures
                "experimentalFeaturesEnabled": False,
                "featuresConfiguration": {},
                "indexing": {
                    "includedPatterns": ["**/*.rb", "**/*.rake", "**/*.ru", "**/*.erb"],
                    "excludedPatterns": exclude_patterns,
                },
            },
        }

        return initialize_params

    def _start_server(self) -> None:
        """
        Starts the ruby-lsp Language Server for Ruby
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                self.logger.log(f"Registered capability: {registration['method']}", logging.INFO)
            return

        def lang_status_handler(params: dict) -> None:
            self.logger.log(f"LSP: language/status: {params}", logging.INFO)
            if params.get("type") == "ready":
                self.logger.log("ruby-lsp service is ready.", logging.INFO)
                self.analysis_complete.set()
                self.completions_available.set()

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def progress_handler(params: dict) -> None:
            # ruby-lsp sends progress notifications during indexing
            if "value" in params:
                value = params["value"]
                if value.get("kind") == "end":
                    self.logger.log("ruby-lsp indexing complete", logging.INFO)
                    self.analysis_complete.set()
                    self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", progress_handler)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting ruby-lsp server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params()

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        self.logger.log(f"Sending init params: {json.dumps(initialize_params, indent=4)}", logging.INFO)
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received init response: {init_response}", logging.INFO)

        # Verify expected capabilities
        # Note: ruby-lsp may return textDocumentSync in different formats (number or object)
        text_document_sync = init_response["capabilities"].get("textDocumentSync")
        if isinstance(text_document_sync, int):
            assert text_document_sync in [1, 2], f"Unexpected textDocumentSync value: {text_document_sync}"
        elif isinstance(text_document_sync, dict):
            # ruby-lsp returns an object with change property
            assert "change" in text_document_sync, "textDocumentSync object should have 'change' property"

        assert "completionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        # Wait for ruby-lsp to complete its initial indexing
        # ruby-lsp has fast indexing
        self.logger.log("Waiting for ruby-lsp to complete initial indexing...", logging.INFO)
        if self.analysis_complete.wait(timeout=30.0):
            self.logger.log("ruby-lsp initial indexing complete, server ready", logging.INFO)
        else:
            self.logger.log("Timeout waiting for ruby-lsp indexing completion, proceeding anyway", logging.WARNING)
            # Fallback: assume indexing is complete after timeout
            self.analysis_complete.set()
            self.completions_available.set()

    def _handle_initialization_response(self, init_response):
        """
        Handle the initialization response from ruby-lsp and validate capabilities.
        """
        if "capabilities" in init_response:
            capabilities = init_response["capabilities"]

            # Validate textDocumentSync (ruby-lsp may return different formats)
            text_document_sync = capabilities.get("textDocumentSync")
            if isinstance(text_document_sync, int):
                assert text_document_sync in [1, 2], f"Unexpected textDocumentSync value: {text_document_sync}"
            elif isinstance(text_document_sync, dict):
                # ruby-lsp returns an object with change property
                assert "change" in text_document_sync, "textDocumentSync object should have 'change' property"

            # Log important capabilities
            important_capabilities = [
                "completionProvider",
                "hoverProvider",
                "definitionProvider",
                "referencesProvider",
                "documentSymbolProvider",
                "codeActionProvider",
                "documentFormattingProvider",
                "semanticTokensProvider",
            ]

            for cap in important_capabilities:
                if cap in capabilities:
                    self.logger.log(f"ruby-lsp {cap}: available", logging.DEBUG)

        # Signal that the service is ready
        self.service_ready_event.set()
