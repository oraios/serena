import argparse
import logging
import os
import threading
from pathlib import Path
from typing import Any

from agno.agent import Agent
from agno.memory import AgentMemory
from agno.models.base import Model
from agno.storage.sqlite import SqliteStorage
from agno.tools.function import Function
from agno.tools.toolkit import Toolkit
from dotenv import load_dotenv
from sensai.util.logging import LogTime

from serena import serena_root_path
from serena.agent import SerenaAgent, Tool, show_fatal_exception_safe

log = logging.getLogger(__name__)


class SerenaAgnoToolkit(Toolkit):
    def __init__(self, serena_agent: SerenaAgent):
        super().__init__("Serena")
        for tool in serena_agent.get_exposed_tools():
            self.functions[tool.get_name()] = self._create_agno_function(tool)
        log.info("Agno agent functions: %s", list(self.functions.keys()))

    @staticmethod
    def _create_agno_function(tool: Tool) -> Function:
        def entrypoint(**kwargs: Any) -> str:
            if "kwargs" in kwargs:
                # Agno sometimes passes a kwargs argument explicitly, so we merge it
                kwargs.update(kwargs["kwargs"])
                del kwargs["kwargs"]
            log.info(f"Calling tool {tool}")
            return tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)

        function = Function.from_callable(tool.get_apply_fn())
        function.name = tool.get_name()
        function.entrypoint = entrypoint
        function.skip_entrypoint_processing = True
        return function


class SerenaAgnoAgentProvider:
    _agent: Agent | None = None
    _lock = threading.Lock()

    @classmethod
    def get_agent(cls, model: Model) -> Agent:
        """
        Returns the singleton instance of the Serena agent or creates it with the given parameters if it doesn't exist.

        NOTE: This is very ugly with poor separation of concerns, but the way in which the Agno UI works (reloading the
            module that defines the `app` variable) essentially forces us to do something like this.

        :param model: the large language model to use for the agent
        :return: the agent instance
        """
        with cls._lock:
            if cls._agent is not None:
                return cls._agent

            # change to Serena root
            os.chdir(serena_root_path())

            load_dotenv()

            parser = argparse.ArgumentParser(description="Serena coding assistant")
            parser.add_argument(
                "--project-file", required=False, help="Path to the project file, either absolute or relative to the root directory"
            )
            args = parser.parse_args()

            if args.project_file:
                project_file = Path(args.project_file).resolve()
                # If project file path is relative, make it absolute by joining with project root
                if not project_file.is_absolute():
                    # Get the project root directory (parent of scripts directory)
                    project_root = Path(serena_root_path())
                    project_file = project_root / args.project_file

                # Ensure the path is normalized and absolute
                project_file = str(project_file.resolve())
            else:
                project_file = None

            with LogTime("Loading Serena agent"):
                try:
                    serena_agent = SerenaAgent(project_file)
                except Exception as e:
                    show_fatal_exception_safe(e)
                    raise

            # Even though we don't want to keep history between sessions,
            # for agno-ui to work as a conversation, we use a persistent storage on disk.
            # This storage should be deleted between sessions.
            # Note that this might collide with custom options for the agent, like adding vector-search based tools.
            # See here for an explanation: https://www.reddit.com/r/agno/comments/1jk6qea/regarding_the_built_in_memory/
            sql_db_path = (Path("temp") / "agno_agent_storage.db").absolute()
            sql_db_path.parent.mkdir(exist_ok=True)
            # delete the db file if it exists
            log.info(f"Deleting DB from PID {os.getpid()}")
            if sql_db_path.exists():
                sql_db_path.unlink()

            agno_agent = Agent(
                name="Serena",
                model=model,
                # See explanation above on why storage is needed
                storage=SqliteStorage(table_name="serena_agent_sessions", db_file=str(sql_db_path)),
                description="A fully-featured coding assistant",
                tools=[SerenaAgnoToolkit(serena_agent)],
                # The tool calls will be shown in the UI anyway since whether to show them is configurable per tool
                # To see detailed logs, you should use the serena logger (configure it in the project file path)
                show_tool_calls=False,
                markdown=True,
                system_message=serena_agent.prompt_factory.create_system_prompt(),
                telemetry=False,
                memory=AgentMemory(),
                add_history_to_messages=True,
                num_history_responses=100,  # you might want to adjust this (expense vs. history awareness)
            )
            cls._agent = agno_agent
            log.info(f"Agent instantiated: {agno_agent}")

        return agno_agent
