# Suggested Commands

Run via `uv run poe <task>` (or `poe <task>` inside the activated venv). Poe executor is `simple`, so plain `poe` works without uv re-resolving.

## Dev loop
- `poe test` — pytest on `test/` (per-language tests are marker-gated; pass `-m <marker>` to enable).
- `poe lint` — ruff format-check + ruff check (no fixes).
- `poe format` — ruff `--fix` then `ruff format` (mutates files).
- `poe type-check` — ty on `src/serena`, `src/solidlsp`, and `test/` (test pass relaxes pytest/mock-noisy rules via `[[tool.ty.overrides]]`).
- Single test file: `uv run pytest test/path/to/test_x.py -vv`. Language-gated: add `-m python` etc.

## Docs
- `poe doc-build` — clean + autogen + sphinx (uses `rm -rf`; needs a unix-like shell, e.g. Git Bash on Windows).

## Entrypoints
- `uv run serena ...` — main CLI (`serena.cli:top_level`).
- `uv run serena-hooks ...` — hook helpers.
- `python scripts/gen_prompt_factory.py` — regenerate `src/serena/generated/generated_prompt_factory.py` after editing prompt templates.

## Windows shell notes (PowerShell 7+ is the project shell)
- Use `Remove-Item -Recurse -Force <path>` instead of `rm -rf` (the `doc-clean` poe task uses unix `rm -rf` and requires bash).
- Env vars: `$env:NAME = 'value'` (not `export`).
- Path separator in `pyproject.toml` poe tasks uses forward slashes; PowerShell accepts them in arguments.
- `git`, `uv`, `poe`, `pytest` behave identically to unix.
