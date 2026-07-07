"""Characterization tests for ``SolidLanguageServer`` diagnostics behavior.

Phase 0 safety net: these tests pin the CURRENT behavior of the diagnostics API
(``src/solidlsp/ls.py``) before the planned refactoring of ``SolidLanguageServer``
into a facade over smaller collaborators. They intentionally encode the ACTUAL
observed behavior of the shipped code rather than any desired specification.

Covered public methods:
- ``request_text_document_diagnostics`` (pull, with published fallback)
- ``request_published_text_document_diagnostics`` (publishDiagnostics + cache fallback)
- ``get_cached_published_text_document_diagnostics`` (cache-only)

Pinned behaviors:
- start_line/end_line range filtering, including ``end_line=-1`` (no upper bound);
- ``min_severity`` filtering (1=Error .. 4=Hint), returning items with numeric
  severity <= the threshold;
- returned items are normalized ``Diagnostic`` dicts carrying ``uri``/``message``/``range``
  (and ``severity`` where present);
- consistency between the cached path and a freshly-published path;
- argument validation and the ``None`` return when nothing was published.

The fixture file ``test_repo/diagnostics_sample.py`` contains two undefined-name
references, which every supported Python backend (Pyright and ty) reports as two
Error-severity (severity == 1) diagnostics on lines 4 and 10 (0-based). The exact
message text differs per backend, so assertions match name fragments, not full text.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from test.conftest import PYTHON_LANGUAGE_BACKENDS

# Relative (to the repo root) path of the sample file with two undefined names.
DIAGNOSTICS_FILE = os.path.join("test_repo", "diagnostics_sample.py")

# 0-based lines of the two undefined-name diagnostics in the sample file.
MISSING_USER_LINE = 4
UNDEFINED_NAME_LINE = 10

# A relative path that is never opened/published in this module, so the cache
# never holds an entry for it.
NEVER_PUBLISHED_FILE = os.path.join("test_repo", "__char_diagnostics_no_such_file__.py")

# Argument combinations that must be rejected by all three public methods.
INVALID_ARG_KWARGS = [
    {"start_line": -1},
    {"start_line": 5, "end_line": 3},
    {"min_severity": 0},
    {"min_severity": 5},
]


def _start_lines(diagnostics: list) -> set[int]:
    return {d["range"]["start"]["line"] for d in diagnostics}


def _signature(diagnostics: list) -> list[tuple]:
    """Order-independent identity of a diagnostics set (message, start line, severity)."""
    return sorted((d["message"], d["range"]["start"]["line"], int(d["severity"])) for d in diagnostics)


@pytest.mark.python
@pytest.mark.parametrize("language_server", PYTHON_LANGUAGE_BACKENDS, indirect=True)
class TestCharDiagnostics:
    def test_pull_diagnostics_are_normalized_dicts(self, language_server: SolidLanguageServer) -> None:
        """request_text_document_diagnostics returns normalized Diagnostic dicts."""
        diagnostics = language_server.request_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=1)

        assert isinstance(diagnostics, list)
        assert len(diagnostics) == 2

        for diagnostic in diagnostics:
            # normalized shape: uri/message/range always present
            assert {"uri", "message", "range"}.issubset(diagnostic.keys())
            assert isinstance(diagnostic["uri"], str)
            assert diagnostic["uri"].endswith("test_repo/diagnostics_sample.py")
            assert isinstance(diagnostic["message"], str) and diagnostic["message"]

            rng = diagnostic["range"]
            for boundary in ("start", "end"):
                assert isinstance(rng[boundary]["line"], int)
                assert isinstance(rng[boundary]["character"], int)

            # both sample diagnostics are Errors and carry a severity
            assert "severity" in diagnostic
            assert int(diagnostic["severity"]) == 1

        # all diagnostics for one file share a single canonical uri
        assert len({d["uri"] for d in diagnostics}) == 1

        # the two undefined names are reported, one per known line
        by_line = {d["range"]["start"]["line"]: d for d in diagnostics}
        assert set(by_line) == {MISSING_USER_LINE, UNDEFINED_NAME_LINE}
        assert "missing_user" in by_line[MISSING_USER_LINE]["message"]
        assert "undefined_name" in by_line[UNDEFINED_NAME_LINE]["message"]

    def test_min_severity_filtering(self, language_server: SolidLanguageServer) -> None:
        """min_severity keeps items whose numeric severity <= the threshold.

        The sample file yields only Error-severity (1) diagnostics, so every
        threshold from 1 (Error) through 4 (Hint) returns the same two items, and
        no returned diagnostic ever exceeds the requested threshold.
        """
        errors_only = language_server.request_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=1)
        all_severities = language_server.request_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=4)

        # only Error-severity diagnostics exist here: the strictest and loosest
        # thresholds return the identical set.
        assert len(errors_only) == 2
        assert _signature(errors_only) == _signature(all_severities)

        # invariant of the filter: every returned severity is <= the threshold.
        for min_severity in (1, 2, 3, 4):
            filtered = language_server.request_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=min_severity)
            assert len(filtered) == 2
            for diagnostic in filtered:
                assert int(diagnostic["severity"]) <= min_severity

    def test_line_range_filtering_and_end_line_no_upper_bound(self, language_server: SolidLanguageServer) -> None:
        """start_line/end_line window the results; end_line=-1 imposes no upper bound."""
        # populate the published cache and learn the actual diagnostic lines
        full = language_server.request_published_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=1)
        assert full is not None and len(full) == 2

        lines = sorted(_start_lines(full))
        lo, hi = lines[0], lines[-1]
        assert lo < hi  # the two diagnostics are on distinct lines

        def cached(**kwargs) -> list:
            result = language_server.get_cached_published_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=1, **kwargs)
            assert result is not None
            return result

        # no window: both diagnostics
        assert _start_lines(cached(start_line=0, end_line=-1)) == {lo, hi}

        # finite end_line at the lower line excludes the higher-line diagnostic
        assert _start_lines(cached(start_line=0, end_line=lo)) == {lo}

        # end_line=-1 from the higher line: no upper bound, but lower line excluded
        assert _start_lines(cached(start_line=hi, end_line=-1)) == {hi}

        # a finite window strictly between the two diagnostics matches nothing
        assert cached(start_line=lo + 1, end_line=hi - 1) == []

        # a finite window entirely below the first diagnostic matches nothing
        assert cached(start_line=0, end_line=lo - 1) == []

    def test_cached_matches_published_and_pull_consistency(self, language_server: SolidLanguageServer) -> None:
        """Cached, freshly-published, and pull paths agree on the diagnostics set."""
        published = language_server.request_published_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=1)
        cached = language_server.get_cached_published_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=1)

        assert published is not None
        assert cached is not None
        # the cached path returns exactly what was last published (same dicts, same order)
        assert cached == published

        pull = language_server.request_text_document_diagnostics(DIAGNOSTICS_FILE, min_severity=1)

        assert len(pull) == len(published) == len(cached) == 2
        # pull and published report the same diagnostics (message/line/severity)
        assert _signature(pull) == _signature(published)

        # every path agrees on a single canonical uri for the file
        uris = {d["uri"] for d in pull} | {d["uri"] for d in published} | {d["uri"] for d in cached}
        assert len(uris) == 1

    def test_get_cached_returns_none_when_never_published(self, language_server: SolidLanguageServer) -> None:
        """get_cached_published_text_document_diagnostics returns None with no cache entry."""
        assert language_server.get_cached_published_text_document_diagnostics(NEVER_PUBLISHED_FILE) is None

    def test_invalid_arguments_raise_value_error(self, language_server: SolidLanguageServer) -> None:
        """All three public methods validate arguments and raise ValueError before I/O."""
        for kwargs in INVALID_ARG_KWARGS:
            with pytest.raises(ValueError):
                language_server.get_cached_published_text_document_diagnostics(DIAGNOSTICS_FILE, **kwargs)
            with pytest.raises(ValueError):
                language_server.request_text_document_diagnostics(DIAGNOSTICS_FILE, **kwargs)
            with pytest.raises(ValueError):
                language_server.request_published_text_document_diagnostics(DIAGNOSTICS_FILE, **kwargs)
