# Murena Core Concepts and Architecture

## High-Level Architecture

Murena is built around a dual-layer architecture:

1. **MurenaAgent** - The main orchestrator that manages projects, tools, and user interactions
2. **SolidLanguageServer** - A unified wrapper around Language Server Protocol (LSP) implementations

## Core Components

### 1. MurenaAgent (`src/murena/agent.py`)

The central coordinator that:
- Manages active projects and their configurations
- Coordinates between different tools and contexts
- Handles language server lifecycle
- Manages memory persistence
- Provides MCP (Model Context Protocol) server interface

Key responsibilities:
- **Project Management** - Activating, switching between projects
- **Tool Registry** - Loading and managing available tools based on context/mode
- **Language Server Integration** - Starting/stopping language servers per project
- **Memory Management** - Persistent storage of project knowledge
- **Task Execution** - Coordinating complex multi-step operations

### 2. SolidLanguageServer (`src/solidlsp/ls.py`)

A unified abstraction over multiple language servers that provides:
- **Language-agnostic interface** for symbol operations
- **Caching layer** for performance optimization
- **Error handling and recovery** for unreliable language servers
- **Uniform API** regardless of underlying LSP implementation

Core capabilities:
- Symbol discovery and navigation
- Code completion and hover information
- Find references and definitions
- Document and workspace symbol search
- File watching and change notifications

### 3. Tool System (`src/murena/tools/`)

Modular tool architecture with several categories:

#### File Tools (`file_tools.py`)
- File system operations (read, write, list directories)
- Text search and pattern matching
- Regex-based replacements

#### Symbol Tools (`symbol_tools.py`)  
- Language-aware symbol finding and navigation
- Symbol body replacement and insertion
- Reference finding across codebase

#### Memory Tools (`memory_tools.py`)
- Project knowledge persistence
- Memory retrieval and management
- Onboarding information storage

#### Configuration Tools (`config_tools.py`)
- Project activation and switching
- Mode and context management
- Tool inclusion/exclusion

### 4. Configuration System (`src/murena/config/`)

Multi-layered configuration supporting:
- **Contexts** - Define available tools and their behavior
- **Modes** - Specify operational patterns (interactive, editing, etc.)
- **Projects** - Per-project settings and language server configs
- **Tool Sets** - Grouped tool collections for different use cases

## Language Server Integration

### Language Support Model

Each supported language has:
1. **Language Server Implementation** (`src/solidlsp/language_servers/`)
2. **Runtime Dependencies** - Managed downloads of language servers
3. **Test Repository** (`test/resources/repos/<language>/`)
4. **Test Suite** (`test/solidlsp/<language>/`)

### Language Server Lifecycle

1. **Discovery** - Find language servers or download them automatically
2. **Initialization** - Start server process and perform LSP handshake
3. **Project Setup** - Open workspace and configure language-specific settings
4. **Operation** - Handle requests/responses with caching and error recovery
5. **Shutdown** - Clean shutdown of server processes

### Supported Languages

Current language support includes:
- **C#** - Microsoft.CodeAnalysis.LanguageServer (.NET 9)
- **Python** - Pyright or Jedi
- **TypeScript/JavaScript** - TypeScript Language Server
- **Rust** - rust-analyzer
- **Go** - gopls
- **Java** - Eclipse JDT Language Server
- **Kotlin** - Kotlin Language Server
- **PHP** - Intelephense
- **Ruby** - Solargraph
- **Clojure** - clojure-lsp
- **Elixir** - ElixirLS
- **Dart** - Dart Language Server
- **C/C++** - clangd
- **Terraform** - terraform-ls

## Memory and Knowledge Management

### Memory System
- **Markdown-based storage** in `.murena/memories/` directory
- **Contextual retrieval** - memories loaded based on relevance
- **Project-specific** knowledge persistence
- **Onboarding support** - guided setup for new projects

### Knowledge Categories
- **Project Structure** - Directory layouts, build systems
- **Architecture Patterns** - How the codebase is organized
- **Development Workflows** - Testing, building, deployment
- **Domain Knowledge** - Business logic and requirements

## MCP Server Interface

Murena exposes its functionality through Model Context Protocol:
- **Tool Discovery** - AI agents can enumerate available tools
- **Context-Aware Operations** - Tools behave based on active project/mode
- **Stateful Sessions** - Maintains project state across interactions
- **Error Handling** - Graceful degradation when tools fail

## Error Handling and Resilience

### Language Server Reliability
- **Timeout Management** - Configurable timeouts for LSP requests
- **Process Recovery** - Automatic restart of crashed language servers
- **Fallback Behavior** - Graceful degradation when LSP unavailable
- **Caching Strategy** - Reduces impact of server failures

### Project Activation Safety
- **Validation** - Verify project structure before activation
- **Error Isolation** - Project failures don't affect other projects
- **Recovery Mechanisms** - Automatic cleanup and retry logic

## Performance Considerations

### Caching Strategy
- **Symbol Cache** - In-memory caching of expensive symbol operations
- **File System Cache** - Reduced disk I/O for repeated operations
- **Language Server Cache** - Persistent cache across sessions

### Resource Management
- **Language Server Pooling** - Reuse servers across projects when possible
- **Memory Management** - Automatic cleanup of unused resources
- **Background Operations** - Async operations don't block user interactions

## Extension Points

### Adding New Languages
1. Implement language server class in `src/solidlsp/language_servers/`
2. Add runtime dependencies configuration
3. Create test repository and test suite
4. Update language enumeration and configuration

### Adding New Tools
1. Inherit from `Tool` base class in `tools_base.py`
2. Implement required methods and parameter validation
3. Register tool in appropriate tool registry
4. Add to context/mode configurations as needed

### Custom Contexts and Modes
- Define new contexts in YAML configuration files
- Specify tool sets and operational patterns
- Configure for specific development workflows