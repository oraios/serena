"""
The Serena Model Context Protocol (MCP) Server
"""

import inspect
import json
import os
import platform
import sys
import traceback
from abc import ABC
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Iterator
from contextlib import contextmanager
from logging import Logger
from pathlib import Path
from typing import Any, TypeVar, cast

import yaml
from sensai.util import logging
from sensai.util.string import dict_string

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_types import SymbolKind
from serena.gui_log_viewer import GuiLogViewer, GuiLogViewerHandler
from serena.llm.prompt_factory import PromptFactory
from serena.symbol import SymbolLocation, SymbolManager
from serena.util.file_system import scan_directory
from serena.util.inspection import iter_subclasses
from serena.util.shell import execute_shell_command

log = logging.getLogger(__name__)
LOG_FORMAT = "%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s"
TTool = TypeVar("TTool", bound="Tool")
SUCCESS_RESULT = "OK"


class LinesRead:
    def __init__(self) -> None:
        self.files: dict[str, set[tuple[int, int]]] = defaultdict(lambda: set())

    def add_lines_read(self, relative_path: str, lines: tuple[int, int]) -> None:
        self.files[relative_path].add(lines)

    def were_lines_read(self, relative_path: str, lines: tuple[int, int]) -> bool:
        lines_read_in_file = self.files[relative_path]
        return lines in lines_read_in_file

    def invalidate_lines_read(self, relative_path: str) -> None:
        if relative_path in self.files:
            del self.files[relative_path]


class SerenaAgent:
    def __init__(self, project_file_path: str, start_language_server: bool = False):
        """
        :param project_file_path: the project configuration file path (.yml)
        :param start_language_server: whether to start the language server immediately and manage its
            lifecycle internally
        """
        self._start_language_server = start_language_server

        if not os.path.exists(project_file_path):
            print(f"Project file not found: {project_file_path}", file=sys.stderr)
            sys.exit(1)

        # read project configuration
        with open(project_file_path, encoding="utf-8") as f:
            project_config = yaml.safe_load(f)
        self.project_config = project_config
        self.language = Language(project_config["language"])
        self.project_root = str(Path(project_config["project_root"]).resolve())

        # enable GUI log window
        enable_gui_log = project_config.get("gui_log_window", True)
        self._gui_log_handler = None
        if enable_gui_log:
            if platform.system() == "Darwin":
                log.warning("GUI log window is not supported on macOS")
            else:
                log_level = project_config.get("gui_log_level", logging.INFO)
                if Logger.root.level > log_level:
                    log.info(f"Root logger level is higher than GUI log level; changing the root logger level to {log_level}")
                    Logger.root.setLevel(log_level)
                self._gui_log_handler = GuiLogViewerHandler(GuiLogViewer(title="Serena Logs"), level=log_level, format_string=LOG_FORMAT)
                Logger.root.addHandler(self._gui_log_handler)

        log.info(
            f"Starting serena server for project {project_file_path} (language={self.language}, root={self.project_root}); "
            f"process id={os.getpid()}, parent process id={os.getppid()}"
        )

        # create and start the language server instance
        config = MultilspyConfig(code_language=self.language)
        logger = MultilspyLogger()
        self.language_server = SyncLanguageServer.create(config, logger, self.project_root)

        self.prompt_factory = PromptFactory()
        self.symbol_manager = SymbolManager(self.language_server, self)
        self.memories_manager = MemoriesManager(os.path.join(self.get_serena_managed_dir(), "memories"))
        self.lines_read = LinesRead()

        # find all tool classes and instantiate them
        excluded_tools = project_config.get("excluded_tools", [])
        self._all_tools: dict[type[Tool], Tool] = {}
        self.tools: dict[type[Tool], Tool] = {}
        for tool_class in iter_tool_classes():
            tool_instance = tool_class(self)
            self._all_tools[tool_class] = tool_instance
            if (tool_name := tool_class.get_name()) in excluded_tools:
                log.info(f"Skipping tool {tool_name} because it is in the exclude list")
                continue
            self.tools[tool_class] = tool_instance
        log.info(f"Loaded tools: {', '.join([tool.get_name() for tool in self.tools.values()])}")

        # If GUI log window is enabled, set the tool names for highlighting
        if self._gui_log_handler is not None:
            tool_names = [tool.get_name() for tool in self.tools.values()]
            self._gui_log_handler.log_viewer.set_tool_names(tool_names)
        # start the language server if requested
        if self._start_language_server:
            log.info("Starting the language server ...")
            self.language_server.start()

    def get_tool(self, tool_class: type[TTool]) -> TTool:
        return self._all_tools[tool_class]  # type: ignore

    def print_tool_overview(self) -> None:
        _print_tool_overview(self.tools.values())

    def get_serena_managed_dir(self) -> str:
        return os.path.join(self.project_root, ".serena")

    def mark_file_modified(self, relativ_path: str) -> None:
        self.lines_read.invalidate_lines_read(relativ_path)

    def __del__(self) -> None:
        """
        Destructor to clean up the language server instance and GUI logger
        """
        if not hasattr(self, "_is_initialized"):
            return
        log.info("SerenaAgent is shutting down ...")
        if self._start_language_server:
            log.info("Stopping the language server ...")
            self.language_server.stop()
        if self._gui_log_handler:
            log.info("Stopping the GUI log window ...")
            self._gui_log_handler.stop_viewer()
            Logger.root.removeHandler(self._gui_log_handler)

    @contextmanager
    def language_server_lifecycle_context(self) -> Iterator[None]:
        """
        Context manager for the language server's lifecycle
        """
        if self._start_language_server:
            raise Exception("This context manager can only be used if the instance is created with start_language_server=True")
        with self.language_server.start_server():
            yield


