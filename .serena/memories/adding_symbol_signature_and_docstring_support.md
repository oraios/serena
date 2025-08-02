# Adding Symbol Signature and Docstring Support to FindSymbolTool

## Overview

This document outlines the implementation plan for extending the FindSymbolTool to include symbol signatures and docstrings. The feature will leverage existing LSP hover functionality and add new signature help capabilities to provide rich symbol information when `include_body` is false for methods and classes.

## Current Architecture Analysis

### Existing Components

1. **FindSymbolTool** (`src/serena/tools/symbol_tools.py`)
   - Uses `LanguageServerSymbolRetriever` for symbol discovery
   - Returns `UnifiedSymbolInformation` objects with basic metadata
   - Supports optional body content inclusion via `include_body` parameter

2. **SolidLanguageServer** (`src/solidlsp/ls.py`)
   - **✅ Hover support**: `request_hover()` method already implemented (lines 1164-1191)
   - **❌ Signature help**: LSP protocol support exists but not implemented
   - Handles LSP communication with language-specific servers

3. **UnifiedSymbolInformation** (`src/solidlsp/ls_types.py`)
   - Contains `detail` field that could store signature information
   - Currently unused for systematic signature/docstring storage

## Implementation Plan

### Phase 1: Extend Language Server Interface

#### 1.1 Add Signature Help Support to SolidLanguageServer

**File**: `src/solidlsp/ls.py`

Add new method following the existing `request_hover()` pattern:

```python
async def request_signature_help(
    self,
    file_path: str,
    line: int,
    column: int,
    timeout_seconds: float = 5.0
) -> SignatureHelp | None:
    """Request signature help for a symbol at the given position."""
    if not self.supports_signature_help():
        return None
    
    try:
        params = SignatureHelpParams(
            textDocument=TextDocumentIdentifier(uri=f"file://{file_path}"),
            position=Position(line=line, character=column)
        )
        response = await self.client.signature_help_request(params)
        return response
    except Exception as e:
        logger.warning(f"Signature help request failed: {e}")
        return None

def supports_signature_help(self) -> bool:
    """Check if language server supports signature help."""
    capabilities = self.get_server_capabilities()
    return capabilities and getattr(
        capabilities, 'signatureHelpProvider', None
    ) is not None
```

#### 1.2 Add LSP Protocol Support

**File**: `src/solidlsp/lsp_protocol_handler/lsp_requests.py`

Add signature help request method:

```python
async def signature_help_request(
    self, params: SignatureHelpParams
) -> SignatureHelp | None:
    """Send signature help request to language server."""
    response = await self.send_request("textDocument/signatureHelp", params)
    if response:
        return SignatureHelp.parse_obj(response)
    return None
```

#### 1.3 Update LSP Types

**File**: `src/solidlsp/lsp_protocol_handler/lsp_types.py`

Ensure complete type definitions exist (they may already be present):

```python
class SignatureHelpParams(BaseModel):
    textDocument: TextDocumentIdentifier
    position: Position
    context: Optional[SignatureHelpContext] = None

class SignatureInformation(BaseModel):
    label: str
    documentation: Optional[Union[str, MarkupContent]] = None
    parameters: Optional[List[ParameterInformation]] = None

class SignatureHelp(BaseModel):
    signatures: List[SignatureInformation]
    activeSignature: Optional[int] = None
    activeParameter: Optional[int] = None
```

### Phase 2: Create Symbol Information Retrieval System

#### 2.1 Add SymbolInfoRetriever Class

**File**: `src/solidlsp/symbol_info_retriever.py` (new file)

