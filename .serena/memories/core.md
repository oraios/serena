# Serena — Project Core

Serena is an MCP-based "IDE for coding agents": semantic code retrieval/editing/refactoring tools driven by language servers.

## Source map

- `src/serena/` — agent, MCP server, tools, project/config layer
  - `agent.py`, `mcp.py`, `project_server.py`, `cli.py`, `hooks.py` — entrypoints/wiring
  - `tools/` — tool implementations (memory_tools, symbol_tools, file_tools, workflow_tools, query_project_tools, config_tools, cmd_tools, jetbrains_tools)
  - `tools/tools_base.py` — base classes for all tools
  - `config/` — `serena_config.py`, `context_mode.py`, `client_setup.py`
  - `resources/config/contexts/*.yml`, `resources/config/modes/*.yml` — context/mode definitions
  - `code_editor.py`, `symbol.py`, `ls_manager.py` — symbolic editing / LS lifecycle
  - `dashboard.py`, `gui_log_viewer.py` — web dashboard / log viewer
  - `prompt_factory.py` + `generated/generated_prompt_factory.py` — prompts (regenerate with `scripts/gen_prompt_factory.py`)
- `src/solidlsp/` — LSP client framework; per-language servers under `language_servers/`
- `src/interprompt/` — prompt template library (synced from external repo; see `.syncCommitId.*`)
- `test/serena/`, `test/solidlsp/<lang>/` — pytest suites; per-language tests gated by pytest markers
- `test/resources/repos/<lang>/` — fixture projects used by language-server tests
- `scripts/` — utilities (prompt regen, tool overview, profiling, agno agent)
- `docs/` — Jupyter Book sources; build via poe `doc-build`

## Project-wide invariants

- Package name (PyPI): `serena-agent`; import root: `serena`. Wheel includes `serena`, `interprompt`, `solidlsp`.
- Python: `>=3.11, <3.15`. Dependencies are exact-pinned in `pyproject.toml` (uvx installs from git, lockfile ignored — pin exactly).
- Entry points: `serena` → `serena.cli:top_level`; `serena-hooks` → `serena.hooks:hook_commands`.
- Per-project state lives under `<project>/.serena/` (config + `memories/` as `.md` files).
- See `mem:tech_stack`, `mem:suggested_commands`, `mem:conventions`, `mem:task_completion`.
