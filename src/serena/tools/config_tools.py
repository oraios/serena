import logging
import os
import subprocess
from pathlib import Path

from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional
from serena.util.file_system import find_git_main_repo_path, is_git_worktree

log = logging.getLogger(__name__)


class ListWorktreesTool(Tool, ToolMarkerOptional):
    """
    Lists all git worktrees for the current project.

    This tool shows all available worktrees, making it easy to see which
    worktrees exist and which one is currently active.
    """

    def apply(self) -> str:
        """
        List all git worktrees for the current project.

        :return: A formatted list of all worktrees with the current one highlighted
        """
        active_project = self.agent.get_active_project()
        if active_project is None:
            return "No active project. Please activate a project first."

        project_root = Path(active_project.project_root)

        # Determine the git common dir (main repo)
        if is_git_worktree(project_root):
            main_repo = find_git_main_repo_path(project_root)
            if main_repo is None:
                return f"Current directory '{project_root}' appears to be a worktree but main repo could not be found."
            git_dir = main_repo / ".git"
        else:
            git_dir = project_root / ".git"

        try:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                check=False,
                cwd=git_dir.parent if git_dir.is_dir() else project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return f"Failed to list worktrees: {result.stderr}"

            worktrees: list[dict[str, str | bool]] = []
            current_path: str | None = None

            for line in result.stdout.splitlines():
                if line.startswith("worktree "):
                    if current_path is not None:
                        worktrees.append({"path": current_path, "is_current": False})
                    current_path = line.split(" ", 1)[1]

            # Add the last worktree
            if current_path is not None:
                worktrees.append({"path": current_path, "is_current": False})

            # Mark the current worktree
            current_resolved = project_root.resolve()
            for wt in worktrees:
                wt_path = wt["path"]
                if isinstance(wt_path, str) and Path(wt_path).resolve() == current_resolved:
                    wt["is_current"] = True
                    break

            if not worktrees:
                return f"No git worktrees found for project at {project_root}."

            output = [f"Git worktrees for {active_project.project_name}:"]
            for wt in worktrees:
                marker = " (current)" if wt["is_current"] else ""
                wt_path = wt["path"]
                if not isinstance(wt_path, str):
                    continue
                path_display = wt_path
                # Try to show relative path if it's a subdirectory
                try:
                    rel_path = os.path.relpath(wt_path, project_root.parent.parent)
                    if not rel_path.startswith(".."):
                        path_display = f"{wt_path} (relative: {rel_path})"
                except ValueError:
                    pass
                output.append(f"  - {path_display}{marker}")

            output.append(f"\nCurrent project root: {project_root}")
            if is_git_worktree(project_root):
                main_repo = find_git_main_repo_path(project_root)
                if main_repo:
                    output.append(f"Main repository: {main_repo}")

            return "\n".join(output)

        except subprocess.TimeoutExpired:
            return "Command timed out while listing worktrees."
        except Exception as e:
            return f"Error listing worktrees: {e}"


class CheckGitStateTool(Tool, ToolMarkerOptional):
    """
    Checks for git state changes (branch switches, worktree changes, etc.).

    This tool detects when the user has changed branches or switched worktrees
    outside of Serena (e.g., via terminal commands), allowing Serena to stay
    in sync with the current repository state.
    """

    def apply(self) -> str:
        """
        Check for git state changes and report any differences.

        :return: Message describing any detected changes or current state
        """
        active_project = self.agent.get_active_project()
        if active_project is None:
            return "No active project. Please activate a project first."

        has_changed, message, new_state = active_project.check_git_state_changes()

        if has_changed:
            result = f"⚠️ Git state change detected!\n{message}\n\n"
            result += f"Current state: {active_project.get_git_state_summary()}"
            result += "\n\nNote: File locations and available content may have changed."
            return result
        else:
            return f"No git state changes detected.\n\nCurrent: {active_project.get_git_state_summary()}"


