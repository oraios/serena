"""
Management of context and mode configurations for Serena.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass
class ToolSettings:
    """Configuration for which tools should be included or excluded."""

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
class PromptAdjustments:
    """Configuration for prompt adjustments."""

    description: str
    instructions: list[str]
    examples: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptAdjustments":
        """Create a PromptAdjustments instance from a dictionary."""
        return cls(
            description=data.get("description", ""),
            instructions=data.get("instructions", []),
            examples=data.get("examples")
        )


@dataclass
class ContextConfig:
    """Configuration for a context."""

    name: str
    description: str
    tool_settings: ToolSettings
    prompt_adjustments: PromptAdjustments

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ContextConfig":
        """Create a ContextConfig instance from a dictionary."""
        return cls(
            name=name,
            description=data.get("description", ""),
            tool_settings=ToolSettings.from_dict(data.get("tool_settings", {})),
            prompt_adjustments=PromptAdjustments.from_dict(data.get("prompt_adjustments", {}))
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
    prompt_adjustments: PromptAdjustments

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ModeConfig":
        """Create a ModeConfig instance from a dictionary."""
        return cls(
            name=name,
            description=data.get("description", ""),
            tool_settings=ToolSettings.from_dict(data.get("tool_settings", {})),
            prompt_adjustments=PromptAdjustments.from_dict(data.get("prompt_adjustments", {}))
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


def resolve_path_or_name(name_or_path: str, base_dir: str, default_ext: str = ".yml") -> Path:
    """
    Resolve a name or path to a full path. If name_or_path is a name, look for it in base_dir.
    If it's already a path, use it directly.
    
    :param name_or_path: Name or path to resolve
    :param base_dir: Base directory to look for named files
    :param default_ext: Default extension to add if name_or_path is a name and doesn't have an extension
    :return: Resolved Path object
    """
    path = Path(name_or_path)
    
    # If it's a direct path and exists, use it
    if path.exists():
        return path
    
    # If it's likely a name, look in the base directory
    if not path.suffix:
        path = Path(base_dir) / f"{name_or_path}{default_ext}"
        if path.exists():
            return path
    
    # If it's a path but doesn't exist, still return it (the caller will handle the error)
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
    context_config: ContextConfig | None, 
    mode_configs: list[ModeConfig]
) -> tuple[set[str], set[str]]:
    """
    Resolve tool activations based on context and mode configurations.
    
    :param context_config: Context configuration (optional)
    :param mode_configs: List of mode configurations
    :return: Tuple of (included_tools, excluded_tools)
    """
    included_tools: set[str] = set()
    excluded_tools: set[str] = set()
    
    # First add context includes/excludes
    if context_config:
        included_tools.update(context_config.tool_settings.included_tools)
        excluded_tools.update(context_config.tool_settings.excluded_tools)
    
    # Now add mode includes/excludes
    mode_included: set[str] = set()
    mode_excluded: set[str] = set()
    
    for mode_config in mode_configs:
        mode_included_set = set(mode_config.tool_settings.included_tools)
        mode_excluded_set = set(mode_config.tool_settings.excluded_tools)
        
        # Check for conflicts between modes
        conflicts_include = mode_included_set & mode_excluded
        conflicts_exclude = mode_excluded_set & mode_included
        
        if conflicts_include or conflicts_exclude:
            conflict_tools = list(conflicts_include | conflicts_exclude)
            mode_names = ", ".join([mode.name for mode in mode_configs])
            raise ValueError(
                f"Conflict in tool activation between modes {mode_names}. "
                f"Conflicting tools: {', '.join(conflict_tools)}"
            )
        
        mode_included.update(mode_included_set)
        mode_excluded.update(mode_excluded_set)
    
    # If context and mode have conflicts, context takes precedence
    if context_config:
        # Remove from mode_excluded any tools that are explicitly included in context
        mode_excluded -= set(context_config.tool_settings.included_tools)
        # Remove from mode_included any tools that are explicitly excluded in context
        mode_included -= set(context_config.tool_settings.excluded_tools)
    
    # Now add mode includes/excludes
    included_tools.update(mode_included)
    excluded_tools.update(mode_excluded)
    
    # Remove any tools that are both included and excluded (should not happen, but just in case)
    common = included_tools & excluded_tools
    if common:
        log.warning(f"These tools are both included and excluded, which should not happen: {common}")
        included_tools -= common
    
    return included_tools, excluded_tools
