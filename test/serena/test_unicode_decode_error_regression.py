"""
Regression tests for graceful degradation when the encoding of a referenced
file differs from the project encoding.

``Project.retrieve_content_around_line`` reads files using the active project
encoding. If a referenced file uses a different encoding, the read raises a
``UnicodeDecodeError``. Both the language server based tool
(``FindReferencingSymbolsTool``) and the JetBrains based tool
(``JetBrainsFindReferencingSymbolsTool``) must degrade gracefully instead of
crashing the whole tool call.

Closes: #2017
"""

from types import SimpleNamespace
from unittest import mock

from solidlsp.ls_types import SymbolKind

from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClient
from serena.symbol import LanguageServerSymbol, ReferenceInLanguageServerSymbol
from serena.tools.jetbrains_tools import JetBrainsFindReferencingSymbolsTool
from serena.tools.symbol_tools import FindReferencingSymbolsTool

UNREADABLE_MARKER = "<unreadable: file encoding differs from project encoding>"


def _make_unicode_decode_error() -> UnicodeDecodeError:
    return UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")


def _make_ls_symbol_root(relative_path: str = "src/foo.py", name: str = "Foo") -> dict:
    return {
        "name": name,
        "kind": SymbolKind.Class,
        "location": {
            "relativePath": relative_path,
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 10, "character": 0}},
        },
        "selectionRange": {"start": {"line": 0, "character": 0}},
        "children": [],
    }


def _make_ls_referencing_symbol_tool(project: mock.MagicMock) -> FindReferencingSymbolsTool:
    """
    Builds a ``FindReferencingSymbolsTool`` wired to a mocked agent/project and
    a mocked symbol retriever, without booting a language server.
    """
    agent = mock.MagicMock()
    agent.get_active_project_or_raise.return_value = project
    agent.serena_config.default_max_tool_answer_chars = 150_000

    tool = FindReferencingSymbolsTool(agent)

    reference = ReferenceInLanguageServerSymbol(
        symbol=LanguageServerSymbol(_make_ls_symbol_root()),
        line=3,
        character=0,
    )
    retriever = mock.MagicMock()
    retriever.find_referencing_symbols.return_value = [reference]
    tool.create_language_server_symbol_retriever = mock.MagicMock(return_value=retriever)
    return tool


class TestLanguageServerTool:
    def test_references_tool_degrades_gracefully_on_unicode_decode_error(self) -> None:
        """
        When reading the content around a reference raises ``UnicodeDecodeError``,
        the tool call must not fail; the reference is included with a marker
        noting that the content is unreadable.
        """
        project = mock.MagicMock()
        project.ls_sync_file_system_changes = mock.MagicMock()
        project.retrieve_content_around_line.side_effect = _make_unicode_decode_error()
        tool = _make_ls_referencing_symbol_tool(project)

        result = tool.apply(name_path="/Foo", relative_path="src/foo.py")

        project.retrieve_content_around_line.assert_called_once_with(
            relative_file_path="src/foo.py", line=3, context_lines_before=1, context_lines_after=1
        )
        assert UNREADABLE_MARKER in result
        assert "src/foo.py" in result

    def test_references_tool_includes_content_when_read_succeeds(self) -> None:
        """
        Control case: when the file can be read normally, the surrounding code
        is included and the unreadable marker is absent.
        """
        project = mock.MagicMock()
        project.ls_sync_file_system_changes = mock.MagicMock()
        project.retrieve_content_around_line.return_value = SimpleNamespace(
            to_display_string=lambda: "    def helper():\n        pass"
        )
        tool = _make_ls_referencing_symbol_tool(project)

        result = tool.apply(name_path="/Foo", relative_path="src/foo.py")

        assert "def helper():" in result
        assert UNREADABLE_MARKER not in result


def _make_jetbrains_referencing_symbol_tool(project: mock.MagicMock) -> JetBrainsFindReferencingSymbolsTool:
    agent = mock.MagicMock()
    agent.get_active_project_or_raise.return_value = project
    agent.serena_config.default_max_tool_answer_chars = 150_000
    return JetBrainsFindReferencingSymbolsTool(agent)


class TestJetBrainsTool:
    def _run_tool(
        self,
        project: mock.MagicMock,
        symbols: list[dict],
    ) -> str:
        tool = _make_jetbrains_referencing_symbol_tool(project)
        client = mock.MagicMock()
        # Make the mock behave as a context manager that yields itself
        client.__enter__ = mock.MagicMock(return_value=client)
        client.__exit__ = mock.MagicMock(return_value=False)
        client.find_references.return_value = {"symbols": symbols}
        with mock.patch.object(JetBrainsPluginClient, "from_project", return_value=client):
            result = tool.apply(name_path="/Foo", relative_path="src/foo.py")
        return result

    def test_references_tool_degrades_gracefully_on_unicode_decode_error(self) -> None:
        """
        When reading the context of a JetBrains reference raises
        ``UnicodeDecodeError``, the reference is kept with a marker and the
        ``reference_line_no`` placeholder is still removed.
        """
        project = mock.MagicMock()
        project.retrieve_content_around_line.side_effect = _make_unicode_decode_error()
        symbols = [
            {
                "relative_path": "src/other.py",
                "name_path": "/Other",
                "type": "function",
                "reference_line_no": 3,
            }
        ]

        result = self._run_tool(project, symbols)

        project.retrieve_content_around_line.assert_called_once_with(
            relative_file_path="src/other.py", line=3, context_lines_before=1, context_lines_after=1
        )
        assert UNREADABLE_MARKER in result
        assert "src/other.py" in result
        assert "reference_line_no" not in result

    def test_references_tool_includes_context_when_read_succeeds(self) -> None:
        """
        Control case: when the file can be read normally, the context is
        included and the unreadable marker is absent.
        """
        project = mock.MagicMock()
        project.retrieve_content_around_line.return_value = SimpleNamespace(
            to_display_string=lambda: "    def other():\n        pass"
        )
        symbols = [
            {
                "relative_path": "src/other.py",
                "name_path": "/Other",
                "type": "function",
                "reference_line_no": 3,
            }
        ]

        result = self._run_tool(project, symbols)

        assert "def other():" in result
        assert UNREADABLE_MARKER not in result

    def test_external_references_are_not_read(self) -> None:
        """
        External library references (relative path starting with the external
        file prefix) must not trigger a file read at all.
        """
        project = mock.MagicMock()
        symbols = [
            {
                "relative_path": "<ext:org.example.Lib>",
                "name_path": "/Lib",
                "type": "class",
                "reference_line_no": 0,
            }
        ]

        result = self._run_tool(project, symbols)

        project.retrieve_content_around_line.assert_not_called()
        assert UNREADABLE_MARKER not in result


def test_regression_issue_2017_reproducer_text() -> None:
    """
    Guards against the exact failure described in issue #2017: a referenced
    file with non-project encoding crashing the tool call.
    """
    project = mock.MagicMock()
    project.ls_sync_file_system_changes = mock.MagicMock()
    project.retrieve_content_around_line.side_effect = _make_unicode_decode_error()
    tool = _make_ls_referencing_symbol_tool(project)

    # Must not raise, even though content reads fail
    result = tool.apply(name_path="/Foo", relative_path="src/foo.py")
    assert "foo.py" in result