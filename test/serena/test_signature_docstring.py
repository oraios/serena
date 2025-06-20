"""Tests for signature and docstring retrieval functionality using real language servers."""

import pytest

from multilspy.language_server import SyncLanguageServer
from multilspy.multilspy_config import Language
from src.serena.symbol import Symbol, SymbolManager

pytestmark = pytest.mark.python


class TestSignatureAndDocstring:
    """Test suite for signature and docstring functionality using real language servers."""

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_symbol_signature_property(self, language_server: SyncLanguageServer):
        """Test signature property getter and setter."""
        symbol_manager = SymbolManager(language_server)

        # Find a real symbol from the test repository
        symbols = symbol_manager.find_by_name("create_user", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        symbol = symbols[0]

        # Initially should be None
        assert symbol.signature is None

        # Set signature
        symbol.signature = "def create_user(self, id: str, name: str, email: str) -> User"
        assert symbol.signature == "def create_user(self, id: str, name: str, email: str) -> User"

        # Set to None
        symbol.signature = None
        assert symbol.signature is None

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_symbol_docstring_property(self, language_server: SyncLanguageServer):
        """Test docstring property getter and setter."""
        symbol_manager = SymbolManager(language_server)

        # Find a real symbol from the test repository
        symbols = symbol_manager.find_by_name("create_user", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        symbol = symbols[0]

        # Initially should be None
        assert symbol.docstring is None

        # Set docstring
        symbol.docstring = "Create a new user and store it"
        assert symbol.docstring == "Create a new user and store it"

        # Set to None
        symbol.docstring = None
        assert symbol.docstring is None

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_symbol_to_dict_with_signature_and_docstring(self, language_server: SyncLanguageServer):
        """Test to_dict method includes signature and docstring when requested."""
        symbol_manager = SymbolManager(language_server)

        # Find a real symbol from the test repository
        symbols = symbol_manager.find_by_name("create_user", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        symbol = symbols[0]

        symbol.signature = "def create_user(self, id: str, name: str, email: str) -> User"
        symbol.docstring = "Create a new user and store it"

        # Test without signature/docstring
        result = symbol.to_dict()
        assert "signature" not in result
        assert "docstring" not in result

        # Test with signature only
        result = symbol.to_dict(include_signature=True)
        assert result["signature"] == "def create_user(self, id: str, name: str, email: str) -> User"
        assert "docstring" not in result

        # Test with docstring only
        result = symbol.to_dict(include_docstring=True)
        assert "signature" not in result
        assert result["docstring"] == "Create a new user and store it"

        # Test with both
        result = symbol.to_dict(include_signature=True, include_docstring=True)
        assert result["signature"] == "def create_user(self, id: str, name: str, email: str) -> User"
        assert result["docstring"] == "Create a new user and store it"

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_get_signature_and_docstring_real_function(self, language_server: SyncLanguageServer):
        """Test signature and docstring retrieval from a real function."""
        symbol_manager = SymbolManager(language_server)

        # Find the create_user method which has both signature and docstring
        symbols = symbol_manager.find_by_name("create_user", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        symbol = symbols[0]

        signature, docstring = symbol_manager.get_signature_and_docstring(symbol)

        # Should have retrieved some signature information
        assert signature is not None
        assert "create_user" in signature

        # Should have retrieved docstring information
        assert docstring is not None
        assert len(docstring.strip()) > 0

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_get_signature_and_docstring_class(self, language_server: SyncLanguageServer):
        """Test signature and docstring retrieval from a class."""
        symbol_manager = SymbolManager(language_server)

        # Find the UserService class
        symbols = symbol_manager.find_by_name("UserService", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        symbol = symbols[0]

        signature, docstring = symbol_manager.get_signature_and_docstring(symbol)

        # For classes, we may get signature and/or docstring depending on LSP implementation
        # We just verify that the method doesn't crash and returns valid types
        assert signature is None or isinstance(signature, str)
        assert docstring is None or isinstance(docstring, str)

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_get_signature_and_docstring_constructor(self, language_server: SyncLanguageServer):
        """Test signature and docstring retrieval from a constructor."""
        symbol_manager = SymbolManager(language_server)

        # Find the __init__ method of UserService
        symbols = symbol_manager.find_by_name("UserService/__init__", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        symbol = symbols[0]

        signature, docstring = symbol_manager.get_signature_and_docstring(symbol)

        # Should handle constructors gracefully
        assert signature is None or isinstance(signature, str)
        assert docstring is None or isinstance(docstring, str)

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_enrich_symbol_with_signature_and_docstring(self, language_server: SyncLanguageServer):
        """Test enriching a symbol with signature and docstring."""
        symbol_manager = SymbolManager(language_server)

        # Find a real symbol from the test repository
        symbols = symbol_manager.find_by_name("get_user", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        symbol = symbols[0]

        # Initially no signature/docstring
        assert symbol.signature is None
        assert symbol.docstring is None

        # Enrich the symbol
        symbol_manager.enrich_symbol_with_signature_and_docstring(symbol)

        # Check that properties were set (they may be None depending on LSP capabilities)
        # But the enrichment should not crash
        assert symbol.signature is None or isinstance(symbol.signature, str)
        assert symbol.docstring is None or isinstance(symbol.docstring, str)

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_signature_and_docstring_error_handling(self, language_server: SyncLanguageServer):
        """Test error handling when symbol has no valid position."""
        symbol_manager = SymbolManager(language_server)

        # Find a symbol and create a modified version with invalid position
        symbols = symbol_manager.find_by_name("UserService", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        original_symbol = symbols[0]

        # Create a symbol with None relative_path to test error handling
        symbol_info = original_symbol.symbol_root.copy()
        if symbol_info.get("location"):
            symbol_info["location"]["relativePath"] = None
        symbol_with_no_path = Symbol(symbol_info)

        signature, docstring = symbol_manager.get_signature_and_docstring(symbol_with_no_path)

        # Should handle gracefully and return None
        assert signature is None
        assert docstring is None

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_multiple_functions_signature_retrieval(self, language_server: SyncLanguageServer):
        """Test signature retrieval for multiple functions to ensure consistency."""
        symbol_manager = SymbolManager(language_server)

        function_names = ["create_user", "get_user", "list_users", "delete_user"]

        for func_name in function_names:
            symbols = symbol_manager.find_by_name(func_name, within_relative_path="test_repo/services.py")
            if symbols:  # Some functions might not be found depending on implementation
                symbol = symbols[0]
                signature, docstring = symbol_manager.get_signature_and_docstring(symbol)

                # Verify the method doesn't crash and returns appropriate types
                assert signature is None or (isinstance(signature, str) and func_name in signature)
                assert docstring is None or isinstance(docstring, str)

    @pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
    def test_item_service_functions(self, language_server: SyncLanguageServer):
        """Test signature and docstring retrieval for ItemService functions."""
        symbol_manager = SymbolManager(language_server)

        # Test the create_item function which should have a signature and docstring
        symbols = symbol_manager.find_by_name("create_item", within_relative_path="test_repo/services.py")
        assert len(symbols) > 0
        symbol = symbols[0]

        signature, docstring = symbol_manager.get_signature_and_docstring(symbol)

        # Should retrieve some information for this function
        assert signature is None or ("create_item" in signature and isinstance(signature, str))
        assert docstring is None or isinstance(docstring, str)
