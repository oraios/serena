"""Lazy initialization of Murena projects on first tool call.

This module provides automatic project configuration generation when Claude Code
works in a directory without .murena/project.yml. It uses background initialization
to avoid blocking MCP server startup while providing seamless onboarding.

Key features:
- Triggers on first tool call, not at startup
- Non-interactive mode (no TTY prompts)
- Thread-safe with lock-protected initialization
- Graceful error handling with helpful messages
- Transparent to user experience
"""

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from murena.agent import MurenaAgent
    from murena.project import Project

log = logging.getLogger(__name__)


class LazyProjectInitializer:
    """Handles lazy initialization of Murena projects on first tool call.

    Instead of blocking MCP server startup with language detection, this class
    performs initialization in response to the first tool call. This provides:

    - Fast MCP server startup (<500ms, no regression)
    - Seamless onboarding (no user interaction required)
    - Thread-safe concurrent execution
    - Graceful error handling for edge cases

    Initialization happens exactly once due to idempotent locking mechanism.
    """

    def __init__(self, agent: "MurenaAgent"):
        """Initialize lazy initialization manager.

        Args:
            agent: The MurenaAgent instance managing this project

        """
        self._agent = agent
        self._initialization_attempted = False
        self._initialization_lock = threading.Lock()
        self._project_root: str | None = None

    def set_project_root(self, project_root: str) -> None:
        """Set the project root for lazy initialization.

        Args:
            project_root: Absolute path to the project root directory

        """
        self._project_root = project_root
        log.debug(f"Lazy initialization configured for: {project_root}")

    def ensure_initialized(self) -> str | None:
        """Check if project is initialized; initialize if needed.

        This method is called at the start of tool execution. It:
        1. Checks if initialization has already been attempted
        2. Returns early if project is already active
        3. Acquires lock to ensure thread-safe single initialization
        4. Performs non-interactive project generation
        5. Returns activation message to user

        Returns:
            Activation message if initialization occurred, None otherwise.
            The message is safe to include in tool results.

        """
        # Quick path: skip if already attempted or project is active
        if self._initialization_attempted or self._agent.get_active_project() is not None:
            return None

        # Acquire lock to ensure only one thread performs initialization
        result: str | None = None
        with self._initialization_lock:
            # Re-check after acquiring lock (thread-safe double-checked locking)
            if not self._initialization_attempted:
                self._initialization_attempted = True

                # Verify project root is set
                if self._project_root:
                    # Perform initialization
                    try:
                        project = self._run_initialization()
                        result = self._format_activation_message(project)
                    except Exception as e:
                        log.exception(f"Lazy initialization failed: {e}")
                        result = self._get_error_message(e)
                else:
                    log.debug("Project root not set, skipping lazy initialization")

        return result

    def _run_initialization(self) -> "Project":
        """Run autogenerate and activate the project.

        This method:
        1. Detects programming languages in the project
        2. Creates .murena/project.yml with sensible defaults
        3. Activates the project in the agent
        4. Returns the activated project

        Returns:
            The initialized and activated Project instance

        Raises:
            ValueError: If no source files are found in the project
            Exception: Other errors during initialization

        """
        from murena.config.murena_config import ProjectConfig
        from murena.project import Project

        # self._project_root is guaranteed non-None by caller (ensure_initialized)
        assert self._project_root is not None
        project_root = self._project_root

        log.info(f"Starting lazy project initialization: {project_root}")

        # Run autogenerate with timeout for language detection
        # interactive=False prevents TTY prompts (critical for MCP stdio transport)
        project_config = ProjectConfig.autogenerate(
            project_root=project_root,
            save_to_disk=True,
            interactive=False,
        )

        log.debug(f"Generated config: {project_config}")

        # Activate the project in the agent
        project = Project(
            project_root=project_root,
            project_config=project_config,
            is_newly_created=True,
        )

        # Trigger activation in agent (registers language servers, etc.)
        self._agent._activate_project(project)

        log.info(f"Lazy initialization complete for: {self._project_root}")

        return project

    def _format_activation_message(self, project: "Project") -> str:
        """Format user-friendly activation message.

        Args:
            project: The activated project

        Returns:
            Multi-line message describing the auto-initialization

        """
        config = project.project_config
        languages = ", ".join(lang.value for lang in config.languages) or "(none detected)"

        message = (
            f"✓ Auto-initialized Murena project in {self._project_root}\n"
            f"  Detected languages: {languages}\n"
            f"  Created .murena/project.yml"
        )

        return message

    def _get_error_message(self, error: Exception) -> str:
        """Format helpful error message for initialization failure.

        Args:
            error: The exception that occurred

        Returns:
            User-friendly error message with remediation suggestions

        """
        error_type = error.__class__.__name__
        error_msg = str(error)

        # Handle specific error types with helpful guidance
        if "No source files found" in error_msg or isinstance(error, ValueError):
            return (
                f"⚠ Could not auto-initialize project in {self._project_root}:\n"
                f"  {error_msg}\n\n"
                f"To use Murena:\n"
                f"  1. Add source files (*.py, *.ts, *.go, etc.)\n"
                f"  2. Or manually create: murena project create --project . --language python\n\n"
                f"File operations and memory tools will still work."
            )

        if isinstance(error, PermissionError):
            return (
                f"⚠ Cannot write .murena/project.yml (permission denied):\n"
                f"  {self._project_root}\n\n"
                f"Working in ephemeral mode (configuration not saved).\n"
                f"To persist configuration, check directory permissions."
            )

        # Generic error message with context
        return (
            f"⚠ Failed to auto-initialize project:\n"
            f"  {error_type}: {error_msg}\n\n"
            f"Check the Murena logs for details:\n"
            f"  ~/.murena/logs/mcp_*.log"
        )
