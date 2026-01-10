"""
Tools supporting the execution of (external) commands
"""

import contextlib
import io
import logging
import os.path

from serena.tools import Tool, ToolMarkerCanEdit, ToolMarkerOptional
from serena.util.shell import execute_shell_command


class ExecuteShellCommandTool(Tool, ToolMarkerCanEdit):
    """
    Executes a shell command.
    """

    def apply(
        self,
        command: str,
        cwd: str | None = None,
        capture_stderr: bool = True,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Execute a shell command and return its output. If there is a memory about suggested commands, read that first.
        Never execute unsafe shell commands!
        IMPORTANT: Do not use this tool to start
          * long-running processes (e.g. servers) that are not intended to terminate quickly,
          * processes that require user interaction.

        :param command: the shell command to execute
        :param cwd: the working directory to execute the command in. If None, the project root will be used.
        :param capture_stderr: whether to capture and return stderr output
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. -1 means using the default value, don't adjust unless there is no other way to get the content
            required for the task.
        :return: a JSON object containing the command's stdout and optionally stderr output
        """
        if cwd is None:
            _cwd = self.get_project_root()
        else:
            if os.path.isabs(cwd):
                _cwd = cwd
            else:
                _cwd = os.path.join(self.get_project_root(), cwd)
                if not os.path.isdir(_cwd):
                    raise FileNotFoundError(
                        f"Specified a relative working directory ({cwd}), but the resulting path is not a directory: {_cwd}"
                    )

        result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr)
        result = result.json()
        return self._limit_length(result, max_answer_chars)


class ExecuteSerenaCodeTool(Tool, ToolMarkerCanEdit, ToolMarkerOptional):
    """
    Executes python code in an environment where Serena is installed.
    """

    # TODO: `serena_config.language_backend = LanguageBackend.LSP` is needed until we include the depth parameter
    #   into the jetbrains overview tool. This is now just to make the example in demo_run_tools.py work.
    #   Of course, this becomes very slow since we start the LS every time.
    #   We can also consider making the serena_agent variable available in a different way, maybe by passing it
    #   as a parameter to exec instead of creating it inside the executed code.
    _AGENT_INSTANCE_PREPEND_CODE_TEMPLATE = """\
from serena.agent import SerenaAgent
from serena.analytics import RegisteredTokenCountEstimator
from serena.config.serena_config import SerenaConfig, LanguageBackend

serena_config = SerenaConfig.from_config_file()
serena_config.language_backend = LanguageBackend.LSP
serena_config.log_level = {log_level}
serena_config.web_dashboard = False
serena_config.token_count_estimator = RegisteredTokenCountEstimator.CHAR_COUNT.name
optional_tools = serena_config.included_optional_tools or []
if "execute_serena_code" not in optional_tools:
    optional_tools.append("execute_serena_code")
serena_config.included_optional_tools = optional_tools
serena_agent = SerenaAgent(project={project_path!r}, serena_config=serena_config)
"""

    @classmethod
    def execute_code(cls, code: str, project_path: str | None = None, log_level: int = logging.WARNING) -> str:
        """
        Execute python code in an environment where Serena is installed and return the captured stdout.

        :param code: the python code to execute
        :param project_path: the path to the project to use for the serena_agent instance.
            If None, uses the current working directory.
        :param log_level: the logging level to set during code execution
        :return: the stdout output of the executed code
        """
        # We can make it parametrizable later if needed
        prepend_agent_instance = True

        stdout_buffer = io.StringIO()
        if prepend_agent_instance:
            if project_path is None:
                project_path = os.getcwd()
            prepend_code = cls._AGENT_INSTANCE_PREPEND_CODE_TEMPLATE.format(project_path=project_path, log_level=log_level)
            code = prepend_code + "\n" + code
        try:
            with contextlib.redirect_stdout(stdout_buffer):
                exec(code)
            output = stdout_buffer.getvalue().strip().rstrip("\n")
            if not output:
                output = "Code executed successfully, no output."
        except Exception as e:
            output = f"Error executing code: {e}"
        return output

    def apply(
        self,
        code: str,
        max_answer_chars: int | None = None,
        project_path: str | None = None,
    ) -> str:
        """
        Execute python code in an environment where Serena is installed and return the captured stdout.
        An instance of SerenaAgent called 'serena_agent' is available for use in the code, all tools are accessible
        through it. This tool is useful for advanced usage of tools where scripting gives a benefit (e.g., looping,
        filtering, combining multiple tool calls, etc.).

        Example - find usages of `run` method of all classes that contain `Agent` in their name (passed as triple-quoted
        string as the `code` parameter):

            .. code-block:: python

                matches = serena_agent.apply_tool("search_for_pattern", substring_pattern="class .*Agent.*", restrict_search_to_code_files=True)
                if isinstance(matches, str):
                    import json
                    matches = json.loads(matches)
                candidate_files = list(matches)
                # contains tuples of (file_path, name_path) for all run methods found
                run_methods = []

                for file_path in candidate_files:
                    symbols_overview = serena_agent.apply_tool("get_symbol_overview", relative_path=file_path, depth=1)
                    cls_overviews = symbols_overview["Class"]
                    for cls_overview in cls_overviews:
                        cls_name = list(cls_overview)[0]  # has only one key which is the symbol name
                        methods = cls_overview[cls_name].get("Methods", [])
                        if "run" in methods:
                            run_methods.append((file_path, cls_name+"/run"))

                from pprint import pprint
                for file_path, name_path in run_methods:
                    usages = serena_agent.apply_tool("find_referencing_symbols", name_path=name_path, relative_path=file_path)
                    print(f"Usages of {name_path} in {file_path}:")
                    pprint(usages)

        :param code: the python code to execute
        :param max_answer_chars: limit the length of the returned output to this number of characters (if provided,
            -1 means using the default value)
        :param project_path: the path to the project to use for the serena_agent instance.
            If None, uses the current agent's project root.
        :return: the stdout output of the executed code
        """
        result = self.execute_code(
            code,
            project_path=project_path or self.get_project_root(),
        )
        return self._limit_length(result, max_answer_chars)
