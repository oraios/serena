"""
Provides Ansible specific instantiation of the LanguageServer class using ansible-language-server.
Contains various configurations and settings specific to Ansible YAML files (playbooks, roles, etc.).
"""

import fnmatch
import logging
import os
import pathlib
import shutil
from typing import Any, ClassVar

from overrides import override

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_ANSIBLE_LANGUAGE_SERVER_VERSION = "1.2.3"
DEFAULT_ANSIBLE_LANGUAGE_SERVER_VERSION = "1.2.3"


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base*, modifying *base* in-place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


class AnsibleLanguageServer(SolidLanguageServer):
    """Provides Ansible specific instantiation of the LanguageServer class using ansible-language-server.

    Contains various configurations and settings specific to Ansible YAML files
    (playbooks, roles, inventories, etc.).

    Supported ``ls_specific_settings`` keys (via ``serena_config.yml``):

    * ``ls_path`` (str) — path to the ansible-language-server executable
      (handled by the base class).
    * ``ansible_path`` (str, default ``"ansible"``) — path to the ``ansible`` executable.
    * ``python_interpreter_path`` (str, default ``"python3"``) — path to the Python interpreter.
    * ``python_activation_script`` (str, default ``""``) — virtualenv activation script.
    * ``lint_enabled`` (bool, default ``False``) — enable ansible-lint
      (requires a separate installation of ``ansible-lint``).
    * ``lint_path`` (str, default ``"ansible-lint"``) — path to ``ansible-lint``.
    * ``ansible_settings`` (dict) — full settings dict, deep-merged on top of defaults.
      The structure mirrors the Ansible Language Server settings
      (``ansible.*``, ``python.*``, ``validation.*``, ``completion.*``,
      ``executionEnvironment.*``).
    """

    # directory names that signal ansible content at ANY nesting level
    _ANSIBLE_DIR_NAMES: ClassVar[set[str]] = {
        "roles",
        "playbooks",
        "tasks",
        "handlers",
        "group_vars",
        "host_vars",
        "inventory",
        "inventories",
        "defaults",
        "vars",
        "meta",
    }

    # filename patterns handled by ansible LS regardless of path
    _ANSIBLE_FILENAME_PATTERNS: ClassVar[list[str]] = [
        "playbook*.yml",
        "playbook*.yaml",
        "site.yml",
        "site.yaml",
        "requirements.yml",
        "requirements.yaml",
    ]

    @staticmethod
    def _is_ansible_path(relative_path: str) -> bool:
        """Check if a file is in an ansible-specific location.

        Matches if ANY component of the path is an ansible-specific
        directory name (e.g. ``roles``, ``tasks``, ``group_vars``),
        or if the filename matches an ansible-specific pattern.
        This works regardless of nesting depth:
        ``project/deploy/roles/web/tasks/main.yml`` matches on both
        ``roles`` and ``tasks``.

        :param relative_path: path relative to the repository root
        :return: True if the path is an ansible-specific location
        """
        normalized = relative_path.replace("\\", "/")
        parts = normalized.split("/")

        # check if any directory component is ansible-specific
        dir_parts = parts[:-1]
        for part in dir_parts:
            if part in AnsibleLanguageServer._ANSIBLE_DIR_NAMES:
                return True

        # check filename patterns (e.g. playbook.yml, site.yaml)
        filename = parts[-1]
        for pattern in AnsibleLanguageServer._ANSIBLE_FILENAME_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True

        return False

    @override
    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True) -> bool:
        # standard ignore rules (extension, gitignore, etc.)
        if super().is_ignored_path(relative_path, ignore_unsupported_files):
            return True

        # for yml/yaml files, check if they are in ansible-specific paths
        if relative_path.endswith((".yml", ".yaml")):
            if not self._is_ansible_path(relative_path):
                return True

        return False

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """Classify ansible-language-server stderr output to avoid false-positive errors."""
        line_lower = line.lower()

        if any(
            [
                "ansible is not installed" in line_lower,
                "ansible-lint" in line_lower and "not found" in line_lower,
                "cannot find module" in line_lower,
            ]
        ):
            return logging.DEBUG

        return SolidLanguageServer._determine_log_level(line)

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """Creates an AnsibleLanguageServer instance.

        This class is not meant to be instantiated directly.
        Use ``SolidLanguageServer.create()`` instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "ansible",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Setup runtime dependencies for Ansible Language Server and return the path to the executable."""
            # verify both node and npm are installed
            is_node_installed = shutil.which("node") is not None
            assert is_node_installed, "node is not installed or isn't in PATH. Please install Node.js and try again."
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."
            ansible_language_server_version = self._custom_settings.get(
                "ansible_language_server_version", DEFAULT_ANSIBLE_LANGUAGE_SERVER_VERSION
            )
            npm_registry = self._custom_settings.get("npm_registry")

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="ansible-language-server",
                        description="Ansible Language Server (@ansible/ansible-language-server)",
                        command=build_npm_install_command(
                            "@ansible/ansible-language-server",
                            ansible_language_server_version,
                            npm_registry,
                        ),
                        platform_id="any",
                    ),
                ]
            )

            # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
            ls_dirname = (
                "ansible-lsp"
                if ansible_language_server_version == INITIAL_ANSIBLE_LANGUAGE_SERVER_VERSION
                else f"ansible-lsp-{ansible_language_server_version}"
            )
            ansible_ls_dir = os.path.join(self._ls_resources_dir, ls_dirname)
            ansible_executable_path = os.path.join(ansible_ls_dir, "node_modules", ".bin", "ansible-language-server")

            # handle Windows executable extension
            if os.name == "nt":
                ansible_executable_path += ".cmd"

            if not os.path.exists(ansible_executable_path):
                log.info(f"Ansible Language Server executable not found at {ansible_executable_path}. Installing...")
                deps.install(ansible_ls_dir)
                log.info("Ansible Language Server dependencies installed successfully")

            if not os.path.exists(ansible_executable_path):
                raise FileNotFoundError(
                    f"ansible-language-server executable not found at {ansible_executable_path}, "
                    "something went wrong with the installation."
                )

            return ansible_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """Returns the initialize params for the Ansible Language Server.

        Reads shortcut keys and the ``ansible_settings`` dict from ``_custom_settings``
        to build ``initializationOptions``.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        # default ansible settings, populated from shortcut keys
        ansible_settings: dict[str, Any] = {
            "ansible": {
                "path": self._custom_settings.get("ansible_path", "ansible"),
                "useFullyQualifiedCollectionNames": True,
            },
            "python": {
                "interpreterPath": self._custom_settings.get("python_interpreter_path", "python3"),
                "activationScript": self._custom_settings.get("python_activation_script", ""),
            },
            "validation": {
                "enabled": True,
                "lint": {
                    "enabled": self._custom_settings.get("lint_enabled", False),
                    "path": self._custom_settings.get("lint_path", "ansible-lint"),
                },
            },
            "completion": {
                "provideRedirectModules": True,
                "provideModuleOptionAliases": True,
            },
            "executionEnvironment": {"enabled": False},
        }

        # full override via ansible_settings dict for advanced configuration
        user_settings = self._custom_settings.settings.get("ansible_settings")
        if user_settings:
            if not isinstance(user_settings, dict):
                raise TypeError(
                    f"ansible_settings must be a dict, got {type(user_settings).__name__}. "
                    "Expected structure matching Ansible LS settings: "
                    "{'ansible': {...}, 'python': {...}, 'validation': {...}, ...}"
                )
            _deep_merge(ansible_settings, user_settings)

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
            "initializationOptions": {"ansible": ansible_settings},
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Starts the Ansible Language Server, waits for the server to be ready."""

        def register_capability_handler(params: Any) -> None:
            return

        def show_message_request_handler(params: Any) -> None:
            """Handle ``window/showMessageRequest`` by returning ``null``.

            Per the LSP spec, returning ``null`` means no action was selected.
            Without this handler the client replies with ``MethodNotFound``,
            which the ansible LS treats as fatal.
            """
            log.info(f"LSP: window/showMessageRequest (dismissed): {params.get('message', params)}")
            return

        def do_nothing(params: Any) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("window/showMessageRequest", show_message_request_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Ansible server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Ansible server: {init_response}")

        log.debug(f"Ansible server capabilities: {list(init_response['capabilities'].keys())}")

        self.server.notify.initialized({})
        log.info("Ansible server initialization complete")
