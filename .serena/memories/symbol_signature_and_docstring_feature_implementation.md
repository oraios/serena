# Feature: Symbol Signature and Docstring Retrieval

## Overview

This feature extends the `FindSymbolTool` to retrieve symbol signatures and docstrings by leveraging language servers' signature help and hover functionality. The information should be included in `find_symbol` results for methods and classes when `include_body=false`.

## Implementation Plan

### 1. Language Server Extension

**Location:** `src/solidlsp/ls.py` - `SolidLanguageServer` class

**New Methods to Add:**
- `request_signature_help(relative_file_path: str, line: int, column: int) -> SignatureHelp | None`
  - Uses LSP `textDocument/signatureHelp` request
  - Returns signature information for callable symbols (methods, functions)
  - Similar pattern to existing `request_hover` method

**Enhancement to Existing Methods:**
- Modify `request_document_symbols` or create new method `request_symbol_info`
- For each symbol found, if it's a method/class/function:
  1. Get position of symbol definition
  2. Call `request_hover` to get docstring from hover content
  3. Call `request_signature_help` to get signature (for callable symbols)
  4. Combine this information into symbol metadata

### 2. Symbol Information Data Structure

**Location:** `src/solidlsp/ls_types.py`

**New Types:**
```python
@dataclass
class SymbolInfo:
    signature: str | None = None
    docstring: str | None = None
    
    def is_empty(self) -> bool:
        return not self.signature and not self.docstring
```

**Enhancement to UnifiedSymbolInformation:**
Add `symbol_info: SymbolInfo | None = None` field

### 3. Tool Integration

**Location:** `src/serena/tools/symbol_tools.py` - `FindSymbolTool` class

**Modifications:**
- Add new parameter `include_symbol_info: bool = False` 
- When `include_symbol_info=True` and `include_body=False`:
  - For symbols with kinds: Method (6), Function (12), Class (5), Constructor (9)
  - Retrieve symbol info using new language server methods
  - Include in returned symbol dictionaries

**Logic:**
- Only retrieve symbol info for relevant symbol kinds (methods, classes, functions)
- Info should be empty when no docstring/signature available
- If symbol has signature (method/function), include it even without docstring
- Python variables can have docstrings, so include them too

### 4. Testing Strategy

**Unit Tests:**
Create `test_retrieve_symbol_info` in each language's test suite:
- `test/solidlsp/python/test_python_symbol_info.py`
- `test/solidlsp/csharp/test_csharp_symbol_info.py`
- `test/solidlsp/typescript/test_typescript_symbol_info.py`
- etc.

**Test Cases per Language:**
1. **Method with docstring and signature** - should return both
2. **Method with signature only** - should return signature, empty docstring
3. **Method with docstring only** - should return docstring, signature may be inferred
4. **Class with docstring** - should return class docstring
5. **Variable with docstring** (Python-specific) - should return docstring
6. **Symbol without documentation** - should return empty info
7. **Non-callable symbols** - should not attempt signature retrieval

**Manual Testing:**
Create `scripts/demo_symbol_info.py` similar to `demo_run_tools.py`:
- Demonstrate retrieving symbol info for various symbol types
- Show integration with FindSymbolTool

### 5. Implementation Challenges & Solutions

**Challenge 1: Position Mapping**
- Need accurate line/column positions for LSP requests
- Solution: Use existing symbol location information from document symbols

**Challenge 2: Language Server Differences**
- Different LSPs provide different hover/signature formats
- Solution: Create language-agnostic parsing utilities
- Extract docstring from hover content (often in Markdown format)
- Extract signature from signature help response

**Challenge 3: Performance Impact**
- Multiple LSP requests per symbol could be slow
- Solution: 
  - Add caching layer for symbol info
  - Batch requests where possible
  - Only retrieve when explicitly requested (`include_symbol_info=True`)

**Challenge 4: Markdown Processing**
- Hover responses often contain Markdown
- Solution: Add utility to extract plain text docstrings from MarkupContent

**Challenge 5: Error Handling**
- LSP requests may fail or timeout
- Solution: Graceful fallback - return empty symbol info on failure

### 6. Code Style & Integration

**Consistency:**
- Follow existing patterns in `SolidLanguageServer` class
- Use same error handling and timeout patterns as `request_hover`
- Maintain existing naming conventions

**Object-Oriented Design:**
- Create dedicated classes for symbol info processing
- Separate concerns: LSP communication, data parsing, result formatting

**Testing Integration:**
- Use existing `create_ls()` fixture pattern
- Follow existing pytest marker system for language-specific tests
- Reuse test repository structures in `test/resources/repos/`

### 7. Expected File Changes

**New Files:**
- `scripts/demo_symbol_info.py` - Manual testing script
- `test/solidlsp/*/test_*_symbol_info.py` - Unit tests per language

**Modified Files:**
- `src/solidlsp/ls.py` - Add new methods
- `src/solidlsp/ls_types.py` - Add SymbolInfo dataclass
- `src/serena/tools/symbol_tools.py` - Extend FindSymbolTool
- Various test files to add `test_retrieve_symbol_info` tests

### 8. Implementation Order

1. **Data structures** - Add SymbolInfo types
2. **Language server methods** - Add signature/info retrieval
3. **Utility functions** - Markdown parsing, info extraction
4. **Tool integration** - Extend FindSymbolTool
5. **Testing** - Create comprehensive test suite
6. **Demo script** - Manual testing and demonstration
7. **Documentation** - Update tool descriptions and examples

This feature will significantly enhance the semantic understanding capabilities of Serena by providing rich symbol metadata alongside structural information.