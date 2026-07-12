from unittest.mock import Mock

from solidlsp.language_servers.pyright_server import PyrightServer


def test_analysis_timeout_does_not_mark_analysis_complete() -> None:
    server = object.__new__(PyrightServer)
    server.analysis_complete = Mock()
    server.analysis_complete.wait.return_value = False

    server._wait_for_initial_analysis(timeout=0)

    server.analysis_complete.wait.assert_called_once_with(timeout=0)
    server.analysis_complete.set.assert_not_called()
