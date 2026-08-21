import logging
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest

from serena.config.serena_config import ProjectConfig
from serena.constants import PROJECT_TEMPLATE_FILE
from serena.ls_manager import LanguageServerFactory, LanguageServerManager
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
    LanguageServerKey,
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


def test_resolving_language_id_does_not_trigger_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_discovered(*, group: str) -> tuple[FakeEntryPoint, ...]:
        raise AssertionError(f"Discovery unexpectedly triggered for {group}")

    monkeypatch.setattr("solidlsp.language_server_adapter_discovery.metadata.entry_points", fail_if_discovered)

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


def test_entry_point_metadata_failure_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_entry_points(*, group: str) -> tuple[FakeEntryPoint, ...]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("metadata unavailable")

        def register_dummy() -> None:
            register_ls("retryable", FilenameMatcher(".retry"), DummyLanguageServer)

        return (FakeEntryPoint("retryable", register_dummy),)

    monkeypatch.setattr("solidlsp.language_server_adapter_discovery.metadata.entry_points", fake_entry_points)
    discover_registered_language_server_adapters()
    discover_registered_language_server_adapters()

    assert calls == 2
    assert resolve_language_server_id("retryable").get_ls_class() is DummyLanguageServer


def test_concurrent_discovery_registers_each_adapter_once(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata_calls = 0
    registration_calls = 0
    calls_lock = threading.Lock()
    second_metadata_call = threading.Event()
    start_barrier = threading.Barrier(2)

    def register_concurrent() -> None:
        nonlocal registration_calls
        with calls_lock:
            registration_calls += 1
        register_ls("concurrent", FilenameMatcher(".concurrent"), DummyLanguageServer)

    entry_point = FakeEntryPoint("concurrent", register_concurrent)

    def fake_entry_points(*, group: str) -> tuple[FakeEntryPoint, ...]:
        nonlocal metadata_calls
        assert group == ENTRY_POINT_GROUP
        with calls_lock:
            metadata_calls += 1
            call_number = metadata_calls
        if call_number == 1:
            second_metadata_call.wait(timeout=1)
        else:
            second_metadata_call.set()
        return (entry_point,)

    monkeypatch.setattr("solidlsp.language_server_adapter_discovery.metadata.entry_points", fake_entry_points)

    def discover_after_barrier() -> None:
        start_barrier.wait()
        discover_registered_language_server_adapters()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(discover_after_barrier) for _ in range(2)]
        for future in futures:
            future.result()

    assert metadata_calls == 1
    assert registration_calls == 1
    assert resolve_language_server_id("concurrent").get_ls_class() is DummyLanguageServer


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
    discover_registered_language_server_adapters()
    data, _ = ProjectConfig._load_yaml_dict(PROJECT_TEMPLATE_FILE)
    data["project_name"] = "test"
    data["language_servers"] = ["roundtrip"]

    config = ProjectConfig._from_dict(data, local_override_keys=[])
    assert config.language_servers == [resolve_language_server_id("roundtrip")]
    assert config._to_yaml_dict()["language_servers"] == ["roundtrip"]


