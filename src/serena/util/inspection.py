import logging
import os
from collections.abc import Callable, Iterator
from typing import TypeVar

from serena.util.file_system import find_all_non_ignored_files
from solidlsp.ls_config import Language

T = TypeVar("T")

log = logging.getLogger(__name__)


def iter_subclasses(
    cls: type[T], recursive: bool = True, inclusion_predicate: Callable[[type[T]], bool] = lambda t: True
) -> Iterator[type[T]]:
    """Iterate over all subclasses of a class.

    :param cls: The class whose subclasses to iterate over.
    :param recursive: If True, also iterate over all subclasses of all subclasses.
    :param inclusion_predicate: a predicate function to decide whether to include a subclass in the result
    """
    for subclass in cls.__subclasses__():
        if inclusion_predicate(subclass):
            yield subclass
        if recursive:
            yield from iter_subclasses(subclass, recursive, inclusion_predicate)


def determine_programming_language_composition(repo_path: str) -> dict[Language, float]:
    """
    Determine the programming language composition of a repository.

    Percentages are computed relative to the number of files that match at least
    one supported language, not the total file count.  This prevents files that
    belong to no supported language (images, plain text, licenses, lock files, etc.)
    from diluting language percentages in repositories where such files dominate.

    :param repo_path: Path to the repository to analyze
    :return: Dictionary mapping languages to percentages of recognised source files
        matching each language (denominator = files matched by at least one language)
    """
    all_files = find_all_non_ignored_files(repo_path)

    if not all_files:
        return {}

    # collect all language matchers once
    all_languages = list(Language.iter_all(include_experimental=False))
    matchers = {lang: lang.get_source_fn_matcher() for lang in all_languages}

    # count files per language in a single pass over the files
    language_counts: dict[Language, int] = {}
    recognised_files = 0
    for file_path in all_files:
        # Use just the filename for matching, not the full path
        filename = os.path.basename(file_path)
        matched_any = False
        for lang, matcher in matchers.items():
            if matcher.is_relevant_filename(filename):
                language_counts[lang] = language_counts.get(lang, 0) + 1
                matched_any = True
        if matched_any:
            recognised_files += 1

    if recognised_files == 0:
        return {}

    # convert to percentages relative to recognised source files only
    return {lang: round(count / recognised_files * 100, 2) for lang, count in language_counts.items()}
