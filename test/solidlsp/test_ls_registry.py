import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from serena.config.serena_config import ProjectConfig
from serena.constants import PROJECT_TEMPLATE_FILE
from solidlsp import SolidLanguageServer
from solidlsp.language_server_adapter_discovery import (
    ENTRY_POINT_GROUP,
    _reset_language_server_adapter_discovery_for_tests,
    discover_registered_language_server_adapters,
)
from solidlsp.ls_config import (
    FilenameMatcher,
    LanguageServerConfig,
    LanguageServerId,
    RegisteredLanguageServerId,
    _reset_registered_language_servers_for_tests,
    register_ls,
    resolve_language_server_id,
)
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings
from test.conftest import create_default_serena_config


@pytest.fixture(autouse=True)
def isolated_registry() -> None:
    _reset_registered_language_servers_for_tests()
    _reset_language_server_adapter_discovery_for_tests()
    yield
    _reset_registered_language_servers_for_tests()
    _reset_language_server_adapter_discovery_for_tests()


@dataclass
class FakeDistribution:
    name: str


class FakeEntryPoint:
    def __init__(self, name: str, registration: Callable[[], None], distribution: str = "test-adapter") -> None:
        self.name = name
        self._registration = registration
        self.dist = FakeDistribution(distribution)

    def load(self) -> Callable[[], None]:
        return self._registration


def install_entry_points(monkeypatch: pytest.MonkeyPatch, *entry_points: FakeEntryPoint) -> None:
    def fake_entry_points(*, group: str) -> tuple[FakeEntryPoint, ...]:
        assert group == ENTRY_POINT_GROUP
        return entry_points

    monkeypatch.setattr("solidlsp.language_server_adapter_discovery.metadata.entry_points", fake_entry_points)


class DummyLanguageServer(SolidLanguageServer):
    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=["dummy"], cwd=repository_root_path), "dummy", solidlsp_settings
        )

    def _create_base_initialize_params(self) -> dict:
        return {}

    def _start_server(self) -> None:
        self.server.start()


class OtherDummyLanguageServer(DummyLanguageServer):
    pass


def test_builtin_language_ids_remain_resolvable() -> None:
    assert resolve_language_server_id("python") is LanguageServerId.PYTHON


def test_unknown_language_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown language server"):
        resolve_language_server_id("missing-custom-language")


def test_entry_point_discovery_registers_an_external_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    def register_dummy() -> None:
        register_ls("dummy", FilenameMatcher(".dummy"), DummyLanguageServer)

    install_entry_points(monkeypatch, FakeEntryPoint("dummy", register_dummy))
    discover_registered_language_server_adapters()

    assert resolve_language_server_id("dummy").get_ls_class() is DummyLanguageServer


def test_entry_point_discovery_registers_multiple_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    def register_first() -> None:
        register_ls("dummy-one", FilenameMatcher(".one"), DummyLanguageServer)

    def register_second() -> None:
        register_ls("dummy-two", FilenameMatcher(".two"), OtherDummyLanguageServer)

    install_entry_points(monkeypatch, FakeEntryPoint("first", register_first), FakeEntryPoint("second", register_second))
    discover_registered_language_server_adapters()

    assert resolve_language_server_id("dummy-one").get_ls_class() is DummyLanguageServer
    assert resolve_language_server_id("dummy-two").get_ls_class() is OtherDummyLanguageServer


def test_two_registered_language_servers_are_resolvable_together() -> None:
    first = register_ls("dummy-one", FilenameMatcher(".one"), DummyLanguageServer)
    second = register_ls("dummy-two", FilenameMatcher(".two"), OtherDummyLanguageServer)

    assert isinstance(first, RegisteredLanguageServerId)
    assert resolve_language_server_id("dummy-one") == first
    assert resolve_language_server_id("dummy-two") == second
    assert first.get_source_fn_matcher().is_relevant_filename("file.one")
    assert second.get_source_fn_matcher().is_relevant_filename("file.two")

    with tempfile.TemporaryDirectory() as project_data_path:
        settings = SolidLSPSettings(project_data_path=project_data_path)
        first_server = SolidLanguageServer.create(
            LanguageServerConfig(ls_id=first),
            project_data_path,
            solidlsp_settings=settings,
        )
        second_server = SolidLanguageServer.create(
            LanguageServerConfig(ls_id=second),
            project_data_path,
            solidlsp_settings=settings,
        )

    assert first_server.ls_id == first
    assert second_server.ls_id == second


