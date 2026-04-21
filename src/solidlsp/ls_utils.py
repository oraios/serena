"""
This file contains various utility functions like I/O operations, handling paths, etc.
"""

import gzip
import hashlib
import logging
import os
import platform
import shutil
import subprocess
import tarfile
import uuid
import zipfile
from enum import Enum
from pathlib import Path, PurePath
from typing import Literal, cast
from urllib.parse import urlparse

import charset_normalizer
import requests

from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_types import UnifiedSymbolInformation

log = logging.getLogger(__name__)


class InvalidTextLocationError(Exception):
    pass


class TextUtils:
    """
    Utilities for text operations.
    """

    @staticmethod
    def get_line_col_from_index(text: str, index: int) -> tuple[int, int]:
        """
        Returns the zero-indexed line and column number of the given index in the given text
        """
        l = 0
        c = 0
        idx = 0
        while idx < index:
            if text[idx] == "\n":
                l += 1
                c = 0
            else:
                c += 1
            idx += 1

        return l, c

    @staticmethod
    def get_index_from_line_col(text: str, line: int, col: int) -> int:
        """
        Returns the index of the given zero-indexed line and column number in the given text
        """
        idx = 0
        while line > 0:
            if idx >= len(text):
                raise InvalidTextLocationError
            if text[idx] == "\n":
                line -= 1
            idx += 1
        idx += col
        return idx

    @staticmethod
    def _get_updated_position_from_line_and_column_and_edit(l: int, c: int, text_to_be_inserted: str) -> tuple[int, int]:
        """
        Utility function to get the position of the cursor after inserting text at a given line and column.
        """
        num_newlines_in_gen_text = text_to_be_inserted.count("\n")
        if num_newlines_in_gen_text > 0:
            l += num_newlines_in_gen_text
            c = len(text_to_be_inserted.split("\n")[-1])
        else:
            c += len(text_to_be_inserted)
        return (l, c)

    @staticmethod
    def delete_text_between_positions(text: str, start_line: int, start_col: int, end_line: int, end_col: int) -> tuple[str, str]:
        """
        Deletes the text between the given start and end positions.
        Returns the modified text and the deleted text.
        """
        del_start_idx = TextUtils.get_index_from_line_col(text, start_line, start_col)
        del_end_idx = TextUtils.get_index_from_line_col(text, end_line, end_col)

        deleted_text = text[del_start_idx:del_end_idx]
        new_text = text[:del_start_idx] + text[del_end_idx:]
        return new_text, deleted_text

    @staticmethod
    def insert_text_at_position(text: str, line: int, col: int, text_to_be_inserted: str) -> tuple[str, int, int]:
        """
        Inserts the given text at the given line and column.
        Returns the modified text and the new line and column.
        """
        try:
            change_index = TextUtils.get_index_from_line_col(text, line, col)
        except InvalidTextLocationError:
            num_lines_in_text = text.count("\n") + 1
            max_line = num_lines_in_text - 1
            if line == max_line + 1 and col == 0:  # trying to insert at new line after full text
                # insert at end, adding missing newline
                change_index = len(text)
                text_to_be_inserted = "\n" + text_to_be_inserted
            else:
                raise
        new_text = text[:change_index] + text_to_be_inserted + text[change_index:]
        new_l, new_c = TextUtils._get_updated_position_from_line_and_column_and_edit(line, col, text_to_be_inserted)
        return new_text, new_l, new_c

    @staticmethod
    def get_text_in_range(text: str, start_line: int, start_col: int, end_line: int, end_col: int) -> str:
        """
        Returns the text between the given start and end positions.
        """
        start_idx = TextUtils.get_index_from_line_col(text, start_line, start_col)
        end_idx = TextUtils.get_index_from_line_col(text, end_line, end_col)
        return text[start_idx:end_idx]


