"""
YAML-based DSL for defining workflows.

Workflows are declarative descriptions of multi-step operations:
- test-fix-commit: Run tests, fix failures, commit
- review-pr: Lint, test, security scan
- refactor-safe: Rename with test validation

Example workflow:
```yaml
name: test-fix-commit
description: Run tests, fix failures, commit changes
steps:
  - name: run_tests
    tool: run_tests
    args:
      file_path: "${file}"
    on_failure: continue

  - name: verify_fix
    tool: run_tests
    args:
      file_path: "${file}"
    condition: "${run_tests.failed > 0}"
```
"""

import os
from dataclasses import dataclass, field
from typing import Any

import yaml
from sensai.util import logging

log = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """
    Represents a single step in a workflow.

    A step executes a tool with specified arguments and can have conditions,
    error handling, and variable interpolation.
    """

    name: str
    """Unique name for this step (used for referencing in conditions and variables)"""

    tool: str
    """Name of the tool to execute (e.g., 'run_tests', 'find_symbol')"""

    args: dict[str, Any] = field(default_factory=dict)
    """Arguments to pass to the tool (can use ${variable} interpolation)"""

    condition: str | None = None
    """Optional condition to evaluate before running (e.g., '${previous.failed > 0}')"""

    on_failure: str = "abort"
    """What to do on failure: 'abort' (stop workflow) or 'continue' (proceed to next step)"""

    description: str | None = None
    """Optional description of what this step does"""

    def __repr__(self) -> str:
        return f"WorkflowStep(name={self.name}, tool={self.tool})"


