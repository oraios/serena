# Serena-TF

**Comprehensive Terraform Language Server MCP Server written in Go**

Serena-TF is a production-ready Golang port of Serena, specifically focused on Terraform infrastructure as code. It provides AI agents with powerful symbol-based navigation, editing capabilities, and project management through the Model Context Protocol (MCP).

## Features

### 🚀 Core Capabilities

- **Terraform Language Server Integration**
  - Auto-download and manage terraform-ls binaries (cross-platform)
  - Full LSP capabilities: symbols, definitions, references, hover, rename
  - Symbol caching for high performance
  - Terraform-aware path ignoring (.terraform/, *.tfstate)

- **Symbol-Based Operations**
  - Navigate resources, modules, variables, and outputs
  - Find symbols by name patterns (absolute/relative paths)
  - Get document symbol overviews
  - Find all references to symbols
  - Advanced filtering by symbol kind
  - **Edit symbols**: Replace body, insert before/after, rename across project
  - LSP-powered refactoring with workspace-wide changes

- **File Operations**
  - Read, create, list, and find files
  - Regex-based search and replace (DOTALL + MULTILINE)
  - Gitignore-aware file operations
  - Line-based editing operations

- **Memory System**
  - Persist project knowledge across sessions
  - Markdown-based storage in `.serena-tf/memories/`
  - Write, read, list, delete, and edit memories
  - Accumulate Terraform project insights over time

- **Context & Mode System**
  - **Contexts**: Environment-specific configurations (agent, ide-assistant, desktop-app)
  - **Modes**: Operational patterns (planning, editing, interactive, one-shot)
  - Tool inclusion/exclusion per context/mode
  - Customizable system prompts

- **Shell Command Execution**
  - Run Terraform CLI commands (plan, apply, validate, etc.)
  - Configurable working directory
  - Capture stdout/stderr

- **Workflow Tools**
  - Project onboarding with guided analysis
  - Initial instructions and manual
  - Onboarding status tracking

### 🎯 MCP Protocol

Full implementation of the Model Context Protocol:
- JSON-RPC over stdio
- Tool schema generation
- System prompt exposure
- Error handling and timeouts

## Installation

### Prerequisites

- Go 1.21 or later
- Terraform CLI installed and in PATH

### Build from Source

```bash
# Clone the repository
git clone https://github.com/TahirRiaz/serena-tf.git
cd serena-tf

# Build the binary
make build

# Or install directly
make install
```

The binary will be available as `serena-tf`.

## Usage

### Starting the MCP Server

```bash
# Basic usage (default project directory: current directory)
serena-tf

# Specify project directory
serena-tf --project /path/to/terraform/project

# Specify context and modes
serena-tf --context agent --modes interactive,editing

# Full configuration
serena-tf \
  --project /path/to/terraform/project \
  --context agent \
  --modes interactive,editing \
  --config-dir ~/.serena-tf
```

### Command Line Options

- `--project, -p`: Path to the Terraform project (default: `.`)
- `--context, -c`: Context name - agent, ide-assistant, or desktop-app (default: `agent`)
- `--modes, -m`: Comma-separated mode names - planning, editing, interactive, one-shot (default: `interactive`)
- `--config-dir, -d`: Configuration directory (default: `~/.serena-tf`)

### MCP Client Configuration

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "serena-tf": {
      "command": "serena-tf",
      "args": [
        "--project", "/path/to/your/terraform/project",
        "--context", "agent",
        "--modes", "interactive,editing"
      ]
    }
  }
}
```

## Available Tools

### File Tools (6 tools)

- **read_file**: Read files with line range support
- **create_text_file**: Create or overwrite files
- **list_dir**: List directory contents (recursive option)
- **find_file**: Find files by glob patterns
- **search_for_pattern**: Regex search across files with context
- **replace_regex**: Regex-based file editing

### Symbol Tools - Read Operations (3 tools)

- **get_symbols_overview**: Get top-level symbols in a file
- **find_symbol**: Advanced symbol search with name path patterns
- **find_referencing_symbols**: Find all references to a symbol

### Symbol Tools - Editing Operations (5 tools)

- **replace_symbol_body**: Replace entire symbol definition
- **insert_after_symbol**: Insert content after a symbol
- **insert_before_symbol**: Insert content before a symbol (e.g., add imports)
- **rename_symbol**: LSP-powered symbol renaming across project
- **restart_language_server**: Restart hung language server (optional)

### Line Editing Tools (3 tools - optional)

- **delete_lines**: Delete a range of lines
- **replace_lines**: Replace a range of lines with new content
- **insert_at_line**: Insert content at a specific line

### Memory Tools (5 tools)

- **write_memory**: Save project knowledge for future sessions
- **read_memory**: Retrieve saved knowledge
- **list_memories**: List all memories
- **delete_memory**: Remove a memory
- **edit_memory**: Edit memory with regex

### Workflow Tools (3 tools)

- **initial_instructions**: Get system prompt and manual
- **check_onboarding_performed**: Check if onboarding was done
- **onboarding**: Get instructions for project onboarding (optional)

### Config Tools (1 tool)

- **get_current_config**: Show current configuration and active project

### Command Tools (1 tool)

- **execute_shell_command**: Execute shell commands (terraform plan/apply/validate, etc.)

**Total: 27 comprehensive tools**

## Architecture

### Project Structure

```
serena-tf/
├── cmd/serena-tf/          # CLI entry point
├── pkg/
│   ├── lsp/                # LSP client and Terraform LS wrapper
│   ├── editor/             # Code editor with symbol-aware operations
│   ├── tools/              # Tool system and implementations (27 tools)
│   ├── mcp/                # MCP protocol server
│   ├── project/            # Project management
│   ├── memory/             # Memory system
│   ├── config/             # Context/mode system
│   ├── cache/              # Symbol caching
│   ├── agent/              # Main orchestrator
│   └── util/               # Utilities
├── configs/                # Built-in contexts and modes
├── testdata/terraform/     # Example Terraform project
└── docs/                   # Documentation
```

### Key Components

1. **LSP Client**: Generic JSON-RPC LSP client with full protocol support
2. **Terraform LS**: Wrapper with auto-download and lifecycle management
3. **Code Editor**: Symbol-aware editing with LSP refactoring support
4. **Symbol Cache**: MD5-based file caching for performance
5. **Tool Registry**: Plugin-style tool registration and discovery (27 tools)
6. **MCP Server**: Full MCP protocol implementation
7. **Agent**: Orchestrates all components and provides tool access

## Configuration

### Contexts

Contexts define the environment (agent, IDE, desktop app):

```yaml
# configs/contexts/agent.yml
description: All tools for agent context
prompt: |
  You are running in agent context...
