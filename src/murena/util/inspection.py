import logging
import os
from collections.abc import Generator
from typing import TypeVar

from murena.util.file_system import find_all_non_ignored_files
from solidlsp.ls_config import Language

T = TypeVar("T")

log = logging.getLogger(__name__)


def iter_subclasses(cls: type[T], recursive: bool = True) -> Generator[type[T], None, None]:
    """Iterate over all subclasses of a class. If recursive is True, also iterate over all subclasses of all subclasses."""
    for subclass in cls.__subclasses__():
        yield subclass
        if recursive:
            yield from iter_subclasses(subclass, recursive)


def determine_programming_language_composition(repo_path: str) -> dict[Language, float]:
    """
    Determine the programming language composition of a repository.

    :param repo_path: Path to the repository to analyze

    :return: Dictionary mapping languages to percentages of files matching each language
    """
    all_files = find_all_non_ignored_files(repo_path)

    if not all_files:
        return {}

    # Count files for each language
    language_counts: dict[Language, int] = {}
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
            language_counts[language] = count

    # Convert counts to percentages
    language_percentages: dict[Language, float] = {}
    for language, count in language_counts.items():
        percentage = (count / total_files) * 100
        language_percentages[language] = round(percentage, 2)

    return language_percentages
