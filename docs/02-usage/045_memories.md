# Memories & Onboarding

Serena provides the functionality of a fully featured agent, and a useful aspect of this is Serena's memory system.
Despite its simplicity, we received positive feedback from many users who tend to combine it with their
agent's internal memory management (e.g., `AGENTS.md` files).

## Memories

Memories are simple, human-readable Markdown files that both you and
your agent can create, read, and edit. 

Serena differentiates between 
  * **project-specific memories**, which are stored in the `.serena/memories/` directory within your project folder, and
  * **global memories**, which are shared across all projects and, by default, are stored in `~/.serena/memories/global/`

The LLM is informed about the existence of memories and instructed to read them when appropriate, 
inferring appropriateness from the file name.
When the agent starts working on a project, it receives the list of available memories. 
The agent should be instructed to update memories by the user when appropriate.

### Organizing Memories

Memories can be organized into **topics** by using `/` in the memory name (e.g. `modules/frontend`).
The structure is mapped to the file system, where topics correspond to subdirectories.
The `list_memories` tool can filter by topic, allowing the agent to explore even large numbers of memories in a structured way.

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

### Manually Editing Memories

You may edit memories directly in the file system, using your preferred text editor or IDE.
Alternatively, access them via the [Serena Dashboard](060_dashboard), which provides a graphical interface for
viewing, creating, editing, and deleting memories while Serena is running.

(onboarding)=
## Onboarding

By default, Serena performs an **onboarding process** when it encounters a project
for the first time (i.e., when no project memories exist yet).
The goal of the onboarding is for Serena to get familiar with the project —
its structure, build system, testing setup, and other essential aspects —
and to store this knowledge as memories for future interactions.

In further project activations, Serena will check whether onboarding was already
performed by looking for existing project memories and will skip the onboarding
process if memories are found.

### How Onboarding Works

1. When a project is activated, Serena checks whether onboarding was already
   performed (by checking if any memories exist).
2. If no memories are found, Serena triggers the onboarding process, which
   reads key files and directories to understand the project.
3. The gathered information is written into project-specific memory files (see above).

### Tips for Onboarding

- **Context usage**: The onboarding process will read a lot of content from the project,
  filling up the context window. It is therefore advisable to **switch to a new conversation**
  once the onboarding is complete.
- **LLM failures**: If an LLM fails to complete the onboarding and does not actually
  write the respective memories to disk, you may need to ask it to do so explicitly.
- **Review the results**: After onboarding, we recommend having a quick look at the
  generated memories and editing them or adding new ones as needed.

## Disabling Memories and Onboarding

If you do not require the functionality described in this section, you can selectively disable it.

 * To disable all memory related tools (including onboarding), adding `no-memories` to the `base_modes`
   in Serena's [global configuration](050_configuration).
 * Similarly, to disable only onboarding, add `no-onboarding` to the `base_modes`.