excluded_tools: []
tool_description_overrides: {}
```

### Modes

Modes define operational patterns:

```yaml
# configs/modes/planning.yml
description: Read-only mode for analysis
prompt: |
  You are operating in planning mode...
excluded_tools:
  - create_text_file
  - replace_regex
  - execute_shell_command
```

### Project Configuration

Create `.serena-tf/project.yml` in your Terraform project:

```yaml
name: my-terraform-project
encoding: utf-8
excluded_tools:
  - execute_shell_command  # Optionally exclude specific tools
```

## Examples

### Example 1: Explore Infrastructure

```
User: "What resources are defined in main.tf?"

Agent uses: get_symbols_overview(relative_path="main.tf")

Returns: List of all resources, modules, variables, etc.
```

### Example 2: Find VPC Configuration

```
User: "Find all VPC-related resources"

Agent uses: find_symbol(
  name_path="aws_vpc",
  substring_matching=true
)

Returns: All VPC resources across the project
```

### Example 3: Store Knowledge

```
User: "Remember that we use us-west-2 for production"

Agent uses: write_memory(
  memory_file_name="deployment_regions",
  content="# Deployment Regions\n\nProduction: us-west-2\n..."
)

Future sessions can read this memory!
```

### Example 4: Run Terraform Commands

```
User: "Run terraform plan"

Agent uses: execute_shell_command(
  command="terraform plan",
  cwd="."
)

Returns: Terraform plan output
```

## Development

### Running Tests

```bash
# Run all tests
make test

# Run tests with coverage
make test-coverage

# Run specific package tests
go test ./pkg/lsp/...
```

### Building

```bash
# Build binary
make build

# Build and install
make install

# Clean build artifacts
make clean
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run tests and linting
6. Submit a pull request

## Terraform LS Auto-Download

Serena-TF automatically downloads the appropriate terraform-ls binary for your platform:

- **Platforms**: macOS (darwin), Linux, Windows
- **Architectures**: amd64, arm64
- **Version**: 0.33.3 (configurable)
- **Install Location**: `~/.serena-tf/ls_resources/TerraformLS/`

The download happens automatically on first run if terraform-ls is not found.

## Performance

### Symbol Caching

- Symbols are cached by file content hash (MD5)
- Cache stored in `.serena-tf/cache/terraform/`
- Thread-safe operations
- Automatic invalidation on file changes

### Optimization Tips

1. Use `find_symbol` with `relative_path` to restrict search scope
2. Memory system reduces redundant explanations
3. Symbol cache eliminates redundant LSP queries
4. Gitignore patterns reduce file scanning

## Troubleshooting

### Terraform CLI Not Found

Ensure `terraform` is installed and in your PATH:

```bash
terraform version
```

### Terraform LS Download Issues

If auto-download fails, manually download terraform-ls from:
https://releases.hashicorp.com/terraform-ls/

Place in: `~/.serena-tf/ls_resources/TerraformLS/terraform-ls`

### Symbol Cache Issues

Clear the cache:

```bash
rm -rf .serena-tf/cache/
```

### LSP Not Starting

Check logs for LSP stderr output. Ensure:
- Terraform files are valid
- Project root is correct
- No conflicting terraform-ls processes

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Inspired by [Serena](https://github.com/sensai-inc/serena) Python implementation
- Uses [terraform-ls](https://github.com/hashicorp/terraform-ls) for Terraform language support
- Implements [Model Context Protocol (MCP)](https://modelcontextprotocol.io)

## Support

- **Issues**: https://github.com/TahirRiaz/serena-tf/issues
- **Discussions**: https://github.com/TahirRiaz/serena-tf/discussions
- **Documentation**: https://github.com/TahirRiaz/serena-tf/tree/main/docs

## Roadmap

- [ ] Additional editing operations (insert, delete, rename symbols)
- [ ] Support for terraform fmt/validate integration
- [ ] Workspace-wide symbol search optimization
- [ ] Enhanced error recovery and diagnostics
- [ ] Plugin system for custom tools
- [ ] Web UI for configuration and monitoring

---

**Built with ❤️ for the Terraform community**
