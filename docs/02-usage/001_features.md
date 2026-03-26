# Features

Serena is essentially an **IDE for coding agents** -- it gives LLMs the same kind of structural code understanding
that human developers get from their IDEs, but through interfaces purpose-built for agents.
Every feature is available through both the **Language Server (LS)** backend (free, open-source) and the **JetBrains (JB)** plugin backend.
The JetBrains backend provides equivalents for all LS tools and adds additional, more powerful capabilities on top.

## General

Serena is designed around a few core principles:

- **Agent-first tool design** -- Serena's tools operate on **symbols and name paths** rather than on lines and columns.
  This is a deliberate design choice: line numbers and column offsets are fragile and shift with every edit,
  making them unreliable anchors for agents working on evolving code.
  Symbols (classes, methods, functions) are stable, meaningful identifiers that agents can reason about naturally.
  Tool results are compact JSON, keeping token usage low and output qujuality high.
- **LLM- and framework-independent** -- Serena is not tied to any specific LLM, agent framework, or interface. It works with any MCP-compatible client
  and can be integrated into custom agent pipelines.
- **Lightweight** -- Serena runs as a standalone MCP server. Language servers are downloaded automatically on demand. With the JetBrains backend, no additional downloads or processes are required.
- **Project-based configuration** -- Each project can have its own configuration, language servers, and memory store. Modes and contexts allow
  tailoring the active tool set to the workflow at hand.
- **Memories** -- A simple but effective Markdown-based memory system allows agents to persist and retrieve project knowledge across sessions,
  including automatic onboarding for new projects.

## Navigation

Serena's navigation tools allow agents to explore codebases at the symbol level, understanding structure and relationships
without reading entire files.

| Capability                         | Language Server                      | JetBrains Plugin (additional)          |
|------------------------------------|--------------------------------------|----------------------------------------|
| **Symbol overview** (file outline) | yes                                  | --                                     |
| **Find symbol** (by name path)     | yes                                  | --                                     |
| **Find references**                | yes                                  | --                                     |
| **Find implementations**          | yes (limited language support)       | yes (all languages)                    |
| **Go to definition** (by location) | yes                                  | --                                     |
| **Go to definition** (by regex)   | yes                                  | --                                     |
| **Type hierarchy** (super/subtypes)| --                                   | yes                                    |
| **Search in dependencies**        | --                                   | yes                                    |

The JetBrains backend supports **find implementations** across all languages, whereas the LS backend is limited to
languages whose language server supports it (e.g. not Python). The **type hierarchy** and **dependency search** are
JetBrains-exclusive features.

<!-- TODO: Add navigation demo video here
<video src=""
controls
preload="metadata"
style="max-width: 100%; height: auto;">
Your browser does not support the video tag.
</video>
-->

## Refactoring

Serena supports safe, codebase-wide refactoring operations.

| Capability              | Language Server | JetBrains Plugin (additional) |
|-------------------------|-----------------|-------------------------------|
| **Rename symbol**       | yes             | --                            |
| **Move** (symbol, file, directory) | --   | yes                           |
| **Inline method**       | --              | yes                           |
| **Safe delete**         | --              | yes                           |

**Rename** updates all references across the codebase automatically.
The JetBrains backend adds **move** (relocate symbols, files, or directories with automatic reference updates),
**inline method** (replace a method with its body at all call sites), and **safe delete** (delete a symbol only
after verifying it is unused, or propagate the deletion to remove all usages).

<!-- TODO: Add refactoring demo video here
<video src=""
controls
preload="metadata"
style="max-width: 100%; height: auto;">
Your browser does not support the video tag.
</video>
-->

## Diagnostics

Diagnostics expose compiler errors, warnings, and hints to the agent, enabling it to identify and fix issues
without running external build commands.

| Capability                            | Language Server | JetBrains Plugin (additional)                |
|---------------------------------------|-----------------|----------------------------------------------|
| **File diagnostics** (by line range)  | yes             | --                                           |
| **Symbol diagnostics** (+ references) | yes             | --                                           |
| **Automatic post-edit diagnostics**   | yes             | --                                           |
| **Quick fixes**                       | --              | yes                                          |

Both backends surface compiler errors, warnings, and hints. Serena's editing tools automatically report new diagnostics
after every edit, giving the agent immediate feedback on whether its changes introduced errors.

The JetBrains backend provides diagnostics customized to the user's IDE inspection profile and can offer
**quick fixes** -- automated, one-click resolutions for common issues.

<!-- TODO: Add diagnostics demo video here
<video src=""
controls
preload="metadata"
style="max-width: 100%; height: auto;">
Your browser does not support the video tag.
</video>
-->

## Debugging

Debugging is a **JetBrains-exclusive** feature. It allows the agent to launch run/debug configurations,
set breakpoints, and inspect program state -- all through the IDE's debugger.

<!-- TODO: Add debugging demo video here
<video src=""
controls
preload="metadata"
style="max-width: 100%; height: auto;">
Your browser does not support the video tag.
</video>
-->

## Editing

Serena provides both symbol-level and file-level editing tools for precise code modifications.

| Capability                    | Language Server | JetBrains Plugin (additional) |
|-------------------------------|-----------------|-------------------------------|
| **Replace symbol body**       | yes             | --                            |
| **Insert after symbol**       | yes             | --                            |
| **Insert before symbol**      | yes             | --                            |
| **Replace content** (regex)   | yes             | --                            |
| **Create / overwrite file**   | yes             | --                            |
| **Delete lines**              | yes             | --                            |
| **Replace lines**             | yes             | --                            |
| **Insert at line**            | yes             | --                            |
| **Auto-format after edit**    | --              | yes                           |

Symbol-level editing is Serena's recommended approach: the agent retrieves a symbol's body, modifies it, and writes
it back using `replace_symbol_body`. This avoids line-number fragility and ensures precise edits.

The JetBrains backend automatically **formats code** after every edit using the project's configured code style,
so the agent doesn't need to worry about indentation or formatting conventions.

<!-- TODO: Add editing demo video here
<video src=""
controls
preload="metadata"
style="max-width: 100%; height: auto;">
Your browser does not support the video tag.
</video>
-->

## Basic Features

Beyond its semantic capabilities, Serena includes essential utilities that round out the agent's toolkit.

- **`search_for_pattern`** -- Flexible regex search across the codebase with glob-based file filtering, context lines,
  and the option to restrict to code files only. Useful when you don't know the exact symbol name.
- **`list_dir` / `find_file`** -- Directory listing and file search with glob support. Helps agents orient themselves
  in unfamiliar projects.
- **`read_file`** -- Read files or file chunks by line range, for cases where symbolic access isn't applicable
  (e.g. configuration files, HTML templates).
- **`execute_shell_command`** -- Run shell commands (builds, tests, linters) directly from the agent,
  with configurable working directory and output limits.
- **Memories** (`write_memory`, `read_memory`, `list_memory`, `edit_memory`, `delete_memory`, `rename_memory`) --
  Persistent, Markdown-based project knowledge that survives across sessions. Supports hierarchical topics
  and global (cross-project) memories.
- **Onboarding** -- Automatic project familiarization on first encounter, storing key information as memories for future use.
- **Thinking tools** -- Structured reflection prompts (`think_about_collected_information`, `think_about_task_adherence`,
  `think_about_whether_you_are_done`) that improve agent reasoning quality during complex tasks.
