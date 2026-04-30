import inspect
import json
from abc import ABC
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cached_property
from types import TracebackType
from typing import TYPE_CHECKING, Any, Optional, Protocol, Self, TypeVar, cast

from mcp import Implementation
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata, func_metadata
from sensai.util import logging
from sensai.util.string import dict_string

from serena.config.serena_config import LanguageBackend
from serena.project import MemoriesManager, Project
from serena.prompt_factory import PromptFactory
from serena.util.class_decorators import singleton
from serena.util.inspection import iter_subclasses
from serena.util.ls_diagnostics import DiagnosticsDiff, EditedFilePath, PublishedDiagnosticsSnapshot
from solidlsp.ls_exceptions import SolidLSPException

if TYPE_CHECKING:
    from serena.agent import SerenaAgent
    from serena.code_editor import CodeEditor, LanguageServerCodeEditor
    from serena.symbol import LanguageServerSymbolRetriever

log = logging.getLogger(__name__)
T = TypeVar("T")
SUCCESS_RESULT = "OK"


class Component(ABC):
    def __init__(self, agent: "SerenaAgent"):
        self.agent = agent

    def get_project_root(self) -> str:
        """
        :return: the root directory of the active project, raises a ValueError if no active project configuration is set
        """
        return self.project.project_root

    @property
    def prompt_factory(self) -> PromptFactory:
        return self.agent.prompt_factory

    @property
    def memories_manager(self) -> "MemoriesManager":
        return self.project.memories_manager

    def create_language_server_symbol_retriever(self) -> "LanguageServerSymbolRetriever":
        from serena.symbol import LanguageServerSymbolRetriever

        assert self.agent.get_language_backend().is_lsp(), "Language server symbol retriever can only be created for LSP language backend"
        return LanguageServerSymbolRetriever(self.project)

    @property
    def project(self) -> Project:
        return self.agent.get_active_project_or_raise()

    def create_code_editor(self) -> "CodeEditor":
        from ..code_editor import JetBrainsCodeEditor

        match self.agent.get_language_backend():
            case LanguageBackend.LSP:
                return self.create_ls_code_editor()
            case LanguageBackend.JETBRAINS:
                return JetBrainsCodeEditor(project=self.project)
            case _:
                raise ValueError

    def create_ls_code_editor(self) -> "LanguageServerCodeEditor":
        from ..code_editor import LanguageServerCodeEditor

        if not self.agent.is_using_language_server():
            raise Exception("Cannot create LanguageServerCodeEditor; agent is not in language server mode.")
        return LanguageServerCodeEditor(self.create_language_server_symbol_retriever())


class ToolMarker:
    """
    Base class for tool markers.
    """


class ToolMarkerCanEdit(ToolMarker):
    """
    Marker class for all tools that can perform editing operations on files.
    """


class ToolMarkerDoesNotRequireActiveProject(ToolMarker):
    pass


class ToolMarkerOptional(ToolMarker):
    """
    Marker class for optional tools that are disabled by default.
    """


class ToolMarkerSymbolicRead(ToolMarker):
    """
    Marker class for tools that perform symbol read operations.
    """


class ToolMarkerSymbolicEdit(ToolMarkerCanEdit):
    """
    Marker class for tools that perform symbolic edit operations.
    """


class ToolMarkerBeta(ToolMarker):
    """
    Marker for tools that are considered beta features (may not be fully robust)
    """


class ApplyMethodProtocol(Protocol):
    """Callable protocol for the apply method of a tool."""

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        pass


