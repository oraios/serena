# Serena Project Overview

## Purpose
Serena is a powerful coding agent toolkit that turns an LLM into a fully-featured agent capable of working directly on a codebase. It provides semantic code retrieval and editing tools (symbol-level extraction and relational structure exploitation) to enhance token efficiency and quality of AI-generated code.

## Key Capabilities
- **Symbol-level analysis**: Tools like `find_symbol`, `find_referencing_symbols`.
- **Precision editing**: `insert_after_symbol`, `replace_symbol_body`.
- **LSP Integration**: Supports 30+ programming languages via the Language Server Protocol.
- **MCP Server**: Exposes tools via Model Context Protocol for clients like Claude Code, Cursor, and IDEs.
- **Persistence**: Project knowledge memory system in Markdown format.

## Core Components
- **SerenaAgent (`src/serena/agent.py`)**: Orchestrator for projects, tools, and users.
- **SolidLanguageServer (`src/solidlsp/ls.py`)**: Unified wrapper for LSP servers.
- **Tool System (`src/serena/tools/`)**: File, symbol, memory, config, and workflow tools.
- **Configuration System (`src/serena/config/`)**: Contexts (environments) and Modes (operational patterns).
