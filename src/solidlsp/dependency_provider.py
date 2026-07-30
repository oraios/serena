import logging
import os
import platform
import shutil
from abc import ABC, abstractmethod
from collections.abc import Sequence

from solidlsp.settings import SolidLSPSettings
from solidlsp.util.subprocess_util import subprocess_run

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

    def install_dependencies(self) -> None:
        """
        Downloads and installs all dependencies that are managed by this provider, such that
        a subsequent launch of the language server requires no further downloads.

        This is used to prepare environments in which the language server is to be run without
        (unrestricted) network access later on.

        The default implementation covers the regular case, where the dependencies are installed
        as part of the launch command's construction; providers which defer the installation
        beyond that point must override this method.

        :raises Exception: if the dependencies could not be installed
        """
        self.create_launch_command()


class LanguageServerDependencyProviderBaseCommand(LanguageServerDependencyProvider, ABC):
    """
    Special case of a dependency provider, where the launch command is constructed from a base command.

    The user can configure aspects of the launch command in LS-specific settings:

      * ``ls_base_cmd`: overrides the base command
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

    def _get_custom_base_command(self) -> list[str] | None:
        """
        Obtains the base command from the user-provided settings, which bypasses the managed installation
        of the language server's dependencies.

        :return: the user-provided base command or None if the managed installation applies
        """
        base_command = self._custom_settings.get("ls_base_cmd", None)
        if base_command is not None and not isinstance(base_command, list):
            log.warning("The 'ls_base_cmd' setting should be a list of strings. Ignoring the provided value: %s", base_command)
            base_command = None
        if base_command is None:
            ls_path = self._custom_settings.get("ls_path", None)
            if ls_path is not None:
                base_command = [ls_path]
        return base_command

    def create_launch_command(self) -> list[str]:
        # obtain base command
        base_command = self._get_custom_base_command()
        if base_command is None:
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
        """Build a command that runs a pinned PyPI package's console script on demand via ``uvx`` / ``uv tool run``.

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
            return [uv_path, "tool", "run", *base_args]  # `uv tool run` is the same as `uvx`

        raise RuntimeError("Could not find 'uvx' or 'uv' in PATH. Install uv (https://docs.astral.sh/uv/).")

    @staticmethod
    def _find_uv_executable() -> str:
        """
        :return: the path to the ``uv`` executable
        :raises RuntimeError: if uv is not installed
        """
        uv_path = shutil.which("uv")
        if uv_path is not None:
            return uv_path

        # fall back to the 'uv' executable residing alongside 'uvx' (the two are shipped together),
        # resolving the configured uvx command against the PATH, as it need not be a path
        uvx_path = os.environ.get("UVX") or "uvx"
        uvx_path = shutil.which(uvx_path)
        if uvx_path is not None:
            candidate = os.path.join(os.path.dirname(uvx_path), "uv.exe" if platform.system() == "Windows" else "uv")
            if os.path.isfile(candidate):
                return candidate

        raise RuntimeError("Could not find 'uv' in PATH. Install uv (https://docs.astral.sh/uv/).")

    @classmethod
    def _build_uv_tool_install_command(cls, package: str, version: str, python_version: str = DEFAULT_UVX_PYTHON_VERSION) -> list[str]:
        """
        Builds a command which persistently installs a pinned PyPI package's console script as a uv tool.

        :param package: PyPI package name (e.g. ``"pyright"``).
        :param version: Pinned package version.
        :param python_version: Python interpreter version passed via ``-p`` (uv will fetch it if missing).
        :return: the installation command
        """
        return [cls._find_uv_executable(), "tool", "install", "-p", python_version, f"{package}=={version}"]

    def _create_default_base_command(self):
        version = self._custom_settings.get(self._version_setting_key, self._default_version)
        return self._build_uvx_base_command(self._package, version, self._entrypoint)

    def _create_launch_command_from_base_command(self, base_command: list[str]) -> list[str]:
        return base_command + list(self._extra_args)

    def install_dependencies(self) -> None:
        # Note that the base class implementation would be insufficient here: constructing the launch command
        # downloads nothing, because uvx materialises the package's environment only when the command is
        # actually executed. We therefore install the pinned package as a uv tool, which downloads the package
        # (and, if necessary, the Python interpreter), such that the subsequent `uvx` invocation can reuse
        # the existing installation instead of retrieving it from the network.

        # skip if the user bypasses the uv-managed installation via a custom launch command/path
        # (applying the very same criterion as the launch command construction, such that the two cannot diverge)
        if self._get_custom_base_command() is not None:
            log.info("A custom launch command is configured for package '%s'; no dependencies to install", self._package)
            return

        # perform the installation
        version = self._custom_settings.get(self._version_setting_key, self._default_version)
        cmd = self._build_uv_tool_install_command(self._package, version)
        log.info("Installing %s==%s via %s", self._package, version, cmd)
        result = subprocess_run(cmd)
        if result.returncode != 0:
            raise RuntimeError(f"Installation of {self._package}=={version} failed: {result.stderr or result.stdout}")
