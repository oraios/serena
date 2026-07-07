from __future__ import annotations

"""
Language server launch coordination (Phase 2 deep module).

This module owns:
- The LanguageServerDependencyProvider hierarchy (base classes + Uvx provider)
- Process launch info construction
- Language server interface creation
- Initialize params building (via DefaultInitializeParamsBuilder)

The facade (SolidLanguageServer) retains narrow policy hooks that adapters override:
- _create_dependency_provider()
- _create_base_initialize_params()
- _create_language_server_interface()
- _start_server()

The launcher is a collaborator; it does not own adapter-specific policy.
"""

import logging
import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from solidlsp.ls_process import LanguageServerInterface
from solidlsp.lsp_protocol_handler import lsp_types
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo, StringDict

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer  # for type annotations only
    from solidlsp.initialize_params import InitializeParamsBuilder
    from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class LanguageServerDependencyProvider(ABC):
    """
    Prepares dependencies for a language server (if any), ultimately enabling the launch command to be constructed
    and optionally providing environment variables that are necessary for the execution.
    """

    def __init__(self, custom_settings: SolidLSPSettings.CustomLSSettings, ls_resources_dir: str):
        """
        :param custom_settings: the (user-provided) language server-specific settings
        :param ls_resources_dir: the directory in which data for the language-server shall be stored
            (this is already specific to the concrete language server, i.e. no further subdirectory is needed)
        """
        self._custom_settings = custom_settings
        self._ls_resources_dir = ls_resources_dir

    @abstractmethod
    def create_launch_command(self) -> list[str]:
        """
        Creates the launch command for this language server, potentially downloading and installing dependencies
        beforehand.

        :return: the launch command as a list containing the executable and its arguments
        """

    def create_launch_command_env(self) -> dict[str, str]:
        """
        Provides environment variables to be set when executing the launch command.

        This method is intended to be overridden by subclasses that need to set variables.

        :return: a mapping for variable names to values
        """
        return {}


class LanguageServerDependencyProviderBaseCommand(LanguageServerDependencyProvider, ABC):
    """
    Special case of a dependency provider, where the launch command is constructed from a base command.

    The user can configure aspects of the launch command in LS-specific settings:

      * ``ls_base_cmd``: overrides the base command
      * ``ls_path``: overrides the path of the language server's core dependency (e.g. its executable or a JAR file),
        from which the base command is formed, bypassing Serena's managed installation
      * ``ls_args``: overrides the arguments that are added to the base command in order to form the launch command
      * ``ls_extra_args``: additional arguments to append to the launch command
    """

    @abstractmethod
    def _create_default_base_command(self) -> list[str]:
        """
        Obtains the default base command for this language server, potentially downloading and installing dependencies
        beforehand.

        Note: The user can override the base command, so this will only be run if no custom base command is provided.

        :return: the base command as a list containing the executable and its arguments
        """

    @abstractmethod
    def _create_launch_command_from_base_command(self, base_command: list[str]) -> list[str]:
        """
        Adds any additional arguments to the base command to create the final launch command.

        :param base_command: the base command
        :return: the extended command
        """

    def create_launch_command(self) -> list[str]:
        # obtain base command
        base_command = self._custom_settings.get("ls_base_cmd", None)
        if base_command is not None and not isinstance(base_command, list):
            log.warning("The 'ls_base_cmd' setting should be a list of strings. Ignoring the provided value: %s", base_command)
            base_command = None
        if base_command is None:
            ls_path = self._custom_settings.get("ls_path", None)
            if ls_path is not None:
                base_command = [ls_path]
            else:
                # default case: base command is constructed by the provider implementation
                base_command = self._create_default_base_command()

        # create launch command from base command
        ls_args = self._custom_settings.get("ls_args")
        if ls_args is not None:
            if not isinstance(ls_args, list):
                log.warning("The 'ls_args' setting should be a list of strings. Ignoring the provided value: %s", ls_args)
                ls_args = None
        if ls_args is not None:
            cmd = list(base_command) + ls_args
        else:
            cmd = self._create_launch_command_from_base_command(list(base_command))

        # add user-provided extra arguments (if any)
        ls_extra_args = self._custom_settings.get("ls_extra_args", [])
        if ls_extra_args:
            if not isinstance(ls_extra_args, list):
                log.warning("The 'ls_extra_args' setting should be a list of strings. Ignoring the provided value: %s", ls_extra_args)
            else:
                cmd = cmd + ls_extra_args

        return cmd


