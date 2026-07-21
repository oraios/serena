import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.solidity_language_server import SolidityLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.util.diagnostics import assert_file_diagnostics


class _NeverSetEvent:
    """Stand-in for :class:`threading.Event` whose wait never succeeds."""

    def wait(self, timeout: float | None = None) -> bool:
        return False

    def clear(self) -> None:
        return None

    def set(self) -> None:
        return None


class _AlwaysSignalledEvent:
    """Stand-in for :class:`threading.Event` whose wait always reports a completion; counts clears."""

    def __init__(self) -> None:
        self.cleared = 0

    def wait(self, timeout: float | None = None) -> bool:
        return True

    def clear(self) -> None:
        self.cleared += 1

    def set(self) -> None:
        return None


@pytest.mark.solidity
class TestSolidityDiagnostics:
    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "contracts/DiagnosticsSample.sol",
            (),
            min_count=1,
        )

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    def test_file_diagnostics_via_validation_completion(
        self, language_server: SolidLanguageServer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Diagnostics must still arrive via the validation-completion fallback when the initial
        publish wait does not observe them (the failure mode of cold/slow CI runners).
        """
        assert isinstance(language_server, SolidityLanguageServer)

        # force the fast path to miss so that only the validation-completion fallback can deliver
        monkeypatch.setattr(language_server, "_wait_for_relevant_published_diagnostics", lambda **kwargs: None)

        assert_file_diagnostics(
            language_server,
            "contracts/DiagnosticsSample.sol",
            (),
            min_count=1,
        )

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    def test_file_diagnostics_without_validation_signal(
        self, language_server: SolidLanguageServer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A server that never signals validation completion must yield an empty result within the
        bound instead of hanging or raising.
        """
        assert isinstance(language_server, SolidityLanguageServer)

        # force the fast path to miss and make the completion signal unobtainable
        monkeypatch.setattr(language_server, "_wait_for_relevant_published_diagnostics", lambda **kwargs: None)
        monkeypatch.setattr(language_server, "_VALIDATION_COMPLETION_TIMEOUT", 0.2)
        monkeypatch.setattr(language_server, "_validation_completed", _NeverSetEvent())

        diagnostics = language_server.request_text_document_diagnostics("contracts/DiagnosticsSample.sol", min_severity=1)
        assert diagnostics == []

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    def test_file_diagnostics_rearms_after_spurious_completion(
        self, language_server: SolidLanguageServer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A completion signal belonging to another document (the payload carries no URI) must
        re-arm the fallback wait instead of ending the request without diagnostics.
        """
        assert isinstance(language_server, SolidityLanguageServer)

        expected_diagnostic = {
            "uri": "file:///spurious-completion-test",
            "severity": 1,
            "message": "delivered after re-arm",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
            "code": None,
        }
        # first wake is spurious (no publication for the request URI), second delivers
        grace_reads: list[list | None] = [None, [expected_diagnostic]]
        event = _AlwaysSignalledEvent()

        # force the fast path to miss and script the fallback's wake/read sequence
        monkeypatch.setattr(language_server, "_wait_for_relevant_published_diagnostics", lambda **kwargs: None)
        monkeypatch.setattr(language_server, "_validation_completed", event)
        monkeypatch.setattr(language_server, "_wait_for_published_diagnostics", lambda **kwargs: grace_reads.pop(0))

        diagnostics = language_server.request_text_document_diagnostics("contracts/DiagnosticsSample.sol", min_severity=1)

        # one clear at request start plus exactly one re-arm after the spurious wake
        assert event.cleared == 2
        assert not grace_reads  # both scripted reads consumed
        assert [diagnostic["message"] for diagnostic in diagnostics] == ["delivered after re-arm"]
