# About Serena

Serena is **the IDE for your coding agent**. 

* It provides essential **semantic code retrieval, editing and refactoring tools** that are akin to an IDE's capabilities,
  operating at the symbol level and exploiting relational structure. 
* It integrates with any client/LLM via the model context protocol (MCP).

Serena's agent-first tool design involves robust high-level abstractions, distinguishing it from
approaches that rely on low-level concepts like line numbers or primitive search patterns.

Practically, this means that your agent operates faster, more efficiently and more reliably, especially in larger and
more complex codebases.

## Features

Serena supports two code intelligence backends:

* **Language servers** implementing the language server protocol (LSP) — the free/open-source alternative.
* **The Serena JetBrains Plugin**, which leverages the capabilities of your JetBrains IDE.

Language Servers, while very powerful, have inherent limitations.
The JetBrains variant is the more advanced solution, as detailed below. It is also more memory-efficient, especially in
multi-agent scenarios.


Purchasing the JetBrains plugin supports the continued development of Serena.


### Retrieval

Serena's retrieval tools allow agents to explore codebases at the symbol level, understanding structure and relationships
without reading entire files.

| Capability                         | Language Server | JetBrains Plugin |
|------------------------------------|-----------------|------------------|
| **find symbol**                    | yes             | yes              |
| **symbol overview** (file outline) | yes             | yes              |
| **find referencing symbols**       | yes             | yes              |
| **search in project dependencies** | --              | yes              |
| **type hierarchy**                 | --              | yes              |
| **find declaration**               | --              | yes              |
| **find implementations**           | --              | yes              |
| **query external projects**        | yes             | yes              |


### Refactoring

| Capability                                   | Language Server    | JetBrains Plugin                  |
|----------------------------------------------|--------------------|-----------------------------------|
| **rename**                                   | yes (only symbols) | yes (symbols, files, directories) |
| **move** (symbol, file, directory)           | --                 | yes                               |
| **inline**                                   | --                 | yes                               |
| **propagate deletions** (remove unused code) | --                 | yes                               |


### Symbolic Editing

Much more token-efficient than default editing tools.

| Capability               | Language Server | JetBrains Plugin |
|--------------------------|-----------------|------------------|
| **replace symbol body**  | yes             | yes              |
| **insert after symbol**  | yes             | yes              |
| **insert before symbol** | yes             | yes              |
| **safe delete**          | yes             | yes              |

### Basic Features

Beyond its semantic capabilities, Serena includes a set of basic utilities for completeness.
When Serena is used inside an agentic harness such as Claude Code or Codex, these tools are typically disabled by default,
since the surrounding harness already provides overlapping file, search, and shell capabilities.

- **`search_for_pattern`** -- Flexible regex search across the codebase with glob-based file filtering, context lines,
  and the option to restrict to code files only. Useful when you don't know the exact symbol name.
- **`list_dir` / `find_file`** -- Directory listing and file search with glob support. Helps agents orient themselves
  in unfamiliar projects.
- **`read_file`** -- Read files or file chunks by line range, for cases where symbolic access isn't applicable
  (e.g. configuration files, HTML templates).
- **`execute_shell_command`** -- Run shell commands (builds, tests, linters) directly from the agent,
  with configurable working directory and output limits.

### Memory Management

Serena provides the functionality of a fully featured agent, and a useful aspect of this is Serena's memory system.
Despite its simplicity, we received positive feedback from many users who tend to combine it with their
agent's internal memory management (e.g., `AGENTS.md` files).
Many other memory management systems for agents exist, and you can easily disable Serena's memory management if you
prefer not to use it.

## Configurability

Active tools, tool descriptions, prompts, language backend details and many other aspects of Serena
can be flexibly configured on a per-case basis by simply adjusting a few lines of YAML.
To achieve this, Serena offers multiple levels of (composable) configuration:

* global configuration
* MCP launch command (CLI) configuration
* per-project configuration (with local overrides)
* execution context-specific configuration (e.g. for particular clients)
* dynamically composable configuration fragments (modes)