class LanguageServerDependencyProviderSinglePath(LanguageServerDependencyProviderBaseCommand, ABC):
    """
    Special case of a dependency provider, where there is a single core dependency which provides
    the basis for the launch command.

    The core dependency's path can be overridden by the user in LS-specific settings (SerenaConfig)
    via the key "ls_path". If the user provides the key, the specified path is used directly.
    Otherwise, the provider implementation is called to get or install the core dependency.

    Note: The inheritance from the BaseCommand class serves to allow user overrides to be handled
      centrally, but implementations of this class do not necessarily follow the principle that
      the base command is strictly extended.
      Yet incompatibility arises only if (a) the user overrides the base command with a command that
      has arguments, and (b) the implementation of this class does not construct the launch command
      by appending arguments to the core dependency's path.
    """

    @abstractmethod
    def _get_or_install_core_dependency(self) -> str:
        """
        Gets the language server's core path, potentially installing dependencies beforehand.

        :return: the core dependency's path (e.g. executable, jar, etc.)
        """

    @abstractmethod
    def _create_launch_command(self, core_path: str) -> list[str]:
        """
        :param core_path: path to the core dependency
        :return: the launch command as a list containing the executable and its arguments
        """

    def _create_default_base_command(self) -> list[str]:
        # We treat the core path as the only element of the base command,
        # noting that the construction of the launch command from the base command
        # is not necessarily to append arguments only.
        core_path = self._get_or_install_core_dependency()
        return [core_path]

    def _create_launch_command_from_base_command(self, base_command: list[str]) -> list[str]:
        core_path = base_command[0]
        cmd = self._create_launch_command(core_path)
        if len(base_command) == 1:
            # This is the regular case, where the base command consists only of the core
            # dependency's path, and the launch command is constructed from it.
            return cmd
        else:
            # In this case, the user has overridden the base command via LS-specific settings
            # with a command that has arguments and therefore does not map cleanly to
            # the single path assumption. However, in special cases where the full command
            # was constructed by appending arguments to the core dependency's path,
            # we simply assume that the provided base command can be substituted.
            if cmd[0] == core_path:
                return base_command + cmd[1:]
            else:
                raise ValueError("Language server base launch command with arguments unsupported")


class LanguageServerDependencyProviderUvx(LanguageServerDependencyProviderBaseCommand):
    """
    Dependency provider for language servers distributed as a PyPI package, run on demand via ``uvx`` / ``uv x``.

    The pinned package version can be overridden by the user via the LS-specific setting given by
    ``version_setting_key``. Alternatively, the LS-specific setting "ls_path" can be set to the path of an
    already-installed language server executable, in which case it is launched directly, bypassing uv entirely.
    """

    DEFAULT_UVX_PYTHON_VERSION = "3.13"

    def __init__(
        self,
        custom_settings: "SolidLSPSettings.CustomLSSettings",
        ls_resources_dir: str,
        *,
        package: str,
        entrypoint: str,
        default_version: str,
        version_setting_key: str,
        extra_args: Sequence[str] = (),
    ):
        """
        :param package: the PyPI package name (e.g. ``"pyright"``)
        :param entrypoint: the console script provided by the package (e.g. ``"pyright-langserver"``)
        :param default_version: the package version to pin unless overridden
        :param version_setting_key: the LS-specific setting key through which the user can override the version
        :param extra_args: arguments appended after the entrypoint (e.g. ``("--stdio",)``)
        """
        super().__init__(custom_settings, ls_resources_dir)
        self._package = package
        self._entrypoint = entrypoint
        self._default_version = default_version
        self._version_setting_key = version_setting_key
        self._extra_args = tuple(extra_args)

    @staticmethod
    def _build_uvx_base_command(
        package: str,
        version: str,
        entrypoint: str,
        python_version: str = DEFAULT_UVX_PYTHON_VERSION,
    ) -> list[str]:
        """Build a command that runs a pinned PyPI package's console script on demand via ``uvx`` / ``uv x``.

        Resolution order:
          1. Prefer ``uvx`` (env var ``UVX`` or PATH lookup).
          2. Fall back to ``uv x`` if only ``uv`` is on PATH.
          3. Raise ``RuntimeError`` if neither is available.

        :param package: PyPI package name (e.g. ``"pyright"``).
        :param version: Pinned package version.
        :param entrypoint: Console script provided by the package (e.g. ``"pyright-langserver"``).
        :param python_version: Python interpreter version passed via ``-p`` (uv will fetch it if missing).
        """
        base_args = ["-p", python_version, "--from", f"{package}=={version}", entrypoint]

        uvx_path = os.environ.get("UVX") or shutil.which("uvx")
        if uvx_path is not None:
            return [uvx_path, *base_args]

        uv_path = shutil.which("uv")
        if uv_path is not None:
            return [uv_path, "x", *base_args]

        raise RuntimeError("Could not find 'uvx' or 'uv' in PATH. Install uv (https://docs.astral.sh/uv/).")

    def _create_default_base_command(self):
        version = self._custom_settings.get(self._version_setting_key, self._default_version)
        return self._build_uvx_base_command(self._package, version, self._entrypoint)

    def _create_launch_command_from_base_command(self, base_command: list[str]) -> list[str]:
        return base_command + list(self._extra_args)


