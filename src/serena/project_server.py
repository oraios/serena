import json
import logging
from typing import TYPE_CHECKING

import requests as requests_lib
from flask import Flask, request
from pydantic import BaseModel
from sensai.util.logging import LogTime

from serena.config.serena_config import LanguageBackend, SerenaConfig
from serena.constants import SerenaPorts

if TYPE_CHECKING:
    from serena.project import Project

log = logging.getLogger(__name__)

# disable Werkzeug's logging to avoid cluttering the output
logging.getLogger("werkzeug").setLevel(logging.WARNING)


class QueryProjectRequest(BaseModel):
    """
    Request model for the /query_project endpoint, matching the interface of
    :class:`~serena.tools.query_project_tools.QueryProjectTool`.
    """

    project_name: str
    tool_name: str
    tool_params_json: str


class ProjectServer:
    """
    A lightweight Flask server that exposes a SerenaAgent's project querying
    capabilities via HTTP, using the LSP language server backend for symbolic retrieval.

    Projects are loaded on demand when a query is made for them, and cached in memory for subsequent queries.

    The server instantiates a :class:`SerenaAgent` with default options and
    provides a ``/query_project`` endpoint whose interface matches
    :class:`~serena.tools.query_project_tools.QueryProjectTool`.
    """

    PORT = SerenaPorts.PROJECT_SERVER_PORT

    def __init__(self) -> None:
        from serena.agent import SerenaAgent

        serena_config = SerenaConfig.from_config_file()
        serena_config.gui_log_window = False
        serena_config.web_dashboard = False
        serena_config.language_backend = LanguageBackend.LSP

        self._agent = SerenaAgent(serena_config=serena_config)
        self._loaded_projects_by_root: dict[str, "Project"] = {}

        # create the Flask application
        self._app = Flask(__name__)
        self._setup_routes()

    def _setup_routes(self) -> None:
        @self._app.route("/heartbeat", methods=["GET"])
        def heartbeat() -> dict[str, str]:
            return {"status": "alive"}

        @self._app.route("/query_project", methods=["POST"])
        def query_project() -> str:
            query_request = QueryProjectRequest.model_validate(request.get_json())
            return self._query_project(query_request)

    def _get_project(self, project_root_or_name: str) -> "Project":
        """Gets the project with the given name, loading it if necessary."""
        serena_config = self._agent.serena_config
        registered_project = serena_config.get_registered_project(project_root_or_name)
        if registered_project is None:
            raise ValueError(f"Project '{project_root_or_name}' is not registered with Serena.")

        key = str(registered_project.project_root)

        if key in self._loaded_projects_by_root:
            return self._loaded_projects_by_root[key]

        with LogTime(f"Loading project '{project_root_or_name}'"):
            project = registered_project.get_project_instance(serena_config)
            project.create_language_server_manager()
        self._loaded_projects_by_root[key] = project
        return project

    def _query_project(self, req: QueryProjectRequest) -> str:
        """Handle a /query_project request by invoking the agent on the specified project and tool."""
        project = self._get_project(req.project_name)
        with self._agent.active_project_context(project):
            tool = self._agent.get_tool_by_name(req.tool_name)
            if not tool.is_readonly():
                raise ValueError(f"Tool '{req.tool_name}' is not read-only and cannot be executed via the query_project route")
            params = json.loads(req.tool_params_json)
            return tool.apply_ex(**params)

    def run(self, host: str = "127.0.0.1", port: int = PORT) -> int:
        """Run the server on the given host and port.

        :param host: the host address to listen on.
        :param port: the port to listen on.
        :return: the port number the server is running on.
        """
        from flask import cli

        # suppress the default Flask startup banner
        cli.show_server_banner = lambda *args, **kwargs: None

        self._app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        return port


class ProjectServerClient:
    """Client for interacting with a running :class:`ProjectServer`.

    Upon instantiation, the client verifies that the server is reachable
    by sending a heartbeat request. If the server is not running, a
    :class:`ConnectionError` is raised.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = ProjectServer.PORT, timeout: int = 300) -> None:
        """
        :param host: the host address of the project server.
        :param port: the port of the project server.
        :raises ConnectionError: if the project server is not reachable.
        """
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout

        # verify that the server is running
        try:
            response = requests_lib.get(f"{self._base_url}/heartbeat", timeout=5)
            response.raise_for_status()
        except requests_lib.ConnectionError:
            raise ConnectionError(f"ProjectServer is not reachable at {self._base_url}. Make sure the server is running.")
        except requests_lib.RequestException as e:
            raise ConnectionError(f"ProjectServer health check failed: {e}")

    def query_project(self, project_name: str, tool_name: str, tool_params_json: str) -> str:
        """
        Query a project by executing a Serena tool in its context.

        The interface matches :meth:`QueryProjectTool.apply
        <serena.tools.query_project_tools.QueryProjectTool.apply>`.

        :param project_name: the name of the project to query.
        :param tool_name: the name of the tool to execute. The tool must be read-only.
        :param tool_params_json: the parameters to pass to the tool, encoded as a JSON string.
        :return: the tool's result as a string.
        """
        payload = QueryProjectRequest(
            project_name=project_name,
            tool_name=tool_name,
            tool_params_json=tool_params_json,
        ).model_dump()

        response = requests_lib.post(f"{self._base_url}/query_project", json=payload, timeout=self._timeout)
        response.raise_for_status()
        return response.text
