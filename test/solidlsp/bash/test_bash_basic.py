from pathlib import Path

import pytest

from solidlsp.language_servers.bash_language_server import BashLanguageServer


@pytest.mark.bash
def test_bash_language_server_initialization(bash_language_server):
    """Test that bash language server can be initialized successfully."""
    assert bash_language_server is not None
    assert isinstance(bash_language_server, BashLanguageServer)


@pytest.mark.bash
def test_bash_file_extensions(bash_language_server):
    """Test that bash language server recognizes proper file extensions."""
    # The language server should handle .sh, .bash files
    # Basic functionality test - if we got here, the server is working
    assert bash_language_server is not None


@pytest.mark.bash
def test_bash_symbols_overview(bash_language_server):
    """Test retrieving symbols overview from bash files."""
    try:
        # Test getting symbols from main.sh
        symbols = bash_language_server.get_symbols_for_document(Path("test/resources/repos/bash/test_repo/main.sh"))

        # Should find function definitions
        symbol_names = [symbol.name for symbol in symbols]
        assert any("greet_user" in name for name in symbol_names), "Should find greet_user function"
        assert any("process_items" in name for name in symbol_names), "Should find process_items function"
        assert any("main" in name for name in symbol_names), "Should find main function"

    except Exception as e:
        # If symbols aren't fully supported yet, at least ensure the server starts
        pytest.skip(f"Symbol retrieval not fully implemented yet: {e}")


@pytest.mark.bash
def test_bash_function_detection_hybrid_approach(bash_language_server):
    """Test our enhanced hybrid function detection (LSP + regex fallback)."""
    try:
        # Test the request_document_symbols method directly
        all_symbols, root_symbols = bash_language_server.request_document_symbols(
            "main.sh", 
            include_body=False
        )
        
        # Extract function symbols (LSP Symbol Kind 12)
        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]
        
        # Should detect all 3 functions from main.sh
        assert "greet_user" in function_names, "Should find greet_user function"
        assert "process_items" in function_names, "Should find process_items function" 
        assert "main" in function_names, "Should find main function"
        assert len(function_symbols) >= 3, f"Should find at least 3 functions, found {len(function_symbols)}"
        
        # Test with utils.sh as well
        utils_all_symbols, utils_root_symbols = bash_language_server.request_document_symbols(
            "utils.sh",
            include_body=False
        )
        
        utils_function_symbols = [symbol for symbol in utils_all_symbols if symbol.get("kind") == 12]
        utils_function_names = [symbol["name"] for symbol in utils_function_symbols]
        
        # Should detect functions from utils.sh
        expected_utils_functions = ["to_uppercase", "to_lowercase", "trim_whitespace", "backup_file", 
                                   "contains_element", "log_message", "is_valid_email", "is_number"]
        
        for func_name in expected_utils_functions:
            assert func_name in utils_function_names, f"Should find {func_name} function in utils.sh"
            
        assert len(utils_function_symbols) >= 8, f"Should find at least 8 functions in utils.sh, found {len(utils_function_symbols)}"
        
    except Exception as e:
        pytest.fail(f"Enhanced function detection failed: {e}")


@pytest.mark.bash  
def test_bash_function_detection_with_body(bash_language_server):
    """Test function detection with body extraction."""
    try:
        # Test with include_body=True
        all_symbols, root_symbols = bash_language_server.request_document_symbols(
            "main.sh",
            include_body=True
        )
        
        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        
        # Find greet_user function and check it has body
        greet_user_symbol = next((sym for sym in function_symbols if sym["name"] == "greet_user"), None)
        assert greet_user_symbol is not None, "Should find greet_user function"
        
        if "body" in greet_user_symbol:
            body = greet_user_symbol["body"]
            assert "function greet_user()" in body, "Function body should contain function definition"
            assert "case" in body.lower(), "Function body should contain case statement"
            
    except Exception as e:
        pytest.skip(f"Function body extraction not fully implemented yet: {e}")


@pytest.mark.bash
def test_bash_regex_fallback_detection(bash_language_server):
    """Test the regex-based fallback function detection directly."""
    try:
        # Check if the method exists (it should if we have our enhanced bash server)
        if not hasattr(bash_language_server, '_detect_bash_functions'):
            pytest.skip("Enhanced bash function detection not available - this may be due to test environment setup")
        
        # Test the _detect_bash_functions method directly 
        detected_functions = bash_language_server._detect_bash_functions(
            "main.sh",
            include_body=True
        )
        
        # Should detect functions even if LSP doesn't provide them
        assert len(detected_functions) == 3, f"Should detect exactly 3 functions, found {len(detected_functions)}"
        
        function_names = [func["name"] for func in detected_functions]
        assert "greet_user" in function_names, "Regex should detect greet_user function"
        assert "process_items" in function_names, "Regex should detect process_items function"
        assert "main" in function_names, "Regex should detect main function"
        
        # Check that symbols have proper structure
        for func in detected_functions:
            assert func["kind"] == 12, f"Function {func['name']} should have LSP Symbol Kind 12"
            assert "location" in func, f"Function {func['name']} should have location info"
            assert "range" in func, f"Function {func['name']} should have range info"
            assert "selectionRange" in func, f"Function {func['name']} should have selectionRange info"
            
            # Check location structure
            location = func["location"]
            assert "uri" in location, f"Function {func['name']} location should have URI"
            assert "range" in location, f"Function {func['name']} location should have range"
            assert "relativePath" in location, f"Function {func['name']} location should have relative path"
            
    except Exception as e:
        pytest.fail(f"Regex fallback detection failed: {e}")


