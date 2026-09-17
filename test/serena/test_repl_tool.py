"""
Tests for the REPL tool, which executes Python code against the facade entrypoint `s`.
"""

import os
from unittest.mock import MagicMock

import pytest

from serena.config.serena_config import ApiInclusionDefinition, LanguageBackend
from serena.repl.api.edit_api import EditApi
from serena.repl.api.lsp_api import LspApi
from serena.repl.external_project import ExternalProjectExecution
from serena.repl.facade import ApiScope, Facade, FacadeApi, FacadeMethodInfo, facade_method
from serena.repl.repl import SerenaRepl
from serena.session import SerenaSession
from serena.tools import FindSymbolTool, SerenaReplTool
from solidlsp.ls_config import LanguageServerId
from test.conftest import agent_for_project_context


class TestReplExecution:
    """Tests the code execution mechanics of the REPL, which do not require a project."""

    @pytest.fixture
    def repl(self) -> SerenaRepl:
        return SerenaRepl([Facade.from_api(LspApi(MagicMock()), ApiScope())], ApiScope())

    def test_last_expression_defines_result(self, repl: SerenaRepl) -> None:
        assert repl.execute("x = 20\ny = 22\nx + y") == "42"
        assert repl.execute("x = 20\ny = 22") == "None"  # no trailing expression
        assert repl.execute("") == "None"

    def test_return_yields_a_hint(self, repl: SerenaRepl) -> None:
        result = repl.execute("x = 1\nreturn x")
        assert result.startswith("SyntaxError") and "line 2" in result
        assert "last expression is the result" in result

    def test_single_expression_is_evaluated(self, repl: SerenaRepl) -> None:
        assert repl.execute("1 + 2") == "3"

    def test_list_is_rendered_element_wise(self, repl: SerenaRepl) -> None:
        assert repl.execute('["a", "b"]') == "a\nb"

    def test_error_reports_type_message_and_line(self, repl: SerenaRepl) -> None:
        result = repl.execute("x = 1\nraise ValueError('boom')")
        assert result.startswith("ValueError: boom")
        assert "line 2" in result

    def test_syntax_error_reports_line(self, repl: SerenaRepl) -> None:
        result = repl.execute("x = 1\ny = (2")
        assert result.startswith("SyntaxError")
        assert "line 2" in result

    def test_top_level_names_persist_within_session(self, repl: SerenaRepl) -> None:
        session = SerenaSession("a")
        repl.execute("x = 20\ndef double(v):\n    return 2 * v\nfor i in range(3):\n    pass\nimport os as os_module", session)
        assert repl.execute("double(x) + i", session) == "42"
        assert repl.execute("os_module.sep is not None", session) == "True"

        # local variables of nested scopes do not persist; persisted items can be listed and cleared
        assert "v" not in repl.execute("s.vars()", session)
        listing = repl.execute("s.vars()", session)
        assert "x: int = 20" in listing and "double: function" in listing
        assert repl.execute("s.clear()", session) == "Removed 4 persisted item(s)."
        assert repl.execute("s.vars()", session) == "No persisted variables."
        assert "NameError" in repl.execute("x", session)

    def test_sessions_have_separate_namespaces(self, repl: SerenaRepl) -> None:
        session_a = SerenaSession("a")
        repl.execute("x = 1", session_a)
        assert "NameError" in repl.execute("x", SerenaSession("b"))
        assert repl.execute("x", session_a) == "1"
        # ... and execution without a session persists nothing
        repl.execute("y = 1")
        assert "NameError" in repl.execute("y")

    def test_persisted_functions_use_the_current_entrypoint(self) -> None:
        # a function defined against one REPL instance uses the entrypoint of the REPL that later calls it
        session = SerenaSession("a")
        SerenaRepl([Facade.from_api(LspApi(MagicMock()), ApiScope())], ApiScope()).execute("def facades():\n    return s.info()", session)
        rebuilt_repl = SerenaRepl([Facade.from_api(EditApi(MagicMock()), ApiScope())], ApiScope())
        overview = rebuilt_repl.execute("facades()", session)
        assert "s.edit" in overview and "s.lsp" not in overview

    @pytest.mark.parametrize("backend", [LanguageBackend.LSP, LanguageBackend.JETBRAINS])
    @pytest.mark.parametrize("read_only", [True, False])
    def test_external_project_dispatch(self, backend: LanguageBackend, read_only: bool) -> None:
        agent = MagicMock()
        agent.get_language_backend.return_value = backend

        class FakeExternalProject(ExternalProjectExecution):
            def __init__(self) -> None:
                super().__init__("other", read_only=read_only, agent=agent)
                self.calls: list[tuple[str, str, tuple, dict]] = []

            def call_remotely(self, facade_name: str, method_name: str, args: tuple, kwargs: dict) -> str:
                self.calls.append((facade_name, method_name, args, kwargs))
                return "remote result"

        class LocalApi(FacadeApi):
            @facade_method(can_edit=True)
            def write(self, content: str) -> str:
                return f"local result: {content}"

        # expose a server-backed read and a backend-dependent write
        facades = [Facade.from_api(LspApi(agent), ApiScope()), Facade.from_api(LocalApi(agent, "local", "local operations"), ApiScope())]
        repl = SerenaRepl(facades, ApiScope())
        external_project = FakeExternalProject()
        repl.entrypoint.set_external_project_(external_project)

        # methods explicitly requiring the project server are executed remotely
        assert repl.execute('s.lsp.find_symbol("Foo", depth=1)') == "remote result"
        assert external_project.calls == [("lsp", "find_symbol", ("Foo",), {"depth": 1})]

        # writes obey the context's access mode and use the selected backend
        result = repl.execute('s.local.write("content")')
        if read_only:
            assert "PermissionError" in result and "read-only" in result
            assert len(external_project.calls) == 1
        elif backend.is_lsp():
            assert result == "remote result"
            assert external_project.calls[-1] == ("local", "write", ("content",), {})
        else:
            assert result == "local result: content"
            assert len(external_project.calls) == 1

        # leaving the external execution context restores local execution
        repl.entrypoint.set_external_project_(None)
        assert repl.execute('s.local.write("restored")') == "local result: restored"

    def test_facade_discovery(self, repl: SerenaRepl) -> None:
        overview = repl.execute("s.info()")
        assert "s.lsp" in overview
        assert "find_symbol" in overview  # method names are listed, but not signatures
        assert "name_path_pattern" not in overview
        facade_info = repl.execute('s.info("lsp")')
        assert "find_symbol(" in facade_info
        method_info = repl.execute('s.info("lsp.find_symbol")')
        assert "name_path_pattern" in method_info

    def test_type_discovery(self, repl: SerenaRepl) -> None:
        # the overview names the result types of methods returning objects that can be processed in code
        assert "find_symbol -> LspSymbolCollection" in repl.execute("s.info()")

        # signatures render type names without module paths, and point to the documentation of referenced return types
        method_info = repl.execute('s.info("lsp.find_symbol")')
        assert "-> LspSymbolCollection" in method_info and "lsp_api." not in method_info
        assert 's.info("LspSymbolCollection")' in method_info

        # the facade description documents the operations only and lists the result types by name
        facade_info = repl.execute('s.info("lsp")')
        assert "type LspSymbolCollection" not in facade_info
        assert "Result types: " in facade_info and "LspSymbolCollection" in facade_info

        # types can be requested via the facade or by bare name, and their curated members are documented
        type_info = repl.execute('s.info("lsp.LanguageServerSymbol")')
        assert type_info == repl.execute('s.info("LanguageServerSymbol")')
        assert "get_name_path() -> str" in type_info and "iter_children()" in type_info
        assert "to_dict" not in type_info  # not among the curated members

        # types reachable through annotations are documented without being declared: SymbolKind (a parameter type of
        # iter_ancestors) is documented as an enum with its members, both transitively and on request
        assert "enum SymbolKind" in type_info and "SymbolKind.Class = 5" in type_info
        assert "enum SymbolKind" in repl.execute('s.info("SymbolKind")')

        # TypedDicts reachable through annotations are documented with their keys
        assert "keys:" in repl.execute('s.info("Diagnostic")') and "severity" in repl.execute('s.info("Diagnostic")')
        assert "represent()" not in repl.execute('s.info("LspSymbolCollection")')  # the representation mechanism is not exposed

    def test_contained_types_are_documented_once_per_session(self, repl: SerenaRepl) -> None:
        session = SerenaSession("test")

        # a type's documentation includes the types it contains (transitively)
        first = repl.execute('s.info("LspReferenceCollection")', session)
        assert "type LspReferenceCollection" in first
        assert "type ReferenceInLanguageServerSymbol" in first and "type LanguageServerSymbol" in first

        # a contained type documented earlier in the session is only pointed to; an explicit request yields it again
        second = repl.execute('s.info("LspSymbolCollection")', session)
        assert "type LspSymbolCollection" in second
        assert "type LanguageServerSymbol: documented earlier" in second and "get_name_path()" not in second
        assert "get_name_path()" in repl.execute('s.info("LanguageServerSymbol")', session)

        # another session is unaffected
        assert "get_name_path()" in repl.execute('s.info("LspSymbolCollection")', SerenaSession("other"))

    def test_info_documents_several_items(self, repl: SerenaRepl) -> None:
        info = repl.execute('s.info("lsp.find_symbol", "nope", "lsp.LspSymbolCollection")')
        assert "lsp.find_symbol(" in info and "type LspSymbolCollection" in info
        assert "Unknown item 'nope'" in info  # an unknown item does not prevent the documentation of the others


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

        @facade_method(niche=True)
        def rarely(self, x: int) -> str:
            """Rarely needed operation.

            :param x: some parameter
            """
            return str(x)

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

    def test_optional_facade_is_opt_in(self) -> None:
        # an optional facade is disabled unless it is included explicitly
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope(), is_optional=True)
        assert not facade.is_enabled()
        assert facade.enabled_method_names == []

        # including the facade enables its non-optional methods
        facade = Facade.from_api(self.DummyApi(MagicMock()), self._scope(included_apis=["dummy"]), is_optional=True)
        assert facade.is_enabled()
        assert set(facade.enabled_method_names) == {"add", "secret", "rarely"}

        # including a single method enables the facade with just that method
        facade = Facade.from_api(self.DummyApi(MagicMock()), self._scope(included_apis=["dummy.add"]), is_optional=True)
        assert facade.is_enabled()
        assert facade.enabled_method_names == ["add"]

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
        assert set(facade.enabled_method_names) == {"add", "secret", "rarely"}

    def test_api_scope_read_only_excludes_editing_methods(self) -> None:
        scope = self._scope(included_apis=["dummy.secret"])
        scope.exclude_editing()
        facade = Facade.from_api(self.DummyApi(MagicMock()), scope)
        assert set(facade.enabled_method_names) == {"add", "rarely"}

    def test_enabled_methods_delegate_to_implementation(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope())
        assert facade.add(1, 2) == 3
        assert "dummy.add(a: int, b: int) -> int" in facade.describe()
        assert "Adds two numbers." in facade.describe_member("add")

    def test_disabled_methods_are_inaccessible_and_undocumented(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), self._scope(excluded_apis=["dummy.secret"]))
        assert facade.add(1, 2) == 3
        with pytest.raises(AttributeError):
            facade.secret()
        with pytest.raises(ValueError):
            facade.describe_member("secret")
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

    def test_niche_methods_are_summarised_in_facade_description(self) -> None:
        facade = Facade.from_api(self.DummyApi(MagicMock()), ApiScope())
        description = facade.describe()
        assert "dummy.rarely: Rarely needed operation." in description
        assert ":param x:" not in description  # only the summary, no signature or full documentation
        assert ":param x:" in facade.describe_member("rarely")  # full documentation on request

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
            session_id = agent.create_session().session_id

            # a returned collection is rendered, identifying the symbol and its file
            rendered = tool.apply(session_id, 's.lsp.find_symbol("create_user")')
            assert "create_user" in rendered
            assert "services.py" in rendered

            # the underlying symbols are accessible from code, e.g. to retrieve a body without rendering the collection
            body = tool.apply(
                session_id,
                f'result = s.lsp.find_symbol("create_user", relative_path={self._SERVICES_FILE!r})\nresult.symbols[0].body',
            )
            assert body.startswith("def create_user")
