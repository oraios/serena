# Language Server Architecture and Tool Propagation in Serena

## Overview
Serena uses a multi-layered architecture to interact with language servers, providing semantic code understanding through the Language Server Protocol (LSP). This document explains the abstraction layers and how new functionality propagates through them.

## Architecture Layers (Bottom to Top)

### 1. Process Layer
- **LanguageServerHandler** (`src/multilspy/lsp_protocol_handler/server.py`)
  - Manages the actual LSP process lifecycle (start/stop/cleanup)
  - Handles JSON-RPC communication over stdin/stdout pipes
  - Manages async message handling, request/response correlation
  - Contains process management, signal handling, and cleanup logic

### 2. Language Server Layer
- **LanguageServer** (`src/multilspy/language_server.py`)
  - Wraps LanguageServerHandler with LSP-specific functionality
  - Implements all LSP request methods (symbols, references, definitions, etc.)
  - Manages file buffers, caching, and language-specific configurations
  - Handles async-to-sync conversions for easier usage

### 3. Sync Language Server Layer
- **SyncLanguageServer** (`src/multilspy/language_server.py`)
  - Provides synchronous interface by wrapping LanguageServer
  - Manages event loop and threading for async operations
  - Exposes simplified synchronous API for all LSP operations
  - Handles timeout management and resource cleanup

### 4. Symbol Management Layer
- **SymbolManager** (`src/serena/symbol.py`)
  - High-level semantic operations (find symbols, references, etc.)
  - Uses SyncLanguageServer for language-specific operations
  - Provides code editing capabilities (replace body, insert, etc.)
  - Manages symbol location tracking and file change coordination

### 5. Symbol Abstraction Layer
- **Symbol** (`src/serena/symbol.py`)
  - Represents individual code symbols with location and metadata
  - Provides symbol tree navigation (parents, children, ancestors)
  - Handles name path matching and symbol identification
  - Contains body content and positional information

### 6. Tool Layer
- **Tool Classes** (`src/serena/agent.py`)
  - High-level tools like FindSymbolTool, ReplaceSymbolBodyTool, etc.
  - Use SymbolManager for semantic operations
  - Provide user-friendly interfaces with validation and error handling
  - Integrate with SerenaAgent's configuration and context system

### 7. Agent Layer
- **SerenaAgent** (`src/serena/agent.py`)
  - Orchestrates all tools and provides the main API
  - Manages project configuration, memory, and context
  - Handles tool registration and execution
  - Provides the interface for MCP server and other integrations

## How New Functionality Propagates

### Adding a New LSP Request Type

1. **Process Layer**: No changes needed (handles all JSON-RPC)

2. **Language Server Layer**: 
   - Add new async method to LanguageServer class
   - Handle LSP request/response format conversion
   - Add proper error handling and logging

3. **Sync Language Server Layer**:
   - Add corresponding synchronous wrapper method
   - Handle async-to-sync conversion with proper timeout

4. **Symbol Management Layer**:
   - Add method to SymbolManager if symbol-related
   - Integrate with existing symbol tracking and caching

5. **Symbol Layer**:
   - Add properties/methods to Symbol class if needed
   - Update symbol tree navigation if required

6. **Tool Layer**:
   - Create new Tool class inheriting from Tool base class
   - Implement execute() method with proper validation
   - Add tool to agent's tool registry

7. **Agent Layer**:
   - Register new tool in ToolRegistry
   - Update configuration if needed

### Adding a New Language Server

1. **Create language-specific handler** in `src/multilspy/language_servers/`
2. **Extend base LanguageServer** with language-specific configurations
3. **Update multilspy config** to recognize new language
4. **No changes needed** in higher layers - they work with any LSP-compliant server

### Adding a New Tool Using Existing LSP Functionality

1. **Tool Layer**: Create new Tool class using existing SymbolManager methods
2. **Agent Layer**: Register tool in ToolRegistry
3. **No changes needed** in lower layers

## Key Design Principles

- **Separation of Concerns**: Each layer has a specific responsibility
- **Language Agnostic**: Higher layers work with any LSP-compliant language server
- **Synchronous API**: Complex async handling is abstracted away from tool developers
- **Robust Error Handling**: Each layer adds appropriate error handling and recovery
- **Process Isolation**: Language server processes are properly managed and cleaned up

This architecture allows new developers to add functionality at the appropriate level without understanding all layers, while maintaining clean separation between process management, LSP protocol handling, semantic operations, and user-facing tools.