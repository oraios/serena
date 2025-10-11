"""
The Serena Model Context Protocol (MCP) Server
"""

import sys
from abc import abstractmethod
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, cast

import docstring_parser
from fastmcp import FastMCP, Context
from fastmcp.settings import Settings
from pydantic_settings import SettingsConfigDict
from sensai.util import logging

from serena.agent import (
    SerenaAgent,
    SerenaConfig,
)
from serena.config.context_mode import SerenaAgentContext, SerenaAgentMode
from serena.constants import DEFAULT_CONTEXT, DEFAULT_MODES, SERENA_LOG_FORMAT
from serena.tools import Tool
from serena.util.exception import show_fatal_exception_safe
from serena.util.logging import MemoryLogHandler

log = logging.getLogger(__name__)


def configure_logging(*args, **kwargs) -> None:  # type: ignore
    # We only do something here if logging has not yet been configured.
    # Normally, logging is configured in the MCP server startup script.
    if not logging.is_enabled():
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format=SERENA_LOG_FORMAT)


@dataclass
class SerenaMCPRequestContext:
    agent: SerenaAgent


class SerenaMCPFactory:
    def __init__(self, context: str = DEFAULT_CONTEXT, project: str | None = None):
        """
        :param context: The context name or path to context file
        :param project: Either an absolute path to the project directory or a name of an already registered project.
            If the project passed here hasn't been registered yet, it will be registered automatically and can be activated by its name
            afterward.
        """
        self.context = SerenaAgentContext.load(context)
        self.project = project

    @staticmethod
    def _sanitize_for_openai_tools(schema: dict) -> dict:
        """
        This method was written by GPT-5, I have not reviewed it in detail.
        Only called when `openai_tool_compatible` is True.

        Make a Pydantic/JSON Schema object compatible with OpenAI tool schema.
        - 'integer' -> 'number' (+ multipleOf: 1)
        - remove 'null' from union type arrays
        - coerce integer-only enums to number
        - best-effort simplify oneOf/anyOf when they only differ by integer/number
        """
        s = deepcopy(schema)

        def walk(node):  # type: ignore
            if not isinstance(node, dict):
                # lists get handled by parent calls
                return node

            # ---- handle type ----
            t = node.get("type")
            if isinstance(t, str):
                if t == "integer":
                    node["type"] = "number"
                    # preserve existing multipleOf but ensure it's integer-like
                    if "multipleOf" not in node:
                        node["multipleOf"] = 1
            elif isinstance(t, list):
                # remove 'null' (OpenAI tools don't support nullables)
                t2 = [x if x != "integer" else "number" for x in t if x != "null"]
                if not t2:
                    # fall back to object if it somehow becomes empty
                    t2 = ["object"]
                node["type"] = t2[0] if len(t2) == 1 else t2
                if "integer" in t or "number" in t2:
                    # if integers were present, keep integer-like restriction
                    node.setdefault("multipleOf", 1)

            # ---- enums of integers -> number ----
            if "enum" in node and isinstance(node["enum"], list):
                vals = node["enum"]
                if vals and all(isinstance(v, int) for v in vals):
                    node.setdefault("type", "number")
                    # keep them as ints; JSON 'number' covers ints
                    node.setdefault("multipleOf", 1)

            # ---- simplify anyOf/oneOf if they only differ by integer/number ----
            for key in ("oneOf", "anyOf"):
                if key in node and isinstance(node[key], list):
                    # Special case: anyOf or oneOf with "type X" and "null"
                    if len(node[key]) == 2:
                        types = [sub.get("type") for sub in node[key]]
                        if "null" in types:
                            non_null_type = next(t for t in types if t != "null")
                            if isinstance(non_null_type, str):
                                node["type"] = non_null_type
                                node.pop(key, None)
                                continue
                    simplified = []
                    changed = False
                    for sub in node[key]:
                        sub = walk(sub)  # recurse
                        simplified.append(sub)
                    # If all subs are the same after integer→number, collapse
                    try:
                        import json

                        canon = [json.dumps(x, sort_keys=True) for x in simplified]
                        if len(set(canon)) == 1:
                            # copy the single schema up
                            only = simplified[0]
                            node.pop(key, None)
                            for k, v in only.items():
                                if k not in node:
                                    node[k] = v
                            changed = True
                    except Exception:
                        pass
                    if not changed:
                        node[key] = simplified

            # ---- recurse into known schema containers ----
            for child_key in ("properties", "patternProperties", "definitions", "$defs"):
                if child_key in node and isinstance(node[child_key], dict):
                    for k, v in list(node[child_key].items()):
                        node[child_key][k] = walk(v)

            # arrays/items
            if "items" in node:
                node["items"] = walk(node["items"])

            # allOf/if/then/else - pass through with integer→number conversions applied inside
            for key in ("allOf",):
                if key in node and isinstance(node[key], list):
                    node[key] = [walk(x) for x in node[key]]

            if "if" in node:
                node["if"] = walk(node["if"])
            if "then" in node:
                node["then"] = walk(node["then"])
            if "else" in node:
                node["else"] = walk(node["else"])

            return node

        return walk(s)

    @staticmethod
    def register_mcp_tool(mcp: FastMCP, tool: Tool, openai_tool_compatible: bool = True) -> None:
        """
        Register a Serena Tool with a FastMCP server using FastMCP 2.0's decorator API.

        :param mcp: The FastMCP server instance.
        :param tool: The Serena Tool instance to register.
        :param openai_tool_compatible: whether to process the tool schema to be compatible with OpenAI tools
            (doesn't accept integer, needs number instead, etc.). This allows using Serena MCP within codex.
        """
        import inspect

        func_name = tool.get_name()
        func_doc = tool.get_apply_docstring() or ""

        docstring = docstring_parser.parse(func_doc)

        # Mount the tool description as a combination of the docstring description and
        # the return value description, if it exists.
        overridden_description = tool.agent.get_context().tool_description_overrides.get(func_name, None)

        if overridden_description is not None:
            func_doc = overridden_description
        elif docstring.description:
            func_doc = docstring.description
        else:
            func_doc = ""
        func_doc = func_doc.strip().strip(".")
        if func_doc:
            func_doc += "."
        if docstring.returns and (docstring_returns_descr := docstring.returns.description):
            # Only add a space before "Returns" if func_doc is not empty
            prefix = " " if func_doc else ""
            func_doc = f"{func_doc}{prefix}Returns {docstring_returns_descr.strip().strip('.')}."

        # Get the apply method and check if it's async and needs context
        apply_method = tool.get_apply_fn()
        is_async = inspect.iscoroutinefunction(apply_method)

        # Debug: Verify the tool instance is properly initialized
        log.debug(f"Registering tool {func_name}: tool.agent={tool.agent}, bound_method.__self__={apply_method.__self__}")

        # Get the signature from the CLASS method (not the bound method) for proper introspection
        class_method = tool.__class__.apply
        class_sig = inspect.signature(class_method)

        # Build exclude_args list for FastMCP
        # We need to exclude parameters that are FastMCP dependencies (like Context)
        # FastMCP will inject these automatically but they shouldn't be exposed to clients
        exclude_args = []

        # Detect Context-annotated parameters for dependency injection
        try:
            from typing import get_type_hints, get_origin, get_args, Union
            type_hints = get_type_hints(class_method)
            for param_name, param_hint in type_hints.items():
                if param_name == 'self' or param_name == 'return':
                    continue
                # Check if the type hint is Context or a Union containing Context
                if param_hint is Context:
                    exclude_args.append(param_name)
                    log.debug(f"Tool {tool.get_name()}: excluding '{param_name}' (type: Context)")
                elif get_origin(param_hint) is Union:
                    # Check if Context is in the Union args
                    args = get_args(param_hint)
                    if Context in args:
                        exclude_args.append(param_name)
                        log.debug(f"Tool {tool.get_name()}: excluding '{param_name}' (type: Union with Context)")
        except Exception as e:
            log.warning(f"Failed to detect Context parameters for tool {tool.get_name()}: {e}")

        # Instead of using exec, use tool.apply_ex which properly handles the tool instance
        # This method is specifically designed to call tools correctly
        def sync_wrapper(**kwargs):  # type: ignore
            return tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)

        async def async_wrapper(**kwargs):  # type: ignore
            # For async tools, call apply directly since apply_ex doesn't support async
            # FastMCP will inject 'context' parameter automatically via dependency injection
            return await apply_method(**kwargs)

        # Choose the appropriate wrapper
        wrapper = async_wrapper if is_async else sync_wrapper

        # Set metadata on the wrapper
        wrapper.__name__ = func_name

        # Create a signature without 'self' for FastMCP to introspect
        params = [p for name, p in class_sig.parameters.items() if name != 'self']
        wrapper.__signature__ = inspect.Signature(parameters=params)  # type: ignore

        # Copy type annotations from the class method
        # FastMCP needs these to detect Context parameters for dependency injection
        try:
            from typing import get_type_hints
            # Get type hints with globalns from the tool's module to resolve imports
            type_hints = get_type_hints(class_method, globalns=tool.__class__.__module__.__dict__ if hasattr(tool.__class__.__module__, '__dict__') else None)
            # Remove 'self' from annotations
            wrapper.__annotations__ = {k: v for k, v in type_hints.items() if k != 'self'}
            log.debug(f"Tool {func_name} annotations: {wrapper.__annotations__}")
        except Exception as e:
            log.warning(f"Failed to copy type hints for tool {func_name}: {e}")
            # Fall back to copying raw annotations
            wrapper.__annotations__ = {k: v for k, v in class_method.__annotations__.items() if k != 'self'}

        # Register using FastMCP 2.0's decorator API
        mcp.tool(
            wrapper,
            name=func_name,
            description=func_doc,
            exclude_args=exclude_args
        )

    @abstractmethod
    def _iter_tools(self) -> Iterator[Tool]:
        pass

    def _set_mcp_tools(self, mcp: FastMCP, openai_tool_compatible: bool = False) -> None:
        """Register all Serena tools with the MCP server using FastMCP 2.0 API"""
        if mcp is not None:
            tool_names = []
            for tool in self._iter_tools():
                log.debug(f"Registering tool {tool.get_name()}: tool={tool}, tool.agent={getattr(tool, 'agent', None)}")
                self.register_mcp_tool(mcp, tool, openai_tool_compatible=openai_tool_compatible)
                tool_names.append(tool.get_name())
            log.info(f"Starting MCP server with {len(tool_names)} tools: {tool_names}")

    @abstractmethod
    def _instantiate_agent(self, serena_config: SerenaConfig, modes: list[SerenaAgentMode]) -> None:
        pass

    def create_mcp_server(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        modes: Sequence[str] = DEFAULT_MODES,
        enable_web_dashboard: bool | None = None,
        enable_gui_log_window: bool | None = None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
        trace_lsp_communication: bool | None = None,
        tool_timeout: float | None = None,
    ) -> FastMCP:
        """
        Create an MCP server with process-isolated SerenaAgent to prevent asyncio contamination.

        :param host: The host to bind to
        :param port: The port to bind to
        :param modes: List of mode names or paths to mode files
        :param enable_web_dashboard: Whether to enable the web dashboard. If not specified, will take the value from the serena configuration.
        :param enable_gui_log_window: Whether to enable the GUI log window. It currently does not work on macOS, and setting this to True will be ignored then.
            If not specified, will take the value from the serena configuration.
        :param log_level: Log level. If not specified, will take the value from the serena configuration.
        :param trace_lsp_communication: Whether to trace the communication between Serena and the language servers.
            This is useful for debugging language server issues.
        :param tool_timeout: Timeout in seconds for tool execution. If not specified, will take the value from the serena configuration.
        """
        try:
            config = SerenaConfig.from_config_file()

            # update configuration with the provided parameters
            if enable_web_dashboard is not None:
                config.web_dashboard = enable_web_dashboard
            if enable_gui_log_window is not None:
                config.gui_log_window_enabled = enable_gui_log_window
            if log_level is not None:
                log_level = cast(Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], log_level.upper())
                config.log_level = logging.getLevelNamesMapping()[log_level]
            if trace_lsp_communication is not None:
                config.trace_lsp_communication = trace_lsp_communication
            if tool_timeout is not None:
                config.tool_timeout = tool_timeout

            modes_instances = [SerenaAgentMode.load(mode) for mode in modes]
            self._instantiate_agent(config, modes_instances)

        except Exception as e:
            show_fatal_exception_safe(e)
            raise

        # Override model_config to disable the use of `.env` files for reading settings, because user projects are likely to contain
        # `.env` files (e.g. containing LOG_LEVEL) that are not supposed to override the MCP settings;
        # retain only FASTMCP_ prefix for already set environment variables.
        Settings.model_config = SettingsConfigDict(env_prefix="FASTMCP_")
        instructions = self._get_initial_instructions()
        mcp = FastMCP(lifespan=self.server_lifespan, host=host, port=port, instructions=instructions)
        return mcp

    @asynccontextmanager
    @abstractmethod
    async def server_lifespan(self, mcp_server: FastMCP) -> AsyncIterator[None]:
        """Manage server startup and shutdown lifecycle."""
        yield None  # ensures MyPy understands we yield None

    @abstractmethod
    def _get_initial_instructions(self) -> str:
        pass


