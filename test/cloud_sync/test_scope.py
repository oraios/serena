from pathlib import Path

from serena.cloud_sync.scope import (
    DEFAULT_GLOBAL_INCLUDES,
    DEFAULT_PROJECT_INCLUDES,
    ScopeFilter,
    ScopeRoot,
)


def _make_scope(opt_in_local_yml: bool = False) -> ScopeFilter:
    return ScopeFilter(
        include_patterns=tuple(list(DEFAULT_GLOBAL_INCLUDES) + list(DEFAULT_PROJECT_INCLUDES)),
        opt_in_project_local_yml=opt_in_local_yml,
    )


def test_hard_excludes_are_not_overridable(tmp_path: Path) -> None:
    s = _make_scope()
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "serena.log").write_text("x")
    (tmp_path / "config.env").write_text("SECRET=1")
    (tmp_path / "id_rsa").write_text("-----BEGIN RSA-----")
    (tmp_path / "memories").mkdir()
    (tmp_path / "memories" / "ok.md").write_text("m")
    (tmp_path / "serena_config.yml").write_text("x")

    root = ScopeRoot(local_root=tmp_path, remote_subprefix="global")
    collected = [rel for _, _, rel in s.iter_files([root])]
    assert "memories/ok.md" in collected
    assert "serena_config.yml" in collected
    assert not any("logs/" in p for p in collected)
    assert "config.env" not in collected
    assert "id_rsa" not in collected


def test_project_local_yml_opt_in(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text("y")
    (tmp_path / "project.local.yml").write_text("y")
    root = ScopeRoot(local_root=tmp_path, remote_subprefix="projects/x")

    s_off = _make_scope(opt_in_local_yml=False)
    collected = {rel for _, _, rel in s_off.iter_files([root])}
    assert "project.yml" in collected
    assert "project.local.yml" not in collected

    s_on = _make_scope(opt_in_local_yml=True)
    collected = {rel for _, _, rel in s_on.iter_files([root])}
    assert "project.local.yml" in collected


def test_size_cap(tmp_path: Path) -> None:
    s = _make_scope()
    root = ScopeRoot(local_root=tmp_path, remote_subprefix="global")
    (tmp_path / "memories").mkdir()
    # Under cap
    (tmp_path / "memories" / "small.md").write_bytes(b"a" * 100)
    # Over cap (6 MiB)
    big = tmp_path / "memories" / "big.md"
    big.write_bytes(b"b" * (6 * 1024 * 1024))
    collected = {rel for _, _, rel in s.iter_files([root])}
    assert "memories/small.md" in collected
    assert "memories/big.md" not in collected
