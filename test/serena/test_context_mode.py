"""Tests for the context and mode functionality in SerenaAgent."""

import tempfile
from pathlib import Path

import pytest
import yaml

from serena.agent import SerenaAgent
from serena.llm.multilang_prompt import ContextConfig, ModeConfig
from serena.llm.prompt_factory import PromptFactory


def test_context_config():
    """Test that ContextConfig is properly initialized with correct attributes."""
    context = ContextConfig(
        name="test_context",
        description="Test description",
        system_prompt_addition="Test system prompt addition",
        excluded_tools=["tool1", "tool2"],
    )

    assert context.name == "test_context"
    assert context.description == "Test description"
    assert context.system_prompt_addition == "Test system prompt addition"
    assert context.excluded_tools == ["tool1", "tool2"]


def test_mode_config():
    """Test that ModeConfig is properly initialized with correct attributes."""
    mode = ModeConfig(
        name="test_mode",
        description="Test description",
        system_prompt_addition="Test system prompt addition",
        excluded_tools=["tool1", "tool2"],
    )

    assert mode.name == "test_mode"
    assert mode.description == "Test description"
    assert mode.system_prompt_addition == "Test system prompt addition"
    assert mode.excluded_tools == ["tool1", "tool2"]


def test_existing_contexts_and_modes():
    """Test that predefined contexts and modes are loaded correctly."""
    factory = PromptFactory()

    # Test existing contexts
    factory.set_context("agent")
    assert factory.context is not None
    assert factory.context.name == "agent"
    assert "agent" in factory.context.system_prompt_addition.lower()
    assert "initial_instructions" in factory.context.excluded_tools

    factory.set_context("desktop-app")
    assert factory.context is not None
    assert factory.context.name == "desktop-app"

    factory.set_context("ide-assistant")
    assert factory.context is not None
    assert factory.context.name == "ide-assistant"

    # Test existing modes
    factory.set_modes(["editing"])
    assert len(factory.modes) == 1
    assert factory.modes[0].name == "editing"
    assert "editing mode" in factory.modes[0].system_prompt_addition.lower()
    assert factory.modes[0].excluded_tools == []

    factory.set_modes(["planning"])
    assert len(factory.modes) == 1
    assert factory.modes[0].name == "planning"

    # Test with multiple modes
    factory.set_modes(["editing", "interactive"])
    assert len(factory.modes) == 2
    assert factory.modes[0].name == "editing"
    assert factory.modes[1].name == "interactive"


def test_context_and_mode_from_temp_files():
    """Test loading context and mode from custom YAML files."""
    # Create temporary files
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test context config
        context_path = Path(temp_dir) / "test_context.yml"
        context_data = {
            "name": "test_context",
            "description": "Test context from file",
            "system_prompt_addition": "Context from file prompt addition",
            "excluded_tools": ["file_tool1", "file_tool2"],
        }
        with open(context_path, "w") as f:
            yaml.dump(context_data, f)

        # Create test mode config
        mode_path = Path(temp_dir) / "test_mode.yml"
        mode_data = {
            "name": "test_mode",
            "description": "Test mode from file",
            "system_prompt_addition": "Mode from file prompt addition",
            "excluded_tools": ["file_tool3"],
        }
        with open(mode_path, "w") as f:
            yaml.dump(mode_data, f)

        # Test loading from files
        factory = PromptFactory()
        factory.set_context(str(context_path))
        factory.set_modes([str(mode_path)])

        # Check context was loaded correctly
        assert factory.context is not None
        assert factory.context.name == "test_context"
        assert factory.context.description == "Test context from file"
        assert factory.context.system_prompt_addition == "Context from file prompt addition"
        assert factory.context.excluded_tools == ["file_tool1", "file_tool2"]

        # Check mode was loaded correctly
        assert len(factory.modes) == 1
        assert factory.modes[0].name == "test_mode"
        assert factory.modes[0].description == "Test mode from file"
        assert factory.modes[0].system_prompt_addition == "Mode from file prompt addition"
        assert factory.modes[0].excluded_tools == ["file_tool3"]

        # Check excluded tools are collected correctly
        excluded_tools = factory.get_context_and_modes_excluded_tools()
        assert sorted(excluded_tools) == ["file_tool1", "file_tool2", "file_tool3"]