class PathUtils:
    """
    Utilities for platform-agnostic path operations.
    """

    @staticmethod
    def uri_to_path(uri: str) -> str:
        """
        Converts a URI to a file path. Works on both Linux and Windows.

        This method was obtained from https://stackoverflow.com/a/61922504
        """
        try:
            from urllib.parse import unquote, urlparse
            from urllib.request import url2pathname
        except ImportError:
            # backwards compatibility (Python 2)
            from urllib.parse import unquote as unquote_py2
            from urllib.request import url2pathname as url2pathname_py2

            from urlparse import urlparse as urlparse_py2

            unquote = unquote_py2
            url2pathname = url2pathname_py2
            urlparse = urlparse_py2
        parsed = urlparse(uri)
        host = f"{os.path.sep}{os.path.sep}{parsed.netloc}{os.path.sep}"
        path = os.path.normpath(os.path.join(host, url2pathname(unquote(parsed.path))))
        return path

    @staticmethod
    def path_to_uri(path: str) -> str:
        """
        Converts a file path to a file URI (file:///...).
        """
        return str(Path(path).absolute().as_uri())

    @staticmethod
    def is_glob_pattern(pattern: str) -> bool:
        """Check if a pattern contains glob-specific characters."""
        return any(c in pattern for c in "*?[]!")

    @staticmethod
    def get_relative_path(path: str, base_path: str) -> str | None:
        """
        Gets relative path if it's possible (paths should be on the same drive),
        returns `None` otherwise.
        """
        if PurePath(path).drive == PurePath(base_path).drive:
            rel_path = str(PurePath(os.path.relpath(path, base_path)))
            return rel_path
        return None