# ---------------------------------------------------------------------------
# Launcher: owns dependency providers + process launch + interface creation
# ---------------------------------------------------------------------------


class LanguageServerLauncher:
    """
    Thin collaborator that owns dependency-provider creation, process launch info,
    and low-level interface creation.

    The launcher does not own adapter policy. The facade (SolidLanguageServer) keeps:
    - _create_dependency_provider()
    - _create_base_initialize_params()
    - _create_language_server_interface()
    - _start_server()

    The launcher is initialized with the facade so it can invoke those narrow hooks.
    """

    def __init__(self, facade: "SolidLanguageServer"):
        self._facade = facade
        self._dependency_provider: LanguageServerDependencyProvider | None = None

    # --- creation of launch artifacts ---

    def ensure_dependency_provider(self) -> LanguageServerDependencyProvider:
        """
        Ensure a dependency provider exists (via facade hook) and return it.
        """
        if self._dependency_provider is None:
            self._dependency_provider = self._facade._create_dependency_provider()
        return self._dependency_provider

    def create_process_launch_info(self) -> ProcessLaunchInfo:
        """
        Build ProcessLaunchInfo from the dependency provider (or rely on pre-provided info path in facade).
        """
        provider = self.ensure_dependency_provider()
        cmd = provider.create_launch_command()
        env = provider.create_launch_command_env()
        return ProcessLaunchInfo(cmd=cmd, cwd=self._facade.repository_root_path, env=env)

    def create_language_server_interface(
        self,
        process_launch_info: ProcessLaunchInfo,
        logging_fn: Callable[[str, str, StringDict | str], None] | None,
    ) -> LanguageServerInterface:
        """
        Delegate to facade hook so subclasses can override the interface type.
        """
        return self._facade._create_language_server_interface(process_launch_info, logging_fn)

    # --- initialize params (via existing builder) ---

    def create_initialize_params(self) -> lsp_types.InitializeParams:
        """
        Build the final InitializeParams using the facade's base options and the shared builder.
        """
        from solidlsp.initialize_params import DefaultInitializeParamsBuilder  # local import to avoid cycles

        builder: InitializeParamsBuilder = DefaultInitializeParamsBuilder(self._facade)
        base = self._facade._create_base_initialize_params()
        return builder.with_base_options(base).build()

    # --- convenience: perform the low-level start handshake (not policy) ---

    def start_interface_and_initialize(
        self,
        server: LanguageServerInterface,
        initialize_params: lsp_types.InitializeParams,
    ) -> Any:
        """
        Start the low-level server and send the initialize request.
        Returns the initialize response (adapters typically assert on capabilities).
        """
        log.info("Starting language server process")
        server.start()
        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        response = server.send.initialize(initialize_params)
        return response