```python
from dataclasses import dataclass
from typing import Optional
from .ls import SolidLanguageServer
from .ls_types import UnifiedSymbolInformation, SymbolKind

@dataclass
class SymbolInfo:
    signature: Optional[str] = None
    docstring: Optional[str] = None
    
    def is_empty(self) -> bool:
        return not self.signature and not self.docstring

class SymbolInfoRetriever:
    def __init__(self, language_server: SolidLanguageServer):
        self.language_server = language_server
    
    async def get_symbol_info(
        self, 
        symbol: UnifiedSymbolInformation
    ) -> SymbolInfo:
        """Retrieve signature and docstring for a symbol."""
        if not self._should_retrieve_info(symbol):
            return SymbolInfo()
        
        # Get position from symbol's selection range or range
        position = self._get_symbol_position(symbol)
        if not position:
            return SymbolInfo()
        
        file_path = symbol['location']['uri'].replace('file://', '')
        line, column = position
        
        # Retrieve hover information (for docstrings)
        hover_info = await self.language_server.request_hover(
            file_path, line, column
        )
        
        # Retrieve signature information (for methods/functions)
        signature_info = await self.language_server.request_signature_help(
            file_path, line, column
        )
        
        return self._parse_symbol_info(hover_info, signature_info, symbol)
    
    def _should_retrieve_info(self, symbol: UnifiedSymbolInformation) -> bool:
        """Check if symbol type warrants information retrieval."""
        retrievable_kinds = {
            SymbolKind.Function,
            SymbolKind.Method,
            SymbolKind.Class,
            SymbolKind.Constructor,
            SymbolKind.Variable,  # Python can have variable docstrings
            SymbolKind.Field,
            SymbolKind.Property
        }
        return symbol['kind'] in retrievable_kinds
    
    def _get_symbol_position(self, symbol: UnifiedSymbolInformation) -> Optional[tuple[int, int]]:
        """Extract line/column position from symbol."""
        # Prefer selectionRange (symbol name) over range (full symbol)
        range_info = symbol.get('selectionRange') or symbol.get('range')
        if range_info:
            start = range_info['start']
            return start['line'], start['character']
        return None
    
    def _parse_symbol_info(
        self, 
        hover_info, 
        signature_info, 
        symbol: UnifiedSymbolInformation
    ) -> SymbolInfo:
        """Parse LSP responses into SymbolInfo."""
        signature = None
        docstring = None
        
        # Extract signature from signature help
        if signature_info and signature_info.signatures:
            signature = signature_info.signatures[0].label
        
        # Extract docstring from hover
        if hover_info and hover_info.contents:
            docstring = self._extract_docstring_from_hover(hover_info.contents)
        
        # Fallback to symbol detail for signature if no signature help
        if not signature and symbol.get('detail'):
            detail = symbol['detail']
            if self._looks_like_signature(detail):
                signature = detail
        
        return SymbolInfo(signature=signature, docstring=docstring)
    
    def _extract_docstring_from_hover(self, contents) -> Optional[str]:
        """Extract readable docstring from hover contents."""
        if isinstance(contents, str):
            return self._clean_hover_text(contents)
        elif isinstance(contents, list):
            # Join multiple content blocks
            text_parts = []
            for content in contents:
                if isinstance(content, str):
                    text_parts.append(content)
                elif hasattr(content, 'value'):
                    text_parts.append(content.value)
            return self._clean_hover_text('\n'.join(text_parts))
        elif hasattr(contents, 'value'):
            return self._clean_hover_text(contents.value)
        return None
    
    def _clean_hover_text(self, text: str) -> str:
        """Clean markdown and code formatting from hover text."""
        import re
        # Remove code block markers
        text = re.sub(r'```[\w]*\n', '', text)
        text = re.sub(r'```', '', text)
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n', '\n', text)
        return text.strip()
    
    def _looks_like_signature(self, detail: str) -> bool:
        """Heuristic to identify if detail contains a signature."""
        return ('(' in detail and ')' in detail) or '->' in detail or '=>' in detail
```

#### 2.2 Integrate with UnifiedSymbolInformation

**File**: `src/solidlsp/ls_types.py`

Extend the UnifiedSymbolInformation type:

```python
class UnifiedSymbolInformation(TypedDict):
    name: str
    kind: SymbolKind
    detail: NotRequired[str]
    range: NotRequired[Range]
    selectionRange: NotRequired[Range]
    body: NotRequired[str]
    children: list[UnifiedSymbolInformation]
    parent: NotRequired[UnifiedSymbolInformation | None]
    location: Location
    # New fields
    signature: NotRequired[str]
    docstring: NotRequired[str]
```

### Phase 3: Update FindSymbolTool

#### 3.1 Modify FindSymbolTool to Include Symbol Info

**File**: `src/serena/tools/symbol_tools.py`

Update the `find_symbol` method:

```python
async def find_symbol(
    self,
    name_path: str,
    include_body: bool = False,
    include_signature_and_docstring: bool = True,  # New parameter
    kinds: list[int] = None,
    relative_path: str = None,
) -> str:
    """Find symbols matching the given name path pattern.
    
    Args:
        name_path: Pattern to match symbols against
        include_body: Whether to include symbol body content
        include_signature_and_docstring: Whether to include signature/docstring info
        kinds: Filter by LSP SymbolKind values (1-26)
        relative_path: Restrict search to specific path
    """
    # ... existing symbol finding logic ...
    
    # New: Enhance symbols with signature/docstring info
    if include_signature_and_docstring and not include_body:
        symbols = await self._add_symbol_info(symbols)
    
    return json.dumps(symbols, indent=2, default=str)