class Tool(Component):
    # NOTE: each tool should implement the apply method, which is then used in
    # the central method of the Tool class `apply_ex`.
    # Failure to do so will result in a RuntimeError at tool execution time.
    # The apply method is not declared as part of the base Tool interface since we cannot
    # know the signature of the (input parameters of the) method in advance.
    #
    # The docstring and types of the apply method are used to generate the tool description
    # (which is use by the LLM, so a good description is important)
    # and to validate the tool call arguments.

    SESSION_ID_PARAM_NAME = "session_id"
    """
    parameter name to use in apply method for the client session ID.
    This parameter will be ignored by the MCP interface but will be populated with the session ID of the current client session 
    when the tool is called, allowing tools to be session-aware if needed.
    """

    _last_tool_call_client_str: str | None = None
    """We can only get the client info from within a tool call. Each tool call will update this variable."""

    def __init__(self, agent: "SerenaAgent"):
        super().__init__(agent)

    @cached_property
    def _is_session_aware(self) -> bool:
        """
        :return: whether the tool is session-aware, i.e. whether the apply method expects a session_id (str) parameter.
        """
        # check apply method for session_id arg
        apply_fn = self.get_apply_fn()
        sig = inspect.signature(apply_fn)
        for param in sig.parameters.values():
            if param.name == self.SESSION_ID_PARAM_NAME:
                return True
        return False

    @staticmethod
    def _sanitize_input_param(raw_param: str) -> str:
        # some clients replace < and > with their escaped html versions, we need to counteract this
        return raw_param.replace("&lt;", "<").replace("&gt;", ">")

    @classmethod
    def set_last_tool_call_client_str(cls, client_str: str | None) -> None:
        cls._last_tool_call_client_str = client_str

    @classmethod
    def get_last_tool_call_client_str(cls) -> str | None:
        return cls._last_tool_call_client_str

    @classmethod
    def get_name_from_cls(cls) -> str:
        name = cls.__name__
        if name.endswith("Tool"):
            name = name[:-4]
        # convert to snake_case
        name = "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")
        return name

    def get_name(self) -> str:
        return self.get_name_from_cls()

    def get_apply_fn(self) -> ApplyMethodProtocol:
        apply_fn = getattr(self, "apply")
        if apply_fn is None:
            raise RuntimeError(f"apply not defined in {self}. Did you forget to implement it?")
        return apply_fn

    @classmethod
    def can_edit(cls) -> bool:
        """
        Returns whether this tool can perform editing operations on code.

        :return: True if the tool can edit code, False otherwise
        """
        return issubclass(cls, ToolMarkerCanEdit)

    @classmethod
    def get_tool_description(cls) -> str:
        docstring = cls.__doc__
        if docstring is None:
            return ""
        return docstring.strip()

    @classmethod
    def get_apply_docstring_from_cls(cls) -> str:
        """Get the docstring for the apply method from the class (static metadata).
        Needed for creating MCP tools in a separate process without running into serialization issues.
        """
        # First try to get from __dict__ to handle dynamic docstring changes
        if "apply" in cls.__dict__:
            apply_fn = cls.__dict__["apply"]
        else:
            # Fall back to getattr for inherited methods
            apply_fn = getattr(cls, "apply", None)
            if apply_fn is None:
                raise AttributeError(f"apply method not defined in {cls}. Did you forget to implement it?")

        docstring = apply_fn.__doc__
        if not docstring:
            raise AttributeError(f"apply method has no (or empty) docstring in {cls}. Did you forget to implement it?")
        return docstring.strip()

    def get_apply_docstring(self) -> str:
        """Gets the docstring for the tool application, used by the MCP server."""
        return self.get_apply_docstring_from_cls()

    def get_apply_fn_metadata(self) -> FuncMetadata:
        """Gets the metadata for the tool application function, used by the MCP server."""
        return self.get_apply_fn_metadata_from_cls()

    @classmethod
    def get_apply_fn_metadata_from_cls(cls) -> FuncMetadata:
        """Get the metadata for the apply method from the class (static metadata).
        Needed for creating MCP tools in a separate process without running into serialization issues.
        """
        # First try to get from __dict__ to handle dynamic docstring changes
        if "apply" in cls.__dict__:
            apply_fn = cls.__dict__["apply"]
        else:
            # Fall back to getattr for inherited methods
            apply_fn = getattr(cls, "apply", None)
            if apply_fn is None:
                raise AttributeError(f"apply method not defined in {cls}. Did you forget to implement it?")

        return func_metadata(apply_fn, skip_names=["self", "cls", cls.SESSION_ID_PARAM_NAME])

    def _log_tool_application(self, frame: Any, session_id: str) -> None:
        params = {}
        ignored_params = {"self", "log_call", "catch_exceptions", "args", "apply_fn"}
        for param, value in frame.f_locals.items():
            if param in ignored_params:
                continue
            if param == "kwargs":
                params.update(value)
            else:
                params[param] = value
        log.info(f"{self.get_name_from_cls()}: {dict_string(params)}; session_id: {session_id}")

    def _limit_length(
        self,
        result: str,
        max_answer_chars: int,
        shortened_result_factories: list[Callable[[], str]] | None = None,
    ) -> str:
        """Limit the length of the result string, optionally trying progressively shorter versions.

        :param result: the full result string
        :param max_answer_chars: maximum allowed characters. -1 means use the default from config.
        :param shortened_result_factories: optional list of closures, each producing a progressively shorter
            version of the result. They are tried in order until one fits within ``max_answer_chars``.
        :return: the result string, potentially replaced by a shortened version
        """
        if max_answer_chars == -1:
            max_answer_chars = self.agent.serena_config.default_max_tool_answer_chars
        if max_answer_chars <= 0:
            raise ValueError(f"Must be positive or the default (-1), got: {max_answer_chars=}")
        if (n_chars := len(result)) > max_answer_chars:
            too_long_msg = (
                f"The answer is too long ({n_chars} characters). " + "You can adjust your query or raise the max_answer_chars parameter."
            )
            if shortened_result_factories is not None:
                # try each shortening closure in order;
                for make_shorter in shortened_result_factories:
                    shortened = make_shorter()
                    candidate = f"{too_long_msg}\n{shortened}"
                    if len(candidate) <= max_answer_chars:
                        return candidate
            result = too_long_msg
        return result

    def is_active(self) -> bool:
        return self.agent.tool_is_active(self.get_name())

    def is_readonly(self) -> bool:
        return not self.can_edit()

    def is_symbolic(self) -> bool:
        return issubclass(self.__class__, ToolMarkerSymbolicRead) or issubclass(self.__class__, ToolMarkerSymbolicEdit)

    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, mcp_ctx: Context | None = None, **kwargs) -> str:  # type: ignore
        """
        Applies the tool with logging and exception handling, using the given keyword arguments
        """
        session_id = "global"
        if mcp_ctx is not None:
            try:
                session_id = "%x" % id(mcp_ctx.session)
                client_params = mcp_ctx.session.client_params
                if client_params is not None:
                    client_info = cast(Implementation, client_params.clientInfo)
                    client_str = client_info.title if client_info.title else client_info.name + " " + client_info.version
                    if client_str != self.get_last_tool_call_client_str():
                        log.debug(f"Updating client info: {client_info}")
                        self.set_last_tool_call_client_str(client_str)
            except Exception as e:
                log.info(f"Failed to get client info: {e}.")

        def task() -> str:
            apply_fn = self.get_apply_fn()

            try:
                if not self.is_active():
                    return f"Error: Tool '{self.get_name_from_cls()}' is not active. Active tools: {self.agent.get_active_tool_names()}"
            except Exception as e:
                return f"RuntimeError while checking if tool {self.get_name_from_cls()} is active: {e}"

            if log_call:
                self._log_tool_application(inspect.currentframe(), session_id)
            try:
                # check whether the tool requires an active project and language server
                if not isinstance(self, ToolMarkerDoesNotRequireActiveProject):
                    if self.agent.get_active_project() is None:
                        return (
                            "Error: No active project. Ask the user to provide the project path or to select a project from this list of known projects: "
                            + f"{self.agent.serena_config.project_names}"
                        )

                # construct apply kwargs, adding session_id if the tool is session-aware
                apply_kwargs = dict(kwargs)
                if self._is_session_aware:
                    apply_kwargs["session_id"] = session_id

                # apply the actual tool
                try:
                    result = apply_fn(**apply_kwargs)
                except SolidLSPException as e:
                    if e.is_language_server_terminated():
                        affected_language = e.get_affected_language()
                        if affected_language is not None:
                            log.error(
                                f"Language server terminated while executing tool ({e}). Restarting the language server and retrying ..."
                            )
                            self.agent.get_language_server_manager_or_raise().restart_language_server(affected_language)
                            result = apply_fn(**apply_kwargs)
                        else:
                            log.error(
                                f"Language server terminated while executing tool ({e}), but affected language is unknown. Not retrying."
                            )
                            raise
                    else:
                        raise

                # record tool usage
                self.agent.record_tool_usage(apply_kwargs, result, self)

            except Exception as e:
                if not catch_exceptions:
                    raise
                msg = f"Error executing tool: {e.__class__.__name__} - {e}"
                log.error(f"Error executing tool: {e}", exc_info=e)
                result = msg

            if log_call:
                log.info(f"Result: {result}")

            try:
                ls_manager = self.agent.get_language_server_manager()
                if ls_manager is not None:
                    ls_manager.save_all_caches()
            except Exception as e:
                log.error(f"Error saving language server cache: {e}")

            return result

        # execute the tool in the agent's task executor, with timeout
        try:
            task_exec = self.agent.issue_task(task, name=self.__class__.__name__)
            return task_exec.result(timeout=self.agent.serena_config.tool_timeout)
        except Exception as e:  # typically TimeoutError (other exceptions caught in task)
            msg = f"Error: {e.__class__.__name__} - {e}"
            log.error(msg)
            return msg

    @staticmethod
    def _to_json(x: Any) -> str:
        return json.dumps(x, ensure_ascii=False)


