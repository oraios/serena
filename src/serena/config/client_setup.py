from abc import ABC, abstractmethod

import click

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

    def _run_shell_command(self, cmd: str) -> bool:
        """
        Runs the given shell command.
        If the command fails (i.e., with non-zero exit code), prints the stdout and stderr of the command for debugging.

        :param cmd: the shell command to execute
        :return: whether the command executed successfully (i.e., with exit code 0)
        """
        click.echo("Running command:")
        click.echo(cmd)
        result = execute_shell_command(cmd)
        is_success = result.return_code == 0
        if not is_success:
            if result.stdout:
                click.echo(result.stdout)
            if result.stderr:
                click.echo(result.stderr)
        return is_success

    @abstractmethod
    def apply(self) -> bool:
        """
        Applies the client setup
        """


class ClientSetupHandlerClaudeCode(ClientSetupHandler):
    def __init__(self) -> None:
        super().__init__("claude-code")

    def is_applicable(self) -> bool:
        result = execute_shell_command("claude --version")
        return result.return_code == 0 and "Claude" in result.stdout

    def get_mcp_server_options(self) -> list[str]:
        return ["--context=claude-code", "--project-from-cwd"]

    def apply(self) -> bool:
        cmd = f"claude mcp add --scope user serena -- {self.get_mcp_server_command()}"
        is_success = self._run_shell_command(cmd)
        if is_success:
            click.echo("\nIMPORTANT: We additionally recommend to set up hooks for Claude Code to ensure the best experience.")
            click.echo("   Please read the instructions here:")
            click.echo("   https://oraios.github.io/serena/02-usage/030_clients.html#claude-code")
        return is_success


class ClientSetupHandlerCodex(ClientSetupHandler):
    """
    Setup for Codex CLI and Codex App (shared config)
    """

    def __init__(self) -> None:
        super().__init__("codex")

    def is_applicable(self) -> bool:
        result = execute_shell_command("codex --version")
        return result.return_code == 0 and "codex-cli" in result.stdout

    def get_mcp_server_options(self) -> list[str]:
        return ["--context=codex", "--project-from-cwd"]

    def apply(self) -> bool:
        return self._run_shell_command(f"codex mcp add serena -- {self.get_mcp_server_command()}")


client_setup_handlers = [ClientSetupHandlerClaudeCode(), ClientSetupHandlerCodex()]
