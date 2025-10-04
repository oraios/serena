import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.al
class TestALLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that AL Language Server can find symbols in the test repository."""
        symbols = language_server.request_full_symbol_tree()

        # Check for table symbols - AL returns full object names like 'Table 50000 "TEST Customer"'
        assert SymbolUtils.symbol_tree_contains_name(symbols, 'Table 50000 "TEST Customer"'), "TEST Customer table not found in symbol tree"

        # Check for page symbols
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, 'Page 50001 "TEST Customer Card"'
        ), "TEST Customer Card page not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, 'Page 50002 "TEST Customer List"'
        ), "TEST Customer List page not found in symbol tree"

        # Check for codeunit symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Codeunit 50000 CustomerMgt"), "CustomerMgt codeunit not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, "Codeunit 50001 PaymentProcessorImpl"
        ), "PaymentProcessorImpl codeunit not found in symbol tree"

        # Check for enum symbol
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Enum 50000 CustomerType"), "CustomerType enum not found in symbol tree"

        # Check for interface symbol
        assert SymbolUtils.symbol_tree_contains_name(
            symbols, "Interface IPaymentProcessor"
        ), "IPaymentProcessor interface not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_table_fields(self, language_server: SolidLanguageServer) -> None:
        """Test that AL Language Server can find fields within a table."""
        file_path = os.path.join("src", "Tables", "Customer.Table.al")
        symbols = language_server.request_document_symbols(file_path)

        # AL tables should have their fields as child symbols
        customer_table = None
        _all_symbols, root_symbols = symbols
        for sym in root_symbols:
            if "TEST Customer" in sym.get("name", ""):
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
        symbols = language_server.request_document_symbols(file_path)

        # Find the codeunit symbol - AL returns 'Codeunit 50000 CustomerMgt'
        codeunit_symbol = None
        _all_symbols, root_symbols = symbols
        for sym in root_symbols:
            if "CustomerMgt" in sym.get("name", ""):
                codeunit_symbol = sym
                break

        assert codeunit_symbol is not None, "Could not find CustomerMgt codeunit symbol"

        # Check for procedure symbols (if hierarchical)
        if "children" in codeunit_symbol:
            procedure_names = [child.get("name", "") for child in codeunit_symbol.get("children", [])]
            assert any("CreateCustomer" in name for name in procedure_names), "CreateCustomer procedure not found"
            # Note: UpdateCustomerBalance doesn't exist in our test repo, check for actual procedures
            assert any("TestNoSeries" in name for name in procedure_names), "TestNoSeries procedure not found"

    @pytest.mark.parametrize("language_server", [Language.AL], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that AL Language Server can find references to symbols."""
        # Find references to the Customer table from the CustomerMgt codeunit
        table_file = os.path.join("src", "Tables", "Customer.Table.al")
        symbols = language_server.request_document_symbols(table_file)

        # Find the Customer table symbol
        customer_symbol = None
        _all_symbols, root_symbols = symbols
        for sym in root_symbols:
            if "TEST Customer" in sym.get("name", ""):
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

        # Count how many AL-specific symbols we found
        al_symbols = []

        def collect_symbols(syms):
            for sym in syms:
                if isinstance(sym, dict):
                    name = sym.get("name", "")
                    # Look for AL object names (Table, Page, Codeunit, etc.)
                    if any(keyword in name for keyword in ["Table", "Page", "Codeunit", "Enum", "Interface"]):
                        al_symbols.append(name)
                    if "children" in sym:
                        collect_symbols(sym["children"])

        collect_symbols(symbols)

        # We should find symbols from multiple files
        assert len(al_symbols) >= 5, f"Expected at least 5 AL object symbols, found {len(al_symbols)}: {al_symbols}"

        # Verify we have symbols from different AL object types
        has_table = any("Table" in s for s in al_symbols)
        has_page = any("Page" in s for s in al_symbols)
        has_codeunit = any("Codeunit" in s for s in al_symbols)

        assert has_table, f"No Table symbols found in: {al_symbols}"
        assert has_page, f"No Page symbols found in: {al_symbols}"
        assert has_codeunit, f"No Codeunit symbols found in: {al_symbols}"
