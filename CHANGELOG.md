# Unreleased (main)

Status of the `main` branch. Changes prior to the next official version change will appear here.

* General:
  - Add notion of trusted projects via new global configuration setting `trusted_project_path_patterns`.
    Current effects:
    - `ls_specific_settings` defined in project configurations will only be applied for trusted projects    
  - Fix: context or mode argument referencing a known name (e.g. `--context anitgravity`) could result in   
    incorrect file access if a corresponding local file existed (e.g. `./antigravity` binary);
    file access is now guarded with path detection (file ending or path separator must be present)
  - Adjust prompt generation mechanism to use newly introduced tool name mapping `tool_names`, allowing
    prompts to directly use tool names that match the active language backend (and removing the need
    for additional prompts that explain tool name differences)
  - Improve quoting/escaping of arguments in shell executions on Windows (via `oslex` dependency)
  - Fix: a registered project whose root directory was deleted while Serena was already running could break
    `activate_project`/project lookup, raising `FileNotFoundError` in `RegisteredProject.matches_root_path`
  - Update prompts/instructions: Serena instructions manual, modes (editing, interactive) 
  - Allow structured tool output to be configured on a per-context basis, disabling it for Claude Code
    (which does not correctly unpack structured output) #1042

* CLI:
  - Fix `--project-from-cwd` hijacking git worktrees nested under a Serena project. `find_project_root`
    now walks up in a single pass so the nearest project boundary wins (either a `.serena/project.yml`
    or a `.git`, including worktree/submodule pointer files), instead of preferring an ancestor's
    `.serena/project.yml` over a closer `.git`. This previously bound CLI agents (Claude Code, Codex,
    Gemini) launched from inside a worktree to the parent repo, causing stale reads and misdirected edits.
  - Fix: CLI flags on `start-mcp-server` could incorrectly be saved to the global configuration file if the
    list of projects was modified (triggering a save of the configuration with transient overrides applied)

* Tools:
  - New tool: `replace_in_files`
  - `get_symbols_overview`, `jet_brains_get_symbols_overview`: Improved default for `depth` parameter
  - Add tool parameter alias support, adding `name_path` as an alias for `name_path_pattern` in `find_symbol` tools
  - Allow `query_project` tool to access read-only tools that are not enabled in the current configuration
  - Make tool call errors surface explicitly as errors at the MCP protocol level

