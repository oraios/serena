"""Project discovery and MCP configuration generation for multi-project support."""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from murena.config.murena_config import ProjectConfig, RegisteredProject

log = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server instance."""

    command: str
    args: list[str]
    env: dict[str, str]


class ProjectDiscovery:
    """Discovers Murena projects and generates MCP configurations."""

    def __init__(self, search_root: Path | None = None):
        """
        Initialize project discovery.

        :param search_root: Root directory to search for projects. Defaults to ~/Documents/projects
        """
        self.search_root = search_root or Path.home() / "Documents" / "projects"

    def is_murena_project(self, path: Path) -> bool:
        """
        Check if a directory is a Murena project.

        A directory is considered a Murena project if it contains:
        - .murena/project.yml (explicit Murena project)
        - .git + code files (potential project)
        - pyproject.toml with murena dependencies (Python project using Murena)

        :param path: Path to check
        :return: True if the path is a Murena project
        """
        if not path.is_dir():
            return False

        # Check for explicit Murena project marker
        murena_project_yml = path / ".murena" / "project.yml"
        if murena_project_yml.exists():
            log.debug(f"Found Murena project marker at {murena_project_yml}")
            return True

        # Check for git repo with code files
        git_dir = path / ".git"
        if git_dir.exists():
            # Look for common code file extensions
            code_extensions = {
                ".py",
                ".js",
                ".ts",
                ".tsx",
                ".jsx",
                ".go",
                ".java",
                ".rs",
                ".rb",
                ".php",
                ".cpp",
                ".c",
                ".h",
                ".hpp",
                ".cs",
                ".swift",
                ".kt",
            }

            # Quick scan for code files (limit to avoid deep traversal)
            for root, dirs, files in os.walk(path):
                # Skip common non-source directories
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}]

                for file in files:
                    if any(file.endswith(ext) for ext in code_extensions):
                        log.debug(f"Found git repo with code files at {path}")
                        return True

                # Only scan first level to avoid deep traversal
                break

        # Check for pyproject.toml with murena
        pyproject_toml = path / "pyproject.toml"
        if pyproject_toml.exists():
            try:
                content = pyproject_toml.read_text()
                if "murena" in content.lower() or "serena" in content.lower():
                    log.debug(f"Found pyproject.toml with murena at {path}")
                    return True
            except Exception as e:
                log.debug(f"Error reading {pyproject_toml}: {e}")

        return False

    def find_murena_projects(self) -> list[RegisteredProject]:
        """
        Scan the search root for Murena projects.

        :return: List of RegisteredProject instances for discovered projects
        """
        if not self.search_root.exists():
            log.warning(f"Search root does not exist: {self.search_root}")
            return []

        log.info(f"Searching for Murena projects in {self.search_root}")
        discovered_projects: list[RegisteredProject] = []

        for entry in self.search_root.iterdir():
            if not entry.is_dir():
                continue

            # Skip hidden directories
            if entry.name.startswith("."):
                continue

            if self.is_murena_project(entry):
                try:
                    # Try to load existing project config
                    try:
                        project_config = ProjectConfig.load(entry, autogenerate=False)
                    except FileNotFoundError:
                        # Auto-generate config if it doesn't exist
                        log.info(f"Auto-generating config for project at {entry}")
                        project_config = ProjectConfig.autogenerate(project_root=entry, save_to_disk=False, interactive=False)

                    registered_project = RegisteredProject(
                        project_root=str(entry),
                        project_config=project_config,
                    )
                    discovered_projects.append(registered_project)
                    log.info(f"Discovered project: {registered_project.project_name} at {entry}")

                except Exception as e:
                    log.warning(f"Failed to load project at {entry}: {e}")
                    continue

        log.info(f"Discovered {len(discovered_projects)} Murena project(s)")
        return discovered_projects

    def generate_mcp_config(self, project: RegisteredProject, auto_name: bool = True) -> tuple[str, MCPServerConfig]:
        """
        Generate MCP server configuration for a single project.

        :param project: The RegisteredProject to generate config for
        :param auto_name: Whether to use auto-naming (murena-{project_name})
        :return: Tuple of (server_name, MCPServerConfig)
        """
        project_root = str(project.project_root)

        # Determine server name
        if auto_name:
            # Use project directory name for MCP server name
            project_dir_name = Path(project_root).name
            server_name = f"murena-{project_dir_name}"
        else:
            server_name = "murena"

        # Generate MCP config
        config = MCPServerConfig(
            command="uvx",
            args=[
                "murena",
                "start-mcp-server",
                "--project",
                project_root,
                "--auto-name",
            ],
            env={},
        )

        log.debug(f"Generated MCP config for {server_name}: {config}")
        return server_name, config

    def generate_mcp_configs(self, projects: list[RegisteredProject] | None = None) -> dict[str, dict[str, Any]]:
        """
        Generate MCP configurations for Claude Code.

        :param projects: List of projects to generate configs for. If None, discovers projects automatically.
        :return: Dictionary mapping server names to MCP configurations
        """
        if projects is None:
            projects = self.find_murena_projects()

        configs: dict[str, dict[str, Any]] = {}

        for project in projects:
            server_name, mcp_config = self.generate_mcp_config(project, auto_name=True)

            configs[server_name] = {
                "command": mcp_config.command,
                "args": mcp_config.args,
                "env": mcp_config.env,
            }

        log.info(f"Generated MCP configs for {len(configs)} project(s)")
        return configs

    def save_mcp_configs(
        self, output_path: Path | None = None, projects: list[RegisteredProject] | None = None, merge: bool = True
    ) -> Path:
        """
        Save MCP configurations to a JSON file.

        :param output_path: Path to save configs. Defaults to ~/.claude/mcp_servers_murena.json
        :param projects: List of projects to generate configs for. If None, discovers automatically.
        :param merge: Whether to merge with existing configs (True) or overwrite (False)
        :return: Path where configs were saved
        """
        if output_path is None:
            output_path = Path.home() / ".claude" / "mcp_servers_murena.json"

        # Generate new configs
        new_configs = self.generate_mcp_configs(projects)

        # Merge with existing if requested
        if merge and output_path.exists():
            try:
                existing_configs = json.loads(output_path.read_text())
                # Update existing configs with new ones
                existing_configs.update(new_configs)
                final_configs = existing_configs
                log.info(f"Merged with existing configs at {output_path}")
            except Exception as e:
                log.warning(f"Failed to load existing configs: {e}. Will overwrite.")
                final_configs = new_configs
        else:
            final_configs = new_configs

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save configs
        output_path.write_text(json.dumps(final_configs, indent=2))
        log.info(f"Saved MCP configs to {output_path}")

        return output_path
