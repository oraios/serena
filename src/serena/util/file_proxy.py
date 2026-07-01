import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from serena.project import Project

log = logging.getLogger(__name__)


class FileProxy(ABC):
    @abstractmethod
    def get_contents(self) -> str:
        """:return: the contents of the file as a string."""

    @abstractmethod
    def get_relative_path(self) -> str:
        """:return: the relative path reported by Serena (actual relative path or encoded external path)"""

    @abstractmethod
    def is_glob_supported(self):
        """
        :return: whether the proxy supports glob filtering based on its relative path
        """


class LocalProjectFileProxy(FileProxy):
    def __init__(self, relative_path: str, project: "Project"):
        self._relative_path = relative_path
        self._project = project

    def get_contents(self) -> str:
        abs_path = os.path.join(self._project.project_root, self._relative_path)
        with open(abs_path, encoding=self._project.project_config.encoding) as f:
            return f.read()

    def get_relative_path(self) -> str:
        return self._relative_path

    def is_glob_supported(self):
        return True


class FileCollection:
    def __init__(self, file_proxies: list[FileProxy]):
        self._file_proxies = file_proxies

    def __len__(self) -> int:
        return len(self._file_proxies)

    def __iter__(self) -> Iterator[FileProxy]:
        return iter(self._file_proxies)

    @classmethod
    def from_local_project_paths(cls, relative_paths: list[str], project: "Project") -> Self:
        return cls([LocalProjectFileProxy(path, project) for path in relative_paths])

    def filter_glob(self, paths_include_glob: str | None = None, paths_exclude_glob: str | None = None) -> "FileCollection":
        """
        Filters the collection based on the given patterns.
        Note: Filtering is applied only to local project files. Other files are always retained.

        :param paths_include_glob: optional glob pattern to include files from the list
        :param paths_exclude_glob: optional glob pattern to exclude files from the list
        :return: the filtered collection
        """
        from serena.util.text_utils import GlobMatcher

        if paths_include_glob is None and paths_exclude_glob is None:
            return self

        include_glob_matcher = GlobMatcher(paths_include_glob) if paths_include_glob else None
        exclude_glob_matcher = GlobMatcher(paths_exclude_glob) if paths_exclude_glob else None

        filtered_files = []
        for f in self._file_proxies:
            if f.is_glob_supported():
                path = f.get_relative_path()
                if include_glob_matcher:
                    if not include_glob_matcher.matches(path):
                        log.debug(f"Skipping {path}: does not match include pattern {paths_include_glob}")
                        continue
                if exclude_glob_matcher:
                    if exclude_glob_matcher.matches(path):
                        log.debug(f"Skipping {path}: matches exclude pattern {paths_exclude_glob}")
                        continue
            filtered_files.append(f)

        return FileCollection(filtered_files)
