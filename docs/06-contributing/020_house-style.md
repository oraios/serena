# House Style

Every codebase has opinions; Serena writes its down where its agents can read them — as
checked-in memories under
[`.serena/memories/`](https://github.com/oraios/serena/tree/main/.serena/memories). This page is
the human rendering of the load-bearing one,
[`critical_info.md`](https://github.com/oraios/serena/blob/main/.serena/memories/critical_info.md);
where the two disagree, the memory wins.

## Design

The style is idiomatic, object-oriented Python — Java-esque principles, Pythonic syntax:

- **Each concern has exactly one home.** A mechanism whose parts are only correct in combination
  is implemented as one class, and its parts are private to it. Helpers and constants used by a
  single abstraction live inside it, not beside it.
- **Invariants are enforced through structure and visibility.** An interface should not permit
  states the design forbids.
- **Non-trivial interfaces take explicitly typed abstractions, not bare functions** — the
  strategy pattern rather than a callback parameter.
- **Dataclasses over dictionaries and tuples** for anything that stores structured data.

## Testing

- Test **only externally observable behaviour**, never implementation structure. The litmus
  test: a behaviour-preserving refactoring must not break any test — a test that could break is
  wrong and must not be written.
- When functionality is removed, its tests are deleted. There are no tests asserting the
  *absence* of something: absence of an implementation detail is not a behaviour, and such tests
  only freeze the current implementation.
- Fewer, behaviour-anchored tests are preferred; a missing test is better than an
  implementation-coupled one.
- Language-server tests are marker-gated per language, and snapshot tests use
  [syrupy](https://github.com/syrupy-project/syrupy) — see
  [Getting Started](010_getting-started) for how tests are selected and skipped.

## Docstrings and comments

- reStructuredText, consistently — `:param x:`, `:return:`.
- **A tool's docstring is its prompt.** For every `Tool` subclass, what the docstring says is
  exactly what the LLM reads: editing one changes the agent's behaviour, not just the
  documentation. The machinery behind this is in
  [serena.tools.tools_base](code-reference/tools/tools_base).
- Function bodies are structured into functional blocks separated by blank lines, each headed by
  a concise, lower-case elliptical phrase describing what the block is for.
- Each piece of information appears exactly once, at the element that owns it: callers do not
  explain callees' internals, and callees do not describe their callers.

## Mechanics

The formatter and linter is ruff (line length 140, double quotes, docstring code formatting on);
the type checker is [`ty`](https://github.com/astral-sh/ty). None of this needs remembering:
`uv run poe format` and `uv run poe type-check` apply it, and [CI](010_getting-started) holds
the same line.

When in doubt, open a neighbouring file: the codebase is consistent enough to teach by
example, and review will nudge you the rest of the way.
