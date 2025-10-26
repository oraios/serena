import pathlib

from solidlsp.language_servers.gdscript_language_server import DEFAULT_GODOT_VERSION, GDScriptLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings


def test_language_settings_reads_variants(solidlsp_settings: SolidLSPSettings) -> None:
    solidlsp_settings.ls_specific_settings = {Language.GDSCRIPT: {"enum": True}}
    assert GDScriptLanguageServer._language_settings(solidlsp_settings) == {"enum": True}

    solidlsp_settings.ls_specific_settings = {"gdscript": {"fallback": True}}
    assert GDScriptLanguageServer._language_settings(solidlsp_settings) == {"fallback": True}

    solidlsp_settings.ls_specific_settings = {"GDSCRIPT": {"upper": True}}
    assert GDScriptLanguageServer._language_settings(solidlsp_settings) == {"upper": True}


def test_select_godot_version_defaults(logger: LanguageServerLogger) -> None:
    assert GDScriptLanguageServer._select_godot_version({}, logger) == DEFAULT_GODOT_VERSION
    custom = GDScriptLanguageServer._select_godot_version({"godot_version": " 5.0-beta "}, logger)
    assert custom == "5.0-beta"


def test_initialize_params_include_workspace_root(tmp_path: pathlib.Path) -> None:
    params = GDScriptLanguageServer._get_initialize_params(str(tmp_path))
    assert params["rootUri"] == pathlib.Path(tmp_path).as_uri()
    assert params["workspaceFolders"][0]["uri"] == pathlib.Path(tmp_path).as_uri()
