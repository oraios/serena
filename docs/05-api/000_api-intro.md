# API Reference

**If you want to *use* Serena** — connect it to your coding agent, configure languages, work with
projects — this is not the page you need. Start with [Getting Started](../02-usage/000_intro) and
come back only if you end up reading the source. Nothing here is required for using Serena.

This section is for reading and extending the code: your first contribution, embedding Serena in
your own agent, or understanding what a tool actually does under the hood. It is generated from
the docstrings in `src/serena`, and every entry links to its source — treat it as a guided way of
reading the code, not a substitute for it.

## The shape of the package, in the order you'll meet it

1. **The agent** — [serena.agent](serena/agent) holds `SerenaAgent`: it loads the configuration,
   activates a project, starts language servers, and decides which tools exist. Everything else
   hangs off it.
2. **The tools** — every capability an LLM sees is a `Tool` subclass. The base machinery
   (execution, logging, error recovery) lives in
   [serena.tools.tools_base](serena/tools/tools_base); the symbolic operations you'd actually
   recognize — `find_symbol`, `replace_symbol_body` — are in
   [serena.tools.symbol_tools](serena/tools/symbol_tools). A tool's docstring *is* its prompt: what
   you read there is exactly what the LLM reads.
3. **The configuration** — [serena.config.serena_config](serena/config/serena_config) contains the
   dataclasses behind `serena_config.yml` and project configuration.
4. **The project layer** — [serena.project](serena/project) is file access, ignore handling, and
   the bridge to the language-server library.

Want to build your own agent on top of Serena? The
[custom agent guide](../03-special-guides/custom_agent) is the narrative version of this section.

Undocumented members are deliberately left out — every entry you find here carries an actual
explanation. (The [solidlsp](https://github.com/oraios/serena/tree/main/src/solidlsp)
language-server library is not yet included.)
