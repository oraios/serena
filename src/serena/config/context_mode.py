"""
Context and Mode configuration loader
"""

import os
from copy import copy
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Self

import yaml
from sensai.util import logging
from sensai.util.string import ToStringMixin

from serena.config.serena_config import ToolInclusionDefinition
from serena.constants import CONTEXT_YAMLS_DIR, DEFAULT_CONTEXT, DEFAULT_MODES, INTERNAL_MODE_YAMLS_DIR, MODE_YAMLS_DIR

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


@dataclass(kw_only=True)
class SerenaAgentMode(ToolInclusionDefinition, ToStringMixin):
    """Represents a mode of operation for the agent, typically read off a YAML file.
    An agent can be in multiple modes simultaneously as long as they are not mutually exclusive.
    The modes can be adjusted after the agent is running, for example for switching from planning to editing.
    """

    name: str
    prompt: str
    description: str = ""

    def _tostring_includes(self) -> list[str]:
        return ["name"]

    def to_json_dict(self) -> dict[str, str | list[str]]:
        result = asdict(self)
        result["excluded_tools"] = list(result["excluded_tools"])
        return result

    @classmethod
    def from_json_dict(cls, data: dict) -> Self:
        data = copy(data)
        data["excluded_tools"] = set(data["excluded_tools"])
        return cls(**data)

    def print_overview(self) -> None:
        """Print an overview of the mode."""
        print(f"{self.name}:\n {self.description}")
        if self.excluded_tools:
            print(" excluded tools:\n  " + ", ".join(sorted(self.excluded_tools)))

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> Self:
        """Load a mode from a YAML file."""
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        name = data.pop("name", Path(yaml_path).stem)
        return cls(name=name, **data)

    @classmethod
    def from_name(cls, name: str) -> Self:
        """Load a registered Serena mode."""
        yaml_path = os.path.join(MODE_YAMLS_DIR, f"{name}.yml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(
                f"Mode {name} not found in {MODE_YAMLS_DIR}. You can load custom modes by using from_yaml() instead. "
                f"Available modes: {cls.list_registered_mode_names()}"
            )
        return cls.from_yaml(yaml_path)

    @classmethod
    def from_name_internal(cls, name: str) -> Self:
        """Loads an internal Serena mode"""
        yaml_path = os.path.join(INTERNAL_MODE_YAMLS_DIR, f"{name}.yml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Internal mode '{name}' not found in {INTERNAL_MODE_YAMLS_DIR}")
        return cls.from_yaml(yaml_path)

    @classmethod
    def list_registered_mode_names(cls) -> list[str]:
        """Names of all registered modes (from the corresponding YAML files in the serena repo)."""
        return sorted([f.stem for f in Path(MODE_YAMLS_DIR).glob("*.yml")])

    @classmethod
    def load_default_modes(cls) -> list[Self]:
        """Load the default modes (interactive and editing)."""
        return [cls.from_name(mode) for mode in DEFAULT_MODES]

    @classmethod
    def load(cls, name_or_path: str | Path) -> Self:
        try:
            return cls.from_name(str(name_or_path))
        except FileNotFoundError:
            return cls.from_yaml(name_or_path)


@dataclass(kw_only=True)
class SerenaAgentContext(ToolInclusionDefinition, ToStringMixin):
    """Represents a context where the agent is operating (an IDE, a chat, etc.), typically read off a YAML file.
    An agent can only be in a single context at a time.
    The contexts cannot be changed after the agent is running.
    """

    name: str
    prompt: str
    description: str = ""

    def _tostring_includes(self) -> list[str]:
        return ["name"]

    def to_json_dict(self) -> dict[str, str | list[str]]:
        result = asdict(self)
        result["excluded_tools"] = list(result["excluded_tools"])
        return result

    @classmethod
    def from_json_dict(cls, data: dict) -> Self:
        data = copy(data)
        data["excluded_tools"] = set(data["excluded_tools"])
        return cls(**data)

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> Self:
        """Load a context from a YAML file."""
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        name = data.pop("name", Path(yaml_path).stem)
        return cls(name=name, **data)

    @classmethod
    def from_name(cls, name: str) -> Self:
        """Load a registered Serena context."""
        yaml_path = os.path.join(CONTEXT_YAMLS_DIR, f"{name}.yml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(
                f"Context {Path(yaml_path).stem} not found in {CONTEXT_YAMLS_DIR}. You can load a custom context by using from_yaml() instead.\n"
                f"Available contexts:\n{cls.list_registered_context_names()}"
            )
        return cls.from_yaml(yaml_path)

    @classmethod
    def load(cls, name_or_path: str | Path) -> Self:
        try:
            return cls.from_name(str(name_or_path))
        except FileNotFoundError:
            try:
                return cls.from_yaml(name_or_path)
            except FileNotFoundError as e:
                raise FileNotFoundError(
                    f"Context {name_or_path} not found in {CONTEXT_YAMLS_DIR}. You can load a custom context by using from_yaml() instead.\n"
                    f"Available contexts:\n{cls.list_registered_context_names()}"
                ) from e

    @classmethod
    def list_registered_context_names(cls) -> list[str]:
        """Names of all registered contexts (from the corresponding YAML files in the serena repo)."""
        return sorted([f.stem for f in Path(CONTEXT_YAMLS_DIR).glob("*.yml")])

    @classmethod
    def load_default(cls) -> Self:
        """Load the default context."""
        return cls.from_name(DEFAULT_CONTEXT)

    def print_overview(self) -> None:
        """Print an overview of the mode."""
        print(f"{self.name}:\n {self.description}")
        if self.excluded_tools:
            print(" excluded tools:\n  " + ", ".join(sorted(self.excluded_tools)))


class RegisteredContext(Enum):
    """A registered context."""

    IDE_ASSISTANT = "ide-assistant"
    """For Serena running within an assistant that already has basic tools, like Claude Code, Cline, Cursor, etc."""
    DESKTOP_APP = "desktop-app"
    """For Serena running within Claude Desktop or a similar app which does not have built-in tools for code editing."""
    AGENT = "agent"
    """For Serena running as a standalone agent, e.g. through agno."""

    def load(self) -> SerenaAgentContext:
        """Load the context."""
        return SerenaAgentContext.from_name(self.value)


class RegisteredMode(Enum):
    """A registered mode."""

    INTERACTIVE = "interactive"
    """Interactive mode, for multi-turn interactions."""
    EDITING = "editing"
    """Editing tools are activated."""
    PLANNING = "planning"
    """Editing tools are deactivated."""
    ONE_SHOT = "one-shot"
    """Non-interactive mode, where the goal is to finish a task autonomously."""

    def load(self) -> SerenaAgentMode:
        """Load the mode."""
        return SerenaAgentMode.from_name(self.value)
