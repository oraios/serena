"""
Workflow composition support.

This module enables workflows to call other workflows, creating reusable
workflow fragments and complex composite workflows.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

log = logging.getLogger(__name__)


class WorkflowComposer:
    """Handles workflow composition and fragment reuse."""

    def __init__(self, workflow_dirs: Optional[list[str]] = None):
        """Initialize the workflow composer.

        Args:
            workflow_dirs: Directories to search for workflows (default: ~/.murena/workflows, .murena/workflows)

        """
        if workflow_dirs is None:
            workflow_dirs = [
                str(Path.home() / ".murena" / "workflows"),
                ".murena/workflows",
            ]
        self._workflow_dirs = workflow_dirs
        self._fragment_cache: dict[str, list[dict[str, Any]]] = {}

    def load_workflow(self, workflow_name: str) -> Optional[dict[str, Any]]:
        """Load a workflow definition by name.

        Args:
            workflow_name: Name of the workflow to load

        Returns:
            Workflow definition dict or None if not found

        """
        for workflow_dir in self._workflow_dirs:
            workflow_path = Path(workflow_dir) / f"{workflow_name}.yml"
            if workflow_path.exists():
                with open(workflow_path) as f:
                    return yaml.safe_load(f)

        log.warning(f"Workflow '{workflow_name}' not found in {self._workflow_dirs}")
        return None

    def load_fragment(self, fragment_name: str) -> Optional[list[dict[str, Any]]]:
        """Load a reusable workflow fragment.

        Fragments are partial workflow definitions that can be included in other workflows.

        Args:
            fragment_name: Name of the fragment to load

        Returns:
            List of step definitions or None if not found

        """
        if fragment_name in self._fragment_cache:
            return self._fragment_cache[fragment_name]

        for workflow_dir in self._workflow_dirs:
            fragment_path = Path(workflow_dir) / "fragments" / f"{fragment_name}.yml"
            if fragment_path.exists():
                with open(fragment_path) as f:
                    fragment = yaml.safe_load(f)
                    self._fragment_cache[fragment_name] = fragment.get("steps", [])
                    return self._fragment_cache[fragment_name]

        log.warning(f"Fragment '{fragment_name}' not found")
        return None

    def compose_workflow(self, workflow_def: dict[str, Any]) -> dict[str, Any]:
        """Compose a workflow by resolving call_workflow and include_fragment steps.

        Args:
            workflow_def: Workflow definition with potential composition directives

        Returns:
            Fully composed workflow definition

        """
        composed_steps = []

        for step in workflow_def.get("steps", []):
            # Handle call_workflow step
            if step.get("call_workflow"):
                nested_workflow = self.load_workflow(step["call_workflow"])
                if nested_workflow:
                    # Merge parameters
                    nested_args = {**nested_workflow.get("args", {}), **step.get("args", {})}
                    # Add nested workflow steps
                    for nested_step in nested_workflow.get("steps", []):
                        # Interpolate nested workflow args
                        composed_step = self._interpolate_nested_args(nested_step, nested_args)
                        composed_steps.append(composed_step)
                else:
                    log.error(f"Failed to load nested workflow: {step['call_workflow']}")

            # Handle include_fragment step
            elif step.get("include_fragment"):
                fragment_steps = self.load_fragment(step["include_fragment"])
                if fragment_steps:
                    composed_steps.extend(fragment_steps)
                else:
                    log.error(f"Failed to load fragment: {step['include_fragment']}")

            # Regular step
            else:
                composed_steps.append(step)

        # Return composed workflow
        return {**workflow_def, "steps": composed_steps}

    def _interpolate_nested_args(self, step: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        """Interpolate nested workflow arguments into step.

        Args:
            step: Step definition
            args: Arguments to interpolate

        Returns:
            Step with interpolated arguments

        """
        # Simple implementation - can be enhanced for nested interpolation
        interpolated = {}
        for key, value in step.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                arg_name = value[2:-1]
                interpolated[key] = args.get(arg_name, value)
            elif isinstance(value, dict):
                interpolated[key] = self._interpolate_nested_args(value, args)
            else:
                interpolated[key] = value
        return interpolated


def create_example_workflows() -> None:
    """Create example workflow files demonstrating composition."""
    workflows_dir = Path.home() / ".murena" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    fragments_dir = workflows_dir / "fragments"
    fragments_dir.mkdir(exist_ok=True)

    # Example fragment: Test validation
    test_fragment = {
        "name": "test-validation",
        "description": "Reusable test validation fragment",
        "steps": [
            {"tool": "find_tests_for_symbol", "args": {"symbol_name": "${symbol_name}", "relative_path": "${relative_path}"}},
            {"tool": "run_tests"},
            {
                "condition": "${test_results.failed} > 0",
                "tool": "analyze_test_failure",
                "args": {"test_result": "${test_results}"},
            },
        ],
    }

    fragment_path = fragments_dir / "test-validation.yml"
    if not fragment_path.exists():
        with open(fragment_path, "w") as f:
            yaml.dump(test_fragment, f)
        log.info(f"Created example fragment: {fragment_path}")

    # Example composite workflow
    composite_workflow = {
        "name": "safe-refactor",
        "description": "Safely refactor with nested workflow calls",
        "args": {"symbol_name": None, "relative_path": None, "new_name": None},
        "steps": [
            # Find and analyze
            {"tool": "find_symbol", "args": {"name_path_pattern": "${symbol_name}", "relative_path": "${relative_path}"}},
            # Use fragment for test validation
            {"include_fragment": "test-validation"},
            # Perform refactoring
            {
                "tool": "rename_symbol",
                "args": {"name_path": "${symbol_name}", "relative_path": "${relative_path}", "new_name": "${new_name}"},
            },
            # Re-validate with tests (reuse fragment)
            {"include_fragment": "test-validation"},
        ],
    }

    composite_path = workflows_dir / "safe-refactor.yml"
    if not composite_path.exists():
        with open(composite_path, "w") as f:
            yaml.dump(composite_workflow, f)
        log.info(f"Created example composite workflow: {composite_path}")
