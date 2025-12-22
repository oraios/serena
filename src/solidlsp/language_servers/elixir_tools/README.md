# Elixir Language Server Integration

This directory contains the integration for Elixir language support using [Expert](https://github.com/elixir-lang/expert), the official Elixir language server.

## Prerequisites

Before using the Elixir language server integration, you need to have:

1. **Elixir** installed and available in your PATH
   - Install from: https://elixir-lang.org/install.html
   - Verify with: `elixir --version`

2. **Expert** (optional - will be downloaded automatically if not found)
   - Expert binaries are automatically downloaded from GitHub releases
   - Manual installation: https://github.com/elixir-lang/expert#installation
   - If installed manually, ensure `expert` is in your PATH

## Features

The Elixir integration provides:

- **Language Server Protocol (LSP) support** via Next LS
- **File extension recognition** for `.ex` and `.exs` files
- **Project structure awareness** with proper handling of Elixir-specific directories:
  - `_build/` - Compiled artifacts (ignored)
  - `deps/` - Dependencies (ignored)
  - `.elixir_ls/` - ElixirLS artifacts (ignored)
  - `cover/` - Coverage reports (ignored)
  - `lib/` - Source code (not ignored)
  - `test/` - Test files (not ignored)

## Configuration

The integration uses the default Expert configuration with:

- **MIX_ENV**: `dev`
- **MIX_TARGET**: `host`
- **Experimental completions**: Disabled by default
- **Credo extension**: Enabled by default

### Version Management (asdf)

Expert automatically respects project-specific Elixir versions when using asdf:
- If a `.tool-versions` file exists in the project root, Expert will use the specified Elixir version
- Expert is launched from the project directory, allowing it to pick up project configuration
- No additional configuration needed - just ensure asdf is installed and the project has a `.tool-versions` file

## Usage

The Elixir language server is automatically selected when working with Elixir projects. It will be used for:

- Code completion
- Go to definition
- Find references
- Document symbols
- Hover information
- Code formatting
- Diagnostics (via Credo integration)

### Important: Project Compilation

Expert requires your Elixir project to be **compiled** for optimal performance, especially for:
- Cross-file reference resolution
- Complete symbol information
- Accurate go-to-definition

**For production use**: Ensure your project is compiled with `mix compile` before using the language server.

**For testing**: The test suite automatically compiles the test repositories before running tests to ensure optimal Expert performance.

## Testing

Run the Elixir-specific tests with:

```bash
pytest test/solidlsp/elixir/ -m elixir
```

## Implementation Details

- **Main class**: `ElixirTools` in `elixir_tools.py`
- **Language identifier**: `"elixir"`
- **Command**: `expert --stdio`
- **Supported platforms**: Linux (x64, arm64), macOS (x64, arm64), Windows (x64, arm64)
- **Binary distribution**: Downloaded from [GitHub releases](https://github.com/elixir-lang/expert/releases)

The implementation follows the same patterns as other language servers in this project, inheriting from `SolidLanguageServer` and providing Elixir-specific configuration and behavior.