* Language Servers:
  - C/C++ (clangd): improve support and documentation for Unreal Engine 5 projects.
  - `typescript_vts`: Add `initialization_options` setting in `ls_specific_settings.typescript_vts`. 
    Enables Yarn PnP setups with `typescript.tsdk` pointing at the Yarn-generated SDK.
  - C#: minor fixes in Omnisharp and Roslyn that prevented startup on some systems #1617
  - `SvelteLanguageServer`: Fix diagnostics requests for TypeScript/JavaScript files incorrectly being
    processed by the Svelte LS instead of the TypeScript LS.
  - `SvelteLanguageServer`: Fix document-symbol requests for TypeScript/JavaScript files returning empty
    results in svelte-only mode (`languages: [svelte]`. #1552
  - `JuliaLanguageServer`: Fix the stdio MCP server exiting right after `initialize` ("tools fetch failed")
    when `julia` is enabled. #1577
  - `Java`: invalidate JDTLS workspace cache when Java import settings change #1576
  - Improve quoting of arguments in shell executions
  - Add **LaTeX** support (experimental) via [texlab](https://github.com/latex-lsp/texlab).
  - PHP: add support for PHPantom as alternative to the already supported PHP LS #1554.

* JetBrains:
  - Add configuration option `jetbrains_launch_command`, allowing Serena to spawn IDE instances automatically
    upon project activation
  - Fix: `jet_brains_list_inspections` failed when only default parameters were used #1615 

* Dashboard:
  - Make list of trusted hosts configurable, fixing host validation introduced in v1.5.2 allowing only
    default local hostnames, effectively preventing remote connections
  - Decouple configuration computation from the agent's task queue by introducing events for agent config/status updates.
    This allows the dashboard to display the configuration while the project provided at startup is still initialising. #1064
  - Fix empty executions queue displaying "Loading..."
  - Tray manager: Add NixOS-support for AppIndicator-based trays (e.g., most Wayland-trays) to the package in flake.nix.
  - Fix: Wait for the subprocess that opens the browser window, preventing zombie processes #1488 

* Hooks:
  - Handle tool_input passed as string gracefully instead of failing (Copilot CLI sends strings).

* Memories:
  - Make memory iteration follow symbolic links 

* Dependencies:
  - Add dependency `oslex`

# v1.5.3 (2026-05-26)

Add meta-data for the GitHub MCP registry

# v1.5.2 (2026-05-26)

* General:
  - Not existing paths return `False` on is ignored checks (instead of raising an error)
  - Add `serena-agent` CLI command so that `uvx serena-agent` can be used as entrypoint.
  - Fortls and pyright are now installed on the fly instead of being bundled in the serena-agent package.

* Dashboard:
  - Add host validation

* Hooks:
  - Extend list of extensions that are considered code files (affects the reminder hook counter).

# v1.5.1 (2026-05-18)

* General:
  - Fix `onboarding_tool`: Used incorrect path to bootstrap memory (regression in v1.5.0)  
 
* Language Servers:
  - Add **CUE** support via the LSP mode of the official [`cue` CLI](https://github.com/cue-lang/cue) (`cue lsp`).

# v1.5.0 (2026-05-18)

* General:
  - Make tool descriptions more amenable to tool search mechanisms as now used in several clients (e.g. avoid referencing other tools' names, etc.)
  - Onboarding is now less invasive (LLM is instructed to ask the user whether to proceed)

* Language Servers:
  - No longer store temporary files (e.g. downloads) in `~/solidlsp_tmp`; instead, use OS-specific temporary directories
  - Add **GDScript** (Godot Engine) support. Serena connects over TCP to the Godot editor's built-in LSP server (port 6008, same for Godot 3 and 4) — no separate language server process to install. Godot major version is auto-detected from `config_version` in `project.godot`. Note: Godot's LSP does not implement `workspace/symbol`; first workspace-wide scans fall back to per-file requests and can be slow for large projects (results are cached to disk). See the [GDScript Setup Guide](https://oraios.github.io/serena/03-special-guides/godot_gdscript_setup_guide_for_serena.html) for details. Closes #1446.

* Dashboard:
  - UI polish: switch UI font to Inter (with system fallbacks) and use JetBrains Mono only for code/logs/paths/identifiers; refine the light/dark palette with softer borders, clearer text hierarchy, and a more nuanced shadow/elevation system; introduce a consistent spacing scale; keep the orange accent.
  - Modal markup cleanup: extract shared CSS classes (`.modal-info`, `.modal-hint`, `.modal-prompt`, `.modal-field`, `.modal-input`, `.modal-select`, `.modal-textarea`, `.modal-actions`, `.btn-secondary`) and remove duplicated inline styles from all seven modals. Inputs and textareas get an accent-colored focus ring; the modal backdrop has a subtle blur.
  - Add Language: replace the native `<select>` with a filterable combobox — type to filter, keyboard navigation (Up/Down/Enter/Esc), substring highlight, click-outside to close. The typed value is validated against the available languages list before submission.

* Memories:
  - Memories can now reference each other using the `mem:<name>` convention. Renames
    propagate to all references automatically. See the [reference convention](https://oraios.github.io/serena/02-usage/045_memories.html#referencing-memories-from-other-memories).
  - Onboarding now seeds a `memory_maintenance` memory describing the memory-style and conventions, 
    and the agent is instructed to read it before writing any other memories. 
    A `global/memory_maintenance` memory takes precedence over the per-project seed. 
    See the [memory maintenance section](https://oraios.github.io/serena/02-usage/045_memories.html#the-memory-maintenance-memory).
   
* CLI:
  - Add `serena memories` CLI command group: `list`, `read`, `write`, `check` (referential
    integrity report) and `auto-prefix-references` (heuristic rewrite of bare occurrences).
    See the [CLI subcommands](https://oraios.github.io/serena/02-usage/045_memories.html#cli-subcommands).

* Tools:
  - `search_for_pattern`: Add parameter `multiline`
  - Delete `check_onboarding_performed` tool (instead extend project activation message)

# v1.3.0 (2026-05-11)

* General:
  - Breaking change in mode definitions: Projects (project.yml) can no longer override `base_modes`.
    Instead, they can define `added_modes` to add modes on top of base and default modes.  
    See updated [documentation on modes](https://oraios.github.io/serena/02-usage/050_configuration.html#modes).
  - Serena's default configuration now uses `interactive` and `editing` as `base_modes` instead of as `default_modes`.
  - Fixed path validation in `search_for_pattern` tool (thanks to [@dodge1218](https://github.com/dodge1218) for the report)
  - Fix: In HTTP/SSE mode, a client disconnection triggered a partial agent shutdown (project deactivation, dashboard manager & GUI viewer shutdown)
  
* JetBrains:
  - Add new tools:
    - `jet_brains_list_inspections`: Lists available IDE inspections (akin to diagnostics), optionally filtered by language or group
    - `jet_brains_run_inspections`: Runs IDE inspections on a file and returns the results

* LSP Backend:
  - Add cross-package reference support via `additional_workspace_folders` setting (currently implemented for TypeScript).
  - Add new tools:
    - `find_declaration`: Finds the declaration/definition of a symbol
    - `find_implementations`: Finds the implementations of an interface or abstract method
    - `get_diagnostics_for_file`: Retrieves diagnostics for a specific file (errors, warnings, etc.)
    - `get_diagnostics_for_symbol`: Retrieves diagnostics pertaining to a specific symbol

* Language Servers:
  - Add **Svelte** support via `svelte-language-server@0.18.0`, installed with npm into Serena-managed language-server resources. The `svelte` language handles `.svelte` Single File Components plus TypeScript/JavaScript files for Svelte projects; use it instead of also enabling `typescript` unless intentionally running multiple language servers.
  - Elixir (`elixir-tools/next-ls`): Fix deadlock in monorepo projects where `mix.exs` lives in a subdirectory. The server now searches immediate subdirectories when no `mix.exs` is found at the repository root. #1444
  - Java (`eclipse.jdt.ls`): Add upstream JDTLS mode for offline / restricted-network use. Setting both `jdtls_path` and `lombok_path` in `ls_specific_settings.java` makes Serena use an existing upstream JDTLS installation (e.g. `brew install jdtls`) and the system JDK 21+, skipping the ~500 MB vscode-java VSIX, Gradle, and IntelliCode downloads. New related setting `java_home` lets the user override the JDK used to launch JDTLS. Default behavior unchanged — the JDTLS workspace hash is preserved bit-for-bit for users on the default route, so existing project caches are reused without a one-time reindex; the launcher path is mixed into the hash only when `jdtls_path` is set, isolating upstream installations from the default workspace. #1415
  - Java (eclipse.jdt.ls): Lombok-generated methods (getters/setters, builder(), equals/hashCode/toString, etc.) are now included in symbol-based tools (find_symbol, get_symbols_overview, edits). Added lombok_show_generated setting (default: on) to toggle this. Updated bundled vscode-java to 1.54.0-923. Issue #1432.
  - Add **Ada / SPARK** support using AdaCore's [Ada Language Server](https://github.com/AdaCore/ada_language_server). Auto-downloads the official prebuilt ALS binary (linux-x64/arm64, darwin-x64/arm64, win32-x64). A single `ada` language covers both Ada and SPARK, since the server uses the same `.ads`/`.adb` files for both and distinguishes SPARK by source-level pragmas/aspects. Users can override the binary by setting `ls_specific_settings.ada.ls_path` to a pre-installed `ada_language_server` (e.g. from Alire, GNAT Studio, or the VS Code Ada extension).
  - Add **Angular** (experimental) via a dual-server architecture: `@angular/language-server` (ngserver) handles standalone `.html` template files, while a companion `typescript-language-server` with `@angular/language-service` loaded as a tsserver plugin handles all `.ts` operations including inline templates. Provides type-aware navigation between templates and component classes. Requires Node.js, npm, and `@angular/core` installed in the project (`npm install` in the project root). Subsumes `typescript`+`html` for `.ts`/`.html` files when active; SCSS is not subsumed.
  - Add **HTML** (experimental) using `vscode-html-language-server` from the `vscode-langservers-extracted` npm package. Provides in-file element/id symbols via documentSymbol; cross-file references are not meaningful for HTML. Also used as a companion server by the Angular LS for plain HTML documentSymbol support.
  - Add **SCSS / Sass / CSS** (experimental) using [some-sass-language-server](https://github.com/wkillerud/some-sass). Handles `.scss`, `.sass`, and `.css` through one server, with full `@use`/`@forward` workspace-wide go-to-definition and find-references for variables, mixins, and functions across Sass files. The `.css` path uses the same `vscode-css-languageservice` engine that powers the standalone CSS LS; CSS feature toggles default off upstream and are flipped on at startup so symbols, hover, completion, and syntax-level diagnostics work for plain CSS as well.
  - Add **1C / OneScript** support using [BSL Language Server](https://github.com/1c-syntax/bsl-language-server/).
  - Add support for more filenames to be considered by ccls and clangd.
  - Clojure (`clojure-lsp`): Fix incomplete `find_referencing_symbols` results in multi-module monorepos. clojure-lsp only discovers source paths from the descriptor at the workspace root and does not recurse for sub-module `deps.edn` / `project.clj` / `shadow-cljs.edn` / `bb.edn` files, so references in sibling modules were silently missed until those files happened to be opened by `find_symbol` / `get_symbols_overview`. Serena now scans the repo for project descriptors at startup and passes the union of their declared source paths to clojure-lsp via `initializationOptions`. Project-local `.lsp/config.edn` files are honoured as-is (no override). New `ls_specific_settings.clojure` keys: `source_paths` (explicit override) and `config_edn_path` (parse `:source-paths` from a user-supplied config file).

* Hooks:
  - `serena-hooks auto-approve` now also emits an `allow` decision when Claude Code reports
    `permission_mode == "auto"`, in addition to the existing `acceptEdits` behavior. #1386
  - Extension: heuristics for parsing commands and firing a hook on too many greps or reads. Important for clients that, unlike claude code, don't have dedicated grep/read tools.
  - Read hook now only fires on reads of code files (using heuristics to parse the read command string)
  - Reminder hook now also counts and fires on usages of serena's non-symbolic tools.

# v1.2.0 (2026-04-27)

* General:
  - Fix: Check for ignored path ignored `.git` folder only at the top level, not in every subdirectory (`Project._is_ignored_relative_path`) #1350
  - `GetSymbolsOverviewTool`: ignored paths were not respected in LSP variant (fix in `SolidLanguageServer`)
  - Fix: Duplicate comments in re-saved YAML configuration files #1285
  - Prompt provision improvements (project activation, initial instructions):
     - Prompt provision is now session-aware, i.e. when using the MCP server in HTTP mode, prompts are provided for each session separately, 
       ensuring that the necessary information is always provided to the LLM
     - Fix: Prompts of dynamically activated modes (upon project activation) were not necessarily passed to the LLM (only in the system prompt via
       `initial_instructions`). Now they are passed directly in the activation message (and excluded from a subsequent `initial_instructions` call).
     - Fix: Project activation message was provided more than once for case of dynamic project activation followed
       by `initial_instructions` #1372
     - Always provide full activation message upon calling `activate_project` (even if project was already active in the same session) #1384
       This is necessary, because some clients (e.g. Claude Desktop) will reuse a single session across chats.
  - Security: Forbid `".."` in memory names to disallow accessing files outside dedicated memory directories
  - Security: Add check for tool being read-only in the project server (previously only checked in `query_project` tool, i.e. client side)
  - Usage reporting now also includes the name of the Serena context that is used 
  - Fix: restricted `insert_after_symbol` to raise if used on an assignment or similar (can't reliably determine the symbol range)
  - Fix: Failure to collect project ignore spec now logs the error and downstream tasks fail fast, fixing hanging LS initialisation
  - Improve loading of `project.yml` files: Gracefully handle user errors involving incorrect use of None/empty instead of list
  - Project server: 
     - `query_project`: Support use of project root instead of project name #1388
     - `list_queryable_projects`: Return both project names and project roots 
  - Fix: `search_for_pattern` tool returned 1-based line numbers (in contrast to all other tools); cause: implementation of `text_utils.search_text`
  - Serena's system prompt (a.k.a. the 'Serena Instructions Manual') is now provided lazily. 
    At MCP connection time, only a one-sentence bootstrap prompt is provided.
    The `initial_instructions` tool provides the full prompt on demand, keeping the initial context lean.
  - Add `serena_info` tool for on-demand retrieval of usage information

* CLI:
  - Support `serena --version` CLI command for displaying the current version #1347
  - Extend `prompts` subcommand with `print-prompt-template` and `print-cc-system-prompt-override`, improve `list` subcommand

* Clients:
  - Document workaround to make Claude Code use Serena's tools after recent degradations caused by changes in CC harness and Opus 4.7 release.

* JetBrains:
  - Add `debug` tool: The agent can set breakpoints, inspect variables, evaluate expressions and control execution flow
    by directly interacting with the IDE's debugger, using a REPL-style interface for maximum flexibility.  
  - `move` and `safe_delete` tools: transform empty string to None (counteracts client errors)

* Dependencies:
  - `pywebview`: Switch back to official release (new version 6.2) #1253
  - `mcp`: Update from `1.26.0` to `1.27.0`

* Evaluations:
  - Added new evaluations for Junie Plugin with Opus 4.6 and GLM 5.1 in Claude Code.

* Language Servers:
  - Fix: clangd capability checks now tolerate valid initialize response shape differences and invalidate cached C++ document symbols when clangd/compile commands context changes #1359                                                                                                                                                                                                            
  - Fix: `rename_symbol` for Vue files now correctly propagates edits to the TypeScript server, enabling cross-file renames in `.vue` files 
  - Fix: Lean4 stale cache — empty document symbol responses (returned before `lake build` completes) are no longer persisted, preventing symbols from being permanently hidden #1356
  - Add JSON language server support via `vscode-json-languageserver` (experimental) #1391
  - Fix: Elixir/Expert deadlock on startup — Expert's build pipeline requires a `textDocument/didOpen` notification to start; Serena now opens `mix.exs` immediately after `initialized` so Expert begins compiling instead of waiting indefinitely #1397

* Dashboard:
  - Add configurable dashboard interface mode (new global configuration setting `web_dashboard_interface`):
    Three modes (browser, native app with tray, tray manager for aggregating multiple instances) are supported, depending on the OS
  - Fix: Memory leaks in frontend when using Chromium-based browsers/Windows webview #1389

* Hooks:
  - Adjusted wording of startup hook, improving project activation instructions #1401.

# v1.1.2 (2026-04-14)

* General:
  - Support environment variable `SERENA_USAGE_REPORTING` (set to `false` to disable usage reporting)
  - Extended the list of always ignored directories (by language servers) with common cases.
  - Improve exposed toolset: With mode switching no longer being a feature, we now fully apply tool exclusions 
    defined by modes when in a single-project context (limiting exposed tools to a minimum)
  - Fix: When scanning for `.gitignore` files, the presence of files that could not be made relative 
    to the project root would cause the scan to fail. #1317

* Dashboard:
  - Fix handling of read news, saving each read news entry separately #1338

* JetBrains: 
  - Improve handling of `relative_path` parameter 
     - Improve its documentation to avoid usage errors
     - Replace escaped characters in `relative_path` with their unescaped counterparts (&lt; and &gt;)
     - `FindSymbolTool`: Force `search_deps=True` if `relative_path` pertains to external dependencies.

* Language Servers:
  - Add mSL (mIRC Scripting Language) support (custom pygls-based language server; symbols, references, definitions)
  - Fix initialisation issues in Vue language server #1333

# v1.1.1 (2026-04-12)

* General:
  - Enable cert verification for HTTPS request to oraios-software.de #1320

* JetBrains:
  - `JetBrainsRenameTool` can now also rename occurrences in comments and text.

* Language Servers:
  - Fix Dart LSP returning only symbol name as body instead of full method body.


# v1.1.0 (2026-04-11)

* General:
  - **Major**: Add commands for hooks and documentation of recommended setup. Consider setting up the [recommended hooks](https://oraios.github.io/serena/02-usage/030_clients.html) !
  - Add `serena init` and `serena setup` commands
  - Rework installation instructions, switching to releases on pypi for distribution. Please update your mcp startup commands!
  - Add minimal usage data collection on startup (only Serena version, language backend, OS, dashboard enabled status; no personally identifiable information)
  - Fix: git commit id in Serena version strings was incorrect

* Language Servers:
  - Add support for Haxe via vshaxe/haxe-language-server. Requires Haxe compiler 3.4.0+ and Node.js. Auto-discovered from the vshaxe VSCode extension or configurable via `ls_path` in `ls_specific_settings`.
  - Add Crystal language support (uses [Crystalline](https://github.com/elbywan/crystalline) language server)
  - Fix: Reactivation of the same project restarted language servers #1280

* JetBrains:
  - `JetBrainsFindReferencingSymbolTool`: Include context lines (when using plugin version 2023.2.15+)

* Dashboard:
  - Add version display
  - Fix: Dashboard viewer (Windows): Add a parent monitoring thread to ensure termination.
    Some clients would terminate the MCP server in a way that did not ensure proper termination.
  - Fix: Manual server shutdown triggered by GUI tool/dashboard not cleaning everything up.

# v1.0.0 (2026-04-03)

* General:
    * Add monorepo/multi-language support
        * Project configuration files (`project.yml`) can now define multiple languages.
          Auto-detection adds only the most prominent language by default.
        * Additional languages can be conveniently added via the Dashboard while a project is already activated.
    * Add support for querying projects other than the currently active one via new tools `QueryProjectTool` and `ListQueryableProjectsTool`.
      The `QueryProjectTool` allows Serena tools to be called on other projects.
        * For the LSP backend, calling symbolic tools require a project server to be spawned that will launch the respective language servers
        * For the JetBrains backend, all projects for which IDE instances are open can directly be queried
    * Support overloaded symbols in `FindSymbolTool` and related tools
        * Name paths of overloaded symbols now include an index (e.g., `myOverloadedFunction[2]`)
        * Responses of the Java language server, which handled this in its own way, are now adapted accordingly,
          solving several issues related to retrieval problems in Java projects
    * Major extensions to the dashboard, which now serves as a central web interface for Serena
        * View current configuration
        * View news which can be marked as read
        * View the executions, with the possibility to cancel running/scheduled executions
        * View tool usage statistics
        * View and create memories and edit the serena configuration file
        * Log page now has save (downloads a snapshot) and clear (resets log view) buttons alongside the existing copy button
    * Language server backend:
        * New two-tier caching of language server document symbols and considerable performance improvements surrounding symbol retrieval/indexing
        * Allow passing language server-specific settings through `ls_specific_settings` field (in `serena_config.yml`)
    * Add the JetBrains language backend as an alternative to language servers
    * Improve management of Serena projects
        * Facilitate project activation based on the current directory (through the `--project-from-cwd` parameter)
        * Add notion of a "single-project context" (flag `single_project`), allowing user-defined contexts to behave
          like the built-in `ide-assistant` context (where the available tools are restricted to ones required by the active
          project and project changes are disabled)
        * The location of Serena's project-specific data folder can now be flexibly configured, allowing, in particular,
          locations outside of the project folder, thus improving support for read-only projects.
        * Add support for `project.local.yml` for local overrides that should not be versioned 
    * Various fixes related to indexing, special paths and determination of ignored paths
    * Memories:
        * Add support for global memories (shared across projects) 
        * Add `read_only_memory_patterns` configuration option
        * Add `ignored_memory_patterns` configuration option
    * Improved client support, e.g. new mode `oaicompat-agent` and extensions enhancing OpenAI tool compatibility

* Tools:
  * Additional symbol meta-information (hover, docstring, quick-info) is now provided as part of `find_symbol` and related tool responses.
  * Added `QueryProjectTool` and `ListQueryableProjectTool` (see above)
  * Added `RenameSymbolTool` for renaming symbols across the codebase (if LS supports this operation).
  * Replaced `ReplaceRegexTool` with `ReplaceContentTool`, which supports both plain text and regex-based replacements
    (and which requires no escaping in the replacement text, making it more robust)
  * Add JetBrains tools which leverage the corresponding JetBrains language backend through our plugin
  * Decreased `TOOL_DEFAULT_MAX_ANSWER_LENGTH` to be in accordance with (below) typical max-tokens configurations

* Language support:

  * **Add support for Lean 4** via built-in `lean --server` with cross-file reference support (requires `lean` and `lake` via [elan](https://github.com/leanprover/elan))
  * **Add support for OCaml** via ocaml-lsp-server with cross-file reference support on OCaml 5.2+ (requires opam; see [setup guide](docs/03-special-guides/ocaml_setup_guide_for_serena.md))
  * **Add Phpactor as alternative PHP language server** (specify `php_phpactor` as language; requires PHP 8.1+)
  * **Add support for Fortran** via fortls language server (requires `pip install fortls`)
  * **Add partial support for Groovy** requires user-provided Groovy language server JAR (see [setup guide](docs/03-special-guides/groovy_setup_guide_for_serena.md))
  * **Add support for Julia** via LanguageServer.jl
  * **Add support for Haskell** via Haskell Language Server (HLS) with automatic discovery via ghcup, stack, or system PATH; supports both Stack and Cabal projects
  * **Add support for Scala** via Metals language server (requires some [manual setup](docs/03-special-guides/scala_setup_guide_for_serena.md))
  * **Add support for F#** via FsAutoComplete/Ionide LSP server. 
  * **Add support for Elm** via @elm-tooling/elm-language-server (automatically downloads if not installed; requires Elm compiler)
  * **Add support for Perl** via Perl::LanguageServer with LSP integration for .pl, .pm, and .t files
  * **Add support for AL (Application Language)** for Microsoft Dynamics 365 Business Central development. Requires VS Code AL extension (ms-dynamics-smb.al).
  * **Add support for R** via the R languageserver package with LSP integration, performance optimizations, and fallback symbol extraction
  * **Add support for Zig** via ZLS (cross-file references may not fully work on Windows)
  * **Add support for Lua** via lua-language-server
  * **Add support for Nix** requires nixd installation (Windows not supported)
  * **Add experimental support for YAML** via yaml-language-server with LSP integration for .yaml and .yml files
  * **Add support for TOML** via Taplo language server with automatic binary download, validation, formatting, and schema support for .toml files
  * **Dart now officially supported**: Dart was always working, but now tests were added, and it is promoted to "officially supported"
  * **Rust now uses already installed rustup**: The rust-analyzer is no longer bundled with Serena. Instead, it uses the rust-analyzer from your Rust toolchain managed by rustup. This ensures compatibility with your Rust version and eliminates outdated bundled binaries.
  * **Kotlin now officially supported**: We now use the official Kotlin LS, tests run through and performance is good, even though the LS is in an early development stage.
  * **Add support for Erlang** experimental, may hang or be slow, uses the recently archived [erlang_ls](https://github.com/erlang-ls/erlang_ls)
  * **Ruby dual language server support**: Added ruby-lsp as the modern primary Ruby language server. Solargraph remains available as an experimental legacy option. ruby-lsp supports both .rb and .erb files, while Solargraph supports .rb files only.
  * **Add support for PowerShell** via PowerShell Editor Services (PSES). Requires `pwsh` (PowerShell Core) to be installed and available in PATH. Supports symbol navigation, go-to-definition, and within-file references for .ps1 files.
  * **Add support for MATLAB** via the official MathWorks MATLAB Language Server. Requires MATLAB R2021b or later and Node.js. Set `MATLAB_PATH` environment variable or configure `matlab_path` in `ls_specific_settings`. Supports .m, .mlx, and .mlapp files with code completion, diagnostics, go-to-definition, find references, document symbols, formatting, and rename.
  * **Add support for Pascal** via the official Pascal Language Server.
  * **C/C++ alternate LS (ccls)**: Add experimental, opt-in support for ccls as an alternative backend to clangd. Enable via `cpp_ccls` in project configuration. Requires `ccls` installed and ideally a `compile_commands.json` at repo root.
  * **Add support for Solidity** via the Nomic Foundation `@nomicfoundation/solidity-language-server` (automatically installed via npm)

# v0.1.4 (2025-08-15)

## Summary

This likely is the last release before the stable version 1.0.0 which will come together with the jetbrains IDE extension.
We release it for users who install Serena from a tag, since the last tag cannot be installed due to a breaking change in the mcp dependency (see #381).

Since the last release, several new languages were supported, and the Serena CLI and configurability were significantly extended.
We thank all external contributors who made a lot of the improvements possible!

* General:
  * **Initial instructions no longer need to be loaded by the user**
  * Significantly extended CLI
  * Removed `replace_regex` tool from `ide-assistant` and `codex` contexts.
    The current string replacement tool in Claude Code seems to be sufficiently efficient and is better
    integrated with the IDE. Users who want to enable `replace_regex` can do so by customizing the context.

* Configuration:
  * Simplify customization of modes and contexts, including CLI support.
  * Possibility to customize the system prompt and outputs of simple tools, including CLI support.
  * Possibility to override tool descriptions through the context YAML.
  * Prompt templates are now automatically adapted to the enabled tools.
  * Several tools are now excluded by default, need to be included explicitly.
  * New context for ChatGPT

* Language servers:
  * Reliably detect language server termination and propagate the respective error all the way
    back to the tool application, where an unexpected termination is handled by restarting the language server
    and subsequently retrying the tool application.
  * **Add support for Swift**
  * **Add support for Bash**
  * Enhance Solargraph (Ruby) integration
    * Automatic Rails project detection via config/application.rb, Rakefile, and Gemfile analysis
    * Ruby/Rails-specific exclude patterns for improved indexing performance (vendor/, .bundle/, tmp/, log/, coverage/)
    * Enhanced error handling with detailed diagnostics and Ruby manager-specific installation instructions (rbenv, RVM, asdf)
    * Improved LSP capability negotiation and analysis completion detection
    * Better Bundler and Solargraph installation error messages with clear resolution steps

Fixes:
* Ignore `.git` in check for ignored paths and improve performance of `find_all_non_ignored_files`
* Fix language server startup issues on Windows when using Claude Code (which was due to
  default shell reconfiguration imposed by Claude Code)
* Additional wait for initialization in C# language server before requesting references, allowing cross-file references to be found.

# v0.1.3 (2025-07-22)

## Summary

This is the first release of Serena to pypi. Since the last release, we have greatly improved 
stability and performance, as well as extended functionality, improved editing tools and included support for several new languages. 

* **Reduce the use of asyncio to a minimum**, improving stability and reducing the need for workarounds
   * Switch to newly developed fully synchronous LSP library `solidlsp` (derived from `multilspy`),
     removing our fork of `multilspy` (src/multilspy)
   * Switch from fastapi (which uses asyncio) to Flask in the Serena dashboard
   * The MCP server is the only asyncio-based component now, which resolves cross-component loop contamination,
     such that process isolation is no longer required.
     Neither are non-graceful shutdowns on Windows.
* **Improved editing tools**: The editing logic was simplified and improved, making it more robust.
   * The "minimal indentation" logic was removed, because LLMs did not understand it.
   * The logic for the insertion of empty lines was improved (mostly controlled by the LLM now)
* Add a task queue for the agent, which is executed in a separate and thread and
   * allows the language server to be initialized in the background, making the MCP server respond to requests
     immediately upon startup,
   * ensures that all tool executions are fully synchronized (executed linearly).
* `SearchForPatternTool`: Better default, extended parameters and description for restricting the search
* Language support:
   * Better support for C# by switching from `omnisharp` to Microsoft's official C# language server.
   * **Add support for Clojure, Elixir and Terraform. New language servers for C# and typescript.**
   * Experimental language server implementations can now be accessed by users through configuring the `language` field
* Configuration:
   * Add option `web_dashboard_open_on_launch` (allowing the dashboard to be enabled without opening a browser window) 
   * Add options `record_tool_usage_stats` and `token_count_estimator`
   * Serena config, modes and contexts can now be adjusted from the user's home directory.
   * Extended CLI to help with configuration
* Dashboard:
  * Displaying tool usage statistics if enabled in the config

Fixes:
* Fix `ExecuteShellCommandTool` and `GetCurrentConfigTool` hanging on Windows
* Fix project activation by name via `--project` not working (was broken in previous release) 
* Improve handling of indentation and newlines in symbolic editing tools
* Fix `InsertAfterSymbolTool` failing for insertions at the end of a file that did not end with a newline
* Fix `InsertBeforeSymbolTool` inserting in the wrong place in the absence of empty lines above the reference symbol
* Fix `ReplaceSymbolBodyTool` changing whitespace before/after the symbol
* Fix repository indexing not following links and catch exceptions during indexing, allowing indexing
  to continue even if unexpected errors occur for individual files.
* Fix `ImportError` in Ruby language server.
* Fix some issues with gitignore matching and interpreting of regexes in `search_for_pattern` tool.

# 2025-06-20

* **Overhaul and major improvement of editing tools!**
  This represents a very important change in Serena. Symbols can now be addressed by their `name_path` (including nested ones)
  and we introduced a regex-based replaced tools. We tuned the prompts and tested the new editing mechanism.
  It is much more reliable, flexible, and at the same time uses fewer tokens.
  The line-replacement tools are disabled by default and deprecated, we will likely remove them soon.
* **Better multi-project support and zero-config setup**: We significantly simplified the config setup, you no longer need to manually
  create `project.yaml` for each project. Project activation is now always available. 
  Any project can now be activated by just asking the LLM to do so and passing the path to a repo.
* Dashboard as web app and possibility to shut down Serena from it (or the old log GUI).
* Possibility to index your project beforehand, accelerating Serena's tools.
* Initial prompt for project supported (has to be added manually for the moment)
* Massive performance improvement of pattern search tool
* Use **process isolation** to fix stability issues and deadlocks (see #170). 
  This uses separate process for the MCP server, the Serena agent and the dashboard in order to fix asyncio-related issues.

# 2025-05-24

* Important new feature: **configurability of mode and context**, allowing better integration in a variety of clients.
  See corresponding section in readme - Serena can now be integrated in IDE assistants in a more productive way. 
  You can now also do things like switching to one-shot planning mode, ask to plan something (which will create a memory),
  then switch to interactive editing mode in the next conversation and work through the plan read from the memory.
* Some improvements to prompts.

# 2025-05-21

**Significant improvement in symbol finding!**

* Serena core:
    * `FindSymbolTool` now can look for symbols by specifying paths to them, not just the symbol name
* Language Servers:
    * Fixed `gopls` initialization
    * Symbols retrieved through the symbol tree or through overview methods now are linked to their parents


# 2025-05-19

* Serena core:
    * Bugfix in `FindSymbolTool` (a bug fixed in LS)
    * Fix in `ListDirTool`: Do not ignore files with extensions not understood by the language server, only skip ignored directories
      (error introduced in previous version)
    * Merged the two overview tools (for directories and files) into a single one: `GetSymbolsOverviewTool`
    * One-click setup for Cline enabled
    * `SearchForPatternTool` can now (optionally) search in the entire project
    * New tool `RestartLanguageServerTool` for restarting the language server (in case of other sources of editing apart from Serena)
    * Fix `CheckOnboardingPerformedTool`:
        * Tool description was incompatible with project change
        * Returned result was not as useful as it could be (now added list of memories)

* Language Servers:
    * Add further file extensions considered by the language servers for Python (.pyi), JavaScript (.jsx) and TypeScript (.tsx, .jsx)
    * Updated multilspy, adding support for Kotlin, Dart and C/C++ and several improvements.
    * Added support for PHP
    

# 2025-04-07

> **Breaking Config Changes**: make sure to set `ignore_all_files_in_gitignore`, remove `ignore_dirs`
>  and (optionally) set `ignore_paths` in your project configs. See [updated config template](myproject.template.yml)

* Serena core:
    * New tool: FindReferencingCodeSnippets
    * Adjusted prompt in CreateTextFileTool to prevent writing partial content (see [here](https://www.reddit.com/r/ClaudeAI/comments/1jpavtm/comment/mloek1x/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button)).
    * FindSymbolTool: allow passing a file for restricting search, not just a directory (Gemini was too dumb to pass directories)
    * Native support for gitignore files for configuring files to be ignored by serena. See also
      in *Language Servers* section below.
    * **Major Feature**: Allow Serena to switch between projects (project activation)
        * Add central Serena configuration in `serena_config.yml`, which 
            * contains the list of available projects
            * allows to configure whether project activation is enabled
            * now contains the GUI logging configuration (project configurations no longer do)
        * Add new tools `activate_project` and `get_active_project`
        * Providing a project configuration file in the launch parameters is now optional
* Logging:
    * Improve error reporting in case of initialization failure: 
      open a new GUI log window showing the error or ensure that the existing log window remains visible for some time
* Language Servers:
    * Fix C# language server initialization issue when the project path contains spaces
    * Native support for gitignore in overview, document-tree and find_references operations.
      This is an **important** addition, since previously things like `venv` and `node_modules` were scanned
      and were likely responsible for slowness of tools and even server crashes (presumably due to OOM errors).
* Agno: 
    * Fix Agno reloading mechanism causing failures when initializing the sqlite memory database #8
    * Fix Serena GUI log window not capturing logs after initialization

# 2025-04-01

Initial public version
