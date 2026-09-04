"""
Provides an experimental Lua language server implementation using emmylua_ls.

The backend is deliberately separate from the default Lua Language Server so projects can
select it explicitly with ``language: lua_emmylua``.
"""

import logging
import platform
from pathlib import Path

from overrides import override

from solidlsp.dependency_provider import DownloadedDependency, DownloadedDependencyHashDatabase
from solidlsp.language_servers.lua_ls import LuaLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import FileUtils
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

EMMYLUA_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
# NOTE: after bumping DEFAULT_EMMYLUA_LS_VERSION, re-run scripts/update_downloaded_dependency_hashes.py
# and commit the resulting changes to src/solidlsp/resources/downloaded_dependency_hashes.json; a stale
# hash database means unverified downloads locally and a CI failure.
INITIAL_EMMYLUA_LS_VERSION = "0.25.1"
DEFAULT_EMMYLUA_LS_VERSION = "0.25.1"


def _emmylua_ls_dep(system: str, machine: str, version: str | None = None) -> DownloadedDependency:
    """Build the pinned emmylua_ls download for the given platform.

    Custom (user-selected) versions are passed with ``verified=False`` because their checksums
    cannot be pinned by design; the pinned default release is always verified against the
    central hash database.
    """
    version = version or DEFAULT_EMMYLUA_LS_VERSION
    asset_name, archive_type, _ = _emmylua_ls_asset(system, machine)
    return DownloadedDependency(
        url=f"https://github.com/EmmyLuaLs/emmylua-analyzer-rust/releases/download/{version}/{asset_name}",
        archive_type=archive_type,
        allowed_hosts=EMMYLUA_ALLOWED_HOSTS,
        verified=version == DEFAULT_EMMYLUA_LS_VERSION,
    )


def _emmylua_ls_install_dir(ls_resources_dir: str, version: str) -> Path:
    # Keep the original unversioned cache location stable and namespace later upgrades.
    if version == INITIAL_EMMYLUA_LS_VERSION:
        return Path(ls_resources_dir) / "emmylua"
    return Path(ls_resources_dir) / f"emmylua-{version}"


def _emmylua_ls_asset(system: str, machine: str) -> tuple[str, FileUtils.ArchiveType, str]:
    """Return ``(archive name, archive type, binary name)`` for a platform."""
    normalized_machine = machine.lower()
    if system == "Linux":
        if normalized_machine in {"x86_64", "amd64"}:
            return "emmylua_ls-linux-x64-glibc.2.17.tar.gz", "gztar", "emmylua_ls"
        if normalized_machine in {"aarch64", "arm64"}:
            return "emmylua_ls-linux-aarch64-glibc.2.17.tar.gz", "gztar", "emmylua_ls"
        raise RuntimeError(f"Unsupported Linux architecture: {machine}")
    if system == "Darwin":
        if normalized_machine in {"x86_64", "amd64"}:
            return "emmylua_ls-darwin-x64.tar.gz", "gztar", "emmylua_ls"
        if normalized_machine in {"arm64", "aarch64"}:
            return "emmylua_ls-darwin-arm64.tar.gz", "gztar", "emmylua_ls"
        raise RuntimeError(f"Unsupported macOS architecture: {machine}")
    if system == "Windows":
        if normalized_machine in {"amd64", "x86_64"}:
            return "emmylua_ls-win32-x64.zip", "zip", "emmylua_ls.exe"
        if normalized_machine in {"arm64", "aarch64"}:
            return "emmylua_ls-win32-arm64.zip", "zip", "emmylua_ls.exe"
        raise RuntimeError(f"Unsupported Windows architecture: {machine}")
    raise RuntimeError(f"Unsupported operating system: {system}")


class EmmyLuaLanguageServer(LuaLanguageServer):
    """Experimental Lua backend using the Rust-based ``emmylua_ls`` server."""

    @classmethod
    def update_dep_hashes(cls) -> None:
        supported_platforms = [
            ("Linux", "x86_64"),
            ("Linux", "aarch64"),
            ("Darwin", "x86_64"),
            ("Darwin", "arm64"),
            ("Windows", "amd64"),
            ("Windows", "arm64"),
        ]
        deps = [_emmylua_ls_dep(system, machine) for system, machine in supported_platforms]
        with DownloadedDependencyHashDatabase.get_instance().update_context() as db:
            for dep in deps:
                db.update(dep)

    @staticmethod
    def _get_emmylua_ls_path(solidlsp_settings: SolidLSPSettings | None = None) -> str | None:
        """Find a configured or managed emmylua_ls executable."""
        if solidlsp_settings is not None:
            settings = solidlsp_settings.get_ls_specific_settings(LanguageServerId.LUA_EMMYLUA)
            configured_path = settings.get("ls_path")
            if configured_path:
                return str(configured_path)

        if solidlsp_settings is not None:
            settings = solidlsp_settings.get_ls_specific_settings(LanguageServerId.LUA_EMMYLUA)
            version = settings.get("emmylua_ls_version", DEFAULT_EMMYLUA_LS_VERSION)
            install_dir = _emmylua_ls_install_dir(EmmyLuaLanguageServer.ls_resources_dir(solidlsp_settings), version)
            binary_name = "emmylua_ls.exe" if platform.system() == "Windows" else "emmylua_ls"
            managed_path = install_dir / binary_name
            if managed_path.exists():
                return str(managed_path)

        return None

    @staticmethod
    def _download_emmylua_ls(solidlsp_settings: SolidLSPSettings) -> str:
        """Download and install the pinned emmylua_ls release for the current platform."""
        settings = solidlsp_settings.get_ls_specific_settings(LanguageServerId.LUA_EMMYLUA)
        version = settings.get("emmylua_ls_version", DEFAULT_EMMYLUA_LS_VERSION)
        system, machine = platform.system(), platform.machine()
        _, _, binary_name = _emmylua_ls_asset(system, machine)
        dep = _emmylua_ls_dep(system, machine, version)

        install_dir = _emmylua_ls_install_dir(EmmyLuaLanguageServer.ls_resources_dir(solidlsp_settings), version)
        install_dir.mkdir(parents=True, exist_ok=True)
        log.info("Downloading emmylua_ls from %s", dep.get_url())
        dep.download_to(str(install_dir))

        binary_path = install_dir / binary_name
        if not binary_path.exists():
            raise RuntimeError(f"Failed to find emmylua_ls executable after extraction at {binary_path}")
        if platform.system() != "Windows":
            binary_path.chmod(binary_path.stat().st_mode | 0o111)
        return str(binary_path)

    @staticmethod
    def _setup_runtime_dependency(solidlsp_settings: SolidLSPSettings) -> str:
        """Return an emmylua_ls executable, downloading it when necessary."""
        binary_path = EmmyLuaLanguageServer._get_emmylua_ls_path(solidlsp_settings)
        if binary_path:
            return binary_path
        return EmmyLuaLanguageServer._download_emmylua_ls(solidlsp_settings)

    @override
    def _create_base_initialize_params(self) -> dict:
        """Use the shared Lua capabilities without LuaLS-specific initialization options."""
        params = super()._create_base_initialize_params()
        params["initializationOptions"] = {}
        return params

    @override
    def _start_server(self) -> None:
        """Start the emmylua_ls process using the shared Lua LSP lifecycle."""
        super()._start_server()
