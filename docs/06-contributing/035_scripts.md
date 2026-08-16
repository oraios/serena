# Scripts

Everything in `scripts/` runs the same way, from the repository root:

```bash
uv run python scripts/<name>.py
```

This page is the map — what each one does, and when you will be glad it exists.

## Demos: see a tool run, no agent attached

A tool is an ordinary Python object; these scripts execute tools directly against real
repositories — no MCP client, no LLM — which makes them the fastest way to see behaviour and
the natural starting point for tool work.

| script | what it shows |
|:--|:--|
| `demo_run_tools.py` | Serena's tools executed against this repository itself — the tour, and where `CONTRIBUTING.md` points first |
| `demo_diagnostics.py` | file- and symbol-level diagnostics, and an edit reporting only the warnings it introduced — [the loop explained](015_using-serena) |
| `demo_find_defining_symbol.py` | both defining-symbol tools, on the Python test repo |
| `demo_find_implementing_symbol.py` | the implementations tool, on the Go test repo |
| `demo_progressive_tool_shortening.py` | how tool results shorten as `max_answer_chars` tightens, on both the LSP and JetBrains backends |
| `demo_cli_call.py` | the CLI entry point invoked programmatically |
| `mcp_server.py` | the MCP server started programmatically — three lines, and a convenient place to hang a debugger |

## Generators: outputs, not sources

Four scripts regenerate files that are never edited by hand; *when* each one must run is
covered in [Getting Started](010_getting-started).

| script | regenerates |
|:--|:--|
| `gen_prompt_factory.py` | `src/serena/generated/generated_prompt_factory.py`, from the prompt templates |
| `print_language_list.py` | the commented language list pasted into `src/serena/resources/project.template.yml` |
| `update_downloaded_dependency_hashes.py` | the checksum database in `src/solidlsp/resources/downloaded_dependency_hashes.json`, after a server version bump |
| `build_news_json.py` | `news/news.json`, from the `news/*.html` items |

## Introspection and profiling

| script | the question it answers |
|:--|:--|
| `print_tool_overview.py` | which tools exist, with their descriptions |
| `print_mode_context_options.py` | which modes and contexts are registered, with an overview of each |
| `profile_tool_call.py` | where the time goes in a symbol lookup (cProfile / pyinstrument) |
| `memory_graph.py` | how a project's memories reference each other — emits GraphML, `-o` to name the output (default `memory_graph.graphml`) |

## Release machinery

`bump_version.py` (`--patch` or `--minor`) bumps the version and creates the git tag;
pushing that tag starts the release workflow. The process around it lives in
[`README-dev.md`](https://github.com/oraios/serena/blob/main/README-dev.md). Contributors
never need to run these.

## The odd ones out

- `agno_agent.py` — the Agno-based agent that the
  [custom agent guide](../03-special-guides/custom_agent) builds on: Serena as a toolkit
  inside another framework, no MCP involved.
- `live_test_grok.py` — a live smoke test against a real `grok` CLI, the un-mocked
  counterpart of the mocked client-setup tests. It needs the real binary and is not part of
  `poe test`.
