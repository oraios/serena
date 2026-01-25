"""Claude Code MCP configuration management."""

import json
import logging
from pathlib import Path
from typing import Any

from murena.config.murena_config import RegisteredProject

log = logging.getLogger(__name__)


class ClaudeCodeConfigManager:
    """Manages MCP server configurations for Claude Code integration."""

    def __init__(self, config_path: Path | None = None):
        """
        Initialize the configuration manager.

        :param config_path: Path to .claude directory. Defaults to ~/.claude
        """
        self.config_dir = config_path or Path.home() / ".claude"
        self.mcp_config_path = self.config_dir / "mcp_servers_murena.json"

    def _load_configs(self) -> dict[str, Any]:
        """Load existing MCP configurations."""
        if not self.mcp_config_path.exists():
            return {}

        try:
            return json.loads(self.mcp_config_path.read_text())
        except Exception as e:
            log.warning(f"Failed to load existing configs from {self.mcp_config_path}: {e}")
            return {}

    def _save_configs(self, configs: dict[str, Any]) -> None:
        """Save MCP configurations to file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_config_path.write_text(json.dumps(configs, indent=2))
        log.info(f"Saved MCP configs to {self.mcp_config_path}")

    def _get_server_name(self, project: RegisteredProject) -> str:
        """
        Generate MCP server name for a project.

        :param project: The RegisteredProject
        :return: Server name (e.g., 'murena-serena')
        """
        project_dir_name = Path(project.project_root).name
        return f"murena-{project_dir_name}"

    def add_project_server(self, project: RegisteredProject) -> str:
        """
        Add MCP server configuration for a project.

        :param project: The RegisteredProject to add
        :return: The server name that was added
        """
        server_name = self._get_server_name(project)
        configs = self._load_configs()

        # Determine Murena installation path (parent of src directory)
        murena_root = Path(__file__).resolve().parent.parent.parent.parent

        server_config = {
            "command": "uv",
            "args": [
                "run",
                "--project",
                str(murena_root),
                "murena",
                "start-mcp-server",
                "--project",
                str(project.project_root),
                "--context",
                "claude-code",
            ],
            "env": {},
        }

        configs[server_name] = server_config
        self._save_configs(configs)

        log.info(f"Added MCP server config for project: {project.project_name} ({server_name})")
        return server_name

    def remove_project_server(self, project_name: str) -> bool:
        """
        Remove MCP server configuration by project name.

        :param project_name: Name of the project (directory name)
        :return: True if removed, False if not found
        """
        configs = self._load_configs()
        server_name = f"murena-{project_name}"

        if server_name in configs:
            del configs[server_name]
            self._save_configs(configs)
            log.info(f"Removed MCP server config: {server_name}")
            return True
        else:
            log.warning(f"MCP server config not found: {server_name}")
            return False

    def list_configured_projects(self) -> list[str]:
        """
        List all configured project server names.

        :return: List of server names (e.g., ['murena-serena', 'murena-spec-kit'])
        """
        configs = self._load_configs()
        # Filter only murena-prefixed servers
        return [name for name in configs.keys() if name.startswith("murena-")]

    def get_project_config(self, project_name: str) -> dict[str, Any] | None:
        """
        Get MCP configuration for a specific project.

        :param project_name: Name of the project (directory name)
        :return: Configuration dict or None if not found
        """
        configs = self._load_configs()
        server_name = f"murena-{project_name}"
        return configs.get(server_name)

    def sync_with_discovered_projects(
        self,
        discovered_projects: list[RegisteredProject],
        remove_stale: bool = False,
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Synchronize MCP configs with discovered projects.

        :param discovered_projects: List of RegisteredProject instances
        :param remove_stale: Whether to remove configs for non-existent projects
        :return: Tuple of (added, updated, removed) server names
        """
        configs = self._load_configs()
        existing_servers = set(self.list_configured_projects())

        # Build set of expected server names
        expected_servers = {self._get_server_name(p) for p in discovered_projects}

        # Determine Murena installation path (parent of src directory)
        murena_root = Path(__file__).resolve().parent.parent.parent.parent

        added = []
        updated = []
        removed = []

        # Add or update projects
        for project in discovered_projects:
            server_name = self._get_server_name(project)

            new_config = {
                "command": "uv",
                "args": [
                    "run",
                    "--project",
                    str(murena_root),
                    "murena",
                    "start-mcp-server",
                    "--project",
                    str(project.project_root),
                    "--context",
                    "claude-code",
                ],
                "env": {},
            }

            if server_name in configs:
                # Check if config needs update
                if configs[server_name] != new_config:
                    configs[server_name] = new_config
                    updated.append(server_name)
                    log.info(f"Updated MCP config for: {server_name}")
            else:
                # Add new config
                configs[server_name] = new_config
                added.append(server_name)
                log.info(f"Added MCP config for: {server_name}")

        # Remove stale configs if requested
        if remove_stale:
            stale_servers = existing_servers - expected_servers
            for server_name in stale_servers:
                if server_name in configs:
                    del configs[server_name]
                    removed.append(server_name)
                    log.info(f"Removed stale MCP config: {server_name}")

        # Save updated configs
        if added or updated or removed:
            self._save_configs(configs)

        return added, updated, removed

    def merge_with_existing(self, new_configs: dict[str, Any]) -> dict[str, Any]:
        """
        Merge new configurations with existing ones.

        :param new_configs: New configurations to merge
        :return: Merged configurations
        """
        existing = self._load_configs()
        existing.update(new_configs)
        return existing
