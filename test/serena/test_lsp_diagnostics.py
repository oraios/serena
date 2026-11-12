"""
Tests for the diagnostics context of the editing tools.
"""

from unittest.mock import MagicMock

from serena.language_backend import BuiltinLanguageBackend
from serena.lsp.lsp_diagnostics import DiagnosticsContext


def test_diagnostics_context_leaves_the_result_alone_for_a_non_lsp_backend() -> None:
    """
    Per-edit diagnostics come from language servers; with a backend that runs none, an enabled diagnostics context
    answers the edit's result as it is.
    """
    agent = MagicMock()
    agent.get_language_backend.return_value = BuiltinLanguageBackend.JETBRAINS.get_instance()
    project = agent.get_active_project_or_raise.return_value
    project.get_language_server_manager_or_raise.side_effect = Exception("The language server manager is not initialized")

    with DiagnosticsContext(agent, "src/module.py", enable=True) as diagnostics_context:
        result = diagnostics_context.format_result("OK")

    assert result == "OK"
