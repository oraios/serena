"""Symbol discovery through file and directory aliases."""

from dataclasses import replace
from pathlib import Path

import pytest

from solidlsp import ls_types
from solidlsp.ls_config import LanguageServerId
from test.conftest import start_ls_context

pytestmark = pytest.mark.python


@pytest.mark.parametrize("trusted", [False, True])
def test_symbol_tree_symlink_discovery(tmp_path: Path, trusted: bool) -> None:
    """Discovery respects trust and matches ignores against aliases rather than targets."""
    # create ordinary source and targets inside an ignored directory and outside the project
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("def ordinary():\n    return 1\n", encoding="utf-8")
    ignored = root / "ignored"
    outside = tmp_path / "outside"
    for target in (ignored, outside):
        target.mkdir()
        (target / "source.py").write_text("def linked():\n    return 2\n", encoding="utf-8")

    # expose both targets through independently named file and directory aliases
    try:
        for name, target in (("internal", ignored), ("external", outside)):
            (root / f"{name}.py").symlink_to(target / "source.py")
            (root / name).symlink_to(target, target_is_directory=True)
        (root / "excluded.py").symlink_to(outside / "source.py")
        (root / "excluded").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symbolic links are unavailable: {exc}")

    # collect symbol locations from the public tree result
    def symbol_paths(nodes: list[ls_types.UnifiedSymbolInformation]) -> set[str]:
        paths = set()
        for node in nodes:
            if node["kind"] == ls_types.SymbolKind.Function:
                paths.add(Path(node["location"]["relativePath"]).as_posix())
            paths.update(symbol_paths(node.get("children", [])))
        return paths

    with start_ls_context(
        ls_id=LanguageServerId.PYTHON,
        repo_path=str(root),
        ignored_paths=["ignored/", "excluded/", "excluded.py"],
    ) as ls:
        ls.config = replace(ls.config, is_project_trusted=trusted)
        expected = {"main.py"}
        if trusted:
            expected.update({"internal.py", "internal/source.py", "external.py", "external/source.py"})
        assert symbol_paths(ls.request_full_symbol_tree()) == expected
