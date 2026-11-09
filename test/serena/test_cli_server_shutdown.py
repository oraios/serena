"""Regression tests for agent shutdown when the MCP server stops.

Under the SSE and streamable-HTTP transports the server lifespan runs once per
connection, so it cannot shut the agent down; the CLI has to do that once the
server loop has ended, or language servers are left running and symbol caches
are never saved.
"""

import signal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import uvicorn
from click.testing import CliRunner
from mcp.server.mcpserver import MCPServer

from serena.cli import TopLevelCommands, agent_shutdown_on_signal
from serena.config.serena_config import SerenaPaths
from serena.mcp import SerenaMCPFactory


def test_shutdown_agent_calls_on_shutdown_once() -> None:
    factory = SerenaMCPFactory(transport="streamable-http")
    agent = MagicMock()
    factory.agent = agent

    factory.shutdown_agent()
    factory.shutdown_agent()

    agent.on_shutdown.assert_called_once()
    assert factory.agent is None


def test_shutdown_agent_without_agent_is_a_noop() -> None:
    factory = SerenaMCPFactory(transport="streamable-http")
    factory.shutdown_agent()


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
@pytest.mark.parametrize("fail", [False, True])
def test_http_server_shuts_agent_down_when_the_loop_ends(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, transport: str, fail: bool
) -> None:
    factory = MagicMock()
    factory.return_value.create_mcp_server.return_value = MCPServer("test")
    monkeypatch.setattr("serena.mcp.SerenaMCPFactory", factory)
    monkeypatch.setattr(SerenaPaths(), "get_next_log_file_path", lambda prefix: str(tmp_path / "server.log"))

    async def serve(server: uvicorn.Server, sockets=None) -> None:
        # the agent must still be up while the server serves
        factory.return_value.shutdown_agent.assert_not_called()
        if fail:
            raise RuntimeError("server failed")
        server.started = True

    monkeypatch.setattr(uvicorn.Server, "serve", serve)

    result = CliRunner().invoke(TopLevelCommands.start_mcp_server, ["--transport", transport, "--host", "127.0.0.2", "--port", "8123"])

    if fail:
        assert isinstance(result.exception, RuntimeError)
    else:
        assert result.exit_code == 0, result.exception
    factory.return_value.shutdown_agent.assert_called_once()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_agent_shutdown_on_signal_shuts_down_then_re_raises_with_the_default_handler(
    monkeypatch: pytest.MonkeyPatch, sig: signal.Signals
) -> None:
    # uvicorn restores the handlers it found and re-raises a captured SIGINT/SIGTERM once its
    # loop has ended, so the handler installed around `server.run` is what runs last.
    factory = MagicMock()
    raised: list[tuple[signal.Signals, object]] = []
    monkeypatch.setattr(signal, "raise_signal", lambda s: raised.append((s, signal.getsignal(s))))
    before = signal.getsignal(sig)

    with agent_shutdown_on_signal(factory):
        handler = signal.getsignal(sig)
        assert handler is not before
        assert handler is not None and not isinstance(handler, int)
        handler(sig, None)

    factory.shutdown_agent.assert_called_once()
    assert raised == [(sig, signal.SIG_DFL)]
    assert signal.getsignal(sig) is before
