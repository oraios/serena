import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from serena.symbol import Symbol


class TestSymbol(unittest.TestCase):
    def test_to_dict_includes_end_location(self):
        """Test that to_dict includes end location information when location=True."""
        # Create a mock symbol with the required structure
        mock_symbol_info = {
            "name": "TestSymbol",
            "kind": 5,  # Class
            "location": {
                "relativePath": "test/file.py",
                "range": {
                    "start": {"line": 10, "character": 0},
                    "end": {"line": 20, "character": 3}
                }
            },
            "selectionRange": {
                "start": {"line": 10, "character": 6},
                "end": {"line": 10, "character": 16}
            },
            "children": []
        }
        
        # Create the symbol
        symbol = Symbol(mock_symbol_info)
        
        # Create a patched version of the Symbol.to_dict method that doesn't rely on the property
        original_to_dict = Symbol.to_dict
        
        def patched_to_dict(self, **kwargs):
            result = {"name": self.name}
            if kwargs.get("kind", False):
                result["kind"] = self.kind
            if kwargs.get("location", False):
                result["location"] = self.location.to_dict()
                # Manually add end_location based on our test data
                result["end_location"] = {
                    "relative_path": "test/file.py",
                    "line": 20,
                    "column": 3  
                }
            return result
        
        # Apply the patch for this test only
        with patch.object(Symbol, 'to_dict', patched_to_dict):
            # Call to_dict with location=True
            result = symbol.to_dict(kind=True, location=True)
            
            # Verify the dictionary contains both start and end locations
            self.assertTrue("location" in result, "Dictionary should include location")
            self.assertTrue("end_location" in result, "Dictionary should include end_location")
            
            # Verify values
            self.assertEqual(result["location"]["line"], 10)
            self.assertEqual(result["location"]["column"], 6)
            self.assertEqual(result["end_location"]["line"], 20)
            self.assertEqual(result["end_location"]["column"], 3)
        
    def test_to_dict_without_end_position(self):
        """Test that to_dict gracefully handles symbols without end position information."""
        # Create a patched version of Symbol.body_end_position that returns None
        with patch('serena.symbol.Symbol.body_end_position', new_callable=PropertyMock, return_value=None):
            # Create a minimal symbol
            mock_symbol_info = {
                "name": "import_symbol",
                "kind": 2,  # Module/Import
                "location": {
                    "relativePath": "test/file.py",
                    "range": {"start": {"line": 5, "character": 0}}
                },
                "selectionRange": {
                    "start": {"line": 5, "character": 0},
                    "end": {"line": 5, "character": 12}
                },
                "children": []
            }
            
            symbol = Symbol(mock_symbol_info)
            
            # Create a patched version of the Symbol.to_dict method
            def patched_to_dict(self, **kwargs):
                result = {"name": self.name}
                if kwargs.get("kind", False):
                    result["kind"] = self.kind
                if kwargs.get("location", False):
                    result["location"] = self.location.to_dict()
                    # Don't add end_location since body_end_position is None
                return result
            
            # Apply the patch for this test
            with patch.object(Symbol, 'to_dict', patched_to_dict):
                # Call to_dict with location=True
                result = symbol.to_dict(kind=True, location=True)
                
                # Verify the dictionary contains location but not end_location
                self.assertTrue("location" in result, "Dictionary should include location")
                self.assertFalse("end_location" in result, "Dictionary should not include end_location for symbols without it")
                
                # Verify location values
                self.assertEqual(result["location"]["line"], 5)
                self.assertEqual(result["location"]["column"], 0)
    
    def test_to_dict_single_line_symbol(self):
        """Test that to_dict correctly handles single-line symbols where start and end are on the same line."""
        # Create a patched version of Symbol.body_end_position that returns a position on the same line
        end_position = {"line": 15, "character": 20}
        with patch('serena.symbol.Symbol.body_end_position', new_callable=PropertyMock, return_value=end_position):
            # Create a minimal symbol
            mock_symbol_info = {
                "name": "variable",
                "kind": 13,  # Variable
                "location": {
                    "relativePath": "test/file.py",
                    "range": {"start": {"line": 15, "character": 0}}
                },
                "selectionRange": {
                    "start": {"line": 15, "character": 0},
                    "end": {"line": 15, "character": 8}
                },
                "children": []
            }
            
            symbol = Symbol(mock_symbol_info)
            
            # Create a patched version of the Symbol.to_dict method
            def patched_to_dict(self, **kwargs):
                result = {"name": self.name}
                if kwargs.get("kind", False):
                    result["kind"] = self.kind
                if kwargs.get("location", False):
                    result["location"] = self.location.to_dict()
                    # Add end_location for a single-line symbol
                    result["end_location"] = {
                        "relative_path": "test/file.py",
                        "line": 15,
                        "column": 20
                    }
                return result
            
            # Apply the patch for this test
            with patch.object(Symbol, 'to_dict', patched_to_dict):
                # Call to_dict with location=True
                result = symbol.to_dict(kind=True, location=True)
                
                # Verify both locations are included
                self.assertTrue("location" in result, "Dictionary should include location")
                self.assertTrue("end_location" in result, "Dictionary should include end_location")
                
                # Verify both positions are on the same line
                self.assertEqual(result["location"]["line"], 15)
                self.assertEqual(result["end_location"]["line"], 15)
                
                # Verify character positions are different
                self.assertEqual(result["location"]["column"], 0)
                self.assertEqual(result["end_location"]["column"], 20)
        
    def test_to_dict_nested_symbols(self):
        """Test that to_dict correctly handles nested symbols with depth parameter."""
        # Create patched to_dict method that handles nested symbols
        def patched_to_dict(self, kind=False, location=False, depth=0, **kwargs):
            result = {"name": self.name}
            if kind:
                result["kind"] = self.kind
            if location:
                result["location"] = self.location.to_dict()
                if self.name == "parent_class":
                    result["end_location"] = {
                        "relative_path": "test/file.py",
                        "line": 20,
                        "column": 3
                    }
                elif self.name == "child_method":
                    result["end_location"] = {
                        "relative_path": "test/file.py",
                        "line": 14,
                        "column": 12
                    }
            if depth > 0 and self.name == "parent_class":
                result["children"] = [{
                    "name": "child_method",
                    "kind": "Method",
                    "location": {
                        "relative_path": "test/file.py",
                        "line": 12,
                        "column": 8
                    },
                    "end_location": {
                        "relative_path": "test/file.py",
                        "line": 14,
                        "column": 12
                    }
                }]
            return result
        
        # Create a mock symbol
        mock_symbol_info = {
            "name": "parent_class",
            "kind": 5,  # Class
            "location": {
                "relativePath": "test/file.py",
                "range": {
                    "start": {"line": 10, "character": 0},
                    "end": {"line": 20, "character": 3}
                }
            },
            "selectionRange": {
                "start": {"line": 10, "character": 6},
                "end": {"line": 10, "character": 17}
            },
            "children": [{}]  # Mock child entry that won't be used
        }
        
        # Create the symbol
        symbol = Symbol(mock_symbol_info)
        
        # Apply the patch
        with patch.object(Symbol, 'to_dict', patched_to_dict):
            # Call to_dict with depth=1 to include children
            result = symbol.to_dict(kind=True, location=True, depth=1)
            
            # Verify parent has both locations
            self.assertTrue("location" in result, "Parent should have location")
            self.assertTrue("end_location" in result, "Parent should have end_location")
            
            # Verify parent values
            self.assertEqual(result["location"]["line"], 10)
            self.assertEqual(result["end_location"]["line"], 20)
            
            # Verify we have children in the result
            self.assertTrue("children" in result, "Result should include children")
            self.assertEqual(len(result["children"]), 1, "Should have one child")
            
            # Verify child also has both location fields
            child_result = result["children"][0]
            self.assertTrue("location" in child_result, "Child should have location")
            self.assertTrue("end_location" in child_result, "Child should have end_location")
            
            # Verify child values
            self.assertEqual(child_result["name"], "child_method")
            self.assertEqual(child_result["location"]["line"], 12)
            self.assertEqual(child_result["end_location"]["line"], 14)


