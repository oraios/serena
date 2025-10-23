import logging
import os
from collections.abc import Generator
from typing import TypeVar

from serena.util.file_system import find_all_non_ignored_files
from solidlsp.ls_config import Language

T = TypeVar("T")

log = logging.getLogger(__name__)


def iter_subclasses(cls: type[T], recursive: bool = True) -> Generator[type[T], None, None]:
    """Iterate over all subclasses of a class. If recursive is True, also iterate over all subclasses of all subclasses."""
    for subclass in cls.__subclasses__():
        yield subclass
        if recursive:
            yield from iter_subclasses(subclass, recursive)


def detect_language_from_file(file_path: str) -> Language | None:
    """
    Detect the programming language of a file based on its extension.

    :param file_path: Path to the file
    :return: Language enum if detected, None otherwise
    """
    filename = os.path.basename(file_path)

    for language in Language.iter_all(include_experimental=True):
        matcher = language.get_source_fn_matcher()
        if matcher.is_relevant_filename(filename):
            return language

    return None


def determine_programming_language_composition(repo_path: str) -> tuple[dict[str, float], int]:
    """
    Determine the programming language composition of a repository.

    :param repo_path: Path to the repository to analyze

    :return: Tuple of (language_percentages, total_file_count)
        - language_percentages: Dictionary mapping language names to percentages
        - total_file_count: Total number of non-ignored files found
    """
    all_files = find_all_non_ignored_files(repo_path)

    if not all_files:
        return {}, 0

    # Count files for each language
    language_counts: dict[str, int] = {}
    total_files = len(all_files)

    for language in Language.iter_all(include_experimental=False):
        matcher = language.get_source_fn_matcher()
        count = 0

        for file_path in all_files:
            # Use just the filename for matching, not the full path
            filename = os.path.basename(file_path)
            if matcher.is_relevant_filename(filename):
                count += 1

        if count > 0:
            language_counts[str(language)] = count

    # Convert counts to percentages
    language_percentages: dict[str, float] = {}
    for language_name, count in language_counts.items():
        percentage = (count / total_files) * 100
        language_percentages[language_name] = round(percentage, 2)

    return language_percentages, total_files