@dataclass
class Workflow:
    """
    Represents a complete workflow with multiple steps.

    Workflows are loaded from YAML files and can be:
    - Built-in (shipped with Murena)
    - User-defined (~/.murena/workflows/)
    - Project-specific (.murena/workflows/)
    """

    name: str
    """Unique workflow name (e.g., 'test-fix-commit')"""

    description: str
    """Human-readable description of what the workflow does"""

    steps: list[WorkflowStep]
    """Ordered list of steps to execute"""

    author: str | None = None
    """Optional workflow author"""

    version: str | None = None
    """Optional workflow version"""

    def __repr__(self) -> str:
        return f"Workflow(name={self.name}, steps={len(self.steps)})"

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Workflow":
        """
        Load a workflow from a YAML file.

        :param yaml_path: Path to YAML file
        :return: Parsed Workflow instance
        """
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"Workflow file not found: {yaml_path}")

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty workflow file: {yaml_path}")

        # Parse workflow metadata
        name = data.get("name")
        if not name:
            raise ValueError(f"Workflow must have a 'name' field: {yaml_path}")

        description = data.get("description", "No description")
        author = data.get("author")
        version = data.get("version")

        # Parse steps
        steps_data = data.get("steps", [])
        if not steps_data:
            raise ValueError(f"Workflow must have at least one step: {yaml_path}")

        steps = []
        for i, step_data in enumerate(steps_data):
            if not isinstance(step_data, dict):
                raise ValueError(f"Step {i} must be a dictionary: {yaml_path}")

            step_name = step_data.get("name", f"step_{i}")
            tool = step_data.get("tool")
            if not tool:
                raise ValueError(f"Step '{step_name}' must specify a 'tool': {yaml_path}")

            step = WorkflowStep(
                name=step_name,
                tool=tool,
                args=step_data.get("args", {}),
                condition=step_data.get("condition"),
                on_failure=step_data.get("on_failure", "abort"),
                description=step_data.get("description"),
            )
            steps.append(step)

        return cls(
            name=name,
            description=description,
            steps=steps,
            author=author,
            version=version,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """
        Create a workflow from a dictionary (e.g., for built-in workflows).

        :param data: Workflow specification as dictionary
        :return: Workflow instance
        """
        name = data.get("name")
        if not name:
            raise ValueError("Workflow must have a 'name' field")

        description = data.get("description", "No description")

        steps_data = data.get("steps", [])
        steps = []

        for i, step_data in enumerate(steps_data):
            step_name = step_data.get("name", f"step_{i}")
            tool = step_data.get("tool")
            if not tool:
                raise ValueError(f"Step '{step_name}' must specify a 'tool'")

            step = WorkflowStep(
                name=step_name,
                tool=tool,
                args=step_data.get("args", {}),
                condition=step_data.get("condition"),
                on_failure=step_data.get("on_failure", "abort"),
                description=step_data.get("description"),
            )
            steps.append(step)

        return cls(
            name=name,
            description=description,
            steps=steps,
            author=data.get("author"),
            version=data.get("version"),
        )


class WorkflowLoader:
    """
    Loads workflows from various locations:
    - Built-in workflows (murena/workflows/builtin/)
    - User workflows (~/.murena/workflows/)
    - Project workflows (.murena/workflows/)
    """

    def __init__(self, project_root: str | None = None):
        """
        Initialize workflow loader.

        :param project_root: Optional project root for project-specific workflows
        """
        self.project_root = project_root
        self._workflows: dict[str, Workflow] = {}

    def load_builtin_workflows(self) -> dict[str, Workflow]:
        """
        Load all built-in workflows.

        :return: Dictionary mapping workflow names to Workflow instances
        """
        # Import here to avoid circular dependency
        from murena.workflows.builtin_workflows import BUILTIN_WORKFLOWS

        workflows = {}
        for workflow_dict in BUILTIN_WORKFLOWS:
            workflow = Workflow.from_dict(workflow_dict)
            workflows[workflow.name] = workflow
            log.debug(f"Loaded built-in workflow: {workflow.name}")

        return workflows

    def load_user_workflows(self) -> dict[str, Workflow]:
        """
        Load user-defined workflows from ~/.murena/workflows/

        :return: Dictionary mapping workflow names to Workflow instances
        """
        user_workflows_dir = os.path.expanduser("~/.murena/workflows")
        return self._load_workflows_from_dir(user_workflows_dir)

    def load_project_workflows(self) -> dict[str, Workflow]:
        """
        Load project-specific workflows from .murena/workflows/

        :return: Dictionary mapping workflow names to Workflow instances
        """
        if not self.project_root:
            return {}

        project_workflows_dir = os.path.join(self.project_root, ".murena", "workflows")
        return self._load_workflows_from_dir(project_workflows_dir)

    def _load_workflows_from_dir(self, directory: str) -> dict[str, Workflow]:
        """
        Load all YAML workflows from a directory.

        :param directory: Directory to scan for .yml/.yaml files
        :return: Dictionary of workflows
        """
        workflows: dict[str, Workflow] = {}

        if not os.path.isdir(directory):
            return workflows

        for filename in os.listdir(directory):
            if not filename.endswith((".yml", ".yaml")):
                continue

            filepath = os.path.join(directory, filename)
            try:
                workflow = Workflow.from_yaml(filepath)
                workflows[workflow.name] = workflow
                log.debug(f"Loaded workflow from {filepath}: {workflow.name}")
            except Exception as e:
                log.warning(f"Failed to load workflow from {filepath}: {e}")

        return workflows

    def load_all(self) -> dict[str, Workflow]:
        """
        Load all workflows from all sources (built-in, user, project).

        Priority order (later overrides earlier):
        1. Built-in workflows
        2. User workflows
        3. Project workflows

        :return: Dictionary of all workflows
        """
        workflows = {}

        # Load in priority order
        workflows.update(self.load_builtin_workflows())
        workflows.update(self.load_user_workflows())
        workflows.update(self.load_project_workflows())

        self._workflows = workflows
        log.info(f"Loaded {len(workflows)} workflows total")

        return workflows

    def get_workflow(self, name: str) -> Workflow | None:
        """
        Get a workflow by name.

        :param name: Workflow name
        :return: Workflow instance or None if not found
        """
        if not self._workflows:
            self.load_all()

        return self._workflows.get(name)

    def list_workflows(self) -> list[str]:
        """
        List all available workflow names.

        :return: List of workflow names
        """
        if not self._workflows:
            self.load_all()

        return sorted(self._workflows.keys())
