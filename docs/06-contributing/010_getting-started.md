# Getting Started

Welcome — this page takes you from a fresh clone to a verified change. None of it assumes
prior context, and none of it takes long.

## The environment

Three commands, described in
[CONTRIBUTING.md](https://github.com/oraios/serena/blob/main/CONTRIBUTING.md): create a
virtualenv with `uv`, activate it, `uv sync --extra dev`.

That is the whole install — no services, no containers. Language servers are fetched on
demand when a test or a project needs them.

## The four commands

Every change runs through the same four [poe](https://github.com/nat-n/poethepoet) tasks,
defined in `pyproject.toml`:

| command | what it does |
|:--|:--|
| `uv run poe format` | rewrites: `ruff check --fix`, then `ruff format`, over `src`, `scripts` and `test` |
| `uv run poe lint` | the same two ruff passes, checking only — this is what CI runs |
| `uv run poe type-check` | [`ty`](https://github.com/astral-sh/ty) over the sources and the tests |
| `uv run poe test` | `pytest test -vv` — see the markers below before running it bare |

Format before pushing: the lint gate is the first thing CI executes, so one unformatted file
fails the whole matrix in its first minute.

## Tests

### Markers select the languages

Core tests are unmarked and always run. Every supported language has a pytest marker
(`python`, `go`, `java`, …), so `poe test -m "python or go"` selects accordingly. The full
list — with the language server each marker uses — is in `pyproject.toml` under
`[tool.pytest.ini_options]`.

Two markers are not languages: `snapshot` (snapshot tests for the symbolic editing
operations, via syrupy) and `slow`.

### Missing toolchains skip, never fail

A language whose server or toolchain is not installed locally is skipped, not failed — you
can work on Python without installing sixty compilers. That decision lives in exactly one
place, `test/conftest.py`, rather than per test file.

### Fixtures are real repositories

Language-server tests run against small, real projects under
`test/resources/repos/<language>/test_repo/`.

## What CI runs against a pull request

The test workflow batches the markers into five jobs — `jvm`, `native`, `other-langs`,
`niche`, and a `catch-all` for everything unmarked — across Linux, macOS and Windows.
`poe lint` and `poe type-check` run once per OS, in the catch-all batch. The docs build
(`poe doc-build`, Sphinx with warnings as errors) and a spell check run alongside.

The full walk through the matrix — the batches, the ceilings, the caching, and why the
suite deliberately does not use xdist — is [The CI Matrix](045_ci).

## Generated files: regenerate, never edit

Some files in the tree are outputs, and hand edits to them are undone by the next generation
run:

- `src/serena/generated/generated_prompt_factory.py` — after changing prompt templates,
  regenerate with `uv run python scripts/dev/gen_prompt_factory.py`, re-format, and commit the
  result.
- The commented language list in `src/serena/resources/project.template.yml` — regenerate with
  `uv run python scripts/dev/print_language_list.py`.
- `docs/01-about/000_intro.md`, `025_features.md` and `035_tools.md` — written by
  `docs/autogen_docs.py` during `poe doc-build`: the first two from the README, the tool list
  from the tool registry.
- The download-verification hashes in
  `src/solidlsp/resources/downloaded_dependency_hashes.json` — via
  `uv run python scripts/dev/update_downloaded_dependency_hashes.py` after a server version bump.

## Running tools without an LLM

A tool is an ordinary Python object and does not need an agent attached:
`scripts/demos/demo_run_tools.py` executes Serena's tools against this repository directly, and its
siblings do the same for narrower surfaces — the full map is in [Scripts](035_scripts).
This is the fastest loop for tool work: no MCP client, no model, no waiting.

## Your first change, end to end

Make the change, then let the tooling carry it home:

1. `uv run poe format` — the formatter fixes what it can and tells you the rest.
2. `uv run poe type-check` — fast, and worth trusting.
3. `uv run poe test -m <marker>` for the languages you touched, or bare `poe test` for core
   work.
4. One concise line in `CHANGELOG.md` under the matching section.
5. Open the pull request — the template asks for exactly two things, and you have just done
   both: the changelog entry, and a scope that fits `CONTRIBUTING.md`'s rules.

CI runs the same commands across Linux, macOS and Windows, so a green local loop is most of
the way there. And if the review takes a few days to arrive, that is [normal
here](040_faq) — important changes get unhurried attention, and quiet does not mean
forgotten.
