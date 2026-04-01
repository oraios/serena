"""
Basic integration tests for the Ansible language server.

These tests validate initialization, hover, and completion capabilities
using the standard Ansible test repository. They work with the standard
@ansible/ansible-language-server from npm.
"""

import platform
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.skipif(platform.system() == "Windows", reason="ansible-language-server does not support native Windows operation")
@pytest.mark.ansible
class TestAnsibleLanguageServerBasics:
    """Test basic Ansible language server functionality."""

    @pytest.mark.parametrize("language_server", [Language.ANSIBLE], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ANSIBLE], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Language server starts and points to the correct repo."""
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.ANSIBLE], indirect=True)
    def test_hover_on_module_contains_documentation(self, language_server: SolidLanguageServer) -> None:
        """Hover on ansible.builtin.package returns module documentation."""
        # playbook.yml line 10 (0-indexed): "ansible.builtin.package:"
        result = language_server.request_hover("playbook.yml", 10, 8)
        assert result is not None, "Expected hover info for ansible.builtin.package"
        hover_value = result["contents"]
        if isinstance(hover_value, dict):
            hover_text = hover_value.get("value", "")
        elif isinstance(hover_value, list):
            hover_text = " ".join(str(v) for v in hover_value)
        else:
            hover_text = str(hover_value)
        assert "package" in hover_text.lower(), f"Hover should mention 'package', got: {hover_text[:300]}"

    @pytest.mark.parametrize("language_server", [Language.ANSIBLE], indirect=True)
    def test_completions_contain_module_names(self, language_server: SolidLanguageServer) -> None:
        """Completions at a task keyword position return Ansible module names."""
        # playbook.yml line 10 (0-indexed), col 6: inside a task block
        result = language_server.request_completions("playbook.yml", 10, 6)
        assert result is not None, "Expected completion results"
        assert len(result) > 0, "Expected non-empty completion list"
        labels = [item["completionText"] for item in result if "completionText" in item]
        assert labels, f"Expected completions with completionText, got: {result[:3]}"

    @pytest.mark.xfail(reason="Seems like ansible LS lacks basic functionality at the moment, textDocument/documentSymbol doesn't work")
    @pytest.mark.parametrize("language_server", [Language.ANSIBLE], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