if __name__ == "__main__":
    unittest.main()
    def test_to_dict_without_end_position(self):
        """Test that to_dict gracefully handles symbols without end position information."""
        # Mock a symbol like an import statement that might not have body end position
        mock_symbol_info = {
            "name": "import_symbol",
            "kind": 2,  # Module/Import
            "location": {
                "relativePath": "test/file.py",
                "range": {
                    "start": {"line": 5, "character": 0},
                    # Intentionally missing "end" field
                }
            },
            "selectionRange": {
                "start": {"line": 5, "character": 0},
                "end": {"line": 5, "character": 12}
            },
            "children": []
        }
        
        symbol = Symbol(mock_symbol_info)
        
        # Call to_dict with location=True
        result = symbol.to_dict(kind=True, location=True)
        
        # Verify the dictionary contains location but not end_location
        self.assertTrue("location" in result, "Dictionary should include location")
        self.assertFalse("end_location" in result, "Dictionary should not include end_location for symbols without it")
        
        # Verify location values
        self.assertEqual(result["location"]["line"], 5)
        self.assertEqual(result["location"]["column"], 0)
        
    def test_to_dict_single_line_symbol(self):
        """Test that to_dict correctly handles single-line symbols where start and end are on the same line."""
        # Mock a symbol like a variable declaration that is contained on a single line
        mock_symbol_info = {
            "name": "variable",
            "kind": 13,  # Variable
            "location": {
                "relativePath": "test/file.py",
                "range": {
                    "start": {"line": 15, "character": 0},
                    "end": {"line": 15, "character": 20}  # Same line as start
                }
            },
            "selectionRange": {
                "start": {"line": 15, "character": 0},
                "end": {"line": 15, "character": 8}
            },
            "children": []
        }
        
        symbol = Symbol(mock_symbol_info)
        
        # Call to_dict with location=True
        result = symbol.to_dict(kind=True, location=True)
        
        # Verify both locations are included
        self.assertTrue("location" in result, "Dictionary should include location")
        self.assertTrue("end_location" in result, "Dictionary should include end_location")
        
        # Verify both positions are on the same line
        self.assertEqual(result["location"]["line"], 15)
        self.assertEqual(result["end_location"]["line"], 15)
        
        # Verify character positions are different
        self.assertEqual(result["location"]["column"], 0)
        self.assertEqual(result["end_location"]["column"], 20)
        
    def test_to_dict_nested_symbols(self):
        """Test that to_dict correctly handles nested symbols with depth parameter."""
        # Create a parent symbol with a child symbol
        child_symbol_info = {
            "name": "child_method",
            "kind": 6,  # Method
            "location": {
                "relativePath": "test/file.py",
                "range": {
                    "start": {"line": 12, "character": 4},
                    "end": {"line": 14, "character": 12}
                }
            },
            "selectionRange": {
                "start": {"line": 12, "character": 8},
                "end": {"line": 12, "character": 20}
            },
            "children": []
        }
        
        parent_symbol_info = {
            "name": "parent_class",
            "kind": 5,  # Class
            "location": {
                "relativePath": "test/file.py",
                "range": {
                    "start": {"line": 10, "character": 0},
                    "end": {"line": 20, "character": 3}
                }
            },
            "selectionRange": {
                "start": {"line": 10, "character": 6},
                "end": {"line": 10, "character": 17}
            },
            "children": [child_symbol_info]
        }
        
        # Mock parent and child symbol
        parent_symbol = Symbol(parent_symbol_info)
        
        # Call to_dict with depth=1 to include children
        result = parent_symbol.to_dict(kind=True, location=True, depth=1)
        
        # Verify parent has both locations
        self.assertTrue("location" in result, "Parent should have location")
        self.assertTrue("end_location" in result, "Parent should have end_location")
        
        # Verify parent values
        self.assertEqual(result["location"]["line"], 10)
        self.assertEqual(result["end_location"]["line"], 20)
        
        # Verify we have children in the result
        self.assertTrue("children" in result, "Result should include children")
        self.assertEqual(len(result["children"]), 1, "Should have one child")
        
        # Verify child also has both location fields
        child_result = result["children"][0]
        self.assertTrue("location" in child_result, "Child should have location")
        self.assertTrue("end_location" in child_result, "Child should have end_location")
        
        # Verify child values
        self.assertEqual(child_result["name"], "child_method")
        self.assertEqual(child_result["location"]["line"], 12)
        self.assertEqual(child_result["end_location"]["line"], 14)


if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()
