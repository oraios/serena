# Fix Expert deadlock for monorepo Elixir projects

**Date:** 2026-05-03
**Status:** Draft
**PR target:** upstream oraios/serena

## Problem

`ElixirTools._start_server()` sends a `textDocument/didOpen` notification for `mix.exs` to trigger Expert's build pipeline (added in PR #1405). It constructs the path as `os.path.join(self.repository_root_path, "mix.exs")` and silently skips the didOpen when the file doesn't exist.

In monorepo layouts where the Elixir project lives in a subdirectory (e.g. `myproject/server/mix.exs`), `mix.exs` is not at the repository root. The didOpen is skipped, Expert never starts compiling, and Serena blocks for 300 seconds on the readiness timeout before failing.

## Solution

Add a `_find_mix_exs()` method to `ElixirTools` that searches for `mix.exs` at the repository root first, then in immediate subdirectories.

### `_find_mix_exs(self) -> str | None`

1. Check `{repository_root_path}/mix.exs` — if it exists, return it immediately (fast path, preserves current behavior for standard projects).
2. Scan `os.listdir(repository_root_path)` for immediate subdirectories. For each, check if `{subdir}/mix.exs` exists. Return the first match.
3. If nothing found, return `None`.
4. Log at info level when `mix.exs` is found in a subdirectory (aids debugging without being noisy).

### Changes to `_start_server()`

Replace:
```python
mix_exs_path = os.path.join(self.repository_root_path, "mix.exs")
mix_exs_uri = pathlib.Path(mix_exs_path).as_uri() if os.path.exists(mix_exs_path) else None
```

With:
```python
mix_exs_path = self._find_mix_exs()
mix_exs_uri = pathlib.Path(mix_exs_path).as_uri() if mix_exs_path is not None else None
```

The rest of `_start_server()` is unchanged — it already guards on `mix_exs_uri is not None`.

## Files changed

| File | Change |
|------|--------|
| `src/solidlsp/language_servers/elixir_tools/elixir_tools.py` | Add `_find_mix_exs()`, update `_start_server()` |
| `test/solidlsp/elixir/test_elixir_startup.py` | Add monorepo test cases |

## Test cases

Added to existing `TestElixirToolsStartup` class using the same `_make_elixir_tools` / `_make_mock_server` helpers:

1. **`test_finds_mix_exs_in_subdirectory`** — Create `server/mix.exs` (no root `mix.exs`). Verify didOpen is sent with URI ending in `server/mix.exs`.
2. **`test_prefers_root_mix_exs_over_subdirectory`** — Create both `mix.exs` and `server/mix.exs`. Verify didOpen uses root `mix.exs` URI (not the subdirectory one).
3. **`test_no_didopen_when_no_mix_exs_anywhere`** — Empty tmp_path with no `mix.exs` at root or subdirs. Verify no crash and didOpen not called.

## Out of scope

- No changes to project config, `project.yml`, or LS-specific settings
- No recursive or deep search — one level of subdirectories only
- No refactoring of the C# `breadth_first_file_scan` utility
- No changes to LSP initialize params (`rootUri` stays as `repository_root_path`)
