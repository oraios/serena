"""
Tools supporting the general workflow of the agent
"""

import platform

from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional


class CheckOnboardingPerformedTool(Tool):
    """
    Checks whether project onboarding was already performed.
    """

    def apply(self) -> str:
        """
        Checks whether project onboarding was already performed.
        You should always call this tool before beginning to actually work on the project/after activating a project.
        """
        project_memories = self.memories_manager.list_project_memories()
        if len(project_memories) == 0:
            msg = (
                "Onboarding not performed yet (no memories available). "
                "You should perform onboarding by calling the `onboarding` tool before proceeding with the task. "
            )
        else:
            # Not reporting the list of memories here, as they were already reported at project activation
            # (with the system prompt if the project was activated at startup)
            msg = (
                f"Onboarding was already performed: {len(project_memories)} project memories are available. "
                "Consider reading memories if they appear relevant to the task at hand."
            )
        msg += " If you have not read the 'Serena Instructions Manual', do so now."
        return msg


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


class ThinkAboutCollectedInformationTool(Tool, ToolMarkerOptional):
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


class ThinkAboutTaskAdherenceTool(Tool, ToolMarkerOptional):
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


class ThinkAboutWhetherYouAreDoneTool(Tool, ToolMarkerOptional):
    """
    Thinking tool for determining whether the task is truly completed.
    """

    def apply(self) -> str:
        """
        Whenever you feel that you are done with what the user has asked for, it is important to call this tool.
        """
        return self.prompt_factory.create_think_about_whether_you_are_done()


class SummarizeChangesTool(Tool, ToolMarkerOptional):
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
    Provides instructions on how to use the Serena toolbox.
    Should only be used in settings where the system prompt is not read automatically by the client.

    NOTE: Some MCP clients (including Claude Desktop) do not read the system prompt automatically!
    """

    def apply(self) -> str:
        """
        Provides the 'Serena Instructions Manual', which contains essential information on how to use the Serena toolbox.
        IMPORTANT: If you have not yet read the manual, call this tool immediately after you are given your task by the user,
        as it will critically inform you!
        """
        return self.agent.create_system_prompt()
