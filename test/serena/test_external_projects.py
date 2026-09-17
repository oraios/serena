"""
End-to-end test of querying an external project through the REPL: a project server executes the language server
operations of the queried project, and the (pickled) results are usable in the querying agent's REPL.
"""

import socket
import threading
from collections.abc import Iterator

import pytest
from werkzeug.serving import make_server

from serena.agent import SerenaAgent
from serena.config.serena_config import SerenaConfig
from serena.project_server import ProjectServer, ProjectServerClient
from serena.repl.api.lsp_api import LspSymbolCollection
from serena.tools import SerenaReplTool
from solidlsp.ls_config import LanguageServerId
from test.conftest import language_server_tests_enabled
from test.serena.test_serena_agent import serena_config  # noqa: F401  (fixture)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def project_server(serena_config: SerenaConfig) -> Iterator[tuple[ProjectServer, int]]:  # noqa: F811
    """
    Runs a project server (backed by a real agent) on a free port for the duration of the test.
    """
    config = serena_config
    port = _free_port()

    # construct the server around an agent with the test configuration (the constructor would load the user's configuration)
    server = ProjectServer.__new__(ProjectServer)
    server._agent = SerenaAgent(serena_config=config)
    server._loaded_projects_by_root = {}
    server._project_load_locks_by_root = {}
    server._active_project_lock = threading.Lock()
    server._loaded_projects_lock = threading.Lock()
    server._port = port
    server._host = "127.0.0.1"
    from flask import Flask

    server._app = Flask(__name__)
    server._setup_routes()

    http_server = make_server("127.0.0.1", port, server._app, threaded=True)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, port
    finally:
        http_server.shutdown()
        server._agent.on_shutdown(timeout=5)


@pytest.mark.python
@pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.PYTHON), reason="python tests are disabled in this environment")
def test_facade_method_results_are_transferred_from_the_project_server(project_server: tuple[ProjectServer, int]) -> None:
    _, port = project_server
    client = ProjectServerClient(port=port)
    result = client.call_facade_method("test_repo_python", "lsp", "find_symbol", ["create_user"], {"include_body": True})

    # the result is a self-contained object which can be processed and rendered locally
    assert isinstance(result, LspSymbolCollection)
    assert [s.name for s in result.symbols] == ["create_user"]
    assert result.symbols[0].body.startswith("def create_user")
    assert "create_user" in result.represent()


@pytest.mark.python
@pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.PYTHON), reason="python tests are disabled in this environment")
def test_external_project_context_in_repl(
    project_server: tuple[ProjectServer, int],
    serena_config: SerenaConfig,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, port = project_server
    monkeypatch.setattr(ProjectServer, "PORT", port)  # let the REPL's external project context use the test server

    # enable the optional "ext" facade
    serena_config.included_apis = ["ext"]

    # the querying agent has another project active and queries the python test project
    agent = SerenaAgent(project="test_repo_typescript", serena_config=serena_config)
    agent.execute_task(lambda: None)
    try:
        tool = agent.get_tool(SerenaReplTool)
        session_id = agent.create_session().session_id
        code = (
            'with s.ext.read_project_context("test_repo_python"):\n'
            '    result = s.lsp.find_symbol("create_user")\n'
            "[s.name for s in result.symbols]"
        )
        assert tool.apply(session_id, code) == "create_user"
        assert server._loaded_projects_by_root, "the operation was not executed by the project server"

        # the result persists and can be used after the context; the active project is restored
        assert "services.py" in tool.apply(session_id, "result.represent()")
        assert "test_repo_typescript" in agent.get_current_config_overview()
    finally:
        agent.on_shutdown(timeout=5)
