import os

import pytest

from serena.symbol import LanguageServerSymbol
from solidlsp import SolidLanguageServer
from solidlsp.language_servers.al_language_server import extract_al_display_name
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import language_tests_enabled

pytestmark = [pytest.mark.al, pytest.mark.skipif(not language_tests_enabled(Language.AL), reason="AL tests are disabled")]


class TestExtractALDisplayName:
    """Tests for the extract_al_display_name function."""

    def test_table_with_quoted_name(self) -> None:
        """Test extraction from Table with quoted name."""
        assert extract_al_display_name('Table 50000 "TEST Customer"') == "TEST Customer"

    def test_page_with_quoted_name(self) -> None:
        """Test extraction from Page with quoted name."""
        assert extract_al_display_name('Page 50001 "TEST Customer Card"') == "TEST Customer Card"

    def test_codeunit_unquoted(self) -> None:
        """Test extraction from Codeunit with unquoted name."""
        assert extract_al_display_name("Codeunit 50000 CustomerMgt") == "CustomerMgt"

    def test_enum_unquoted(self) -> None:
        """Test extraction from Enum with unquoted name."""
        assert extract_al_display_name("Enum 50000 CustomerType") == "CustomerType"

    def test_interface_no_id(self) -> None:
        """Test extraction from Interface (no ID)."""
        assert extract_al_display_name("Interface IPaymentProcessor") == "IPaymentProcessor"

    def test_table_extension(self) -> None:
        """Test extraction from TableExtension."""
        assert extract_al_display_name('TableExtension 50000 "Ext Customer"') == "Ext Customer"

    def test_page_extension(self) -> None:
        """Test extraction from PageExtension."""
        assert extract_al_display_name('PageExtension 50000 "My Page Ext"') == "My Page Ext"

    def test_non_al_object_unchanged(self) -> None:
        """Test that non-AL-object names pass through unchanged."""
        assert extract_al_display_name("fields") == "fields"
        assert extract_al_display_name("CreateCustomer") == "CreateCustomer"
        assert extract_al_display_name("Name") == "Name"

    def test_report_with_quoted_name(self) -> None:
        """Test extraction from Report."""
        assert extract_al_display_name('Report 50000 "Sales Invoice"') == "Sales Invoice"

    def test_query_unquoted(self) -> None:
        """Test extraction from Query."""
        assert extract_al_display_name("Query 50000 CustomerQuery") == "CustomerQuery"


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