class SerenaMCPFactorySingleProcess(SerenaMCPFactory):
    """
    MCP server factory where the SerenaAgent and its language server run in the same process as the MCP server
    """

    def __init__(self, context: str = DEFAULT_CONTEXT, project: str | None = None, memory_log_handler: MemoryLogHandler | None = None):
        """
        :param context: The context name or path to context file
        :param project: Either an absolute path to the project directory or a name of an already registered project.
            If the project passed here hasn't been registered yet, it will be registered automatically and can be activated by its name
            afterward.
        """
        super().__init__(context=context, project=project)
        self.agent: SerenaAgent | None = None
        self.memory_log_handler = memory_log_handler

    def _instantiate_agent(self, serena_config: SerenaConfig, modes: list[SerenaAgentMode]) -> None:
        self.agent = SerenaAgent(
            project=self.project, serena_config=serena_config, context=self.context, modes=modes, memory_log_handler=self.memory_log_handler
        )

    def _iter_tools(self) -> Iterator[Tool]:
        assert self.agent is not None
        yield from self.agent.get_exposed_tool_instances()

    def _get_initial_instructions(self) -> str:
        assert self.agent is not None
        # we don't use the tool (which at the time of writing calls this method), since the tool may be disabled by the config
        return self.agent.create_system_prompt()

    @asynccontextmanager
    async def server_lifespan(self, mcp_server: FastMCP) -> AsyncIterator[None]:
        openai_tool_compatible = self.context.name in ["chatgpt", "codex", "oaicompat-agent"]
        self._set_mcp_tools(mcp_server, openai_tool_compatible=openai_tool_compatible)
        log.info("MCP server lifetime setup complete")
        yield
