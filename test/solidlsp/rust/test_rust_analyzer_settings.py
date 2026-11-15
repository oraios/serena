from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pathspec
import pytest

from solidlsp import SolidLanguageServer
from solidlsp.language_servers.rust_analyzer import RustAnalyzer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId

pytestmark = pytest.mark.rust


def _make_server() -> RustAnalyzer:
    return object.__new__(RustAnalyzer)


def _make_server_for_root(repository_root: Path, ignored_paths: tuple[str, ...] = ()) -> RustAnalyzer:
    server = _make_server()
    server.repository_root_path = str(repository_root)
    server.config = LanguageServerConfig(ls_id=LanguageServerId.RUST, ignored_paths=list(ignored_paths))
    server._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ignored_paths)
    return server


def _write_cargo_package(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "Cargo.toml").write_text("[package]\nname = 'example'\n", encoding="utf-8")


def test_initialization_uses_lightweight_indexing_settings(tmp_path: Path) -> None:
    initialization_options = _make_server_for_root(tmp_path)._create_base_initialize_params()["initializationOptions"]

    assert initialization_options["cachePriming"]["enable"] is False
    assert initialization_options["checkOnSave"] is True


@pytest.mark.parametrize("pull_diagnostics_failed", [False, True])
def test_published_diagnostics_wait_has_eight_second_minimum(pull_diagnostics_failed: bool) -> None:
    assert _make_server()._get_published_diagnostics_wait_timeout(pull_diagnostics_failed) == 8.0


def test_published_diagnostics_wait_preserves_larger_base_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def wider_base_timeout(_server: SolidLanguageServer, _pull_diagnostics_failed: bool) -> float:
        return 12.0

    monkeypatch.setattr(SolidLanguageServer, "_get_published_diagnostics_wait_timeout", wider_base_timeout)

    assert _make_server()._get_published_diagnostics_wait_timeout(False) == 12.0


def test_diagnostics_request_triggers_check_on_save(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _make_server()
    server_interface = MagicMock()
    server.server = cast(Any, server_interface)
    uri = "file:///workspace/src/lib.rs"

    monkeypatch.setattr(server, "_validate_text_document_diagnostics_request", lambda *_args: uri)
    monkeypatch.setattr(server, "open_file", lambda _relative_file_path: nullcontext())
    monkeypatch.setattr(SolidLanguageServer, "request_text_document_diagnostics", lambda *_args, **_kwargs: [])

    assert server.request_text_document_diagnostics("src/lib.rs") == []
    server_interface.notify.did_save_text_document.assert_called_once_with({"textDocument": {"uri": uri}})


def test_initialization_links_nested_cargo_manifests(tmp_path: Path) -> None:
    _write_cargo_package(tmp_path / "native" / "ex_evm_sign")
    _write_cargo_package(tmp_path / "crates" / "taskfast-attestation")

    initialization_options = _make_server_for_root(tmp_path)._create_base_initialize_params()["initializationOptions"]

    assert initialization_options["linkedProjects"] == [
        str(tmp_path / "crates" / "taskfast-attestation" / "Cargo.toml"),
        str(tmp_path / "native" / "ex_evm_sign" / "Cargo.toml"),
    ]


def test_initialization_links_manifests_with_an_ancestor_manifest_only(tmp_path: Path) -> None:
    _write_cargo_package(tmp_path)
    _write_cargo_package(tmp_path / "crates" / "member")

    initialization_options = _make_server_for_root(tmp_path)._create_base_initialize_params()["initializationOptions"]

    assert initialization_options["linkedProjects"] == [str(tmp_path / "Cargo.toml")]


def test_initialization_skips_manifests_in_ignored_directories(tmp_path: Path) -> None:
    _write_cargo_package(tmp_path / "native" / "real_crate")
    _write_cargo_package(tmp_path / "native" / "target" / "debug" / "build_output")
    _write_cargo_package(tmp_path / "vendor" / "vendored_crate")

    initialization_options = _make_server_for_root(tmp_path, ignored_paths=("vendor/",))._create_base_initialize_params()[
        "initializationOptions"
    ]

    assert initialization_options["linkedProjects"] == [str(tmp_path / "native" / "real_crate" / "Cargo.toml")]
