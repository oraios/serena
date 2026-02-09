"""Tests for SerenaAgent.set_modes() to verify that mode switching works correctly."""

import logging

from serena.agent import SerenaAgent
from serena.config.serena_config import ModeSelectionDefinition, SerenaConfig


class TestSetModes:
    """Test that set_modes correctly changes active modes."""

    def _create_agent(self, modes: ModeSelectionDefinition | None = None) -> SerenaAgent:
        config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)
        return SerenaAgent(serena_config=config, modes=modes)

    def test_set_modes_changes_active_modes(self) -> None:
        """Test that calling set_modes actually changes the active modes."""
        agent = self._create_agent(modes=ModeSelectionDefinition(default_modes=["editing", "interactive"]))

        initial_mode_names = sorted(m.name for m in agent.get_active_modes())
        assert "editing" in initial_mode_names
        assert "interactive" in initial_mode_names

        # Switch to planning mode
        agent.set_modes(["planning", "interactive"])

        new_mode_names = sorted(m.name for m in agent.get_active_modes())
        assert "planning" in new_mode_names
        assert "interactive" in new_mode_names
        assert "editing" not in new_mode_names

    def test_set_modes_overrides_config_defaults(self) -> None:
        """Test that set_modes takes precedence over config defaults."""
        config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR)
        config.default_modes = ["editing", "interactive"]
        agent = SerenaAgent(serena_config=config)

        # Verify config defaults are active
        initial_mode_names = [m.name for m in agent.get_active_modes()]
        assert "editing" in initial_mode_names

        # Switch modes — should override config defaults
        agent.set_modes(["planning", "one-shot"])

        new_mode_names = [m.name for m in agent.get_active_modes()]
        assert "planning" in new_mode_names
        assert "one-shot" in new_mode_names
        assert "editing" not in new_mode_names

    def test_set_modes_persists_after_repeated_calls(self) -> None:
        """Test that set_modes result persists (modes don't revert)."""
        agent = self._create_agent(modes=ModeSelectionDefinition(default_modes=["editing"]))

        agent.set_modes(["planning"])
        mode_names_1 = [m.name for m in agent.get_active_modes()]
        assert "planning" in mode_names_1

        # Call get_active_modes again — should still be planning
        mode_names_2 = [m.name for m in agent.get_active_modes()]
        assert mode_names_1 == mode_names_2

    def test_set_modes_can_switch_back(self) -> None:
        """Test that modes can be switched back to original after switching away."""
        agent = self._create_agent(modes=ModeSelectionDefinition(default_modes=["editing", "interactive"]))

        # Switch away
        agent.set_modes(["planning", "one-shot"])
        assert "planning" in [m.name for m in agent.get_active_modes()]

        # Switch back
        agent.set_modes(["editing", "interactive"])
        mode_names = [m.name for m in agent.get_active_modes()]
        assert "editing" in mode_names
        assert "interactive" in mode_names
        assert "planning" not in mode_names
