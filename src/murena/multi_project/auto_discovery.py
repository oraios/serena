"""Automatic project discovery and registration for Claude Code MCP.

Automatically discovers Murena projects in workspace directories and
registers them in the MCP configuration.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, TypedDict

from murena.multi_project.project_discovery import ProjectDiscovery

log = logging.getLogger(__name__)


class RegistrationResult(TypedDict):
    """Result of project registration."""

    total: int
    registered: int
    updated: int
    failed: int
    projects: list[dict[str, Any]]


class DiscoveryResult(TypedDict):
    """Result of discovery and registration pipeline."""

    success: bool
    message: str
    projects_found: int
    registered: int
    failed: int
    projects: list[dict[str, Any]]


class AutoDiscoveryManager:
    """Manages automatic discovery and registration of Murena projects."""

    def __init__(self, workspace_root: Optional[Path] = None):
        """Initialize auto-discovery manager.

        Args:
            workspace_root: Root directory to search for projects (defaults to cwd)

        """
        self.workspace_root = Path(workspace_root or os.getcwd())
        self.discovery = ProjectDiscovery()

    def discover_projects(self, max_depth: int = 3) -> list[dict]:
        """Discover all Murena projects in workspace.

        Searches for .murena/project.yml files up to specified depth.

        Args:
            max_depth: Maximum directory depth to search

        Returns:
            List of discovered projects with metadata

        """
        projects = []

        try:
            for root, dirs, files in os.walk(self.workspace_root):
                # Calculate depth
                depth = root[len(str(self.workspace_root)) :].count(os.sep)
                if depth > max_depth:
                    dirs[:] = []  # Don't descend further
                    continue

                # Skip common non-project directories
                dirs_to_skip = {"node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", ".git"}
                dirs[:] = [d for d in dirs if d not in dirs_to_skip]

                # Check for Murena project marker
                if ".murena" in dirs:
                    project_file = Path(root) / ".murena" / "project.yml"
                    if project_file.exists():
                        project_data = {
                            "name": Path(root).name,
                            "path": str(root),
                            "marker_file": str(project_file),
                        }
                        projects.append(project_data)
                        log.info(f"Discovered project: {project_data['name']} at {root}")

        except Exception as e:
            log.error(f"Error during project discovery: {e}")

        return projects

    def get_mcp_config_path(self) -> Path:
        """Get path to MCP servers configuration file.

        Returns:
            Path to ~/.claude/mcp_servers_murena.json

        """
        config_dir = Path.home() / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "mcp_servers_murena.json"

    def load_mcp_config(self) -> dict:
        """Load existing MCP configuration.

        Returns:
            Dictionary of MCP server configurations

        """
        config_path = self.get_mcp_config_path()

        if not config_path.exists():
            return {}

        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load MCP config: {e}")
            return {}

    def save_mcp_config(self, config: dict) -> bool:
        """Save MCP configuration to file.

        Args:
            config: Configuration dictionary

        Returns:
            True if successful

        """
        config_path = self.get_mcp_config_path()

        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            log.info(f"Saved MCP config to {config_path}")
            return True
        except Exception as e:
            log.error(f"Failed to save MCP config: {e}")
            return False

    def register_project(self, project_name: str, project_path: str) -> bool:
        """Register a project in MCP configuration.

        Args:
            project_name: Name of the project
            project_path: Path to the project

        Returns:
            True if successfully registered

        """
        config = self.load_mcp_config()

        # Generate server name
        server_name = f"murena-{project_name}"

        # Create MCP server configuration
        server_config = {
            "command": "uvx",
            "args": ["murena", "start-mcp-server", "--project", project_path, "--auto-name"],
            "env": {},
        }

        # Check if already exists
        if server_name in config:
            if config[server_name]["args"][3] == project_path:
                log.info(f"Project {project_name} already registered")
                return True
            else:
                log.info(f"Updating registration for {project_name}")

        config[server_name] = server_config
        return self.save_mcp_config(config)

    def auto_register_projects(self, projects: list[dict]) -> RegistrationResult:
        """Automatically register discovered projects.

        Args:
            projects: List of discovered projects

        Returns:
            Dictionary with registration results

        """
        results: RegistrationResult = {
            "total": len(projects),
            "registered": 0,
            "updated": 0,
            "failed": 0,
            "projects": [],
        }

        for project in projects:
            try:
                if self.register_project(project["name"], project["path"]):
                    results["registered"] += 1
                    results["projects"].append(
                        {
                            "name": project["name"],
                            "status": "registered",
                        }
                    )
                    log.info(f"✅ Registered {project['name']}")
                else:
                    results["failed"] += 1
                    results["projects"].append(
                        {
                            "name": project["name"],
                            "status": "failed",
                        }
                    )
                    log.error(f"❌ Failed to register {project['name']}")
            except Exception as e:
                results["failed"] += 1
                results["projects"].append(
                    {
                        "name": project["name"],
                        "status": "error",
                        "error": str(e),
                    }
                )
                log.error(f"Error registering {project['name']}: {e}")

        return results

    def run_discovery(self, workspace_root: Optional[Path] = None, max_depth: int = 3) -> DiscoveryResult:
        """Run complete discovery and registration pipeline.

        Args:
            workspace_root: Root directory to search
            max_depth: Maximum depth to search

        Returns:
            Dictionary with discovery and registration results

        """
        if workspace_root:
            self.workspace_root = Path(workspace_root)

        log.info(f"Starting auto-discovery in {self.workspace_root}")

        # Discover projects
        projects = self.discover_projects(max_depth=max_depth)
        log.info(f"Found {len(projects)} projects")

        if not projects:
            return {
                "success": True,
                "message": "No projects found",
                "projects_found": 0,
                "registered": 0,
                "failed": 0,
                "projects": [],
            }

        # Register projects
        results = self.auto_register_projects(projects)

        return {
            "success": results["failed"] == 0,
            "message": f"Registered {results['registered']}/{results['total']} projects",
            "projects_found": results["total"],
            "registered": results["registered"],
            "failed": results["failed"],
            "projects": results["projects"],
        }


class QuickDiscoveryMode:
    """Quick discovery mode for Claude Code startup."""

    @staticmethod
    def quick_scan(workspace_root: Optional[Path] = None) -> bool:
        """Quick scan and register projects on Claude Code startup.

        Args:
            workspace_root: Root directory to scan

        Returns:
            True if successful

        """
        try:
            manager = AutoDiscoveryManager(workspace_root)
            result = manager.run_discovery(max_depth=2)

            if result["success"]:
                log.info(f"✅ Auto-discovery complete: {result['message']}")
                return True
            else:
                log.warning(f"⚠️ Auto-discovery partially failed: {result['message']}")
                return False

        except Exception as e:
            log.error(f"Auto-discovery failed: {e}")
            return False

    @staticmethod
    def is_workspace_root(path: Path) -> bool:
        """Check if path looks like a workspace root.

        Returns:
            True if path likely contains projects

        """
        # Check for common project indicators
        indicators = [".git", ".vscode", "pyproject.toml", "package.json"]

        for indicator in indicators:
            if (path / indicator).exists():
                return True

        return False
