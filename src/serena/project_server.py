# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import pickle
import secrets
import threading
from typing import TYPE_CHECKING, Any

import requests as requests_lib
from flask import Flask, Response, abort, request
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


class CallFacadeMethodRequest(BaseModel):
    """
    Request model for the /call_facade_method endpoint: the execution of a REPL facade method
    in the context of a project.
    """

    project_name: str
    facade_name: str
    method_name: str
    args: list[Any]
    kwargs: dict[str, Any]


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

    def __init__(self, host: str = "127.0.0.1", port: int | None = None) -> None:
        """
        :param host: the host address to listen on.
        :param port: the port to listen on; if None, use default
        """
        from serena.agent import SerenaAgent

        if port is None:
            port = self.PORT

        serena_config = SerenaConfig.from_config_file().with_headless_mode_overrides()
        serena_config.language_backend = LanguageBackend.LSP

        self._agent = SerenaAgent(serena_config=serena_config)
        self._loaded_projects_by_root: dict[str, "Project"] = {}
        self._project_load_locks_by_root: dict[str, threading.Lock] = {}
        self._active_project_lock = threading.Lock()
        self._loaded_projects_lock = threading.Lock()
        self._port = port
        self._host = host

        # create the Flask application, limiting trusted hosts for the case where the server is running on localhost
        self._app = Flask(__name__)
        local_hosts = ["localhost", "127.0.0.1"]
        if self._host in local_hosts:
            self._app.config["TRUSTED_HOSTS"] = local_hosts

        self._setup_routes()

    def get_serena_config(self) -> SerenaConfig:
        return self._agent.serena_config

    def get_auth_secret(self) -> str:
        """Returns the authentication secret used by the server."""
        return self._agent.serena_config.auth_secret

    def _setup_routes(self) -> None:
        @self._app.before_request
        def authenticate() -> None:
            # authenticate every request before parsing input or accessing projects
            secret = self.get_auth_secret()
            provided = request.headers.get("Authorization", "")
            if not secret or not secrets.compare_digest(provided.encode("utf-8"), f"Bearer {secret}".encode()):
                abort(401)

        @self._app.route("/heartbeat", methods=["GET"])
        def heartbeat() -> dict[str, str]:
            return {"status": "alive"}

        @self._app.route("/query_project", methods=["POST"])
        def query_project() -> str:
            query_request = QueryProjectRequest.model_validate(request.get_json())
            return self._query_project(query_request)

        @self._app.route("/call_facade_method", methods=["POST"])
        def call_facade_method() -> Response:
            call_request = CallFacadeMethodRequest.model_validate(request.get_json())
            try:
                result = self._call_facade_method(call_request)
            except Exception as e:
                # report the error to the client (which raises it in the REPL) instead of a generic server error page
                log.warning("Facade method call failed: %s", e)
                return Response(f"{type(e).__name__}: {e}", status=400, mimetype="text/plain")
            # NOTE: the result is pickled; the client (a Serena instance on the same machine) unpickles it
            return Response(pickle.dumps(result), mimetype="application/octet-stream")

    def _get_project(self, project_root_or_name: str) -> "Project":
        """Gets the project with the given name, loading it if necessary."""
        serena_config = self._agent.serena_config
        registered_project = serena_config.get_registered_project(project_root_or_name)
        if registered_project is None:
            raise ValueError(f"Project '{project_root_or_name}' is not registered with Serena.")

        key = str(registered_project.project_root)

        # find or publish the per-project load lock while holding the shared dictionaries
        with self._loaded_projects_lock:
            project = self._loaded_projects_by_root.get(key)
            if project is not None:
                return project
            project_load_lock = self._project_load_locks_by_root.get(key)
            if project_load_lock is None:
                project_load_lock = threading.Lock()
                self._project_load_locks_by_root[key] = project_load_lock

        # initialize only this project; another project's cached lookup or cold load can proceed
        with project_load_lock:
            with self._loaded_projects_lock:
                project = self._loaded_projects_by_root.get(key)
                if project is not None:
                    return project

            with LogTime(f"Loading project '{project_root_or_name}'"):
                project = registered_project.get_project_instance(serena_config)
                project.create_language_server_manager()

            with self._loaded_projects_lock:
                self._loaded_projects_by_root[key] = project
            return project

    def _query_project(self, req: QueryProjectRequest) -> str:
        """Handle a /query_project request by invoking the agent on the specified project and tool.

        The active project is process-wide state, whereas ``apply_ex`` runs the tool on the
        agent's task executor thread. Without the lock, a second request entering
        ``active_project_context`` while the first request's tool is still executing would
        redirect that tool to the wrong project (and restore the wrong project afterwards).
        """
        project = self._get_project(req.project_name)
        with self._active_project_lock, self._agent.active_project_context(project):
            tool = self._agent.get_tool_by_name(req.tool_name)
            if not tool.is_readonly():
                raise ValueError(f"Tool '{req.tool_name}' is not read-only and cannot be executed via the query_project route")
            params = json.loads(req.tool_params_json)
            return tool.apply_ex(**params)

    def _call_facade_method(self, req: CallFacadeMethodRequest) -> Any:
        """
        Handles a /call_facade_method request by executing the facade method on the agent's REPL facades in the
        context of the specified project (see `_query_project` regarding the lock).
        """
        project = self._get_project(req.project_name)
        with self._active_project_lock, self._agent.active_project_context(project):
            facade = self._agent.get_repl().entrypoint.get_facade_(req.facade_name)
            method = facade.get_method(req.method_name)
            return self._agent.execute_task(lambda: method(*req.args, **req.kwargs))

    def run(self) -> None:
        """
        Run the server on the given host and port.
        """
        from flask import cli

        # suppress the default Flask startup banner
        # ty cannot model reassigning a third-party module's function attribute (it rejects any
        # replacement, even one with an identical signature), so the monkeypatch is suppressed here
        cli.show_server_banner = lambda *args, **kwargs: None  # ty: ignore[invalid-assignment]

        self._app.run(host=self._host, port=self._port, debug=False, use_reloader=False, threaded=True)


