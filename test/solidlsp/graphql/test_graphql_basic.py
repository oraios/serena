"""
Basic integration tests for the GraphQL language server (graphql-language-service-cli).

The server uses graphql-config (``.graphqlrc.yml`` at the repo root) to link the SDL
schema with the operation documents, so this suite exercises single-file document
symbols as well as cross-file go-to-definition from an operation field into the schema
type that declares it.

Note: ``graphql-language-service-cli`` does not implement ``textDocument/references``,
so find-references is intentionally not covered here — cross-file navigation is verified
through go-to-definition instead.
"""

import os
import re
from pathlib import Path

import pytest

from serena.util.text_utils import find_text_coordinates
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_types import SymbolKind
from test.solidlsp.conftest import read_repo_file, request_all_symbols

# graphql-language-service reports both SDL type definitions and operation definitions with
# the Class kind, and their fields/selections with the Field kind.
TYPE_KINDS = {SymbolKind.Class, SymbolKind.Struct, SymbolKind.Interface, SymbolKind.Enum, SymbolKind.Object}
FIELD_KINDS = {SymbolKind.Field, SymbolKind.Property}


@pytest.mark.graphql
class TestGraphqlLanguageServerBasics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.GRAPHQL], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_schema_type_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Every top-level type/enum/input in the SDL schema must surface as a symbol."""
        all_symbols, _ = language_server.request_document_symbols("schema.graphql").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for type_name in ("Query", "Mutation", "User", "Post", "Role", "CreateUserInput"):
            assert type_name in names, f"Expected type {type_name!r} to appear in schema symbols: {names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_schema_field_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Field definitions within the schema types must surface as symbols too."""
        all_symbols, _ = language_server.request_document_symbols("schema.graphql").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for field_name in ("email", "title", "published", "createUser"):
            assert field_name in names, f"Expected field {field_name!r} to appear in schema symbols: {names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_query_operation_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("operations/queries.graphql").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for op_name in ("GetUser", "GetPosts", "SearchUsers"):
            assert op_name in names, f"Expected operation {op_name!r} to appear in query symbols: {names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_mutation_operation_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("operations/mutations.graphql").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        for op_name in ("CreateUser", "CreatePost"):
            assert op_name in names, f"Expected operation {op_name!r} to appear in mutation symbols: {names}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_symbol_kinds(self, language_server: SolidLanguageServer) -> None:
        """Type definitions must be classified as a type-like kind and their fields as fields."""
        all_symbols, _ = language_server.request_document_symbols("schema.graphql").get_all_symbols_and_roots()
        by_name = {s["name"]: s for s in all_symbols}
        assert "User" in by_name, f"'User' type missing from symbols: {list(by_name)}"
        assert "email" in by_name, f"'email' field missing from symbols: {list(by_name)}"
        user_kind = SymbolKind(by_name["User"]["kind"])
        email_kind = SymbolKind(by_name["email"]["kind"])
        assert user_kind in TYPE_KINDS, f"Expected 'User' to be a type-like kind, got {user_kind.name}"
        assert email_kind in FIELD_KINDS, f"Expected 'email' to be a field-like kind, got {email_kind.name}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_full_symbol_tree_includes_all_files(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        relative_paths = {s.get("location", {}).get("relativePath") for s in all_symbols}
        for f in ("schema.graphql", os.path.join("operations", "queries.graphql"), os.path.join("operations", "mutations.graphql")):
            assert f in relative_paths, f"Expected {f} to appear in symbol tree: {sorted(p for p in relative_paths if p)}"


@pytest.mark.graphql
class TestGraphqlDefinition:
    """graphql-config links operations to the schema, enabling cross-file go-to-definition."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_cross_file_definition_query_field(self, language_server: SolidLanguageServer) -> None:
        """`user(id: ...)` in queries.graphql must resolve into the ``Query.user`` field in schema.graphql."""
        path = "operations/queries.graphql"
        needle = "user(id"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        definitions = language_server.request_definition(path, coords.line, coords.col + 1)
        assert definitions, f"Expected non-empty cross-file definition list for 'user', got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("schema.graphql") for uri in target_uris), (
            f"Expected 'user' definition to resolve into schema.graphql, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_cross_file_definition_nested_field(self, language_server: SolidLanguageServer) -> None:
        """A nested selection field (`email`) must resolve into its ``User.email`` schema definition."""
        path = "operations/queries.graphql"
        needle = "email"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        definitions = language_server.request_definition(path, coords.line, coords.col + 1)
        assert definitions, f"Expected non-empty cross-file definition list for 'email', got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("schema.graphql") for uri in target_uris), (
            f"Expected 'email' definition to resolve into schema.graphql, got URIs: {target_uris}"
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_within_file_definition_type_reference(self, language_server: SolidLanguageServer) -> None:
        """`author: User!` in schema.graphql must resolve to the ``type User`` definition (same file)."""
        path = "schema.graphql"
        needle = "author: User!"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        # Cursor on the `User` type reference (skip past `author: `).
        col = coords.col + len("author: U")
        definitions = language_server.request_definition(path, coords.line, col)
        assert definitions, f"Expected non-empty definition list for 'User' type reference, got {definitions}"
        target_uris = [d["uri"] for d in definitions]
        assert any(uri.endswith("schema.graphql") for uri in target_uris), (
            f"Expected 'User' type reference to resolve within schema.graphql, got URIs: {target_uris}"
        )


@pytest.mark.graphql
class TestGraphqlHover:
    """graphql-language-service returns typed hover content backed by the schema."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_hover_on_query_field(self, language_server: SolidLanguageServer) -> None:
        path = "operations/queries.graphql"
        needle = "user(id"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        hover = language_server.request_hover(path, coords.line, coords.col + 1)
        assert hover is not None, f"Expected hover info for 'user' in {path}, got None"
        contents = hover.get("contents")
        assert contents, f"Expected non-empty hover contents, got: {hover}"
        text = contents["value"] if isinstance(contents, dict) else str(contents)
        assert "Query.user" in text, f"Expected hover to describe 'Query.user', got: {text}"

    @pytest.mark.parametrize("language_server", [LanguageServerId.GRAPHQL], indirect=True)
    def test_hover_on_scalar_field(self, language_server: SolidLanguageServer) -> None:
        path = "operations/queries.graphql"
        needle = "email"
        coords = find_text_coordinates(read_repo_file(language_server, path), f"({re.escape(needle)})")
        assert coords is not None, f"Could not find {needle!r} in {path}"
        hover = language_server.request_hover(path, coords.line, coords.col + 1)
        assert hover is not None, f"Expected hover info for 'email' in {path}, got None"
        contents = hover.get("contents")
        assert contents, f"Expected non-empty hover contents, got: {hover}"
        text = contents["value"] if isinstance(contents, dict) else str(contents)
        assert "email" in text and "String" in text, f"Expected hover to describe 'User.email: String!', got: {text}"
