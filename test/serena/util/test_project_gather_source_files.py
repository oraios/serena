from serena.project import Project
from solidlsp.ls_config import Language


def test_gather_source_files_includes_language_sources(tmp_path):
    # Create a minimal Clojure-like project structure
    repo = tmp_path / "repo"
    (repo / "src" / "ns").mkdir(parents=True)
    (repo / "src" / "ns" / "core.clj").write_text("(ns ns.core)\n(defn greet [x] x)\n")
    (repo / "deps.edn").write_text("{}\n")

    # Minimal project config
    (repo / ".serena").mkdir()
    (repo / ".serena" / "project.yml").write_text("language: clojure\nproject_name: test\n")

    project = Project.load(str(repo))

    assert project.language == Language.CLOJURE

    files = project.gather_source_files()

    # Should include clojure source files under src/
    assert any(p.endswith("src/ns/core.clj") for p in files), files
    # Should include deps.edn as well (allowed by matcher)
    assert any(p.endswith("deps.edn") for p in files), files
