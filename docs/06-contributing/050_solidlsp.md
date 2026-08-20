# SolidLSP

`src/solidlsp` is the library under everything: one interface over the Language Server
Protocol, wrapped around some sixty real language servers. It ships in the wheel alongside
`serena` and `interprompt`, and it is deliberately absent from the generated
[Code Reference](code-reference/000_code-reference-intro) — which makes this page its front
door.

## The shape of it

One abstract core, many small adapters:

- **`SolidLanguageServer`** (`ls.py`) — the abstract base every language-server adapter
  extends: lifecycle, requests, file buffers, symbol retrieval. This is the class you
  inherit from when [adding a language](030_adding-a-language).
- **`language_servers/`** — 74 adapters, one per server, and almost all of them small:
  pick a dependency-provider base, declare how to launch, add the server-specific
  initialization.
- **`dependency_provider.py`** — the `LanguageServerDependencyProvider` family: how a
  server gets onto the machine (uvx, a command, a single binary, or bespoke setup) and how
  every download is checksum-verified against
  `resources/downloaded_dependency_hashes.json`.
- **`ls_config.py`** — the registry: `LanguageServerId` (every supported server),
  `FilenameMatcher` (which files belong to which language), `LanguageServerConfig`.
- **`initialize_params.py`** — the `InitializeParamsBuilder`, which owns the common LSP
  initialization keys so an adapter states only what is specific to its server.
- **`lsp_protocol_handler/`, `ls_process.py`, `ls_request.py`, `ls_types.py`** — the wire:
  process management, JSON-RPC, protocol types.

## How Serena uses it

The `serena` package reaches SolidLSP through `LanguageServerManager`
(`src/serena/ls_manager.py`), which starts, holds and restarts servers per project; the
symbol tools sit on top. The separation is deliberate: SolidLSP knows nothing about agents
or tools — it answers questions about code, over LSP, and that is all.

## Working in it

Two kinds of work happen here, and they carry different etiquette:

### Adding a Language Server

The walk-right-in contribution —
[the path is mapped](030_adding-a-language), and adapters are deliberately shaped so that
most of yours is already written.

### Changing the Core

Lifecycle, buffers, initialization, process handling — this work deserves
more care. The core holds principles that are easy to bend without noticing: files are
never left open, a missing server fails fast rather than degrading quietly, cleanup must
never orphan a process. The record shows that correct-looking symptom fixes which bend one
of these get reworked by the maintainers even when the diagnosis was right —
[the FAQ explains that pattern](040_faq) — so for core changes, an issue first goes a long
way.