async def _add_symbol_info(
    self, 
    symbols: list[UnifiedSymbolInformation]
) -> list[UnifiedSymbolInformation]:
    """Add signature and docstring information to symbols."""
    from ..solidlsp.symbol_info_retriever import SymbolInfoRetriever
    
    enhanced_symbols = []
    
    for symbol in symbols:
        # Only enhance methods and classes
        if symbol['kind'] in {SymbolKind.Function, SymbolKind.Method, SymbolKind.Class}:
            # Get language server for this file
            file_path = symbol['location']['uri'].replace('file://', '')
            retriever = await self._get_symbol_info_retriever(file_path)
            
            if retriever:
                symbol_info = await retriever.get_symbol_info(symbol)
                if not symbol_info.is_empty():
                    enhanced_symbol = symbol.copy()
                    if symbol_info.signature:
                        enhanced_symbol['signature'] = symbol_info.signature
                    if symbol_info.docstring:
                        enhanced_symbol['docstring'] = symbol_info.docstring
                    enhanced_symbols.append(enhanced_symbol)
                    continue
        
        enhanced_symbols.append(symbol)
    
    return enhanced_symbols

async def _get_symbol_info_retriever(self, file_path: str) -> Optional[SymbolInfoRetriever]:
    """Get SymbolInfoRetriever for a specific file."""
    language_server = await self.get_language_server_for_file(file_path)
    if language_server:
        return SymbolInfoRetriever(language_server)
    return None
