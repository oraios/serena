# Contributing to Serena

Thank you for your interest in contributing to Serena!

## Scope of Contributions

The following types of contributions can be submitted directly via pull requests:
  * isolated additions which do not change the behaviour of Serena and only extend it along existing lines (e.g., adding support for a new language server)
  * small bug fixes
  * documentation improvements

For other changes, please open an issue first to discuss your ideas with the maintainers.

### Adding Support for a New Language Server

See the corresponding [memory](.serena/memories/adding_new_language_support_guide.md).

## Python Environment Setup

You can install a virtual environment with the required as follows

1. Create a new virtual environment: `uv venv`
2. Activate the environment:
    * On Linux/Unix/macOS or Windows with Git Bash: `source .venv/bin/activate`
    * On Windows outside of Git Bash: `.venv\Scripts\activate.bat` (in cmd/ps) or `source .venv/Scripts/activate` (in git-bash) 
3. Install the required packages with all extras: `uv sync --extra dev`

## Poe Tasks

We use poe to execute development tasks:

- `poe format` - run code auto-formatters
- `poe type-check` - run type checkers

## Testing Tool Executions

The Serena tools (and in fact all Serena code) can be executed without an LLM, and also without
any MCP specifics (though you can use the mcp inspector, if you want).

An example script for running tools is provided in [scripts/demo_run_tools.py](scripts/demo_run_tools.py).