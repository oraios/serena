# Serena Coding Conventions

## General Rules
- **Language**: English for code, comments, and documentation.
- **Type Hints**: Strict typing is enforced via Mypy.
- **Formatting**: Black and Ruff are used for consistent styling.

## Code Style
- **Line Length**: 140 characters (configured in `pyproject.toml`).
- **Imports**: Alphabetical order, managed by Ruff/Isort.
- **Docstrings**: Follow Google/NumPy style (parsed via `docstring_parser`).

## Architecture Patterns
- **Symbol-based editing**: Prioritize symbolic operations over raw string replacements.
- **Async operation**: Handle non-blocking interactions where appropriate.
- **Inheritance**: New tools must inherit from `Tool` base class in `src/serena/tools/tools_base.py`.
- **Language Support**: Language-specific logic resides in `src/solidlsp/language_servers/`.

## Verification Gate
- Every task must be verified with `format`, `type-check`, and `test` before completion.
