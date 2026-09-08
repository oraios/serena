# REPL (`serena.repl`)

Alternative interaction paradigm: one tool (`serena_repl`) executes Python code against entrypoint `s`,
whose attributes are facades (`s.lsp`, `s.edit`, `s.fs`, `s.mem`, `s.shell`, `s.jb`).
Code runs as a function body (`return` defines the result); a single expression is evaluated directly.

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
- Result types: a type returned by a single method is documented under `:return:`. Types that are shared,
  contained (`LanguageServerSymbol`) or navigated are declared per facade as `ReferencedType`s (constructor
  arg `types=`), with `provide_info_with_facade` (full description in `s.info("<facade>")`, else listed by name)
  and an optional `members` whitelist (curation for foreign/large classes; listed methods are shown even if
  undocumented, convention-derived ones only if documented). Types are documented via `s.info("<facade>.<Type>")`
  or bare `s.info("<Type>")`; method docs point to their referenced return type. Result classes declare
  attribute annotations at class level (attributes set only in `__init__` are not discoverable).
  Annotations are rendered without module paths, so signature names equal lookup names.
- APIs must not import `serena.tools` at module level except for tool classes in decorators; tools import
  APIs locally in `_api()` (API modules refer to tool classes).

## Configuration

- `agent_interface: tools | REPL` (`AgentInterface`; global config, overridable per project; CLI `--agent-interface`).
  `None` = Serena's default (`tools`). Fixed for the session. In REPL mode the toolset is *fixed*
  (`serena_repl`, `initial_instructions`, `activate_project` unless single-project); tool inclusion/exclusion
  definitions do not apply — each interface has its own configuration vocabulary (tool definitions ↔ tools,
  API definitions ↔ REPL). Contexts do not influence the interface.
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
- Project activation (activate_project) and initial_instructions stay tool-only (activation rebuilds the REPL);
  Serena's configuration/session state (config overview, dashboard; later e.g. modes) lives in the `cfg` facade.
  Computed conditions (read-only project, dashboard not openable) are applied to the API scope in
  `SerenaAgent.get_repl` via `exclude_editing()`/`NamedApiInclusionDefinition`, mirroring the tool side.
