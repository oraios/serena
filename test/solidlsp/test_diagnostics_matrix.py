from pathlib import Path

import pytest

from serena.symbol import LanguageServerSymbolRetriever
from solidlsp import SolidLanguageServer
from test.conftest import find_identifier_position
from test.diagnostics_cases import DIAGNOSTIC_CASE_PARAMS, DiagnosticCase


@pytest.mark.parametrize("language_server,diagnostic_case", DIAGNOSTIC_CASE_PARAMS, indirect=["language_server"])
def test_request_text_document_diagnostics_matrix(
    language_server: SolidLanguageServer,
    diagnostic_case: DiagnosticCase,
) -> None:
    diagnostics = language_server.request_text_document_diagnostics(diagnostic_case.relative_path, min_severity=1)
    assert diagnostics, f"Expected diagnostics for {diagnostic_case.language.value}:{diagnostic_case.relative_path}"

    diagnostic_messages = [diagnostic["message"] for diagnostic in diagnostics]
    assert any(diagnostic_case.primary_message_fragment in message for message in diagnostic_messages), diagnostic_messages
    assert any(diagnostic_case.reference_message_fragment in message for message in diagnostic_messages), diagnostic_messages

    repo_root = language_server.repository_root_path
    primary_symbol_position = find_identifier_position(Path(repo_root) / diagnostic_case.relative_path, diagnostic_case.primary_symbol_identifier)
    reference_symbol_position = find_identifier_position(Path(repo_root) / diagnostic_case.relative_path, diagnostic_case.reference_symbol_identifier)
    assert primary_symbol_position is not None
    assert reference_symbol_position is not None

    primary_diagnostics = language_server.request_text_document_diagnostics(
        diagnostic_case.relative_path,
        start_line=primary_symbol_position[0],
        end_line=reference_symbol_position[0] - 1,
        min_severity=1,
    )
    primary_messages = [diagnostic["message"] for diagnostic in primary_diagnostics]
    assert primary_messages, f"Expected range-filtered diagnostics for {diagnostic_case.primary_symbol_identifier}"
    assert any(diagnostic_case.primary_message_fragment in message for message in primary_messages), primary_messages
    assert all(diagnostic_case.reference_message_fragment not in message for message in primary_messages), primary_messages


@pytest.mark.parametrize("project_with_ls,diagnostic_case", DIAGNOSTIC_CASE_PARAMS, indirect=["project_with_ls"])
def test_get_symbol_diagnostics_matrix(project_with_ls, diagnostic_case: DiagnosticCase) -> None:
    symbol_retriever = LanguageServerSymbolRetriever(project_with_ls)

    diagnostics_by_symbol = symbol_retriever.get_symbol_diagnostics(
        diagnostic_case.primary_symbol_name_path,
        reference_file=diagnostic_case.relative_path,
        min_severity=1,
    )
    diagnostic_messages_by_symbol = {
        symbol.get_name_path(): [diagnostic["message"] for diagnostic in diagnostics]
        for symbol, diagnostics in diagnostics_by_symbol.items()
    }
    assert diagnostic_case.primary_symbol_name_path in diagnostic_messages_by_symbol, diagnostic_messages_by_symbol
    assert any(
        diagnostic_case.primary_message_fragment in message
        for message in diagnostic_messages_by_symbol[diagnostic_case.primary_symbol_name_path]
    ), diagnostic_messages_by_symbol

    diagnostics_with_references = symbol_retriever.get_symbol_diagnostics(
        diagnostic_case.primary_symbol_name_path,
        reference_file=diagnostic_case.relative_path,
        check_symbol_references=True,
        min_severity=1,
    )
    diagnostic_messages_with_references = {
        symbol.get_name_path(): [diagnostic["message"] for diagnostic in diagnostics]
        for symbol, diagnostics in diagnostics_with_references.items()
    }
    assert diagnostic_case.primary_symbol_name_path in diagnostic_messages_with_references, diagnostic_messages_with_references
    assert diagnostic_case.reference_symbol_name_path in diagnostic_messages_with_references, diagnostic_messages_with_references
    assert any(
        diagnostic_case.reference_message_fragment in message
        for message in diagnostic_messages_with_references[diagnostic_case.reference_symbol_name_path]
    ), diagnostic_messages_with_references
