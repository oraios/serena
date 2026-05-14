# Memories & Onboarding

Serena provides the functionality of a fully featured agent, and a useful aspect of this is Serena's memory system.
Despite its simplicity, we received positive feedback from many users who tend to combine it with their
agent's internal memory management (e.g., `AGENTS.md` files).

(memories)=
## Memories

Memories are simple, human-readable Markdown files that both you and
your agent can create, read, reference, and edit. 

Serena differentiates between 
  * **project-specific memories**, which are stored in the `.serena/memories/` directory within your project folder, and
  * **global memories**, which are shared across all projects and, by default, are stored in `~/.serena/memories/global/`

The LLM is informed about the existence of memories and instructed to read them when appropriate, 
inferring appropriateness from the file name.
When the agent starts working on a project, it receives the list of available memories. 
The agent should be instructed to update memories by the user when appropriate.

### Design Rationale

Serena's memory system is intentionally minimal. It was designed to satisfy the following
criteria:

1. **Human-readable and editable.** Memories must remain directly readable and editable
   in any text editor. The agent is typically the day-to-day consumer, but a human author
   or reviewer must always be able to step in without going through the agent.
2. **Versionable with the project.** Project memories live alongside the code and can
   be committed, reviewed in PRs, and reverted like any other repository artifact.
3. **Progressive disclosure.** Agents receive the full memory *name list* up
   front as part of their initial instructions; any further references are described inside
   the memory content itself - typically a `mem:core` entry point pointing at focused
   memories. The agent decides what to read based on names plus the references it has
   already seen.
4. **Prefer references to search.** Given an intelligent agent and well-structured references, search is
   unnecessary - and it adds noise: any retrieval method (lexical or semantic)
   produces both false positives and false negatives. Explicit, name-based references
   decided by the agent are deterministic and avoid both error modes. Basic search via regex/grep
   is sufficient to complement the references when needed and is available to any agent.
5. **Prefer deliberate reads to triggers.** The agent decides what to read and when. The harness does
   not inject memory content on the agent's behalf.
6. **Framework-agnostic.** The storage format is plain Markdown files in
   a simple directory layout. The only Serena-specific convention is the `mem:` 
   prefix for references to memories, which does not prevent using the memory files outside
   of Serena.
7. **Configurable and composable.** Two orthogonal memory scopes -
   [per-project](memories) (committed alongside the code) and [global](global-memories)
   (shared across all your projects) - can be combined freely. Within either scope,
   regex patterns in the global or project configuration can mark subsets as read-only
   or [hide them entirely](ignoring-memories) from the agent. This lets a project mix
   personal cross-project knowledge with checked-in project conventions, and selectively
   freeze either set, without custom plumbing.

Taken together, these criteria rule out several common alternatives:

- **Database-backed memory** (SQLite, graph databases, vector stores) is excluded by
  criteria 1, 4, and 6.
- **`AGENTS.md` and similar single-file conventions** are excluded by criteria 3 and 5.
- **Hooks and harness-internal memory systems** are excluded by criteria 5 and 6.

To our knowledge, no existing system satisfies our design goal, which is
why Serena ships its own memory layer rather than reusing one.
The closest existing approaches are in the family of Markdown-based personal knowledge
management tools - **Obsidian**, **Logseq**, **Foam**.

### Organizing Memories

Memories can be organized into **topics** by using `/` in the memory name (e.g. `modules/frontend`).
The structure is mapped to the file system, where topics correspond to subdirectories.
The `list_memories` tool can filter by topic, allowing the agent to explore even large numbers of memories in a structured way.

(memory-references)=
### Referencing Memories from Other Memories

Memories may reference each other. Serena recognizes a reference as a memory name prefixed with
`mem:` and wrapped in backticks, for example `` `mem:auth/login` `` or `` `mem:suggested_commands` ``.
This convention has two practical consequences:

- **Renames keep references intact.** When you rename or move a memory with the `rename_memory`
  tool, Serena rewrites every `` `mem:OLD_NAME` `` occurrence across all memories to point to
  the new name. References that do not use the `mem:` prefix will not be updated automatically.
- **Integrity checks** (see [below](memory-cli)) report any `` `mem:NAME` `` whose target does
  not resolve to an existing memory, and propose similarly-named candidates as likely intended
  targets.

The full convention - including style, add/update thresholds, and how to structure references across
`core` memories - is shipped to every onboarded project as the `memory_maintenance` memory; see the
[Onboarding section](onboarding) below.

(global-memories)=
### Global Memories

Global memories use the top-level topic `global`, i.e. whenever a memory name starts with `global/`, 
it is stored in the global memories directory and is shared across all projects.

