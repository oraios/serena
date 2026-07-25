import json
import os
import platform
import shlex
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import click

from serena.util.shell import execute_shell_command


class ClientSetupHandler(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    def set_project_scope(self, project_scope: bool) -> None:
        """Optional hook for handlers that support project-level setup."""

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
        result = execute_shell_command("claude --version", capture_stderr=True)
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
        result = execute_shell_command("codex --version", capture_stderr=True)
        return result.return_code == 0 and "codex-cli" in result.stdout

    def get_mcp_server_options(self) -> list[str]:
        return ["--context=codex", "--project-from-cwd"]

    def apply(self) -> bool:
        return self._run_shell_command(f"codex mcp add serena -- {self.get_mcp_server_command()}")


class ClientSetupHandlerCodeBuddy(ClientSetupHandler):
    def __init__(self) -> None:
        super().__init__("codebuddy")

    def is_applicable(self) -> bool:
        result = execute_shell_command("codebuddy --version", capture_stderr=True)
        return result.return_code == 0

    def get_mcp_server_options(self) -> list[str]:
        return ["--context=codebuddy", "--project-from-cwd"]

    def apply(self) -> bool:
        cmd = f"codebuddy mcp add --scope user serena -- {self.get_mcp_server_command()}"
        is_success = self._run_shell_command(cmd)
        if is_success:
            click.echo("\nIMPORTANT: We additionally recommend to set up hooks for CodeBuddy to ensure the best experience.")
            click.echo("   Please read the instructions here:")
            click.echo("   https://oraios.github.io/serena/02-usage/030_clients.html#codebuddy")
        return is_success


class ClientSetupHandlerGrok(ClientSetupHandler):
    """
    Setup for xAI Grok Build.
    """

    def __init__(self) -> None:
        super().__init__("grok")

    def is_applicable(self) -> bool:
        version_result = execute_shell_command("grok --version", capture_stderr=True)
        if version_result.return_code != 0 or not version_result.stdout.lower().startswith("grok "):
            return False

        mcp_result = execute_shell_command("grok mcp add --help", capture_stderr=True)
        return mcp_result.return_code == 0 and "Add or update an MCP server" in mcp_result.stdout

    def get_mcp_server_options(self) -> list[str]:
        return ["--context=grok", "--project-from-cwd"]

    def apply(self) -> bool:
        cmd = f"grok mcp add --scope user serena -- {self.get_mcp_server_command()}"
        is_success = self._run_shell_command(cmd)
        if is_success:
            click.echo("\nIMPORTANT: We additionally recommend to set up hooks for Grok to ensure the best experience.")
            click.echo("   Please read the instructions here:")
            click.echo("   https://oraios.github.io/serena/02-usage/030_clients.html#grok")
        return is_success


class ClientSetupHandlerDevin(ClientSetupHandler):
    """
    Setup for Devin CLI.

    Registers Serena as an MCP server and writes the minimal supporting
    configuration (permissions + hooks) into Devin CLI's JSON configuration
    file. One command therefore enables the full Devin/serena integration.
    """

    def __init__(self) -> None:
        super().__init__("devin")
        self._project_scope = False

    def set_project_scope(self, project_scope: bool) -> None:
        """When set, configure project-level Devin CLI config instead of user-level."""
        self._project_scope = project_scope

    def is_applicable(self) -> bool:
        result = execute_shell_command("devin --version", capture_stderr=True)
        if result.return_code != 0 or not result.stdout.lower().startswith("devin "):
            return False

        mcp_result = execute_shell_command("devin mcp add --help", capture_stderr=True)
        return mcp_result.return_code == 0 and "Add a new MCP server" in mcp_result.stdout

    def get_mcp_server_options(self) -> list[str]:
        options = [
            "--context=devin",
            "--enable-web-dashboard",
            "false",
            "--open-web-dashboard",
            "false",
            "--add-mode",
            "query-projects",
        ]
        if self._project_scope:
            options.extend(["--project", str(Path.cwd().resolve())])
        else:
            options.append("--project-from-cwd")
        return options

    def get_mcp_server_command(self) -> str:
        # shlex.join is safer than a plain join because some arguments (project path) may contain spaces.
        return f"serena start-mcp-server {shlex.join(self.get_mcp_server_options())}"

    def apply(self) -> bool:
        # Detailed instructions: https://oraios.github.io/serena/02-usage/030_clients.html#devin-cli
        scope = "project" if self._project_scope else "user"
        cmd = f"devin mcp add -s {scope} serena -- {self.get_mcp_server_command()}"
        if not self._run_shell_command(cmd):
            return False
        return self._configure_devin_config(scope)

    def _configure_devin_config(self, scope: str) -> bool:
        config_path = self._devin_config_path(scope)
        if config_path is None:
            click.echo("Could not determine Devin CLI configuration path.")
            return False
        try:
            config = self._read_devin_config(config_path)
            self._merge_serena_permissions(config)
            self._merge_serena_hooks(config)
            self._write_devin_config(config_path, config)
            click.echo("\nSerena Devin CLI integration configured:")
            click.echo(f"  Scope: {scope}")
            click.echo(f"  Config: {config_path}")
            click.echo("  MCP server: serena")
            click.echo("  Permissions: auto-approve mcp__serena__*")
            click.echo("  Hooks: SessionStart, PreToolUse, PostToolUse, PostCompaction, SessionEnd")
            return True
        except Exception as e:
            click.echo(f"Failed to update Devin CLI config: {e}")
            return False

    def _devin_config_path(self, scope: str) -> Path | None:
        if scope == "project":
            return Path.cwd() / ".devin" / "config.json"
        if scope == "local":
            return Path.cwd() / ".devin" / "config.local.json"
        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA")
            if not appdata:
                return None
            return Path(appdata) / "devin" / "config.json"
        return Path.home() / ".config" / "devin" / "config.json"

    def _read_devin_config(self, config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            return {}
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON in {config_path}: {e}") from e

    def _write_devin_config(self, config_path: Path, config: dict[str, Any]) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _merge_serena_permissions(self, config: dict[str, Any]) -> None:
        permissions = config.setdefault("permissions", {})
        allow = permissions.setdefault("allow", [])
        pattern = "mcp__serena__*"
        if pattern not in allow:
            allow.append(pattern)

    def _merge_serena_hooks(self, config: dict[str, Any]) -> None:
        hooks = config.setdefault("hooks", {})

        session_start_command = "serena-hooks activate --client=devin"
        pre_tool_use_command = "serena-hooks remind --client=devin"
        post_tool_use_command = "serena-hooks post-remind --client=devin"
        post_compaction_command = "serena-hooks activate --client=devin --include-instructions --event PostCompaction"
        session_end_command = "serena-hooks cleanup --client=devin"

        self._add_hook_event(hooks, "SessionStart", session_start_command)
        self._add_hook_event(hooks, "PreToolUse", pre_tool_use_command, matcher="")
        self._add_hook_event(hooks, "PostToolUse", post_tool_use_command, matcher="")
        self._add_hook_event(hooks, "PostCompaction", post_compaction_command)
        self._add_hook_event(hooks, "SessionEnd", session_end_command)

    def _add_hook_event(
        self,
        hooks: dict[str, Any],
        event: str,
        command: str,
        matcher: str | None = None,
    ) -> None:
        event_list = hooks.setdefault(event, [])
        if self._has_hook_command(event_list, command):
            return
        entry: dict[str, Any] = {"hooks": [{"type": "command", "command": command, "timeout": 10}]}
        if matcher is not None:
            entry["matcher"] = matcher
        event_list.append(entry)

    def _has_hook_command(self, event_list: list[Any], command: str) -> bool:
        for entry in event_list:
            for hook in entry.get("hooks", []):
                if hook.get("command") == command:
                    return True
        return False


client_setup_handlers = [
    ClientSetupHandlerClaudeCode(),
    ClientSetupHandlerCodeBuddy(),
    ClientSetupHandlerCodex(),
    ClientSetupHandlerGrok(),
    ClientSetupHandlerDevin(),
]
