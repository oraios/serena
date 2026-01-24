# Murena Repository Structure

## Overview
Murena is a multi-language code assistant that combines two main components:
1. **Murena Core** - The main agent framework with tools and MCP server
2. **SolidLSP** - A unified Language Server Protocol wrapper for multiple programming languages

## Top-Level Structure

```
murena/
├── src/                          # Main source code
│   ├── murena/                   # Murena agent framework
│   ├── solidlsp/                 # LSP wrapper library  
│   └── interprompt/              # Multi-language prompt templates
├── test/                         # Test suites
│   ├── murena/                   # Murena agent tests
│   ├── solidlsp/                 # Language server tests
│   └── resources/repos/          # Test repositories for each language
├── scripts/                      # Build and utility scripts
├── resources/                    # Static resources and configurations
├── pyproject.toml               # Python project configuration
├── README.md                    # Project documentation
└── CHANGELOG.md                 # Version history
```

## Source Code Organization

### Murena Core (`src/murena/`)
- **`agent.py`** - Main MurenaAgent class that orchestrates everything
- **`tools/`** - MCP tools for file operations, symbols, memory, etc.
  - `file_tools.py` - File system operations (read, write, search)
  - `symbol_tools.py` - Symbol-based code operations (find, edit)
  - `memory_tools.py` - Knowledge persistence and retrieval
  - `config_tools.py` - Project and mode management
  - `workflow_tools.py` - Onboarding and meta-operations
- **`config/`** - Configuration management
  - `murena_config.py` - Main configuration classes
  - `context_mode.py` - Context and mode definitions
- **`util/`** - Utility modules
- **`mcp.py`** - MCP server implementation
- **`cli.py`** - Command-line interface

### SolidLSP (`src/solidlsp/`)
- **`ls.py`** - Main SolidLanguageServer class
- **`language_servers/`** - Language-specific implementations
  - `csharp_language_server.py` - C# (Microsoft.CodeAnalysis.LanguageServer)
  - `python_server.py` - Python (Pyright)
  - `typescript_language_server.py` - TypeScript
  - `rust_analyzer.py` - Rust
  - `gopls.py` - Go
  - And many more...
- **`ls_config.py`** - Language server configuration
- **`ls_types.py`** - LSP type definitions
- **`ls_utils.py`** - Utilities for working with LSP data

### Interprompt (`src/interprompt/`)
- Multi-language prompt template system
- Jinja2-based templating with language fallbacks

## Test Structure

### Language Server Tests (`test/solidlsp/`)
Each language has its own test directory:
```
test/solidlsp/
├── csharp/
│   └── test_csharp_basic.py
├── python/
│   └── test_python_basic.py
├── typescript/
│   └── test_typescript_basic.py
└── ...
```

### Test Resources (`test/resources/repos/`)
Contains minimal test projects for each language:
```
test/resources/repos/
├── csharp/test_repo/
│   ├── murena.sln
│   ├── TestProject.csproj
│   ├── Program.cs
│   └── Models/Person.cs
├── python/test_repo/
├── typescript/test_repo/
└── ...
```

### Test Infrastructure
- **`test/conftest.py`** - Shared test fixtures and utilities
- **`create_ls()`** function - Creates language server instances for testing
- **`language_server` fixture** - Parametrized fixture for multi-language tests

## Key Configuration Files

- **`pyproject.toml`** - Python dependencies, build config, and tool settings
- **`.murena/`** directories - Project-specific Murena configuration and memories
- **`CLAUDE.md`** - Instructions for AI assistants working on the project

## Dependencies Management

The project uses modern Python tooling:
- **uv** for fast dependency resolution and virtual environments
- **pytest** for testing with language-specific markers (`@pytest.mark.csharp`)
- **ruff** for linting and formatting
- **mypy** for type checking

## Build and Development

- **Docker support** - Full containerized development environment
- **GitHub Actions** - CI/CD with language server testing
- **Development scripts** in `scripts/` directory