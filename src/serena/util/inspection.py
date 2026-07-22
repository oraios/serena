import logging
import os
from collections.abc import Callable, Iterator
from typing import TypeVar

from serena.util.file_system import find_all_non_ignored_files
from solidlsp.ls_config import LanguageServerId

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


def compute_language_server_support_composition(
    repo_path: str, ls_ids: list[LanguageServerId] | None = None
) -> dict[LanguageServerId, float]:
    """
    Determine the composition of a repository in terms of the language servers that can be used to analyze it.

    Percentages are computed relative to the number of files that match at least
    one supported language server, not the total file count.  This prevents files that
    belong to no supported language (images, plain text, licenses, lock files, etc.)
    from diluting language percentages in repositories where such files dominate.

    :param repo_path: path to the repository to analyze
    :param ls_ids: the list of language servers to consider; if None, use default (non-experimental ones)
    :return: dictionary mapping language servers to percentages of recognised source files
        (denominator = files matched by at least one language server)
    """
    if ls_ids is None:
        ls_ids = list(LanguageServerId.iter_all(include_experimental=False))

    all_files = find_all_non_ignored_files(repo_path)

    if not all_files:
        return {}

    matchers = {lang: lang.get_source_fn_matcher() for lang in ls_ids}

    # count files per language in a single pass over the files
    ls_file_counts: dict[LanguageServerId, int] = {}
    recognised_files = 0
    for file_path in all_files:
        # Use just the filename for matching, not the full path
        filename = os.path.basename(file_path)
        matched_any = False
        for ls_id, matcher in matchers.items():
            if matcher.is_relevant_filename(filename):
                ls_file_counts[ls_id] = ls_file_counts.get(ls_id, 0) + 1
                matched_any = True
        if matched_any:
            recognised_files += 1

    if recognised_files == 0:
        return {}

    # convert to percentages relative to recognised source files only
    return {ls_id: round(count / recognised_files * 100, 2) for ls_id, count in ls_file_counts.items()}