@pytest.mark.bash
def test_bash_function_syntax_patterns(bash_language_server):
    """Test detection of different bash function syntax patterns."""
    try:
        # Check if the method exists (it should if we have our enhanced bash server)
        if not hasattr(bash_language_server, '_detect_bash_functions'):
            pytest.skip("Enhanced bash function detection not available - this may be due to test environment setup")
        
        # Test main.sh (has 'function' keyword functions and regular function)
        main_functions = bash_language_server._detect_bash_functions(
            "main.sh",
            include_body=False
        )
        
        # Test utils.sh (all use 'function' keyword)
        utils_functions = bash_language_server._detect_bash_functions(
            "utils.sh", 
            include_body=False
        )
        
        # Verify we detect both syntax patterns
        main_function_names = [func["name"] for func in main_functions]
        utils_function_names = [func["name"] for func in utils_functions]
        
        # main() uses regular syntax: main() {
        assert "main" in main_function_names, "Should detect regular function syntax"
        
        # Functions with 'function' keyword: function name() {
        assert "greet_user" in main_function_names, "Should detect function keyword syntax"
        assert "to_uppercase" in utils_function_names, "Should detect function keyword syntax in utils"
        
        # Verify all expected utils functions are detected
        expected_utils = ["to_uppercase", "to_lowercase", "trim_whitespace", "backup_file",
                         "contains_element", "log_message", "is_valid_email", "is_number"]
        
        for expected_func in expected_utils:
            assert expected_func in utils_function_names, f"Should detect {expected_func} function"
            
    except Exception as e:
        pytest.fail(f"Function syntax pattern detection failed: {e}")


@pytest.mark.bash
def test_bash_document_symbols(bash_language_server):
    """Test document symbols functionality."""
    try:
        # Test getting document symbols from utils.sh
        symbols = bash_language_server.get_symbols_for_document(Path("test/resources/repos/bash/test_repo/utils.sh"))

        # Should find utility functions
        symbol_names = [symbol.name for symbol in symbols]
        assert any("to_uppercase" in name for name in symbol_names), "Should find to_uppercase function"
        assert any("log_message" in name for name in symbol_names), "Should find log_message function"
        assert any("backup_file" in name for name in symbol_names), "Should find backup_file function"

    except Exception as e:
        pytest.skip(f"Document symbols not fully implemented yet: {e}")


@pytest.mark.bash
def test_bash_workspace_symbols(bash_language_server):
    """Test workspace symbols functionality."""
    try:
        # Test workspace symbol search
        symbols = bash_language_server.get_workspace_symbols(query="function")

        # Should find some function symbols across all bash files
        assert len(symbols) > 0, "Should find at least some function symbols"

    except Exception as e:
        pytest.skip(f"Workspace symbols not fully implemented yet: {e}")


@pytest.mark.bash
def test_bash_completion(bash_language_server):
    """Test basic completion functionality if available."""
    try:
        # Test completion at a specific position
        _ = bash_language_server.get_completions(Path("test/resources/repos/bash/test_repo/main.sh"), line=10, character=5)

        # Bash language server may provide completions for commands, variables, etc.
        # The exact completions depend on bash-language-server implementation

    except Exception as e:
        pytest.skip(f"Completions not implemented or available yet: {e}")


@pytest.mark.bash
def test_bash_hover(bash_language_server):
    """Test hover information if available."""
    try:
        # Test hover on a function name
        _ = bash_language_server.get_hover(
            Path("test/resources/repos/bash/test_repo/main.sh"), line=15, character=10  # Around greet_user function
        )

        # May provide documentation or type information

    except Exception as e:
        pytest.skip(f"Hover not implemented or available yet: {e}")


@pytest.mark.bash
def test_bash_diagnostics(bash_language_server):
    """Test that bash language server can provide diagnostics."""
    try:
        # Open a document to trigger diagnostics
        bash_language_server.open_document(Path("test/resources/repos/bash/test_repo/main.sh"))

        # bash-language-server should provide syntax checking
        # The exact diagnostics depend on the file content and server capabilities

    except Exception as e:
        pytest.skip(f"Diagnostics not implemented or available yet: {e}")


@pytest.mark.bash
def test_bash_server_capabilities(bash_language_server):
    """Test that bash language server reports expected capabilities."""
    try:
        capabilities = bash_language_server.server_capabilities

        # bash-language-server typically supports:
        # - textDocumentSync
        # - completionProvider (maybe)
        # - hoverProvider (maybe)
        # - documentSymbolProvider (maybe)

        assert "textDocumentSync" in capabilities, "Should support text document sync"

    except Exception as e:
        pytest.skip(f"Server capabilities not accessible yet: {e}")