class EditingToolWithDiagnostics(Tool, ToolMarkerCanEdit):
    """
    Base class for editing tools that want to capture and report changes in LSP diagnostics before and after the edit.
    """

    ENABLE_DIAGNOSTICS: bool = False
    """
    Global flag to enable/disable diagnostics for LSP-based editing tools derived from this class.
    The feature is currently disabled, because per-edit diagnostics are a questionable feature, since individual
    edits often intentionally introduce diagnostics (e.g. function signature mismatches or even syntax errors) that 
    are then resolved in subsequent edits.
    """

    DIAGNOSTICS_KEY = "diagnostics[warning-or-higher]"

    class DiagnosticsContext:
        def __init__(self, tool: "EditingToolWithDiagnostics", *edited_relative_paths: str) -> None:
            self._tool = tool
            self._is_diagnostics_enabled = tool.ENABLE_DIAGNOSTICS and tool.agent.is_using_language_server()
            self._edited_files = [EditedFilePath(path, path) for path in edited_relative_paths]
            self._before_edit_diagnostics_snapshot: PublishedDiagnosticsSnapshot | None = None
            self._symbol_retriever: Optional["LanguageServerSymbolRetriever"] | None = None
            if self._is_diagnostics_enabled:
                self._symbol_retriever = tool.create_language_server_symbol_retriever()
                self._before_edit_diagnostics_snapshot = PublishedDiagnosticsSnapshot(self._edited_files, self._symbol_retriever)

        def __enter__(self) -> Self:
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore
            pass

        def format_result(
            self,
            base_result: str,
        ) -> str:
            if not self._is_diagnostics_enabled:
                return base_result

            if self._before_edit_diagnostics_snapshot is None:
                return base_result

            assert self._symbol_retriever is not None
            diagnostics_diff = DiagnosticsDiff(self._before_edit_diagnostics_snapshot, self._edited_files, self._symbol_retriever)
            grouped_diagnostics = diagnostics_diff.get_grouped_diagnostics().get_dict()

            if not grouped_diagnostics:
                return base_result
            else:
                result_dict = {
                    "result": base_result,
                    EditingToolWithDiagnostics.DIAGNOSTICS_KEY: grouped_diagnostics,
                }
                return self._tool._to_json(result_dict)


