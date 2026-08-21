import tempfile

import pytest

from serena.config.serena_config import ProjectConfig
from serena.constants import PROJECT_TEMPLATE_FILE
from solidlsp import SolidLanguageServer
from solidlsp.language_servers.quickscript_language_server import QuickScriptLanguageServer
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


@pytest.fixture(autouse=True)
def isolated_registry() -> None:
    _reset_registered_language_servers_for_tests()
    register_ls("quickscript", FilenameMatcher(".vbi", ".vi", case_sensitive=False), QuickScriptLanguageServer)
    yield
    _reset_registered_language_servers_for_tests()


class DummyLanguageServer(SolidLanguageServer):
    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(config, repository_root_path, ProcessLaunchInfo(cmd=["dummy"], cwd=repository_root_path), "dummy", solidlsp_settings)

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


def test_registered_language_server_roundtrips_through_project_config() -> None:
    registered = register_ls("roundtrip", FilenameMatcher(".round"), DummyLanguageServer)
    data, _ = ProjectConfig._load_yaml_dict(PROJECT_TEMPLATE_FILE)
    data["project_name"] = "test"
    data["language_servers"] = [registered.value]

    config = ProjectConfig._from_dict(data, local_override_keys=[])
    assert config.language_servers == [registered]
    assert config._to_yaml_dict()["language_servers"] == ["roundtrip"]


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
    register_ls("quickscript", FilenameMatcher(".vbi", ".vi", case_sensitive=False), QuickScriptLanguageServer)


def test_quickscript_is_explicitly_registered() -> None:
    quickscript = resolve_language_server_id("quickscript")
    assert isinstance(quickscript, RegisteredLanguageServerId)
    assert quickscript.get_ls_class() is QuickScriptLanguageServer
    matcher = quickscript.get_source_fn_matcher()
    assert matcher.is_relevant_filename("definition.vbi")
    assert matcher.is_relevant_filename("caller.vi")
    assert not matcher.is_relevant_filename("README.md")
