"""
Provides an experimental Lua language server implementation using emmylua_ls.

The backend is deliberately separate from the default Lua Language Server so projects can
select it explicitly with ``language: lua_emmylua``.
"""

import logging
import platform
import shutil
from pathlib import Path

from overrides import override

from solidlsp.language_servers.lua_ls import LuaLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_utils import FileUtils
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

EMMYLUA_ALLOWED_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_EMMYLUA_LS_VERSION = "0.25.1"
DEFAULT_EMMYLUA_LS_VERSION = "0.25.1"
DEFAULT_EMMYLUA_LS_SHA256_BY_ASSET = {
    "emmylua_ls-darwin-arm64.tar.gz": "335023043cbc9ad683a13b24eb79f709a370215daf53673276b9a9663df96504",
    "emmylua_ls-darwin-x64.tar.gz": "abc9cbe2e8d28624e0d441fa55055b1196f73251b034356d717b0e58b562f182",
    "emmylua_ls-linux-aarch64-glibc.2.17.tar.gz": "210535be13c31ceefcdd0f8451eb4c0d3d430887fc2c382eaf82484a9187220d",
    "emmylua_ls-linux-x64-glibc.2.17.tar.gz": "9731ec340b1b40916555dcb31c1c539beee9fa184997962c9af250c42b316950",
    "emmylua_ls-win32-arm64.zip": "f6f335f01fccca6f000a6240fb78c6fbab069230b1bb4347361ef3f64550390a",
    "emmylua_ls-win32-x64.zip": "82efa133287f67be09e1a624d8efecd8063832ec2b9bf9279c37afc5f42118bd",
}


def _emmylua_ls_sha(version: str, asset_name: str) -> str | None:
    if version in {INITIAL_EMMYLUA_LS_VERSION, DEFAULT_EMMYLUA_LS_VERSION}:
        return DEFAULT_EMMYLUA_LS_SHA256_BY_ASSET.get(asset_name)
    return None


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

    @staticmethod
    def _get_emmylua_ls_path(solidlsp_settings: SolidLSPSettings | None = None) -> str | None:
        """Find a configured, system-installed, or managed emmylua_ls executable."""
        if solidlsp_settings is not None:
            settings = solidlsp_settings.get_ls_specific_settings(LanguageServerId.LUA_EMMYLUA)
            configured_path = settings.get("ls_path")
            if configured_path:
                return str(configured_path)

        system_path = shutil.which("emmylua_ls")
        if system_path:
            return system_path

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
        asset_name, archive_type, binary_name = _emmylua_ls_asset(platform.system(), platform.machine())
        download_url = f"https://github.com/EmmyLuaLs/emmylua-analyzer-rust/releases/download/{version}/{asset_name}"

        install_dir = _emmylua_ls_install_dir(EmmyLuaLanguageServer.ls_resources_dir(solidlsp_settings), version)
        install_dir.mkdir(parents=True, exist_ok=True)
        log.info("Downloading emmylua_ls from %s", download_url)
        FileUtils.download_and_extract_archive_verified(
            download_url,
            str(install_dir),
            archive_type,
            expected_sha256=_emmylua_ls_sha(version, asset_name),
            allowed_hosts=EMMYLUA_ALLOWED_HOSTS,
        )

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