class MemoriesManager:
    def __init__(self, memory_dir: str):
        self._memory_dir = Path(memory_dir)
        self._memory_dir.mkdir(parents=True, exist_ok=True)

    def _get_memory_file_path(self, memory_file_name: str) -> Path:
        return self._memory_dir / memory_file_name

    def load_memory(self, memory_file_name: str) -> str:
        memory_file_path = self._get_memory_file_path(memory_file_name)
        if not memory_file_path.exists():
            return f"Memory file {memory_file_name} not found, consider creating it with the `write_memory` tool if you need it."
        with open(memory_file_path, encoding="utf-8") as f:
            return f.read()

    def save_memory(self, memory_file_name: str, content: str) -> str:
        memory_file_path = self._get_memory_file_path(memory_file_name)
        with open(memory_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Memory file {memory_file_name} written."

    def list_memories(self) -> list[str]:
        return [f.name for f in self._memory_dir.iterdir() if f.is_file()]

    def delete_memory(self, memory_file_name: str) -> str:
        memory_file_path = self._get_memory_file_path(memory_file_name)
        memory_file_path.unlink()
        return f"Memory file {memory_file_name} deleted."


class Component(ABC):
    def __init__(self, agent: "SerenaAgent"):
        self.agent = agent
        self.language_server = agent.language_server
        self.project_root = agent.project_root
        self.project_config = agent.project_config
        self.prompt_factory = agent.prompt_factory
        self.memories_manager = agent.memories_manager
        self.symbol_manager = agent.symbol_manager


_DEFAULT_MAX_ANSWER_LENGTH = int(2e5)


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

    @classmethod
    def get_name(cls) -> str:
        name = cls.__name__
        if name.endswith("Tool"):
            name = name[:-4]
        # convert to snake_case
        name = "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")
        return name

    def get_apply_fn(self) -> Callable:
        apply_fn = getattr(self, "apply")
        if apply_fn is None:
            raise RuntimeError(f"apply not defined in {self}. Did you forget to implement it?")
        return apply_fn

    @classmethod
    def get_tool_description(cls) -> str:
        docstring = cls.__doc__
        if docstring is None:
            return ""
        return docstring.strip()

    def get_function_description(self) -> str:
        apply_fn = self.get_apply_fn()
        docstring = apply_fn.__doc__
        if docstring is None:
            raise Exception(f"Missing docstring for {self}")
        return docstring

    def _log_tool_application(self, frame: Any) -> None:
        params = {}
        ignored_params = {"self", "log_call", "catch_exceptions", "args", "apply_fn"}
        for param, value in frame.f_locals.items():
            if param in ignored_params:
                continue
            if param == "kwargs":
                params.update(value)
            else:
                params[param] = value
        log.info(f"{self.get_name()}: {dict_string(params)}")

    @staticmethod
    def _limit_length(result: str, max_answer_chars: int) -> str:
        if (n_chars := len(result)) > max_answer_chars:
            result = (
                f"The answer is too long ({n_chars} characters). "
                + "Please try a more specific tool query or raise the max_answer_chars parameter."
            )
        return result

    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, **kwargs) -> str:  # type: ignore
        """
        Applies the tool with the given arguments
        """
        apply_fn = self.get_apply_fn()
        if log_call:
            self._log_tool_application(inspect.currentframe())
        try:
            result = apply_fn(**kwargs)
        except Exception as e:
            if not catch_exceptions:
                raise
            msg = f"Error executing tool: {e}\n{traceback.format_exc()}"
            log.error(f"Error executing tool: {e}", exc_info=e)
            result = msg
        if log_call:
            log.info(f"Result: {result}")
        return result


