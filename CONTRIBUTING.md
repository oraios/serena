# Contributing to Serena

Thank you for your interest in contributing to Serena!

## Scope of Contributions

The following types of contributions can be submitted directly via pull requests:
  * isolated additions which do not change the behaviour of Serena and only extend it along existing lines (e.g., adding support for a new language server)
  * small bug fixes
  * documentation improvements

For other changes, please open an issue first to discuss your ideas with the maintainers.

When submitting a PR, ensure a well-defined scope.
Every PR should cover a single logical change or a set of closely related changes.

### Adding Support for a New Language Server

See the corresponding [memory](.serena/memories/adding_new_language_support_guide.md).

## Submitting Pull Requests

Before submitting a PR, be sure to document your relevant changes (i.e. new features, fixes) in `CHANGELOG.md`.
Use a concise style and add your change to the appropriate section
("Language Servers", "Tools", "JetBrains", "CLI", "Memories", "Dashboard", "Hooks", "General").

## Python Environment Setup

You can install a virtual environment with the required as follows

1. Create a new virtual environment: `uv venv -p 3.13`
2. Activate the environment:
    * On Linux/Unix/macOS or Windows with Git Bash: `source .venv/bin/activate`
    * On Windows outside of Git Bash: `.venv\Scripts\activate.bat` (in cmd/ps) or `source .venv/Scripts/activate` (in git-bash) 
3. Install the required packages with all extras: `uv sync --extra dev`

## Local Installation as Tool

To install Serena as a local tool, run

```shell
uv tool install --reinstall -p 3.13 .
```

## Poe Tasks

We use poe to execute development tasks:

- `poe format` - run code auto-formatters
- `poe type-check` - run type checkers

## Testing Tool Executions

The Serena tools (and in fact all Serena code) can be executed without an LLM, and also without
any MCP specifics (though you can use the mcp inspector, if you want).

An example script for running tools is provided in [scripts/demo_run_tools.py](scripts/demo_run_tools.py).

## Live-Testing the Grok Integration

The unit tests cover client setup and hooks with mocked CLI interactions. To additionally verify the
Grok integration against a *real* `grok` CLI installation, run

```shell
uv run python scripts/live_test_grok.py
```

The script validates client setup (`serena setup grok`), the native hook protocol
(`serena-hooks --client=grok`) and an MCP handshake with the `grok` context — without ever starting a
model session, so it incurs no inference cost. It backs up `~/.grok/config.toml` before the first
change, pairs every registration with a removal, restores the baseline at the end (also on abort), and
refuses to run if a `serena` MCP server is already registered in Grok. Per-check evidence files and a
Markdown report are written to a work directory printed at startup.

Useful options: `--hooks-only` runs only the pure-local checks (never touching the Grok configuration),
`--skip-unit` skips the pytest smoke run, and `--help` lists all options (including overrides for the
`grok`/`serena` executables and the Grok config path).
