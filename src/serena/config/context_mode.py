"""
Context and Mode configuration loader
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Self

import yaml
from sensai.util import logging
from sensai.util.string import ToStringMixin

from serena.config.serena_config import ToolInclusionDefinition
from serena.constants import (
    DEFAULT_CONTEXT,
    DEFAULT_MODES,
    INTERNAL_MODE_YAMLS_DIR,
    SERENA_FILE_ENCODING,
    SERENAS_OWN_CONTEXT_YAMLS_DIR,
    SERENAS_OWN_MODE_YAMLS_DIR,
    USER_CONTEXT_YAMLS_DIR,
    USER_MODE_YAMLS_DIR,
)

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
    """
    a Jinja2 template for the generation of the system prompt.
    It is formatted by the agent (see SerenaAgent._format_prompt()).
    """
    description: str = ""

    def _tostring_includes(self) -> list[str]:
        return ["name"]

    def print_overview(self) -> None:
        """Print an overview of the mode."""
        print(f"{self.name}:\n {self.description}")
        if self.excluded_tools:
            print(" excluded tools:\n  " + ", ".join(sorted(self.excluded_tools)))

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> Self:
        """Load a mode from a YAML file."""
        with open(yaml_path, encoding=SERENA_FILE_ENCODING) as f:
            data = yaml.safe_load(f)
        name = data.pop("name", Path(yaml_path).stem)
        return cls(name=name, **data)

    @classmethod
    def get_path(cls, name: str) -> str:
        """Get the path to the YAML file for a mode."""
        fname = f"{name}.yml"
        custom_mode_path = os.path.join(USER_MODE_YAMLS_DIR, fname)
        if os.path.exists(custom_mode_path):
            return custom_mode_path

        own_yaml_path = os.path.join(SERENAS_OWN_MODE_YAMLS_DIR, fname)
        if not os.path.exists(own_yaml_path):
            raise FileNotFoundError(
                f"Mode {name} not found in {USER_MODE_YAMLS_DIR} or in {SERENAS_OWN_MODE_YAMLS_DIR}."
                f"Available modes:\n{cls.list_registered_mode_names()}"
            )
        return own_yaml_path

    @classmethod
    def from_name(cls, name: str) -> Self:
        """Load a registered Serena mode."""
        mode_path = cls.get_path(name)
        return cls.from_yaml(mode_path)

    @classmethod
    def from_name_internal(cls, name: str) -> Self:
        """Loads an internal Serena mode"""
        yaml_path = os.path.join(INTERNAL_MODE_YAMLS_DIR, f"{name}.yml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Internal mode '{name}' not found in {INTERNAL_MODE_YAMLS_DIR}")
        return cls.from_yaml(yaml_path)

    @classmethod
    def list_registered_mode_names(cls, include_user_modes: bool = True) -> list[str]:
        """Names of all registered modes (from the corresponding YAML files in the serena repo)."""
        modes = [f.stem for f in Path(SERENAS_OWN_MODE_YAMLS_DIR).glob("*.yml") if f.name != "mode.template.yml"]
        if include_user_modes:
            modes += cls.list_custom_mode_names()
        return sorted(set(modes))

    @classmethod
    def list_custom_mode_names(cls) -> list[str]:
        """Names of all custom modes defined by the user."""
        return [f.stem for f in Path(USER_MODE_YAMLS_DIR).glob("*.yml")]

    @classmethod
    def load_default_modes(cls) -> list[Self]:
        """Load the default modes (interactive and editing)."""
        return [cls.from_name(mode) for mode in DEFAULT_MODES]

    @classmethod
    def load(cls, name_or_path: str | Path) -> Self:
        if str(name_or_path).endswith(".yml"):
            return cls.from_yaml(name_or_path)
        return cls.from_name(str(name_or_path))


@dataclass(kw_only=True)
class SerenaAgentContext(ToolInclusionDefinition, ToStringMixin):
    """Represents a context where the agent is operating (an IDE, a chat, etc.), typically read off a YAML file.
    An agent can only be in a single context at a time.
    The contexts cannot be changed after the agent is running.
    """

    name: str
    """the name of the context"""

    prompt: str
    """
    a Jinja2 template for the generation of the system prompt.
    It is formatted by the agent (see SerenaAgent._format_prompt()).
    """

    description: str = ""

    tool_description_overrides: dict[str, str] = field(default_factory=dict)
    """
    maps tool names to custom descriptions, default descriptions are extracted from the tool docstrings.
    """

    single_project: bool = False
    """
    whether to assume that Serena shall only work on a single project in this context (provided that a project is given
    when Serena is started).
    If set to true and a project is provided at startup, the set of tools is limited to those required by the project's
    concrete configuration, and other tools are excluded completely, allowing the set of tools to be minimal.
    The `activate_project` tool will, therefore, be disabled in this case, as project switching is not allowed.
    """

    def _tostring_includes(self) -> list[str]:
        return ["name"]

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> Self:
        """Load a context from a YAML file."""
        with open(yaml_path, encoding=SERENA_FILE_ENCODING) as f:
            data = yaml.safe_load(f)
        name = data.pop("name", Path(yaml_path).stem)
        # Ensure backwards compatibility for tool_description_overrides
        if "tool_description_overrides" not in data:
            data["tool_description_overrides"] = {}
        return cls(name=name, **data)

    @classmethod
    def get_path(cls, name: str) -> str:
        """Get the path to the YAML file for a context."""
        fname = f"{name}.yml"
        custom_context_path = os.path.join(USER_CONTEXT_YAMLS_DIR, fname)
        if os.path.exists(custom_context_path):
            return custom_context_path

        own_yaml_path = os.path.join(SERENAS_OWN_CONTEXT_YAMLS_DIR, fname)
        if not os.path.exists(own_yaml_path):
            raise FileNotFoundError(
                f"Context {name} not found in {USER_CONTEXT_YAMLS_DIR} or in {SERENAS_OWN_CONTEXT_YAMLS_DIR}."
                f"Available contexts:\n{cls.list_registered_context_names()}"
            )
        return own_yaml_path

    @classmethod
    def from_name(cls, name: str) -> Self:
        """Load a registered Serena context."""
        context_path = cls.get_path(name)
        return cls.from_yaml(context_path)

    @classmethod
    def load(cls, name_or_path: str | Path) -> Self:
        if str(name_or_path).endswith(".yml"):
            return cls.from_yaml(name_or_path)
        return cls.from_name(str(name_or_path))

    @classmethod
    def list_registered_context_names(cls, include_user_contexts: bool = True) -> list[str]:
        """Names of all registered contexts (from the corresponding YAML files in the serena repo)."""
        contexts = [f.stem for f in Path(SERENAS_OWN_CONTEXT_YAMLS_DIR).glob("*.yml")]
        if include_user_contexts:
            contexts += cls.list_custom_context_names()
        return sorted(set(contexts))

    @classmethod
    def list_custom_context_names(cls) -> list[str]:
        """Names of all custom contexts defined by the user."""
        return [f.stem for f in Path(USER_CONTEXT_YAMLS_DIR).glob("*.yml")]

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
