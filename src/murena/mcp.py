"""
The Murena Model Context Protocol (MCP) Server
"""

import re
import sys
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import docstring_parser
from mcp.server.fastmcp import server
from mcp.server.fastmcp.server import FastMCP, Settings
from mcp.server.fastmcp.tools.base import Tool as MCPTool
from mcp.types import ToolAnnotations
from pydantic_settings import SettingsConfigDict
from sensai.util import logging

from murena.agent import (
    MurenaAgent,
    MurenaConfig,
)
from murena.config.context_mode import MurenaAgentContext, MurenaAgentMode
from murena.config.murena_config import LanguageBackend
from murena.constants import DEFAULT_CONTEXT, DEFAULT_MODES, MURENA_LOG_FORMAT
from murena.tools import Tool
from murena.util.exception import show_fatal_exception_safe
from murena.util.logging import MemoryLogHandler

log = logging.getLogger(__name__)


def configure_logging(*args, **kwargs) -> None:  # type: ignore
    # We only do something here if logging has not yet been configured.
    # Normally, logging is configured in the MCP server startup script.
    if not logging.is_enabled():
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format=MURENA_LOG_FORMAT)


# patch the logging configuration function in fastmcp, because it's hard-coded and broken
server.configure_logging = configure_logging  # type: ignore


@dataclass
class MurenaMCPRequestContext:
    agent: MurenaAgent


