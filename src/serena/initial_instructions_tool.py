"""
Modified InitialInstructionsTool to use the new get_system_prompt method.
"""
from serena.agent import Tool


class InitialInstructionsTool(Tool):
    """
    Gets the initial instructions for the current project.
    Should only be used in settings where the system prompt cannot be set,
    e.g. in clients you have no control over, like Claude Desktop.
    """

    def apply(self) -> str:
        """
        Get the initial instructions for the current coding project.
        You should always call this tool before starting to work (including using any other tool) on any programming task!
        """
        # Use the get_system_prompt method if it exists, otherwise fall back to the original
        if hasattr(self.agent, "get_system_prompt"):
            return self.agent.get_system_prompt()
        else:
            return self.agent.prompt_factory.create_system_prompt()
