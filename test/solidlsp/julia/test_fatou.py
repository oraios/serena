"""Integration tests for the Fatou Julia language server."""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId


@pytest.mark.julia
class TestFatouLanguageServer:
    @pytest.mark.parametrize("language_server", [LanguageServerId.JULIA_FATOU], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer) -> None:
        symbols, _ = language_server.request_document_symbols("main.jl").get_all_symbols_and_roots()

        assert {symbol["name"] for symbol in symbols} >= {"calculate_sum", "main"}

    @pytest.mark.parametrize("language_server", [LanguageServerId.JULIA_FATOU], indirect=True)
    def test_within_file_references(self, language_server: SolidLanguageServer) -> None:
        references = language_server.request_references("main.jl", line=2, column=10)

        locations = {(reference["relativePath"], reference["range"]["start"]["line"]) for reference in references}
        assert ("main.jl", 7) in locations

    @pytest.mark.parametrize("language_server", [LanguageServerId.JULIA_FATOU], indirect=True)
    def test_cross_file_references(self, language_server: SolidLanguageServer) -> None:
        references = language_server.request_references("src/fatou_a.jl", line=0, column=2)

        locations = {(reference["relativePath"].replace("\\", "/"), reference["range"]["start"]["line"]) for reference in references}
        assert locations >= {("src/fatou_a.jl", 1), ("src/fatou_b.jl", 0)}

    def test_file_matching(self) -> None:
        matcher = LanguageServerId.JULIA_FATOU.get_source_fn_matcher()

        assert matcher.is_relevant_filename("analysis.jl")
        assert not matcher.is_relevant_filename("analysis.R")
