# Language Support

Serena provides a set of versatile code querying and editing functionalities
based on symbolic understanding of the code across a wide range of programming languages.
Equipped with these capabilities, Serena discovers and edits code just like a seasoned developer
making use of an IDE's capabilities would.
Serena can efficiently find the right context and do the right thing even in very large and
complex projects!

There are two alternative technologies powering these capabilities:

* **Language servers** implementing the language server Protocol (LSP) — the free/open-source alternative.
* **The Serena JetBrains Plugin**, which leverages the powerful code analysis and editing
  capabilities of your JetBrains IDE.

See the [Features](025_features) section for a detailed comparison of the capabilities provided by the JetBrains Plugin vs. language servers.

(language-servers)=
## Language Servers

Serena incorporates a powerful abstraction layer for the integration of language servers 
that implement the language server protocol (LSP).
It even supports multiple language servers in parallel to support polyglot projects.

The language servers themselves are typically open-source projects (like Serena)
or at least freely available for use.

We currently provide direct, out-of-the-box support for the programming languages listed below.
Some languages require additional installations or setup steps, as noted.

### Ada / SPARK
  (uses AdaCore's [Ada Language Server (ALS)](https://github.com/AdaCore/ada_language_server),
  automatically downloaded; supports `.ads`, `.adb`, and `.ada` files;
  works best with a `.gpr` GNAT project file at the repository root;
  SPARK is handled by the same server transparently — set language `ada` for both.
  To use a pre-installed ALS (e.g. from Alire, GNAT Studio, or the VS Code Ada extension),
  set `ls_specific_settings.ada.ls_path`.)
