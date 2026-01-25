"""
Tools supporting the general workflow of the agent
"""

import json
import platform

from murena.tools import Tool, ToolMarkerDoesNotRequireActiveProject


class CheckOnboardingPerformedTool(Tool):
    """
    Checks whether project onboarding was already performed.
    """

    def apply(self) -> str:
        """
        Checks whether project onboarding was already performed.
        You should always call this tool before beginning to actually work on the project/after activating a project.
        """
        from .memory_tools import ListMemoriesTool

        list_memories_tool = self.agent.get_tool(ListMemoriesTool)
        memories = json.loads(list_memories_tool.apply())
        if len(memories) == 0:
            return (
                "Onboarding not performed yet (no memories available). "
                + "You should perform onboarding by calling the `onboarding` tool before proceeding with the task."
            )
        else:
            return f"""The onboarding was already performed, below is the list of available memories.
            Do not read them immediately, just remember that they exist and that you can read them later, if it is necessary
            for the current task.
            Some memories may be based on previous conversations, others may be general for the current project.
            You should be able to tell which one you need based on the name of the memory.
            
            {memories}"""


class OnboardingTool(Tool):
    """
    Performs onboarding (identifying the project structure and essential tasks, e.g. for testing or building).
    """

    def apply(self) -> str:
        """
        Call this tool if onboarding was not performed yet.
        You will call this tool at most once per conversation.

        :return: instructions on how to create the onboarding information
        """
        system = platform.system()
        return self.prompt_factory.create_onboarding_prompt(system=system)


class ThinkAboutCollectedInformationTool(Tool):
    """
    Thinking tool for pondering the completeness of collected information.
    """

    def apply(self) -> str:
        """
        Think about the collected information and whether it is sufficient and relevant.
        This tool should ALWAYS be called after you have completed a non-trivial sequence of searching steps like
        find_symbol, find_referencing_symbols, search_files_for_pattern, read_file, etc.
        """
        return self.prompt_factory.create_think_about_collected_information()


class ThinkAboutTaskAdherenceTool(Tool):
    """
    Thinking tool for determining whether the agent is still on track with the current task.
    """

    def apply(self) -> str:
        """
        Think about the task at hand and whether you are still on track.
        Especially important if the conversation has been going on for a while and there
        has been a lot of back and forth.

        This tool should ALWAYS be called before you insert, replace, or delete code.
        """
        return self.prompt_factory.create_think_about_task_adherence()


class ThinkAboutWhetherYouAreDoneTool(Tool):
    """
    Thinking tool for determining whether the task is truly completed.
    """

    def apply(self) -> str:
        """
        Whenever you feel that you are done with what the user has asked for, it is important to call this tool.
        """
        return self.prompt_factory.create_think_about_whether_you_are_done()


class SummarizeChangesTool(Tool):
    """
    Provides instructions for summarizing the changes made to the codebase.
    """

    def apply(self) -> str:
        """
        Summarize the changes you have made to the codebase.
        This tool should always be called after you have fully completed any non-trivial coding task,
        but only after the think_about_whether_you_are_done call.
        """
        return self.prompt_factory.create_summarize_changes()


class PrepareForNewConversationTool(Tool):
    """
    Provides instructions for preparing for a new conversation (in order to continue with the necessary context).
    """

    def apply(self) -> str:
        """
        Instructions for preparing for a new conversation. This tool should only be called on explicit user request.
        """
        return self.prompt_factory.create_prepare_for_new_conversation()


class InitialInstructionsTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Provides instructions on how to use the Murena toolbox.
    Should only be used in settings where the system prompt is not read automatically by the client.

    NOTE: Some MCP clients (including Claude Desktop) do not read the system prompt automatically!
    """

    def apply(self) -> str:
        """
        Provides the 'Murena Instructions Manual', which contains essential information on how to use the Murena toolbox.
        IMPORTANT: If you have not yet read the manual, call this tool immediately after you are given your task by the user,
        as it will critically inform you!
        """
        return self.agent.create_system_prompt()


class RunWorkflowTool(Tool):
    """
    Execute a predefined workflow.

    Workflows automate common multi-step patterns:
    - test-fix-commit: Run tests, fix failures, commit
    - review-pr: Lint, test, security scan
    - refactor-safe: Rename with test validation

    Provides 90% token savings vs manual multi-step execution.
    """

    def apply(self, name: str, args: dict[str, str] | None = None, verbose: bool = False) -> str:
        """
        Execute a workflow by name with the given arguments.

        Example:
        - run_workflow("test-fix-commit", {"file": "tests/test_auth.py"})
        - run_workflow("refactor-safe", {"symbol": "MyClass", "file": "src/foo.py", "new_name": "BetterClass"})

        :param name: Workflow name (e.g., "test-fix-commit")
        :param args: Arguments to pass to workflow (available as ${arg_name} in workflow steps)
        :param verbose: Whether to return verbose output (default: compact format)
        :return: JSON string with workflow result

        """
        from murena.workflows.workflow_dsl import WorkflowLoader
        from murena.workflows.workflow_engine import WorkflowEngine

        # Load workflow
        loader = WorkflowLoader(project_root=self.get_project_root())
        workflow = loader.get_workflow(name)

        if workflow is None:
            available = loader.list_workflows()
            return json.dumps({"error": f"Workflow '{name}' not found. Available workflows: {', '.join(available)}"})

        # Execute workflow
        engine = WorkflowEngine(self.agent)

        try:
            result = engine.execute(workflow, args or {}, verbose=verbose)

            if verbose:
                return json.dumps(result.to_verbose_dict(), indent=2)
            else:
                return json.dumps(result.to_compact_dict())

        except Exception as e:
            return json.dumps({"error": f"Workflow execution failed: {e}"})


class ListWorkflowsTool(Tool):
    """
    List all available workflows.

    Shows built-in, user-defined, and project-specific workflows.
    """

    def apply(self) -> str:
        """
        List all available workflows with descriptions.

        Returns:
        - Built-in workflows (shipped with Murena)
        - User workflows (~/.murena/workflows/)
        - Project workflows (.murena/workflows/)

        :return: JSON string with workflow list

        """
        from murena.workflows.workflow_dsl import WorkflowLoader

        loader = WorkflowLoader(project_root=self.get_project_root())
        workflows = loader.load_all()

        workflow_list = []
        for name, workflow in workflows.items():
            workflow_list.append(
                {
                    "name": name,
                    "description": workflow.description,
                    "steps": len(workflow.steps),
                    "author": workflow.author or "Unknown",
                }
            )

        return json.dumps({"workflows": workflow_list, "total": len(workflow_list)}, indent=2)