By default, deletion and editing of global memories is allowed.
If you want to protect them from accidental modification by the agent,
you can add regex patterns to `read_only_memory_patterns` in your global or
project-level [configuration](050_configuration). For example, setting "global/.*" will mark all global memories as read-only. The agent will be informed which memories are read-only.

Since global memories are not versioned alongside your project files,
it can be helpful to track global memories with git (i.e. to make `~/.serena/memories/` a git repository)
in order to have a history of changes and the possibility to revert them if needed.

(ignoring-memories)=
### Ignoring Memories

Projects that accumulate large numbers of archived memory files can use `ignored_memory_patterns`
to exclude them from `list_memories` and `activate_project` output. Add regex patterns to the
global or project-level [configuration](050_configuration):

```yaml
ignored_memory_patterns: ["_archive/.*", "_episodes/.*"]
```

Ignored memories are completely excluded - they cannot be accessed via `read_memory`, `write_memory`,
or any other memory tool. To read an ignored memory file, use the `read_file` tool on the raw file path
(e.g., `.serena/memories/_archive/2026-03/some-topic.md`).

Like `read_only_memory_patterns`, patterns from the global and project-level configurations are merged additively.

### Manually Editing Memories

You may edit memories directly in the file system, using your preferred text editor or IDE.
Alternatively, access them via the [Serena Dashboard](060_dashboard), which provides a graphical interface for
viewing, creating, editing, and deleting memories while Serena is running.

(onboarding)=
## Onboarding

By default, Serena performs an **onboarding process** when it encounters a project
for the first time (i.e., when no project memories exist yet).
The goal of the onboarding is for Serena to get familiar with the project -
its structure, build system, testing setup, and other essential aspects -
and to store this knowledge as memories for future interactions.

In further project activations, Serena will check whether onboarding was already
performed by looking for existing project memories and will skip the onboarding
process if memories are found.

### How Onboarding Works

1. When a project is activated, Serena checks whether onboarding was already
   performed (by checking if any memories exist).
2. If no memories are found, Serena triggers the onboarding process, which
   reads key files and directories to understand the project.
3. Before any project memory is written, Serena materializes a project-local
   `memory_maintenance` memory (see below). The agent is then instructed to read it
   first and follow the conventions it describes.
4. The gathered information is written into project-specific memory files following
   the onboarding prompt instructions and the conventions outlined in `memory_maintenance`.

(memory-maintenance-memory)=
### The `memory_maintenance` Memory

To make memory conventions discoverable to both the LLM and the user, Serena seeds
a `memory_maintenance` memory on first onboarding. The seed is copied from a template
shipped with the Serena package and contains the dense agent-notes style, the
`mem:` reference convention, the reference model around `core` memories, the
add/update threshold, and the maintenance actions (rename / delete / split).

The seeding follows a strict precedence:

1. If you already maintain a `global/memory_maintenance` memory, Serena uses that
   and **does not** create a project-local copy. This is the recommended approach
   for teams that want one shared convention document across all projects.
2. Otherwise, if the project already has a `memory_maintenance` memory, it is left
   untouched.
3. Otherwise, the shipped template is written to `.serena/memories/memory_maintenance.md`.

Existing files are never overwritten - you can freely customize the project copy.
To refresh from the shipped template, delete the existing memory first.

### Tips for Onboarding

- **Context usage**: The onboarding process will read a lot of content from the project,
  filling up the context window. It is therefore advisable to **switch to a new conversation**
  once the onboarding is complete.
- **LLM failures**: If an LLM fails to complete the onboarding and does not actually
  write the respective memories to disk, you may need to ask it to do so explicitly.
- **Review the results**: After onboarding, we recommend having a quick look at the
  generated memories and editing them or adding new ones as needed.

(memory-cli)=
### CLI Subcommands

While the recommended way to manage memories is through the **MCP integration**, 
Serena also offers memory-related CLI commands.

The following commands have **no MCP tool counterpart** and are intended for human execution:

- `serena memories check` — referential-integrity report. By default reports stale
  `` `mem:NAME` `` references; additional scans (bare occurrences and fuzzy near-misses)
  are opt-in via flags. Run `serena memories check --help` for the full flag list.
- `serena memories auto-prefix-references` — heuristic rewrite of bare occurrences to add
  the `mem:` prefix; supports `--dry-run`.
- `serena memories initialize` will seed the `memory_maintenance` memory for the project.

The remaining commands mirror the MCP tools, you can thus instruct your agent to manage memories with
serena without having a running MCP server. Discover the full surface and per-command flags via:

```shell
serena memories --help
serena memories <subcommand> --help
```

## Disabling Memories and Onboarding

If you do not require the functionality described in this section, you can selectively disable it.

 * To disable all memory related tools (including onboarding), adding `no-memories` to the `base_modes`
   in Serena's [global configuration](050_configuration).
 * Similarly, to disable only onboarding, add `no-onboarding` to the `base_modes`.
