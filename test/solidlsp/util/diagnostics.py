from collections.abc import Sequence

from solidlsp import SolidLanguageServer


def assert_file_diagnostics(
    language_server: SolidLanguageServer,
    relative_file_path: str,
    expected_message_fragments: Sequence[str],
    min_count: int = 1,
) -> None:
    diagnostics = language_server.request_text_document_diagnostics(relative_file_path, min_severity=1)

    assert isinstance(diagnostics, list), diagnostics
    assert len(diagnostics) >= min_count, diagnostics

    diagnostic_messages = [diagnostic["message"] for diagnostic in diagnostics]
    for fragment in expected_message_fragments:
        assert any(fragment in message for message in diagnostic_messages), diagnostic_messages