def test_project_yml_resolves_discovered_external_adapter(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def register_example() -> None:
        register_ls("example-adapter", FilenameMatcher(".example"), DummyLanguageServer)

    install_entry_points(monkeypatch, FakeEntryPoint("example", register_example, "example-serena-adapter"))
    project_config_path = tmp_path / ".serena"
    project_config_path.mkdir()
    (project_config_path / "project.yml").write_text('project_name: "external-example"\nlanguage_servers: ["example-adapter"]\n')

    config = ProjectConfig.load(tmp_path, create_default_serena_config())

    assert config.language_servers == [resolve_language_server_id("example-adapter")]


@pytest.mark.parametrize(
    ("registration_id", "message"),
    [
        ("", "non-empty"),
        ("   ", "non-empty"),
        (" leading", "trimmed"),
        ("trailing ", "trimmed"),
        ("Mixed-Case", "lowercase"),
    ],
)
def test_registration_rejects_noncanonical_ids(registration_id: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        register_ls(registration_id, FilenameMatcher(".example"), DummyLanguageServer)


def test_duplicate_registration_and_builtin_override_are_rejected() -> None:
    register_ls("duplicate", FilenameMatcher(".dup"), DummyLanguageServer)
    with pytest.raises(ValueError, match="already registered"):
        register_ls("duplicate", FilenameMatcher(".dup"), DummyLanguageServer)
    with pytest.raises(ValueError, match="already built in"):
        register_ls("python", FilenameMatcher(".py"), DummyLanguageServer)


def test_implementation_class_cannot_be_registered_under_multiple_external_ids() -> None:
    register_ls("first-id", FilenameMatcher(".first"), DummyLanguageServer)

    with pytest.raises(ValueError, match="DummyLanguageServer.*first-id"):
        register_ls("second-id", FilenameMatcher(".second"), DummyLanguageServer)

    with pytest.raises(ValueError, match="Unknown language server"):
        resolve_language_server_id("second-id")


def test_builtin_implementation_class_cannot_be_registered_under_external_id() -> None:
    python_implementation = LanguageServerId.PYTHON.get_ls_class()

    with pytest.raises(ValueError, match="python-alias.*PyrightServer.*built-in id 'python'"):
        register_ls("python-alias", FilenameMatcher(".alias"), python_implementation)

    with pytest.raises(ValueError, match="Unknown language server"):
        resolve_language_server_id("python-alias")


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


def test_failing_entry_point_does_not_block_other_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    def register_broken_adapter() -> None:
        register_ls("broken", FilenameMatcher(".broken"), DummyLanguageServer)
        raise RuntimeError("registration failed")

    def register_working_adapter() -> None:
        register_ls("working", FilenameMatcher(".working"), OtherDummyLanguageServer)

    install_entry_points(
        monkeypatch,
        FakeEntryPoint("broken", register_broken_adapter, "broken-adapter"),
        FakeEntryPoint("working", register_working_adapter, "working-adapter"),
    )
    discover_registered_language_server_adapters()

    with pytest.raises(ValueError, match="Unknown language server"):
        resolve_language_server_id("broken")
    assert resolve_language_server_id("working").get_ls_class() is OtherDummyLanguageServer


def test_external_entry_point_registers_its_matcher(monkeypatch: pytest.MonkeyPatch) -> None:
    def register_example() -> None:
        register_ls("case-insensitive-example", FilenameMatcher(".sample", ".fixture", case_sensitive=False), DummyLanguageServer)

    install_entry_points(monkeypatch, FakeEntryPoint("example", register_example, "example-serena-adapter"))
    discover_registered_language_server_adapters()

    external_id = resolve_language_server_id("case-insensitive-example")
    assert isinstance(external_id, RegisteredLanguageServerId)
    matcher = external_id.get_source_fn_matcher()
    assert matcher.is_relevant_filename("definition.SAMPLE")
    assert matcher.is_relevant_filename("caller.fixture")
    assert not matcher.is_relevant_filename("README.md")


def test_factory_and_manager_route_mixed_builtin_and_external_ids(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    external_id = register_ls("external-example", FilenameMatcher(".external"), DummyLanguageServer)
    data, _ = ProjectConfig._load_yaml_dict(PROJECT_TEMPLATE_FILE)
    data["project_name"] = "mixed-language-servers"
    data["language_servers"] = ["python", "external-example"]
    data["ls_specific_settings"] = {"external-example": {"mode": "external"}}
    project_config = ProjectConfig._from_dict(data, local_override_keys=[])
    captured_settings: dict[LanguageServerKey, str | None] = {}
    captured_settings_lock = threading.Lock()

    class FakeLanguageServer:
        def __init__(self, ls_id: LanguageServerKey) -> None:
            self.ls_id = ls_id
            self._running = False

        def start(self) -> None:
            self._running = True

        def is_running(self) -> bool:
            return self._running

        def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool) -> bool:
            return not self.ls_id.get_source_fn_matcher().is_relevant_filename(relative_path)

    def fake_create(config, repository_root_path, timeout=None, solidlsp_settings=None):
        assert solidlsp_settings is not None
        with captured_settings_lock:
            captured_settings[config.ls_id] = solidlsp_settings.get_ls_specific_settings(config.ls_id).get("mode")
        return FakeLanguageServer(config.ls_id)

    class FakeProject:
        project_root = str(tmp_path)

        @staticmethod
        def gather_source_files() -> list[str]:
            return []

    class FakeSerenaPaths:
        serena_user_home_dir = str(tmp_path / "serena-home")

    monkeypatch.setattr(SolidLanguageServer, "create", staticmethod(fake_create))
    monkeypatch.setattr("serena.ls_manager.SerenaPaths", FakeSerenaPaths)
    factory = LanguageServerFactory(
        project_root=str(tmp_path),
        project_config=project_config,
        project_data_path=str(tmp_path / "project-data"),
        encoding="utf-8",
        ignored_patterns=[],
        ls_specific_settings=project_config.ls_specific_settings,
    )

    manager = LanguageServerManager.from_languages(project_config.language_servers, factory, FakeProject())

    assert manager.get_active_language_server_ids() == [LanguageServerId.PYTHON, external_id]
    assert manager.get_language_server("module.py").ls_id is LanguageServerId.PYTHON
    assert manager.get_language_server("module.external").ls_id == external_id
    assert captured_settings[LanguageServerId.PYTHON] is None
    assert captured_settings[external_id] == "external"
