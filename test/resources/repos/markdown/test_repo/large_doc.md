# Large Documentation Test

This is a comprehensive documentation file designed to test Markdown symbolic operations
with realistic documentation content. This file contains 600+ lines to validate token
efficiency when using symbolic tools versus reading the entire file.

## Table of Contents

- [Introduction](#introduction)
- [Installation Guide](#installation-guide)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Advanced Installation](#advanced-installation)
- [API Reference](#api-reference)
  - [Core API](#core-api)
  - [Advanced API](#advanced-api)
  - [Authentication API](#authentication-api)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Introduction

Welcome to the Large Documentation Test repository. This document serves as a comprehensive
guide to understanding how Murena MCP handles large markdown files efficiently through
symbolic operations.

### Why Symbolic Operations Matter

When working with documentation, traditional approaches require reading entire files
into context, which can consume 20,000+ tokens for a file of this size. Symbolic
operations using Marksman LSP allow for:

1. **Hierarchical navigation** - Access document structure without reading content
2. **Section-level extraction** - Read only relevant sections
3. **Token efficiency** - 70-90% reduction in token consumption
4. **Caching benefits** - Reuse structure across multiple queries

### Use Cases

This approach is particularly valuable for:

- Large README files (500+ lines)
- API documentation with many endpoints
- User guides with multiple sections
- Project wikis with interconnected documents
- Technical specifications with deep hierarchies

### Architecture Overview

The symbolic approach works in two phases:

**Phase 1: Structure Discovery**
```python
overview = get_symbols_overview(relative_path="large_doc.md", depth=2)
# Returns: Hierarchical list of headings (~1000 tokens)
```

**Phase 2: Content Extraction**
```python
section = find_symbol(
    name_path_pattern="Installation Guide",
    relative_path="large_doc.md",
    include_body=True
)
# Returns: Only the requested section (~500-1500 tokens)
```

**Total Token Cost**: ~1500-2500 tokens instead of 20,000+ tokens for full file read.

## Installation Guide

This section provides comprehensive installation instructions for various deployment
scenarios. Follow the appropriate subsection based on your use case.

### Prerequisites

Before installing, ensure your system meets these requirements:

#### System Requirements

- **Operating System**: Linux, macOS, or Windows
- **Python Version**: 3.11 or higher
- **Memory**: Minimum 4GB RAM (8GB recommended)
- **Disk Space**: At least 1GB free space
- **Network**: Internet connection for package downloads

#### Required Software

You'll need the following software installed:

1. **Python 3.11+**
   ```bash
   # On macOS with Homebrew
   brew install python@3.11

   # On Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install python3.11 python3.11-venv

   # On Windows
   # Download from python.org
   ```

2. **uv Package Manager**
   ```bash
   # Install uv (recommended)
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Or use pip
   pip install uv
   ```

3. **Git**
   ```bash
   # On macOS
   brew install git

   # On Ubuntu/Debian
   sudo apt-get install git

   # On Windows
   # Download from git-scm.com
   ```

#### Optional Dependencies

For enhanced functionality, consider installing:

- **Docker** - For containerized deployments
- **Language Servers** - Automatically downloaded on first use
- **Visual Studio Code** - For IDE integration

### Quick Start

Get up and running in under 5 minutes:

#### Step 1: Clone the Repository

```bash
git clone https://github.com/example/murena.git
cd murena
```

#### Step 2: Set Up Virtual Environment

```bash
# Create virtual environment with uv
uv venv

# Activate the environment
# On macOS/Linux
source .venv/bin/activate

# On Windows
.venv\Scripts\activate
```

#### Step 3: Install Dependencies

```bash
# Install project dependencies
uv sync
```

#### Step 4: Verify Installation

```bash
# Run tests to verify everything works
uv run poe test

# Check version
uv run murena-mcp-server --version
```

#### Step 5: Start the Server

```bash
# Start the MCP server
uv run murena-mcp-server

# Or with custom configuration
uv run murena-mcp-server --config ~/.murena/murena_config.yml
```

**Congratulations!** You now have a working Murena MCP installation.

### Advanced Installation

For production deployments or custom configurations:

#### Custom Installation Paths

You can customize installation paths through environment variables:

```bash
# Set custom paths
export MURENA_HOME="$HOME/.murena"
export MURENA_CONFIG="$MURENA_HOME/murena_config.yml"
export MURENA_CACHE="$MURENA_HOME/cache"

# Install with custom paths
uv sync --python-platform linux
```

#### Development Installation

For contributors and developers:

```bash
# Clone with development tools
git clone --recurse-submodules https://github.com/example/murena.git
cd murena

# Install with dev dependencies
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install
```

#### Docker Installation

Run Murena MCP in a Docker container:

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install uv && uv sync

CMD ["uv", "run", "murena-mcp-server"]
```

Build and run:

```bash
docker build -t murena-mcp .
docker run -p 8080:8080 -v ~/.murena:/root/.murena murena-mcp
```

#### Language Server Configuration

Configure specific language servers:

```yaml
# ~/.murena/murena_config.yml
language_servers:
  python:
    command: "pyright-langserver"
    args: ["--stdio"]
  typescript:
    command: "typescript-language-server"
    args: ["--stdio"]
  markdown:
    command: "marksman"
    args: ["server"]
```

## API Reference

Complete API documentation for all public interfaces.

### Core API

The core API provides essential functionality for symbolic operations.

#### get_symbols_overview

Retrieves hierarchical structure of symbols in a file.

**Signature:**
```python
def get_symbols_overview(
    relative_path: str,
    depth: int = 0,
    max_answer_chars: int = -1
) -> dict
```

**Parameters:**
- `relative_path` (str): Path to the file relative to project root
- `depth` (int): How deep to traverse the symbol hierarchy (0 = top-level only)
- `max_answer_chars` (int): Maximum characters in response (-1 = use default)

**Returns:**
- Dictionary with symbols grouped by kind (Class, Function, Method, etc.)

**Example:**
```python
overview = get_symbols_overview(
    relative_path="src/murena/agent.py",
    depth=2
)
print(overview["Class"])  # List all classes with methods
```

**Token Efficiency:**
- Traditional Read: ~15,000 tokens for 500-line file
- Symbolic Overview: ~800 tokens
- **Savings: 95%**

#### find_symbol

Finds symbols matching a name pattern.

**Signature:**
```python
def find_symbol(
    name_path_pattern: str,
    relative_path: str = "",
    include_body: bool = False,
    depth: int = 0,
    substring_matching: bool = False
) -> list[dict]
```

**Parameters:**
- `name_path_pattern` (str): Pattern to match (e.g., "MyClass/my_method")
- `relative_path` (str): Restrict search to this file/directory
- `include_body` (bool): Include symbol source code
- `depth` (int): Retrieve children up to this depth
- `substring_matching` (bool): Enable partial name matching

**Returns:**
- List of matching symbols with metadata and optional body

**Example:**
```python
# Find a specific method
symbols = find_symbol(
    name_path_pattern="MurenaTool/execute",
    relative_path="src/murena/tools/tools_base.py",
    include_body=True
)

# Find all methods starting with "get"
symbols = find_symbol(
    name_path_pattern="get",
    substring_matching=True,
    relative_path="src/"
)
```

**Token Efficiency:**
- Reading full file then searching: ~15,000 tokens
- Direct symbol find: ~500-1500 tokens
- **Savings: 90%**

#### find_referencing_symbols

Finds all references to a symbol.

**Signature:**
```python
def find_referencing_symbols(
    name_path: str,
    relative_path: str,
    context_mode: str = "full",
    include_info: bool = False
) -> list[dict]
```

**Parameters:**
- `name_path` (str): Symbol name path to find references for
- `relative_path` (str): File containing the symbol
- `context_mode` (str): "none", "line_only", or "full" (3-line context)
- `include_info` (bool): Include hover/signature info

**Returns:**
- List of references with metadata and code context

**Example:**
```python
refs = find_referencing_symbols(
    name_path="MurenaTool",
    relative_path="src/murena/tools/tools_base.py",
    context_mode="line_only"
)
```

**Context Mode Token Impact:**
- "none": ~50 tokens per reference
- "line_only": ~75 tokens per reference
- "full": ~150 tokens per reference

### Advanced API

Advanced operations for complex use cases.

#### replace_symbol_body

Replaces the body of a symbol.

**Signature:**
```python
def replace_symbol_body(
    name_path: str,
    relative_path: str,
    body: str
) -> str
```

**Parameters:**
- `name_path` (str): Symbol to replace
- `relative_path` (str): File containing the symbol
- `body` (str): New symbol body (including signature)

**Returns:**
- "OK" on success

**Example:**
```python
replace_symbol_body(
    name_path="MyClass/my_method",
    relative_path="src/module.py",
    body='''def my_method(self, arg: str) -> None:
        """Updated implementation."""
        print(f"Processing: {arg}")'''
)
```

**Best Practices:**
- Include complete method signature
- Preserve proper indentation
- Don't include decorators or docstrings above the method

#### insert_after_symbol

Inserts content after a symbol.

**Signature:**
```python
def insert_after_symbol(
    name_path: str,
    relative_path: str,
    body: str
) -> str
```

**Parameters:**
- `name_path` (str): Symbol to insert after
- `relative_path` (str): File containing the symbol
- `body` (str): Content to insert

**Returns:**
- "OK" on success

**Example:**
```python
# Add a new method to a class
insert_after_symbol(
    name_path="MyClass/existing_method",
    relative_path="src/module.py",
    body='''
    def new_method(self) -> None:
        """A new method."""
        pass
'''
)
```

#### rename_symbol

Renames a symbol throughout the codebase.

**Signature:**
```python
def rename_symbol(
    name_path: str,
    relative_path: str,
    new_name: str
) -> str
```

**Parameters:**
- `name_path` (str): Symbol to rename
- `relative_path` (str): File containing the symbol
- `new_name` (str): New name for the symbol

**Returns:**
- Result summary

**Example:**
```python
rename_symbol(
    name_path="UserService/getUserData",
    relative_path="src/services/user_service.py",
    new_name="fetch_user_data"
)
# Updates all references across the entire codebase
```

### Authentication API

API endpoints related to authentication and authorization.

This section would contain authentication-specific APIs in a real project.
For this test file, we'll keep it brief as a placeholder.

## Configuration

Configuration options for Murena MCP.

### Configuration File Location

Murena looks for configuration in the following order:

1. Project-specific: `.murena/project.yml`
2. User-level: `~/.murena/murena_config.yml`
3. System-level: `/etc/murena/config.yml`

### Basic Configuration

Minimal configuration example:

```yaml
# ~/.murena/murena_config.yml
contexts:
  default: agent

modes:
  default: interactive

language_servers:
  python: {}
  typescript: {}
  markdown: {}
```

### Advanced Configuration

Full configuration with all options:

```yaml
# Project name
project_name: "my-project"

# Active context
contexts:
  default: agent
  available:
    - agent
    - desktop-app
    - ide-assistant

# Operational modes
modes:
  default: interactive
  available:
    - interactive
    - planning
    - editing
    - one-shot

# Language server settings
language_servers:
  python:
    enabled: true
    command: "pyright-langserver"
    args: ["--stdio"]
    ls_specific_settings:
      python.analysis.typeCheckingMode: "strict"

  typescript:
    enabled: true
    command: "typescript-language-server"
    args: ["--stdio"]

  markdown:
    enabled: true
    command: "marksman"
    args: ["server"]

# Memory settings
memory:
  enabled: true
  location: ".murena/memories"
  max_memories: 100

# Cache settings
cache:
  enabled: true
  ttl_seconds: 86400
  location: "~/.murena/cache"
```

### Environment Variables

Override configuration with environment variables:

```bash
export MURENA_HOME="$HOME/.murena"
export MURENA_CONFIG="$MURENA_HOME/murena_config.yml"
export MURENA_CACHE_DIR="$MURENA_HOME/cache"
export MURENA_LOG_LEVEL="DEBUG"
```

## Troubleshooting

Common issues and solutions.

### Language Server Not Starting

**Symptom:** Language server fails to initialize

**Possible Causes:**
1. Language server binary not found
2. Incorrect configuration
3. Missing dependencies

**Solutions:**

```bash
# Check language server installation
which marksman
which pyright-langserver

# Reinstall language servers
uv run murena-mcp-server --reinstall-ls

# Check logs
tail -f ~/.murena/logs/murena.log
```

### High Memory Usage

**Symptom:** Process consuming excessive memory

**Solutions:**

1. **Clear cache:**
   ```bash
   rm -rf ~/.murena/cache/*
   ```

2. **Reduce cache TTL:**
   ```yaml
   cache:
     ttl_seconds: 3600  # 1 hour instead of 24
   ```

3. **Limit concurrent language servers:**
   ```yaml
   language_servers:
     max_concurrent: 3
   ```

### Slow Symbol Lookup

**Symptom:** Symbolic operations taking too long

**Solutions:**

1. **Index the project:**
   ```bash
   uv run index-project
   ```

2. **Use caching:**
   ```python
   # Enable session cache
   get_symbols_overview(..., use_cache=True)
   ```

3. **Restrict search scope:**
   ```python
   # Narrow search to specific directory
   find_symbol(
       name_path_pattern="MyClass",
       relative_path="src/services/"  # Don't search everything
   )
   ```

## Contributing

Guidelines for contributing to the project.

### Development Setup

See [Advanced Installation](#advanced-installation) for development setup.

### Code Style

We use strict formatting tools:

```bash
# Format code
uv run poe format

# Type check
uv run poe type-check

# Run linter
uv run poe lint
```

### Testing

Always include tests for new features:

```bash
# Run all tests
uv run poe test

# Run specific markers
uv run poe test -m markdown

# Run with coverage
uv run poe test --cov
```

### Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run formatters and tests
6. Submit pull request

---

**End of Documentation**

This file contains approximately 650 lines, making it suitable for testing
token efficiency of symbolic operations versus full-file reads.
