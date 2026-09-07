"""
Tests for the REPL tool, which executes Python code against the facade entrypoint `s`.
"""

import os
from unittest.mock import MagicMock

import pytest

from serena.config.serena_config import ApiInclusionDefinition
from serena.repl.api.lsp_api import LspApi
from serena.repl.facade import ApiScope, Facade, FacadeApi, FacadeMethodInfo, facade_method
from serena.repl.repl import SerenaRepl
from serena.tools import FindSymbolTool, SerenaReplTool
from solidlsp.ls_config import LanguageServerId
from test.conftest import agent_for_project_context


class TestReplExecution:
    """Tests the code execution mechanics of the REPL, which do not require a project."""

    @pytest.fixture
    def repl(self) -> SerenaRepl:
        return SerenaRepl([Facade.from_api(LspApi(MagicMock()), ApiScope())], ApiScope())

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

        @facade_method()
        def add(self, a: int, b: int) -> int:
            """Adds two numbers."""
            return a + b

        @facade_method(can_edit=True)
        def secret(self) -> str:
            return "hidden"

        @facade_method(optional=True, beta=True)
        def extra(self) -> str:
            return "extra"

        def undecorated(self) -> str:
            """Public within Serena, but not exposed, since it is not decorated."""
            return "internal"

        def _internal(self) -> None:
            pass

    @staticmethod
    def _scope(*definitions: ApiInclusionDefinition, **kwargs: list[str]) -> ApiScope:
        """
        :param definitions: definitions to apply in order
        :param kwargs: an additional definition (`included_apis`/`excluded_apis`) to apply last
        """
        scope = ApiScope()
        for definition in definitions:
            scope.process(definition)
        if kwargs:
            scope.process(ApiInclusionDefinition(**kwargs))
        return scope

    def test_api_scope_facade_exclusion_and_method_inclusion(self) -> None:
        # excluding the facade disables everything
        facade = Facade.from_api(self.DummyApi(MagicMock()), self._scope(excluded_apis=["dummy"]))
        assert facade.enabled_method_names == []

        # an excluded facade is opt-in: a method inclusion enables exactly that method
        facade = Facade.from_api(self.DummyApi(MagicMock()), self._scope(excluded_apis=["dummy"], included_apis=["dummy.add"]))
        assert facade.enabled_method_names == ["add"]

    def test_entrypoint_omits_excluded_facades(self) -> None:
        def create_repl(scope: ApiScope) -> SerenaRepl:
            return SerenaRepl([Facade.from_api(self.DummyApi(MagicMock()), scope)], scope)

        assert "s.dummy" in create_repl(ApiScope()).execute("s.info()")
        assert "s.dummy" not in create_repl(self._scope(excluded_apis=["dummy"])).execute("s.info()")
        # a method inclusion keeps the facade available (with just that method)
        overview = create_repl(self._scope(excluded_apis=["dummy"], included_apis=["dummy.add"])).execute("s.info()")
        assert "s.dummy" in overview and "methods: add" in overview

    def test_api_scope_later_definitions_take_precedence(self) -> None:
        scope = self._scope(
            ApiInclusionDefinition(included_apis=["dummy.extra"]),
            ApiInclusionDefinition(excluded_apis=["dummy.extra", "dummy.add"]),
            ApiInclusionDefinition(included_apis=["dummy.add"]),
        )
        facade = Facade.from_api(self.DummyApi(MagicMock()), scope)
        assert set(facade.enabled_method_names) == {"add", "secret"}

    def test_api_scope_read_only_excludes_editing_methods(self) -> None:
        scope = self._scope(included_apis=["dummy.secret"])
        scope.exclude_editing()
        facade = Facade.from_api(self.DummyApi(MagicMock()), scope)
        assert facade.enabled_method_names == ["add"]

    def test_enabled_methods_delegate_to_implementation(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope())
        assert facade.add(1, 2) == 3
        assert "dummy.add(a: int, b: int) -> int" in facade.describe()
        assert "Adds two numbers." in facade.describe_method("add")

    def test_disabled_methods_are_inaccessible_and_undocumented(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), self._scope(excluded_apis=["dummy.secret"]))
        assert facade.add(1, 2) == 3
        with pytest.raises(AttributeError):
            facade.secret()
        with pytest.raises(ValueError):
            facade.describe_method("secret")
        assert "secret" not in facade.describe()
        assert "_internal" not in facade.describe()

    def test_undecorated_methods_are_not_exposed(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope())
        assert self.DummyApi(MagicMock()).undecorated() == "internal"  # usable from within Serena
        with pytest.raises(AttributeError):
            facade.undecorated()
        with pytest.raises(ValueError):
            facade.get_method("undecorated")
        assert "undecorated" not in facade.describe()
        assert "undecorated" not in facade.enabled_method_names

    def test_optional_methods_are_disabled_by_default(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope())
        assert "extra" not in facade.enabled_method_names
        with pytest.raises(AttributeError):
            facade.extra()
        facade.get_method("extra").enabled = True
        assert facade.extra() == "extra"

        # an explicit inclusion enables it
        facade = Facade.from_api(self.DummyApi(MagicMock()), self._scope(included_apis=["dummy.extra"]))
        assert "extra" in facade.enabled_method_names

    def test_corresponding_tool(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope())
        assert facade.get_method("add").info.get_corresponding_tool_name() is None

        lsp_facade = Facade.from_api(LspApi(MagicMock()), ApiScope())
        info = lsp_facade.get_method("find_symbol").info
        assert info.corresponding_tool is FindSymbolTool
        assert info.get_corresponding_tool_name() == "find_symbol"

    def test_method_info_mirrors_decorator(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope())
        assert facade.get_method("add").info == FacadeMethodInfo(name="add")
        assert facade.get_method("secret").info.can_edit
        assert facade.get_method("extra").info == FacadeMethodInfo(name="extra", optional=True, beta=True)

    def test_enablement_can_be_changed(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope())
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
