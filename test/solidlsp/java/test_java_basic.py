import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import (
    find_identifier_position,
    get_repo_path,
    language_has_verified_implementation_support,
    language_tests_enabled,
)
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols

pytestmark = [pytest.mark.java, pytest.mark.skipif(not language_tests_enabled(Language.JAVA), reason="Java tests disabled")]


class TestJavaLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model class not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        # Use correct Maven/Java file paths
        file_path = os.path.join("src", "main", "java", "test_repo", "Utils.java")
        refs = language_server.request_references(file_path, 4, 20)
        assert any("Main.java" in ref.get("relativePath", "") for ref in refs), "Main should reference Utils.printHello"

        # Dynamically determine the correct line/column for the 'Model' class name
        file_path = os.path.join("src", "main", "java", "test_repo", "Model.java")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        model_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "Model" and sym.get("kind") == 5:  # 5 = Class
                model_symbol = sym
                break
        assert model_symbol is not None, "Could not find 'Model' class symbol in Model.java"
        # Use selectionRange if present, otherwise fall back to range
        if "selectionRange" in model_symbol:
            sel_start = model_symbol["selectionRange"]["start"]
        else:
            sel_start = model_symbol["range"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("Main.java" in ref.get("relativePath", "") for ref in refs), (
            "Main should reference Model (tried all positions in selectionRange)"
        )

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_overview_methods(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model missing from overview"

    if language_has_verified_implementation_support(Language.JAVA):

        @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.JAVA)
            pos = find_identifier_position(repo_path / "src/main/java/test_repo/Greeter.java", "formatGreeting")
            assert pos is not None, "Could not find Greeter.formatGreeting in fixture"

            implementations = language_server.request_implementation("src/main/java/test_repo/Greeter.java", *pos)
            assert implementations, "Expected at least one implementation of Greeter.formatGreeting"
            assert any("ConsoleGreeter.java" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected ConsoleGreeter.formatGreeting in implementations, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.JAVA)
            pos = find_identifier_position(repo_path / "src/main/java/test_repo/Greeter.java", "formatGreeting")
            assert pos is not None, "Could not find Greeter.formatGreeting in fixture"

            implementing_symbols = language_server.request_implementing_symbols("src/main/java/test_repo/Greeter.java", *pos)
            assert implementing_symbols, "Expected implementing symbols for Greeter.formatGreeting"
            assert any(
                symbol.get("name") == "formatGreeting" and "ConsoleGreeter.java" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected ConsoleGreeter.formatGreeting symbol, got: {implementing_symbols}"

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_lombok_generated_methods_visible_by_default(self, language_server: SolidLanguageServer) -> None:
        """Generated Lombok methods must appear in document symbols across the common annotations.

        Default `lombok_show_generated=True` sends `java.symbols.includeGeneratedCode=true` to JDTLS,
        which disables the SourceMethod-isGenerated filter in DocumentSymbolHandler. Without it,
        find_symbol/get_symbols_overview cannot reach Lombok-synthesised methods at all (#1432).
        Covers @Data, @Builder(toBuilder=true), @With, @AllArgsConstructor, @NoArgsConstructor,
        @Delegate and @Accessors(fluent=true) — every method-generating annotation listed in the
        issue plus fluent prefix-stripped accessors and @Delegate forwarders.
        """

        def _names_by_kind(doc, kind: int) -> set[str]:
            return {sym.get("name") for sym in doc.get_all_symbols_and_roots()[0] if sym.get("kind") == kind}

        SYMBOL_KIND_CLASS = 5
        SYMBOL_KIND_METHOD = 6
        SYMBOL_KIND_CONSTRUCTOR = 9

        # ---- LombokModel: @Data + @Builder(toBuilder=true) + @With + ctors + @Delegate -------
        lombok_path = os.path.join("src", "main", "java", "test_repo", "LombokModel.java")
        lombok_doc = language_server.request_document_symbols(lombok_path)

        lombok_methods = _names_by_kind(lombok_doc, SYMBOL_KIND_METHOD)
        # @Data getters/setters (prefixed) + canonical Object overrides
        for expected in ("getName", "getAge", "setName", "setAge", "equals", "hashCode", "toString"):
            assert expected in lombok_methods, f"@Data did not surface {expected!r}; got: {sorted(lombok_methods)}"
        # @Builder(toBuilder=true): static factory + instance toBuilder + inner build()
        for expected in ("builder", "toBuilder", "build"):
            assert expected in lombok_methods, f"@Builder did not surface {expected!r}; got: {sorted(lombok_methods)}"
        # @With: copy-with methods
        for expected in ("withName", "withAge"):
            assert expected in lombok_methods, f"@With did not surface {expected!r}; got: {sorted(lombok_methods)}"
        # @Delegate: forwarder methods for every method of the delegate target
        for expected in ("greet", "farewell"):
            assert expected in lombok_methods, f"@Delegate did not surface forwarder {expected!r}; got: {sorted(lombok_methods)}"

        # @Builder generates an inner builder class
        lombok_classes = _names_by_kind(lombok_doc, SYMBOL_KIND_CLASS)
        assert "LombokModelBuilder" in lombok_classes, f"@Builder inner class missing; got: {sorted(lombok_classes)}"

        # @AllArgsConstructor + @NoArgsConstructor surface as ctor symbols (kind=9)
        lombok_ctors = _names_by_kind(lombok_doc, SYMBOL_KIND_CONSTRUCTOR)
        assert "LombokModel" in lombok_ctors, f"Lombok ctors missing; got ctors {sorted(lombok_ctors)}"

        # ---- FluentLombokModel: @Accessors(fluent=true) - prefix-stripped accessors ---------
        fluent_path = os.path.join("src", "main", "java", "test_repo", "FluentLombokModel.java")
        fluent_doc = language_server.request_document_symbols(fluent_path)
        fluent_methods = _names_by_kind(fluent_doc, SYMBOL_KIND_METHOD)
        for expected in ("host", "tag"):
            assert expected in fluent_methods, f"@Accessors(fluent=true) did not surface {expected!r}; got: {sorted(fluent_methods)}"
