# REPL (`serena.repl`)

Alternative interaction paradigm: one tool (`serena_repl`) executes Python code against entrypoint `s`,
whose attributes are facades (`s.lsp`, `s.edit`, `s.fs`, `s.mem`, `s.shell`, `s.jb`, `s.cfg`).
Code runs like a notebook cell (module-level exec in the session namespace); the value of a trailing
expression is the result. No `return` (a top-level `return` yields a SyntaxError with a hint).

## Structure

- `repl/api/*_api.py`: `FacadeApi` implementations = the single implementation of each operation.
  The classic tools are thin adapters delegating to the APIs (via `*ApiMixin`); tools retain only
  transport concerns (input sanitisation, diagnostics context, tool-level output shaping).
- `repl/facade.py`: `Facade` = indirection over an API instance; `FacadeMethod` (enabled flag + `FacadeMethodInfo`);
  `ApiScope` = which facades/methods are enabled.
- `repl/repl.py`: `SerenaRepl` (execution, error formatting), `SerenaReplEntrypoint` (`s`, `info`).
- `repl/representable.py`: `Representable`/`Renderer`; result objects carry their rendering policy.

## Design principles

- Exposure is explicit: a method is exposed iff decorated with `@facade_method(...)`, which carries
  `optional`, `beta`, `can_edit`, `corresponding_tool` (mirroring the tool markers; the tool correspondence
  is recorded for optional derivation of exclusions and prompt conditions, never applied automatically).
- Naming: on result objects and non-exposed API helpers, a trailing underscore (`symbols_`, `to_dict_`)
  marks members that are Serena-public but not LLM-facing.
- Facades group by *domain*, not by read vs. write; mutation is expressed via `can_edit` (read-only projects
  exclude editing methods). Boundary `fs`/`edit`: files as units vs. modifying content within existing files.
- Facade descriptions describe the domain only; never list operations (the method list is always shown alongside).
- Output parameters (depth, include_body, max_answer_chars, ...) are passed at retrieval time so that the
  rendering policy is fixed once and inherited by derived results.
- Results expose data to code (`.symbols`, `.occurrences`, `.lines`, ...) and render like the classic tool output.
- Progressive disclosure: a priori only facade names, descriptions and method names; `s.info("<facade>")` /
  `s.info("<facade>.<method>")` give signature + docstring together, never a signature alone.
  `info(*items)` documents several items at once; unknown items are reported inline.
- Disclosure tiers: tier 0 (tool description) = facades, descriptions, method names with navigable return types
  (`find_symbol -> LspSymbolCollection`); tier 1 (`s.info("<facade>")`) = all common methods in full,
  `niche` methods (`@facade_method(niche=True)`, rarely needed + long docs) only as summary + pointer, result
  types by name only; tier 2 = types on request. Types are never pushed (`provide_info_with_facade` exists but
  is set nowhere); the tool description tells the model to request type docs only when processing results in code.
- Result types: every user-defined class reachable through annotations (method parameters/returns, and the members
  of reachable types, transitively) is automatically documentable (`Facade._discover_referenced_types`); builtins,
  typing constructs and stdlib classes are excluded. Explicit `ReferencedType` declarations (constructor arg
  `types=`) exist for curation only: an optional `members` whitelist (foreign/large classes such as
  `LanguageServerSymbol`; listed methods are shown even if undocumented, convention-derived ones only if
  documented) and flags. Enums render with members/values, TypedDicts with their keys. Types are documented via
  `s.info("<facade>.<Type>")` or bare `s.info("<Type>")`; method docs point to their referenced types.
  Result classes declare attribute annotations at class level (attributes set only in `__init__` are not
  discoverable). Annotations are rendered without module paths, so signature names equal lookup names.
  A type's documentation transitively includes the declared types its members reference; within a session
  (`SerenaSession.described_type_names`), a contained type is documented once and afterwards only pointed to
  (explicit requests always yield full documentation).

## Sessions (`serena.session`)

