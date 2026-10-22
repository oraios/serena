"""Normalization of Erlang's ``name/arity`` symbol identifiers.

Reproduces https://github.com/oraios/serena/issues/1797: ELP names functions, types and
parameterised macros ``name/arity`` (e.g. ``create_user/4``), but ``/`` separates the components of
a Serena name path. Such a name was therefore parsed as "symbol ``4`` nested inside ``create_user``"
and could never be matched -- not even by the very name path Serena itself reported for the symbol.
In practice that made ``find_referencing_symbols``, ``replace_symbol_body`` and
``insert_after_symbol`` unusable on Erlang functions, while read-only browsing kept working, so the
language looked supported until one tried to do anything with a function.

``ErlangLanguageServer._normalize_symbol_name`` now substitutes
:data:`~solidlsp.language_servers.erlang_language_server.ARITY_SEPARATOR` for the ``/``, which makes
the reported name path round-trip back into the symbol tools.
"""

import os

import pytest

from serena.project import Project
from serena.symbol import LanguageServerSymbolRetriever
from solidlsp.language_servers.erlang_language_server import ARITY_SEPARATOR
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_types import SymbolKind, UnifiedSymbolInformation
from test.conftest import language_server_tests_enabled

pytestmark = [
    pytest.mark.erlang,
    pytest.mark.skipif(not language_server_tests_enabled(LanguageServerId.ERLANG), reason="Erlang tests are disabled"),
]

MODELS_ERL = os.path.join("src", "models.erl")
SERVICES_ERL = os.path.join("src", "services.erl")
RECORDS_HRL = os.path.join("include", "records.hrl")

# `models:create_user/4`, spelled the way Serena addresses it
CREATE_USER_4 = f"create_user{ARITY_SEPARATOR}4"

# file and directory symbols are named after path components, so `/` is legitimate for them
CONTAINER_KINDS = (SymbolKind.File, SymbolKind.Package)


class TestErlangSymbolNames:
    @pytest.mark.parametrize("project_with_ls", [LanguageServerId.ERLANG], indirect=True)
    def test_no_symbol_name_contains_the_name_path_separator(self, project_with_ls: Project) -> None:
        """No Erlang symbol may carry a `/` in its name, since that is the name path separator."""
        offenders: list[str] = []

        def visit(symbol: UnifiedSymbolInformation) -> None:
            if symbol["kind"] not in CONTAINER_KINDS and "/" in symbol["name"]:
                offenders.append(symbol["name"])
            for child in symbol.get("children", []):
                visit(child)

        for ls in project_with_ls.get_language_server_manager_or_raise().iter_language_servers():
            for root in ls.request_full_symbol_tree():
                visit(root)

        assert not offenders, f"Symbol names containing the name path separator: {sorted(set(offenders))}"

    @pytest.mark.parametrize("project_with_ls", [LanguageServerId.ERLANG], indirect=True)
    def test_function_name_path_round_trips(self, project_with_ls: Project) -> None:
        """The name path reported for a function must find that same function again."""
        retriever = LanguageServerSymbolRetriever(project_with_ls)

        symbol = retriever.find_unique(CREATE_USER_4, within_relative_path=MODELS_ERL)
        assert symbol.symbol_kind == SymbolKind.Function
        assert symbol.get_name_path() == CREATE_USER_4

        # feeding the reported name path back in is what used to yield no match at all
        assert [s.get_name_path() for s in retriever.find(symbol.get_name_path())] == [CREATE_USER_4]

    @pytest.mark.parametrize("project_with_ls", [LanguageServerId.ERLANG], indirect=True)
    def test_arity_remains_part_of_the_name(self, project_with_ls: Project) -> None:
        """The arity is kept rather than stripped: it is part of a function's identity in Erlang."""
        retriever = LanguageServerSymbolRetriever(project_with_ls)

        # models:create_order/3 and services:create_order/2 are different functions
        models_create_order = retriever.find_unique(f"create_order{ARITY_SEPARATOR}3")
        services_create_order = retriever.find_unique(f"create_order{ARITY_SEPARATOR}2")

        assert models_create_order.relative_path is not None
        assert models_create_order.relative_path.replace("\\", "/") == "src/models.erl"
        assert services_create_order.relative_path is not None
        assert services_create_order.relative_path.replace("\\", "/") == "src/services.erl"

    @pytest.mark.parametrize("project_with_ls", [LanguageServerId.ERLANG], indirect=True)
    def test_find_referencing_symbols_locates_a_function(self, project_with_ls: Project) -> None:
        """The headline symptom of #1797: this used to raise `No symbol matching ...`."""
        retriever = LanguageServerSymbolRetriever(project_with_ls)

        references = retriever.find_referencing_symbols(CREATE_USER_4, MODELS_ERL)

        # create_user/4 is called from models.erl itself and from at least one other module
        referencing_paths = {r.symbol.relative_path.replace("\\", "/") for r in references if r.symbol.relative_path is not None}
        assert referencing_paths, f"Expected references to {CREATE_USER_4}, got none"
        assert referencing_paths - {"src/models.erl"}, f"Expected cross-file references, got only {referencing_paths}"

    @pytest.mark.parametrize("project_with_ls", [LanguageServerId.ERLANG], indirect=True)
    def test_names_without_an_arity_are_untouched(self, project_with_ls: Project) -> None:
        """Records and macros have no arity, so normalization must leave their names alone."""
        retriever = LanguageServerSymbolRetriever(project_with_ls)

        user_record = retriever.find_unique("user", within_relative_path=RECORDS_HRL)
        assert user_record.name == "user"
