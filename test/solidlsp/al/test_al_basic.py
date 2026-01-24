import os

import pytest

from murena.symbol import LanguageServerSymbol
from solidlsp import SolidLanguageServer
from solidlsp.language_servers.al_language_server import ALLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import language_tests_enabled

pytestmark = [pytest.mark.al, pytest.mark.skipif(not language_tests_enabled(Language.AL), reason="AL tests are disabled")]


class TestExtractALDisplayName:
    """Tests for the ALLanguageServer._extract_al_display_name method."""

    def test_table_with_quoted_name(self) -> None:
        """Test extraction from Table with quoted name."""
        assert ALLanguageServer._extract_al_display_name('Table 50000 "TEST Customer"') == "TEST Customer"

    def test_page_with_quoted_name(self) -> None:
        """Test extraction from Page with quoted name."""
        assert ALLanguageServer._extract_al_display_name('Page 50001 "TEST Customer Card"') == "TEST Customer Card"

    def test_codeunit_unquoted(self) -> None:
        """Test extraction from Codeunit with unquoted name."""
        assert ALLanguageServer._extract_al_display_name("Codeunit 50000 CustomerMgt") == "CustomerMgt"

    def test_enum_unquoted(self) -> None:
        """Test extraction from Enum with unquoted name."""
        assert ALLanguageServer._extract_al_display_name("Enum 50000 CustomerType") == "CustomerType"

    def test_interface_no_id(self) -> None:
        """Test extraction from Interface (no ID)."""
        assert ALLanguageServer._extract_al_display_name("Interface IPaymentProcessor") == "IPaymentProcessor"

    def test_table_extension(self) -> None:
        """Test extraction from TableExtension."""
        assert ALLanguageServer._extract_al_display_name('TableExtension 50000 "Ext Customer"') == "Ext Customer"

    def test_page_extension(self) -> None:
        """Test extraction from PageExtension."""
        assert ALLanguageServer._extract_al_display_name('PageExtension 50000 "My Page Ext"') == "My Page Ext"

    def test_non_al_object_unchanged(self) -> None:
        """Test that non-AL-object names pass through unchanged."""
        assert ALLanguageServer._extract_al_display_name("fields") == "fields"
        assert ALLanguageServer._extract_al_display_name("CreateCustomer") == "CreateCustomer"
        assert ALLanguageServer._extract_al_display_name("Name") == "Name"

    def test_report_with_quoted_name(self) -> None:
        """Test extraction from Report."""
        assert ALLanguageServer._extract_al_display_name('Report 50000 "Sales Invoice"') == "Sales Invoice"

    def test_query_unquoted(self) -> None:
        """Test extraction from Query."""
        assert ALLanguageServer._extract_al_display_name("Query 50000 CustomerQuery") == "CustomerQuery"