class ReadFileTool(Tool):
    """
    Reads a file within the project directory.
    """

    def apply(
        self, relative_path: str, start_line: int = 0, end_line: int | None = None, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH
    ) -> str:
        """
        Reads the given file or a chunk of it. Generally, symbolic operations
        like find_symbol or find_referencing_symbols should be preferred if you know which symbols you are looking for.
        Reading the entire file is only recommended if there is no other way to get the content required for the task.

        :param relative_path: the relative path to the file to read
        :param start_line: the 0-based index of the first line to be retrieved.
        :param end_line: the 0-based index of the last line to be retrieved (inclusive). If None, read until the end of the file.
        :param max_answer_chars: if the file (chunk) is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: the full text of the file at the given relative path
        """
        result = self.language_server.retrieve_full_file_content(relative_path)
        result_lines = result.splitlines()
        if end_line is None:
            result_lines = result_lines[start_line:]
        else:
            self.agent.lines_read.add_lines_read(relative_path, (start_line, end_line))
            result_lines = result_lines[start_line : end_line + 1]
        result = "\n".join(result_lines)

        return self._limit_length(result, max_answer_chars)


class CreateTextFileTool(Tool):
    """
    Creates/overwrites a file in the project directory.
    """

    def apply(self, relative_path: str, content: str) -> str:
        """
        Write a new file (or overwrite an existing file). For existing files, it is strongly recommended
        to use symbolic operations like replace_symbol_body or insert_after_symbol/insert_before_symbol, if possible.
        You can also use insert_at_line to insert content at a specific line for existing files if the symbolic operations
        are not the right choice for what you want to do.

        If ever used on an existing file, the content has to be the complete content of that file (so it
        may never end with something like "The remaining content of the file is left unchanged.").
        For operations that just replace a part of a file, use the replace_lines or the symbolic editing tools instead.

        :param relative_path: the relative path to the file to create
        :param content: the (utf-8-encoded) content to write to the file
        :return: a message indicating success or failure
        """
        absolute_path = os.path.join(self.project_root, relative_path)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        with open(absolute_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File created: {relative_path}"


class ListDirTool(Tool):
    """
    Lists files and directories in the given directory (optionally with recursion).
    """

    def apply(self, relative_path: str, recursive: bool, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        :param relative_path: the relative path to the directory to list; pass "." to scan the project root
        :param recursive: whether to scan subdirectories recursively
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object with the names of directories and files within the given directory
        """
        dirs, files = scan_directory(
            os.path.join(self.project_root, relative_path),
            relative_to=self.project_root,
            recursive=recursive,
            ignored_dirs=self.project_config["ignored_dirs"],
        )
        result = json.dumps({"dirs": dirs, "files": files})
        return self._limit_length(result, max_answer_chars)


class GetDirOverviewTool(Tool):
    """
    Gets an overview of the top-level symbols defined in all files within a given directory.
    """

    def apply(self, relative_path: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Gets an overview of the given directory.
        For each file in the directory, we list the top-level symbols in the file (name, kind, line).
        Use this tool to get a high-level understanding of the code symbols inside a directory.

        :param relative_path: the relative path to the directory to get the overview of
        :param max_answer_chars: if the overview is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. If the overview is too long, you should use a smaller directory instead,
            (e.g. a subdirectory).
        :return: a JSON object mapping relative paths of all contained files to info about top-level symbols in the file (name, kind, line, column).
        """
        path_to_symbol_infos = self.language_server.request_dir_overview(relative_path)
        result = {}
        for file_path, symbols in path_to_symbol_infos.items():
            result[file_path] = [_tuple_to_info(*symbol_info) for symbol_info in symbols]

        result_json_str = json.dumps(result)
        return self._limit_length(result_json_str, max_answer_chars)


class GetDocumentOverviewTool(Tool):
    """
    Gets an overview of the top-level symbols defined in a given file.
    """

    def apply(self, relative_path: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Use this tool to get a high-level understanding of the code symbols in a file. It often makes sense
        to call this before targeted reading, searching or editing operations on the code symbols in the file,
        as the output will contain a lot of information about names and lines.

        :param relative_path: the relative path to the file to get the overview of
        :param max_answer_chars: if the overview is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object with the info (name, kind, line, column) of all top-level symbols in the file.
        """
        result = self.language_server.request_document_overview(relative_path)
        result_json_str = json.dumps([_tuple_to_info(*symbol_info) for symbol_info in result])
        return self._limit_length(result_json_str, max_answer_chars)


class FindSymbolTool(Tool):
    """
    Performs a global (or local) search for symbols with/containing a given name/substring (optionally filtered by type).
    """

    def apply(
        self,
        name: str,
        depth: int = 0,
        include_body: bool = False,
        include_kinds: list[int] | None = None,
        exclude_kinds: list[int] | None = None,
        substring_matching: bool = False,
        dir_relative_path: str | None = None,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Retrieves information on all symbols/code entities, i.e. classes, methods, attributes, variables, etc.
        with the given name.
        The returned symbol location information can subsequently be used to edit the returned symbols
        or to retrieve further information using other tools.
        If you already anticipate that you will need to reference children of the symbol (like methods or fields contained in a class),
        you can specify a depth > 0.

        :param name: the name of the symbols to find
        :param depth: specifies the depth up to which descendants of the symbol are to be retrieved
            (e.g. depth 1 will retrieve methods and attributes for the case where the symbol refers to a class).
            Provide a non-zero depth if you intend to subsequently query symbols that are contained in the
            retrieved symbol.
        :param dir_relative_path: pass a directory relative path to only consider symbols within this directory.
            If None, the entire codebase will be considered.
        :param include_body: whether to include the body of all symbols in the result. You should only use this
            if you actually need the body of the symbol for the task at hand (for example, for a deep analysis
            of the functionality or for an editing task).
        :param include_kinds: an optional list of ints representing the LSP symbol kind.
            If provided, only symbols of the given kinds will be included in the result.
            Valid kinds:
            1=file, 2=module, 3=namespace, 4=package, 5=class, 6=method, 7=property, 8=field, 9=constructor, 10=enum,
            11=interface, 12=function, 13=variable, 14=constant, 15=string, 16=number, 17=boolean, 18=array, 19=object,
            20=key, 21=null, 22=enum member, 23=struct, 24=event, 25=operator, 26=type parameter
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
            Takes precedence over include_kinds.
        :param substring_matching: whether to use substring matching for the symbol name.
            If True, the symbol name will be matched if it contains the given name as a substring.
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        :return: a list of symbols (with symbol locations) that match the given name in JSON format
        """
        include_kinds = cast(list[SymbolKind] | None, include_kinds)
        exclude_kinds = cast(list[SymbolKind] | None, exclude_kinds)
        symbols = self.symbol_manager.find_by_name(
            name,
            include_body=include_body,
            include_kinds=include_kinds,
            exclude_kinds=exclude_kinds,
            substring_matching=substring_matching,
            dir_relative_path=dir_relative_path,
        )
        symbol_dicts = [s.to_dict(kind=True, location=True, depth=depth, include_body=include_body) for s in symbols]
        result = json.dumps(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindReferencingSymbolsTool(Tool):
    """
    Finds symbols that reference the symbol at the given location (optionally filtered by type).
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        include_body: bool = False,
        include_kinds: list[int] | None = None,
        exclude_kinds: list[int] | None = None,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Finds symbols that reference the symbol at the given location.
        Note that among other kinds of references, this function can be used to find (direct) subclasses of a class,
        as subclasses are referencing symbols that have the kind class.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number
        :param column: the column
        :param include_body: whether to include the body of the symbols in the result.
            Note that this might lead to a very long output, so you should only use this if you actually need the body
            of the referencing symbols for the task at hand. Usually it is a better idea to find
            the referencing symbols without the body and then use the find_symbol tool to get the body of
            specific symbols if needed.
        :param include_kinds: an optional list of integers representing the LSP symbol kinds to include.
            If provided, only symbols of the given kinds will be included in the result.
            Valid kinds:
            1=file, 2=module, 3=namespace, 4=package, 5=class, 6=method, 7=property, 8=field, 9=constructor, 10=enum,
            11=interface, 12=function, 13=variable, 14=constant, 15=string, 16=number, 17=boolean, 18=array, 19=object,
            20=key, 21=null, 22=enum member, 23=struct, 24=event, 25=operator, 26=type parameter
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
            Takes precedence over include_kinds.
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        :return: a list of JSON objects with the symbols referencing the requested symbol
        """
        include_kinds = cast(list[SymbolKind] | None, include_kinds)
        exclude_kinds = cast(list[SymbolKind] | None, exclude_kinds)
        symbols = self.symbol_manager.find_referencing_symbols(
            SymbolLocation(relative_path, line, column),
            include_body=include_body,
            include_kinds=include_kinds,
            exclude_kinds=exclude_kinds,
        )
        symbol_dicts = [s.to_dict(kind=True, location=True, depth=0, include_body=include_body) for s in symbols]
        result = json.dumps(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindReferencingCodeSnippetsTool(Tool):
    """
    Finds code snippets in which the symbol at the given location is referenced.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Returns short code snippets where the symbol at the given location is referenced.

        Contrary to the `find_referencing_symbols` tool, this tool returns references that are not symbols but instead
        code snippets that may or may not be contained in a symbol (for example, file-level calls).
        It may make sense to use this tool to get a quick overview of the code that references
        the symbol. Usually, just looking at code snippets is not enough to understand the full context,
        unless the case you are investigating is very simple,
        or you already have read the relevant symbols using the find_referencing_symbols tool and
        now want to get an overview of how the referenced symbol (at the given location) is used in them.
        The size of the snippets is controlled by the context_lines_before and context_lines_after parameters.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number of the symbol to find references for
        :param column: the column of the symbol to find references for
        :param context_lines_before: the number of lines to include before the line containing the reference
        :param context_lines_after: the number of lines to include after the line containing the reference
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        """
        matches = self.language_server.request_references_with_content(
            relative_path, line, column, context_lines_before, context_lines_after
        )
        result = [match.to_display_string() for match in matches]
        result_json_str = json.dumps(result)
        return self._limit_length(result_json_str, max_answer_chars)


class ReplaceSymbolBodyTool(Tool):
    """
    Replaces the full definition of a symbol.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        body: str,
    ) -> str:
        """
        Replaces the body of the symbol at the given location.
        Important: Do not try to guess symbol locations but instead use the find_symbol tool to get the correct location.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number
        :param column: the column
        :param body: the new symbol body. Important: Provide the correct level of indentation
            (as the original body). Note that the first line must not be indented (i.e. no leading spaces).
        """
        self.symbol_manager.replace_body(
            SymbolLocation(relative_path, line, column),
            body=body,
        )
        return SUCCESS_RESULT


class InsertAfterSymbolTool(Tool):
    """
    Inserts content after the end of the definition of a given symbol.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        body: str,
    ) -> str:
        """
        Inserts the given body/content after the end of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number
        :param column: the column
        :param body: the body/content to be inserted
        """
        location = SymbolLocation(relative_path, line, column)
        self.symbol_manager.insert_after(
            location,
            body=body,
        )
        return SUCCESS_RESULT


class InsertBeforeSymbolTool(Tool):
    """
    Inserts content before the beginning of the definition of a given symbol.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        body: str,
    ) -> str:
        """
        Inserts the given body/content before the beginning of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.
        It also can be used to insert a new import statement before the first symbol in the file.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number
        :param column: the column
        :param body: the body/content to be inserted
        """
        self.symbol_manager.insert_before(
            SymbolLocation(relative_path, line, column),
            body=body,
        )
        return SUCCESS_RESULT


class DeleteLinesTool(Tool):
    """
    Deletes a range of lines within a file.
    """

    def apply(
        self,
        relative_path: str,
        start_line: int,
        end_line: int,
    ) -> str:
        """
        Deletes the given lines in the file.
        Requires that the same range of lines was previously read using the `read_file` tool to verify correctness
        of the operation.

        :param relative_path: the relative path to the file
        :param start_line: the 0-based index of the first line to be deleted
        :param end_line: the 0-based index of the last line to be deleted
        """
        if not self.agent.lines_read.were_lines_read(relative_path, (start_line, end_line)):
            read_lines_tool = self.agent.get_tool(ReadFileTool)
            return f"Error: Must call `{read_lines_tool.get_name()}` first to read exactly the affected lines."
        self.symbol_manager.delete_lines(relative_path, start_line, end_line)
        return SUCCESS_RESULT


class ReplaceLinesTool(Tool):
    """
    Replaces a range of lines within a file with new content.
    """

    def apply(
        self,
        relative_path: str,
        start_line: int,
        end_line: int,
        content: str,
    ) -> str:
        """
        Replaces the given range of lines in the given file.
        Requires that the same range of lines was previously read using the `read_file` tool to verify correctness
        of the operation.

        :param relative_path: the relative path to the file
        :param start_line: the 0-based index of the first line to be deleted
        :param end_line: the 0-based index of the last line to be deleted
        :param content: the content to insert
        """
        if not content.endswith("\n"):
            content += "\n"
        result = self.agent.get_tool(DeleteLinesTool).apply(relative_path, start_line, end_line)
        if result != SUCCESS_RESULT:
            return result
        self.agent.get_tool(InsertAtLineTool).apply(relative_path, start_line, content)
        return SUCCESS_RESULT


class InsertAtLineTool(Tool):
    """
    Inserts content at a given line in a file.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        content: str,
    ) -> str:
        """
        Inserts the given content at the given line in the file, pushing existing content of the line down.
        In general, symbolic insert operations like insert_after_symbol or insert_before_symbol should be preferred if you know which
        symbol you are looking for.
        However, this can also be useful for small targeted edits of the body of a longer symbol (without replacing the entire body).

        :param relative_path: the relative path to the file
        :param line: the 0-based index of the line to insert content at
        :param content: the content to be inserted
        """
        if not content.endswith("\n"):
            content += "\n"
        self.symbol_manager.insert_at_line(relative_path, line, content)
        return SUCCESS_RESULT


class CheckOnboardingPerformedTool(Tool):
    """
    Checks whether the onboarding was already performed.
    """

    def apply(self) -> str:
        """
        Check if onboarding was performed yet.
        You should always call this tool in the beginning of the conversation,
        before any question about code or the project is asked.
        You will call this tool only once per conversation.
        """
        list_memories_tool = self.agent.get_tool(ListMemoriesTool)
        memories = json.loads(list_memories_tool.apply())
        if len(memories) == 0:
            return (
                "Onboarding not performed yet (no memories available). "
                + "You should perform onboarding by calling the `onboarding` tool before proceeding with the task."
            )
        else:
            return "Onboarding already performed, no need to perform it again."


class OnboardingTool(Tool):
    """
    Performs onboarding (identifying the project structure and essential tasks, e.g. for testing or building).
    """

    def apply(self) -> str:
        """
        Call this tool if onboarding was not performed yet.
        You will call this tool at most once per conversation.

        :return: instructions on how to create the onboarding information
        """
        system = platform.system()
        return self.prompt_factory.create_onboarding_prompt(system=system)


class WriteMemoryTool(Tool):
    """
    Writes a named memory (for future reference) to Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str, content: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Write some information about this project that can be useful for future tasks to a memory file.
        The information should be short and to the point.
        The memory file name should be meaningful, such that from the name you can infer what the information is about.
        It is better to have multiple small memory files than to have a single large one because
        memories will be read one by one and we only ever want to read relevant memories.

        This tool is either called during the onboarding process or when you have identified
        something worth remembering about the project from the past conversation.
        """
        if len(content) > max_answer_chars:
            raise ValueError(
                f"Content for {memory_file_name    } is too long. Max length is {max_answer_chars} characters. "
                + "Please make the content shorter."
            )

        return self.memories_manager.save_memory(memory_file_name, content)


class ReadMemoryTool(Tool):
    """
    Reads the memory with the given name from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Read the content of a memory file. This tool should only be used if the information
        is relevant to the current task. You can infer whether the information
        is relevant from the memory file name.
        You should not read the same memory file multiple times in the same conversation.
        """
        return self.memories_manager.load_memory(memory_file_name)


class ListMemoriesTool(Tool):
    """
    Lists memories in Serena's project-specific memory store.
    """

    def apply(self) -> str:
        """
        List available memories. Any memory can be read using the `read_memory` tool.
        """
        return json.dumps(self.memories_manager.list_memories())


class DeleteMemoryTool(Tool):
    """
    Deletes a memory from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str) -> str:
        """
        Delete a memory file. Should only happen if a user asks for it explicitly,
        for example by saying that the information retrieved from a memory file is no longer correct
        or no longer relevant for the project.
        """
        return self.memories_manager.delete_memory(memory_file_name)


class ThinkAboutCollectedInformationTool(Tool):
    """
    Thinking tool for pondering the completeness of collected information.
    """

    def apply(self) -> str:
        """
        Think about the collected information and whether it is sufficient and relevant.
        This tool should ALWAYS be called after you have completed a non-trivial sequence of searching steps like
        find_symbol, find_referencing_symbols, search_files_for_pattern, read_file, etc.
        """
        return self.prompt_factory.create_think_about_collected_information()


class ThinkAboutTaskAdherenceTool(Tool):
    """
    Thinking tool for determining whether the agent is still on track with the current task.
    """

    def apply(self) -> str:
        """
        Think about the task at hand and whether you are still on track.
        Especially important if the conversation has been going on for a while and there
        has been a lot of back and forth.

        This tool should ALWAYS be called before you insert, replace, or delete code.
        """
        return self.prompt_factory.create_think_about_task_adherence()


class ThinkAboutWhetherYouAreDoneTool(Tool):
    """
    Thinking tool for determining whether the task is truly completed.
    """

    def apply(self) -> str:
        """
        Think about whether you are done with the task.

        This tool should ALWAYS be called after you have completed a task or a subtask.
        """
        return self.prompt_factory.create_think_about_whether_you_are_done()


class SummarizeChangesTool(Tool):
    """
    Provides instructions for summarizing the changes made to the codebase.
    """

    def apply(self) -> str:
        """
        Summarize the changes you have made to the codebase.
        This tool should ALWAYS be called after you have fully completed any non-trivial coding task
        (but after the think_about_whether_you_are_done call).
        """
        return self.prompt_factory.create_summarize_changes()


class PrepareForNewConversationTool(Tool):
    """
    Provides instructions for preparing for a new conversation (in order to continue with the necessary context).
    """

    def apply(self) -> str:
        """
        Instructions for preparing for a new conversation. This tool should only be called on explicit user request.
        """
        return self.prompt_factory.create_prepare_for_new_conversation()


class SearchInAllCodeTool(Tool):
    """
    Performs a search for a pattern in all code files (and only in code files) in the project.
    """

    def apply(
        self,
        pattern: str,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Search for a pattern in all code files (and only in code files) in the project. Generally, symbolic operations like find_symbol or find_referencing_symbols
        should be preferred if you know which symbols you are looking for.
        If you have to look in non-code files (like notebooks, documentation, etc.), you should use the shell_command tool with grep or similar.
        This tool can be useful if you are looking for a specific pattern in the codebase that is not a symbol name.

        :param pattern: Regular expression pattern to search for, either as a compiled Pattern or string
        :param context_lines_before: Number of lines of context to include before each match
        :param context_lines_after: Number of lines of context to include after each match
        :param paths_include_glob: optional glob pattern specifying files to include in the search; if not provided, search globally.
        :param paths_exclude_glob: optional glob pattern specifying files to exclude from the search (takes precedence over paths_include_glob).
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        :return: A JSON object mapping file paths to lists of matched consecutive lines (with context, if requested).
        """
        matches = self.language_server.search_files_for_pattern(
            pattern=pattern,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            paths_include_glob=paths_include_glob,
            paths_exclude_glob=paths_exclude_glob,
        )
        # group matches by file
        file_to_matches: dict[str, list[str]] = defaultdict(list)
        for match in matches:
            assert match.source_file_path is not None
            file_to_matches[match.source_file_path].append(match.to_display_string())
        result = json.dumps(file_to_matches)
        return self._limit_length(result, max_answer_chars)


class ExecuteShellCommandTool(Tool):
    """
    Executes a shell command.
    """

    def apply(
        self,
        command: str,
        cwd: str | None = None,
        capture_stderr: bool = True,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Execute a shell command and return its output.

        IMPORTANT: you should always consider the memory about suggested shell commands before using this tool.
        If this memory was not loaded in the current conversation, you should load it using the `read_memory` tool
        before using this tool.

        You should have at least once looked at the suggested shell commands from the corresponding memory
        created during the onboarding process before using this tool.
        Never execute unsafe shell commands like `rm -rf /` or similar! Generally be very careful with deletions.

        :param command: the shell command to execute
        :param cwd: the working directory to execute the command in. If None, the project root will be used.
        :param capture_stderr: whether to capture and return stderr output
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object containing the command's stdout and optionally stderr output
        """
        _cwd = cwd or self.project_root
        result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr)
        result = result.json()
        return self._limit_length(result, max_answer_chars)


def iter_tool_classes() -> Generator[type[Tool], None, None]:
    return iter_subclasses(Tool)


def print_tool_overview() -> None:
    _print_tool_overview(iter_tool_classes())


def _print_tool_overview(tools: Iterable[type[Tool] | Tool]) -> None:
    tool_dict: dict[str, type[Tool] | Tool] = {}
    for tool in tools:
        tool_dict[tool.get_name()] = tool
    for tool_name in sorted(tool_dict.keys()):
        tool = tool_dict[tool_name]
        print(f" * `{tool_name}`: {tool.get_tool_description().strip()}")


def _tuple_to_info(name: str, symbol_type: SymbolKind, line: int, column: int) -> dict[str, int | str]:
    return {"name": name, "symbol_kind": symbol_type, "line": line, "column": column}
