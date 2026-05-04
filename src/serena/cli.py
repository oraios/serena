import collections
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from logging import Logger
from pathlib import Path
from typing import Any, Literal

import click
from sensai.util import logging
from sensai.util.logging import FileLoggerContext, datetime_tag
from sensai.util.string import dict_string
from tqdm import tqdm

from serena import serena_version
from serena.config.client_setup import client_setup_handlers
from serena.config.context_mode import SerenaAgentContext, SerenaAgentMode
from serena.config.serena_config import (
    LanguageBackend,
    ModeSelectionDefinition,
    ModeSelectionDefinitionWithAddedModes,
    ProjectConfig,
    RegisteredProject,
    SerenaConfig,
    SerenaPaths,
)
from serena.constants import (
    DEFAULT_CONTEXT,
    PROMPT_TEMPLATES_DIR_INTERNAL,
    SERENA_LOG_FORMAT,
    SERENAS_OWN_CONTEXT_YAMLS_DIR,
    SERENAS_OWN_MODE_YAMLS_DIR,
)
from serena.prompt_factory import SerenaPromptFactory
from serena.util.cli_util import AutoRegisteringGroup
from serena.util.logging import MemoryLogHandler
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from solidlsp.util.subprocess_util import subprocess_kwargs

log = logging.getLogger(__name__)

_MAX_CONTENT_WIDTH = 200
_MODES_EXPLANATION = """\b\nBuilt-in mode names or paths to custom mode YAMLs with which to 
override the default_modes defined in the global Serena configuration or 
the active project.
For details on mode configuration, see 
  https://oraios.github.io/serena/02-usage/050_configuration.html#modes.
"""
_ADD_MODES_EXPLANATION = """\b\nMode names or paths to custom mode YAMLs which shall
be added on top of the other modes specified by the global/project configuration.
For details on mode configuration, see 
  https://oraios.github.io/serena/02-usage/050_configuration.html#modes.
"""


def find_project_root(root: str | Path | None = None) -> str | None:
    """Find project root by walking up from CWD.

    Checks for .serena/project.yml first (explicit Serena project), then .git (git root).

    :param root: If provided, constrains the search to this directory and below
                 (acts as a virtual filesystem root). Search stops at this boundary.
    :return: absolute path to project root or None if not suitable root is found
    """
    current = Path.cwd().resolve()
    boundary = Path(root).resolve() if root is not None else None

    def ancestors() -> Iterator[Path]:
        """Yield current directory and ancestors up to boundary."""
        yield current
        for parent in current.parents:
            yield parent
            if boundary is not None and parent == boundary:
                return

    # First pass: look for .serena
    for directory in ancestors():
        if (directory / ".serena" / "project.yml").is_file():
            return str(directory)

    # Second pass: look for .git
    for directory in ancestors():
        if (directory / ".git").exists():  # .git can be file (worktree) or dir
            return str(directory)

    return None


def _open_in_editor(path: str) -> None:
    """Open the given file in the system's default editor or viewer."""
    editor = os.environ.get("EDITOR")
    run_kwargs = subprocess_kwargs()
    try:
        if editor:
            subprocess.run([editor, path], check=False, **run_kwargs)
        elif sys.platform.startswith("win"):
            try:
                os.startfile(path)
            except OSError:
                subprocess.run(["notepad.exe", path], check=False, **run_kwargs)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False, **run_kwargs)
        else:
            subprocess.run(["xdg-open", path], check=False, **run_kwargs)
    except Exception as e:
        print(f"Failed to open {path}: {e}")


class ProjectType(click.ParamType):
    """ParamType allowing either a project name or a path to a project directory."""

    name = "[PROJECT_NAME|PROJECT_PATH]"

    def convert(self, value: str, param: Any, ctx: Any) -> str:
        path = Path(value).resolve()
        if path.exists() and path.is_dir():
            return str(path)
        return value


PROJECT_TYPE = ProjectType()