- MCP provides no reliable session identification (newer protocol versions drop it), and clients keep a stdio
  server across conversations. Hence the REPL's session identity is LLM-supplied: `create_system_prompt` creates
  a `SerenaSession` and states its id; `serena_repl` takes a required `session_id`. `SessionRegistry` creates
  unknown ids on demand (benign: at worst docs are repeated) and evicts LRU and idle (TTL) sessions.
  Sessions survive REPL rebuilds.
- Persistence (notebook semantics): `SerenaSession.repl_namespace` is the globals of the session's executions,
  which run at module level (statements exec'd, a trailing expression eval'd; line numbers preserved), so all
  top-level bindings persist across calls. `s` is re-bound in the namespace before every execution, so persisted
  functions always use the current entrypoint. `s.vars()`/`s.clear()` list/remove persisted items. Data is tied to
  the session's lifetime (not cleared on REPL rebuild); stored facades/project objects may go stale.
  Deferred idea if memory becomes an issue: hybrid — implicit items expire after N turns, explicit store
  (e.g. `s.d`) for indefinite retention.
- Only tools whose use presupposes having read the instructions may require the id. `activate_project` and
  `initial_instructions` may be called first and keep the existing MCP-context-derived session handling (prompt
  provision status); migrating that to LLM-supplied ids is a separate, future change.
- APIs must not import `serena.tools` at module level except for tool classes in decorators; tools import
  APIs locally in `_api()` (API modules refer to tool classes).

## Configuration

- `agent_interface: tools | REPL` (`AgentInterface`; global config, overridable per project; CLI `--agent-interface`).
  `None` = Serena's default (`tools`). Fixed for the session. In REPL mode the toolset is *fixed*
  (`serena_repl`, `initial_instructions`, `activate_project` unless single-project); tool inclusion/exclusion
  definitions do not apply — each interface has its own configuration vocabulary (tool definitions ↔ tools,
  API definitions ↔ REPL). Contexts do not influence the interface.
  In REPL mode, the language backend may change upon project activation (a project's backend override is
  applied; background modes, facades, prompt params and backend initialisation are recomputed), whereas the
  tool interface forbids this (the toolset depends on the backend and is fixed).
  Idea (not implemented, considered over-engineered for now): contexts could declare *supported* interfaces
  (a capability constraint, e.g. clients that handle the REPL badly), with the user's preference choosing among them.
- `included_apis`/`excluded_apis` (references `facade` or `facade.method`) in global config, context, modes,
  project config; applied in that order via `ApiScope` (exclusions first, then inclusions; later definitions win).
  Optional methods and all methods of an excluded facade must be included explicitly.
- The REPL is rebuilt whenever the active tools are updated (mode switch, project activation).

## Availability policy

- Keep as much functionality as possible in the REPL; do not mirror the contexts' tool exclusions.
  Reads must stay in (composability); exclusions can only steer the model, never enforce anything.
- Python code can always modify the system; the REPL tool is inherently fully privileged, regardless of
  facade scope or the project's `read_only` setting (which only makes Serena's own API refuse edits).
  A "read-only REPL" is not feasible and must not be promised.
- External projects (`s.ext`): `list_projects()`, `project_context(name)` (a `with`-able context; not nestable).
  Within it, the agent's active project is temporarily switched (`active_project_context`) and the facades are
  read-only (`can_edit` methods raise). Methods marked `@facade_method(uses_project_server=True)` (all of `lsp`)
  are executed in the project server via `/call_facade_method` ({facade, method, args, kwargs} as JSON, result
  pickled; the server is a trusted local process) when the LSP backend is active; with JetBrains they run locally
  (the IDE serves all projects). Result objects must be self-contained/picklable: renderers hold no agent (only the
  default length limit), LSP results carry eagerly retrieved info and reference contexts, no lambdas in output
  params. Replaces the query_project/list_queryable_projects tools in the REPL.
- Project activation (activate_project) and initial_instructions stay tool-only (activation rebuilds the REPL);
  Serena's configuration/session state (config overview, dashboard; later e.g. modes) lives in the `cfg` facade.
  Computed conditions (read-only project, dashboard not openable) are applied to the API scope in
  `SerenaAgent.get_repl` via `exclude_editing()`/`NamedApiInclusionDefinition`, mirroring the tool side.
