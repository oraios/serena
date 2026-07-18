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
import tempfile
import uuid
import zipfile
from enum import Enum
from pathlib import Path, PurePath
from typing import Literal, cast
from urllib.parse import urlparse

import charset_normalizer
import requests

from solidlsp.ls_exceptions import InvalidTextLocationError, SolidLSPException
from solidlsp.ls_types import UnifiedSymbolInformation

log = logging.getLogger(__name__)


class TextStepper:
    r"""
    A utility class for stepping through a text string line by line, keeping track of the current line and column numbers.

    It handles the newline sequences "\n", "\r\n", and "\r" as defined by the Language Server Protocol (LSP).
    However, note that files read through `FileUtils.read_file` will contain only "\n" (LF).
    """

    def __init__(self, chars: str):
        self._chars = chars
        self._len = len(chars)
        self.line = 0
        """
        the current 0-based line index
        """
        self.col = 0
        """
        the current 0-based column index
        """
        self.idx = 0
        """
        the current 0-based index in the full text.
        The index specifies the next character to be processed, i.e. if this is
        the length of the text, then the end of the text has been reached.
        It specifies a location in the same way as a cursor insertion position:
        cursor at the very beginning (idx=0) means insert before the first character.
        """
        self.is_newline = False
        """
        whether the last step processed a full line ending in a line break
        """
        self.prev_line_start_idx = 0
        """
        start index of the last fully processed line (inclusive)    
        """
        self.prev_line_end_idx = 0
        """
        end of the last fully processed line (exclusive), excluding newline characters
        """
        self.line_start_idx = 0
        """
        start of the current, not yet completed line (inclusive)
        """

    def _get_char(self, idx: int) -> str | None:
        if idx < 0 or idx >= self._len:
            return None
        return self._chars[idx]

    def step_line(self) -> bool:
        """
        Processes the next line in the text, advancing past the next newline sequence or,
        if no further newline is present, to the end of the text.

        :return: True if processing was possible, False if the end of the text had already been reached
            (idx not advanced)
        """
        if self.idx >= self._len:
            return False

        # find the next newline sequence
        # Note: LSP defines that a newline is given by either "\n", "\r\n", or "\r" on its own
        # Reference: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.18/specification/#textDocuments
        # The search for "\r" is bounded by the position of the next "\n".
        lf_idx = self._chars.find("\n", self.idx)
        cr_idx = self._chars.find("\r", self.idx, lf_idx if lf_idx != -1 else self._len)
        if cr_idx != -1:
            newline_start_idx = cr_idx
            newline_end_idx = cr_idx + 2 if self._get_char(cr_idx + 1) == "\n" else cr_idx + 1
        elif lf_idx != -1:
            newline_start_idx = lf_idx
            newline_end_idx = lf_idx + 1
        else:
            newline_start_idx = None
            newline_end_idx = None

        # advance past the newline sequence or, in its absence, consume the trailing line
        if newline_start_idx is not None and newline_end_idx is not None:
            self.idx = newline_end_idx
            self.line += 1
            self.col = 0
            self.is_newline = True
            self.prev_line_start_idx = self.line_start_idx
            self.prev_line_end_idx = newline_start_idx
            self.line_start_idx = newline_end_idx
        else:
            self.idx = self._len
            self.col = self._len - self.line_start_idx
            self.is_newline = False
        return True

    def step_to(self, line: int, col: int):
        """
        Steps through the text until the given line and column are reached, or until the end of the text is reached.

        :param line: the 0-based line number to step to
        :param col: the 0-based column number to step to
        """
        while self.line < line:
            if not self.step_line():
                break
        if self.line != line:
            raise InvalidTextLocationError
        self.idx += col
        self.col = col

    def process_all(self):
        """
        Processes all characters in the text, updating the line and column numbers accordingly.
        """
        while self.step_line():
            pass

    def get_last_line(self, with_end: bool) -> str:
        """
        Returns the last line processed, optionally including the newline character(s) at the end
        """
        start_idx = self.prev_line_start_idx
        end_idx = self.prev_line_end_idx if not with_end else self.line_start_idx
        return self._chars[start_idx:end_idx]

    def process_all_gather_lines(self, with_ends: bool) -> list[str]:
        """
        Processes all characters in the text and returns a list of lines

        :param with_ends: whether to include the newline character(s) at the end of each line
        :return: the list of lines
        """
        lines = []
        while self.step_line():
            if self.is_newline:
                lines.append(self.get_last_line(with_end=with_ends))

        # add the last line (which was not followed by a newline), even if empty
        last_line = self._chars[self.line_start_idx :]
        lines.append(last_line)

        return lines