```

### Phase 4: Testing Implementation

#### 4.1 Create Manual Testing Script

**File**: `scripts/test_symbol_info_demo.py` (new file)

```python
#!/usr/bin/env python3
"""Manual testing script for symbol signature and docstring functionality."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from serena.agent import SerenaAgent
from serena.config.contexts import get_context_by_name

async def test_symbol_info():
    """Test symbol signature and docstring retrieval."""
    
    # Initialize agent
    context = get_context_by_name("agent")
    agent = SerenaAgent(context=context)
    
    # Test cases for different languages
    test_cases = [
        # Python - function with docstring
        {
            "name": "Python function with docstring",
            "args": {
                "name_path": "calculate_sum",
                "include_body": False,
                "include_signature_and_docstring": True
            }
        },
        # Python - class with docstring  
        {
            "name": "Python class with docstring",
            "args": {
                "name_path": "DataProcessor", 
                "include_body": False,
                "include_signature_and_docstring": True
            }
        },
        # Python - variable with docstring (if supported)
        {
            "name": "Python variable with docstring",
            "args": {
                "name_path": "CONSTANT_VALUE",
                "include_body": False, 
                "include_signature_and_docstring": True
            }
        }
    ]
    
    for test_case in test_cases:
        print(f"\n=== {test_case['name']} ===")
        try:
            result = await agent.find_symbol(**test_case['args'])
            print("Result:", result)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_symbol_info())
```

#### 4.2 Unit Test Implementation

**File**: `test/solidlsp/test_symbol_info_retrieval.py` (new file)

```python
"""Unit tests for symbol signature and docstring retrieval functionality."""

import pytest
from pathlib import Path

from solidlsp.symbol_info_retriever import SymbolInfoRetriever, SymbolInfo
from solidlsp.ls_types import UnifiedSymbolInformation, SymbolKind


class TestSymbolInfoRetrieval:
    """Test symbol information retrieval across all supported languages."""
    
    @pytest.mark.python
    @pytest.mark.asyncio
    async def test_retrieve_symbol_info_python_function(self, python_language_server):
        """Test signature and docstring retrieval for Python functions."""
        # Setup test symbol
        test_symbol = self._create_test_symbol(
            name="test_function",
            kind=SymbolKind.Function,
            file_path="test/resources/repos/python/test_repo/functions.py",
            line=10, column=0
        )
        
        # Test retrieval
        retriever = SymbolInfoRetriever(python_language_server)
        symbol_info = await retriever.get_symbol_info(test_symbol)
        
        # Assertions
        assert symbol_info.signature is not None
        assert "test_function" in symbol_info.signature
        assert "(" in symbol_info.signature and ")" in symbol_info.signature
        assert symbol_info.docstring is not None
        assert len(symbol_info.docstring) > 0

    @pytest.mark.python
    @pytest.mark.asyncio
    async def test_retrieve_symbol_info_python_class(self, python_language_server):
        """Test signature and docstring retrieval for Python classes."""
        test_symbol = self._create_test_symbol(
            name="TestClass",
            kind=SymbolKind.Class,
            file_path="test/resources/repos/python/test_repo/classes.py",
            line=5, column=0
        )
        
        retriever = SymbolInfoRetriever(python_language_server)
        symbol_info = await retriever.get_symbol_info(test_symbol)
        
        assert symbol_info.docstring is not None
        # Classes may not have signatures in traditional sense
        
    @pytest.mark.python
    @pytest.mark.asyncio
    async def test_retrieve_symbol_info_python_variable_with_docstring(self, python_language_server):
        """Test docstring retrieval for Python variables (module-level constants)."""
        test_symbol = self._create_test_symbol(
            name="MODULE_CONSTANT",
            kind=SymbolKind.Variable,
            file_path="test/resources/repos/python/test_repo/constants.py",
            line=3, column=0
        )
        
        retriever = SymbolInfoRetriever(python_language_server)
        symbol_info = await retriever.get_symbol_info(test_symbol)
        
        # Python variables can have docstrings
        if symbol_info.docstring:
            assert len(symbol_info.docstring) > 0

    @pytest.mark.typescript
    @pytest.mark.asyncio
    async def test_retrieve_symbol_info_typescript_function(self, typescript_language_server):
        """Test signature and docstring retrieval for TypeScript functions."""
        test_symbol = self._create_test_symbol(
            name="calculateSum",
            kind=SymbolKind.Function,
            file_path="test/resources/repos/typescript/test_repo/functions.ts",
            line=8, column=0
        )
        
        retriever = SymbolInfoRetriever(typescript_language_server)
        symbol_info = await retriever.get_symbol_info(test_symbol)
        
        assert symbol_info.signature is not None
        assert "calculateSum" in symbol_info.signature
        # TypeScript should show type annotations
        assert ":" in symbol_info.signature

    @pytest.mark.go
    @pytest.mark.asyncio
    async def test_retrieve_symbol_info_go_function(self, go_language_server):
        """Test signature and docstring retrieval for Go functions."""
        test_symbol = self._create_test_symbol(
            name="CalculateSum",
            kind=SymbolKind.Function,
            file_path="test/resources/repos/go/test_repo/functions.go",
            line=5, column=0
        )
        
        retriever = SymbolInfoRetriever(go_language_server)
        symbol_info = await retriever.get_symbol_info(test_symbol)
        
        assert symbol_info.signature is not None
        assert "CalculateSum" in symbol_info.signature
        # Go comments above functions should be captured
        if symbol_info.docstring:
            assert len(symbol_info.docstring) > 0

    @pytest.mark.asyncio
    async def test_symbol_info_empty_when_no_info_available(self, python_language_server):
        """Test that SymbolInfo is empty when no signature/docstring available."""
        test_symbol = self._create_test_symbol(
            name="simple_variable",
            kind=SymbolKind.Variable,
            file_path="test/resources/repos/python/test_repo/simple.py",
            line=1, column=0
        )
        
        retriever = SymbolInfoRetriever(python_language_server)
        symbol_info = await retriever.get_symbol_info(test_symbol)
        
        # Should be empty if no signature or docstring
        if not symbol_info.signature and not symbol_info.docstring:
            assert symbol_info.is_empty()

    def _create_test_symbol(
        self, 
        name: str, 
        kind: SymbolKind, 
        file_path: str, 
        line: int, 
        column: int
    ) -> UnifiedSymbolInformation:
        """Helper to create test symbol objects."""
        return {
            "name": name,
            "kind": kind,
            "location": {
                "uri": f"file://{file_path}",
                "range": {
                    "start": {"line": line, "character": column},
                    "end": {"line": line, "character": column + len(name)}
                }
            },
            "selectionRange": {
                "start": {"line": line, "character": column},
                "end": {"line": line, "character": column + len(name)}
            },
            "children": []
        }


# Add parametrized test for all supported languages
@pytest.mark.parametrize("language", ["python", "typescript", "go", "java", "rust"])
@pytest.mark.asyncio
async def test_retrieve_symbol_info_all_languages(language, request):
    """Test symbol info retrieval for all supported languages."""
    # Get language server fixture dynamically
    language_server = request.getfixturevalue(f"{language}_language_server")
    
    # Skip if language server not available
    if not language_server:
        pytest.skip(f"{language} language server not available")
    
    # Test basic functionality exists
    retriever = SymbolInfoRetriever(language_server)
    assert retriever is not None
    assert retriever.language_server == language_server
```

#### 4.3 Add Test Resources

Create test files in `test/resources/repos/<language>/test_repo/` for each language with examples of:

- Functions/methods with signatures and docstrings
- Classes with docstrings  
- Variables with docstrings (where supported)
- Functions without docstrings (to test empty info)

**Example for Python** (`test/resources/repos/python/test_repo/symbol_info_examples.py`):

```python
"""Test file for symbol info retrieval."""

MODULE_CONSTANT = "test_value"
"""This is a module-level constant with a docstring."""

def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two integers.
    
    Args:
        a: First integer
        b: Second integer
        
    Returns:
        The sum of a and b
    """
    return a + b