class TopLevelCommands(AutoRegisteringGroup):
    """Root CLI group containing the core Serena commands."""

    def __init__(self) -> None:
        super().__init__(
            name="serena",
            help="Main serena CLI commands. "
            "Note that you also have access to `serena-hooks` CLI commands which are kept under "
            "that separate entrypoint for performance reasons, see `serena-hooks --help`. You can run `<command> --help` for more info on each command.",
        )

        # register --version / -V flag
        self.params.append(
            click.Option(
                ["--version", "-V"],
                is_flag=True,
                expose_value=False,
                is_eager=True,
                callback=self._print_version,
                help="Show the version and exit.",
            )
        )

    @staticmethod
    def _print_version(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
        """Print version string and exit if the flag is set."""
        if not value:
            return
        click.echo(f"Serena {serena_version()}")
        ctx.exit()

    @staticmethod
    @click.command(
        "init",
        help="Initialize Serena by creating a global config file with the specified default language backend.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.option(
        "--language-backend",
        "-b",
        type=click.Choice([b.value for b in LanguageBackend]),
        default=LanguageBackend.LSP.value,
        show_default=True,
        help="Default code intelligence backend (can be overridden in the project config).",
    )
    def init(language_backend: Literal["LSP", "JetBrains"] = "LSP") -> None:
        click.echo(f"\nSerena version: {serena_version()}\n")
        serena_config = SerenaConfig.from_config_file()
        serena_config.language_backend = LanguageBackend(language_backend)
        serena_config.save()
        click.echo(f"Configuration file: {serena_config.config_file_path}")
        click.echo(f"Language backend: {language_backend}")

        # check for auto-configurable clients
        applicable_setup_handlers = []
        for setup_handler in client_setup_handlers:
            if setup_handler.is_applicable():
                applicable_setup_handlers.append(setup_handler)
        if len(applicable_setup_handlers) > 0:
            click.echo(
                "\nAuto-configurable clients detected.\nApply the following commands to configure the Serena MCP server (in a default configuration):"
            )
            for setup_handler in applicable_setup_handlers:
                click.echo(f"  serena setup {setup_handler.name}")

        click.echo("\nSerena has been initialised successfully.\n")

    @staticmethod
    @click.command(
        "setup",
        help="Set up Serena for use with a specific client by registering it as an MCP server.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument(
        "client",
        type=click.Choice([h.name for h in client_setup_handlers]),
    )
    def setup(client: str) -> None:
        # find the matching handler
        handler = next(h for h in client_setup_handlers if h.name == client)

        # check applicability
        if not handler.is_applicable():
            click.echo(f"\nCannot apply setup for client '{client}' (not found or not functional).\n")
            raise SystemExit(1)

        # apply the setup
        if handler.apply():
            click.echo(f"\nSerena has been successfully set up for {client}.\n")
        else:
            click.echo(f"\nFailed to set up Serena for {client}.\n")
            raise SystemExit(1)

    @staticmethod
    @click.command("start-mcp-server", help="Starts the Serena MCP server.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.option("--project", "project", type=PROJECT_TYPE, default=None, help="Path or name of project to activate at startup.")
    @click.option("--project-file", "project", type=PROJECT_TYPE, default=None, help="[DEPRECATED] Use --project instead.")
    @click.argument("project_file_arg", type=PROJECT_TYPE, required=False, default=None, metavar="")
    @click.option(
        "--context", type=str, default=DEFAULT_CONTEXT, show_default=True, help="Built-in context name or path to custom context YAML."
    )
    @click.option(
        "--mode",
        "default_modes",
        type=str,
        multiple=True,
        default=(),
        show_default=False,
        help=_MODES_EXPLANATION,
    )
    @click.option(
        "--add-mode",
        "added_modes",
        type=str,
        multiple=True,
        default=(),
        show_default=False,
        help=_ADD_MODES_EXPLANATION,
    )
    @click.option(
        "--language-backend",
        type=click.Choice([lb.value for lb in LanguageBackend]),
        default=None,
        help="Override the configured language backend.",
    )
    @click.option(
        "--transport",
        type=click.Choice(["stdio", "sse", "streamable-http"]),
        default="stdio",
        show_default=True,
        help="Transport protocol.",
    )
    @click.option(
        "--host",
        type=str,
        default="127.0.0.1",
        show_default=True,
        help="Listen address for the MCP server (when using corresponding transport).",
    )
    @click.option(
        "--port", type=int, default=8000, show_default=True, help="Listen port for the MCP server (when using corresponding transport)."
    )
    @click.option(
        "--enable-web-dashboard",
        type=bool,
        is_flag=False,
        default=None,
        help="Enable the web dashboard (overriding the setting in Serena's config). "
        "It is recommended to always enable the dashboard. If you don't want the browser to open on startup, set open-web-dashboard to False. "
        "For more information, see\nhttps://oraios.github.io/serena/02-usage/060_dashboard.html",
    )
    @click.option(
        "--enable-gui-log-window",
        type=bool,
        is_flag=False,
        default=None,
        help="Enable the gui log window (currently only displays logs; overriding the setting in Serena's config).",
    )
    @click.option(
        "--open-web-dashboard",
        type=bool,
        is_flag=False,
        default=None,
        help="Open Serena's dashboard in your browser after MCP server startup (overriding the setting in Serena's config).",
    )
    @click.option(
        "--log-level",
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
        default=None,
        help="Override log level in config.",
    )
    @click.option("--trace-lsp-communication", type=bool, is_flag=False, default=None, help="Whether to trace LSP communication.")
    @click.option("--tool-timeout", type=float, default=None, help="Override tool execution timeout in config.")
    @click.option(
        "--project-from-cwd",
        is_flag=True,
        default=False,
        help="Auto-detect project from current working directory (searches for .serena/project.yml or .git, falls back to CWD). Intended for CLI-based agents like Claude Code, Gemini and Codex.",
    )
    def start_mcp_server(
        project: str | None,
        project_file_arg: str | None,
        project_from_cwd: bool | None,
        context: str,
        default_modes: Sequence[str],
        added_modes: Sequence[str],
        language_backend: str | None,
        transport: Literal["stdio", "sse", "streamable-http"],
        host: str,
        port: int,
        enable_web_dashboard: bool | None,
        open_web_dashboard: bool | None,
        enable_gui_log_window: bool | None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None,
        trace_lsp_communication: bool | None,
        tool_timeout: float | None,
    ) -> None:
        from serena.mcp import SerenaMCPFactory

        # initialize logging, using INFO level initially (will later be adjusted by SerenaAgent according to the config)
        #   * memory log handler (for use by GUI/Dashboard)
        #   * stream handler for stderr (for direct console output, which will also be captured by clients like Claude Desktop)
        #   * file handler
        # (Note that stdout must never be used for logging, as it is used by the MCP server to communicate with the client.)
        Logger.root.setLevel(logging.INFO)
        formatter = logging.Formatter(SERENA_LOG_FORMAT)
        memory_log_handler = MemoryLogHandler()
        Logger.root.addHandler(memory_log_handler)
        stderr_handler = logging.StreamHandler(stream=sys.stderr)
        stderr_handler.formatter = formatter
        Logger.root.addHandler(stderr_handler)
        log_path = SerenaPaths().get_next_log_file_path("mcp")
        file_handler = logging.FileHandler(log_path, mode="w")
        file_handler.formatter = formatter
        Logger.root.addHandler(file_handler)

        log.info("Initializing Serena MCP server")
        log.info("Storing logs in %s", log_path)

        # Handle --project-from-cwd flag
        if project_from_cwd:
            if project is not None or project_file_arg is not None:
                raise click.UsageError("--project-from-cwd cannot be used with --project or positional project argument")
            project = find_project_root()
            if project is not None:
                log.info("Auto-detected project root: %s", project)
            else:
                log.warning("No project root found from %s; not activating any project", os.getcwd())

        project_file = project_file_arg or project

        mode_selection_def: ModeSelectionDefinition | None = None
        if default_modes or added_modes:
            mode_selection_def = ModeSelectionDefinitionWithAddedModes(default_modes=default_modes or None, added_modes=added_modes or None)

        factory = SerenaMCPFactory(context=context, project=project_file, memory_log_handler=memory_log_handler)
        server = factory.create_mcp_server(
            host=host,
            port=port,
            mode_selection_def=mode_selection_def,
            language_backend=LanguageBackend.from_str(language_backend) if language_backend else None,
            enable_web_dashboard=enable_web_dashboard,
            open_web_dashboard=open_web_dashboard,
            enable_gui_log_window=enable_gui_log_window,
            log_level=log_level,
            trace_lsp_communication=trace_lsp_communication,
            tool_timeout=tool_timeout,
        )
        if project_file_arg:
            log.warning(
                "Positional project arg is deprecated; use --project instead. Used: %s",
                project_file,
            )
        log.info("Starting MCP server …")
        server.run(transport=transport)

    @staticmethod
    @click.command(
        "print-system-prompt", help="Print the system prompt for a project.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH}
    )
    @click.argument("project", type=click.Path(exists=True), default=os.getcwd(), required=False)
    @click.option(
        "--log-level",
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
        default="WARNING",
        help="Log level for prompt generation.",
    )
    @click.option("--only-instructions", is_flag=True, help="Print only the initial instructions, without prefix/postfix.")
    @click.option(
        "--context", type=str, default=DEFAULT_CONTEXT, show_default=True, help="Built-in context name or path to custom context YAML."
    )
    @click.option(
        "--mode",
        "modes",
        type=str,
        multiple=True,
        default=(),
        show_default=False,
        help=_MODES_EXPLANATION,
    )
    def print_system_prompt(
        project: str, log_level: str, only_instructions: bool, context: str, modes: Sequence[str] | None = None
    ) -> None:
        from serena.agent import SerenaAgent

        prefix = "You will receive access to Serena's symbolic tools. Below are instructions for using them, take them into account."
        postfix = "You begin by acknowledging that you understood the above instructions and are ready to receive tasks."

        lvl = logging.getLevelNamesMapping()[log_level.upper()]
        logging.configure(level=lvl)
        context_instance = SerenaAgentContext.load(context)
        modes_selection_def: ModeSelectionDefinition | None = None
        if modes:
            modes_selection_def = ModeSelectionDefinition(default_modes=modes)
        serena_config = SerenaConfig.from_config_file()
        serena_config.web_dashboard = False
        print(serena_config.default_modes)
        print(serena_config.base_modes)

        agent = SerenaAgent(
            project=os.path.abspath(project),
            serena_config=serena_config,
            context=context_instance,
            modes=modes_selection_def,
        )
        instr = agent.create_system_prompt()
        if only_instructions:
            print(instr)
        else:
            print(f"{prefix}\n{instr}\n{postfix}")

    @staticmethod
    @click.command(
        "start-project-server",
        help="Starts the Serena project server, which exposes project querying capabilities via HTTP.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.option(
        "--host",
        type=str,
        default="127.0.0.1",
        show_default=True,
        help="Listen address for the project server.",
    )
    @click.option(
        "--port",
        type=int,
        default=None,
        help="Listen port for the project server (default: ProjectServer.PORT).",
    )
    @click.option(
        "--log-level",
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
        default=None,
        help="Override log level in config.",
    )
    def start_project_server(
        host: str,
        port: int | None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None,
    ) -> None:
        from serena.project_server import ProjectServer

        # initialize logging
        Logger.root.setLevel(logging.INFO)
        formatter = logging.Formatter(SERENA_LOG_FORMAT)
        stderr_handler = logging.StreamHandler(stream=sys.stderr)
        stderr_handler.formatter = formatter
        Logger.root.addHandler(stderr_handler)
        log_path = SerenaPaths().get_next_log_file_path("project-server")
        file_handler = logging.FileHandler(log_path, mode="w")
        file_handler.formatter = formatter
        Logger.root.addHandler(file_handler)

        if log_level is not None:
            Logger.root.setLevel(logging.getLevelNamesMapping()[log_level])

        log.info("Starting Serena project server")
        log.info("Storing logs in %s", log_path)

        server = ProjectServer()
        run_kwargs: dict[str, Any] = {"host": host}
        if port is not None:
            run_kwargs["port"] = port
        server.run(**run_kwargs)

    @staticmethod
    @click.command(
        "dashboard-viewer",
        help="Open the Serena dashboard viewer for a given URL.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument("url", type=str)
    @click.option("--width", type=int, default=1400, show_default=True, help="Window width.")
    @click.option("--height", type=int, default=900, show_default=True, help="Window height.")
    def dashboard_viewer(url: str, width: int, height: int) -> None:
        from serena.dashboard import SerenaDashboardViewer

        viewer = SerenaDashboardViewer(url, width=width, height=height)
        viewer.run()


class ModeCommands(AutoRegisteringGroup):
    """Group for 'mode' subcommands."""

    def __init__(self) -> None:
        super().__init__(name="mode", help="Manage Serena modes. You can run `mode <command> --help` for more info on each command.")

    @staticmethod
    @click.command("list", help="List available modes.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    def list() -> None:
        mode_names = SerenaAgentMode.list_registered_mode_names()
        max_len_name = max(len(name) for name in mode_names) if mode_names else 20
        for name in mode_names:
            mode_yml_path = SerenaAgentMode.get_path(name)
            is_internal = Path(mode_yml_path).is_relative_to(SERENAS_OWN_MODE_YAMLS_DIR)
            descriptor = "(internal)" if is_internal else f"(at {mode_yml_path})"
            name_descr_string = f"{name:<{max_len_name + 4}}{descriptor}"
            click.echo(name_descr_string)

    @staticmethod
    @click.command("create", help="Create a new mode or copy an internal one.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.option(
        "--name",
        "-n",
        type=str,
        default=None,
        help="Name for the new mode. If --from-internal is passed may be left empty to create a mode of the same name, which will then override the internal mode.",
    )
    @click.option("--from-internal", "from_internal", type=str, default=None, help="Copy from an internal mode.")
    def create(name: str, from_internal: str) -> None:
        if not (name or from_internal):
            raise click.UsageError("Provide at least one of --name or --from-internal.")
        mode_name = name or from_internal
        dest = os.path.join(SerenaPaths().user_modes_dir, f"{mode_name}.yml")
        src = (
            os.path.join(SERENAS_OWN_MODE_YAMLS_DIR, f"{from_internal}.yml")
            if from_internal
            else os.path.join(SERENAS_OWN_MODE_YAMLS_DIR, "mode.template.yml")
        )
        if not os.path.exists(src):
            raise FileNotFoundError(
                f"Internal mode '{from_internal}' not found in {SERENAS_OWN_MODE_YAMLS_DIR}. Available modes: {SerenaAgentMode.list_registered_mode_names()}"
            )
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
        click.echo(f"Created mode '{mode_name}' at {dest}")
        _open_in_editor(dest)

    @staticmethod
    @click.command("edit", help="Edit a custom mode YAML file.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.argument("mode_name")
    def edit(mode_name: str) -> None:
        path = os.path.join(SerenaPaths().user_modes_dir, f"{mode_name}.yml")
        if not os.path.exists(path):
            if mode_name in SerenaAgentMode.list_registered_mode_names(include_user_modes=False):
                click.echo(
                    f"Mode '{mode_name}' is an internal mode and cannot be edited directly. "
                    f"Use 'mode create --from-internal {mode_name}' to create a custom mode that overrides it before editing."
                )
            else:
                click.echo(f"Custom mode '{mode_name}' not found. Create it with: mode create --name {mode_name}.")
            return
        _open_in_editor(path)

    @staticmethod
    @click.command("delete", help="Delete a custom mode file.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.argument("mode_name")
    def delete(mode_name: str) -> None:
        path = os.path.join(SerenaPaths().user_modes_dir, f"{mode_name}.yml")
        if not os.path.exists(path):
            click.echo(f"Custom mode '{mode_name}' not found.")
            return
        os.remove(path)
        click.echo(f"Deleted custom mode '{mode_name}'.")


class ContextCommands(AutoRegisteringGroup):
    """Group for 'context' subcommands."""

    def __init__(self) -> None:
        super().__init__(
            name="context", help="Manage Serena contexts. You can run `context <command> --help` for more info on each command."
        )

    @staticmethod
    @click.command("list", help="List available contexts.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    def list() -> None:
        context_names = SerenaAgentContext.list_registered_context_names()
        max_len_name = max(len(name) for name in context_names) if context_names else 20
        for name in context_names:
            context_yml_path = SerenaAgentContext.get_path(name)
            is_internal = Path(context_yml_path).is_relative_to(SERENAS_OWN_CONTEXT_YAMLS_DIR)
            descriptor = "(internal)" if is_internal else f"(at {context_yml_path})"
            name_descr_string = f"{name:<{max_len_name + 4}}{descriptor}"
            click.echo(name_descr_string)

    @staticmethod
    @click.command(
        "create", help="Create a new context or copy an internal one.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH}
    )
    @click.option(
        "--name",
        "-n",
        type=str,
        default=None,
        help="Name for the new context. If --from-internal is passed may be left empty to create a context of the same name, which will then override the internal context",
    )
    @click.option("--from-internal", "from_internal", type=str, default=None, help="Copy from an internal context.")
    def create(name: str, from_internal: str) -> None:
        if not (name or from_internal):
            raise click.UsageError("Provide at least one of --name or --from-internal.")
        ctx_name = name or from_internal
        dest = os.path.join(SerenaPaths().user_contexts_dir, f"{ctx_name}.yml")
        src = (
            os.path.join(SERENAS_OWN_CONTEXT_YAMLS_DIR, f"{from_internal}.yml")
            if from_internal
            else os.path.join(SERENAS_OWN_CONTEXT_YAMLS_DIR, "context.template.yml")
        )
        if not os.path.exists(src):
            raise FileNotFoundError(
                f"Internal context '{from_internal}' not found in {SERENAS_OWN_CONTEXT_YAMLS_DIR}. Available contexts: {SerenaAgentContext.list_registered_context_names()}"
            )
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
        click.echo(f"Created context '{ctx_name}' at {dest}")
        _open_in_editor(dest)

    @staticmethod
    @click.command("edit", help="Edit a custom context YAML file.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.argument("context_name")
    def edit(context_name: str) -> None:
        path = os.path.join(SerenaPaths().user_contexts_dir, f"{context_name}.yml")
        if not os.path.exists(path):
            if context_name in SerenaAgentContext.list_registered_context_names(include_user_contexts=False):
                click.echo(
                    f"Context '{context_name}' is an internal context and cannot be edited directly. "
                    f"Use 'context create --from-internal {context_name}' to create a custom context that overrides it before editing."
                )
            else:
                click.echo(f"Custom context '{context_name}' not found. Create it with: context create --name {context_name}.")
            return
        _open_in_editor(path)

    @staticmethod
    @click.command("delete", help="Delete a custom context file.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.argument("context_name")
    def delete(context_name: str) -> None:
        path = os.path.join(SerenaPaths().user_contexts_dir, f"{context_name}.yml")
        if not os.path.exists(path):
            click.echo(f"Custom context '{context_name}' not found.")
            return
        os.remove(path)
        click.echo(f"Deleted custom context '{context_name}'.")


class SerenaConfigCommands(AutoRegisteringGroup):
    """Group for 'config' subcommands."""

    def __init__(self) -> None:
        super().__init__(name="config", help="Manage Serena configuration.")

    @staticmethod
    @click.command(
        "edit",
        help="Edit serena_config.yml in your default editor. Will create a config file from the template if no config is found.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    def edit() -> None:
        serena_config = SerenaConfig.from_config_file()
        assert serena_config.config_file_path is not None
        _open_in_editor(serena_config.config_file_path)


class ProjectCommands(AutoRegisteringGroup):
    """Group for 'project' subcommands."""

    def __init__(self) -> None:
        super().__init__(
            name="project", help="Manage Serena projects. You can run `project <command> --help` for more info on each command."
        )

    @staticmethod
    def _create_project(project_path: str, name: str | None, language: tuple[str, ...]) -> RegisteredProject:
        """
        Helper method to create a project configuration file.

        :param project_path: Path to the project directory
        :param name: Optional project name (defaults to directory name if not specified)
        :param language: Tuple of language names
        :raises FileExistsError: If project.yml already exists
        :raises ValueError: If an unsupported language is specified
        :return: the RegisteredProject instance
        """
        project_root = Path(project_path).resolve()
        serena_config = SerenaConfig.from_config_file()
        yml_path = serena_config.get_project_yml_location(str(project_root))
        if os.path.exists(yml_path):
            raise FileExistsError(f"Project file {yml_path} already exists.")

        languages: list[Language] = []
        if language:
            for lang in language:
                try:
                    languages.append(Language(lang.lower()))
                except ValueError:
                    all_langs = [l.value for l in Language]
                    raise ValueError(f"Unknown language '{lang}'. Supported: {all_langs}")

        generated_conf = ProjectConfig.autogenerate(
            project_root=project_path,
            serena_config=serena_config,
            project_name=name,
            languages=languages if languages else None,
            interactive=True,
        )
        languages_str = ", ".join([lang.value for lang in generated_conf.languages]) if generated_conf.languages else "N/A"
        click.echo(f"Generated project with languages {{{languages_str}}} at {yml_path}.")
        registered_project = serena_config.get_registered_project(str(project_root))
        if registered_project is None:
            registered_project = RegisteredProject(str(project_root), generated_conf)
            serena_config.add_registered_project(registered_project)

        return registered_project

    @staticmethod
    @click.command("create", help="Create a new Serena project configuration.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.argument("project_path", type=click.Path(exists=True, file_okay=False), default=os.getcwd())
    @click.option("--name", type=str, default=None, help="Project name; defaults to directory name if not specified.")
    @click.option(
        "--language", type=str, multiple=True, help="Programming language(s); inferred if not specified. Can be passed multiple times."
    )
    @click.option("--index", is_flag=True, help="Index the project after creation.")
    @click.option(
        "--log-level",
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
        default="WARNING",
        help="Log level for indexing (only used if --index is set).",
    )
    @click.option("--timeout", type=float, default=10, help="Timeout for indexing a single file (only used if --index is set).")
    def create(project_path: str, name: str | None, language: tuple[str, ...], index: bool, log_level: str, timeout: float) -> None:
        try:
            registered_project = ProjectCommands._create_project(project_path, name, language)
            if index:
                click.echo("Indexing project...")
                ProjectCommands._index_project(registered_project, log_level, timeout=timeout)
        except FileExistsError as e:
            raise click.ClickException(f"Project already exists: {e}\nUse 'serena project index' to index an existing project.")
        except ValueError as e:
            raise click.ClickException(str(e))

    @staticmethod
    @click.command(
        "index",
        help="Index a project by saving symbols to the LSP cache. Auto-creates project.yml if it doesn't exist.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument("project", type=PROJECT_TYPE, default=os.getcwd(), required=False)
    @click.option("--name", type=str, default=None, help="Project name (only used if auto-creating project.yml).")
    @click.option(
        "--language",
        type=str,
        multiple=True,
        help="Programming language(s) (only used if auto-creating project.yml). Inferred if not specified.",
    )
    @click.option(
        "--log-level",
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
        default="WARNING",
        help="Log level for indexing.",
    )
    @click.option("--timeout", type=float, default=10, help="Timeout for indexing a single file.")
    def index(project: str, name: str | None, language: tuple[str, ...], log_level: str, timeout: float) -> None:
        serena_config = SerenaConfig.from_config_file()
        registered_project = serena_config.get_registered_project(project, autoregister=True)
        if registered_project is None:
            # Project not found; auto-create it
            click.echo(f"No existing project found for '{project}'. Attempting auto-creation ...")
            try:
                registered_project = ProjectCommands._create_project(project, name, language)
            except Exception as e:
                raise click.ClickException(str(e))

        ProjectCommands._index_project(registered_project, log_level, timeout=timeout)

    @staticmethod
    def _index_project(registered_project: RegisteredProject, log_level: str, timeout: float) -> None:
        lvl = logging.getLevelNamesMapping()[log_level.upper()]
        logging.configure(level=lvl)
        serena_config = SerenaConfig.from_config_file()
        proj = registered_project.get_project_instance(serena_config=serena_config)
        click.echo(f"Indexing symbols in {proj} …")
        ls_mgr = proj.create_language_server_manager()
        try:
            log_file = os.path.join(proj.project_root, ".serena", "logs", "indexing.txt")

            files = proj.gather_source_files()

            collected_exceptions: list[Exception] = []
            files_failed = []
            language_file_counts: dict[Language, int] = collections.defaultdict(lambda: 0)
            last_save_time = time.monotonic()
            for i, f in enumerate(tqdm(files, desc="Indexing")):
                try:
                    ls = ls_mgr.get_language_server(f)
                    ls.request_document_symbols(f)
                    language_file_counts[ls.language] += 1
                except Exception as e:
                    log.error(f"Failed to index {f}, continuing.")
                    collected_exceptions.append(e)
                    files_failed.append(f)
                now = time.monotonic()
                if now - last_save_time >= 30:
                    ls_mgr.save_all_caches()
                    last_save_time = now
            reported_language_file_counts = {k.value: v for k, v in language_file_counts.items()}
            click.echo(f"Indexed files per language: {dict_string(reported_language_file_counts, brackets=None)}")
            ls_mgr.save_all_caches()

            if len(files_failed) > 0:
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                with open(log_file, "w") as f:
                    for file, exception in zip(files_failed, collected_exceptions, strict=True):
                        f.write(f"{file}\n")
                        f.write(f"{exception}\n")
                click.echo(f"Failed to index {len(files_failed)} files, see:\n{log_file}")
        finally:
            ls_mgr.stop_all()

    @staticmethod
    @click.command(
        "is_ignored_path",
        help="Check if a path is ignored by the project configuration.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument("path", type=click.Path(exists=False, file_okay=True, dir_okay=True))
    @click.argument("project", type=click.Path(exists=True, file_okay=False, dir_okay=True), default=os.getcwd())
    def is_ignored_path(path: str, project: str) -> None:
        """
        Check if a given path is ignored by the project configuration.

        :param path: The path to check.
        :param project: The path to the project directory, defaults to the current working directory.
        """
        from serena.project import Project

        serena_config = SerenaConfig.from_config_file()
        proj = Project.load(os.path.abspath(project), serena_config=serena_config)
        if os.path.isabs(path):
            path = os.path.relpath(path, start=proj.project_root)
        is_ignored = proj.is_ignored_path(path)
        click.echo(f"Path '{path}' IS {'ignored' if is_ignored else 'IS NOT ignored'} by the project configuration.")

    @staticmethod
    @click.command(
        "index-file",
        help="Index a single file by saving its symbols to the LSP cache.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument("file", type=click.Path(exists=True, file_okay=True, dir_okay=False))
    @click.argument("project", type=click.Path(exists=True, file_okay=False, dir_okay=True), default=os.getcwd())
    @click.option("--verbose", "-v", is_flag=True, help="Print detailed information about the indexed symbols.")
    def index_file(file: str, project: str, verbose: bool) -> None:
        """
        Index a single file by saving its symbols to the LSP cache, useful for debugging.
        :param file: path to the file to index, must be inside the project directory.
        :param project: path to the project directory, defaults to the current working directory.
        :param verbose: if set, prints detailed information about the indexed symbols.
        """
        from serena.project import Project

        serena_config = SerenaConfig.from_config_file()
        proj = Project.load(os.path.abspath(project), serena_config=serena_config)
        if os.path.isabs(file):
            file = os.path.relpath(file, start=proj.project_root)
        if proj.is_ignored_path(file, ignore_non_source_files=True):
            click.echo(f"'{file}' is ignored or declared as non-code file by the project configuration, won't index.")
            exit(1)
        ls_mgr = proj.create_language_server_manager()
        try:
            for ls in ls_mgr.iter_language_servers():
                click.echo(f"Indexing for language {ls.language.value} …")
                document_symbols = ls.request_document_symbols(file)
                symbols, _ = document_symbols.get_all_symbols_and_roots()
                if verbose:
                    click.echo(f"Symbols in file '{file}':")
                    for symbol in symbols:
                        click.echo(f"  - {symbol['name']} at line {symbol['selectionRange']['start']['line']} of kind {symbol['kind']}")
                ls.save_cache()
                click.echo(f"Successfully indexed file '{file}', {len(symbols)} symbols saved to cache in {ls.cache_dir}.")
        finally:
            ls_mgr.stop_all()

    @staticmethod
    @click.command(
        "health-check",
        help="Perform a comprehensive health check of the project's tools and language server.",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument("project", type=click.Path(exists=True, file_okay=False, dir_okay=True), default=os.getcwd())
    def health_check(project: str) -> None:
        """
        Perform a comprehensive health check of the project's tools and language server.

        :param project: path to the project directory, defaults to the current working directory.
        """
        # NOTE: completely written by Claude Code, only functionality was reviewed, not implementation
        from serena.agent import SerenaAgent
        from serena.project import Project
        from serena.tools import FindReferencingSymbolsTool, FindSymbolTool, GetSymbolsOverviewTool, SearchForPatternTool

        logging.configure(level=logging.INFO)
        project_path = os.path.abspath(project)
        serena_config = SerenaConfig.from_config_file()
        serena_config.language_backend = LanguageBackend.LSP
        serena_config.gui_log_window = False
        serena_config.web_dashboard = False
        proj = Project.load(project_path, serena_config=serena_config)

        # Create log file with timestamp
        timestamp = datetime_tag()
        log_dir = os.path.join(project_path, ".serena", "logs", "health-checks")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"health_check_{timestamp}.log")

        with FileLoggerContext(log_file, append=False, enabled=True):
            log.info("Starting health check for project: %s", project_path)

            try:
                # Create SerenaAgent with dashboard disabled
                log.info("Creating SerenaAgent with disabled dashboard...")

                agent = SerenaAgent(project=project_path, serena_config=serena_config)
                log.info("SerenaAgent created successfully")

                # Find first non-empty file that can be analyzed
                log.info("Searching for analyzable files...")
                files = proj.gather_source_files()
                target_file = None

                for file_path in files:
                    try:
                        full_path = os.path.join(project_path, file_path)
                        if os.path.getsize(full_path) > 0:
                            target_file = file_path
                            log.info("Found analyzable file: %s", target_file)
                            break
                    except (OSError, FileNotFoundError):
                        continue

                if not target_file:
                    log.error("No analyzable files found in project")
                    click.echo("❌ Health check failed: No analyzable files found")
                    click.echo(f"Log saved to: {log_file}")
                    return

                # Get tools from agent
                overview_tool = agent.get_tool(GetSymbolsOverviewTool)
                find_symbol_tool = agent.get_tool(FindSymbolTool)
                find_refs_tool = agent.get_tool(FindReferencingSymbolsTool)
                search_pattern_tool = agent.get_tool(SearchForPatternTool)

                # Test 1: Get symbols overview
                log.info("Testing GetSymbolsOverviewTool on file: %s", target_file)
                overview_data = agent.execute_task(lambda: overview_tool.get_symbol_overview(target_file))
                log.info(f"GetSymbolsOverviewTool returned: {overview_data}")

                if not overview_data:
                    log.error("No symbols found in file %s", target_file)
                    click.echo("❌ Health check failed: No symbols found in target file")
                    click.echo(f"Log saved to: {log_file}")
                    return

                # Extract suitable symbol (prefer class or function over variables)
                preferred_kinds = {SymbolKind.Class.name, SymbolKind.Function.name, SymbolKind.Method.name, SymbolKind.Constructor.name}
                selected_symbol = None
                for symbol in overview_data:
                    if symbol.get("kind") in preferred_kinds:
                        selected_symbol = symbol
                        break

                # If no preferred symbol found, use first available
                if not selected_symbol:
                    selected_symbol = overview_data[0]
                    log.info("No class or function found, using first available symbol")

                symbol_name = selected_symbol["name"]
                symbol_kind = selected_symbol["kind"]
                log.info("Using symbol for testing: %s (kind: %s)", symbol_name, symbol_kind)

                # Test 2: FindSymbolTool
                log.info("Testing FindSymbolTool for symbol: %s", symbol_name)
                find_symbol_result = agent.execute_task(
                    lambda: find_symbol_tool.apply(symbol_name, relative_path=target_file, include_body=True)
                )
                find_symbol_data = json.loads(find_symbol_result)
                log.info("FindSymbolTool found %d matches for symbol %s", len(find_symbol_data), symbol_name)

                # Test 3: FindReferencingSymbolsTool
                log.info("Testing FindReferencingSymbolsTool for symbol: %s", symbol_name)
                try:
                    find_refs_result = agent.execute_task(lambda: find_refs_tool.apply(symbol_name, relative_path=target_file))
                    find_refs_data = json.loads(find_refs_result)
                    log.info("FindReferencingSymbolsTool found %d references for symbol %s", len(find_refs_data), symbol_name)
                except Exception as e:
                    log.warning("FindReferencingSymbolsTool failed for symbol %s: %s", symbol_name, str(e))
                    find_refs_data = []

                # Test 4: SearchForPatternTool to verify references
                log.info("Testing SearchForPatternTool for pattern: %s", symbol_name)
                try:
                    search_result = agent.execute_task(
                        lambda: search_pattern_tool.apply(substring_pattern=symbol_name, restrict_search_to_code_files=True)
                    )
                    search_data = json.loads(search_result)
                    pattern_matches = sum(len(matches) for matches in search_data.values())
                    log.info("SearchForPatternTool found %d pattern matches for %s", pattern_matches, symbol_name)
                except Exception as e:
                    log.warning("SearchForPatternTool failed for pattern %s: %s", symbol_name, str(e))
                    pattern_matches = 0

                # Verify tools worked as expected
                tools_working = True
                if not find_symbol_data:
                    log.error("FindSymbolTool returned no results")
                    tools_working = False

                if len(find_refs_data) == 0 and pattern_matches == 0:
                    log.warning("Both FindReferencingSymbolsTool and SearchForPatternTool found no matches - this might indicate an issue")

                log.info("Health check completed successfully")

                if tools_working:
                    click.echo("✅ Health check passed - All tools working correctly")
                else:
                    click.echo("⚠️  Health check completed with warnings - Check log for details")

            except Exception as e:
                log.exception("Health check failed with exception: %s", str(e))
                click.echo(f"❌ Health check failed: {e!s}")

            finally:
                click.echo(f"Log saved to: {log_file}")


class ToolCommands(AutoRegisteringGroup):
    """Group for 'tool' subcommands."""

    def __init__(self) -> None:
        super().__init__(
            name="tools",
            help="Commands related to Serena's tools. You can run `serena tools <command> --help` for more info on each command.",
        )

    @staticmethod
    @click.command(
        "list",
        help="Prints an overview of the tools that are active by default (not just the active ones for your project). For viewing all tools, pass `--all / -a`",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.option("--quiet", "-q", is_flag=True)
    @click.option("--all", "-a", "include_optional", is_flag=True, help="List all tools, including those not enabled by default.")
    @click.option("--only-optional", is_flag=True, help="List only optional tools (those not enabled by default).")
    def list(quiet: bool = False, include_optional: bool = False, only_optional: bool = False) -> None:
        from serena.tools import ToolRegistry

        tool_registry = ToolRegistry()
        if quiet:
            if only_optional:
                tool_names = tool_registry.get_tool_names_optional()
            elif include_optional:
                tool_names = tool_registry.get_tool_names()
            else:
                tool_names = tool_registry.get_tool_names_default_enabled()
            for tool_name in tool_names:
                click.echo(tool_name)
        else:
            ToolRegistry().print_tool_overview(include_optional=include_optional, only_optional=only_optional)

    @staticmethod
    @click.command(
        "description",
        help="Print the description of a tool, optionally with a specific context (the latter may modify the default description).",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument("tool_name", type=str)
    @click.option("--context", type=str, default=None, help="Context name or path to context file.")
    def description(tool_name: str, context: str | None = None) -> None:
        from serena.agent import SerenaAgent
        from serena.mcp import SerenaMCPFactory

        # Load the context
        serena_context = None
        if context:
            serena_context = SerenaAgentContext.load(context)

        agent = SerenaAgent(
            project=None,
            serena_config=SerenaConfig(web_dashboard=False, log_level=logging.INFO),
            context=serena_context,
        )
        tool = agent.get_tool_by_name(tool_name)
        mcp_tool = SerenaMCPFactory.make_mcp_tool(tool)
        click.echo(mcp_tool.description)


class PromptCommands(AutoRegisteringGroup):
    def __init__(self) -> None:
        super().__init__(name="prompts", help="Commands related to Serena's prompts that are outside of contexts and modes.")

    @staticmethod
    def _get_user_prompt_yaml_path(prompt_yaml_name: str) -> str:
        templates_dir = SerenaPaths().user_prompt_templates_dir
        os.makedirs(templates_dir, exist_ok=True)
        return os.path.join(templates_dir, prompt_yaml_name)

    @staticmethod
    @click.command(
        "list", help="Lists prompt names and YAML files that can be overridden.", context_settings={"max_content_width": _MAX_CONTENT_WIDTH}
    )
    def list() -> None:
        # list prompt names
        click.echo("Prompts:")
        factory = SerenaPromptFactory()
        for key in factory.get_prompt_names():
            template = factory.get_prompt_template(key)
            is_overridden = not template.path.startswith(PROMPT_TEMPLATES_DIR_INTERNAL)
            click.echo(f" * '{key}' ({template.path if is_overridden else 'default'})")

        # list prompts files
        click.echo("\nPrompt files (which you can override with the create-override command):")
        serena_prompt_yaml_names = [os.path.basename(f) for f in glob.glob(PROMPT_TEMPLATES_DIR_INTERNAL + "/*.yml")]
        for prompt_yaml_name in serena_prompt_yaml_names:
            user_prompt_yaml_path = PromptCommands._get_user_prompt_yaml_path(prompt_yaml_name)
            if os.path.exists(user_prompt_yaml_path):
                click.echo(f" * {user_prompt_yaml_path} merged with default prompts in {prompt_yaml_name}")
            else:
                click.echo(f" * {prompt_yaml_name}")

    @staticmethod
    @click.command(
        "create-override",
        help="Create an override of an internal prompts yaml for customizing Serena's prompts",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument("prompt_yaml_name")
    def create_override(prompt_yaml_name: str) -> None:
        """
        :param prompt_yaml_name: The yaml name of the prompt you want to override. Call the `list` command for discovering valid prompt yaml names.
        :return:
        """
        # for convenience, we can pass names without .yml
        if not prompt_yaml_name.endswith(".yml"):
            prompt_yaml_name = prompt_yaml_name + ".yml"
        user_prompt_yaml_path = PromptCommands._get_user_prompt_yaml_path(prompt_yaml_name)
        if os.path.exists(user_prompt_yaml_path):
            raise FileExistsError(f"{user_prompt_yaml_path} already exists.")
        serena_prompt_yaml_path = os.path.join(PROMPT_TEMPLATES_DIR_INTERNAL, prompt_yaml_name)
        shutil.copyfile(serena_prompt_yaml_path, user_prompt_yaml_path)
        _open_in_editor(user_prompt_yaml_path)

    @staticmethod
    @click.command(
        "edit-override", help="Edit an existing prompt override file", context_settings={"max_content_width": _MAX_CONTENT_WIDTH}
    )
    @click.argument("prompt_yaml_name")
    def edit_override(prompt_yaml_name: str) -> None:
        """
        :param prompt_yaml_name: The yaml name of the prompt override to edit.
        :return:
        """
        # for convenience, we can pass names without .yml
        if not prompt_yaml_name.endswith(".yml"):
            prompt_yaml_name = prompt_yaml_name + ".yml"
        user_prompt_yaml_path = PromptCommands._get_user_prompt_yaml_path(prompt_yaml_name)
        if not os.path.exists(user_prompt_yaml_path):
            click.echo(f"Override file '{prompt_yaml_name}' not found. Create it with: prompts create-override {prompt_yaml_name}")
            return
        _open_in_editor(user_prompt_yaml_path)

    @staticmethod
    @click.command("list-overrides", help="List existing prompt override files", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    def list_overrides() -> None:
        user_templates_dir = SerenaPaths().user_prompt_templates_dir
        os.makedirs(user_templates_dir, exist_ok=True)
        serena_prompt_yaml_names = [os.path.basename(f) for f in glob.glob(PROMPT_TEMPLATES_DIR_INTERNAL + "/*.yml")]
        override_files = glob.glob(os.path.join(user_templates_dir, "*.yml"))
        for file_path in override_files:
            if os.path.basename(file_path) in serena_prompt_yaml_names:
                click.echo(file_path)

    @staticmethod
    @click.command("delete-override", help="Delete a prompt override file", context_settings={"max_content_width": _MAX_CONTENT_WIDTH})
    @click.argument("prompt_yaml_name")
    def delete_override(prompt_yaml_name: str) -> None:
        """

        :param prompt_yaml_name:  The yaml name of the prompt override to delete."
        :return:
        """
        # for convenience, we can pass names without .yml
        if not prompt_yaml_name.endswith(".yml"):
            prompt_yaml_name = prompt_yaml_name + ".yml"
        user_prompt_yaml_path = PromptCommands._get_user_prompt_yaml_path(prompt_yaml_name)
        if not os.path.exists(user_prompt_yaml_path):
            click.echo(f"Override file '{prompt_yaml_name}' not found.")
            return
        os.remove(user_prompt_yaml_path)
        click.echo(f"Deleted override file '{prompt_yaml_name}'.")

    @staticmethod
    @click.command(
        "print-prompt-template",
        help="prints the (unrendered) template for the corresponding prompt name. "
        "This respects custom prompt yaml overrides and thus will print the value that will be used in Serena",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    @click.argument("prompt_name", type=str)
    def print_prompt_template(prompt_name: str) -> None:
        click.echo(SerenaPromptFactory().get_prompt_template_string(prompt_name))

    @staticmethod
    @click.command(
        "print-cc-system-prompt-override",
        help="To be used specifically in Claude Code as value for `--system-prompt`",
        context_settings={"max_content_width": _MAX_CONTENT_WIDTH},
    )
    def print_cc_system_prompt_override() -> None:
        click.echo(SerenaPromptFactory().create_cc_system_prompt_override())


_mode = ModeCommands()
_context = ContextCommands()
_project = ProjectCommands()
_config = SerenaConfigCommands()
_tools = ToolCommands()
_prompts = PromptCommands()

# Expose so we can use this as an entrypoint
top_level = TopLevelCommands()

# needed for the help script to work - register all subcommands to the top-level group
for subgroup in (_mode, _context, _project, _config, _tools, _prompts):
    top_level.add_command(subgroup)
