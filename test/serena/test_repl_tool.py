"""
Tests for the REPL tool, which executes Python code against the facade entrypoint `s`.
"""

import os
from unittest.mock import MagicMock

import pytest

from serena.facades.api.lsp import LspApi
from serena.facades.facade import Facade, FacadeApi
from serena.facades.repl import SerenaRepl
from serena.tools import SerenaReplTool
from solidlsp.ls_config import LanguageServerId
from test.conftest import agent_for_project_context


class TestReplExecution:
    """Tests the code execution mechanics of the REPL, which do not require a project."""

    @pytest.fixture
    def repl(self) -> SerenaRepl:
        return SerenaRepl([Facade.from_api(LspApi(MagicMock()))])

    def test_return_statement_defines_result(self, repl: SerenaRepl) -> None:
        assert repl.execute("x = 20\ny = 22\nreturn x + y") == "42"

    def test_single_expression_is_evaluated(self, repl: SerenaRepl) -> None:
        assert repl.execute("1 + 2") == "3"

    def test_list_is_rendered_element_wise(self, repl: SerenaRepl) -> None:
        assert repl.execute('return ["a", "b"]') == "a\nb"

    def test_error_reports_type_message_and_line(self, repl: SerenaRepl) -> None:
        result = repl.execute("x = 1\nraise ValueError('boom')")
        assert result.startswith("ValueError: boom")
        assert "line 2" in result

    def test_syntax_error_reports_line(self, repl: SerenaRepl) -> None:
        result = repl.execute("x = 1\ny = (2")
        assert result.startswith("SyntaxError")
        assert "line 2" in result

    def test_facade_discovery(self, repl: SerenaRepl) -> None:
        overview = repl.execute("s.info()")
        assert "s.lsp" in overview
        assert "find_symbol" in overview  # method names are listed, but not signatures
        assert "name_path_pattern" not in overview
        facade_info = repl.execute('s.info("lsp")')
        assert "find_symbol(" in facade_info
        method_info = repl.execute('s.info("lsp.find_symbol")')
        assert "name_path_pattern" in method_info


class TestFacade:
    """Tests the indirection between facades and their implementations."""

    class DummyApi(FacadeApi):
        def __init__(self, agent: MagicMock) -> None:
            super().__init__(agent, name="dummy", description="a dummy facade")

        def add(self, a: int, b: int) -> int:
            """Adds two numbers."""
            return a + b

        def secret(self) -> str:
            return "hidden"

        def serena_internal_(self) -> str:
            """Public within Serena, but not LLM-facing."""
            return "internal"

        def _internal(self) -> None:
            pass

    def test_enabled_methods_delegate_to_implementation(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()))
        assert facade.add(1, 2) == 3
        assert "dummy.add(a: int, b: int) -> int" in facade.describe()
        assert "Adds two numbers." in facade.describe_method("add")

    def test_disabled_methods_are_inaccessible_and_undocumented(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), enabled_methods=["add"])
        assert facade.add(1, 2) == 3
        with pytest.raises(AttributeError):
            facade.secret()
        with pytest.raises(ValueError):
            facade.describe_method("secret")
        assert "secret" not in facade.describe()
        assert "_internal" not in facade.describe()

    def test_trailing_underscore_members_are_not_llm_facing(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()))
        assert self.DummyApi(MagicMock()).serena_internal_() == "internal"  # usable from within Serena
        with pytest.raises(AttributeError):
            facade.serena_internal_()
        with pytest.raises(ValueError):
            facade.get_method("serena_internal_")
        assert "serena_internal_" not in facade.describe()
        assert "serena_internal_" not in facade.enabled_method_names

    def test_enablement_can_be_changed(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()))
        facade.get_method("secret").enabled = False
        with pytest.raises(AttributeError):
            facade.secret()
        facade.get_method("secret").enabled = True
        assert facade.secret() == "hidden"


@pytest.mark.python
class TestLspFacade:
    _SERVICES_FILE = os.path.join("test_repo", "services.py")

    def test_find_symbol_via_repl(self) -> None:
        with agent_for_project_context(LanguageServerId.PYTHON) as agent:
            tool = agent.get_tool(SerenaReplTool)

            # a returned collection is rendered, identifying the symbol and its file
            rendered = tool.apply('return s.lsp.find_symbol("create_user")')
            assert "create_user" in rendered
            assert "services.py" in rendered

            # the underlying symbols are accessible from code, e.g. to retrieve a body without rendering the collection
            body = tool.apply(
                f'result = s.lsp.find_symbol("create_user", relative_path={self._SERVICES_FILE!r})\nreturn result.symbols[0].body'
            )
            assert body.startswith("def create_user")
