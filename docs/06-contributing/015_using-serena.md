# Serena for Serena

The tightest loop for working on Serena is Serena itself: point your coding agent at your
development checkout, and every change you make is immediately the server you are using.
The first time you fix a tool, restart, and feel the fix under your own hands, the loop
makes sense for good. This
page covers the two skills that make that loop work — choosing which Serena you run (and how
to run a specific branch when the work calls for it), and letting the diagnostics tools tell
you what an edit did.

## Which Serena you run

For everyday use — including while working on Serena — run current `main`. It is where every
fix lands first, and using it daily is the cheapest way to notice a regression before a
release does. From a checkout tracking `main`, the persistent install `CONTRIBUTING.md`
describes keeps it fresh:

```bash
git pull && uv tool install --reinstall -p 3.13 .
```

Your MCP clients launch `serena` by name and always get an up-to-date main.

## Running the server from a specific branch

Two situations call for a branch instead: testing a change you are making, and trying a
branch someone else has proposed. In both, leave the main install alone.

### Your own checkout

Scope the branch to a separate client entry:

```json
{
  "mcpServers": {
    "serena-dev": {
      "command": "uv",
      "args": ["run", "--directory", "/abs/path/to/your/serena", "serena", "start-mcp-server"]
    }
  }
}
```

`uv run` rebuilds the package from the tree on launch, so what runs is exactly the code that
is checked out — switch branches, restart the server, and you are testing the other branch.
No install step in between.

### A remote branch, without cloning

To try a pull request you are reviewing, `uvx` can run it straight from git:

```bash
uvx --from git+https://github.com/<owner>/serena@<branch> serena start-mcp-server
```

This path ignores the lockfile, which is exactly why the project pins its dependencies to
exact versions — the git install resolves to the same environment anyway.

### Why not `uv tool install .` from the branch

The persistent install holds a single slot per tool name, so installing a branch that way
replaces your main-based Serena for every client that launches it by name — and it stays
replaced after you have moved on. The `--directory` form keeps the branch scoped to the one
client entry that asked for it.

### Restart semantics

Configuration is read at startup, so config changes need a server restart; a language can be
added to a running instance from the dashboard. The [FAQ](040_faq) covers the details.

## Letting diagnostics do the checking

Serena's language servers already know what is wrong with a file. The diagnostics tools
expose that, and for the inner loop they are much cheaper than a build or a test run.

### Ask for a file's diagnostics

`get_diagnostics_for_file` returns a file's diagnostics grouped by severity and by the
symbol they belong to, with a `min_severity` filter (error, warning, information, hint) —
raise the threshold and hint-level noise disappears. Reach for it after a series of edits,
before spending minutes on `poe test`.

### The editing tools report their own damage

Every editing tool checks the diagnostics delta of its edit and reports newly introduced
warning-or-higher findings in its result — not the file's pre-existing noise, only what the
edit itself caused. An agent using Serena sees the consequence of each change at the moment
it makes it, which is the difference between fixing one mistake and discovering twelve at
build time. The machinery is `EditingToolWithDiagnostics` in
[serena.tools.tools_base](code-reference/tools/tools_base).

### See both in five minutes

`scripts/demo_diagnostics.py` creates a temporary file in this repository, introduces a
warning, shows file- and symbol-level diagnostics, then makes a second flawed edit and
demonstrates that only the new warning is reported.
