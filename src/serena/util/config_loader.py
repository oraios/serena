"""
Context and Mode configuration loader
"""

import os
import pathlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sensai.util import logging

log = logging.getLogger(__name__)


@dataclass
class ConfigData:
    """Base class for context and mode configurations."""

    name: str
    description: str
    system_prompt_extension: str
    excluded_tools: set[str]
    tool_description_overrides: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigData":
        """Create a ConfigData instance from a dictionary."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            system_prompt_extension=data.get("system_prompt_extension", ""),
            excluded_tools=set(data.get("excluded_tools", [])),
            tool_description_overrides=data.get("tool_description_overrides", {}),
        )


class ConfigLoader:
    """Handles loading of context and mode configurations."""

    def __init__(self) -> None:
        """Initialize the config loader."""
        self.serena_root = self._find_serena_root()
        self.contexts_dir = os.path.join(self.serena_root, "prompts", "contexts")
        self.modes_dir = os.path.join(self.serena_root, "prompts", "modes")

        # Ensure directories exist
        os.makedirs(self.contexts_dir, exist_ok=True)
        os.makedirs(self.modes_dir, exist_ok=True)

        # Cache loaded configs
        self.context_cache: dict[str, ConfigData] = {}
        self.mode_cache: dict[str, ConfigData] = {}

    def _find_serena_root(self) -> str:
        """Find the root directory of Serena."""
        current_dir = pathlib.Path(__file__).parent.parent.parent.parent
        return str(current_dir)

    def load_config_from_file(self, file_path: str | Path) -> ConfigData:
        """Load a configuration from a file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return ConfigData.from_dict(data)

    def get_context(self, context_name_or_path: str) -> ConfigData:
        """
        Get the context configuration by name or path.

        :param context_name_or_path: Either a context name (will be looked up in contexts directory)
                                     or a path to a YAML file
        :return: The context configuration
        """
        # Return from cache if available
        if context_name_or_path in self.context_cache:
            return self.context_cache[context_name_or_path]

        # Check if it's a file path
        if os.path.isfile(context_name_or_path):
            config = self.load_config_from_file(context_name_or_path)
            self.context_cache[context_name_or_path] = config
            return config

        # Check if it's a known context name
        context_file = os.path.join(self.contexts_dir, f"{context_name_or_path}.yml")
        if os.path.isfile(context_file):
            config = self.load_config_from_file(context_file)
            self.context_cache[context_name_or_path] = config
            return config

        raise ValueError(f"Context not found: {context_name_or_path}. Please provide a valid context name or file path.")

    def get_mode(self, mode_name_or_path: str) -> ConfigData:
        """
        Get the mode configuration by name or path.

        :param mode_name_or_path: Either a mode name (will be looked up in modes directory)
                                  or a path to a YAML file
        :return: The mode configuration
        """
        # Return from cache if available
        if mode_name_or_path in self.mode_cache:
            return self.mode_cache[mode_name_or_path]

        # Check if it's a file path
        if os.path.isfile(mode_name_or_path):
            config = self.load_config_from_file(mode_name_or_path)
            self.mode_cache[mode_name_or_path] = config
            return config

        # Check if it's a known mode name
        mode_file = os.path.join(self.modes_dir, f"{mode_name_or_path}.yml")
        if os.path.isfile(mode_file):
            config = self.load_config_from_file(mode_file)
            self.mode_cache[mode_name_or_path] = config
            return config

        raise ValueError(f"Mode not found: {mode_name_or_path}. Please provide a valid mode name or file path.")

    def list_available_contexts(self) -> list[str]:
        """List all available context names."""
        return [f.stem for f in Path(self.contexts_dir).glob("*.yml")]

    def list_available_modes(self) -> list[str]:
        """List all available mode names."""
        return [f.stem for f in Path(self.modes_dir).glob("*.yml")]