def test_discovered_language_server_roundtrips_through_project_config(monkeypatch: pytest.MonkeyPatch) -> None:
    def register_roundtrip() -> None:
        register_ls("roundtrip", FilenameMatcher(".round"), DummyLanguageServer)

    install_entry_points(monkeypatch, FakeEntryPoint("roundtrip", register_roundtrip))
    data, _ = ProjectConfig._load_yaml_dict(PROJECT_TEMPLATE_FILE)
    data["project_name"] = "test"
    data["language_servers"] = ["roundtrip"]

    config = ProjectConfig._from_dict(data, local_override_keys=[])
    assert config.language_servers == [resolve_language_server_id("roundtrip")]
    assert config._to_yaml_dict()["language_servers"] == ["roundtrip"]


def test_project_yml_resolves_discovered_quickscript_adapter(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def register_quickscript() -> None:
        register_ls("quickscript", FilenameMatcher(".vbi", ".vi", case_sensitive=False), DummyLanguageServer)

    install_entry_points(monkeypatch, FakeEntryPoint("quickscript", register_quickscript, "intouch-language-serena"))
    project_config_path = tmp_path / ".serena"
    project_config_path.mkdir()
    (project_config_path / "project.yml").write_text('project_name: "quickscript"\nlanguage_servers: ["quickscript"]\n')

    config = ProjectConfig.load(tmp_path, create_default_serena_config())

    assert config.language_servers == [resolve_language_server_id("quickscript")]


def test_duplicate_registration_and_builtin_override_are_rejected() -> None:
    register_ls("duplicate", FilenameMatcher(".dup"), DummyLanguageServer)
    with pytest.raises(ValueError, match="already registered"):
        register_ls("duplicate", FilenameMatcher(".dup"), DummyLanguageServer)
    with pytest.raises(ValueError, match="already built in"):
        register_ls("python", FilenameMatcher(".py"), DummyLanguageServer)


def test_registry_reset_isolation() -> None:
    register_ls("temporary", FilenameMatcher(".tmp"), DummyLanguageServer)
    assert resolve_language_server_id("temporary").value == "temporary"
    _reset_registered_language_servers_for_tests()
    with pytest.raises(ValueError, match="Unknown language server"):
        resolve_language_server_id("temporary")


def test_failing_entry_point_logs_its_distribution_and_rolls_back_registration(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def register_broken_adapter() -> None:
        register_ls("broken", FilenameMatcher(".broken"), DummyLanguageServer)
        raise RuntimeError("registration failed")

    install_entry_points(monkeypatch, FakeEntryPoint("broken", register_broken_adapter, "broken-adapter"))
    with caplog.at_level(logging.ERROR):
        discover_registered_language_server_adapters()

    with pytest.raises(ValueError, match="Unknown language server"):
        resolve_language_server_id("broken")
    assert "broken" in caplog.text
    assert "broken-adapter" in caplog.text


def test_quickscript_entry_point_registers_its_matcher(monkeypatch: pytest.MonkeyPatch) -> None:
    def register_quickscript() -> None:
        register_ls("quickscript", FilenameMatcher(".vbi", ".vi", case_sensitive=False), DummyLanguageServer)

    install_entry_points(monkeypatch, FakeEntryPoint("quickscript", register_quickscript, "intouch-language-serena"))
    discover_registered_language_server_adapters()

    quickscript = resolve_language_server_id("quickscript")
    assert isinstance(quickscript, RegisteredLanguageServerId)
    matcher = quickscript.get_source_fn_matcher()
    assert matcher.is_relevant_filename("definition.vbi")
    assert matcher.is_relevant_filename("caller.vi")
    assert not matcher.is_relevant_filename("README.md")
