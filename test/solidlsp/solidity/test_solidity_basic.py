"""
Basic integration tests for the Solidity language server.

Tests validate symbol detection and reference finding using the Solidity test repository,
which contains a simple ERC-20 Token contract, a SafeMath library, and an IERC20 interface.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.solidity
class TestSolidityLanguageServerBasics:
    """Test basic functionality of the Solidity language server."""

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
    def test_solidity_language_server_initialization(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that the Solidity language server starts and initializes correctly."""
        assert language_server is not None
        assert language_server.language == Language.SOLIDITY
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
    def test_token_contract_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that document symbols are found in Token.sol.

        Verifies contract, state variables, errors, events, and function symbols.
        """
        all_symbols, root_symbols = language_server.request_document_symbols("contracts/Token.sol").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for Token.sol"
        assert len(all_symbols) > 0, f"Should find symbols in Token.sol, found {len(all_symbols)}"

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Contract-level symbol
        assert "Token" in symbol_names, "Should detect the Token contract"

        # State variables
        assert "name" in symbol_names, "Should detect the 'name' state variable"
        assert "symbol" in symbol_names, "Should detect the 'symbol' state variable"
        assert "decimals" in symbol_names, "Should detect the 'decimals' state variable"

        # Custom errors
        assert "ZeroAddress" in symbol_names, "Should detect the 'ZeroAddress' custom error"
        assert "InsufficientBalance" in symbol_names, "Should detect the 'InsufficientBalance' custom error"

        # Functions
        assert "totalSupply" in symbol_names, "Should detect the 'totalSupply' function"
        assert "balanceOf" in symbol_names, "Should detect the 'balanceOf' function"
        assert "transfer" in symbol_names, "Should detect the 'transfer' function"
        assert "approve" in symbol_names, "Should detect the 'approve' function"
        assert "transferFrom" in symbol_names, "Should detect the 'transferFrom' function"

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
    def test_interface_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that document symbols are found in IERC20.sol."""
        all_symbols, root_symbols = language_server.request_document_symbols("contracts/interfaces/IERC20.sol").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for IERC20.sol"
        assert len(all_symbols) > 0, f"Should find symbols in IERC20.sol, found {len(all_symbols)}"

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Interface
        assert "IERC20" in symbol_names, "Should detect the IERC20 interface"

        # Events
        assert "Transfer" in symbol_names, "Should detect the Transfer event"
        assert "Approval" in symbol_names, "Should detect the Approval event"

        # View functions
        assert "totalSupply" in symbol_names, "Should detect totalSupply"
        assert "balanceOf" in symbol_names, "Should detect balanceOf"
        assert "allowance" in symbol_names, "Should detect allowance"

        # Mutating functions
        assert "transfer" in symbol_names, "Should detect transfer"
        assert "approve" in symbol_names, "Should detect approve"
        assert "transferFrom" in symbol_names, "Should detect transferFrom"

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
    def test_library_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that document symbols are found in SafeMath.sol."""
        all_symbols, root_symbols = language_server.request_document_symbols("contracts/lib/SafeMath.sol").get_all_symbols_and_roots()

        assert all_symbols is not None, "Should return symbols for SafeMath.sol"
        assert len(all_symbols) > 0, f"Should find symbols in SafeMath.sol, found {len(all_symbols)}"

        symbol_names = [sym.get("name") for sym in all_symbols]

        # Library
        assert "SafeMath" in symbol_names, "Should detect the SafeMath library"

        # Library functions
        assert "add" in symbol_names, "Should detect the 'add' function"
        assert "sub" in symbol_names, "Should detect the 'sub' function"
        assert "mul" in symbol_names, "Should detect the 'mul' function"
        assert "div" in symbol_names, "Should detect the 'div' function"

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
    def test_within_file_references(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding within-file references to the _transfer helper in Token.sol."""
        all_symbols, _ = language_server.request_document_symbols("contracts/Token.sol").get_all_symbols_and_roots()

        # Find the line where _transfer is defined
        transfer_symbol = next((s for s in all_symbols if s.get("name") == "_transfer"), None)
        assert transfer_symbol is not None, "Should find the '_transfer' internal function symbol"

        definition_line = transfer_symbol["range"]["start"]["line"]
        references = language_server.request_references(
            "contracts/Token.sol", definition_line, transfer_symbol["range"]["start"]["character"]
        )

        assert references is not None, "Should return references for '_transfer'"
        assert (
            len(references) >= 2
        ), (  # defined once, called in transfer() and transferFrom()
            f"'_transfer' should have at least 2 references (definition + callers), found {len(references)}"
        )

        ref_files = {ref.get("uri", "") for ref in references}
        assert any("Token.sol" in uri for uri in ref_files), "References should include Token.sol"

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
    def test_cross_file_references(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding cross-file references to SafeMath.add used in Token.sol."""
        all_symbols, _ = language_server.request_document_symbols("contracts/lib/SafeMath.sol").get_all_symbols_and_roots()

        add_symbol = next((s for s in all_symbols if s.get("name") == "add"), None)
        assert add_symbol is not None, "Should find the 'add' function in SafeMath.sol"

        definition_line = add_symbol["range"]["start"]["line"]
        references = language_server.request_references(
            "contracts/lib/SafeMath.sol", definition_line, add_symbol["range"]["start"]["character"]
        )

        assert references is not None, "Should return cross-file references for SafeMath.add"
        assert len(references) >= 1, f"SafeMath.add should be referenced at least once (in Token.sol), found {len(references)}"

        ref_files = {ref.get("uri", "") for ref in references}
        assert any("Token.sol" in uri for uri in ref_files), "SafeMath.add references should include Token.sol"
