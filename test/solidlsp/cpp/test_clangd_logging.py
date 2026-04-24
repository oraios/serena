import logging

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer


@pytest.mark.cpp
class TestClangdLogging:
    @pytest.mark.parametrize(
        "expected, line",
        [
            # Parametrize names instead of codes for human-readable output in test logs.
            (logging.getLevelName(logging.INFO), "I[12:00:00.000] clangd version 22.1.3"),
            (logging.getLevelName(logging.INFO), "V[12:00:00.000] verbose detail"),
            (logging.getLevelName(logging.DEBUG), "D[12:00:00.000] debug detail"),
            (logging.getLevelName(logging.ERROR), "E[12:00:00.000] something bad"),
            (logging.getLevelName(logging.ERROR), "F[12:00:00.000] fatal"),
        ],
    )
    def test_log_record_detection(self, expected: str, line: str) -> None:
        """
        Verifies clangd's stderr log classifier maps each level prefix to the
        expected Python logging level and avoids misclassifying compile-command
        payloads as ERROR.
        """
        assert ClangdLanguageServer._determine_log_level(line) == logging.getLevelNamesMapping()[expected]

    def test_log_record_info_payload_mentions_fno_exceptions(self) -> None:
        line = """clang++ -fno-exceptions -c no_exceptions.cpp"""
        # Basic classifier incorrectly detects line as an error log.
        assert SolidLanguageServer._determine_log_level(line) == logging.ERROR
        # Clangd classifier correctly detects line as an info log.
        assert ClangdLanguageServer._determine_log_level(line) == logging.INFO

    def test_log_record_info_payload_without_prefix(self) -> None:
        # Multi-line records: first line carries the I[...] prefix, subsequent
        # lines do not. Treat lack of prefix as continuation.
        assert ClangdLanguageServer._determine_log_level("[/home/user/project/build]") == logging.INFO

    def test_log_record_info_payload_empty(self) -> None:
        assert ClangdLanguageServer._determine_log_level("") == logging.INFO