@pytest.mark.al
class TestALLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_symbol_names_are_normalized(self, language_server: SolidLanguageServer) -> None:
        """Test that AL symbol names are normalized (metadata stripped)."""
        file_path = os.path.join("src", "Tables", "Customer.Table.al")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        _all_symbols, root_symbols = symbols
        customer_table = None
        for sym in root_symbols:
            if sym.get("name") == "TEST Customer":
                customer_table = sym
                break

        assert customer_table is not None, "Could not find 'TEST Customer' table symbol (name should be normalized)"
        # Name should be just "TEST Customer", not "Table 50000 'TEST Customer'"
        assert customer_table["name"] == "TEST Customer", f"Expected normalized name 'TEST Customer', got '{customer_table['name']}'"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_symbol_exact_match(self, language_server: SolidLanguageServer) -> None:
        """Test that find_symbol can match AL symbols by normalized name without substring_matching."""
        file_path = os.path.join("src", "Tables", "Customer.Table.al")
        symbols = language_server.request_document_symbols(file_path)

        # Find symbols that match 'TEST Customer' using LanguageServerSymbol.find()
        for root in symbols.root_symbols:
            ls_symbol = LanguageServerSymbol(root)
            matches = ls_symbol.find("TEST Customer", substring_matching=False)
            if matches:
                assert len(matches) >= 1, "Should find at least one match for 'TEST Customer'"
                assert matches[0].name == "TEST Customer", f"Expected 'TEST Customer', got '{matches[0].name}'"
                return

        pytest.fail("Could not find 'TEST Customer' symbol by exact name match")

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_codeunit_exact_match(self, language_server: SolidLanguageServer) -> None:
        """Test finding a codeunit by its normalized name."""
        file_path = os.path.join("src", "Codeunits", "CustomerMgt.Codeunit.al")
        symbols = language_server.request_document_symbols(file_path)

        for root in symbols.root_symbols:
            ls_symbol = LanguageServerSymbol(root)
            matches = ls_symbol.find("CustomerMgt", substring_matching=False)
            if matches:
                assert len(matches) >= 1
                assert matches[0].name == "CustomerMgt"
                return

        pytest.fail("Could not find 'CustomerMgt' symbol by exact name match")

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that AL Language Server can find symbols in the test repository with normalized names."""
        symbols = language_server.request_full_symbol_tree()

        # Check for table symbols - names should be normalized (no "Table 50000" prefix)
        assert SymbolUtils.symbol_tree_contains_name(symbols, "TEST Customer"), "TEST Customer table not found in symbol tree"

        # Check for page symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "TEST Customer Card"), "TEST Customer Card page not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "TEST Customer List"), "TEST Customer List page not found in symbol tree"

        # Check for codeunit symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CustomerMgt"), "CustomerMgt codeunit not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, "PaymentProcessorImpl"
        ), "PaymentProcessorImpl codeunit not found in symbol tree"

        # Check for enum symbol
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CustomerType"), "CustomerType enum not found in symbol tree"

        # Check for interface symbol
        assert SymbolUtils.symbol_tree_contains_name(symbols, "IPaymentProcessor"), "IPaymentProcessor interface not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_table_fields(self, language_server: SolidLanguageServer) -> None:
        """Test that AL Language Server can find fields within a table."""
        file_path = os.path.join("src", "Tables", "Customer.Table.al")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # AL tables should have their fields as child symbols
        customer_table = None
        _all_symbols, root_symbols = symbols
        for sym in root_symbols:
            if sym.get("name") == "TEST Customer":
                customer_table = sym
                break

        assert customer_table is not None, "Could not find TEST Customer table symbol"

        # Check for field symbols (AL nests fields under a "fields" group)
        if "children" in customer_table:
            # Find the fields group
            fields_group = None
            for child in customer_table.get("children", []):
                if child.get("name") == "fields":
                    fields_group = child
                    break

            assert fields_group is not None, "Fields group not found in Customer table"

            # Check actual field names
            if "children" in fields_group:
                field_names = [child.get("name", "") for child in fields_group.get("children", [])]
                assert any("Name" in name for name in field_names), f"Name field not found. Fields: {field_names}"
                assert any("Balance" in name for name in field_names), f"Balance field not found. Fields: {field_names}"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_procedures(self, language_server: SolidLanguageServer) -> None:
        """Test that AL Language Server can find procedures in codeunits."""
        file_path = os.path.join("src", "Codeunits", "CustomerMgt.Codeunit.al")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Find the codeunit symbol - name should be normalized to 'CustomerMgt'
        codeunit_symbol = None
        _all_symbols, root_symbols = symbols
        for sym in root_symbols:
            if sym.get("name") == "CustomerMgt":
                codeunit_symbol = sym
                break

        assert codeunit_symbol is not None, "Could not find CustomerMgt codeunit symbol"

        # Check for procedure symbols (if hierarchical)
        if "children" in codeunit_symbol:
            procedure_names = [child.get("name", "") for child in codeunit_symbol.get("children", [])]
            assert any("CreateCustomer" in name for name in procedure_names), "CreateCustomer procedure not found"
            assert any("TestNoSeries" in name for name in procedure_names), "TestNoSeries procedure not found"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that AL Language Server can find references to symbols."""
        # Find references to the Customer table from the CustomerMgt codeunit
        table_file = os.path.join("src", "Tables", "Customer.Table.al")
        symbols = language_server.request_document_symbols(table_file).get_all_symbols_and_roots()

        # Find the Customer table symbol (name is normalized)
        customer_symbol = None
        _all_symbols, root_symbols = symbols
        for sym in root_symbols:
            if sym.get("name") == "TEST Customer":
                customer_symbol = sym
                break

        if customer_symbol and "selectionRange" in customer_symbol:
            sel_start = customer_symbol["selectionRange"]["start"]
            refs = language_server.request_references(table_file, sel_start["line"], sel_start["character"])

            # The Customer table should be referenced in CustomerMgt.Codeunit.al
            assert any(
                "CustomerMgt.Codeunit.al" in ref.get("relativePath", "") for ref in refs
            ), "Customer table should be referenced in CustomerMgt.Codeunit.al"

            # It should also be referenced in CustomerCard.Page.al
            assert any(
                "CustomerCard.Page.al" in ref.get("relativePath", "") for ref in refs
            ), "Customer table should be referenced in CustomerCard.Page.al"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_cross_file_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that AL Language Server can handle cross-file symbol relationships."""
        # Get all symbols to verify cross-file visibility
        symbols = language_server.request_full_symbol_tree()

        # Count how many AL object symbols we found (names are now normalized)
        al_object_names = []

        def collect_symbols(syms: list) -> None:
            for sym in syms:
                if isinstance(sym, dict):
                    name = sym.get("name", "")
                    # These are normalized names now, so just collect them
                    al_object_names.append(name)
                    if "children" in sym:
                        collect_symbols(sym["children"])

        collect_symbols(symbols)

        # We should find expected normalized names
        assert "TEST Customer" in al_object_names, f"TEST Customer not found in: {al_object_names}"
        assert "CustomerMgt" in al_object_names, f"CustomerMgt not found in: {al_object_names}"
        assert "CustomerType" in al_object_names, f"CustomerType not found in: {al_object_names}"


@pytest.mark.al
class TestALHoverInjection:
    """Tests for hover injection of original AL object names with type and ID."""

    def _get_symbol_hover(self, language_server: SolidLanguageServer, file_path: str, symbol_name: str) -> tuple[dict | None, str | None]:
        """Helper to get hover info for a symbol by name.

        Returns (hover_info, hover_value) tuple.
        """
        symbols = language_server.request_document_symbols(file_path)
        for sym in symbols.root_symbols:
            if sym.get("name") == symbol_name:
                sel_range = sym.get("selectionRange", {})
                start = sel_range.get("start", {})
                line = start.get("line", 0)
                char = start.get("character", 0)
                hover = language_server.request_hover(file_path, line, char)
                if hover and "contents" in hover:
                    return hover, hover["contents"].get("value", "")
                return hover, None
        return None, None

    def _get_child_symbol_hover(
        self, language_server: SolidLanguageServer, file_path: str, parent_name: str, child_name_contains: str
    ) -> tuple[dict | None, str | None]:
        """Helper to get hover info for a child symbol.

        Returns (hover_info, hover_value) tuple.
        """
        symbols = language_server.request_document_symbols(file_path)
        for sym in symbols.root_symbols:
            if sym.get("name") == parent_name:
                for child in sym.get("children", []):
                    if child_name_contains in child.get("name", ""):
                        sel_range = child.get("selectionRange", {})
                        start = sel_range.get("start", {})
                        line = start.get("line", 0)
                        char = start.get("character", 0)
                        hover = language_server.request_hover(file_path, line, char)
                        if hover and "contents" in hover:
                            return hover, hover["contents"].get("value", "")
                        return hover, None
        return None, None

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_table_injects_full_name(self, language_server: SolidLanguageServer) -> None:
        """Test that hovering over a Table symbol shows the full object name with ID."""
        file_path = os.path.join("src", "Tables", "Customer.Table.al")
        hover, value = self._get_symbol_hover(language_server, file_path, "TEST Customer")

        assert hover is not None, "Hover should return a result for Table symbol"
        assert value is not None, "Hover should have content"
        assert '**Table 50000 "TEST Customer"**' in value, f"Hover should contain full Table name with ID. Got: {value[:200]}"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_page_injects_full_name(self, language_server: SolidLanguageServer) -> None:
        """Test that hovering over a Page symbol shows the full object name with ID."""
        file_path = os.path.join("src", "Pages", "CustomerCard.Page.al")
        hover, value = self._get_symbol_hover(language_server, file_path, "TEST Customer Card")

        assert hover is not None, "Hover should return a result for Page symbol"
        assert value is not None, "Hover should have content"
        assert '**Page 50001 "TEST Customer Card"**' in value, f"Hover should contain full Page name with ID. Got: {value[:200]}"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_codeunit_injects_full_name(self, language_server: SolidLanguageServer) -> None:
        """Test that hovering over a Codeunit symbol shows the full object name with ID."""
        file_path = os.path.join("src", "Codeunits", "CustomerMgt.Codeunit.al")
        hover, value = self._get_symbol_hover(language_server, file_path, "CustomerMgt")

        assert hover is not None, "Hover should return a result for Codeunit symbol"
        assert value is not None, "Hover should have content"
        assert "**Codeunit 50000 CustomerMgt**" in value, f"Hover should contain full Codeunit name with ID. Got: {value[:200]}"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_enum_injects_full_name(self, language_server: SolidLanguageServer) -> None:
        """Test that hovering over an Enum symbol shows the full object name with ID."""
        file_path = os.path.join("src", "Enums", "CustomerType.Enum.al")
        hover, value = self._get_symbol_hover(language_server, file_path, "CustomerType")

        assert hover is not None, "Hover should return a result for Enum symbol"
        assert value is not None, "Hover should have content"
        assert "**Enum 50000 CustomerType**" in value, f"Hover should contain full Enum name with ID. Got: {value[:200]}"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_interface_injects_full_name(self, language_server: SolidLanguageServer) -> None:
        """Test that hovering over an Interface symbol shows the full object name (no ID for interfaces)."""
        file_path = os.path.join("src", "Interfaces", "IPaymentProcessor.Interface.al")
        hover, value = self._get_symbol_hover(language_server, file_path, "IPaymentProcessor")

        assert hover is not None, "Hover should return a result for Interface symbol"
        assert value is not None, "Hover should have content"
        assert "**Interface IPaymentProcessor**" in value, f"Hover should contain full Interface name. Got: {value[:200]}"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_procedure_no_injection(self, language_server: SolidLanguageServer) -> None:
        """Test that hovering over a procedure does NOT inject object name (procedures are not normalized)."""
        file_path = os.path.join("src", "Codeunits", "CustomerMgt.Codeunit.al")
        hover, value = self._get_child_symbol_hover(language_server, file_path, "CustomerMgt", "CreateCustomer")

        assert hover is not None, "Hover should return a result for procedure"
        assert value is not None, "Hover should have content"
        # Procedure hover should NOT start with ** (no injection)
        assert not value.startswith("**"), f"Procedure hover should not have injected name. Got: {value[:200]}"
        # But should contain procedure info
        assert "CreateCustomer" in value, f"Hover should contain procedure name. Got: {value[:200]}"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_field_no_injection(self, language_server: SolidLanguageServer) -> None:
        """Test that hovering over a field does NOT inject object name (fields are not normalized)."""
        file_path = os.path.join("src", "Tables", "Customer.Table.al")
        symbols = language_server.request_document_symbols(file_path)

        # Navigate to a field: Table -> fields -> specific field
        for sym in symbols.root_symbols:
            if sym.get("name") == "TEST Customer":
                for child in sym.get("children", []):
                    if child.get("name") == "fields":
                        for field in child.get("children", []):
                            if "Name" in field.get("name", ""):
                                sel_range = field.get("selectionRange", {})
                                start = sel_range.get("start", {})
                                line = start.get("line", 0)
                                char = start.get("character", 0)
                                hover = language_server.request_hover(file_path, line, char)

                                assert hover is not None, "Hover should return a result for field"
                                value = hover.get("contents", {}).get("value", "")
                                # Field hover should NOT start with ** (no injection)
                                assert not value.startswith("**"), f"Field hover should not have injected name. Got: {value[:200]}"
                                return

        pytest.fail("Could not find a field to test hover on")

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_multiple_objects_correct_injection(self, language_server: SolidLanguageServer) -> None:
        """Test that multiple AL objects each get their correct full name injected."""
        test_cases = [
            (os.path.join("src", "Tables", "Customer.Table.al"), "TEST Customer", 'Table 50000 "TEST Customer"'),
            (os.path.join("src", "Codeunits", "CustomerMgt.Codeunit.al"), "CustomerMgt", "Codeunit 50000 CustomerMgt"),
            (os.path.join("src", "Enums", "CustomerType.Enum.al"), "CustomerType", "Enum 50000 CustomerType"),
        ]

        for file_path, symbol_name, expected_full_name in test_cases:
            hover, value = self._get_symbol_hover(language_server, file_path, symbol_name)

            assert hover is not None, f"Hover should return a result for {symbol_name}"
            assert value is not None, f"Hover should have content for {symbol_name}"
            assert (
                f"**{expected_full_name}**" in value
            ), f"Hover for {symbol_name} should contain '{expected_full_name}'. Got: {value[:200]}"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_contains_separator_after_injection(self, language_server: SolidLanguageServer) -> None:
        """Test that injected hover has a separator between injected name and original content."""
        file_path = os.path.join("src", "Tables", "Customer.Table.al")
        hover, value = self._get_symbol_hover(language_server, file_path, "TEST Customer")

        assert hover is not None, "Hover should return a result"
        assert value is not None, "Hover should have content"
        # Should have the separator after the bold name
        assert "---" in value, f"Hover should contain separator. Got: {value[:300]}"
        # The separator should come after the injected name
        bold_end = value.find("**", 2)  # Find closing **
        separator_pos = value.find("---")
        assert separator_pos > bold_end, "Separator should come after the injected name"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_preserves_original_content(self, language_server: SolidLanguageServer) -> None:
        """Test that the original hover content is preserved after the injected name."""
        file_path = os.path.join("src", "Tables", "Customer.Table.al")
        hover, value = self._get_symbol_hover(language_server, file_path, "TEST Customer")

        assert hover is not None, "Hover should return a result"
        assert value is not None, "Hover should have content"
        # Original AL hover content should still be present (the table structure)
        assert "```al" in value, f"Hover should contain original AL code block. Got: {value[:500]}"
        assert 'Table "TEST Customer"' in value, f"Hover should contain original table definition. Got: {value[:500]}"


@pytest.mark.al
class TestALPathNormalization:
    """Tests for path normalization in hover injection cache."""

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_with_forward_slash_path(self, language_server: SolidLanguageServer) -> None:
        """Test that hover injection works with forward slash paths."""
        file_path = "src/Tables/Customer.Table.al"
        symbols = language_server.request_document_symbols(file_path)

        for sym in symbols.root_symbols:
            if sym.get("name") == "TEST Customer":
                sel_range = sym.get("selectionRange", {})
                start = sel_range.get("start", {})
                line = start.get("line", 0)
                char = start.get("character", 0)

                hover = language_server.request_hover(file_path, line, char)
                assert hover is not None, "Hover should return a result"
                value = hover.get("contents", {}).get("value", "")
                assert '**Table 50000 "TEST Customer"**' in value, f"Hover should have injection. Got: {value[:200]}"
                return

        pytest.fail("Could not find TEST Customer symbol")

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_with_backslash_path(self, language_server: SolidLanguageServer) -> None:
        """Test that hover injection works with backslash paths (Windows style)."""
        file_path = "src\\Tables\\Customer.Table.al"
        symbols = language_server.request_document_symbols(file_path)

        for sym in symbols.root_symbols:
            if sym.get("name") == "TEST Customer":
                sel_range = sym.get("selectionRange", {})
                start = sel_range.get("start", {})
                line = start.get("line", 0)
                char = start.get("character", 0)

                hover = language_server.request_hover(file_path, line, char)
                assert hover is not None, "Hover should return a result"
                value = hover.get("contents", {}).get("value", "")
                assert '**Table 50000 "TEST Customer"**' in value, f"Hover should have injection. Got: {value[:200]}"
                return

        pytest.fail("Could not find TEST Customer symbol")

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_with_mixed_path_formats_symbols_backslash_hover_forward(self, language_server: SolidLanguageServer) -> None:
        """Test hover works when symbols requested with backslash but hover with forward slash."""
        file_path_backslash = "src\\Tables\\Customer.Table.al"
        file_path_forward = "src/Tables/Customer.Table.al"

        # Request symbols with backslash path
        symbols = language_server.request_document_symbols(file_path_backslash)

        for sym in symbols.root_symbols:
            if sym.get("name") == "TEST Customer":
                sel_range = sym.get("selectionRange", {})
                start = sel_range.get("start", {})
                line = start.get("line", 0)
                char = start.get("character", 0)

                # Request hover with forward slash path (different format)
                hover = language_server.request_hover(file_path_forward, line, char)
                assert hover is not None, "Hover should return a result"
                value = hover.get("contents", {}).get("value", "")
                assert (
                    '**Table 50000 "TEST Customer"**' in value
                ), f"Hover injection should work with mixed path formats. Got: {value[:200]}"
                return

        pytest.fail("Could not find TEST Customer symbol")

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_with_mixed_path_formats_symbols_forward_hover_backslash(self, language_server: SolidLanguageServer) -> None:
        """Test hover works when symbols requested with forward slash but hover with backslash."""
        file_path_forward = "src/Tables/Customer.Table.al"
        file_path_backslash = "src\\Tables\\Customer.Table.al"

        # Request symbols with forward slash path
        symbols = language_server.request_document_symbols(file_path_forward)

        for sym in symbols.root_symbols:
            if sym.get("name") == "TEST Customer":
                sel_range = sym.get("selectionRange", {})
                start = sel_range.get("start", {})
                line = start.get("line", 0)
                char = start.get("character", 0)

                # Request hover with backslash path (different format)
                hover = language_server.request_hover(file_path_backslash, line, char)
                assert hover is not None, "Hover should return a result"
                value = hover.get("contents", {}).get("value", "")
                assert (
                    '**Table 50000 "TEST Customer"**' in value
                ), f"Hover injection should work with mixed path formats. Got: {value[:200]}"
                return

        pytest.fail("Could not find TEST Customer symbol")

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_hover_caching_multiple_files_different_path_formats(self, language_server: SolidLanguageServer) -> None:
        """Test that hover injection cache works correctly across multiple files with different path formats."""
        test_cases = [
            ("src/Tables/Customer.Table.al", "src\\Tables\\Customer.Table.al", "TEST Customer", 'Table 50000 "TEST Customer"'),
            (
                "src\\Codeunits\\CustomerMgt.Codeunit.al",
                "src/Codeunits/CustomerMgt.Codeunit.al",
                "CustomerMgt",
                "Codeunit 50000 CustomerMgt",
            ),
        ]

        for symbols_path, hover_path, symbol_name, expected_injection in test_cases:
            # Request symbols with one path format
            symbols = language_server.request_document_symbols(symbols_path)

            for sym in symbols.root_symbols:
                if sym.get("name") == symbol_name:
                    sel_range = sym.get("selectionRange", {})
                    start = sel_range.get("start", {})
                    line = start.get("line", 0)
                    char = start.get("character", 0)

                    # Request hover with different path format
                    hover = language_server.request_hover(hover_path, line, char)
                    assert hover is not None, f"Hover should return a result for {symbol_name}"
                    value = hover.get("contents", {}).get("value", "")
                    assert (
                        f"**{expected_injection}**" in value
                    ), f"Hover for {symbol_name} should have injection with mixed paths. Got: {value[:200]}"
                    break
