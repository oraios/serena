"""
Tests for the context and mode configuration feature.
"""
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from serena.context_mode_config import (
    ContextConfig,
    ModeConfig,
    ToolSettings,
    load_context_config,
    load_mode_config,
    resolve_tool_activations,
)


def test_resolve_tool_activations():
    """Test that tool activations are correctly resolved."""
    # Create test configurations
    context = ContextConfig(
        name="test-context",
        description="Test Context",
        tool_settings=ToolSettings(
            included_tools=["tool1", "tool2"],
            excluded_tools=["tool3"]
        ),
        prompt_extension="Context prompt extension"
    )
    
    modes = [
        ModeConfig(
            name="test-mode-1",
            description="Test Mode 1",
            tool_settings=ToolSettings(
                included_tools=["tool4"],
                excluded_tools=["tool5"]
            ),
            prompt_extension="Mode 1 prompt extension"
        ),
        ModeConfig(
            name="test-mode-2",
            description="Test Mode 2",
            tool_settings=ToolSettings(
                included_tools=["tool6"],
                excluded_tools=["tool7"]
            ),
            prompt_extension="Mode 2 prompt extension"
        )
    ]
    
    included, excluded = resolve_tool_activations(context, modes)
    
    # Context takes precedence
    assert "tool1" in included
    assert "tool2" in included
    assert "tool3" in excluded
    
    # Modes are also applied
    assert "tool4" in included
    assert "tool5" in excluded
    assert "tool6" in included
    assert "tool7" in excluded


def test_resolve_tool_activations_conflict_detection():
    """Test that conflicts between modes are detected."""
    mode1 = ModeConfig(
        name="mode1",
        description="Mode 1",
        tool_settings=ToolSettings(
            included_tools=["tool1"],
            excluded_tools=[]
        ),
        prompt_extension="Mode 1 prompt extension"
    )
    
    mode2 = ModeConfig(
        name="mode2",
        description="Mode 2",
        tool_settings=ToolSettings(
            included_tools=[],
            excluded_tools=["tool1"]
        ),
        prompt_extension="Mode 2 prompt extension"
    )
    
    # This should raise a conflict error
    with pytest.raises(ValueError):
        resolve_tool_activations(None, [mode1, mode2])


def test_context_priority_over_modes():
    """Test that context takes precedence over modes."""
    # Mode tries to exclude tool1, but context includes it
    context = ContextConfig(
        name="test-context",
        description="Test Context",
        tool_settings=ToolSettings(
            included_tools=["tool1", "tool2"],
            excluded_tools=["tool3"]
        ),
        prompt_extension="Context prompt extension"
    )
    
    mode = ModeConfig(
        name="mode",
        description="Mode",
        tool_settings=ToolSettings(
            included_tools=[],
            excluded_tools=["tool1", "tool2"]
        ),
        prompt_extension="Mode prompt extension"
    )
    
    included, excluded = resolve_tool_activations(context, [mode])
    
    # Context includes should override mode excludes
    assert "tool1" in included
    assert "tool2" in included
    assert "tool3" in excluded


def test_load_context_and_mode_configs():
    """Test loading context and mode configurations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test configurations
        context_data = {
            "name": "test-context",
            "description": "Test Context",
            "tool_settings": {
                "included_tools": ["tool1", "tool2"],
                "excluded_tools": ["tool3"]
            },
            "prompt_extension": "Context prompt extension"
        }
        
        mode_data = {
            "name": "test-mode",
            "description": "Test Mode",
            "tool_settings": {
                "included_tools": ["tool4"],
                "excluded_tools": ["tool5"]
            },
            "prompt_extension": "Mode prompt extension"
        }
        
        # Write test files
        context_path = os.path.join(tmpdir, "test-context.yml")
        mode_path = os.path.join(tmpdir, "test-mode.yml")
        
        with open(context_path, "w") as f:
            yaml.dump(context_data, f)
        
        with open(mode_path, "w") as f:
            yaml.dump(mode_data, f)
        
        # Load and verify
        context = load_context_config(context_path)
        mode = load_mode_config(mode_path)
        
        assert context.name == "test-context"
        assert context.description == "Test Context"
        assert "tool1" in context.tool_settings.included_tools
        assert "tool3" in context.tool_settings.excluded_tools
        assert context.prompt_extension == "Context prompt extension"
        
        assert mode.name == "test-mode"
        assert mode.description == "Test Mode"
        assert "tool4" in mode.tool_settings.included_tools
        assert "tool5" in mode.tool_settings.excluded_tools
        assert mode.prompt_extension == "Mode prompt extension"


def test_prompt_extension():
    """Test that prompt extensions are properly used."""
    # Create context and mode configurations
    context = ContextConfig(
        name="test-context",
        description="Test Context",
        tool_settings=ToolSettings(
            included_tools=[],
            excluded_tools=[]
        ),
        prompt_extension="This is a test context."
    )
    
    modes = [
        ModeConfig(
            name="test-mode-1",
            description="Test Mode 1",
            tool_settings=ToolSettings(
                included_tools=[],
                excluded_tools=[]
            ),
            prompt_extension="This is test mode 1."
        ),
        ModeConfig(
            name="test-mode-2",
            description="Test Mode 2",
            tool_settings=ToolSettings(
                included_tools=[],
                excluded_tools=[]
            ),
            prompt_extension="This is test mode 2."
        )
    ]
    
    # Verify prompt extensions
    assert context.prompt_extension == "This is a test context."
    assert modes[0].prompt_extension == "This is test mode 1."
    assert modes[1].prompt_extension == "This is test mode 2."


def test_loading_multiple_modes():
    """Test loading multiple mode configurations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mode configurations
        modes_dir = Path(tmpdir) / "modes"
        modes_dir.mkdir()
        
        mode1_data = {
            "name": "test-mode-1",
            "description": "Test Mode 1",
            "tool_settings": {
                "included_tools": [],
                "excluded_tools": ["tool1"]
            },
            "prompt_extension": "Mode 1 prompt extension"
        }
        
        mode2_data = {
            "name": "test-mode-2",
            "description": "Test Mode 2",
            "tool_settings": {
                "included_tools": [],
                "excluded_tools": ["tool2"]
            },
            "prompt_extension": "Mode 2 prompt extension"
        }
        
        mode1_path = modes_dir / "test-mode-1.yml"
        mode2_path = modes_dir / "test-mode-2.yml"
        
        with open(mode1_path, "w") as f:
            yaml.dump(mode1_data, f)
        
        with open(mode2_path, "w") as f:
            yaml.dump(mode2_data, f)
        
        # Test loading modes directly
        mode1 = load_mode_config(str(mode1_path))
        mode2 = load_mode_config(str(mode2_path))
        
        # Verify mode1 was loaded correctly
        assert mode1.name == "test-mode-1"
        assert "tool1" in mode1.tool_settings.excluded_tools
        assert mode1.prompt_extension == "Mode 1 prompt extension"
        
        # Verify mode2 was loaded correctly
        assert mode2.name == "test-mode-2"
        assert "tool2" in mode2.tool_settings.excluded_tools
        assert mode2.prompt_extension == "Mode 2 prompt extension"
        
        # Test that multiple modes can be loaded
        modes = [mode1, mode2]
        assert len(modes) == 2
        assert modes[0].name == "test-mode-1"
        assert modes[1].name == "test-mode-2"
