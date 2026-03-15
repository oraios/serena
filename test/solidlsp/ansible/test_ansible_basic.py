"""
Basic integration tests for the Ansible language server functionality.

These tests validate the functionality of the language server APIs
using the Ansible test repository. Note that ansible-language-server
does not support documentSymbol; it provides hover, completion, and
definition capabilities.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.ansible
class TestAnsibleLanguageServerBasics:
    """Test basic functionality of the Ansible language server."""

    @pytest.mark.parametrize("language_server", [Language.ANSIBLE], indirect=True)
    def test_ansible_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that Ansible language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.ANSIBLE

    @pytest.mark.parametrize("language_server", [Language.ANSIBLE], indirect=True)
    def test_hover_on_module(self, language_server: SolidLanguageServer) -> None:
        """Test hover information for an Ansible module in playbook.yml."""
        # hover over 'ansible.builtin.package' module name (line 12, col 8 in playbook.yml)
        result = language_server.request_hover("playbook.yml", 12, 8)
        assert result is not None, "Should get hover info for ansible module"

    @pytest.mark.parametrize("language_server", [Language.ANSIBLE], indirect=True)
    def test_completions_in_playbook(self, language_server: SolidLanguageServer) -> None:
        """Test completions work in playbook.yml."""
        # request completions at a task keyword position (line 10, col 6 in playbook.yml)
        result = language_server.request_completions("playbook.yml", 10, 6)
        assert result is not None, "Should get completion results in playbook"
