import os
from collections.abc import Callable


def scan_directory(
    path: str,
    recursive: bool = False,
    relative_to: str | None = None,
    is_ignored_dir: Callable[[str], bool] = lambda x: False,
    is_ignored_file: Callable[[str], bool] = lambda x: False,
) -> tuple[list[str], list[str]]:
    """
    :param path: the path to scan
    :param recursive: whether to recursively scan subdirectories
    :param relative_to: the path to which the results should be relative to; if None, provide absolute paths
    :param is_ignored_dir: a function with which to determine whether the given directory (abs. path) shall be ignored
    :param is_ignored_file: a function with which to determine whether the given file (abs. path) shall be ignored
    :return: the list of directories and files
    """
    files = []
    directories = []

    abs_path = os.path.abspath(path)
    rel_base = os.path.abspath(relative_to) if relative_to else None

    with os.scandir(abs_path) as entries:
        for entry in entries:
            entry_path = entry.path

            if rel_base:
                result_path = os.path.relpath(entry_path, rel_base)
            else:
                result_path = entry_path

            if entry.is_file():
                if not is_ignored_file(entry_path):
                    files.append(result_path)
            elif entry.is_dir():
                if not is_ignored_dir(entry_path):
                    directories.append(result_path)
                    if recursive:
                        sub_dirs, sub_files = scan_directory(
                            entry_path, recursive=True, relative_to=relative_to, is_ignored_dir=is_ignored_dir
                        )
                        files.extend(sub_files)
                        directories.extend(sub_dirs)

    return directories, files
