from serena.config.context_mode import SerenaAgentMode


def test_planning_mode_excludes_rename_symbol():
    """Planning mode is read-only, so symbol renaming must not be available in it."""
    mode = SerenaAgentMode.from_name("planning")

    assert "rename_symbol" in mode.excluded_tools
