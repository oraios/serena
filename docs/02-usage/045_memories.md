(memories-onboarding-doc)=
# Memories & Onboarding

Serena provides the functionality of a fully featured agent, and a useful aspect of this is Serena's memory system.
Despite its simplicity, we received positive feedback from many users who tend to combine it with their
agent's internal memory management (e.g., `AGENTS.md` files).
If you don't need this functionality, you can disable all memory related tools by adding `no-memories` to the `base_modes`
`serena_config.yml` file. You can also disable just the onboarding process through the `no-onboarding` mode.

## How Memories Work

Memories are simple, human-readable Markdown files that both you and
your agent can create, read, and edit. The LLM is informed about the existence
of memories and instructed to read them when appropriate, inferring the appropriateness
from the file name.

When the agent starts working on a project, it receives the list of available memories. The agent
should be instructed to update memories by the user when appropriate.

### Organizing Memories

Memories can be organized into **topics** by using `/` in the memory name,
and the `list_memories` tool can filter by topic.

(global-memories)=
### Global Memories

In addition to project-specific memories that are stored in the `.serena/memories/` directory within
your project folder, Serena supports **global memories** that are
shared across all projects. Global memories are stored in `~/.serena/memories/global/`
and are addressed using the `global/` topic prefix (e.g., `global/java/style_guide`).

By default, deletion and editing of global memories is allowed.
If you want to protect global memories from accidental modification by the agent,
set `edit_global_memories: False` in your `serena_config.yml`.
We recommend tracking global memories with git.

(onboarding)=
## Onboarding

By default, Serena performs an **onboarding process** when it encounters a project
for the first time (i.e., when no project memories exist yet).
The goal of the onboarding is for Serena to get familiar with the project —
its structure, build system, testing setup, and other essential aspects —
and to store this knowledge as memories for future interactions.

In further project activations, Serena will check whether onboarding was already
performed by looking for existing project memories,and will skip the onboarding
process if any are found.

### How Onboarding Works

1. When a project is activated, Serena checks whether onboarding was already
   performed (by checking if any memories exist).
2. If no memories are found, Serena triggers the onboarding process, which
   reads key files and directories to understand the project.
3. The gathered information is written into memory files in `.serena/memories/`.

### Tips for Onboarding

- **Context usage**: The onboarding process will read a lot of content from the project,
  filling up the context window. It is therefore advisable to **switch to a new conversation**
  once the onboarding is complete.
- **LLM failures**: If an LLM fails to complete the onboarding and does not actually
  write the respective memories to disk, you may need to ask it to do so explicitly.
- **Review the results**: After onboarding, we recommend having a quick look at the
  generated memories and editing them or adding new ones as needed.

## Managing Memories Manually

Since memories are plain Markdown files, you can manage them manually at any time.

The [Serena Dashboard](060_dashboard) also provides a graphical interface for
viewing, creating, editing, and deleting memories while Serena is running.
