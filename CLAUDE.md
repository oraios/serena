# Serena Development Conventions

## Build & Setup
- Python 3.11 required (>=3.11, <3.12)
- Uses `uv` for package management
- Install with extras: `uv pip install --all-extras -r pyproject.toml -e .`

## Testing
- Run all tests: `poe test`
- Run single test: `pytest test/path/to/test_file.py::test_function -v`
- Tests use pytest with coverage reporting

## Linting & Formatting
- Code formatting: `poe format` (runs ruff and black)
- Lint check: `poe lint` (runs black --check and ruff check)
- Type checking: `poe type-check` (runs mypy)

## Code Style
- Line length: 140 characters
- Quotes: Double quotes
- Type annotations required (disallow_untyped_defs = true)
- Imports: Organized by standard library, third-party, local
- Strong typing with TypeVar and generics
- Exception handling: Explicit except clauses preferred
- Docstrings: Required for public functions
- Class style: ABC for abstract classes, dataclasses where appropriate

## Project Structure
- Main code in `/src/serena`
- Tests in `/test`
- Documentation in `/docs`
- Config file: `serena_config.yml` and project-specific `myproject.yml`