"""
Unit tests for the detection of Scala build roots, which Metals is given as workspace folders.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.scala_language_server import (
    DEFAULT_PROJECT_ROOT_SCAN_DEPTH,
    ScalaInitializeParamsBuilder,
    ScalaLanguageServer,
    find_build_roots,
)
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.settings import SolidLSPSettings


def make_sbt_build(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "build.sbt").write_text('ThisBuild / scalaVersion := "3.3.6"\n')
    (path / "src" / "main" / "scala").mkdir(parents=True)
    return path


@pytest.mark.scala
class TestFindBuildRoots:
    def test_repository_root_is_the_build_root(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path)
        assert find_build_roots(str(tmp_path)) == [str(tmp_path)]

    def test_single_build_below_the_root(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "backend")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend")]

    def test_several_builds_below_the_root(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "backend")
        make_sbt_build(tmp_path / "tooling")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend"), str(tmp_path / "tooling")]

    def test_nested_build(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "scala" / "backend")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "scala" / "backend")]

    def test_scan_depth_is_bounded(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "a" / "b" / "c")
        assert find_build_roots(str(tmp_path), max_depth=2) == [str(tmp_path)]
        assert find_build_roots(str(tmp_path), max_depth=3) == [str(tmp_path / "a" / "b" / "c")]

    def test_does_not_descend_into_a_build_root(self, tmp_path: Path) -> None:
        """A subproject of an sbt build is not a build root of its own."""
        make_sbt_build(tmp_path / "backend")
        make_sbt_build(tmp_path / "backend" / "module")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend")]

    def test_falls_back_to_the_repository_root(self, tmp_path: Path) -> None:
        """With nothing to find, Metals' own behaviour is left unchanged."""
        (tmp_path / "docs").mkdir()
        assert find_build_roots(str(tmp_path)) == [str(tmp_path)]

    def test_hidden_and_uninteresting_directories_are_skipped(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / ".git" / "backend")
        make_sbt_build(tmp_path / "node_modules" / "backend")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path)]

    def test_bsp_connection_file_marks_a_build_root(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / ".bsp").mkdir(parents=True)
        (tmp_path / "backend" / ".bsp" / "sbt.json").write_text("{}")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend")]

    def test_sbt_build_defined_only_under_project(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / "project").mkdir(parents=True)
        (tmp_path / "backend" / "project" / "build.properties").write_text("sbt.version=1.11.7\n")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend")]

    def test_build_properties_without_a_version_is_not_a_build_root(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / "project").mkdir(parents=True)
        (tmp_path / "backend" / "project" / "build.properties").write_text("# nothing to see here\n")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path)]

    def test_an_empty_bsp_directory_is_not_a_build_root(self, tmp_path: Path) -> None:
        """Metals requires a connection file in there, not merely the directory."""
        (tmp_path / "backend" / ".bsp").mkdir(parents=True)
        make_sbt_build(tmp_path / "backend" / "module")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend" / "module")]

    def test_a_skipped_directory_is_still_probed(self, tmp_path: Path) -> None:
        """`src` and friends are not descended into, but may themselves be a build root."""
        make_sbt_build(tmp_path / "src")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "src")]

    def test_a_skipped_directory_is_not_descended_into(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "node_modules" / "backend")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path)]

    def test_bazel_workspace_marker(self, tmp_path: Path) -> None:
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "MODULE.bazel").write_text("")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend")]

    def test_symlinked_build_is_found_without_looping(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "elsewhere" / "backend")
        (tmp_path / "repo").mkdir()
        (tmp_path / "repo" / "link").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
        (tmp_path / "repo" / "loop").symlink_to(tmp_path / "repo", target_is_directory=True)
        assert find_build_roots(str(tmp_path / "repo")) == [str(tmp_path / "repo" / "link" / "backend")]


@pytest.mark.scala
class TestResolveBuildRoots:
    """The `project_roots` / `project_root_scan_depth` settings, which override the detection."""

    @staticmethod
    def resolve(root: Path, **scala_settings) -> list[str]:
        settings = SolidLSPSettings(ls_specific_settings={LanguageServerId.SCALA: scala_settings})
        return ScalaLanguageServer._resolve_build_roots(str(root), settings)

    def test_detection_is_used_when_unset(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "backend")
        assert self.resolve(tmp_path) == [str(tmp_path / "backend")]

    def test_configured_roots_are_resolved_against_the_repository_root(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        assert self.resolve(tmp_path, project_roots=["a/b"]) == [str(tmp_path / "a" / "b")]

    def test_configured_roots_need_not_look_like_builds(self, tmp_path: Path) -> None:
        """The setting exists precisely for where the detection is wrong."""
        (tmp_path / "odd").mkdir()
        assert self.resolve(tmp_path, project_roots=["odd"]) == [str(tmp_path / "odd")]

    def test_a_missing_configured_root_is_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "here").mkdir()
        assert self.resolve(tmp_path, project_roots=["here", "gone"]) == [str(tmp_path / "here")]

    def test_detection_takes_over_when_no_configured_root_exists(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "backend")
        assert self.resolve(tmp_path, project_roots=["gone"]) == [str(tmp_path / "backend")]

    @pytest.mark.parametrize("bad", ["backend", 42, [1, 2], []])
    def test_a_malformed_project_roots_falls_back_to_detection(self, tmp_path: Path, bad: object) -> None:
        make_sbt_build(tmp_path / "backend")
        assert self.resolve(tmp_path, project_roots=bad) == [str(tmp_path / "backend")]

    @pytest.mark.parametrize("bad", [None, "3", 0, -1, True])
    def test_a_malformed_scan_depth_falls_back_to_the_default(self, tmp_path: Path, bad: object) -> None:
        make_sbt_build(tmp_path / "a" / "b" / "c")
        assert self.resolve(tmp_path, project_root_scan_depth=bad) == [str(tmp_path / "a" / "b" / "c")]
        assert DEFAULT_PROJECT_ROOT_SCAN_DEPTH == 3

    def test_scan_depth_is_honoured(self, tmp_path: Path) -> None:
        make_sbt_build(tmp_path / "a" / "b" / "c")
        assert self.resolve(tmp_path, project_root_scan_depth=2) == [str(tmp_path)]


@pytest.mark.scala
class TestScalaInitializeParamsBuilder:
    @staticmethod
    def workspace_folder_paths(tmp_path: Path, build_roots: list[str], additional: list[str]) -> list[str]:
        ls = SimpleNamespace(
            repository_root_path=str(tmp_path),
            custom_settings={},
            config=LanguageServerConfig(ls_id=LanguageServerId.SCALA, additional_workspace_folders=additional),
        )
        params = ScalaInitializeParamsBuilder(cast(SolidLanguageServer, ls), build_roots).build()
        folders = params["workspaceFolders"] or []
        return [url2pathname(urlparse(folder["uri"]).path) for folder in folders]

    def test_the_build_roots_become_the_workspace_folders(self, tmp_path: Path) -> None:
        roots = [str(tmp_path / "alpha"), str(tmp_path / "beta")]
        assert self.workspace_folder_paths(tmp_path, roots, additional=[]) == roots

    def test_additional_workspace_folders_are_kept(self, tmp_path: Path) -> None:
        """They can lie outside the repository, so detection could never recover them."""
        outside = tmp_path.parent / "shared-lib"
        outside.mkdir(exist_ok=True)
        roots = [str(tmp_path / "alpha")]
        assert self.workspace_folder_paths(tmp_path, roots, additional=[str(outside)]) == [*roots, str(outside)]
