from abc import ABC, abstractmethod

from serena.util.shell import execute_shell_command


class ClientSetupHandler(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def is_applicable(self) -> bool:
        """
        :return: whether the client setup can applied (respective client is available)
        """

    @abstractmethod
    def get_mcp_server_options(self) -> list[str]:
        pass

    def get_mcp_server_command(self) -> str:
        return f"serena start-mcp-server {' '.join(self.get_mcp_server_options())}"

    @abstractmethod
    def apply(self) -> bool:
        """
        Applies the client setup
        """


class ClientSetupHandlerClaudeCode(ClientSetupHandler):
    def __init__(self) -> None:
        super().__init__("ClaudeCode")

    def is_applicable(self) -> bool:
        result = execute_shell_command("claude --version")
        return result.return_code == 0 and "Claude" in result.stdout

    def get_mcp_server_options(self) -> list[str]:
        return ["--context=claude-code", "--project-from-cwd"]

    def apply(self) -> bool:
        result = execute_shell_command(f"claude mcp add --scope user serena -- {self.get_mcp_server_command()}")
        return result.return_code == 0


class ClientSetupHandlerCodexCLI(ClientSetupHandler):
    def __init__(self) -> None:
        super().__init__("CodexCLI")

    def is_applicable(self) -> bool:
        result = execute_shell_command("codex --version")
        return result.return_code == 0 and "codex-cli" in result.stdout

    def get_mcp_server_options(self) -> list[str]:
        return ["--context=codex", "--project-from-cwd"]

    def apply(self) -> bool:
        result = execute_shell_command(f"codex mcp add serena -- {self.get_mcp_server_command()}")
        return result.return_code == 0


client_setup_handlers = [ClientSetupHandlerClaudeCode(), ClientSetupHandlerCodexCLI()]
