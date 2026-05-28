# Task Completion Checklist

After any code change in `src/` or `test/`, run:

1. `uv run poe format` — applies ruff fixes + formatting (mutates files).
2. `uv run poe type-check` — mypy strict on `src/serena`, `src/solidlsp`, `test/`.
3. `uv run poe test` — pytest on affected files or affected languages, using `-m` markers.

If prompt templates changed: `uv run python scripts/gen_prompt_factory.py` (regenerates `src/serena/generated/generated_prompt_factory.py`; use `uv run poe format` and commit the result).

If memories were edited/renamed/split: run `uv run serena memories check` from the project root to find broken `mem:` references.