class DataProcessor:
    """A class for processing data.
    
    This class provides methods for various data processing operations.
    """
    
    def process_data(self, data: list) -> dict:
        """Process input data and return results.
        
        Args:
            data: List of data items to process
            
        Returns:
            Dictionary containing processing results
        """
        return {"processed": len(data)}

# Function without docstring for testing empty info
def simple_function():
    return "no docstring"

simple_variable = 42  # No docstring
```

## Implementation Challenges and Solutions

### Challenge 1: Language Server Capability Differences

**Problem**: Different language servers have varying levels of support for hover and signature help.

**Solution**: 
- Implement capability detection methods (`supports_signature_help()`, `supports_hover()`)
- Graceful degradation when features not supported
- Fallback to symbol `detail` field when signature help unavailable

### Challenge 2: Information Format Variations

**Problem**: Hover and signature help responses vary significantly between languages.

**Solutions**:
- Abstract parsing logic in `SymbolInfoRetriever._parse_symbol_info()`
- Language-specific parsing strategies where needed
- Robust text cleaning for markdown/code formatting
- Heuristic detection of signature vs. docstring content

### Challenge 3: Performance Impact

**Problem**: Additional LSP requests for each symbol could slow down FindSymbolTool.

**Solutions**:
- Only retrieve info for methods/classes when `include_body=False`
- Implement caching at the language server level
- Batch requests where possible
- Make signature/docstring retrieval optional via parameter

### Challenge 4: Test Complexity

**Problem**: Testing across 13+ languages requires extensive test data and setup.

**Solutions**:
- Create parametrized tests for common functionality
- Language-specific test cases for unique features
- Test resource files with realistic symbol examples
- Mock language server responses for unit tests where needed

### Challenge 5: Error Handling

**Problem**: LSP requests can fail or timeout, breaking symbol retrieval.

**Solutions**:
- Wrap all LSP calls in try-catch blocks
- Set reasonable timeouts (5 seconds default)
- Log warnings but don't fail the entire symbol search
- Return empty SymbolInfo on errors

## Migration Strategy

### Phase 1: Core Infrastructure (Week 1)
- Implement signature help in SolidLanguageServer
- Create SymbolInfoRetriever class
- Add basic unit tests

### Phase 2: Integration (Week 2) 
- Integrate with FindSymbolTool
- Update UnifiedSymbolInformation type
- Create manual testing script

### Phase 3: Testing & Validation (Week 3)
- Comprehensive test suite across all languages
- Performance testing and optimization
- Error handling validation

### Phase 4: Documentation & Polish (Week 4)
- Update API documentation
- Code review and refinements
- Performance tuning based on testing results

## Success Criteria

1. **Functional Requirements**:
   - FindSymbolTool includes signature/docstring for methods and classes when `include_body=False`
   - Information retrieval works for all supported languages with LSP capability
   - Empty info returned when no signature/docstring available
   - Existing functionality remains unaffected

2. **Quality Requirements**:
   - All tests pass: `uv run poe test`
   - Code formatting: `uv run poe format`
   - Type checking: `uv run poe type-check`
   - Performance impact < 20% on symbol searches

3. **Testing Requirements**:
   - Unit tests for SymbolInfoRetriever with all languages
   - Integration tests with FindSymbolTool
   - Manual testing script demonstrating functionality
   - Error handling validation

This implementation will provide rich symbol information while maintaining the existing architecture's robustness and performance characteristics.