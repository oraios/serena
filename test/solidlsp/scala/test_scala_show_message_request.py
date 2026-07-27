"""
Unit tests for Serena's answer to Metals' `window/showMessageRequest` prompts.
"""

import pytest

from solidlsp.language_servers.scala_language_server import (
    _get_scala_settings,
    choose_show_message_request_action,
)
from solidlsp.ls_config import LanguageServerId
from solidlsp.settings import SolidLSPSettings

# Metals' own prompts, with the message and action titles as its `Messages` object builds them
# (scala/meta/internal/metals/Messages.scala) and `type` as lsp4j serialises `MessageType.Info`.
IMPORT_BUILD = {
    "message": "New sbt workspace detected, would you like to import the build?",
    "type": 3,
    "actions": [{"title": "Import build"}, {"title": "Not now"}, {"title": "Don't show again"}],
}
IMPORT_CHANGES = {
    "message": "sbt build needs to be re-imported",
    "type": 3,
    "actions": [{"title": "Import changes"}, {"title": "Not now"}, {"title": "Don't show again"}],
}
GENERATE_BSP_AND_CONNECT = {
    "message": "New sbt workspace detected, would you like connect to the Bloop build server?",
    "type": 3,
    "actions": [{"title": "Connect"}, {"title": "Not now"}, {"title": "Don't show again"}],
}
OLD_BLOOP_VERSION_RUNNING = {
    "message": "Deprecated Bloop server is still running and is taking up resources, do you want to kill the process?",
    "type": 3,
    "actions": [{"title": "Yes"}, {"title": "Not now"}],
}
CHOOSE_BUILD_TOOL = {
    "message": "Multiple build definitions found. Which would you like to use?",
    "type": 3,
    "actions": [{"title": "sbt"}, {"title": "mill"}],
}


@pytest.mark.scala
class TestChooseShowMessageRequestAction:
    @pytest.mark.parametrize("params", [IMPORT_BUILD, IMPORT_CHANGES, GENERATE_BSP_AND_CONNECT])
    def test_build_import_prompts_are_answered_affirmatively(self, params: dict) -> None:
        chosen = choose_show_message_request_action(params)
        assert chosen is not None
        assert chosen["title"] in ("Import build", "Import changes", "Connect")

    @pytest.mark.parametrize("params", [IMPORT_BUILD, IMPORT_CHANGES, GENERATE_BSP_AND_CONNECT])
    def test_auto_import_build_can_be_turned_off(self, params: dict) -> None:
        assert choose_show_message_request_action(params, auto_import_build=False) is None

    def test_dont_show_again_is_never_chosen(self) -> None:
        """Metals persists that dismissal in the project's own state."""
        params = {"message": "…", "actions": [{"title": "Don't show again"}, {"title": "Not now"}]}
        assert choose_show_message_request_action(params) is None

    def test_an_unrecognised_prompt_is_dismissed(self) -> None:
        """Answering "Yes" here would kill a process on the user's machine."""
        assert choose_show_message_request_action(OLD_BLOOP_VERSION_RUNNING) is None

    def test_a_prompt_with_no_actions_is_dismissed(self) -> None:
        assert choose_show_message_request_action({"message": "just so you know"}) is None
        assert choose_show_message_request_action({"message": "just so you know", "actions": None}) is None

    def test_malformed_actions_do_not_raise(self) -> None:
        params = {"message": "…", "actions": ["Import build", None, {"title": "Import build"}]}
        assert choose_show_message_request_action(params) == {"title": "Import build"}

    def test_choosing_between_build_tools_is_left_alone(self) -> None:
        """Naming the build tool for the user is a guess of a different order; see the comment
        on BUILD_IMPORT_PROMPT_ACTIONS. A workspace with several build definitions is therefore
        still not imported.
        """
        assert choose_show_message_request_action(CHOOSE_BUILD_TOOL) is None


@pytest.mark.scala
class TestAutoImportBuildSetting:
    """`auto_import_build` has to reach the handler from the project configuration."""

    @staticmethod
    def setting(**scala_settings) -> object:
        settings = SolidLSPSettings(ls_specific_settings={LanguageServerId.SCALA: scala_settings})
        return _get_scala_settings(settings)["auto_import_build"]

    def test_defaults_to_true(self) -> None:
        assert self.setting() is True
        assert _get_scala_settings(SolidLSPSettings())["auto_import_build"] is True

    def test_can_be_disabled(self) -> None:
        assert self.setting(auto_import_build=False) is False