def test_set_context_and_modes_in_agent():
    """Test setting context and modes through SerenaAgent's initialization."""
    # Create a test project config file
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        serena_dir = project_dir / ".serena"
        serena_dir.mkdir()

        project_config = {
            "language": "python",
            "project_root": str(project_dir),
            "ignored_paths": [],
            "excluded_tools": ["project_excluded_tool"],
            "read_only": False,
            "ignore_all_files_in_gitignore": True,
        }

        config_path = serena_dir / "project.yml"
        with open(config_path, "w") as f:
            yaml.dump(project_config, f)

        agent = SerenaAgent(project_file_path=str(config_path), context="agent", modes=["editing", "interactive"])

        # Check context was set
        assert agent.prompt_factory.context is not None
        assert agent.prompt_factory.context.name == "agent"

        # Check modes were set
        assert len(agent.prompt_factory.modes) == 2
        assert agent.prompt_factory.modes[0].name == "editing"
        assert agent.prompt_factory.modes[1].name == "interactive"

        # Test changing modes after initialization
        result = agent.set_modes(["planning"])
        assert result == "OK"
        assert len(agent.prompt_factory.modes) == 1
        assert agent.prompt_factory.modes[0].name == "planning"


def test_excluded_tools_priority():
    """Test that tool exclusion follows the correct priority (project > context > modes)."""
    # Create a mock PromptFactory for tool exclusion testing
    factory = PromptFactory()

    # Set context excluding tools
    context = ContextConfig(
        name="test_context",
        description="Test context",
        system_prompt_addition="",
        excluded_tools=["context_excluded_tool", "both_excluded_tool"],
    )
    factory.context = context

    # Set mode excluding tools
    mode = ModeConfig(
        name="test_mode", description="Test mode", system_prompt_addition="", excluded_tools=["mode_excluded_tool", "both_excluded_tool"]
    )
    factory.modes = [mode]

    # Get combined excluded tools from context and modes
    excluded_tools = factory.get_context_and_modes_excluded_tools()

    # Both lists should be combined and deduplicated
    assert sorted(excluded_tools) == ["both_excluded_tool", "context_excluded_tool", "mode_excluded_tool"]


def test_system_prompt_format():
    """Test the format of system prompts with contexts and modes."""
    factory = PromptFactory()

    # Test with no context or modes
    system_prompt_base = factory.create_system_prompt()

    # Set context
    factory.set_context("agent")
    system_prompt_with_context = factory.create_system_prompt()
    assert len(system_prompt_with_context) > len(system_prompt_base)
    assert "agent" in system_prompt_with_context.lower()

    # Set modes
    factory.set_modes(["editing", "interactive"])
    system_prompt_with_context_and_modes = factory.create_system_prompt()
    assert len(system_prompt_with_context_and_modes) > len(system_prompt_with_context)
    assert "editing mode" in system_prompt_with_context_and_modes.lower()
    assert "interactive" in system_prompt_with_context_and_modes.lower()


def test_mode_conflict_detection():
    """Test that conflicting mode tool exclusions are detected."""
    # Create a temporary file with conflicting modes
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary project file
        project_dir = Path(temp_dir)
        serena_dir = project_dir / ".serena"
        serena_dir.mkdir()

        project_config = {
            "language": "python",
            "project_root": str(project_dir),
            "ignored_paths": [],
            "excluded_tools": [],
            "read_only": False,
            "ignore_all_files_in_gitignore": True,
        }

        config_path = serena_dir / "project.yml"
        with open(config_path, "w") as f:
            yaml.dump(project_config, f)

        # Create first mode
        mode1_path = Path(temp_dir) / "mode1.yml"
        mode1_data = {
            "name": "conflict_mode1",
            "description": "Test mode with conflict",
            "system_prompt_addition": "",
            "excluded_tools": ["conflict_tool"],
        }
        with open(mode1_path, "w") as f:
            yaml.dump(mode1_data, f)

        # Create second mode (conflicting)
        mode2_path = Path(temp_dir) / "mode2.yml"
        mode2_data = {
            "name": "conflict_mode2",
            "description": "Test mode without the same exclusion",
            "system_prompt_addition": "",
            "excluded_tools": [],  # Does not exclude conflict_tool
        }
        with open(mode2_path, "w") as f:
            yaml.dump(mode2_data, f)

        # Conflict detection happens in SerenaAgent, not directly in PromptFactory
        try:
            # First try creating with one mode (should work)
            agent = SerenaAgent(project_file_path=str(config_path), modes=[str(mode1_path)])

            # Now try with both conflicting modes
            with pytest.raises(ValueError) as excinfo:
                # This will trigger the conflict detection in _set_context_and_modes
                agent._set_context_and_modes(None, [str(mode1_path), str(mode2_path)])

            # Check error message contains info about the conflict
            assert "conflict_tool" in str(excinfo.value)
            assert "conflicting exclusion settings" in str(excinfo.value)

        except Exception as e:
            # If agent creation fails due to language server, we'll skip
            # (but preserve the original test failure if that happens)
            if "Failed to start the language server" in str(e):
                pytest.skip("Language server failed to start")
            else:
                raise
