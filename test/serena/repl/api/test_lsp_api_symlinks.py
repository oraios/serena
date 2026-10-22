"""Project trust checks for explicit LspApi paths through symlinks."""

from pathlib import Path

import pytest

from serena.agent import SerenaAgent
from serena.repl.api.lsp_api import LspApi
from test.conftest import create_default_serena_config

pytestmark = pytest.mark.python


@pytest.mark.parametrize("outside_root", [False, True], ids=["inside", "outside"])
@pytest.mark.parametrize("directory_link", [False, True], ids=["file-link", "directory-link"])
@pytest.mark.parametrize("trusted", [False, True], ids=["untrusted", "trusted"])
def test_explicit_symbol_paths_respect_project_trust(tmp_path: Path, outside_root: bool, directory_link: bool, trusted: bool) -> None:
    """Only trusted projects permit explicit symbol reads through links to outside targets."""
    # create ordinary source and a distinguishable linked target
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("def ordinary():\n    return 1\n", encoding="utf-8")
    target_dir = (tmp_path if outside_root else root) / "target"
    target_dir.mkdir()
    target = target_dir / "source.py"
    target.write_text("def linked_target():\n    return 'SYNTHETIC_LINK_TARGET'\n", encoding="utf-8")
    (root / ".serena").mkdir()
    (root / ".serena" / "project.yml").write_text("project_name: symlink-test\nlanguage_servers: [python]\n", encoding="utf-8")

    # address the target through either a file link or a linked parent directory
    try:
        if directory_link:
            (root / "alias").symlink_to(target_dir, target_is_directory=True)
            requested_path = "alias/source.py"
        else:
            (root / "alias.py").symlink_to(target)
            requested_path = "alias.py"
    except OSError as exc:
        pytest.skip(f"Symbolic links are unavailable: {exc}")

    # activate the project with trust configured before language server creation
    config = create_default_serena_config()
    config.trusted_project_path_patterns = [str(root)] if trusted else []
    agent = SerenaAgent(project=str(root), serena_config=config)
    try:
        agent.execute_task(lambda: None)
        assert agent.get_active_project_or_raise().is_trusted() == trusted
        api = LspApi(agent)
        ordinary = api.find_symbol("ordinary", relative_path="main.py", include_body=True)
        assert "def ordinary" in ordinary.represent()

        # reject outside targets for every explicit read operation in an untrusted project
        if outside_root and not trusted:
            with pytest.raises(ValueError, match="outside the project root"):
                api.find_symbol("linked_target", relative_path=requested_path, include_body=True)
            with pytest.raises(ValueError, match="outside the project root"):
                api.get_symbols_overview(requested_path)
            with pytest.raises(ValueError, match="outside the project root"):
                api.find_referencing_symbols("linked_target", relative_path=requested_path)
            with pytest.raises(ValueError, match="outside the project root"):
                api.find_implementations("linked_target", relative_path=requested_path)
            with pytest.raises(ValueError, match="outside the project root"):
                api.find_declaration(requested_path, r"def (linked_target)")
            with pytest.raises(ValueError, match="outside the project root"):
                api.get_diagnostics_for_file(requested_path)
            with pytest.raises(ValueError, match="outside the project root"):
                api.get_diagnostics_for_symbol("linked_target", reference_file=requested_path)
        else:
            # preserve explicit reads through permitted links
            result = api.find_symbol("linked_target", relative_path=requested_path, include_body=True)
            assert "SYNTHETIC_LINK_TARGET" in result.represent()
            overview = api.get_symbols_overview(requested_path)
            assert "linked_target" in overview.represent()
    finally:
        agent.on_shutdown()