class SwitchWorktreeTool(Tool, ToolMarkerOptional):
    """
    Switches to a different git worktree of the current project.

    This tool allows switching between worktrees while maintaining the same
    project configuration and shared memories.
    """

    def apply(self, worktree: str) -> str:
        """
        Switch to a different git worktree.

        :param worktree: The path to the worktree, or the worktree name (relative to main repo)
        :return: Confirmation message with the new worktree path
        """
        active_project = self.agent.get_active_project()
        if active_project is None:
            return "No active project. Please activate a project first."

        project_root = Path(active_project.project_root)

        # Find the main repo
        if is_git_worktree(project_root):
            main_repo = find_git_main_repo_path(project_root)
        else:
            main_repo = project_root

        if main_repo is None:
            return f"Could not determine main repository for project at {project_root}."

        # Resolve the worktree path
        worktree_path = Path(worktree)
        if not worktree_path.is_absolute():
            # Assume it's relative to the main repo
            worktree_path = (main_repo / worktree).resolve()

        if not worktree_path.exists():
            return f"Worktree path does not exist: {worktree_path}"

        # Verify it's actually a worktree of the same repo
        if not is_git_worktree(worktree_path) and worktree_path != main_repo:
            return f"Path '{worktree_path}' does not appear to be a git worktree of the current project."

        worktree_main = find_git_main_repo_path(worktree_path) if is_git_worktree(worktree_path) else worktree_path
        if worktree_main != main_repo:
            return f"Path '{worktree_path}' is not a worktree of the current project (main repo: {main_repo})."

        # Activate the project at the new worktree path
        try:
            new_project = self.agent.activate_project_from_path_or_name(str(worktree_path))
            result = f"Switched to worktree at {worktree_path}"
            result += f"\n{new_project.get_activation_message()}"
            result += "\nNote: Memories are shared across all worktrees of this project."
            return result
        except Exception as e:
            return f"Error switching to worktree: {e}"


class OpenDashboardTool(Tool, ToolMarkerOptional, ToolMarkerDoesNotRequireActiveProject):
    """
    Opens the Serena web dashboard in the default web browser.
    The dashboard provides logs, session information, and tool usage statistics.
    """

    def apply(self) -> str:
        """
        Opens the Serena web dashboard in the default web browser.
        """
        if self.agent.open_dashboard():
            return f"Serena web dashboard has been opened in the user's default web browser: {self.agent.get_dashboard_url()}"
        else:
            return f"Serena web dashboard could not be opened automatically; tell the user to open it via {self.agent.get_dashboard_url()}"


class ActivateProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Activates a project based on the project name or path.
    """

    def apply(self, project: str) -> str:
        """
        Activates the project with the given name or path.

        :param project: the name of a registered project to activate or a path to a project directory
        """
        active_project = self.agent.activate_project_from_path_or_name(project)
        result = active_project.get_activation_message()
        result += "\nIMPORTANT: If you have not yet read the 'Serena Instructions Manual', do it now before continuing!"
        return result


class RemoveProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional):
    """
    Removes a project from the Serena configuration.
    """

    def apply(self, project_name: str) -> str:
        """
        Removes a project from the Serena configuration.

        :param project_name: Name of the project to remove
        """
        self.agent.serena_config.remove_project(project_name)
        return f"Successfully removed project '{project_name}' from configuration."


class SwitchModesTool(Tool, ToolMarkerOptional):
    """
    Activates modes by providing a list of their names
    """

    def apply(self, modes: list[str]) -> str:
        """
        Activates the desired modes, like ["editing", "interactive"] or ["planning", "one-shot"]

        :param modes: the names of the modes to activate
        """
        self.agent.set_modes(modes)

        # Inform the Agent about the activated modes and the currently active tools
        mode_instances = self.agent.get_active_modes()
        result_str = f"Active modes: {', '.join([mode.name for mode in mode_instances])}" + "\n"
        result_str += "\n".join([mode_instance.prompt for mode_instance in mode_instances]) + "\n"
        result_str += f"Currently active tools: {', '.join(self.agent.get_active_tool_names())}"
        return result_str


class GetCurrentConfigTool(Tool):
    """
    Prints the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
    """

    def apply(self) -> str:
        """
        Print the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
        """
        return self.agent.get_current_config_overview()
