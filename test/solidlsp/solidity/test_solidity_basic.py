"""
Basic integration tests for the Solidity language server.

Tests validate symbol detection and reference finding using the Solidity test repository,
which contains a simple ERC-20 Token contract, a SafeMath library, and an IERC20 interface.
"""

import re
from pathlib import Path
from typing import Optional

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.conftest import language_has_verified_implementation_support
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


def _find_identifier_position(file_path: Path, symbol_name: str) -> Optional[tuple[int, int]]:
    """Return the (line, column) of the first occurrence of *symbol_name* as an identifier.

    Scans the file for a word-boundary match of *symbol_name* so that the position
    returned is the exact location of the identifier, regardless of what range the
    language server reports for the surrounding symbol.  Returns None if not found.
    """
    pattern = re.compile(r"\b" + re.escape(symbol_name) + r"\b")
    with file_path.open(encoding="utf-8") as fh:
        for line_idx, line in enumerate(fh):
            m = pattern.search(line)
            if m:
                return line_idx, m.start()
    return None


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
        # Use the file to find the exact identifier position: the Solidity LSP reports
        # the symbol range starting at the preceding whitespace/comment block, not the
        # function keyword, so we locate '_transfer' directly in the source.
        pos = _find_identifier_position(repo_path / "contracts/Token.sol", "_transfer")
        assert pos is not None, "Should find '_transfer' identifier in Token.sol"
        definition_line, definition_char = pos

        references = language_server.request_references("contracts/Token.sol", definition_line, definition_char)

        assert references is not None, "Should return references for '_transfer'"
        assert len(references) >= 2, (
            f"'_transfer' should have at least 2 references (callers), found {len(references)}"
        )  # called in transfer() and transferFrom()

        ref_files = {ref.get("uri", "") for ref in references}
        assert any("Token.sol" in uri for uri in ref_files), "References should include Token.sol"

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
    def test_cross_file_references(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding cross-file references: IERC20.transfer implemented in Token.sol."""
        # Use 'transfer' in the interface — Token.sol inherits IERC20 and overrides it,
        # so the LSP resolves the implementation site in Token.sol as a cross-file reference.
        pos = _find_identifier_position(repo_path / "contracts/interfaces/IERC20.sol", "transfer")
        assert pos is not None, "Should find 'transfer' identifier in IERC20.sol"
        definition_line, definition_char = pos

        references = language_server.request_references("contracts/interfaces/IERC20.sol", definition_line, definition_char)

        assert references is not None, "Should return cross-file references for IERC20.transfer"
        assert len(references) >= 1, f"IERC20.transfer should be referenced at least once (in Token.sol), found {len(references)}"

        ref_files = {ref.get("uri", "") for ref in references}
        assert any("Token.sol" in uri for uri in ref_files), "IERC20.transfer references should include Token.sol"

    if language_has_verified_implementation_support(Language.SOLIDITY):

        @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
        @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
            pos = _find_identifier_position(repo_path / "contracts/interfaces/IERC20.sol", "transfer")
            assert pos is not None, "Should find 'transfer' identifier in IERC20.sol"

            implementations = language_server.request_implementation("contracts/interfaces/IERC20.sol", *pos)
            assert implementations, "Expected Token.transfer to be returned as an implementation"
            assert any("Token.sol" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected Token.transfer implementation, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
        @pytest.mark.parametrize("repo_path", [Language.SOLIDITY], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
            pos = _find_identifier_position(repo_path / "contracts/interfaces/IERC20.sol", "transfer")
            assert pos is not None, "Should find 'transfer' identifier in IERC20.sol"

            implementing_symbols = language_server.request_implementing_symbols("contracts/interfaces/IERC20.sol", *pos)
            assert implementing_symbols, "Expected implementing symbols for IERC20.transfer"
            assert any(
                symbol.get("name") == "transfer" and "Token.sol" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected Token.transfer symbol, got: {implementing_symbols}"

    @pytest.mark.parametrize("language_server", [Language.SOLIDITY], indirect=True)
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
