"""
Tools supporting the general workflow of the agent
"""

import json
import platform
from typing import Any, List

from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional

# Import Context for type annotation - needed for FastMCP dependency injection
try:
    from fastmcp import Context
except ImportError:
    Context = Any  # Fallback if fastmcp is not installed


class CheckOnboardingPerformedTool(Tool):
    """
    Checks whether project onboarding was already performed.
    """

    def apply(self) -> str:
        """
        Checks whether project onboarding was already performed.
        You should always call this tool before beginning to actually work on the project/after activating a project,
        but after calling the initial instructions tool.
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


class AskUserTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Asks the user to make a decision when the agent is uncertain which option to select.
    Uses MCP's elicitation feature to interactively request user input.
    """

    async def apply(self, question: str, options: List[str], ctx: Context | None = None) -> str:
        """
        Ask the user to choose between multiple options when you are uncertain which path to take.
        Use this tool when you need user input to make a decision and continue processing.

        :param question: The question to ask the user, providing context about the decision.
        :param options: A list of options (at least 2) for the user to choose from. Each option should be a clear, concise description.
        :param ctx: MCP context for elicitation (automatically injected by MCP server).
        :return: The user's selected option or an error message.
        """
        if len(options) < 2:
            return "Error: You must provide at least 2 options for the user to choose from."

        # Format the options for display
        formatted_options = "\n".join([f"- {option}" for option in options])

        # If no context is provided (non-MCP execution), return formatted question
        if ctx is None:
            return f"""
                    **Decision Required:**
                    {question}
                    **Available Options:**
                    {formatted_options}
                    Please respond with your selected option or provide additional guidance.
                    """

        # Use MCP elicitation for interactive user input
        try:
            # First, get the user's choice from the constrained options
            result = await ctx.elicit(question, response_type=options)

            # Handle the elicitation result
            if result.action == "accept" and result.data:
                # The data contains the selected option directly
                user_selected = result.data
                response = f"User selected option: {user_selected}"

                # Optionally ask for additional guidance as a follow-up
                guidance_result = await ctx.elicit(
                    "Would you like to provide any additional guidance for this choice?",
                    response_type=str
                )
                if guidance_result.action == "accept" and guidance_result.data:
                    response += f"\n\nAdditional guidance: {guidance_result.data}"

                return response
            elif result.action == "decline":
                return "User declined to make a selection. Please proceed with your best judgment or ask for clarification in a different way."
            else:  # cancelled
                return "User cancelled the decision request. The task may need to be reconsidered or abandoned."

        except Exception as e:
            return f"""
                    **Decision Required (Elicitation unavailable: {e}):**\n
                    {question}\n
                    **Available Options:**\n
                    {formatted_options}\n
                    Please respond with your selected option or provide additional guidance.
                    """


class InitialInstructionsTool(Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional):
    """
    Gets the initial instructions for the current project.
    Should only be used in settings where the system prompt cannot be set,
    e.g. in clients you have no control over, like Claude Desktop.
    """

    def apply(self) -> str:
        """
        Get the initial instructions for the current coding project.
        If you haven't received instructions on how to use Serena's tools in the system prompt,
        you should always call this tool before starting to work (including using any other tool) on any programming task,
        the only exception being when you are asked to call `activate_project`, which you should then call before.
        """
        return self.agent.create_system_prompt()
