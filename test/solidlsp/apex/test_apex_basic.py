"""
Basic tests for Apex language support.

Since no LSP exists for Apex, these tests verify that:
1. Apex files are recognized by their extensions
2. Basic file operations work
3. The language server can be created (even though it doesn't start an actual LSP)
"""

from pathlib import Path

import pytest

from serena.project import Project
from solidlsp.ls_config import Language


@pytest.fixture
def apex_test_repo():
    """Path to the Apex test repository."""
    return str(Path(__file__).parent.parent.parent / "resources" / "repos" / "apex" / "test_repo")


@pytest.mark.apex
def test_apex_language_enum():
    """Test that Apex is in the Language enum."""
    assert Language.APEX == "apex"
    assert Language.APEX.value == "apex"


@pytest.mark.apex
def test_apex_file_extensions():
    """Test that Apex file extensions are recognized."""
    matcher = Language.APEX.get_source_fn_matcher()

    # Should match Apex files
    assert matcher.is_relevant_filename("AccountController.cls")
    assert matcher.is_relevant_filename("AccountTrigger.trigger")
    assert matcher.is_relevant_filename("SomeClass.apex")

    # Should not match non-Apex files
    assert not matcher.is_relevant_filename("test.py")
    assert not matcher.is_relevant_filename("test.java")
    assert not matcher.is_relevant_filename("test.js")


@pytest.mark.apex
def test_apex_is_experimental():
    """Test that Apex is marked as experimental."""
    assert Language.APEX.is_experimental()


@pytest.mark.apex
def test_read_apex_file(apex_test_repo):
    """Test that Apex files can be read using the Project.read_file method."""
    # Create a project with Apex language
    from serena.config.serena_config import ProjectConfig

    config = ProjectConfig(
        project_name="apex_test",
        languages=[Language.APEX],
        encoding="utf-8",
    )

    project = Project(apex_test_repo, config)

    # Read the AccountController.cls file
    content = project.read_file("AccountController.cls")

    # Verify content
    assert "public class AccountController" in content
    assert "getActiveAccounts" in content
    assert "createAccount" in content

    # Read the AccountTrigger.trigger file
    trigger_content = project.read_file("AccountTrigger.trigger")

    # Verify trigger content
    assert "trigger AccountTrigger on Account" in trigger_content
    assert "Trigger.isBefore" in trigger_content


@pytest.mark.apex
def test_apex_language_server_creation(apex_test_repo):
    """Test that an Apex language server can be created (even though it won't start an actual LSP)."""
    from solidlsp.ls_config import LanguageServerConfig
    from solidlsp.settings import SolidLSPSettings

    config = LanguageServerConfig(
        code_language=Language.APEX,
        encoding="utf-8",
    )

    settings = SolidLSPSettings()

    # Create the language server
    ls_class = Language.APEX.get_ls_class()
    ls = ls_class(config, apex_test_repo, settings)

    # Verify it was created
    assert ls is not None
    assert ls.language_id == "apex"
    assert ls.repository_root_path == apex_test_repo

    # Start the server (which should succeed even though no actual LSP starts)
    ls.start()
    assert ls.server_started is True
