"""
Module for context and mode configuration.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sensai.util import logging

log = logging.getLogger(__name__)


@dataclass
class ToolSettings:
    """Configuration for tool settings."""

    included_tools: list[str]
    excluded_tools: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolSettings":
        """Create a ToolSettings instance from a dictionary."""
        return cls(
            included_tools=data.get("included_tools", []),
            excluded_tools=data.get("excluded_tools", [])
        )


@dataclass
class ContextConfig:
    """Configuration for a context."""

    name: str
    description: str
    tool_settings: ToolSettings
    prompt_extension: str

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ContextConfig":
        """Create a ContextConfig instance from a dictionary."""
        return cls(
            name=name,
            description=data.get("description", ""),
            tool_settings=ToolSettings.from_dict(data.get("tool_settings", {})),
            prompt_extension=data.get("prompt_extension", "")
        )

    @classmethod
    def from_yml(cls, path: Path) -> "ContextConfig":
        """Create a ContextConfig from a YAML file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                name = data.get("name", path.stem)
                return cls.from_dict(name, data)
        except Exception as e:
            raise ValueError(f"Error loading context configuration from {path}: {e}") from e


@dataclass
class ModeConfig:
    """Configuration for a mode."""

    name: str
    description: str
    tool_settings: ToolSettings
    prompt_extension: str

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ModeConfig":
        """Create a ModeConfig instance from a dictionary."""
        return cls(
            name=name,
            description=data.get("description", ""),
            tool_settings=ToolSettings.from_dict(data.get("tool_settings", {})),
            prompt_extension=data.get("prompt_extension", "")
        )

    @classmethod
    def from_yml(cls, path: Path) -> "ModeConfig":
        """Create a ModeConfig from a YAML file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                name = data.get("name", path.stem)
                return cls.from_dict(name, data)
        except Exception as e:
            raise ValueError(f"Error loading mode configuration from {path}: {e}") from e


def resolve_path_or_name(name_or_path: str, subdir: str) -> Path:
    """
    Resolve a name or path to a configuration file.
    
    :param name_or_path: Name of a built-in config or path to a YAML file
    :param subdir: Subdirectory for built-in configs (contexts or modes)
    :return: Path to the configuration file
    """
    path = Path(name_or_path)
    
    # If it's a direct path and exists, use it
    if path.exists() and path.is_file():
        return path
    
    # Check if it's a built-in config
    built_in_path = Path(__file__).parent / subdir / f"{name_or_path}.yml"
    if built_in_path.exists():
        return built_in_path
    
    # Try adding .yml extension
    path_with_ext = Path(f"{name_or_path}.yml")
    if path_with_ext.exists():
        return path_with_ext
    
    # Return the original path (will fail with FileNotFoundError when loaded)
    return path


def load_context_config(name_or_path: str) -> ContextConfig:
    """
    Load a context configuration from a name or path.
    
    :param name_or_path: Name of a built-in context or path to a YAML file
    :return: ContextConfig object
    """
    path = resolve_path_or_name(name_or_path, "contexts")
    if not path.exists():
        raise FileNotFoundError(f"Context configuration not found: {name_or_path}")
    
    return ContextConfig.from_yml(path)


def load_mode_config(name_or_path: str) -> ModeConfig:
    """
    Load a mode configuration from a name or path.
    
    :param name_or_path: Name of a built-in mode or path to a YAML file
    :return: ModeConfig object
    """
    path = resolve_path_or_name(name_or_path, "modes")
    if not path.exists():
        raise FileNotFoundError(f"Mode configuration not found: {name_or_path}")
    
    return ModeConfig.from_yml(path)


def resolve_tool_activations(
    context: ContextConfig | None, modes: list[ModeConfig] | None
) -> tuple[set[str], set[str]]:
    """
    Resolve tool activations from context and modes.
    
    :param context: Context configuration (optional)
    :param modes: List of mode configurations (optional)
    :return: Tuple of (included_tools, excluded_tools)
    """
    included_tools: set[str] = set()
    excluded_tools: set[str] = set()
    
    # First apply context settings (highest priority)
    if context:
        included_tools.update(context.tool_settings.included_tools)
        excluded_tools.update(context.tool_settings.excluded_tools)
    
    # Then apply mode settings
    if modes:
        mode_included: set[str] = set()
        mode_excluded: set[str] = set()
        
        for mode in modes:
            # Check for conflicts between modes
            for tool in mode.tool_settings.included_tools:
                if tool in mode_excluded:
                    raise ValueError(
                        f"Conflict in mode configurations: tool '{tool}' is both included and excluded"
                    )
            
            for tool in mode.tool_settings.excluded_tools:
                if tool in mode_included:
                    raise ValueError(
                        f"Conflict in mode configurations: tool '{tool}' is both included and excluded"
                    )
            
            mode_included.update(mode.tool_settings.included_tools)
            mode_excluded.update(mode.tool_settings.excluded_tools)
        
        # Apply mode settings, but don't override context settings
        for tool in mode_included:
            if tool not in excluded_tools:
                included_tools.add(tool)
        
        for tool in mode_excluded:
            if tool not in included_tools:
                excluded_tools.add(tool)
    
    return included_tools, excluded_tools
