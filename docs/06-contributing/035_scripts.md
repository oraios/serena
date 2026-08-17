# Scripts

Everything under `scripts/` runs the same way, from the repository root:

```bash
uv run python scripts/<name>.py
```

The sections below group them by audience: demos show tools running, dev tooling serves
people working on Serena itself, and release machinery is for maintainers. Two of them —
`mcp_server.py` and `agno_agent.py` — are entry points that configurations and guides
outside this repository launch by path.

This page is the map — what each one does, what its arguments mean, and when you will be
glad it exists. Every script also answers `--help` with its purpose and arguments, so the
fastest way to check any of them is to ask the script itself.

## Demos: see a tool run, no agent attached

A tool is an ordinary Python object; these scripts execute tools directly against real
repositories — no MCP client, no LLM — which makes them the fastest way to see behaviour and
the natural starting point for tool work. None of them take arguments: run one, read what it
prints, then open the script and change what it calls.

- **`demo_run_tools.py`** — the tour, and where `CONTRIBUTING.md` points first:
  Serena's tools executed against this repository itself, so the output describes the very
  code you have open.
- **`demo_diagnostics.py`** — file- and symbol-level diagnostics, then an edit that
  reports only the warnings it introduced — [the loop explained](015_using-serena).
- **`demo_find_defining_symbol.py`** — both defining-symbol tools on the Python test
  repository: start from a location, get the symbol that defines it.
- **`demo_find_implementing_symbol.py`** — the implementations tool on the Go test
  repository: start from an interface, get everything that implements it.
- **`demo_progressive_tool_shortening.py`** — how a tool result shortens stage by
  stage as `max_answer_chars` tightens, on both the LSP and JetBrains backends (the
  JetBrains half skips itself when no IDE is running).
- **`demo_cli_call.py`** — the `serena` CLI entry point called in-process instead of
  as a subprocess — a convenient place to hang a debugger on a CLI path.

`mcp_server.py` is the same idea for the server itself — covered with the other outside
entry points at the end of this page.

## Doctor and live probes: is this machine ready?

**`check_dev_env.py`** — run this one first. It checks the core environment (Python
version, uv, the project virtual environment, and version skew between an installed
`serena` executable and this checkout), then reports which per-language pytest markers this
machine's toolchains can actually run. The toolchain table mirrors the availability rules
the test suite itself applies, so "runnable here" means the suite will agree — and every
missing toolchain is listed with what would satisfy it.

| argument | effect |
|:--|:--|
| *(none)* | the full report: environment checks, then runnable and missing toolchains per language |
| `--markers` | print only the `pytest -m` expression selecting the runnable markers — paste it straight into a test run. When nothing is runnable it prints nothing and exits non-zero, because an empty `-m` expression is no filter at all and would run the whole suite |

**`live_test_client_setup.py`** — does `serena setup <client>` still work against the
real MCP client CLIs installed on this machine? For every client it knows (claude-code,
codebuddy, codex, grok) it runs the full registration lifecycle — register, verify the
registration landed, remove, verify nothing was left behind — refusing to touch a client
that already has a live serena registration, and restoring configuration byte-for-byte.

| argument | effect |
|:--|:--|
| `--client {claude-code, codebuddy, codex, grok}` | probe only this client |
| `--list` | only report which client CLIs are detected; probe nothing |
| `--record DIR` | additionally write a JSON snapshot of each probed client's observable behaviour into `DIR` — a dated record of how the client behaves today, for diffing across client releases |

**`live_test_grok.py`** — the deep single-client counterpart: a live, zero-inference
smoke test against a real `grok` CLI, the un-mocked sibling of the mocked client-setup
tests. Deliberately not part of `poe test`.

| argument | effect |
|:--|:--|
| `--hooks-only` | run only the pure-local checks; never touches the Grok configuration |
| `--skip-unit` | skip the pytest smoke phase |
| `--work-dir DIR` | where evidence and reports are written (default: a fresh private directory under the system tmp) |
| `--repo-root` / `--serena-bin` / `--serena-hooks-bin` / `--grok-bin` / `--grok-config` | override the discovery of each piece under test; the defaults resolve from this checkout and `PATH` |

## Generators: outputs, not sources

Four scripts regenerate files that are never edited by hand; *when* each one must run is
covered in [Getting Started](010_getting-started). Only `build_news_json.py` takes an
argument.

| script | regenerates |
|:--|:--|
| `gen_prompt_factory.py` | `src/serena/generated/generated_prompt_factory.py`, from the prompt templates |
| `print_language_list.py` | the commented language list pasted into `src/serena/resources/project.template.yml` |
| `update_downloaded_dependency_hashes.py` | the checksum database in `src/solidlsp/resources/downloaded_dependency_hashes.json`, after a server version bump |
| `build_news_json.py` | `news/news.json`, from the `news/*.html` items; `--deploy` additionally uploads it to the news web root (maintainer-only, needs `HADES_USER`) |

## Introspection and profiling

- **`print_tool_overview.py`** — the full tool registry: every tool's name and
  description exactly as clients see them. The quickest answer to "which tools exist?",
  no server required.
- **`print_mode_context_options.py`** — every registered mode and context — the values
  `--mode` and `--context` accept — with each one's description.
- **`profile_tool_call.py`** — where the time goes in one symbol lookup: starts a
  `SerenaAgent` on this repository, runs `FindSymbolTool` once, and writes profiler output
  (`tool_call.pstat` for cProfile, to view with snakeviz, or a pyinstrument report — the
  `profiler` variable inside the script switches between them).
- **`memory_graph.py`** — how a project's memories reference each other, as a GraphML
  file for any graph viewer. Takes the project name (or root path) as its one positional
  argument; `-o`/`--output` names the output file (default `memory_graph.graphml`).

## Release machinery

Contributors never need to run these; the release process around them lives in
[`README-dev.md`](https://github.com/oraios/serena/blob/main/README-dev.md).

**`bump_version.py`** bumps the version and creates the git tag; pushing that tag
starts the release workflow.

| argument | effect |
|:--|:--|
| `--major` / `--minor` / `--patch` | bump that component and reset the smaller ones to zero |
| `-v X.Y.Z` / `--version X.Y.Z` | set an explicit version instead of bumping |
| `--dry-run` | show what would change without writing any files |

## Entry points launched from outside

**`mcp_server.py`** starts the Serena MCP server programmatically — the same server that
`serena start-mcp-server` runs, in the form that configurations and guides outside this
repository launch by path. It is also the natural place to hang a debugger
on the server itself, and it accepts the server's full option set:

| argument | effect |
|:--|:--|
| `--project NAME_OR_PATH` | project to activate at startup |
| `--context NAME_OR_PATH` | context to run under: a built-in name or a path to a custom context YAML (default `desktop-app`) |
| `--mode NAME_OR_PATH` | modes replacing the configured defaults; repeatable ([modes explained](../02-usage/050_configuration)) |
| `--add-mode NAME_OR_PATH` | modes added on top of the configured ones; repeatable |
| `--language-backend {LSP, JetBrains}` | override the configured language backend |
| `--transport {stdio, sse, streamable-http}` | transport protocol (default `stdio`) |
| `--host` / `--port` | listen address and port for the network transports (defaults `127.0.0.1` / `8000`) |

**`agno_agent.py`** is the Agno-based agent that the
[custom agent guide](../03-special-guides/custom_agent) builds on: Serena as a plain
toolkit inside another agent framework, no MCP involved. It needs the optional `agno`
dependency group (`uv sync --extra agno`) and model credentials — by default it drives
Claude, so an Anthropic API key; the guide walks through both.