class EditedFileContext:
    """
    Context manager for file editing.

    Create the context, then use `set_updated_content` to set the new content, the original content
    being provided in `original_content`.
    When exiting the context without an exception, the updated content will be written back to the file.
    """

    def __init__(self, relative_path: str, code_editor: "CodeEditor"):
        self._relative_path = relative_path
        self._code_editor = code_editor
        self._edited_file: CodeEditor.EditedFile | None = None
        self._edited_file_context: Any = None

    def __enter__(self) -> Self:
        self._edited_file_context = self._code_editor.edited_file_context(self._relative_path)
        self._edited_file = self._edited_file_context.__enter__()
        return self

    def get_original_content(self) -> str:
        """
        :return: the original content of the file before any modifications.
        """
        assert self._edited_file is not None
        return self._edited_file.get_contents()

    def set_updated_content(self, content: str) -> None:
        """
        Sets the updated content of the file, which will be written back to the file
        when the context is exited without an exception.

        :param content: the updated content of the file
        """
        assert self._edited_file is not None
        self._edited_file.set_contents(content)

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        assert self._edited_file_context is not None
        self._edited_file_context.__exit__(exc_type, exc_value, traceback)


@dataclass(kw_only=True)
class RegisteredTool:
    tool_class: type[Tool]
    is_optional: bool
    is_beta: bool
    tool_name: str

    @property
    def class_docstring(self) -> str:
        """
        :return: the tool description (high-level class docstring)
        """
        return self.tool_class.get_tool_description()


tool_packages = ["serena.tools"]


