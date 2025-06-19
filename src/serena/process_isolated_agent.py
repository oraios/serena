import asyncio
import contextlib
import logging
import multiprocessing
import os
import traceback
import webbrowser
from enum import StrEnum
from logging.handlers import QueueHandler
from multiprocessing.connection import Connection
from multiprocessing.sharedctypes import Synchronized
from multiprocessing.synchronize import Event as EventClass
from typing import Any, Literal, Self

import uvicorn
from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata

from serena.agent import SerenaAgent, SerenaConfig, SerenaConfigBase, Tool, ToolInterface, ToolRegistry
from serena.config import SerenaAgentContext, SerenaAgentMode
from serena.dashboard import MemoryLogHandler, SerenaDashboardAPI

log = logging.getLogger(__name__)

# Global synchronization primitives
_global_log_queue: multiprocessing.Queue = multiprocessing.Queue()
_dashboard_ready_event = multiprocessing.Event()
_dashboard_port_value = multiprocessing.Value("i", 0)
global_shutdown_event = multiprocessing.Event()


def request_global_shutdown() -> None:
    """Signal the global shutdown event."""
    global_shutdown_event.set()
    log.info("Global shutdown event set")


def _dashboard_worker(
    tool_names: list[str],
    log_q: "multiprocessing.Queue[Any]",
    dashboard_ready_event: EventClass,
    port_value: "Synchronized[int]",
    shutdown_evt: EventClass,
) -> None:
    """Entry point for the dashboard process."""
    # Route all logging to the shared queue
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.addHandler(QueueHandler(log_q))

    async def _process_logs(api: SerenaDashboardAPI) -> None:
        while not shutdown_evt.is_set():
            while not log_q.empty():
                record = log_q.get_nowait()
                if record is None:
                    break
                api.memory_log_handler.emit(record)
            # Small delay to avoid busy waiting
            await asyncio.sleep(0.1)

    async def _monitor_shutdown() -> None:
        # Poll the multiprocessing Event in async context
        # Check every 100ms until shutdown is requested
        loop = asyncio.get_event_loop()
        while True:
            # Check in executor to avoid blocking
            result = await loop.run_in_executor(None, shutdown_evt.is_set)
            if result:
                break
            await asyncio.sleep(0.1)

    async def _async_main() -> None:
        api = SerenaDashboardAPI(
            memory_log_handler=MemoryLogHandler(),
            tool_names=tool_names,
            shutdown_callback=shutdown_evt.set,
        )
        # Pick a free port and signal readiness
        port = api._find_first_free_port(0x5EDA)
        port_value.value = port

        # Start server first, then log processing
        config = uvicorn.Config(
            app=api._app,
            host="0.0.0.0",
            port=port,
            workers=1,
            log_config=None,
            log_level="critical",
        )
        server = uvicorn.Server(config)

        # Serve and await shutdown signal
        server_task = asyncio.create_task(server.serve())
        shutdown_task = asyncio.create_task(_monitor_shutdown())
        logging_loop_task = asyncio.create_task(_process_logs(api))
        dashboard_ready_event.set()

        done, pending = await asyncio.wait(
            [server_task, shutdown_task, logging_loop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if shutdown_task in done:
            server.should_exit = True
            await server_task

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    try:
        asyncio.run(_async_main())
    except BaseException:
        logging.exception("Dashboard worker crashed")
    finally:
        logging.info("Dashboard worker exiting")


def _shutdown_process(proc: multiprocessing.Process, timeout: float = 1.0) -> None:
    """Helper to shutdown a process gracefully."""
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=timeout)
    if proc.is_alive():
        log.error("Process did not terminate gracefully, forcing kill")
        proc.kill()
        proc.join(timeout=timeout)
    if proc.is_alive():
        log.error("Process did not respond to kill")


class ProcessIsolatedDashboard:
    """Dashboard running in a separate process to avoid asyncio contamination."""

    def __init__(self, tool_names: list[str]):
        self.tool_names = tool_names
        self.process: multiprocessing.Process | None = None

    def start(self, timeout: float = 10.0) -> None:
        """Start the dashboard process."""
        if self.process is not None:
            raise RuntimeError("Dashboard already started")

        self.process = multiprocessing.Process(
            target=_dashboard_worker,
            args=(self.tool_names, _global_log_queue, _dashboard_ready_event, _dashboard_port_value, global_shutdown_event),
            daemon=True,
        )
        self.process.start()

        if not _dashboard_ready_event.wait(timeout):
            self.process.terminate()
            self.process.join(timeout=1.0)
            self.process = None
            raise RuntimeError("Dashboard failed to start within timeout")

        port = _dashboard_port_value.value
        log.info(f"Dashboard started on port {port}")
        webbrowser.open(f"http://localhost:{port}/dashboard/index.html")

    def stop(self, timeout: float = 1.0) -> None:
        """Signal shutdown and wait for the dashboard process to exit."""
        if self.process is None:
            return

        log.info("Stopping dashboard process")
        request_global_shutdown()
        _shutdown_process(self.process, timeout=timeout)
        self.process = None


class SerenaAgentWorker:
    """Worker process that hosts the actual SerenaAgent."""

    class RequestMethod(StrEnum):
        INITIALIZE = "initialize"
        TOOL_CALL = "tool_call"
        GET_ACTIVE_TOOL_NAMES = "get_active_tool_names"
        IS_LANGUAGE_SERVER_RUNNING = "is_language_server_running"
        RESET_LANGUAGE_SERVER = "reset_language_server"
        GET_EXPOSED_TOOL_NAMES = "get_exposed_tool_names"
        SHUTDOWN = "shutdown"

    def __init__(self, conn: Connection):
        self.conn = conn
        self.agent: SerenaAgent | None = None

    def run(self, log_queue: "multiprocessing.Queue[str]") -> None:
        """Main worker loop - runs in separate process."""
        qh = QueueHandler(log_queue)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        root.addHandler(qh)

        log.info("SerenaAgent worker process started")
        try:
            while not global_shutdown_event.is_set():
                try:
                    # Use polling to avoid blocking indefinitely
                    if self.conn.poll(timeout=0.5):  # Poll every 500ms
                        try:
                            request = self.conn.recv()
                            if request is None:  # Explicit shutdown signal
                                break

                            response = self._handle_request(request)
                            self.conn.send(response)
                        except EOFError:
                            # Connection closed - parent process terminated
                            log.info("Connection closed, worker shutting down")
                            break
                        except (BrokenPipeError, ConnectionResetError):
                            # Connection broken, can't communicate
                            log.info("Connection broken, worker shutting down")
                            break
                        except Exception as e:
                            log.error(f"Error processing request: {e}")
                            try:
                                response = {
                                    "error": f"Worker process error: {e!s}",
                                    "traceback": traceback.format_exc(),
                                }
                                self.conn.send(response)
                            except (EOFError, BrokenPipeError, ConnectionResetError):
                                # Connection is broken, can't send error response
                                log.info("Connection broken during error response, shutting down")
                                break
                    # Continue polling if no data available

                except Exception as e:
                    log.error(f"Error in worker main loop: {e}")
                    break
        except Exception as e:
            log.error(f"Fatal error in worker process: {e}")
        finally:
            self._cleanup()
            log.info("SerenaAgent worker process stopped")
            os._exit(0)  # Exit without raising any further exceptions

    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a single request."""
        try:
            method = request["method"]
            params = request.get("params", {})

            match method:
                case self.RequestMethod.INITIALIZE:
                    return self._initialize(params)
                case self.RequestMethod.TOOL_CALL:
                    return self._tool_call(params)
                case self.RequestMethod.GET_ACTIVE_TOOL_NAMES:
                    return self._get_active_tool_names()
                case self.RequestMethod.IS_LANGUAGE_SERVER_RUNNING:
                    return self._is_language_server_running()
                case self.RequestMethod.RESET_LANGUAGE_SERVER:
                    return self._reset_language_server()
                case self.RequestMethod.GET_EXPOSED_TOOL_NAMES:
                    return self._get_exposed_tool_names()
                case self.RequestMethod.SHUTDOWN:
                    return self.shutdown()
                case _:
                    return {"error": f"Unknown method: {method}"}
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Initialize the SerenaAgent."""
        if self.agent is not None:
            return {"result": "SerenaAgent already initialized"}
        try:
            # Extract all possible initialization parameters
            context_param = params.get("context")
            project = params.get("project")
            serena_config = SerenaConfig.from_json_dict(params["serena_config"])
            context = SerenaAgentContext.from_json_dict(context_param) if context_param is not None else None
            modes = [SerenaAgentMode.from_json_dict(m) for m in params["modes"]]
            log_level = params.get("log_level")
            trace_lsp_communication = params.get("trace_lsp_communication")
            tool_timeout = params.get("tool_timeout")
            serena_config_dir = params.get("serena_config_dir")

            self.agent = SerenaAgent(
                project=project,
                serena_config=serena_config,
                context=context,
                modes=modes,
                enable_web_dashboard=False,
                enable_gui_log_window=False,
                log_level=log_level,
                trace_lsp_communication=trace_lsp_communication,
                tool_timeout=tool_timeout,
                serena_config_dir=serena_config_dir,
            )
            return {"result": "SerenaAgent initialized successfully"}
        except Exception as e:
            return {"error": f"Failed to initialize SerenaAgent: {e!s}", "traceback": traceback.format_exc()}

    def _tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call."""
        if self.agent is None:
            return {"error": "SerenaAgent not initialized"}

        try:
            tool_name = params["tool_name"]
            tool_params = params["tool_params"]

            # Get the tool by name
            tool = None
            for tool_instance in self.agent._active_tools.values():
                if tool_instance.get_name_from_cls() == tool_name:
                    tool = tool_instance
                    break

            if tool is None:
                return {"error": f"Tool '{tool_name}' not found or not active"}

            # Execute the tool
            result = tool.apply_ex(**tool_params)

            return {"result": result}

        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def _get_active_tool_names(self) -> dict[str, Any]:
        """Get list of active tool names."""
        if self.agent is None:
            return {"error": "SerenaAgent not initialized"}

        try:
            tool_names = self.agent.get_active_tool_names()
            return {"result": tool_names}
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def _is_language_server_running(self) -> dict[str, Any]:
        """Check if language server is running."""
        if self.agent is None:
            return {"error": "SerenaAgent not initialized"}

        try:
            is_running = self.agent.is_language_server_running()
            return {"result": is_running}
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def _reset_language_server(self) -> dict[str, Any]:
        """Reset the language server."""
        if self.agent is None:
            return {"error": "SerenaAgent not initialized"}

        try:
            self.agent.reset_language_server()
            return {"result": "Language server reset successfully"}
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def _get_exposed_tool_names(self) -> dict[str, Any]:
        """Get exposed tool names for MCP tool creation."""
        if self.agent is None:
            return {"error": "SerenaAgent not initialized"}

        try:
            tool_instances = self.agent.get_exposed_tool_instances()
            # Return only tool names - metadata will be reconstructed from ToolRegistry
            tool_names = [tool.get_name_from_cls() for tool in tool_instances]
            return {"result": tool_names}
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}

    def shutdown(self) -> dict[str, Any]:
        try:
            log.info("Shutting down SerenaAgent worker process on request")
            self._cleanup()
            request_global_shutdown()
            # Return successful response before exiting
            return {"result": "Shutdown initiated"}
        except Exception as e:
            log.error(f"Error during shutdown: {e}")
            return {"error": str(e), "traceback": traceback.format_exc()}

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self.agent is not None:
            try:
                if self.agent.is_language_server_running() and self.agent.language_server is not None:
                    self.agent.language_server.stop()
            except Exception as e:
                log.error(f"Error stopping language server: {e}")
            self.agent = None


class ProcessIsolatedSerenaAgent:
    """Process-isolated wrapper for SerenaAgent that prevents asyncio contamination."""

    def __init__(
        self,
        project: str | None = None,
        serena_config: SerenaConfigBase | None = None,
        context: SerenaAgentContext | None = None,
        modes: list[SerenaAgentMode] | None = None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
        trace_lsp_communication: bool | None = None,
        tool_timeout: float | None = None,
        serena_config_dir: str | None = None,
    ):
        self.project = project
        self.serena_config = serena_config or SerenaConfig.from_config_file()
        self.context = context
        self.modes = modes or []
        self.log_level = log_level
        self.trace_lsp_communication = trace_lsp_communication
        self.tool_timeout = tool_timeout
        self.serena_config_dir = serena_config_dir

        self.process: multiprocessing.Process | None = None
        self.conn: Connection | None = None

    def start(self) -> None:
        """Start the worker process."""
        if self.process is not None:
            raise RuntimeError("ProcessIsolatedSerenaAgent already started")

        log.info("Starting process-isolated SerenaAgent")

        # Create communication pipe
        parent_conn, child_conn = multiprocessing.Pipe()
        self.conn = parent_conn

        # Create and start worker process, passing along the dashboard's queue if available
        worker = SerenaAgentWorker(child_conn)
        self.process = multiprocessing.Process(target=worker.run, args=[_global_log_queue])
        self.process.start()

        # Prepare initialization parameters, converting complex objects to dict if present
        init_params = {
            "project": self.project,
            "serena_config": self.serena_config.to_json_dict(),
            "context": self.context.to_json_dict() if self.context is not None else None,
            "modes": [m.to_json_dict() for m in self.modes],
            "log_level": self.log_level,
            "trace_lsp_communication": self.trace_lsp_communication,
            "tool_timeout": self.tool_timeout,
            "serena_config_dir": self.serena_config_dir,
        }
        # Initialize the agent in the worker process
        try:
            self._make_request_with_result(SerenaAgentWorker.RequestMethod.INITIALIZE, init_params)
        except Exception as e:
            self.stop()
            raise RuntimeError(f"Failed to initialize SerenaAgent: {e}") from e

        log.info("Process-isolated SerenaAgent started successfully")

    def stop(self) -> None:
        """Stop the worker process."""
        if self.process is None:
            return
        log.info("Stopping SerenaAgent process")
        try:
            # Close connection to signal worker to shutdown
            if self.conn is not None:
                self.conn.close()
            _shutdown_process(self.process, timeout=2.0)
            self.process = None
        except KeyboardInterrupt:
            log.warning("Keyboard interrupt during shutdown - forcing termination")
            if self.process and self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=1.0)
        except Exception as e:
            log.error(f"Error stopping worker process: {e}")
        finally:
            self.process = None
            self.conn = None

        log.info("SerenaAgent stopped")

    def _make_request(self, method: SerenaAgentWorker.RequestMethod, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a request to the worker process."""
        if self.process is None or not self.process.is_alive():
            raise RuntimeError("Worker process is not running")

        if self.conn is None:
            raise RuntimeError("Connection is not initialized")

        request = {"method": method, "params": params or {}}

        # Send request
        try:
            self.conn.send(request)
        except (EOFError, BrokenPipeError) as e:
            raise RuntimeError("Failed to send request: worker process may have crashed") from e

        # Wait for response with timeout
        timeout = self.serena_config.tool_timeout
        if self.conn.poll(timeout):
            try:
                return self.conn.recv()
            except (EOFError, BrokenPipeError) as e:
                raise RuntimeError("Failed to receive response: worker process may have crashed") from e
        else:
            raise TimeoutError(f"Request {method} timed out after {timeout} seconds")

    def _make_request_with_result(self, method: SerenaAgentWorker.RequestMethod, params: dict[str, Any] | None = None) -> Any:
        """Make a request and return the result, raising an exception if there's an error."""
        response = self._make_request(method, params)
        if "error" in response:
            raise RuntimeError(f"Request {method} failed: {response['error']}")
        return response["result"]

    def tool_call(self, tool_name: str, **tool_params: Any) -> str:
        """Call a tool in the worker process."""
        return self._make_request_with_result(
            SerenaAgentWorker.RequestMethod.TOOL_CALL, {"tool_name": tool_name, "tool_params": tool_params}
        )

    def get_tool(self, tool_cls: type[Tool]) -> "ProcessIsolatedTool":
        """Get a process-isolated tool that delegates to this agent."""
        tool_name = tool_cls.get_name_from_cls()
        return ProcessIsolatedTool(self, tool_name)

    def get_active_tool_names(self) -> list[str]:
        """Get list of active tool names."""
        return self._make_request_with_result(SerenaAgentWorker.RequestMethod.GET_ACTIVE_TOOL_NAMES)

    def is_language_server_running(self) -> bool:
        """Check if language server is running."""
        return self._make_request_with_result(SerenaAgentWorker.RequestMethod.IS_LANGUAGE_SERVER_RUNNING)

    def reset_language_server(self) -> None:
        """Reset the language server."""
        self._make_request_with_result(SerenaAgentWorker.RequestMethod.RESET_LANGUAGE_SERVER)

    def shutdown_from_dashboard(self) -> None:
        """Request shutdown from dashboard."""
        self._make_request_with_result(SerenaAgentWorker.RequestMethod.SHUTDOWN)

    def get_exposed_tool_names(self) -> list[str]:
        """Get tool names for MCP tool creation."""
        return self._make_request_with_result(SerenaAgentWorker.RequestMethod.GET_EXPOSED_TOOL_NAMES)

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


class ProcessIsolatedTool(ToolInterface):
    """A clean tool wrapper that delegates to ProcessIsolatedSerenaAgent."""

    def __init__(self, process_agent: ProcessIsolatedSerenaAgent, tool_name: str):
        self.process_agent = process_agent
        self._tool_name = tool_name

    @property
    def _tool_class(self) -> type[Tool]:
        return ToolRegistry.get_tool_class_by_name(self._tool_name)

    def get_name(self) -> str:
        """Get the tool name for this process-isolated tool."""
        return self._tool_name

    def get_apply_docstring(self) -> str:
        """Get the docstring for the apply method."""
        # in the actual tool, this is a classmethod
        return self._tool_class.get_apply_docstring_from_cls()

    def get_apply_fn_metadata(self) -> FuncMetadata:
        """Get the metadata for the apply method."""
        # in the actual tool, this is a classmethod
        return self._tool_class.get_apply_fn_metadata_from_cls()

    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, **kwargs: Any) -> str:
        """Apply the tool with logging and exception handling."""
        try:
            return self.process_agent.tool_call(self._tool_name, **kwargs)
        except Exception as e:
            if catch_exceptions:
                return f"Error executing tool {self._tool_name}: {e!s}"
            raise