### AL
  (uses the AL Language Server from Microsoft's [AL extension for VS Code](https://marketplace.visualstudio.com/items?itemName=ms-dynamics-smb.al) (`ms-dynamics-smb.al`), automatically downloaded from the VS Code Marketplace)
### Angular
  (experimental; uses the official [@angular/language-server](https://github.com/angular/angular/tree/main/vscode-ng-language-service) (ngserver), automatically installed via npm; requires Node.js + npm, plus `npm install` having been run in the project root so that `@angular/core`
  is resolvable — without it, template-aware features silently return empty;
  subsumes `typescript` and `html` for `.ts`/`.html` files, so do not also list those)
### Ansible
  (experimental; requires Node.js and npm; automatically installs [`@ansible/ansible-language-server`](https://github.com/ansible/vscode-ansible);
  must be explicitly specified in the `languages` entry in the `project.yml`; requires `ansible` in PATH for full functionality)
  the upstream `@ansible/ansible-language-server@1.2.3` supports hover, completion, definition,
  semantic tokens, and validation; document symbols, workspace symbols, references, and rename
  are not supported by this version)
### Bash
  (uses [bash-language-server](https://github.com/bash-lsp/bash-language-server), automatically installed via npm; requires Node.js and npm on PATH; a pinned ShellCheck binary is downloaded automatically)
### BSL (1C:Enterprise / OneScript)
  (requires Java 21+ on PATH; uses [bsl-language-server](https://github.com/1c-syntax/bsl-language-server) by 1c-syntax; the JAR is auto-downloaded and SHA-256-verified for the bundled default version; supports `.bsl` and `.os` files; configure optional `ls_path` or `bsl_ls_version` under `ls_specific_settings.bsl`)
### C#
  (by default, uses the [Roslyn language server](https://www.nuget.org/packages/roslyn-language-server) (language `csharp`), requiring [.NET v10+](https://dotnet.microsoft.com/en-us/download/dotnet) and, on Windows, `pwsh` ([PowerShell 7+](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows?view=powershell-7.5));
  set language to `csharp_omnisharp` to use OmiSharp instead)
### C/C++
  (by default, uses the [clangd](https://clangd.llvm.org/) language server (language `cpp`) but we also support [ccls](https://github.com/MaskRay/ccls) (language `cpp_ccls`);
  for best results, provide a `compile_commands.json` at the repository root;
  see the [C/C++ Setup Guide](../03-special-guides/cpp_setup) for details;
  for Unreal Engine 5 projects, see the [Unreal Engine Setup Guide](../03-special-guides/unreal_engine_setup_guide_for_serena).)
### Clojure
  (uses [clojure-lsp](https://github.com/clojure-lsp/clojure-lsp), automatically downloaded; requires the [Clojure CLI](https://clojure.org/guides/getting_started) to be installed)
### Crystal
  (requires [Crystalline](https://github.com/elbywan/crystalline) language server to be installed and available on PATH;
  note: Crystalline has limited go-to-definition support and does not support find-references)
### CUE
  (uses `cue lsp` from the official [cue](https://github.com/cue-lang/cue) binary, automatically downloaded)
### Dart
  (uses the [Dart SDK](https://dart.dev)'s built-in language server (`dart language-server`); the SDK is downloaded automatically)
### Elixir
  (requires Elixir installation; [Expert](https://github.com/elixir-lang/expert) language server is downloaded automatically)
### Elm
  (requires Elm compiler; uses [elm-language-server](https://github.com/elm-tooling/elm-language-server), installed automatically via npm)
### Erlang
  (requires installation of beam and [erlang_ls](https://github.com/erlang-ls/erlang_ls); experimental, might be slow or hang;
  note that functions are addressed as `name#arity`, e.g. `create_user#4`, because `/` is reserved as the name path separator)
### F#
  (requires [.NET v8.0+](https://dotnet.microsoft.com/en-us/download/dotnet); uses [FsAutoComplete](https://github.com/ionide/FsAutoComplete)/Ionide, which is auto-installed; for Homebrew .NET on macOS, set DOTNET_ROOT in your environment)
### Fortran
  (uses [fortls](https://github.com/fortran-lang/fortls), run automatically via `uvx`; requires `uv`/`uvx` in PATH)
### GDScript (Godot Engine)
  (requires the [Godot](https://godotengine.org) editor to be running with its built-in LSP enabled — default on port 6008;
  Serena connects over TCP and does not launch Godot itself;
  see the [GDScript Setup Guide](../03-special-guides/godot_gdscript_setup_guide_for_serena) for details)
### Gleam
  (requires the [Gleam compiler](https://gleam.run) on PATH; the language server is bundled with the compiler and started via `gleam lsp`)
### Go
  (requires installation of [`gopls`](https://pkg.go.dev/golang.org/x/tools/gopls))
### Groovy
  (requires local [groovy-language-server.jar](https://github.com/GroovyLanguageServer/groovy-language-server) setup via `GROOVY_LS_JAR_PATH` or configuration)
### Haskell
  (automatically locates [HLS](https://github.com/haskell/haskell-language-server) via ghcup, stack, or system PATH; supports Stack and Cabal projects)
### Haxe
  (requires Haxe compiler 3.4.0+ and Node.js; uses the [vshaxe language server](https://github.com/vshaxe/haxe-language-server);
  automatically downloaded from Open VSX, or discovered from the vshaxe VSCode extension)
### HLSL / GLSL / WGSL
  (uses [shader-language-server](https://github.com/antaalt/shader-sense) (language `hlsl`); automatically downloaded;
  on macOS, requires Rust toolchain for building from source;
  note: reference search is not supported by this language server)
### HTML
  (experimental; requires Node.js + npm; automatically installs [vscode-html-language-server](https://github.com/hrsh7th/vscode-langservers-extracted) via the `vscode-langservers-extracted` npm package)
### Java
  (uses Eclipse JDT LS via the [vscode-java](https://github.com/redhat-developer/vscode-java) extension bundle, automatically downloaded with a bundled JRE)
### JavaScript
  (supported via the [TypeScript language server](https://github.com/typescript-language-server/typescript-language-server), i.e. use language `typescript` for both JavaScript and TypeScript)
### Julia
  (requires a Julia installation; uses [LanguageServer.jl](https://github.com/julia-vscode/LanguageServer.jl), automatically installed via Pkg if missing)
### Kotlin
  (uses the pre-alpha [official kotlin LS](https://github.com/Kotlin/kotlin-lsp), some issues may appear)
### LaTeX
  (experimental; must be explicitly enabled via language `latex`; uses [texlab](https://github.com/latex-lsp/texlab),
  auto-downloaded as a SHA-256-verified prebuilt binary; supports `.tex`, `.bib`, `.sty`, and `.cls` files; texlab is
  GPL-3.0 and runs as a separate downloaded process)
### Lean 4
  (requires `lean` and `lake` installed via [elan](https://github.com/leanprover/elan); uses the built-in Lean 4 LSP;
  the project must be a Lake project with `lake build` run before use)
### Lua
  (uses [lua-language-server](https://github.com/LuaLS/lua-language-server), taken from PATH if present, otherwise downloaded automatically)
### Luau
  (uses [luau-lsp](https://github.com/JohnnyMorganz/luau-lsp), taken from PATH or automatically downloaded)
### Markdown
  (uses [Marksman](https://github.com/artempyanykh/marksman), automatically downloaded; must explicitly enable language `markdown`, primarily useful for documentation-heavy projects)
### MATLAB
  (requires Node.js and a licensed local MATLAB installation, R2021b or later; Serena automatically downloads version 1.3.9 of the VS Code MATLAB extension, which bundles the [MATLAB language server](https://github.com/mathworks/MATLAB-language-server))
### mSL (mIRC Scripting Language)
  (auto-installed; no external dependencies required — uses a custom pygls-based LSP server shipped with Serena;
  supports document symbols, workspace symbols, references, and go-to-definition for aliases, events, menus, dialogs, and CTCP handlers in `.mrc` files)
### Nextflow
  (uses the official [Nextflow language server](https://github.com/nextflow-io/language-server), which is automatically
  downloaded; requires a Java 17+ runtime, discovered via `ls_specific_settings.nextflow.java_home`, `JAVA_HOME` or `java` on PATH;
  covers `.nf` scripts — Nextflow `.config` files are not treated as source files, since the language server reports no symbols for them;
  processes, workflows and functions are reported under their declared name, e.g. `GREET` for `process GREET`)
### Nix
  (requires [nixd](https://github.com/nix-community/nixd) installation)
### OCaml
  (requires opam and [ocaml-lsp-server](https://github.com/ocaml/ocaml-lsp) to be installed manually; see the [OCaml Setup Guide](../03-special-guides/ocaml_setup_guide_for_serena.md))
### Pascal
  (uses the [Pascal/Lazarus language server (pasls)](https://github.com/zen010101/pascal-language-server), which is automatically downloaded; set `PP` and `FPCDIR` environment variables for source navigation)
### Perl
  (requires installation of [Perl::LanguageServer](https://metacpan.org/pod/Perl::LanguageServer))
### PHP
  (by default, uses the [Intelephense](https://intelephense.com) language server (language `php`), set `INTELEPHENSE_LICENSE_KEY` environment variable for premium features;
  we also support [Phpactor](https://github.com/phpactor/phpactor) (language `php_phpactor`), which requires PHP 8.1+;
  and the experimental [PHPantom](https://github.com/PHPantom-dev/phpantom_lsp) backend (language `php_phpantom`)
### PowerShell
  (requires PowerShell 7+ (`pwsh`) on PATH or in a standard install location; Serena automatically downloads [PowerShell Editor Services](https://github.com/PowerShell/PowerShellEditorServices) 4.4.0 and installs PSScriptAnalyzer 1.25.0 via `Save-Module` from your configured PowerShell repository)
### Python
  (by default, uses [Pyright](https://github.com/microsoft/pyright) (language `python`);
  alternatives: [BasedPyright](https://github.com/DetachHead/basedpyright) (language `python_basedpyright`),
  [ty](https://github.com/astral-sh/ty) (language `python_ty`),
  [pyrefly](https://github.com/facebook/pyrefly) (language `python_pyrefly`),
  [Jedi](https://github.com/pappasam/jedi-language-server) (language `python_jedi`);
  Pyright, BasedPyright, ty, and pyrefly require `uv`/`uvx` in PATH)
### QML
  (requires Qt 6, provides `qmlls` or `qmlls6` on PATH; see the [Qt qmlls documentation](https://doc.qt.io/qt-6/qtqml-tooling-qmlls.html))
### R
  (requires installation of the [`languageserver`](https://github.com/REditorSupport/languageserver) R package)
### Rego
  (requires the [Regal](https://github.com/open-policy-agent/regal) language server on PATH)
### Ruby
  (by default, uses [ruby-lsp](https://github.com/Shopify/ruby-lsp) (language `ruby`); use language `ruby_solargraph` to use Solargraph instead.)
### Rust
  (requires [rustup](https://rustup.rs/) - uses [rust-analyzer](https://github.com/rust-lang/rust-analyzer) from your toolchain)
### Scala
  (uses [Metals](https://scalameta.org/metals/) LSP, which imports the build on first use — see the [setup guide](../03-special-guides/scala_setup_guide_for_serena))
### SCSS / Sass / CSS
  (experimental; requires Node.js + npm; uses [some-sass-language-server](https://github.com/wkillerud/some-sass) to handle
  `.scss`, `.sass`, and `.css`)
### Solidity
  (experimental; requires Node.js and npm; automatically installs [`@nomicfoundation/solidity-language-server`](https://github.com/NomicFoundation/hardhat-vscode);
  works best with a `foundry.toml` or `hardhat.config.js` in the project root)
### Svelte
  (requires Node.js v18+ and npm; supports `.svelte` Single File Components plus TypeScript/JavaScript files via [`svelte-language-server`](https://github.com/sveltejs/language-tools); a companion `typescript-language-server` + `typescript-svelte-plugin` is spawned automatically for cross-file rename, go-to-definition, and references across `.ts`/`.js` and `.svelte` files; use language `svelte` for Svelte projects instead of also enabling `typescript`)
### Swift
  (uses [sourcekit-lsp](https://github.com/apple/sourcekit-lsp), which must be installed and available on your PATH)
### SystemVerilog
  (uses [`verible-verilog-ls`](https://github.com/chipsalliance/verible), taken from PATH if present, otherwise version `v0.0-4051-g9fdb4057` is downloaded automatically)
### Terraform
  (uses [`terraform-ls`](https://github.com/hashicorp/terraform-ls) 0.36.5, which Serena downloads automatically; requires Terraform on PATH)
### TOML
  (experimental; uses [Taplo](https://github.com/tamasfe/taplo) 0.10.0, taken from PATH if present, otherwise downloaded automatically)
### TypeScript
  (uses [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server) together with the `typescript` package, both installed automatically via npm; requires Node.js and npm)
### Deno
  (experimental; requires the [`deno` CLI](https://docs.deno.com/runtime/getting_started/installation/) on PATH — it bundles the language server used here;
  serves Deno TypeScript/JavaScript and understands `npm:` / `jsr:` / `https:` imports and the `Deno.*`
  globals, which the plain TypeScript language server does not; overlaps `typescript` on file extensions,
  so it is not auto-detected and must be set as the language explicitly — do not also enable `typescript`
  for the same files)
### Vue
  (3.x with TypeScript; uses [`@vue/language-server`](https://github.com/vuejs/language-tools) (Volar), installed automatically via npm; requires Node.js v18+ and npm; supports .vue Single File Components with monorepo detection)
### Wolfram Language
  (requires Wolfram Mathematica 13.0+ or Wolfram Engine 12.1+; uses the official [WolframResearch LSPServer](https://github.com/WolframResearch/LSPServer) paclet; supports .wl and .wls files; references are within-file only)
### YAML
  (experimental; uses [yaml-language-server](https://github.com/redhat-developer/yaml-language-server) (Red Hat), installed automatically via npm; requires Node.js and npm)
### JSON
  (experimental; uses `vscode-json-languageserver` (Microsoft), installed automatically via npm; must be explicitly added to the languages list; requires Node.js and npm)
### Zig
  (requires installation of [ZLS](https://github.com/zigtools/zls) - Zig Language Server)

Support for further languages can easily be added by providing a shallow adapter for a new language server implementation,
see Serena's [memory on that](https://github.com/oraios/serena/blob/main/.serena/memories/adding_new_language_support_guide.md).

## The Serena JetBrains Plugin

The [Serena JetBrains Plugin](https://plugins.jetbrains.com/plugin/28946-serena/) leverages the powerful code analysis capabilities of JetBrains IDEs. 
The plugin naturally supports all programming languages and frameworks that are supported by JetBrains IDEs.

When using the plugin, Serena connects to an instance of your JetBrains IDE via the plugin. For users who already
work in a JetBrains IDE, this means Serena seamlessly integrates with the IDE instance you typically have open anyway,
requiring no additional setup or configuration beyond the plugin itself.

* See the [JetBrains Plugin documentation](../02-usage/025_jetbrains_plugin) for a high-level overview of its benefits and usage details.
* See the [Features](025_features) section for a detailed comparison of the capabilities provided by the JetBrains Plugin vs. language servers.

```{raw} html
<p>
<a href="https://plugins.jetbrains.com/plugin/28946-serena/">
<img style="background-color:transparent;" src="../_static/images/jetbrains-marketplace-button.png">
</a>
</p>
```
