# Tech Stack

- Language: Python 3.11–3.14 (`requires-python = ">=3.11, <3.15"`).
- Package/dep manager: **uv** (uv.lock present). Exact version pins in `pyproject.toml` because `uvx` installs from git and ignores the lockfile.
- Build backend: `hatchling`. Packages: `src/serena`, `src/interprompt`, `src/solidlsp`.
- Task runner: **poethepoet** (`poe <task>`). Poe executor is `simple` (does NOT shell out via uv) — avoids env recreation while MCP server is running.
- Key runtime deps: `mcp`, `flask` (dashboard), `pydantic`, `pygls` + `lsprotocol` (LSP), `anthropic`, `jinja2`, `ruamel.yaml`, `pywebview`/`pystray` (GUI), `pythonnet` (Windows only).
- Dev deps: `ruff` (lint+format), `ty` (Astral type checker; replaced mypy), `pytest` (+ `pytest-xdist`, `pytest-timeout`, `syrupy` snapshots), `sphinx`/`jupyter-book` for docs.
- Optional extras: `agno` (Agno agent integration), `google` (gemini).
- LSP client core lives under `src/solidlsp/`; one subdir per supported language server under `language_servers/`.
