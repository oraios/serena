"""
Unit tests for the detection of Scala build roots, which Metals is given as workspace folders.
"""

from pathlib import Path

import pytest

from solidlsp.language_servers.scala_language_server import find_build_roots


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

    def test_bsp_directory_marks_a_build_root(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / ".bsp").mkdir(parents=True)
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend")]

    def test_sbt_build_defined_only_under_project(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / "project").mkdir(parents=True)
        (tmp_path / "backend" / "project" / "build.properties").write_text("sbt.version=1.11.7\n")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path / "backend")]

    def test_build_properties_without_a_version_is_not_a_build_root(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / "project").mkdir(parents=True)
        (tmp_path / "backend" / "project" / "build.properties").write_text("# nothing to see here\n")
        assert find_build_roots(str(tmp_path)) == [str(tmp_path)]
