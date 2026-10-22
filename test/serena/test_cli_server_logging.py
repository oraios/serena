"""Regression tests for logging during HTTP server startup."""

import logging
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import uvicorn
from click.testing import CliRunner
from mcp.server.mcpserver import MCPServer

from serena.cli import TopLevelCommands
from serena.config.serena_config import SerenaPaths
from serena.util.logging import MemoryLogHandler


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
@pytest.mark.parametrize("fail", [False, True])
def test_http_startup_preserves_dashboard_logging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, transport: str, fail: bool) -> None:
    # isolate agent construction while retaining HTTP server logging configuration
    factory = MagicMock()
    factory.return_value.create_mcp_server.return_value = MCPServer("test")
    monkeypatch.setattr("serena.mcp.SerenaMCPFactory", factory)
    monkeypatch.setattr(SerenaPaths(), "get_next_log_file_path", lambda prefix: str(tmp_path / "server.log"))
    loggers = [logging.getLogger(name) for name in ("uvicorn.error", "uvicorn.access", "uvicorn.asgi")]
    for logger in loggers:
        monkeypatch.setattr(logger, "level", logging.ERROR)

    async def serve(server: uvicorn.Server, sockets=None) -> None:
        assert all(logger.level == logging.ERROR for logger in loggers)
        assert server.config.host == "127.0.0.2"
        assert server.config.port == 8123

        # capture a message emitted after Uvicorn has configured logging
        handler: MemoryLogHandler = factory.call_args.kwargs["memory_log_handler"]
        received = threading.Event()
        message = "message after HTTP startup"
        handler.add_emit_callback(lambda text: received.set() if text.endswith(message) else None)
        logging.getLogger(__name__).warning(message)
        assert received.wait(timeout=2)
        assert handler.get_log_messages().messages[-1].endswith(message)
        if fail:
            raise RuntimeError("server failed")
        server.started = True

    monkeypatch.setattr(uvicorn.Server, "serve", serve)
    result = CliRunner().invoke(TopLevelCommands.start_mcp_server, ["--transport", transport, "--host", "127.0.0.2", "--port", "8123"])
    if fail:
        assert isinstance(result.exception, RuntimeError)
        assert str(result.exception) == "server failed"
    else:
        assert result.exit_code == 0, result.exception

    # verify subsequent Uvicorn configurations can set their own logging levels
    uvicorn.Config("test:app", log_config=None, log_level="debug")
    assert all(logger.level == logging.DEBUG for logger in loggers)
