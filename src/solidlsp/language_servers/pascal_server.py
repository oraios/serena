"""
Provides Pascal/Free Pascal specific instantiation of the LanguageServer class using pasls.
Contains various configurations and settings specific to Pascal and Free Pascal.

pasls installation strategy:
1. Use existing pasls from PATH
2. Download prebuilt binary from GitHub releases (auto-updated)

Supported platforms for binary download:
- linux-x64, linux-arm64
- osx-x64, osx-arm64
- win-x64

Auto-update features:
- Checks for updates every 24 hours via GitHub API
- SHA256 checksum verification before installation
- Atomic update with rollback on failure
- Windows file locking detection

You can pass the following entries in ls_specific_settings["pascal"]:

Environment variables (recommended for CodeTools configuration):
- pp: Path to FPC compiler driver, must be "fpc.exe" (e.g., "D:/laz32/fpc/bin/i386-win32/fpc.exe").
  Do NOT use backend compilers like ppc386.exe or ppcx64.exe - CodeTools queries fpc.exe for
  configuration (fpc -iV, fpc -iTO, etc.). This is the most important setting for hover/navigation.
- fpcdir: Path to FPC source directory (e.g., "D:/laz32/fpcsrc"). Helps CodeTools locate
  standard library sources for better navigation.
- lazarusdir: Path to Lazarus directory (e.g., "D:/laz32/lazarus"). Required for Lazarus
  projects using LCL and other Lazarus components.

Target platform overrides (use only if pp setting is not sufficient):
- fpc_target: Override target OS (e.g., "Win32", "Win64", "Linux"). Sets FPCTARGET env var.
- fpc_target_cpu: Override target CPU (e.g., "i386", "x86_64", "aarch64"). Sets FPCTARGETCPU.

Example configuration in ~/.serena/serena_config.yml:
    ls_specific_settings:
        pascal:
            pp: "D:/laz32/fpc/bin/i386-win32/fpc.exe"
            fpcdir: "D:/laz32/fpcsrc"
            lazarusdir: "D:/laz32/lazarus"
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import platform
import shutil
import tarfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, quote_windows_path
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class PascalLanguageServer(SolidLanguageServer):
    """
    Provides Pascal specific instantiation of the LanguageServer class using pasls.
    Contains various configurations and settings specific to Free Pascal and Lazarus.
    """

    # URL configuration
    PASLS_RELEASES_URL = "https://github.com/zen010101/pascal-language-server/releases/latest/download"
    PASLS_API_URL = "https://api.github.com/repos/zen010101/pascal-language-server/releases/latest"

    # Update check interval (seconds)
    UPDATE_CHECK_INTERVAL = 86400  # 24 hours

    # Metadata directory name
    META_DIR = ".meta"

    # Network timeout (seconds)
    NETWORK_TIMEOUT = 10

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a PascalLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        pasls_executable_path = self._setup_runtime_dependencies(solidlsp_settings)

        # Build environment variables for pasls
        # These control CodeTools' configuration and target platform settings
        proc_env: dict[str, str] = {}

        # Read from ls_specific_settings["pascal"]
        from solidlsp.ls_config import Language

        pascal_settings = solidlsp_settings.get_ls_specific_settings(Language.PASCAL)

        # pp: Path to FPC compiler driver (must be fpc.exe, NOT ppc386.exe/ppcx64.exe)
        # CodeTools queries fpc.exe for configuration via "fpc -iV", "fpc -iTO", etc.
        pp = pascal_settings.get("pp", "")
        if pp:
            proc_env["PP"] = pp
            log.info(f"Setting PP={pp} from ls_specific_settings")

        # fpcdir: Path to FPC source directory (e.g., "D:/laz32/fpcsrc")
        fpcdir = pascal_settings.get("fpcdir", "")
        if fpcdir:
            proc_env["FPCDIR"] = fpcdir
            log.info(f"Setting FPCDIR={fpcdir} from ls_specific_settings")

        # lazarusdir: Path to Lazarus directory (e.g., "D:/laz32/lazarus")
        lazarusdir = pascal_settings.get("lazarusdir", "")
        if lazarusdir:
            proc_env["LAZARUSDIR"] = lazarusdir
            log.info(f"Setting LAZARUSDIR={lazarusdir} from ls_specific_settings")

        # fpc_target: Override target OS (e.g., "Win32", "Win64", "Linux")
        fpc_target = pascal_settings.get("fpc_target", "")
        if fpc_target:
            proc_env["FPCTARGET"] = fpc_target
            log.info(f"Setting FPCTARGET={fpc_target} from ls_specific_settings")

        # fpc_target_cpu: Override target CPU (e.g., "i386", "x86_64", "aarch64")
        fpc_target_cpu = pascal_settings.get("fpc_target_cpu", "")
        if fpc_target_cpu:
            proc_env["FPCTARGETCPU"] = fpc_target_cpu
            log.info(f"Setting FPCTARGETCPU={fpc_target_cpu} from ls_specific_settings")

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=pasls_executable_path, cwd=repository_root_path, env=proc_env),
            "pascal",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    # ============== Metadata Directory Management ==============

    @classmethod
    def _meta_dir(cls, pasls_dir: str) -> str:
        """Get metadata directory path, create if not exists."""
        meta_path = os.path.join(pasls_dir, cls.META_DIR)
        os.makedirs(meta_path, exist_ok=True)
        return meta_path

    @classmethod
    def _meta_file(cls, pasls_dir: str, filename: str) -> str:
        """Get metadata file path."""
        return os.path.join(cls._meta_dir(pasls_dir), filename)

    # ============== Version Management ==============

    @staticmethod
    def _normalize_version(version: str | None) -> str:
        """Normalize version string by removing 'v' prefix and whitespace."""
        if not version:
            return ""
        return version.strip().lstrip("vV")

    @classmethod
    def _is_newer_version(cls, latest: str | None, local: str | None) -> bool:
        """Compare versions, return True if latest is newer than local."""
        if not latest:
            return False
        if not local:
            return True

        latest_norm = cls._normalize_version(latest)
        local_norm = cls._normalize_version(local)

        if not latest_norm:
            return False
        if not local_norm:
            return True

        try:

            def parse_version(v: str) -> list[int]:
                parts = []
                for part in v.split("."):
                    num = ""
                    for c in part:
                        if c.isdigit():
                            num += c
                        else:
                            break
                    parts.append(int(num) if num else 0)
                return parts

            latest_parts = parse_version(latest_norm)
            local_parts = parse_version(local_norm)

            # Pad to same length
            max_len = max(len(latest_parts), len(local_parts))
            latest_parts.extend([0] * (max_len - len(latest_parts)))
            local_parts.extend([0] * (max_len - len(local_parts)))

            return latest_parts > local_parts
        except Exception:
            log.warning(f"Failed to parse versions for comparison: {latest_norm} vs {local_norm}")
            return False

    @classmethod
    def _get_latest_version(cls) -> str | None:
        """Get latest version from GitHub API, return None on failure."""
        try:
            headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Serena-LSP"}
            # Support GITHUB_TOKEN for CI environments with rate limits
            github_token = os.environ.get("GITHUB_TOKEN")
            if github_token:
                headers["Authorization"] = f"token {github_token}"

            req = urllib.request.Request(cls.PASLS_API_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=cls.NETWORK_TIMEOUT) as response:
                data = json.loads(response.read().decode())
                return data.get("tag_name")
        except Exception as e:
            log.debug(f"Failed to get latest pasls version: {type(e).__name__}: {e}")
            return None

    @classmethod
    def _get_local_version(cls, pasls_dir: str) -> str | None:
        """Read local version file."""
        version_file = cls._meta_file(pasls_dir, "version")
        if os.path.exists(version_file):
            try:
                with open(version_file, encoding="utf-8") as f:
                    return f.read().strip()
            except OSError:
                return None
        return None

    @classmethod
    def _save_local_version(cls, pasls_dir: str, version: str) -> None:
        """Save version to local file."""
        version_file = cls._meta_file(pasls_dir, "version")
        try:
            with open(version_file, "w", encoding="utf-8") as f:
                f.write(version)
        except OSError as e:
            log.warning(f"Failed to save version file: {e}")

    # ============== Update Check Timing ==============

    @classmethod
    def _should_check_update(cls, pasls_dir: str) -> bool:
        """Check if we should query for updates (more than 24 hours since last check)."""
        last_check_file = cls._meta_file(pasls_dir, "last_check")
        if not os.path.exists(last_check_file):
            return True
        try:
            with open(last_check_file, encoding="utf-8") as f:
                last_check = float(f.read().strip())
            return (time.time() - last_check) > cls.UPDATE_CHECK_INTERVAL
        except (OSError, ValueError):
            return True

    @classmethod
    def _update_last_check(cls, pasls_dir: str) -> None:
        """Update last check timestamp."""
        last_check_file = cls._meta_file(pasls_dir, "last_check")
        try:
            with open(last_check_file, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except OSError as e:
            log.warning(f"Failed to update last check time: {e}")

    # ============== SHA256 Checksum ==============

    @classmethod
    def _get_checksums(cls) -> dict[str, str] | None:
        """Download checksums file from GitHub, return {filename: sha256} dict."""
        checksums_url = f"{cls.PASLS_RELEASES_URL}/checksums.sha256"
        try:
            req = urllib.request.Request(checksums_url, headers={"User-Agent": "Serena-LSP"})
            with urllib.request.urlopen(req, timeout=cls.NETWORK_TIMEOUT) as response:
                content = response.read().decode("utf-8")
                checksums = {}
                for line in content.strip().split("\n"):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        sha256 = parts[0]
                        filename = parts[1].lstrip("*")  # Remove possible * prefix
                        checksums[filename] = sha256
                return checksums
        except Exception as e:
            log.warning(f"Failed to get checksums: {type(e).__name__}: {e}")
            return None

    @staticmethod
    def _calculate_sha256(file_path: str) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @classmethod
    def _verify_checksum(cls, file_path: str, expected_sha256: str) -> bool:
        """Verify file checksum."""
        try:
            actual_sha256 = cls._calculate_sha256(file_path)
            if actual_sha256.lower() == expected_sha256.lower():
                log.debug(f"Checksum verified: {file_path}")
                return True
            else:
                log.error(f"Checksum mismatch for {file_path}: expected {expected_sha256}, got {actual_sha256}")
                return False
        except Exception as e:
            log.error(f"Failed to verify checksum: {e}")
            return False

    # ============== Windows File Locking ==============

    @staticmethod
    def _is_file_locked(file_path: str) -> bool:
        """Check if file is locked (Windows)."""
        if platform.system() != "Windows":
            return False

        if not os.path.exists(file_path):
            return False

        try:
            with open(file_path, "a"):
                pass
            return False
        except (OSError, PermissionError):
            return True

    @classmethod
    def _safe_remove(cls, file_path: str) -> bool:
        """Safely remove file, handle Windows file locking."""
        if not os.path.exists(file_path):
            return True

        if platform.system() == "Windows" and cls._is_file_locked(file_path):
            temp_name = f"{file_path}.old.{uuid.uuid4().hex[:8]}"
            try:
                os.rename(file_path, temp_name)
                log.info(f"File locked, renamed to: {temp_name}")
                cls._mark_for_cleanup(os.path.dirname(file_path), temp_name)
                return True
            except PermissionError:
                log.warning(f"Cannot remove/rename locked file: {file_path}")
                return False
        else:
            try:
                os.remove(file_path)
                return True
            except OSError as e:
                log.warning(f"Failed to remove file {file_path}: {e}")
                return False

    @classmethod
    def _mark_for_cleanup(cls, pasls_dir: str, file_path: str) -> None:
        """Mark file for later cleanup."""
        cleanup_file = cls._meta_file(pasls_dir, "cleanup_list")
        try:
            with open(cleanup_file, "a", encoding="utf-8") as f:
                f.write(file_path + "\n")
        except OSError:
            pass

    @classmethod
    def _cleanup_old_files(cls, pasls_dir: str) -> None:
        """Clean up old files marked for deletion."""
        cleanup_file = cls._meta_file(pasls_dir, "cleanup_list")
        if not os.path.exists(cleanup_file):
            return

        try:
            with open(cleanup_file, encoding="utf-8") as f:
                files = [line.strip() for line in f if line.strip()]

            remaining = []
            for file_path in files:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        log.debug(f"Cleaned up old file: {file_path}")
                    except OSError:
                        remaining.append(file_path)

            if remaining:
                with open(cleanup_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(remaining) + "\n")
            else:
                os.remove(cleanup_file)
        except OSError:
            pass

    # ============== Download and Atomic Update ==============

    @classmethod
    def _download_archive(cls, url: str, target_path: str) -> bool:
        """Download archive to specified path."""
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "Serena-LSP"})
            with urllib.request.urlopen(req, timeout=60) as response:
                with open(target_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            return True
        except Exception as e:
            log.error(f"Failed to download {url}: {type(e).__name__}: {e}")
            return False

    @classmethod
    def _is_safe_tar_member(cls, member: tarfile.TarInfo, target_dir: str) -> bool:
        """Check if tar member is safe (prevent path traversal attack)."""
        # Check for .. in path components
        if ".." in member.name.split("/") or ".." in member.name.split("\\"):
            return False

        # Check extracted path is within target directory
        abs_target = os.path.abspath(target_dir)
        abs_member = os.path.abspath(os.path.join(target_dir, member.name))

        return abs_member.startswith(abs_target + os.sep) or abs_member == abs_target

    @classmethod
    def _extract_archive(cls, archive_path: str, target_dir: str, archive_type: str) -> bool:
        """Safely extract archive to specified directory."""
        try:
            os.makedirs(target_dir, exist_ok=True)

            if archive_type == "gztar":
                with tarfile.open(archive_path, "r:gz") as tar:
                    for member in tar.getmembers():
                        if not cls._is_safe_tar_member(member, target_dir):
                            log.error(f"Unsafe tar member detected (path traversal): {member.name}")
                            return False
                    tar.extractall(target_dir)

            elif archive_type == "zip":
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    for name in zip_ref.namelist():
                        if ".." in name.split("/") or ".." in name.split("\\"):
                            log.error(f"Unsafe zip member detected (path traversal): {name}")
                            return False
                        abs_target = os.path.abspath(target_dir)
                        abs_member = os.path.abspath(os.path.join(target_dir, name))
                        if not (abs_member.startswith(abs_target + os.sep) or abs_member == abs_target):
                            log.error(f"Unsafe zip member detected (path traversal): {name}")
                            return False
                    zip_ref.extractall(target_dir)

            else:
                log.error(f"Unsupported archive type: {archive_type}")
                return False

            # Handle nested directory: if extraction created a single subdirectory,
            # move its contents up to target_dir (common with GitHub release archives)
            cls._flatten_single_subdir(target_dir)

            return True
        except Exception as e:
            log.error(f"Failed to extract archive: {type(e).__name__}: {e}")
            return False

    @classmethod
    def _flatten_single_subdir(cls, target_dir: str) -> None:
        """If target_dir contains only a single subdirectory, move its contents up."""
        entries = os.listdir(target_dir)
        if len(entries) == 1:
            subdir = os.path.join(target_dir, entries[0])
            if os.path.isdir(subdir):
                # Move all contents from subdir to target_dir
                for item in os.listdir(subdir):
                    src = os.path.join(subdir, item)
                    dst = os.path.join(target_dir, item)
                    shutil.move(src, dst)
                # Remove the now-empty subdirectory
                os.rmdir(subdir)

    @classmethod
    def _get_archive_filename(cls, dep: RuntimeDependency) -> str:
        """Get archive filename from URL."""
        assert dep.url is not None, "RuntimeDependency.url must be set"
        return dep.url.split("/")[-1]

    @classmethod
    def _atomic_install(cls, pasls_dir: str, deps: RuntimeDependencyCollection, checksums: dict[str, str] | None) -> bool:
        """Atomic update: download -> verify checksum -> extract -> replace."""
        temp_dir = pasls_dir + ".tmp"
        backup_dir = pasls_dir + ".backup"
        temp_archive_dir = os.path.join(os.path.expanduser("~"), "solidlsp_tmp")

        try:
            dep = deps.get_single_dep_for_current_platform()
            assert dep.url is not None, "RuntimeDependency.url must be set"
            assert dep.archive_type is not None, "RuntimeDependency.archive_type must be set"

            archive_filename = cls._get_archive_filename(dep)
            archive_path = os.path.join(temp_archive_dir, archive_filename)

            # 1. Clean up any existing temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_archive_dir, exist_ok=True)

            # 2. Download archive
            log.info(f"Downloading pasls archive: {archive_filename}")
            if not cls._download_archive(dep.url, archive_path):
                log.error("Failed to download pasls archive")
                return False

            # 3. Verify SHA256 checksum (critical security step, before extraction)
            if checksums:
                expected_sha256 = checksums.get(archive_filename)
                if expected_sha256:
                    log.info(f"Verifying SHA256 checksum for {archive_filename}...")
                    if not cls._verify_checksum(archive_path, expected_sha256):
                        log.error(f"SHA256 checksum verification FAILED for {archive_filename}")
                        log.error("Aborting installation due to checksum mismatch - possible security issue!")
                        try:
                            os.remove(archive_path)
                        except OSError:
                            pass
                        return False
                    log.info("SHA256 checksum verified successfully")
                else:
                    log.warning(f"No checksum found for {archive_filename} in checksums file")
            else:
                log.warning("No checksums available - skipping verification (not recommended for production)")

            # 4. Extract to temp directory
            os.makedirs(temp_dir, exist_ok=True)
            log.info("Extracting archive to temporary directory...")
            if not cls._extract_archive(archive_path, temp_dir, dep.archive_type):
                log.error("Failed to extract archive")
                return False

            # 5. Set execute permission
            binary_path = deps.binary_path(temp_dir)
            if os.path.exists(binary_path):
                try:
                    os.chmod(binary_path, 0o755)
                except OSError:
                    pass  # May fail on Windows

            # 6. Backup old version
            if os.path.exists(pasls_dir):
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir)
                shutil.move(pasls_dir, backup_dir)

            # 7. Replace with new version
            shutil.move(temp_dir, pasls_dir)

            # 8. Restore meta directory from backup (preserves version info, last_check, etc.)
            if os.path.exists(backup_dir):
                backup_meta = os.path.join(backup_dir, cls.META_DIR)
                if os.path.exists(backup_meta):
                    target_meta = os.path.join(pasls_dir, cls.META_DIR)
                    if not os.path.exists(target_meta):
                        shutil.copytree(backup_meta, target_meta)

            # 9. Clean up downloaded archive and temp directory
            try:
                os.remove(archive_path)
                os.rmdir(temp_archive_dir)
            except OSError:
                pass

            log.info("pasls installation completed successfully")
            return True

        except Exception as e:
            log.error(f"Installation failed: {e}")

            # Rollback
            if os.path.exists(backup_dir) and not os.path.exists(pasls_dir):
                try:
                    shutil.move(backup_dir, pasls_dir)
                    log.info("Rolled back to previous version")
                except Exception as rollback_error:
                    log.error(f"Rollback failed: {rollback_error}")

            # Clean up temp directory
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

            return False

    @classmethod
    def _setup_runtime_dependencies(cls, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Pascal Language Server (pasls).
        Automatically checks for updates every 24 hours with security verification.

        Returns:
            str: The command to start the pasls server

        """
        # Check if pasls is already in PATH
        pasls_in_path = shutil.which("pasls")
        if pasls_in_path:
            log.info(f"Found pasls in PATH: {pasls_in_path}")
            return quote_windows_path(pasls_in_path)

        pasls_dir = cls.ls_resources_dir(solidlsp_settings)
        os.makedirs(pasls_dir, exist_ok=True)

        # Clean up old files from previous sessions
        cls._cleanup_old_files(pasls_dir)

        # Use RuntimeDependencyCollection for platform detection
        # Asset names follow zen010101/pascal-language-server release convention:
        # pasls-{cpu_arch}-{os}.{ext} where cpu_arch is x86_64/aarch64/i386
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Linux (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/pasls-x86_64-linux.tar.gz",
                    platform_id="linux-x64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Linux (arm64)",
                    url=f"{cls.PASLS_RELEASES_URL}/pasls-aarch64-linux.tar.gz",
                    platform_id="linux-arm64",
                    archive_type="gztar",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for macOS (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/pasls-x86_64-darwin.zip",
                    platform_id="osx-x64",
                    archive_type="zip",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for macOS (arm64)",
                    url=f"{cls.PASLS_RELEASES_URL}/pasls-aarch64-darwin.zip",
                    platform_id="osx-arm64",
                    archive_type="zip",
                    binary_name="pasls",
                ),
                RuntimeDependency(
                    id="PascalLanguageServer",
                    description="Pascal Language Server for Windows (x64)",
                    url=f"{cls.PASLS_RELEASES_URL}/pasls-x86_64-win64.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="pasls.exe",
                ),
            ]
        )

        pasls_executable_path = deps.binary_path(pasls_dir)

        # Determine if download is needed
        need_download = False
        latest_version = None
        checksums = None

        if not os.path.exists(pasls_executable_path):
            # First install
            log.info("pasls not found, will download...")
            need_download = True
            latest_version = cls._get_latest_version()
            checksums = cls._get_checksums()
        elif cls._should_check_update(pasls_dir):
            # Check for updates
            log.debug("Checking for pasls updates...")
            latest_version = cls._get_latest_version()
            local_version = cls._get_local_version(pasls_dir)

            if cls._is_newer_version(latest_version, local_version):
                log.info(f"New pasls version available: {latest_version} (current: {local_version})")

                # Check Windows file locking
                if cls._is_file_locked(pasls_executable_path):
                    log.warning("Cannot update pasls: file is in use. Will retry next time.")
                else:
                    need_download = True
                    checksums = cls._get_checksums()
            else:
                log.debug(f"pasls is up to date: {local_version}")

        if need_download:
            if cls._atomic_install(pasls_dir, deps, checksums):
                # Update metadata after successful installation
                if latest_version:
                    cls._save_local_version(pasls_dir, latest_version)
                else:
                    # API failed but download succeeded, record placeholder version
                    cls._save_local_version(pasls_dir, "unknown")
                cls._update_last_check(pasls_dir)
            else:
                # Installation failed, use existing version if available
                if not os.path.exists(pasls_executable_path):
                    raise RuntimeError("Failed to install pasls and no local version available")
                log.warning("Update failed, using existing version")

        # Update check time even if no update (avoid frequent checks)
        if not need_download and cls._should_check_update(pasls_dir):
            cls._update_last_check(pasls_dir)

        assert os.path.exists(pasls_executable_path), f"pasls executable not found at {pasls_executable_path}"

        # Ensure execute permission
        try:
            os.chmod(pasls_executable_path, 0o755)
        except OSError:
            pass  # May fail on Windows, ignore

        log.info(f"Using pasls at: {pasls_executable_path}")
        return quote_windows_path(pasls_executable_path)

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Pascal Language Server.

        pasls (genericptr/pascal-language-server) reads compiler paths from:
        1. Environment variables (PP, FPCDIR, LAZARUSDIR) via TCodeToolsOptions.InitWithEnvironmentVariables
        2. Lazarus config files via GuessCodeToolConfig

        We only pass target OS/CPU in initializationOptions if explicitly set.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        # Build initializationOptions from environment variables
        # pasls reads these to configure CodeTools:
        # - PP: Path to FPC compiler executable
        # - FPCDIR: Path to FPC source directory
        # - LAZARUSDIR: Path to Lazarus directory (only needed for LCL projects)
        # - FPCTARGET: Target OS
        # - FPCTARGETCPU: Target CPU
        initialization_options: dict = {}

        env_vars = ["PP", "FPCDIR", "LAZARUSDIR", "FPCTARGET", "FPCTARGETCPU"]
        for var in env_vars:
            value = os.environ.get(var, "")
            if value:
                initialization_options[var] = value

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "didSave": True,
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                        },
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "quickfix",
                                    "refactor",
                                    "refactor.extract",
                                    "refactor.inline",
                                    "refactor.rewrite",
                                    "source",
                                    "source.organizeImports",
                                ]
                            }
                        },
                    },
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True},
                    "configuration": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                    },
                },
            },
            "initializationOptions": initialization_options,
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }

        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """
        Starts the Pascal Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def register_capability_handler(params: dict) -> None:
            log.debug(f"Capability registered: {params}")
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            # Mark server as ready when we see initialization messages
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                log.info("Pascal language server ready signal detected")
                self.server_ready.set()

        def publish_diagnostics(params: dict) -> None:
            log.debug(f"Diagnostics: {params}")
            return

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_log_message)
        self.server.on_notification("textDocument/publishDiagnostics", publish_diagnostics)
        self.server.on_notification("$/progress", do_nothing)

        log.info("Starting Pascal server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Pascal server: {init_response}")

        # Verify capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities

        # Check for various capabilities
        if "completionProvider" in capabilities:
            log.info("Pascal server supports code completion")
        if "definitionProvider" in capabilities:
            log.info("Pascal server supports go to definition")
        if "referencesProvider" in capabilities:
            log.info("Pascal server supports find references")
        if "documentSymbolProvider" in capabilities:
            log.info("Pascal server supports document symbols")

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for Pascal language server to be ready...")
        if not self.server_ready.wait(timeout=5.0):
            # pasls may not send explicit ready signals, so we proceed after timeout
            log.info("Timeout waiting for Pascal server ready signal, assuming server is ready")
            self.server_ready.set()
        else:
            log.info("Pascal server initialization complete")

    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        Check if a directory should be ignored for Pascal projects.
        Common Pascal/Lazarus directories to ignore.
        """
        ignored_dirs = {
            "lib",
            "backup",
            "__history",
            "__recovery",
            "bin",
            ".git",
            ".svn",
            ".hg",
            "node_modules",
        }
        return dirname.lower() in ignored_dirs