class MurenaMCPFactory:
    """
    Factory for the creation of the Murena MCP server with an associated MurenaAgent(s).
    Supports both single-project and multi-project (grouped) configurations.
    """

    def __init__(
        self,
        context: str = DEFAULT_CONTEXT,
        project: str | None = None,
        projects: list[str] | None = None,
        primary_project: str | None = None,
        server_name: str = "murena",
        memory_log_handler: MemoryLogHandler | None = None,
    ):
        """
        :param context: The context name or path to context file
        :param project: [DEPRECATED] Use projects instead. Single project path.
        :param projects: List of project paths for grouped server configuration.
        :param primary_project: The initial active project (first in list if not specified).
        :param server_name: Name for this MCP server (used for namespacing in grouped mode).
        :param memory_log_handler: the in-memory log handler to use for the agent's logging
        """
        self.context = MurenaAgentContext.load(context)
        self.server_name = server_name
        self.memory_log_handler = memory_log_handler

        # Handle both legacy (single project) and new (multiple projects) modes
        if projects:
            self.projects = projects
            self.primary_project = primary_project or (projects[0] if projects else None)
        elif project:
            self.projects = [project]
            self.primary_project = project
        else:
            self.projects = []
            self.primary_project = None

        # Single agent for backward compatibility (used in single-project mode)
        self.agent: MurenaAgent | None = None
        # Multiple agents for grouped mode (one per project)
        self.agents_by_project: dict[str, MurenaAgent] = {}

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
    def make_mcp_tool(tool: Tool, openai_tool_compatible: bool = True, compact_mode: bool = False) -> MCPTool:
        """
        Create an MCP tool from a Murena Tool instance.

        :param tool: The Murena Tool instance to convert.
        :param openai_tool_compatible: whether to process the tool schema to be compatible with OpenAI tools
            (doesn't accept integer, needs number instead, etc.). This allows using Murena MCP within codex.
        :param compact_mode: whether to compress descriptions to reduce token consumption.
        """
        func_name = tool.get_name()
        func_doc = tool.get_apply_docstring() or ""
        func_arg_metadata = tool.get_apply_fn_metadata()
        is_async = False
        parameters = func_arg_metadata.arg_model.model_json_schema()

        # Apply schema optimizations
        if compact_mode:
            parameters = MurenaMCPFactory._strip_schema_metadata(parameters)

        if openai_tool_compatible:
            parameters = MurenaMCPFactory._sanitize_for_openai_tools(parameters)

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

        # Apply compression if enabled
        if compact_mode and not overridden_description:
            func_doc = MurenaMCPFactory._compress_docstring(func_doc)

        # Parse the parameter descriptions from the docstring and add pass its description
        # to the parameter schema.
        docstring_params = {param.arg_name: param for param in docstring.params}
        parameters_properties: dict[str, dict[str, Any]] = parameters["properties"]
        for parameter, properties in parameters_properties.items():
            if (param_doc := docstring_params.get(parameter)) and param_doc.description:
                param_desc = f"{param_doc.description.strip().strip('.') + '.'}"
                if compact_mode:
                    param_desc = MurenaMCPFactory._compress_param_description(param_desc)
                properties["description"] = param_desc[0].upper() + param_desc[1:]

        def execute_fn(**kwargs) -> str:  # type: ignore
            return tool.apply_ex(log_call=True, catch_exceptions=True, **kwargs)

        # Generate human-readable title from snake_case tool name
        tool_title = " ".join(word.capitalize() for word in func_name.split("_"))

        # Create annotations with appropriate hints based on tool capabilities
        can_edit = tool.can_edit()
        annotations = ToolAnnotations(
            title=tool_title,
            readOnlyHint=not can_edit,
            destructiveHint=can_edit,
        )

        return MCPTool(
            fn=execute_fn,
            name=func_name,
            description=func_doc,
            parameters=parameters,
            fn_metadata=func_arg_metadata,
            is_async=is_async,
            # keep the value in sync with the kwarg name in Tool.apply_ex. The mcp sdk uses reflection to infer this
            # when the tool is constructed via from_function (which is a bit crazy IMO, but well...)
            context_kwarg="mcp_ctx",
            annotations=annotations,
            title=tool_title,
        )

    def make_batch_execution_tool(self, agent: MurenaAgent, compact_mode: bool = False) -> MCPTool:
        """
        Create an MCP tool for batch parallel execution of multiple tools.

        This tool enables Claude to execute multiple independent tools in parallel,
        significantly improving performance for multi-tool operations.

        :param agent: The MurenaAgent instance to use for tool execution
        :param compact_mode: Whether to use compact descriptions
        :return: An MCPTool for batch execution
        """
        from pydantic import BaseModel

        class ToolCallSpec(BaseModel):
            """Specification for a single tool call in a batch."""

            tool_name: str
            params: dict[str, Any]

        def execute_batch(**kwargs) -> str:  # type: ignore
            """Execute multiple tools in parallel with automatic dependency analysis."""
            tool_calls_raw = kwargs.get("tool_calls", [])
            # Convert to dicts if they're pydantic models
            tool_calls = [tc if isinstance(tc, dict) else tc.model_dump() for tc in tool_calls_raw]

            if not tool_calls:
                return "[]"

            # Extract tool names and parameters
            tool_names = [call["tool_name"] for call in tool_calls]
            tool_params = [call["params"] for call in tool_calls]

            # Check if parallel execution is enabled
            performance_config = agent.murena_config.performance
            enabled = performance_config.parallel_tool_execution if performance_config else False

            # Execute tools in parallel (or sequentially if disabled)
            results = agent.execute_tools_parallel(
                tool_names=tool_names,
                tool_params=tool_params,
                enabled=enabled,
            )

            # Return results as JSON
            import json
            return json.dumps(results, indent=2)

        # Create parameter schema for batch execution
        parameters = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "tool_calls": {
                    "type": "array",
                    "description": "List of tool calls to execute in parallel. Each call specifies a tool_name and params.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool_name": {
                                "type": "string",
                                "description": "Name of the tool to execute",
                            },
                            "params": {
                                "type": "object",
                                "description": "Parameters to pass to the tool",
                            },
                        },
                        "required": ["tool_name", "params"],
                    },
                },
            },
            "required": ["tool_calls"],
        }

        description = """Execute multiple tools in parallel with automatic dependency analysis.

This tool enables batch execution of multiple independent tools, significantly improving
performance for multi-tool operations. The system automatically:
- Analyzes read-after-write dependencies between tools
- Executes independent tools in parallel waves
- Respects file access patterns to prevent race conditions
- Returns results in the same order as inputs

Example usage:
{
  "tool_calls": [
    {"tool_name": "read_file", "params": {"relative_path": "file1.py"}},
    {"tool_name": "read_file", "params": {"relative_path": "file2.py"}},
    {"tool_name": "find_symbol", "params": {"name_path_pattern": "MyClass"}}
  ]
}

Performance impact: 40-70% reduction in multi-tool operation time."""

        if compact_mode:
            description = "Execute multiple tools in parallel. Automatically analyzes dependencies and executes in waves. Returns results in input order."

        annotations = ToolAnnotations(
            title="Batch Execute Tools",
            readOnlyHint=False,  # Can execute write operations
            destructiveHint=False,  # Not inherently destructive
        )

        # Create FuncMetadata using pydantic's create_model
        from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase, FuncMetadata
        from pydantic import Field

        # Create arg model from tool_calls parameter
        # Use pydantic.create_model to create the arg model dynamically
        class BatchExecuteArgs(ArgModelBase):
            tool_calls: list[ToolCallSpec] = Field(
                ..., description="List of tool calls to execute in parallel"
            )

        fn_metadata = FuncMetadata(
            arg_model=BatchExecuteArgs,
            output_schema=None,
            output_model=None,
            wrap_output=False,
        )

        return MCPTool(
            fn=execute_batch,
            name="batch_execute_tools",
            description=description,
            parameters=parameters,
            fn_metadata=fn_metadata,
            is_async=False,
            context_kwarg="mcp_ctx",
            annotations=annotations,
            title="Batch Execute Tools",
        )

    @staticmethod
    def _compress_docstring(doc: str) -> str:
        """
        Compress docstring by removing examples and verbose explanations.

        :param doc: The docstring to compress.
        :return: Compressed docstring.
        """
        # Split into sentences
        sentences = doc.split(". ")

        # Keep first 2 sentences (core description)
        # Remove common verbose patterns
        compressed = []
        for i, sentence in enumerate(sentences):
            # Skip examples, notes, and other verbose patterns
            if any(
                skip in sentence.lower()
                for skip in [
                    "example:",
                    "note:",
                    "important:",
                    "for instance",
                    "for example",
                    "e.g.",
                    "i.e.",
                ]
            ):
                continue
            compressed.append(sentence)
            # Keep max 2 sentences
            if len(compressed) >= 2:
                break

        result = ". ".join(compressed)
        if not result.endswith("."):
            result += "."

        return result

    @staticmethod
    def _compress_param_description(desc: str) -> str:
        """
        Compress parameter description to essentials.

        :param desc: The parameter description to compress.
        :return: Compressed parameter description.
        """
        # Remove parenthetical explanations
        desc = re.sub(r"\([^)]+\)", "", desc)

        # Keep only first sentence
        first_sentence = desc.split(". ")[0]
        if not first_sentence.endswith("."):
            first_sentence += "."

        return first_sentence

    @staticmethod
    def _strip_schema_metadata(schema: dict) -> dict:
        """
        Remove unnecessary JSON Schema metadata to reduce tokens.

        :param schema: The JSON Schema to strip.
        :return: Stripped JSON Schema.
        """
        # Remove top-level metadata
        schema.pop("$schema", None)
        schema.pop("title", None)
        schema.pop("additionalProperties", None)

        # For each property, remove verbose metadata
        if "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                if isinstance(prop_schema, dict):
                    # Keep only essential fields: type, description, enum, items, properties, required
                    essential = {}
                    for key in ["type", "description", "enum", "items", "properties", "required", "default"]:
                        if key in prop_schema:
                            essential[key] = prop_schema[key]

                    # Recursively strip nested schemas
                    if "items" in essential and isinstance(essential["items"], dict):
                        essential["items"] = MurenaMCPFactory._strip_schema_metadata(essential["items"])

                    if "properties" in essential:
                        essential["properties"] = {
                            k: MurenaMCPFactory._strip_schema_metadata(v) if isinstance(v, dict) else v
                            for k, v in essential["properties"].items()
                        }

                    schema["properties"][prop_name] = essential

        return schema

    def _iter_tools(self) -> Iterator[tuple[str, Tool, str]]:
        """
        Iterate over all tools with their project context.

        Yields tuples of (project_path, tool, project_name) for each tool from each agent.
        """
        for project_path, agent in self.agents_by_project.items():
            project_name = Path(project_path).name
            for tool in agent.get_exposed_tool_instances():
                yield (project_path, tool, project_name)

    # noinspection PyProtectedMember
    def _set_mcp_tools(self, mcp: FastMCP, openai_tool_compatible: bool = False) -> None:
        """Update the tools in the MCP server"""
        if mcp is not None:
            mcp._tool_manager._tools = {}

            # Get compact mode setting from context
            compact_mode = self.context.compact_descriptions

            # Handle both single-project and multi-project modes
            if len(self.agents_by_project) == 1:
                # Single-project mode: use simple tool names (backward compatible)
                for project_path, tool, _ in self._iter_tools():
                    mcp_tool = self.make_mcp_tool(tool, openai_tool_compatible=openai_tool_compatible, compact_mode=compact_mode)
                    mcp._tool_manager._tools[tool.get_name()] = mcp_tool
            else:
                # Multi-project mode: use namespaced tool names
                for project_path, tool, project_name in self._iter_tools():
                    # Create namespaced tool name: {server_name}__{project_name}__{tool_name}
                    namespaced_name = f"{self.server_name}__{project_name}__{tool.get_name()}"
                    mcp_tool = self.make_mcp_tool(tool, openai_tool_compatible=openai_tool_compatible, compact_mode=compact_mode)

                    # Wrap the tool to activate project before execution
                    original_fn = mcp_tool.fn

                    def make_wrapper(proj_path: str, orig_fn, agent):  # type: ignore
                        """Create a wrapper that activates the project before executing the tool."""

                        def wrapped_fn(**kwargs) -> str:  # type: ignore
                            # Activate the project on the agent
                            agent.activate_project_from_path_or_name(proj_path)
                            # Execute the original tool
                            return orig_fn(**kwargs)

                        return wrapped_fn

                    mcp_tool.fn = make_wrapper(project_path, original_fn, self.agents_by_project[project_path])
                    mcp._tool_manager._tools[namespaced_name] = mcp_tool

            # Add batch execution tool for parallel tool execution
            # Safe to use in async context now - execute_tools_parallel() is async-aware
            # In single-project mode, add one batch tool
            # In multi-project mode, add batch tool for each project
            if len(self.agents_by_project) == 1:
                # Single-project mode: add one batch execution tool
                agent = next(iter(self.agents_by_project.values()))
                batch_tool = self.make_batch_execution_tool(agent, compact_mode=compact_mode)
                mcp._tool_manager._tools["batch_execute_tools"] = batch_tool
            else:
                # Multi-project mode: add batch execution tool for each project
                for project_path, agent in self.agents_by_project.items():
                    project_name = Path(project_path).name
                    batch_tool_name = f"{self.server_name}__{project_name}__batch_execute_tools"
                    batch_tool = self.make_batch_execution_tool(agent, compact_mode=compact_mode)

                    # Wrap to activate project before execution
                    original_batch_fn = batch_tool.fn

                    def make_batch_wrapper(proj_path: str, orig_fn, proj_agent):  # type: ignore
                        """Create a wrapper that activates the project before batch execution."""

                        def wrapped_batch_fn(**kwargs) -> str:  # type: ignore
                            # Activate the project on the agent
                            proj_agent.activate_project_from_path_or_name(proj_path)
                            # Execute the batch
                            return orig_fn(**kwargs)

                        return wrapped_batch_fn

                    batch_tool.fn = make_batch_wrapper(project_path, original_batch_fn, agent)
                    mcp._tool_manager._tools[batch_tool_name] = batch_tool

            log.info(f"Starting MCP server with {len(mcp._tool_manager._tools)} tools: {list(mcp._tool_manager._tools.keys())}")

    def _create_serena_agent(self, murena_config: MurenaConfig, modes: list[MurenaAgentMode], project: str | None = None) -> MurenaAgent:
        """Create a single MurenaAgent for a specific project."""
        return MurenaAgent(
            project=project, murena_config=murena_config, context=self.context, modes=modes, memory_log_handler=self.memory_log_handler
        )

    def _create_all_agents(self, murena_config: MurenaConfig, modes: list[MurenaAgentMode]) -> None:
        """Create agents for all registered projects."""
        for project_path in self.projects:
            agent = self._create_serena_agent(murena_config, modes, project=project_path)
            self.agents_by_project[project_path] = agent

            # Set primary agent for backward compatibility
            if project_path == self.primary_project:
                self.agent = agent

        if not self.agent and self.agents_by_project:
            # Fallback: use first agent if no primary was set
            self.agent = next(iter(self.agents_by_project.values()))

    def _create_default_murena_config(self) -> MurenaConfig:
        return MurenaConfig.from_config_file()

    def create_mcp_server(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        modes: Sequence[str] = DEFAULT_MODES,
        language_backend: LanguageBackend | None = None,
        enable_web_dashboard: bool | None = None,
        enable_gui_log_window: bool | None = None,
        open_web_dashboard: bool | None = None,
        web_dashboard_port: int | None = None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
        trace_lsp_communication: bool | None = None,
        tool_timeout: float | None = None,
    ) -> FastMCP:
        """
        Create an MCP server with process-isolated MurenaAgent to prevent asyncio contamination.

        :param host: The host to bind to
        :param port: The port to bind to
        :param modes: List of mode names or paths to mode files
        :param language_backend: the language backend to use, overriding the configuration setting.
        :param enable_web_dashboard: Whether to enable the web dashboard. If not specified, will take the value from the murena configuration.
        :param enable_gui_log_window: Whether to enable the GUI log window. It currently does not work on macOS, and setting this to True will be ignored then.
            If not specified, will take the value from the murena configuration.
        :param open_web_dashboard: Whether to open the web dashboard on launch.
            If not specified, will take the value from the murena configuration.
        :param log_level: Log level. If not specified, will take the value from the murena configuration.
        :param trace_lsp_communication: Whether to trace the communication between Murena and the language servers.
            This is useful for debugging language server issues.
        :param tool_timeout: Timeout in seconds for tool execution. If not specified, will take the value from the murena configuration.
        """
        try:
            config = self._create_default_murena_config()

            # update configuration with the provided parameters
            if enable_web_dashboard is not None:
                config.web_dashboard = enable_web_dashboard
            if enable_gui_log_window is not None:
                config.gui_log_window = enable_gui_log_window
            if open_web_dashboard is not None:
                config.web_dashboard_open_on_launch = open_web_dashboard
            if web_dashboard_port is not None:
                config.web_dashboard_port = web_dashboard_port
            if log_level is not None:
                log_level = cast(Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], log_level.upper())
                config.log_level = logging.getLevelNamesMapping()[log_level]
            if trace_lsp_communication is not None:
                config.trace_lsp_communication = trace_lsp_communication
            if tool_timeout is not None:
                config.tool_timeout = tool_timeout
            if language_backend is not None:
                config.language_backend = language_backend

            modes_instances = [MurenaAgentMode.load(mode) for mode in modes]
            # Create agents for all projects (primary agent set for backward compatibility)
            self._create_all_agents(config, modes_instances)

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
    async def server_lifespan(self, mcp_server: FastMCP) -> AsyncIterator[None]:
        """Manage server startup and shutdown lifecycle."""
        openai_tool_compatible = self.context.name in ["chatgpt", "codex", "oaicompat-agent"]
        self._set_mcp_tools(mcp_server, openai_tool_compatible=openai_tool_compatible)
        log.info("MCP server lifetime setup complete")
        yield

    def _get_initial_instructions(self) -> str:
        assert self.agent is not None
        return self.agent.create_system_prompt()
