"""
Context and Mode configuration loader
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Self

import yaml
from sensai.util import logging

from serena.constants import CONTEXT_YAMLS_DIR, DEFAULT_CONTEXT, DEFAULT_MODES, MODE_YAMLS_DIR

if TYPE_CHECKING:
    from serena.agent import Tool

log = logging.getLogger(__name__)


@dataclass
class SerenaAgentMode:
    """Represents a mode of operation for the agent, typically read off a YAML file.
    An agent can be in multiple modes simultaneously as long as they are not mutually exclusive.
    The modes can be adjusted after the agent is running, for example for switching from planning to editing.
    """

    name: str
    prompt: str
    description: str = ""
    excluded_tools: set[str] = field(default_factory=set)

    def print_overview(self) -> None:
        """Print an overview of the mode."""
        print(f"{self.name}:\n {self.description}")
        if self.excluded_tools:
            print(" excluded tools:\n  " + ", ".join(sorted(self.excluded_tools)))

    def get_excluded_tool_classes(self) -> list[type["Tool"]]:
        """Get the list of tool classes that are excluded from the mode."""
        from serena.agent import ToolRegistry

        return [ToolRegistry.get_tool_class_by_name(tool_name) for tool_name in self.excluded_tools]

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


@dataclass
class SerenaAgentContext:
    """Represents a context where the agent is operating (an IDE, a chat, etc.), typically read off a YAML file.
    An agent can only be in a single context at a time.
    The contexts cannot be changed after the agent is running.
    """

    name: str
    prompt: str
    description: str = ""
    excluded_tools: set[str] = field(default_factory=set)

    def get_excluded_tool_classes(self) -> list[type["Tool"]]:
        """Get the list of tool classes that are excluded from the context."""
        from serena.agent import ToolRegistry

        return [ToolRegistry.get_tool_class_by_name(tool_name) for tool_name in self.excluded_tools]

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


def init_user_config():
    """
    Initialize user configuration by copying config files from package to user data directory.

    This function:
    1. Creates user config directories if they don't exist
    2. Copies config files from package to user data directory if they don't exist
    3. Handles version-based migration with backup and logging
    4. Copies serena_config.template.yml to serena_config.yml in user data directory

    Raises:
        Exception: If copying fails due to permissions or other IO issues

    """
    from pathlib import Path

    from serena.constants import SERENA_CONFIG_TEMPLATE_FILE, _serena_data_path, _serena_pkg_path

    # Define current config version - increment when config format changes
    CONFIG_VERSION = "1.0"

    user_data_path = Path(_serena_data_path)
    pkg_config_path = Path(_serena_pkg_path) / "resources" / "config"
    user_config_path = user_data_path / "config"

    log.info(f"Initializing user configuration in {user_data_path}")

    try:
        # Create user data directory structure
        user_data_path.mkdir(parents=True, exist_ok=True)
        user_config_path.mkdir(parents=True, exist_ok=True)

        # Create config subdirectories
        config_dirs = ["prompt_templates", "contexts", "modes"]
        for config_dir in config_dirs:
            (user_config_path / config_dir).mkdir(parents=True, exist_ok=True)

        # Define source and destination paths for each config directory
        config_mappings = [
            ("prompt_templates", pkg_config_path / "prompt_templates", user_config_path / "prompt_templates"),
            ("contexts", pkg_config_path / "contexts", user_config_path / "contexts"),
            ("modes", pkg_config_path / "modes", user_config_path / "modes"),
        ]

        # Handle main config file separately
        user_config_file = user_data_path / "serena_config.yml"
        template_config_file = Path(SERENA_CONFIG_TEMPLATE_FILE)

        # Check if we need to copy/migrate config files
        for config_name, src_dir, dest_dir in config_mappings:
            _copy_or_migrate_config_dir(config_name, src_dir, dest_dir, CONFIG_VERSION)

        # Handle main config file (template -> config)
        _copy_or_migrate_main_config(template_config_file, user_config_file, CONFIG_VERSION)

        log.info("User configuration initialization completed successfully")

    except Exception as e:
        log.error(f"Failed to initialize user configuration: {e}")
        raise Exception(f"Critical error during config initialization: {e}") from e


def _copy_or_migrate_config_dir(config_name: str, src_dir: Path, dest_dir: Path, current_version: str):
    """Copy or migrate a configuration directory."""
    import shutil

    version_file = dest_dir / ".version"
    needs_copy = False
    needs_migration = False

    if not dest_dir.exists() or not any(dest_dir.iterdir()):
        log.info(f"Config directory {config_name} doesn't exist in user data, copying from package")
        needs_copy = True
    elif version_file.exists():
        try:
            existing_version = version_file.read_text().strip()
            if existing_version != current_version:
                log.warning(f"Config {config_name} version mismatch: existing={existing_version}, current={current_version}")
                needs_migration = True
        except Exception as e:
            log.warning(f"Could not read version file for {config_name}: {e}, treating as migration needed")
            needs_migration = True
    else:
        log.warning(f"No version file found for {config_name}, treating as migration needed")
        needs_migration = True

    if needs_copy or needs_migration:
        if needs_migration:
            _backup_existing_config(dest_dir, config_name)

        # Copy files from source to destination
        log.info(f"Copying {config_name} config files from {src_dir} to {dest_dir}")

        # Remove existing files if migrating
        if needs_migration and dest_dir.exists():
            shutil.rmtree(dest_dir)

        # Copy the directory
        shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)

        # Write version file
        version_file.write_text(current_version)
        log.info(f"Successfully copied {config_name} config files")


def _copy_or_migrate_main_config(template_file: Path, user_config_file: Path, current_version: str):
    """Copy or migrate the main serena_config.yml file."""
    import shutil

    needs_copy = False
    needs_migration = False

    if not user_config_file.exists():
        log.info("Main config file doesn't exist in user data, copying from template")
        needs_copy = True
    else:
        # Check version in existing config file
        try:
            import yaml

            with open(user_config_file) as f:
                config_data = yaml.safe_load(f) or {}

            existing_version = config_data.get("config_version")
            if existing_version != current_version:
                log.warning(f"Main config version mismatch: existing={existing_version}, current={current_version}")
                needs_migration = True
        except Exception as e:
            log.warning(f"Could not read version from main config: {e}, treating as migration needed")
            needs_migration = True

    if needs_copy or needs_migration:
        if needs_migration:
            _backup_existing_config(user_config_file.parent, "serena_config", user_config_file.name)

        log.info(f"Copying main config from {template_file} to {user_config_file}")
        shutil.copy2(template_file, user_config_file)

        # Add version to the config file
        try:
            import yaml

            with open(user_config_file) as f:
                config_data = yaml.safe_load(f) or {}

            config_data["config_version"] = current_version

            with open(user_config_file, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            log.info("Successfully copied and versioned main config file")
        except Exception as e:
            log.error(f"Failed to add version to config file: {e}")
            # Don't fail completely, the file was copied successfully


def _backup_existing_config(config_path: Path, config_name: str, filename: str | None = None):
    """Create a backup of existing configuration before migration."""
    import datetime
    import shutil

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if filename:
        # Backing up a single file
        backup_name = f"{filename}.backup_{timestamp}"
        backup_path = config_path / backup_name
        source_path = config_path / filename

        if source_path.exists():
            shutil.copy2(source_path, backup_path)
            log.info(f"Created backup of {config_name} at {backup_path}")
    else:
        # Backing up a directory
        backup_name = f"{config_name}_backup_{timestamp}"
        backup_path = config_path.parent / backup_name

        if config_path.exists():
            shutil.copytree(config_path, backup_path)
            log.info(f"Created backup of {config_name} directory at {backup_path}")
