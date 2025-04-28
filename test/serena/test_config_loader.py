"""
Tests for the configuration loader for contexts and modes.
"""

import os
import tempfile

from serena.util.config_loader import ConfigData, ConfigLoader


def test_config_data_from_dict():
    """Test creating ConfigData from a dictionary."""
    data = {
        "name": "test-context",
        "description": "Test context",
        "system_prompt_extension": "You are in test context",
        "excluded_tools": ["tool1", "tool2"],
        "tool_description_overrides": {"tool3": "Override desc"},
    }

    config = ConfigData.from_dict(data)
    assert config.name == "test-context"
    assert config.description == "Test context"
    assert config.system_prompt_extension == "You are in test context"
    assert config.excluded_tools == {"tool1", "tool2"}
    assert config.tool_description_overrides == {"tool3": "Override desc"}


def test_config_loader_default_dirs():
    """Test that ConfigLoader initializes the default directories."""
    loader = ConfigLoader()
    assert os.path.exists(loader.contexts_dir)
    assert os.path.exists(loader.modes_dir)


def test_load_config_from_file():
    """Test loading a configuration from a file."""
    with tempfile.NamedTemporaryFile(suffix=".yml", mode="w+", delete=False) as f:
        f.write(
            """
name: test-config
description: Test config from file
system_prompt_extension: Test from file
excluded_tools:
  - tool1
  - tool2
tool_description_overrides:
  tool3: Override from file
"""
        )
        f.flush()

        try:
            loader = ConfigLoader()
            config = loader.load_config_from_file(f.name)

            assert config.name == "test-config"
            assert config.description == "Test config from file"
            assert config.system_prompt_extension == "Test from file"
            assert config.excluded_tools == {"tool1", "tool2"}
            assert config.tool_description_overrides == {"tool3": "Override from file"}
        finally:
            os.unlink(f.name)


def test_get_context():
    """Test getting a context by name."""
    loader = ConfigLoader()

    # This assumes contexts/desktop-app.yml exists in the project
    config = loader.get_context("desktop-app")
    assert config.name == "desktop-app"

    # Test cache functionality
    assert "desktop-app" in loader.context_cache


def test_get_mode():
    """Test getting a mode by name."""
    loader = ConfigLoader()

    # This assumes modes/interactive.yml exists in the project
    config = loader.get_mode("interactive")
    assert config.name == "interactive"

    # Test cache functionality
    assert "interactive" in loader.mode_cache


def test_list_available():
    """Test listing available contexts and modes."""
    loader = ConfigLoader()

    contexts = loader.list_available_contexts()
    assert len(contexts) > 0
    assert "desktop-app" in contexts

    modes = loader.list_available_modes()
    assert len(modes) > 0
    assert "interactive" in modes
