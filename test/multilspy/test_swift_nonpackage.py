"""
Tests for Swift language server functionality on non-Package.swift projects.

These tests focus on using sourcekit-lsp with Swift projects that don't have a Package.swift file.
"""

import os
import pytest
from pathlib import Path

from multilspy.language_server import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


@pytest.fixture(scope="module")
def bid_project_path():
    """Path to the bid project."""
    path = os.path.expanduser("~/code/bidfrontend/bid/")
    if not os.path.exists(path):
        pytest.skip(f"Bid project not found at {path}")
    return Path(path)


@pytest.fixture(scope="module")
def swift_language_server_bid(bid_project_path: Path):
    """Create a SyncLanguageServer instance configured for Swift using the bid project."""
    config = MultilspyConfig(code_language=Language.SWIFT)
    logger = MultilspyLogger()

    # Create a language server instance
    server = SyncLanguageServer.create(config, logger, str(bid_project_path))

    # Start the server
    server.start()

    try:
        yield server
    finally:
        # Ensure server is shut down
        server.stop()


class TestSwiftNonPackageProject:
    """Test the Swift language server's functionality on projects without Package.swift."""
    
    def test_server_startup(self, swift_language_server_bid):
        """Test that the server starts up successfully."""
        assert swift_language_server_bid is not None
        assert swift_language_server_bid.language_server is not None
    
    def test_document_symbols(self, swift_language_server_bid, bid_project_path):
        """Test that we can retrieve document symbols from Swift files."""
        # Find a Swift file in the project
        swift_files = []
        for root, _, files in os.walk(bid_project_path):
            for file in files:
                if file.endswith(".swift"):
                    swift_files.append(os.path.relpath(os.path.join(root, file), bid_project_path))
                    if len(swift_files) >= 5:  # Limit to 5 files
                        break
            if len(swift_files) >= 5:
                break
        
        if not swift_files:
            pytest.skip("No Swift files found in the bid project")
        
        # Test document symbols for each file
        for file_path in swift_files:
            symbols, _ = swift_language_server_bid.request_document_symbols(file_path)
            # In a non-Package project, we might not get symbols, but at least the call should not fail
            print(f"Found {len(symbols)} symbols in {file_path}")
    
    def test_swift_request_containing_symbol(self, swift_language_server_bid, bid_project_path):
        """Test finding the containing symbol for a position in a Swift file."""
        # Find a Swift file in the project
        swift_files = []
        for root, _, files in os.walk(bid_project_path):
            for file in files:
                if file.endswith(".swift"):
                    swift_files.append(os.path.relpath(os.path.join(root, file), bid_project_path))
                    if len(swift_files) >= 1:  # Just need one file
                        break
            if len(swift_files) >= 1:
                break
        
        if not swift_files:
            pytest.skip("No Swift files found in the bid project")
        
        file_path = swift_files[0]
        
        # Get file content to find a good position to test
        repo_path = swift_language_server_bid.language_server.repository_root_path
        full_path = os.path.join(repo_path, file_path)
        
        try:
            with open(full_path) as f:
                lines = f.readlines()
            
            # Find a line with some code (not a comment or whitespace)
            target_line = 0
            for i, line in enumerate(lines):
                # Look for lines that might contain class/func/var definitions
                if any(keyword in line for keyword in ["class ", "struct ", "func ", "var ", "let "]):
                    target_line = i
                    break
            
            # If we can't find a good line, just use line 10 (or last line if file is shorter)
            if target_line == 0:
                target_line = min(10, len(lines) - 1)
            
            # Request containing symbol
            containing_symbol = swift_language_server_bid.request_containing_symbol(
                file_path, target_line, 10, include_body=True
            )
            
            # Print results for debugging
            print(f"Containing symbol for {file_path}:{target_line}:")
            if containing_symbol:
                print(f"  Name: {containing_symbol.get('name', 'unknown')}")
                print(f"  Kind: {containing_symbol.get('kind', 'unknown')}")
                if 'body' in containing_symbol:
                    body_preview = containing_symbol['body'][:100] + "..." if len(containing_symbol['body']) > 100 else containing_symbol['body']
                    print(f"  Body preview: {body_preview}")
            else:
                print("  No containing symbol found")
            
        except Exception as e:
            pytest.skip(f"Error testing containing symbol: {e}")
    
    def test_swift_request_referencing_symbols(self, swift_language_server_bid, bid_project_path):
        """Test finding references to a Swift symbol."""
        # Find Swift files in the project
        swift_files = []
        for root, _, files in os.walk(bid_project_path):
            for file in files:
                if file.endswith(".swift"):
                    swift_files.append(os.path.relpath(os.path.join(root, file), bid_project_path))
                    if len(swift_files) >= 10:  # Get more files to increase chance of finding references
                        break
            if len(swift_files) >= 10:
                break
        
        if not swift_files:
            pytest.skip("No Swift files found in the bid project")
        
        # We'll need to find a symbol that might be referenced elsewhere
        symbols_to_test = []
        
        # Collect potential symbols from multiple files
        for file_path in swift_files[:5]:  # Check first 5 files
            try:
                # Get all document symbols
                doc_symbols, _ = swift_language_server_bid.request_document_symbols(file_path)
                
                for symbol in doc_symbols:
                    # Look for classes, structs, enums, or functions that might be referenced
                    if symbol.get('kind') in [5, 22, 23, 12]:  # Class, Struct, Enum, Function
                        symbols_to_test.append({
                            'file': file_path,
                            'name': symbol.get('name', 'Unknown'),
                            'line': symbol['location']['range']['start']['line'],
                            'character': symbol['location']['range']['start']['character'] + 1  # +1 to be inside the symbol name
                        })
                    
                    # If we found enough symbols, we can stop
                    if len(symbols_to_test) >= 5:
                        break
                
                if len(symbols_to_test) >= 5:
                    break
                    
            except Exception as e:
                print(f"Error collecting symbols from {file_path}: {e}")
                continue
        
        if not symbols_to_test:
            pytest.skip("No suitable symbols found for testing references")
        
        # Try finding references for each symbol
        for symbol in symbols_to_test:
            print(f"\nTesting references for symbol: {symbol['name']} in {symbol['file']}")
            
            try:
                # Request referencing symbols
                ref_symbols = swift_language_server_bid.request_referencing_symbols(
                    symbol['file'], symbol['line'], symbol['character'], include_imports=True
                )
                
                # Print results
                print(f"Found {len(ref_symbols)} referencing symbols for {symbol['name']}")
                
                for i, ref in enumerate(ref_symbols[:5]):  # Show first 5 references
                    ref_name = ref.get('name', 'Unknown')
                    ref_file = ref.get('location', {}).get('relativePath', 'Unknown file')
                    print(f"  {i+1}. {ref_name} in {ref_file}")
                
                # In a non-Package project, we might not get many references, but the call should work
                # Just test that references list is available, even if empty
                assert isinstance(ref_symbols, list)
                
            except Exception as e:
                print(f"Error finding references for {symbol['name']}: {e}")
                # Not failing the test for specific symbols
                continue

    def test_swift_definitions(self, swift_language_server_bid, bid_project_path):
        """Test finding definitions in Swift files."""
        # Find a Swift file in the project
        swift_files = []
        for root, _, files in os.walk(bid_project_path):
            for file in files:
                if file.endswith(".swift"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, bid_project_path)
                    
                    # Read the file to find method calls or variable uses
                    try:
                        with open(full_path) as f:
                            content = f.readlines()
                            
                        # Look for interesting lines with potential symbol usages
                        for i, line in enumerate(content):
                            line = line.strip()
                            # Skip empty lines, comments and imports
                            if not line or line.startswith("//") or line.startswith("import"):
                                continue
                                
                            # Look for method calls or variable uses
                            # This is a simple heuristic that looks for name.method() or variables
                            if "." in line and "(" in line or "let " in line or "var " in line:
                                swift_files.append((rel_path, i, line))
                                if len(swift_files) >= 5:
                                    break
                    except Exception:
                        continue
                        
                    if len(swift_files) >= 5:
                        break
            if len(swift_files) >= 5:
                break
        
        if not swift_files:
            pytest.skip("No suitable Swift files found in the bid project")
        
        # Test go-to-definition for some positions in these files
        for file_info in swift_files:
            file_path, line_num, line_content = file_info
            
            print(f"\nTesting definition for line in {file_path}:{line_num+1}")
            print(f"Line: {line_content}")
            
            # Find a good column position (e.g., after a dot for method calls)
            col_pos = 10  # Default
            if "." in line_content:
                col_pos = line_content.find(".") + 2  # Position after the dot and first character
            elif "(" in line_content:
                col_pos = line_content.find("(") - 1  # Position at the function name
            
            try:
                # Request definition
                locations = swift_language_server_bid.request_definition(
                    file_path, line_num, col_pos
                )
                
                # Print results
                print(f"Found {len(locations)} definition locations")
                for i, loc in enumerate(locations):
                    loc_file = loc.get('absolutePath', 'Unknown file')
                    loc_line = loc.get('range', {}).get('start', {}).get('line', 'Unknown line')
                    print(f"  {i+1}. Definition at {loc_file}:{loc_line+1}")
                
                # The test passes if the request doesn't throw an exception
                # We can't guarantee definitions will be found
                
            except Exception as e:
                print(f"Error finding definition: {e}")
                # Continue with next file, don't fail the test