@singleton
class ToolRegistry:
    _deleted_tools: list[str] = [
        "think_about_collected_information",
        "prepare_for_new_conversation",
        "summarize_changes",
        "think_about_whether_you_are_done",
        "switch_modes",
    ]

    def __init__(self) -> None:
        self._tool_dict: dict[str, RegisteredTool] = {}
        inclusion_predicate = lambda c: "apply" in c.__dict__  # include only concrete tool classes that implement apply
        for cls in iter_subclasses(Tool, inclusion_predicate=inclusion_predicate):
            if not any(cls.__module__.startswith(pkg) for pkg in tool_packages):
                continue
            is_optional = issubclass(cls, ToolMarkerOptional)
            is_beta = issubclass(cls, ToolMarkerBeta)
            name = cls.get_name_from_cls()
            if name in self._tool_dict:
                raise ValueError(f"Duplicate tool name found: {name}. Tool classes must have unique names.")
            self._tool_dict[name] = RegisteredTool(tool_class=cls, is_optional=is_optional, tool_name=name, is_beta=is_beta)

    def get_registered_tools_by_module(self) -> dict[str, list[RegisteredTool]]:
        """
        :return: the registered tools grouped by their module (ordered alphabetically by module and tool name)
        """
        module_dict: dict[str, list[RegisteredTool]] = {}
        for tool in self._tool_dict.values():
            module = tool.tool_class.__module__
            if module not in module_dict:
                module_dict[module] = []
            module_dict[module].append(tool)
        sorted_module_dict = {}
        for module in sorted(module_dict.keys()):
            sorted_module_dict[module] = sorted(module_dict[module], key=lambda t: t.tool_name)
        return sorted_module_dict

    def get_tool_class_by_name(self, tool_name: str) -> type[Tool]:
        if tool_name not in self._tool_dict:
            raise ValueError(f"Tool named '{tool_name}' not found.")
        return self._tool_dict[tool_name].tool_class

    def get_all_tool_classes(self) -> list[type[Tool]]:
        return list(t.tool_class for t in self._tool_dict.values())

    def get_tool_classes_default_enabled(self) -> list[type[Tool]]:
        """
        :return: the list of tool classes that are enabled by default (i.e. non-optional tools).
        """
        return [t.tool_class for t in self._tool_dict.values() if not t.is_optional]

    def get_tool_classes_optional(self) -> list[type[Tool]]:
        """
        :return: the list of tool classes that are optional (i.e. disabled by default).
        """
        return [t.tool_class for t in self._tool_dict.values() if t.is_optional]

    def get_tool_names_default_enabled(self) -> list[str]:
        """
        :return: the list of tool names that are enabled by default (i.e. non-optional tools).
        """
        return [t.tool_name for t in self._tool_dict.values() if not t.is_optional]

    def get_tool_names_optional(self) -> list[str]:
        """
        :return: the list of tool names that are optional (i.e. disabled by default).
        """
        return [t.tool_name for t in self._tool_dict.values() if t.is_optional]

    def get_tool_names(self) -> list[str]:
        """
        :return: the list of all tool names.
        """
        return list(self._tool_dict.keys())

    def print_tool_overview(
        self, tools: Iterable[type[Tool] | Tool] | None = None, include_optional: bool = False, only_optional: bool = False
    ) -> None:
        """
        Print a summary of the tools. If no tools are passed, a summary of the selection of tools (all, default or only optional) is printed.
        """
        if tools is None:
            if only_optional:
                tools = self.get_tool_classes_optional()
            elif include_optional:
                tools = self.get_all_tool_classes()
            else:
                tools = self.get_tool_classes_default_enabled()

        tool_dict: dict[str, type[Tool] | Tool] = {}
        for tool_class in tools:
            tool_dict[tool_class.get_name_from_cls()] = tool_class
        for tool_name in sorted(tool_dict.keys()):
            tool_class = tool_dict[tool_name]
            print(f" * `{tool_name}`: {tool_class.get_tool_description().strip()}")

    def is_valid_tool_name(self, tool_name: str) -> bool:
        return tool_name in self._tool_dict

    def check_valid_tool_name(self, tool_name: str, caller_context_for_logging: str = "") -> bool:
        """Returns True if the tool name is valid, False if it is deleted, and raises ValueError if it is invalid."""
        if self.is_deleted_tool_name(tool_name):
            log.warning(f"Tool name is deleted: {tool_name}{caller_context_for_logging}")
            return False
        if not self.is_valid_tool_name(tool_name):
            raise ValueError(f"Invalid tool name: {tool_name}{caller_context_for_logging}")
        return True

    def is_deleted_tool_name(self, tool_name: str) -> bool:
        return tool_name in self._deleted_tools
