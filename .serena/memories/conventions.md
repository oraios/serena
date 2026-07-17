# Conventions

## Style (project-instructed)
- Idiomatic, object-oriented design. Non-trivial interfaces use **explicitly typed abstractions** (strategy pattern etc.) rather than bare functions/callbacks.
- Avoid low-level data structures where an OO abstraction fits. For simple data containers use **dataclasses**, not dicts/tuples.
- Structure function bodies into **functional blocks separated by blank lines**, each prefixed with a short elliptical phrase (lowercase, no leading capital) describing the block's purpose.
- **Docstrings: reStructuredText.** Param/return/raises use `:param x:`, `:return:`, `:raises X:`.
- Parameter / method / class descriptions begin with a precise elliptical phrase defining *what* the thing is; details in subsequent sentences.

## Formatting / lint (ruff)
- Line length 140, double quotes, target `py311`.
- Many "annoying" rules are disabled — see `[tool.ruff.lint] ignore` in `pyproject.toml` before adding workarounds (e.g. `Optional[T]` is preferred over `T | None`, `Union` is allowed, relative imports forbidden, `% string formatting` allowed).
- `ruff format` runs on `src scripts test`; same set for `ruff check`.
- mccabe complexity cap: 20.

## Typing (ty)
- Type checker is **ty** (Astral), configured under `[tool.ty]` in `pyproject.toml`.
  
## Tests
- Language-server tests are pytest-marker-gated (one marker per language; see `pyproject.toml` `[tool.pytest.ini_options].markers`). Default `poe test` runs unmarked tests + whatever `PYTEST_MARKERS` selects.
- Snapshot tests use **syrupy** with custom `--snapshot-patch-pycharm-diff` plugin (auto-added via `addopts`).

## Tool descriptions (LLM-facing)
- To change how a tool is described to the model, edit the Tool class's `apply()` **docstring** (in
  `src/serena/tools/*.py`) — `make_mcp_tool` parses the docstring body + `:param:` lines into the MCP tool
  description/schema. Do NOT use `tool_description_overrides` in context ymls (e.g. `claude-code.yml`); the
  docstring is the single source of truth and overrides drift. Keep `:param:` lines accurate.

## Memories
- Follow `mem:memory_maintenance` for any new/updated memory in `.serena/memories/`.
- Durable knowledge goes in memories/docs (not the assistant's auto-memory); see the monorepo top-level
  `CLAUDE.md` for the cross-repo conventions (no benchmark-tuning of agent-facing strings, etc.).
