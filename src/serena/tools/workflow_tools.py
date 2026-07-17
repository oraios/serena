"""
Tools supporting the general workflow of the agent
"""

import platform

from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional, WriteMemoryTool


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
        write_memory_tool_available = self.agent.tool_is_exposed(WriteMemoryTool.get_name_from_cls())
        if not write_memory_tool_available:
            return "Memory writing tool not activated, skipping onboarding."
        system = platform.system()
        # seed the project-local memory-maintenance memory (or detect a global override) so
        # the prompt can point the agent at the conventions before it writes anything
        memory_maintenance_name = self.memory_manager.ensure_memory_maintenance_memory()
        return self.prompt_factory.create_onboarding_prompt(system=system, memory_maintenance_name=memory_maintenance_name)


class InitialInstructionsTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Provides instructions Serena usage (i.e. the 'Serena Instructions Manual')
    for clients that do not read the initial instructions when the MCP server is connected.
    """

    # noinspection PyIncorrectDocstring
    # (session_id is injected via apply_ex)
    def apply(self, session_id: str) -> str:
        """
        Provides the 'Serena Instructions Manual', which contains essential information on how to use the Serena toolbox.
        IMPORTANT: If you have not yet read the manual, call this tool immediately after you are given your task by the user,
        as it will critically inform you!
        """
        return self.agent.create_system_prompt(session_id=session_id)


class SerenaInfoTool(Tool, ToolMarkerOptional, ToolMarkerDoesNotRequireActiveProject):
    """
    Provides information about an advanced topic on demand, facilitating context-efficiency.
    """

    def apply(self, topic: str) -> str:
        """
        Retrieves Serena-specific information
        :param topic: the topic, which you must have been given explicitly
        """
        match topic:
            case "jet_brains_debug_repl":
                return self.agent.prompt_factory.create_info_jet_brains_debug_repl()
            case _:
                raise ValueError("Invalid topic: " + topic)
