import logging
import platform
import re
import shutil
import subprocess
import urllib
from pathlib import Path

from serena.util.version import Version
from solidlsp.ls_exceptions import SolidLSPException

log = logging.getLogger(__name__)


class DotNETUtil:
    def __init__(self, required_version: str, allow_higher_version: bool = True):
        """
        :param required_version: the required .NET runtime version specified as a string (e.g. "10.0" for .NET 10.0)
        :param allow_higher_version: whether to allow higher versions than the required version
        """
        self._system_dotnet = shutil.which("dotnet")
        self._required_version_str = required_version
        self._required_version_components = [int(c) for c in required_version.split(".")]
        self._allow_higher_version = allow_higher_version
        self._installed_versions = self._determine_installed_versions()

    def _determine_installed_versions(self) -> list[Version]:
        if self._system_dotnet:
            try:
                result = subprocess.run([self._system_dotnet, "--list-runtimes"], capture_output=True, text=True, check=True)
                version_strings = re.findall(r"Microsoft.NETCore.App\s+([^\s]+)", result.stdout)
                log.info("Installed .NET runtime versions: %s", version_strings)
                return [Version(v) for v in version_strings]
            except:
                log.warning("Failed to run 'dotnet --list-runtimes' to check .NET version; assuming no installed .NET versions")
                return []
        else:
            log.info("Found no `dotnet` on system PATH; assuming no installed .NET versions")
            return []

    def is_required_version_available(self) -> bool:
        """
        Checks whether the required .NET runtime version is installed and raises an exception if not.

        :param required_version_components: the required .NET runtime version specified as a list of integers representing the version components (e.g., [6, 1] for .NET 6.1)
        :param allow_higher_version: whether to allow higher versions than the required version (e.g., if True, .NET 7.0 would satisfy a requirement of .NET 6.1)
        """
        required_version_str = ".".join(str(c) for c in self._required_version_components)
        for v in self._installed_versions:
            if self._allow_higher_version:
                if v.is_at_least(*self._required_version_components):
                    log.info(f"Found installed .NET runtime version {v} which satisfies requirement of {required_version_str} or higher")
                    return True
            else:
                if v.is_equal(*self._required_version_components):
                    log.info(f"Found installed .NET runtime version {v} which satisfies requirement of {required_version_str}")
                    return True
        return False

    def get_dotnet_path_or_raise(self) -> str:
        """
        Returns the path to the dotnet executable if the required .NET runtime version is available, otherwise raises an exception.
        """
        if not self.is_required_version_available():
            raise SolidLSPException(
                f"Required .NET runtime version {self._required_version_str} not found "
                f"(installed versions: {self._installed_versions}). "
                "Please install the required .NET runtime version from https://dotnet.microsoft.com/en-us/download/dotnet "
                "and ensure that `dotnet` is on the system PATH."
            )
        assert self._system_dotnet is not None
        return self._system_dotnet

    @staticmethod
    def install_dotnet_with_script(version: str, base_path: str) -> str:
        """
        Install .NET runtime using Microsoft's official installation script.

        NOTE: This method is unreliable and therefore currently unused. It is kept for reference.

        :version: the version to install as a string (e.g. "10.0")
        :return: the path to the dotnet executable.
        """
        dotnet_dir = Path(base_path) / f"dotnet-runtime-{version}"

        # Determine binary name based on platform
        is_windows = platform.system().lower() == "windows"
        dotnet_exe = dotnet_dir / ("dotnet.exe" if is_windows else "dotnet")

        if dotnet_exe.exists():
            log.info(f"Using cached .NET {version} runtime from {dotnet_exe}")
            return str(dotnet_exe)

        # Download and run install script
        log.info(f"Installing .NET {version} runtime using official Microsoft install script...")
        dotnet_dir.mkdir(parents=True, exist_ok=True)

        try:
            if is_windows:
                # PowerShell script for Windows
                script_url = "https://dot.net/v1/dotnet-install.ps1"
                script_path = dotnet_dir / "dotnet-install.ps1"
                urllib.request.urlretrieve(script_url, script_path)

                cmd = [
                    "pwsh",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-Version",
                    version,
                    "-InstallDir",
                    str(dotnet_dir),
                    "-Runtime",
                    "dotnet",
                    "-NoPath",
                ]
            else:
                # Bash script for Linux/macOS
                script_url = "https://dot.net/v1/dotnet-install.sh"
                script_path = dotnet_dir / "dotnet-install.sh"
                urllib.request.urlretrieve(script_url, script_path)
                script_path.chmod(0o755)

                cmd = [
                    "bash",
                    str(script_path),
                    "--version",
                    version,
                    "--install-dir",
                    str(dotnet_dir),
                    "--runtime",
                    "dotnet",
                    "--no-path",
                ]

            # Run the install script
            log.info("Running .NET install script: %s", cmd)
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            log.debug(f"Install script output: {result.stdout}")

            if not dotnet_exe.exists():
                raise SolidLSPException(f"dotnet executable not found at {dotnet_exe} after installation")

            log.info(f"Successfully installed .NET {version} runtime to {dotnet_exe}")
            return str(dotnet_exe)

        except subprocess.CalledProcessError as e:
            raise SolidLSPException(f"Failed to install .NET {version} runtime using install script: {e.stderr if e.stderr else e}") from e
        except Exception as e:
            message = f"Failed to install .NET {version} runtime: {e}"
            if is_windows and isinstance(e, FileNotFoundError):
                message += "; pwsh, i.e. PowerShell 7+, is required to install .NET runtime. Make sure pwsh is available on your system."
            raise SolidLSPException(message) from e
