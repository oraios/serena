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

## Typing (mypy strict)
- `disallow_untyped_defs = true`, `disallow_incomplete_defs = true`, `strict_equality`, `strict_optional`, `warn_unreachable`, `no_implicit_optional`.
- Excluded paths: `^build/`, `^docs/`, `^test/resources/`.
- Test files relax `disallow_untyped_defs` (still type-checked otherwise).

## Tests
- Language-server tests are pytest-marker-gated (one marker per language; see `pyproject.toml` `[tool.pytest.ini_options].markers`). Default `poe test` runs unmarked tests + whatever `PYTEST_MARKERS` selects.
- Snapshot tests use **syrupy** with custom `--snapshot-patch-pycharm-diff` plugin (auto-added via `addopts`).

## Memories
- Follow `mem:memory_maintenance` for any new/updated memory in `.serena/memories/`.
