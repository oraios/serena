# Software Design

IMPORTANT: You use an idiomatic, object-oriented style (Java-esque principles, Pythonic syntax and constructs).

* You keep each concern in exactly one home.
  A mechanism whose parts are only correct in combination is implemented as a single component/class, and its parts are private to it;
  expose a minimal public surface. Java-like encapsulation: If helper functions and constants are only used by one abstraction,
  make them internal to the respective class.
* You enforce invariants through structure and visibility; interfaces should not permit states the design forbids.
* For any non-trivial interfaces, you use interfaces that expect explicitly typed abstractions
  rather than mere functions (i.e. use the strategy pattern, for example).
  You avoid the use of low-level data structures in all cases where an object-oriented abstraction would be more appropriate.
  For simple data storage, you use dataclasses instead of dictionaries or tuples.

# Testing

The key principle is to test *only* externally observable behavior and guarantees, never implementation structure.
* Litmus test: a behaviour-preserving refactoring must not break any test. A test that could break is wrong and must not be written.
* When functionality is removed, you delete its tests. You never add tests asserting the *absence* of something;
  absence of an implementation detail is not a behaviour, and such tests only freeze the current implementation and burden maintenance.
* Fewer, behaviour-anchored tests are preferred; a missing test is better than an implementation-coupled one.

Language-server tests are pytest-marker-gated (one marker per language; see `pyproject.toml` `[tool.pytest.ini_options].markers`). Default `poe test` runs unmarked tests + whatever `PYTEST_MARKERS` selects.
Snapshot tests use syrupy.

# Docstrings & Comments

Documentation style:

* You consistently use reStructuredText.
* You structure function implementations into functional blocks that are separated by blank lines.
  Atop each functional block, you write an elliptical phrase (starting with lower-case letter) that describes the purpose of the
  block in a concise manner.
* When describing parameters, methods/functions and classes, you use a precise style, where the initial (elliptical) phrase
  clearly defines *what* it is. Any details then follow in subsequent sentences.

General documentation principles:

* Each piece of information appears exactly once, at the element that owns it: callers do not
  explain callees' internals, and callees do not describe their callers.
* Code changes are documented exclusively in commit messages, not in comments.
* Things you consequently avoid:
    - For a function/class, you do not describe who calls/uses it. A call/usage site may explain why a usage occurs, but only if it is non-obvious.
    - When a function is called, you do not describe what it does. That belongs in the function's docstring.
    - You do not describe in comments how an implementation differs from a previous state of the code or why a change was made. That belongs in the commit message.

# REPL & facades

Read `mem:repl` before working on `serena.repl` (the code-execution paradigm and its facade APIs) or on tools
delegating to it: structure, exposure/naming principles, configuration of the API scope and the availability policy.

# Commits & pull requests

* Commit messages:
  * The subject line must cover the *entire* change; make it suitably abstract if necessary
  * Details are presented in concise bullet items, one point per item; no prose paragraphs.
    Where the change spans several topics, group the items by topic, each group with a short heading.
  * Wrap all lines at ~100 characters.
  * Write the message to a file and commit with `-F`; do not pass long text via `-m`.
* Read `mem:creating_pull_requests` when asked to participate in the creation of a pull request.

# Memories

- Follow `mem:memory_maintenance` for any new/updated memory in `.serena/memories/`.
- Durable project knowledge goes into memories or docs/

# Dev Tools

Read `mem:task_completion` for tools to call upon task completion.