class ProjectServerClient:
    """Client for interacting with a running :class:`ProjectServer`.

    Upon instantiation, the client verifies that the server is reachable
    by sending a heartbeat request. If the server is not running, a
    :class:`ConnectionError` is raised.
    """

    def __init__(self, serena_config: SerenaConfig, host: str = "127.0.0.1", port: int | None = None) -> None:
        """
        :param host: the host address of the project server.
        :param port: the port of the project server; if None, use default.
        :param auth_secret: the shared authentication secret; defaults to the secret in Serena's configuration.
        :raises ConnectionError: if the project server is not reachable.
        """
        if port is None:
            port = ProjectServer.PORT
        self._base_url = f"http://{host}:{port}"
        self._timeout = serena_config.tool_timeout - 1
        auth_secret = serena_config.auth_secret
        self._headers = {"Authorization": f"Bearer {auth_secret}"}

        # verify that the server is running
        try:
            response = requests_lib.get(f"{self._base_url}/heartbeat", headers=self._headers, timeout=5)
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

        response = requests_lib.post(f"{self._base_url}/query_project", json=payload, headers=self._headers, timeout=self._timeout)
        response.raise_for_status()
        return response.text

    def call_facade_method(self, project_name: str, facade_name: str, method_name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        """
        Executes a (read-only) REPL facade method in the context of a project.

        :param project_name: the name of the project to query
        :param facade_name: the facade's name
        :param method_name: the method's name
        :param args: the positional arguments (JSON-serialisable)
        :param kwargs: the keyword arguments (JSON-serialisable)
        :return: the method's result, as returned by the server (unpickled; the server is a trusted local process)
        """
        payload = CallFacadeMethodRequest(
            project_name=project_name, facade_name=facade_name, method_name=method_name, args=args, kwargs=kwargs
        ).model_dump()
        response = requests_lib.post(f"{self._base_url}/call_facade_method", json=payload, headers=self._headers, timeout=self._timeout)
        if not response.ok:
            raise ValueError(f"Project server error ({response.status_code}): {response.text[:2000]}")
        return pickle.loads(response.content)
