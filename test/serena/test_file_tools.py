from pathlib import Path
from unittest.mock import MagicMock

import pytest

from serena.config.serena_config import SerenaConfig
from serena.constants import DEFAULT_SOURCE_FILE_ENCODING
from serena.project import Project
from serena.tools import ReadFileTool
from solidlsp.ls_utils import TextUtils


@pytest.fixture
def read_file_tool(tmp_path: Path) -> ReadFileTool:
    project = Project.load(str(tmp_path), serena_config=SerenaConfig(gui_log_window=False, web_dashboard=False))
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    tool = ReadFileTool(agent)
    # bypass the length limit, which would otherwise depend on the agent configuration
    tool._limit_length = lambda result, max_answer_chars: result
    return tool


def _deleted_by_delete_lines(content: str, line: int) -> str:
    """
    :return: the text that `delete_lines(line, line)` removes from the given content, which is
        computed via the same primitive the tool uses (`code_editor.delete_lines` deletes the text
        between (line, 0) and (line + 1, 0)).
    """
    _, deleted_text = TextUtils.delete_text_between_positions(content, start_line=line, start_col=0, end_line=line + 1, end_col=0)
    return deleted_text


class TestReadFileToolLineNumbering:
    """
    `delete_lines`/`replace_lines` require the same range of lines to have been read via `read_file`
    beforehand, so the line indices reported by `read_file` must be the ones the editing tools apply to.
    """

    @pytest.mark.parametrize(
        "content",
        [
            "line0\nline1\nline2\n",
            "line0\nline1\nline2",
            "line0\r\nline1\r\nline2\r\n",
            "line0\rline1\rline2\r",
            "line0\n\nline2\n",
            # separators which Python's `splitlines` breaks on but which are not line breaks according to the LSP
            "line0\n\x0cline1\nline2\n",
            "line0\n\x0bline1\nline2\n",
            "line0\n\x1cline1\nline2\n",
            "line0\n\x85line1\nline2\n",
            "line0\n\u2028line1\nline2\n",
        ],
    )
    def test_read_file_lines_match_lines_targeted_by_delete_lines(self, read_file_tool: ReadFileTool, tmp_path: Path, content: str) -> None:
        (tmp_path / "file.txt").write_text(content, newline="", encoding=DEFAULT_SOURCE_FILE_ENCODING)

        for line in range(len(TextUtils.split_lines(content.rstrip("\n")))):
            read_line = read_file_tool.apply("file.txt", start_line=line, end_line=line)
            assert read_line == _deleted_by_delete_lines(content, line).rstrip("\r\n")

    def test_form_feed_does_not_shift_reported_line_indices(self, read_file_tool: ReadFileTool, tmp_path: Path) -> None:
        # a form feed is a page-break convention within a line, not a line break
        (tmp_path / "file.txt").write_text("line0\n\x0cline1\nline2\n", newline="", encoding=DEFAULT_SOURCE_FILE_ENCODING)

        assert read_file_tool.apply("file.txt") == "line0\n\x0cline1\nline2\n"
        assert read_file_tool.apply("file.txt", start_line=1, end_line=1) == "\x0cline1"

    @pytest.mark.parametrize(
        "content",
        ["", "line0", "line0\n", "line0\nline1", "line0\nline1\n", "line0\n\n", "\n", "line0\r\nline1\r\n", "line0\rline1\r"],
    )
    def test_read_full_file_recovers_rejoined_lines(self, read_file_tool: ReadFileTool, tmp_path: Path, content: str) -> None:
        (tmp_path / "file.txt").write_text(content, newline="", encoding=DEFAULT_SOURCE_FILE_ENCODING)

        assert read_file_tool.apply("file.txt") == "\n".join(TextUtils.split_lines(content))