class TextUtils:
    """
    Utilities for text operations.
    """

    @staticmethod
    def get_line_col_from_index(text: str, index: int) -> tuple[int, int]:
        """
        :param text: the text in which the index is to be located
        :param index: the 0-based index in the text
        :return: a tuple (0-based line number, 0-based column number) corresponding to the index in the text
        """
        # step over full lines; once the line containing the index has been processed, compute
        # the position from the difference to the respective line's start index
        text_stepper = TextStepper(text)
        while text_stepper.step_line():
            if text_stepper.idx > index:
                if text_stepper.is_newline:
                    # position was stepped over as part of the previous line
                    if index > text_stepper.prev_line_end_idx:
                        # edge case: the index points into a multi-character newline sequence ("\r\n");
                        # map this to the beginning of the following line
                        return text_stepper.line, 0
                    return text_stepper.line - 1, index - text_stepper.prev_line_start_idx
                else:
                    # position was stepped over as part of the current line (which was not followed by a newline)
                    return text_stepper.line, index - text_stepper.line_start_idx

        # handle the case where the end of the text was reached without stepping past the index
        if index > text_stepper.idx:
            raise InvalidTextLocationError(f"{index=}")
        return text_stepper.line, text_stepper.col

    @classmethod
    def get_line_from_index(cls, text: str, index: int) -> int:
        """
        :param text: the text in which the index is to be located
        :param index: the 0-based index in the text
        :return: the 0-based line number corresponding to the index in the text
        """
        return cls.get_line_col_from_index(text, index)[0]

    @staticmethod
    def get_index_from_line_col(text: str, line: int, col: int) -> int:
        """
        :param text: the text in which the coordinates are to be located
        :param line: the 0-based line number
        :param col: the 0-based column number
        :return: the corresponding 0-based index in the text
        """
        # step over full lines until the requested line is reached
        text_stepper = TextStepper(text)
        while text_stepper.line < line:
            if not text_stepper.step_line():
                raise InvalidTextLocationError(f"{line=}, {col=}")

        return text_stepper.line_start_idx + col

    @staticmethod
    def _get_updated_position_from_line_and_column_and_edit(l: int, c: int, text_to_be_inserted: str) -> tuple[int, int]:
        """
        :param l: the 0-based line number before the edit
        :param c: the 0-based column number before the edit
        :param text_to_be_inserted: the text that was inserted at the given position
        :return: the updated 0-based line and column numbers after the edit (end of insertion)
        """
        text_stepper = TextStepper(text_to_be_inserted)
        text_stepper.process_all()
        if text_stepper.line > 0:
            l += text_stepper.line
            c = text_stepper.col
        else:
            c += text_stepper.col
        return l, c

    @staticmethod
    def delete_text_between_positions(text: str, start_line: int, start_col: int, end_line: int, end_col: int) -> tuple[str, str]:
        """
        Deletes the text between the given start and end positions.

        :param text: the original text
        :param start_line: the 0-based line number of the start position
        :param start_col: the 0-based column number of the start position
        :param end_line: the 0-based line number of the end position
        :param end_col: the 0-based column number of the end position
        :return: a tuple containing the modified text and the deleted text
        """
        del_start_idx = TextUtils.get_index_from_line_col(text, start_line, start_col)
        try:
            del_end_idx = TextUtils.get_index_from_line_col(text, end_line, end_col)
        except InvalidTextLocationError:
            # Deleting through the final line addresses the position one line past the
            # last line (line == number of lines, col 0). When the file has no trailing
            # newline there is no closing newline to count, so get_index_from_line_col
            # cannot resolve it; that position means "end of file". Clamp to len(text).
            # (insert_text_at_position handles the same past-EOF position.)
            text_stepper = TextStepper(text)
            text_stepper.process_all()
            num_lines_in_text = text_stepper.line + 1
            if end_line == num_lines_in_text and end_col == 0:
                del_end_idx = len(text)
            else:
                raise

        deleted_text = text[del_start_idx:del_end_idx]
        new_text = text[:del_start_idx] + text[del_end_idx:]
        return new_text, deleted_text

    @staticmethod
    def insert_text_at_position(text: str, line: int, col: int, text_to_be_inserted: str) -> tuple[str, int, int]:
        """
        Inserts the given text at the given position and returns the

        :param text: the original text
        :param line: the 0-based line number where the text should be inserted
        :param col: the 0-based column number where the text should be inserted
        :param text_to_be_inserted: the text to be inserted
        :return: a tuple containing the modified text, the updated line number, and the updated column number
            (position after the inserted text)
        """
        try:
            change_index = TextUtils.get_index_from_line_col(text, line, col)
        except InvalidTextLocationError:
            text_stepper = TextStepper(text)
            text_stepper.process_all()
            num_lines_in_text = text_stepper.line + 1
            max_line = num_lines_in_text - 1
            if line == max_line + 1 and col == 0:  # trying to insert at new line after full text
                # insert at end, adding missing newline and adjusting insertion position
                # to the actual end coordinates of the text
                change_index = len(text)
                text_to_be_inserted = "\n" + text_to_be_inserted
                line = text_stepper.line
                col = text_stepper.col
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

    @classmethod
    def get_text_in_lines_range(cls, text: str, start_line: int, end_line: int) -> str:
        """
        Returns the text encompassed by the given start and end lines (inclusive).
        """
        lines = cls.split_lines(text, with_ends=True)
        return "".join(lines[start_line : end_line + 1])

    @staticmethod
    def split_lines(text: str, with_ends: bool = False) -> list[str]:
        """
        Splits the given text into lines, optionally including the newline character(s) at the end of each line.
        """
        text_stepper = TextStepper(text)
        return text_stepper.process_all_gather_lines(with_ends=with_ends)


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
        from urllib.parse import unquote, urlparse
        from urllib.request import url2pathname

        parsed = urlparse(uri)
        host = f"{os.path.sep}{os.path.sep}{parsed.netloc}{os.path.sep}"
        path = os.path.abspath(os.path.join(host, url2pathname(unquote(parsed.path))))
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
        if os.path.normcase(PurePath(path).drive) == os.path.normcase(PurePath(base_path).drive):
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

        Line endings are normalized to LF (universal newlines), irrespective of the encoding
        used to decode the file.

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
                    # Decoding the raw bytes bypasses the universal-newline translation that the
                    # open() call above applies, so normalize explicitly to keep both paths equivalent.
                    decoded = match.raw.decode(match.encoding)
                    return decoded.replace("\r\n", "\n").replace("\r", "\n")
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
        tmp_dir: str | None = None
        try:
            # preparing the temporary download location
            external_tmp_files: list[str] = []
            tmp_dir = tempfile.mkdtemp(prefix="solidlsp_")
            tmp_file_name = os.path.join(tmp_dir, uuid.uuid4().hex)

            # downloading the archive with optional verification
            FileUtils.download_file_verified(url, tmp_file_name, expected_sha256=expected_sha256, allowed_hosts=allowed_hosts)

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
                with gzip.open(tmp_file_name, "rb") as f_in, open(tmp_file_name_ungzipped, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                FileUtils._extract_zip_archive(tmp_file_name_ungzipped, target_path)
            elif archive_type == "gz":
                target_directory = os.path.dirname(target_path) or "."
                os.makedirs(target_directory, exist_ok=True)
                temp_output_path = str(PurePath(target_directory, f".{Path(target_path).name}.{uuid.uuid4().hex}.extract"))
                external_tmp_files.append(temp_output_path)
                with gzip.open(tmp_file_name, "rb") as f_in, open(temp_output_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.replace(temp_output_path, target_path)
            elif archive_type == "binary":
                target_directory = os.path.dirname(target_path) or "."
                os.makedirs(target_directory, exist_ok=True)
                shutil.move(tmp_file_name, target_path)
            else:
                log.error(f"Unknown archive type '{archive_type}' for extraction")
                raise SolidLSPException(f"Unknown archive type '{archive_type}'")
        except Exception as exc:
            log.error(f"Error extracting archive obtained from '{url}': {exc}")
            raise SolidLSPException("Error extracting archive.") from exc
        finally:
            # cleaning up any temporary files outside the temporary directory
            for tmp_file in external_tmp_files:
                if os.path.exists(tmp_file):
                    Path.unlink(Path(tmp_file))

            # removing the temporary directory
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)

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
        ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(sys_info))

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