class FileUtils:
    """
    Utility functions for file operations.
    """

    @staticmethod
    def read_file(file_path: str, encoding: str) -> str:
        """
        Reads the file at the given path using the given encoding and returns the contents as a string.
        If decoding fails, tries to detect the encoding using charset_normalizer.

        Raises FileNotFoundError if the file does not exist.
        """
        if not os.path.exists(file_path):
            log.error(f"Failed to read '{file_path}': File does not exist.")
            raise FileNotFoundError(f"File read '{file_path}' failed: File does not exist.")
        try:
            try:
                with open(file_path, encoding=encoding) as inp_file:
                    return inp_file.read()
            except UnicodeDecodeError as ude:
                results = charset_normalizer.from_path(file_path)
                match = results.best()
                if match:
                    log.warning(
                        f"Could not decode {file_path} with encoding='{encoding}'; using best match '{match.encoding}' instead",
                    )
                    return match.raw.decode(match.encoding)
                raise ude
        except Exception as exc:
            log.error(f"Failed to read '{file_path}' with encoding '{encoding}': {exc}")
            raise exc

    @staticmethod
    def download_file(url: str, target_path: str) -> None:
        """
        Downloads the file from the given URL to the given {target_path}
        """
        FileUtils.download_file_verified(url, target_path)

    @staticmethod
    def download_file_verified(
        url: str,
        target_path: str,
        expected_sha256: str | None = None,
        allowed_hosts: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        """
        Downloads a file from ``url`` to ``target_path`` with optional integrity and host validation.
        """
        # validating the requested host
        FileUtils._validate_download_host(url, allowed_hosts)

        # streaming the download into a temporary file
        target_directory = os.path.dirname(target_path) or "."
        os.makedirs(target_directory, exist_ok=True)
        temp_file_path = str(PurePath(target_directory, f".{Path(target_path).name}.{uuid.uuid4().hex}.download"))
        response: requests.Response | None = None
        try:
            response = requests.get(url, stream=True, timeout=60)
            if response.status_code != 200:
                log.error(f"Error downloading file '{url}': {response.status_code} {response.text}")
                raise SolidLSPException("Error downloading file.")

            FileUtils._validate_download_host(response.url, allowed_hosts)

            with open(temp_file_path, "wb") as output_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output_file.write(chunk)

            FileUtils._verify_sha256_if_configured(temp_file_path, expected_sha256)

            os.replace(temp_file_path, target_path)
        except Exception as exc:
            log.error(f"Error downloading file '{url}': {exc}")
            raise SolidLSPException("Error downloading file.") from None
        finally:
            if response is not None:
                response.close()
            if os.path.exists(temp_file_path):
                Path.unlink(Path(temp_file_path))

    @staticmethod
    def download_and_extract_archive(url: str, target_path: str, archive_type: str) -> None:
        """
        Downloads the archive from the given URL having format {archive_type} and extracts it to the given {target_path}
        """
        FileUtils.download_and_extract_archive_verified(url, target_path, archive_type)

    @staticmethod
    def download_and_extract_archive_verified(
        url: str,
        target_path: str,
        archive_type: str,
        expected_sha256: str | None = None,
        allowed_hosts: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        """
        Downloads an archive from ``url`` and extracts it safely into ``target_path``.
        """
        try:
            # preparing the temporary download location
            tmp_files: list[str] = []
            tmp_file_name = str(PurePath(os.path.expanduser("~"), "solidlsp_tmp", uuid.uuid4().hex))
            os.makedirs(os.path.dirname(tmp_file_name), exist_ok=True)

            # downloading the archive with optional verification
            FileUtils.download_file_verified(url, tmp_file_name, expected_sha256=expected_sha256, allowed_hosts=allowed_hosts)
            tmp_files.append(tmp_file_name)

            # extracting the archive according to its format
            if archive_type in ["tar", "gztar", "bztar", "xztar"]:
                os.makedirs(target_path, exist_ok=True)
                FileUtils._extract_tar_archive(tmp_file_name, target_path, archive_type)
            elif archive_type == "zip":
                os.makedirs(target_path, exist_ok=True)
                FileUtils._extract_zip_archive(tmp_file_name, target_path)
            elif archive_type == "zip.gz":
                os.makedirs(target_path, exist_ok=True)
                tmp_file_name_ungzipped = tmp_file_name + ".zip"
                tmp_files.append(tmp_file_name_ungzipped)
                with gzip.open(tmp_file_name, "rb") as f_in, open(tmp_file_name_ungzipped, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                FileUtils._extract_zip_archive(tmp_file_name_ungzipped, target_path)
            elif archive_type == "gz":
                target_directory = os.path.dirname(target_path) or "."
                os.makedirs(target_directory, exist_ok=True)
                temp_output_path = str(PurePath(target_directory, f".{Path(target_path).name}.{uuid.uuid4().hex}.extract"))
                tmp_files.append(temp_output_path)
                with gzip.open(tmp_file_name, "rb") as f_in, open(temp_output_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.replace(temp_output_path, target_path)
            elif archive_type == "binary":
                target_directory = os.path.dirname(target_path) or "."
                os.makedirs(target_directory, exist_ok=True)
                shutil.move(tmp_file_name, target_path)
                tmp_files.remove(tmp_file_name)
            else:
                log.error(f"Unknown archive type '{archive_type}' for extraction")
                raise SolidLSPException(f"Unknown archive type '{archive_type}'")
        except Exception as exc:
            log.error(f"Error extracting archive '{tmp_file_name}' obtained from '{url}': {exc}")
            raise SolidLSPException("Error extracting archive.") from exc
        finally:
            for tmp_file_name in tmp_files:
                if os.path.exists(tmp_file_name):
                    Path.unlink(Path(tmp_file_name))

    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        """
        Calculates the SHA256 checksum of a file.
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as input_file:
            for chunk in iter(lambda: input_file.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @staticmethod
    def _verify_sha256_if_configured(file_path: str, expected_sha256: str | None) -> None:
        """
        Verifies the SHA256 checksum of a file when an expected value is provided.
        """
        if expected_sha256 is None:
            return

        actual_sha256 = FileUtils.calculate_sha256(file_path)
        if actual_sha256.lower() != expected_sha256.lower():
            raise SolidLSPException(f"Checksum verification failed for '{file_path}': expected {expected_sha256}, got {actual_sha256}")

    @staticmethod
    def _validate_download_host(url: str, allowed_hosts: tuple[str, ...] | list[str] | None) -> None:
        """
        Validates that a download URL resolves to one of the configured hosts.
        """
        if not allowed_hosts:
            return

        hostname = urlparse(url).hostname
        normalized_allowed_hosts = {host.lower() for host in allowed_hosts}
        if hostname is None or hostname.lower() not in normalized_allowed_hosts:
            raise SolidLSPException(
                f"Refusing to download from host '{hostname or '<unknown>'}'; allowed hosts: {sorted(normalized_allowed_hosts)}"
            )

    @staticmethod
    def _validate_extraction_path(member_name: str, target_path: str) -> str:
        """
        Validates that an archive member stays within the extraction root and returns its destination path.
        """
        normalized_parts = Path(member_name).parts
        if any(part == ".." for part in normalized_parts):
            raise SolidLSPException(f"Unsafe archive member '{member_name}': path traversal is not allowed")

        absolute_target_path = os.path.abspath(target_path)
        absolute_member_path = os.path.abspath(os.path.join(target_path, member_name))
        if not (absolute_member_path.startswith(absolute_target_path + os.sep) or absolute_member_path == absolute_target_path):
            raise SolidLSPException(f"Unsafe archive member '{member_name}': path escapes extraction directory")

        return absolute_member_path

    @staticmethod
    def _extract_zip_archive(archive_path: str, target_path: str) -> None:
        """
        Extracts a ZIP archive safely while preserving Unix permissions when available.
        """
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            for zip_info in zip_ref.infolist():
                extracted_path = FileUtils._validate_extraction_path(zip_info.filename, target_path)

                if zip_info.is_dir():
                    os.makedirs(extracted_path, exist_ok=True)
                    continue

                os.makedirs(os.path.dirname(extracted_path), exist_ok=True)
                with zip_ref.open(zip_info, "r") as source_file, open(extracted_path, "wb") as output_file:
                    shutil.copyfileobj(source_file, output_file)

                ZIP_SYSTEM_UNIX = 3
                if zip_info.create_system == ZIP_SYSTEM_UNIX:
                    attrs = (zip_info.external_attr >> 16) & 0o777
                    if attrs:
                        os.chmod(extracted_path, attrs)

    @staticmethod
    def _extract_tar_archive(archive_path: str, target_path: str, archive_type: str) -> None:
        """
        Extracts a tar archive safely into the target directory.
        """
        archive_mode_by_type = {
            "tar": "r:",
            "gztar": "r:gz",
            "bztar": "r:bz2",
            "xztar": "r:xz",
        }
        tar_mode = cast(Literal["r:", "r:gz", "r:bz2", "r:xz"], archive_mode_by_type[archive_type])

        with tarfile.open(archive_path, tar_mode) as tar_ref:
            for tar_member in tar_ref.getmembers():
                FileUtils._validate_extraction_path(tar_member.name, target_path)

            tar_ref.extractall(target_path)


class PlatformId(str, Enum):
    WIN_x86 = "win-x86"
    WIN_x64 = "win-x64"
    WIN_arm64 = "win-arm64"
    OSX = "osx"
    OSX_x64 = "osx-x64"
    OSX_arm64 = "osx-arm64"
    LINUX_x86 = "linux-x86"
    LINUX_x64 = "linux-x64"
    LINUX_arm64 = "linux-arm64"
    LINUX_MUSL_x64 = "linux-musl-x64"
    LINUX_MUSL_arm64 = "linux-musl-arm64"

    def is_windows(self) -> bool:
        return self.value.startswith("win")


class DotnetVersion(str, Enum):
    V4 = "4"
    V6 = "6"
    V7 = "7"
    V8 = "8"
    V9 = "9"
    VMONO = "mono"


class PlatformUtils:
    """
    This class provides utilities for platform detection and identification.
    """

    @classmethod
    def get_platform_id(cls) -> PlatformId:
        """
        Returns the platform id for the current system
        """
        system = platform.system()
        machine = platform.machine()
        bitness = platform.architecture()[0]
        if system == "Windows" and machine == "":
            machine = cls._determine_windows_machine_type()
        system_map = {"Windows": "win", "Darwin": "osx", "Linux": "linux"}
        machine_map = {
            "AMD64": "x64",
            "x86_64": "x64",
            "i386": "x86",
            "i686": "x86",
            "aarch64": "arm64",
            "arm64": "arm64",
            "ARM64": "arm64",
        }
        if system in system_map and machine in machine_map:
            platform_id = system_map[system] + "-" + machine_map[machine]
            if system == "Linux" and bitness == "64bit":
                libc = platform.libc_ver()[0]
                if libc != "glibc":
                    # Format: linux-musl-arch (e.g., linux-musl-arm64)
                    platform_id = f"{system_map[system]}-{libc}-{machine_map[machine]}"
            return PlatformId(platform_id)
        else:
            raise SolidLSPException(f"Unknown platform: {system=}, {machine=}, {bitness=}")

    @staticmethod
    def _determine_windows_machine_type() -> str:
        import ctypes
        from ctypes import wintypes

        class SYSTEM_INFO(ctypes.Structure):
            class _U(ctypes.Union):
                class _S(ctypes.Structure):
                    _fields_ = [("wProcessorArchitecture", wintypes.WORD), ("wReserved", wintypes.WORD)]

                _fields_ = [("dwOemId", wintypes.DWORD), ("s", _S)]
                _anonymous_ = ("s",)

            _fields_ = [
                ("u", _U),
                ("dwPageSize", wintypes.DWORD),
                ("lpMinimumApplicationAddress", wintypes.LPVOID),
                ("lpMaximumApplicationAddress", wintypes.LPVOID),
                ("dwActiveProcessorMask", wintypes.LPVOID),
                ("dwNumberOfProcessors", wintypes.DWORD),
                ("dwProcessorType", wintypes.DWORD),
                ("dwAllocationGranularity", wintypes.DWORD),
                ("wProcessorLevel", wintypes.WORD),
                ("wProcessorRevision", wintypes.WORD),
            ]
            _anonymous_ = ("u",)

        sys_info = SYSTEM_INFO()
        ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(sys_info))  # type: ignore

        arch_map = {
            9: "AMD64",
            5: "ARM",
            12: "arm64",
            6: "Intel Itanium-based",
            0: "i386",
        }

        return arch_map.get(sys_info.wProcessorArchitecture, f"Unknown ({sys_info.wProcessorArchitecture})")

    @staticmethod
    def get_dotnet_version() -> DotnetVersion:
        """
        Returns the dotnet version for the current system
        """
        try:
            result = subprocess.run(["dotnet", "--list-runtimes"], capture_output=True, check=True)
            available_version_cmd_output = []
            for line in result.stdout.decode("utf-8").split("\n"):
                if line.startswith("Microsoft.NETCore.App"):
                    version_cmd_output = line.split(" ")[1]
                    available_version_cmd_output.append(version_cmd_output)

            if not available_version_cmd_output:
                raise SolidLSPException("dotnet not found on the system")

            # Check for supported versions in order of preference (latest first)
            for version_cmd_output in available_version_cmd_output:
                if version_cmd_output.startswith("9"):
                    return DotnetVersion.V9
                if version_cmd_output.startswith("8"):
                    return DotnetVersion.V8
                if version_cmd_output.startswith("7"):
                    return DotnetVersion.V7
                if version_cmd_output.startswith("6"):
                    return DotnetVersion.V6
                if version_cmd_output.startswith("4"):
                    return DotnetVersion.V4

            # If no supported version found, raise exception with all available versions
            raise SolidLSPException(
                f"No supported dotnet version found. Available versions: {', '.join(available_version_cmd_output)}. Supported versions: 4, 6, 7, 8, 9"
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                result = subprocess.run(["mono", "--version"], capture_output=True, check=True)
                return DotnetVersion.VMONO
            except (FileNotFoundError, subprocess.CalledProcessError):
                raise SolidLSPException("dotnet or mono not found on the system")


class SymbolUtils:
    @staticmethod
    def symbol_tree_contains_name(roots: list[UnifiedSymbolInformation], name: str) -> bool:
        """
        Check if any symbol in the tree has a name matching the given name.
        """
        for symbol in roots:
            if symbol["name"] == name:
                return True
            if SymbolUtils.symbol_tree_contains_name(symbol["children"], name):
                return True
        return False
