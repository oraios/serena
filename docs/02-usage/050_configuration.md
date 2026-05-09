# Configuration

Serena is very flexible in terms of configuration. While for most users, the default configurations will work,
you can fully adjust it to your needs.

You can disable tools, change Serena's fundamental instructions
(what we denote as the `system_prompt`), adjust the output of tools that just provide a prompt, 
and even adjust tool descriptions.

Serena is configured in using a multi-layered approach:

 * **global configuration** (`serena_config.yml`, see below)
 * **project configuration** (`project.yml`, see [Project Configuration](project-config))
 * **contexts and modes** for composable configuration, which can be enabled on a case-by-case basis (see below)
 * **command-line parameters** passed to the `start-mcp-server` server command (overriding/extending configured settings)  
   See [MCP Server Command-Line Arguments](mcp-args) for further information.  

(global-config)=
## Global Configuration

The global configuration file allows you to change general settings and defaults that will apply to all projects unless overridden.

### Settings

Some of the configurable settings include:
  * the language backend to use by default (i.e., the JetBrains plugin or language servers);
    this can also be [overridden per project](per-project-language-backend)
  * UI settings affecting the [Serena Dashboard and GUI tool](060_dashboard.md)
  * the set of tools to enable/disable by default
  * the set of modes to use by default
  * tool execution parameters (timeout, max. answer length)
  * global ignore rules
  * logging settings
  * advanced settings specific to individual language servers (see [below](ls-specific-settings))

The global configuration settings apply to all projects.
Some of the settings it contains can, however, be *extended* or *overridden* in project-specific settings, contexts and modes.

For detailed information on the parameters and possible settings, see the
[template file](https://github.com/oraios/serena/blob/main/src/serena/resources/serena_config.template.yml).

### Accessing the Configuration File

The configuration file is auto-created when you first run Serena. It is stored in your user directory:
  * Linux/macOS/Git-Bash: `~/.serena/serena_config.yml`
  * Windows (CMD/PowerShell): `%USERPROFILE%\.serena\serena_config.yml`

You can access it
  * through [Serena's dashboard](060_dashboard) while Serena is running (use the respective button) 
  * directly, using your favourite text editor
  * using the command

    ```shell
    serena config edit
    ```

## Modes and Contexts

Serena's behaviour and toolset can be adjusted using contexts and modes.
These allow for a high degree of customization to best suit your workflow and the environment Serena is operating in.

(contexts)=
### Contexts

A **context** defines the general environment in which Serena is operating.
It influences the initial system prompt and the set of available tools.
A context is set at startup when launching Serena (e.g., via CLI options for an MCP server or in the agent script) and cannot be changed during an active session.

Serena comes with pre-defined contexts:

* `desktop-app`: Tailored for use with desktop applications like Claude Desktop. This is the default.
  The full set of Serena's tools is provided, as the application is assumed to have no prior coding-specific capabilities.
* `claude-code`: Optimized for use with Claude Code, it disables tools that would duplicate Claude Code's built-in capabilities.
* `codex`: Optimized for use with OpenAI Codex.
* `ide`: Generic context for IDE assistants/coding agents, e.g. VSCode, Cursor, or Cline, focusing on augmenting existing capabilities.
  Basic file operations and shell execution are assumed to be handled by the assistant's own capabilities.
* `agent`: Designed for scenarios where Serena acts as a more autonomous agent, for example, when used with Agno.

Choose the context that best matches the type of integration you are using.

Find the concrete definitions of the above contexts [here](https://github.com/oraios/serena/tree/main/src/serena/resources/config/contexts).

Note that the contexts `ide` and `claude-code` are **single-project contexts** (defining `single_project: true`).
For such contexts, if a project is provided at startup, the set of tools is limited to those required by the project's
concrete configuration, and other tools are excluded completely, allowing the set of tools to be minimal.
Tools explicitly disabled by the project will not be available at all. Since changing the active project
ceases to be a relevant operation in this case, the project activation tool is disabled.

When launching Serena, specify the context using `--context <context-name>`.
Note that for cases where parameter lists are specified (e.g. Claude Desktop), you must add two parameters to the list.

If you are using a local server (such as Llama.cpp) which requires you to use OpenAI-compatible tool descriptions, use context `oaicompat-agent` instead of `agent`.

You can manage contexts using the `context` command,

    serena context --help
    serena context list
    serena context create <context-name>
    serena context edit <context-name>
    serena context delete <context-name>


(modes)=
### Modes

Modes further refine Serena's behavior for specific types of tasks or interaction styles. Multiple modes can be active simultaneously, allowing you to combine their effects. Modes influence the system prompt and can also alter the set of available tools by excluding certain ones.

Examples of built-in modes include:

* `planning`: Focuses Serena on planning and analysis tasks.
* `editing`: Optimizes Serena for direct code modification tasks.
* `interactive`: Suitable for a conversational, back-and-forth interaction style.
* `one-shot`: Configures Serena for tasks that should be completed in a single response, often used with `planning` for generating reports or initial plans.
* `no-onboarding`: Skips the initial onboarding process if it's not needed for a particular session but retains the memory tools (assuming initial memories were created externally).
* `onboarding`: Focuses on the project onboarding process.
* `no-memories`: Disables all memory tools (and tools building on memories such as onboarding tools)
* `query-projects`: Enables tools for querying other Serena projects (without activating them); see section [Reading from External Projects](query-projects) 

Find the concrete definitions of these modes [here](https://github.com/oraios/serena/tree/main/src/serena/resources/config/modes).

The modes to be activated are configured in:
  * the global configuration file (`serena_config.yml`)
     - defines `base_modes`, which are always included
     - defines `default_modes`, which can be overridden by projects or command line parameters
  * the project configuration file (`project.yml`)
     - defines `default_modes` (overriding the default modes in the global configuration)
     - defines `added_modes`, which are added on top
  * at startup via command-line parameters
     - can override default modes with `--mode`
     - can define modes to be added on top with `--add-mode`

Ultimately, the active modes are given by the union of 
  * `base_modes` defined in the global configuration (always active)  
  * `default_modes` (defined in the global configuration, optionally overridden by the project/CLI)
  * `added_modes` (defined in the project configuration/via CLI parameters)

So you should 
 * define modes you definitely always want to use in `base_modes`,
 * define modes that you typically want to use but sometimes want to override in `default_modes`,
 * use `added_modes` to add modes that you need only for specific projects/sessions.

:::{note}
**Mode Compatibility**: While you can combine modes, some may be semantically incompatible (e.g., `interactive` and `one-shot`). 
Serena currently does not prevent incompatible combinations; it is up to the user to choose sensible mode configurations.
:::

You can manage modes using the `mode` command,

    serena mode --help
    serena mode list
    serena mode create <mode-name>
    serena mode edit <mode-name>
    serena mode delete <mode-name>

## Advanced Configuration

For advanced users, Serena's configuration can be further customized.

### Serena Data Directory

The Serena user data directory (where configuration, language server files, logs, etc. are stored) defaults to `~/.serena`.
You can change this location by setting the `SERENA_HOME` environment variable to your desired path.

### Per-Project Serena Folder Location

By default, each project stores its Serena data (memories, caches, etc.) in a `.serena` folder inside the project root.
You can customize this location globally via the `project_serena_folder_location` setting in `serena_config.yml`.

The setting supports two placeholders:

| Placeholder          | Description                                     |
|----------------------|-------------------------------------------------|
| `$projectDir`        | The absolute path to the project root directory |
| `$projectFolderName` | The name of the project folder                  |

**Examples:**

```yaml
# Default: data stored inside the project directory
project_serena_folder_location: "$projectDir/.serena"

# Central location: all project data under a shared directory
project_serena_folder_location: "/projects-metadata/$projectFolderName/.serena"
```

When a project is loaded, Serena uses the following fallback logic:
1. Check if a `.serena` folder exists at the configured path.
2. If not, check if one exists in the project root (default/legacy location).
3. If neither exists, create the folder at the configured path.

This ensures backward compatibility: existing projects that already have a `.serena` folder in the project root will continue to work, even after changing the `project_serena_folder_location` setting.

(ls-specific-settings)=
### Language Server-Specific Settings

:::{note} 
**Advanced Users Only**: The settings described in this section are intended for advanced users who need to fine-tune language server behavior.
Most users will not need to adjust these settings.
:::

Under the key `ls_specific_settings` in `serena_config.yml`, you can you pass global per-language, 
language server-specific configuration. You can use the same key in the project configuration files (`project.yml`
and `project.local.yml` ) to override or extend the global settings for a specific project.
The settings are merged on top-level, meaning that project-level settings for a language will replace global settings for the same language.

Structure:

```yaml
ls_specific_settings:
  <language>:
    # language-server-specific keys
```

(override-ls-path)=
#### Overriding the Language Server Path

Most of Serena's language servers, particularly those that use a single core path for the language server (e.g. the main executable),
support overriding that path via the `ls_path` setting.
Therefore, if you have installed the language server yourself and want to use your installation 
instead of Serena's managed installation, you can set the `ls_path` setting as follows:

```yaml
ls_specific_settings:
  <language>:
    ls_path: "/path/to/language-server"
```

This is supported by all language servers deriving their dependency provider from `LanguageServerDependencyProviderSinglePath`,
and by some additional wrappers that explicitly expose `ls_path`.
Common examples include: `ansible`, `bash`, `bsl`, `clojure`, `cpp`, `cpp_ccls`, `hlsl`, `html`, `kotlin`, `lean4`, `luau`, `markdown`, `php`,
`php_phpactor`, `python`, `rust`, `scss`, `solidity`, `systemverilog`, `toml`, `typescript`, and `yaml`.

Note: `angular` does **not** support `ls_path` — the Angular language server is part of a multi-process orchestration
(`ngserver` plus a companion TypeScript language server with the `@angular/language-service` plugin and an HTML
companion) where the dependency layout matters; use the version overrides documented in the Angular section below
to pin specific releases of the bundled stack.

If a language server supports `ls_path`, setting it bypasses Serena's managed download or install for that server.
In that case, any server-specific version or registry settings only apply when `ls_path` is not set.

#### AL

Serena uses the AL language server bundled in the Microsoft Dynamics 365 Business Central VS Code extension.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `al_extension_version` | `18.0.2242655` | Override the AL VS Code extension version Serena downloads from the VS Code Marketplace. |

#### Angular

Serena uses `@angular/language-server` (`ngserver`) for the `angular` language key, orchestrated together with a
companion `typescript-language-server` (with `@angular/language-service` loaded as a tsserver plugin) and a
companion `vscode-html-language-server` for `.html` `documentSymbol`. This is an **experimental** language and
must be explicitly listed in `project.yml`; it is not auto-detected.

**Project requirements:**

- The project itself must have `@angular/core` installed (i.e. `npm install` must have been run in the project root,
  or in a workspace root above it for monorepo layouts). Without it, `ngserver` reports every file as "not in an
  Angular project" and template-aware features silently return empty.
- A `tsconfig.json` must be reachable at or above any opened `.ts` file.
- Do **not** also list `typescript` or `html` in `languages` when `angular` is active — Angular subsumes both
  for `.ts` / `.html` files. SCSS is **not** subsumed; list `scss` separately if needed.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `angular_language_server_version` | `21.2.10` | Override the bundled `@angular/language-server` npm package version Serena installs. |
| `angular_language_service_version` | `21.2.10` | Override the bundled `@angular/language-service` tsserver plugin version. |
| `typescript_version` | `5.9.3` | Override the bundled `typescript` npm package version. Falls back to `ls_specific_settings.typescript.typescript_version` if unset. |
| `typescript_language_server_version` | `5.1.3` | Override the bundled `typescript-language-server` version. Falls back to `ls_specific_settings.typescript.typescript_language_server_version` if unset. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. Falls back to `ls_specific_settings.typescript.npm_registry` if unset. |

Notes:
- The HTML companion (`vscode-html-language-server`) is configured via `ls_specific_settings.html` — see the HTML section below.
- `ls_path` is not supported (see note above the AL section).

#### Ansible

Serena uses `@ansible/ansible-language-server` for the `ansible` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install | Override the `ansible-language-server` executable path. |
| `ansible_language_server_version` | `1.2.3` | Override the npm package version Serena installs when `ls_path` is not set. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |
| `ansible_path` | `"ansible"` | Path to the `ansible` executable forwarded to the language server. |
| `ansible_settings` | `null` | Full Ansible LS settings dict, deep-merged on top of Serena's defaults. |
| `lint_enabled` | `false` | Enable `ansible-lint` integration. |
| `lint_path` | `"ansible-lint"` | Path to the `ansible-lint` executable. |
| `python_interpreter_path` | `"python3"` | Python interpreter path forwarded to the language server. |
| `python_activation_script` | `""` | Virtualenv activation script forwarded to the language server. |

#### Bash

Serena uses `bash-language-server` for Bash support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install | Override the `bash-language-server` executable path. |
| `bash_language_server_version` | `5.6.0` | Override the npm package version Serena installs when `ls_path` is not set. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |

#### BSL (1C:Enterprise / OneScript)

Serena uses [bsl-language-server](https://github.com/1c-syntax/bsl-language-server) by 1c-syntax
for BSL support. The JAR is downloaded automatically on first use and SHA-256-verified for the
bundled default version. **Requires Java 21+ on `PATH`** — bsl-language-server v0.29.0 is built
with `targetCompatibility = JavaVersion.VERSION_21` and fails to launch under older JDKs.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed download | Override the path to an existing `bsl-language-server-*-exec.jar`. When set, Serena does not download anything; the JAR is launched directly via `java -jar`. |
| `bsl_ls_version` | `0.29.0` | Override the bsl-language-server release version Serena downloads when `ls_path` is not set. SHA-256 verification is performed only for the default version; user-overridden versions install without SHA verification. |

Example:

```yaml
ls_specific_settings:
  bsl:
    bsl_ls_version: "0.29.0"
    # ls_path: "/opt/bsl/bsl-language-server-0.29.0-exec.jar"  # optional
```

#### Clojure

Serena uses `clojure-lsp` for Clojure support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed download | Override the `clojure-lsp` executable path. |
| `clojure_lsp_version` | `2026.02.20-16.08.58` | Override the `clojure-lsp` release version Serena downloads when `ls_path` is not set. |
| `source_paths` | scanned from project descriptors (or unset if a project-local `.lsp/config.edn` is found) | Explicit list of repo-root-relative source paths to inject into clojure-lsp's `initializationOptions`. Use this when the auto-discovery picks up too few or too many paths. |
| `config_edn_path` | unset | Path to a `config.edn` file whose `:source-paths` entry should be parsed and injected. Useful when the project's clojure-lsp config lives outside the standard `.lsp/config.edn` location. |

**Why this exists**: clojure-lsp discovers source paths only from the project descriptor at the workspace root (root `deps.edn` / `project.clj` / `shadow-cljs.edn` / `bb.edn`) and does not recurse for sub-module descriptors. In multi-module monorepos (e.g. `common/` + `frontend/` + `backend/` layouts), this means references in sibling modules are silently missed by `find_referencing_symbols` until a tool call happens to open one of their files. Serena works around this by walking the repo for project descriptors at startup and passing the union of their declared source paths to clojure-lsp via `initializationOptions["source-paths"]`.

**Resolution order** (first match wins):

1. `source_paths` setting — explicit override.
2. `config_edn_path` setting — Serena parses `:source-paths` from the supplied file.
3. `<repo>/.lsp/config.edn` exists — Serena injects nothing; clojure-lsp reads the file natively, so hand-tuned project configs are never clobbered.
4. Walk the repo for project descriptors and synthesise a source-paths list from their declared `:paths` / `:extra-paths` / `:source-paths` (skipping `.git`, `.clj-kondo`, `.lsp`, `.cpcache`, `node_modules`, `target`, `out`, `dist`).

Example — a monorepo without a `.lsp/config.edn`, where you want to override what Serena scanned:

```yaml
ls_specific_settings:
  clojure:
    source_paths:
      - "common/src"
      - "common/test"
      - "frontend/src"
      - "backend/src"
```

#### C/C++ (`clangd`)

Serena uses `clangd` for the `cpp` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed download | Override the `clangd` executable path. |
| `compile_commands_dir` | `.serena` | Directory where Serena writes a transformed `compile_commands.json` if the project's original database uses relative `directory` entries. |
| `clangd_version` | `19.1.2` | Override the `clangd` version Serena downloads when `ls_path` is not set. |

#### C/C++ via `ccls`

Serena uses the `cpp_ccls` language key for `ccls`.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | `ccls` from PATH | Override the `ccls` executable path. Serena does not manage `ccls` downloads or installs. |


#### C# (Roslyn Language Server)

Serena uses [Microsoft's Roslyn Language Server](https://github.com/dotnet/roslyn) for C# support.

**Runtime Requirements:**

- .NET 10 or higher is required. If not found in PATH, Serena automatically installs it using Microsoft's official install scripts.
- The Roslyn Language Server is automatically downloaded from NuGet.org.

**Supported Platforms:**

Automatic download is supported for: Windows (x64, ARM64), macOS (x64, ARM64), Linux (x64, ARM64).

**Configuration:**

The `runtime_dependencies` setting allows you to override the download URLs for the Roslyn Language Server. This is useful if you need to use a private package mirror or a specific version.
For the common case of changing only the package version, use `csharp_language_server_version`.

Example configuration to override the language server download URL:

```yaml
ls_specific_settings:
  csharp:
    csharp_language_server_version: "5.5.0-2.26078.4"
    runtime_dependencies:
      - id: "CSharpLanguageServer"
        platform_id: "linux-x64"  # or win-x64, win-arm64, osx-x64, osx-arm64, linux-arm64
        url: "https://your-mirror.example.com/roslyn-language-server.linux-x64.5.5.0-2.26078.4.nupkg"
        package_version: "5.5.0-2.26078.4"
```

Available fields for `runtime_dependencies` entries:

| Field             | Description                                                                 |
| ----------------- | --------------------------------------------------------------------------- |
| `id`              | Dependency identifier (use `CSharpLanguageServer`)                          |
| `platform_id`     | Target platform: `win-x64`, `win-arm64`, `osx-x64`, `osx-arm64`, `linux-x64`, `linux-arm64` |
| `url`             | Download URL for the NuGet package                                          |
| `package_version` | Package version string                                                      |
| `extract_path`    | Path within the package to extract (default: `tools/net10.0/<platform>`)    |

Notes:
- Only specify the platforms you want to override; others will use the defaults.
- The language server package is a `.nupkg` file (ZIP format) downloaded from NuGet.org by default.
- If you have .NET 10+ already installed, Serena will use your system installation.

#### C# (`OmniSharp`)

Serena uses the `csharp_omnisharp` language key for OmniSharp.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `omnisharp_version` | `1.39.10` | Override the OmniSharp version Serena downloads. |
| `razor_omnisharp_version` | `7.0.0-preview.23363.1` | Override the Razor OmniSharp plugin version Serena downloads. |

#### Dart

Serena uses the Dart SDK's built-in language server for Dart support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `dart_sdk_version` | `3.7.1` | Override the Dart SDK version Serena downloads. |

#### Elixir

Serena uses [Expert](https://github.com/elixir-lang/expert) for Elixir support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `expert_version` | `v0.1.0-rc.6` | Override the Expert version Serena downloads when it does not use an `expert` executable already found in PATH. |

#### Elm

Serena uses `@elm-tooling/elm-language-server` for Elm support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `elm_language_server_version` | `2.8.0` | Override the npm package version Serena installs when no system `elm-language-server` is found. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |

#### F#

Serena uses FsAutoComplete (Ionide LSP) for F# support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `fsautocomplete_version` | `0.83.0` | Override the FsAutoComplete version Serena installs as a .NET tool. |


#### Go (`gopls`)

Serena forwards `ls_specific_settings.go.gopls_settings` to `gopls` as LSP `initializationOptions` when the Go language server is started.

Example: enable build tags and set a build environment:

```yaml
ls_specific_settings:
  go:
    gopls_settings:
      buildFlags:
        - "-tags=foo"
      env:
        GOOS: "linux"
        GOARCH: "amd64"
        CGO_ENABLED: "0"
```

Notes:
- To enable multiple tags, use `"-tags=foo,bar"`.
- `gopls_settings.env` values are strings.
- `GOFLAGS` (from the environment you start Serena in) may also affect the Go build context. Prefer `buildFlags` for tags.
- Build context changes are only picked up when `gopls` starts. After changing `gopls_settings` (or relevant env vars like `GOFLAGS`), restart the Serena process (or server) that hosts the Go language server, or use your client's "Restart language server" action if it causes `gopls` to restart.

#### Groovy

Serena uses a user-provided Groovy Language Server JAR for Groovy support. If `ls_java_home_path` is not set, Serena downloads
a bundled Java runtime for launching that JAR.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_jar_path` | required | Path to the Groovy Language Server JAR |
| `ls_java_home_path` | `null` | Path to a Java installation to use instead of Serena's managed runtime |
| `ls_jar_options` | `""` | Additional options passed when launching the Groovy LS JAR |
| `vscode_java_version` | `1.42.0-561` | Override the bundled Java runtime bundle version Serena downloads by default |

Note:
- When overriding `vscode_java_version`, Serena still assumes that the downloaded runtime bundle keeps the same internal
  directory layout and file names as the bundled default version.

Example:

```yaml
ls_specific_settings:
  groovy:
    ls_jar_path: "/path/to/groovy-language-server-all.jar"
    vscode_java_version: "1.42.0-561"
```

#### HLSL

Serena uses `shader-language-server` for the `hlsl` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install or build | Override the `shader-language-server` executable path. |
| `version` | `1.3.1` | Override the bundled version Serena downloads, or builds from source on macOS, when `ls_path` is not set. |


#### Haxe

Serena uses the [vshaxe/haxe-language-server](https://github.com/vshaxe/haxe-language-server) for Haxe support.
Requires Haxe compiler (3.4.0+) and Node.js.

The server is discovered in order: user-configured `ls_path`, system PATH, vshaxe VSCode extension, auto-download from Open VSX.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | auto-discovered | Path to the Haxe language server binary (e.g., `/path/to/server.js`). |
| `version` | `2.34.2` | Override the vshaxe extension version downloaded from Open VSX. SHA256 verification is only performed for the default version. |
| `buildFile` | auto-discovered `.hxml` | Relative path to the `.hxml` build file used for compilation (e.g., `build/debug.hxml`). If not set, Serena searches the project for `.hxml` files (max depth 5, skipping dependency directories). |
| `haxePath` | `haxe` from PATH | Path to the Haxe compiler executable. The LS delegates to this for code analysis. Useful when multiple Haxe versions are installed or when `haxe` is not on the PATH. |
| `renameSourceFolders` | not set (LS default) | List of source directories for scoping rename operations (e.g., `["src", "lib"]`). If not set, the Haxe LS uses its own defaults. |

Example (typically in `project.yml`, since these are project-specific):

```yaml
ls_specific_settings:
  haxe:
    buildFile: "build/debug.hxml"
    haxePath: "/usr/local/bin/haxe"
    renameSourceFolders: ["src", "lib"]
```

#### HTML

Serena uses `vscode-html-language-server` from Microsoft's `vscode-langservers-extracted` npm package for the
`html` language key. **Experimental** — must be explicitly listed in `project.yml`; not auto-detected. The HTML
LSP returns in-file element / id symbols via `documentSymbol`; cross-file `definition` / `references` are not
meaningful for HTML and are not exposed.

This same language server is also used as a tertiary companion by the Angular language server (see the Angular
section), since `ngserver` does not implement `textDocument/documentSymbol` for `.html` files.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install | Override the `vscode-html-language-server` executable path. |
| `vscode_langservers_package` | `vscode-langservers-extracted` | npm package providing the binary. Set to `@t1ckbase/vscode-langservers-extracted` (or any other source) to use the actively-maintained 2026 fork. |
| `vscode_langservers_version` | `4.10.0` | Override the npm package version Serena installs when `ls_path` is not set. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |

#### Java (`eclipse.jdt.ls`)

Java support has two installation modes:

1. **Default vscode-java VSIX mode** (no extra config required): Serena downloads the platform-specific
   vscode-java VSIX (~500 MB: JDTLS + bundled JRE 21 + Lombok + IntelliCode), Gradle distribution and
   IntelliCode VSIX from public hosts on first use.
2. **Upstream JDTLS mode** (offline-friendly): Activated by setting both `jdtls_path` and `lombok_path`.
   Uses an existing JDTLS installation (~100 MB) and the system JDK 21+. Nothing is downloaded.
   Recommended for restricted-network/corporate environments.

**When to use which mode:**

- **Default vscode-java VSIX mode** — recommended for most users. No setup required;
  Serena downloads everything on first use.
- **Upstream JDTLS mode** — recommended when:
  - you cannot reach `github.com`, `services.gradle.org` or `marketplace.visualstudio.com`
    from the host (corporate proxy, air-gapped network);
  - you want a smaller on-disk footprint (~100 MB vs ~500 MB);
  - you already maintain a JDTLS installation (e.g. for `nvim-jdtls` or another editor);
  - your security policy prohibits per-project runtime downloads.

**JDK 21+ is required** in upstream mode. Serena resolves the JDK in this order:
`ls_specific_settings.java.java_home` → `JAVA_HOME` env var → first `java` on `PATH`.
The resolved JVM is interrogated and rejected if its `java.specification.version` is below 21.

The following settings are supported for the Java language server:

| Setting | Default | Description |
|---|---|---|
| `jdtls_path` | `null` | Activates upstream JDTLS mode. Path to upstream JDTLS root (containing `plugins/` and `config_<platform>/`). Get via `brew install jdtls` or extract `jdt-language-server-*.tar.gz` from <https://download.eclipse.org/jdtls/snapshots/>. Must be set together with `lombok_path`. |
| `lombok_path` | `null` | Path to the Lombok jar. Activates upstream JDTLS mode together with `jdtls_path`. Get from `~/.m2/repository/org/projectlombok/lombok/<ver>/lombok-<ver>.jar` or download from <https://projectlombok.org/downloads/>. |
| `java_home` | `null` | (upstream-jdtls mode only) Path to JDK 21+ home directory used to launch JDTLS. Falls back to `JAVA_HOME` env var, then `which java`. |
| `maven_user_settings` | `~/.m2/settings.xml` | Path to Maven `settings.xml` |
| `gradle_user_home` | `~/.gradle` | Path to Gradle user home directory |
| `gradle_wrapper_enabled` | `false` | Use the project's Gradle wrapper (`gradlew`) instead of the bundled Gradle distribution. Enable this for projects with custom plugins or repositories. |
| `gradle_java_home` | `null` | Path to the JDK used by Gradle. When unset, Gradle uses the bundled JRE. |
| `use_system_java_home` | `false` | Use the system's `JAVA_HOME` environment variable for JDTLS itself. Enable this if your project requires a specific JDK vendor or version for Gradle's JDK checks. |
| `gradle_version` | `8.14.2` | (vscode-java mode only) Override the Gradle distribution version Serena downloads by default. |
| `vscode_java_version` | `1.54.0-923` | (vscode-java mode only) Override the bundled `vscode-java` runtime bundle version Serena downloads by default. |
| `intellicode_version` | `1.2.30` | (vscode-java mode only) Override the IntelliCode VSIX version Serena downloads by default. |
| `lombok_show_generated` | `true` | Show Lombok-generated methods (`getX/setX`, `builder()`, `equals/hashCode/toString`, `withX`, fluent accessors) in `find_symbol`, `get_symbols_overview` and the symbol-edit tools. Set to `false` to restore the previous JDTLS default and hide the synthetic methods (e.g. when `@Data` classes pollute the outline with too many getters/setters). Requires JDTLS commit `b2d8952` / `vscode-java >= 1.53.0`; the bundled default already meets this. |
| `jdtls_xmx` | `3G` | Maximum heap size for the JDTLS server JVM. |
| `jdtls_xms` | `100m` | Initial heap size for the JDTLS server JVM. |
| `intellicode_xmx` | `1G` | (vscode-java mode only) Maximum heap size for the IntelliCode embedded JVM. |
| `intellicode_xms` | `100m` | (vscode-java mode only) Initial heap size for the IntelliCode embedded JVM. |

Notes:
- When overriding `vscode_java_version`, Serena still assumes that the downloaded runtime bundle keeps the same internal
  directory layout and file names as the bundled default version.
- In upstream-jdtls mode, IntelliCode is not loaded (it's an ML completions ranker that is irrelevant to Serena's
  symbol-tools workflow), and Serena does not ship a Gradle distribution. Maven projects work via JDTLS's bundled m2e.
  Gradle projects must have `./gradlew` in the project, or rely on a system-installed Gradle through Buildship's
  default discovery rules.
- In upstream-jdtls mode the `gradle_version`, `vscode_java_version`, `intellicode_version`,
  `intellicode_xmx`, `intellicode_xms` settings are silently ignored — they only apply to the
  vscode-java VSIX mode.

Example: upstream-jdtls mode (offline / corporate network):

```yaml
ls_specific_settings:
  java:
    jdtls_path: "/opt/homebrew/Cellar/jdtls/1.50.0/libexec"
    lombok_path: "/Users/me/.m2/repository/org/projectlombok/lombok/1.18.38/lombok-1.18.38.jar"
    # java_home: "/opt/homebrew/opt/openjdk@21"  # optional
```

Example: default vscode-java VSIX mode for a project with custom Gradle plugins:

```yaml
ls_specific_settings:
  java:
    gradle_wrapper_enabled: true
    use_system_java_home: true
```

#### Kotlin

Serena uses [JetBrains' Kotlin Language Server](https://github.com/Kotlin/kotlin-lsp) for Kotlin support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed download | Override the Kotlin Language Server executable path. |
| `kotlin_lsp_version` | `261.13587.0` | Override the Kotlin Language Server version Serena downloads when `ls_path` is not set. |
| `jvm_options` | `-Xmx2G` | Value assigned to `JAVA_TOOL_OPTIONS` for the Kotlin LS process. Set to `""` to disable JVM options entirely. |

Example:

```yaml
ls_specific_settings:
  kotlin:
    kotlin_lsp_version: "261.13587.0"
    jvm_options: "-Xmx4G -XX:+UseG1GC"
```

#### Lean 4

Serena uses `lean --server` for Lean 4 support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | `lean` from PATH | Override the `lean` executable path. Serena does not manage Lean downloads. |

#### Lua

Serena uses `lua-language-server` for Lua support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `lua_language_server_version` | `3.15.0` | Override the bundled `lua-language-server` version Serena downloads when it cannot use an existing installation from PATH or common install locations. |


#### Luau

Serena uses [`luau-lsp`](https://github.com/JohnnyMorganz/luau-lsp) for Luau support.

**Runtime Requirements:**

- `luau-lsp` is used from PATH if available.
- Otherwise, Serena downloads the pinned `luau-lsp` release for the current platform.

**Configuration:**

```yaml
ls_specific_settings:
  luau:
    ls_path: "/path/to/luau-lsp"            # Optional: override the language server executable
    luau_lsp_version: "1.63.0"              # Optional: override the bundled luau-lsp version
    platform: "roblox"                      # "roblox" (default) or "standard"
    roblox_security_level: "PluginSecurity" # Roblox only: None, PluginSecurity, LocalUserSecurity, RobloxScriptSecurity
```

Notes:
- In `roblox` mode, Serena downloads Roblox definitions and Roblox API docs and passes them to `luau-lsp`.
- In `standard` mode, Serena skips Roblox definitions and only downloads the standard Luau docs bundle.

#### Markdown

Serena uses [Marksman](https://github.com/artempyanykh/marksman) for the `markdown` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed download | Override the `marksman` executable path. |
| `marksman_version` | `2024-12-18` | Override the Marksman release tag Serena downloads when `ls_path` is not set. |

#### MATLAB

Serena uses the official MathWorks MATLAB language server from the VS Code extension.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `matlab_path` | auto-detected | Path to the MATLAB installation. This overrides `MATLAB_PATH` and auto-detection, but not Serena's managed extension download. |
| `matlab_extension_version` | `1.3.9` | Override the MathWorks VS Code extension version Serena downloads. |


#### Pascal (`pasls`)

Serena uses [pasls](https://github.com/genericptr/pascal-language-server) (Pascal Language Server) for Pascal/Free Pascal support.

**Language Server Installation:**

1. If `pasls` is found in your system PATH, Serena uses it directly
2. Otherwise, Serena automatically downloads a prebuilt binary from GitHub releases

Supported platforms for automatic download: Linux (x64, arm64), macOS (x64, arm64), Windows (x64).

**Auto-Update:**

Serena automatically checks for pasls updates every 24 hours. Updates include:
- SHA256 checksum verification before installation
- Atomic update with rollback on failure
- Windows file locking detection (defers update if pasls is in use)

**Configuration:**

Configure pasls via `ls_specific_settings.pascal` in `serena_config.yml`:

| Setting          | Description                                                                 |
| ---------------- | --------------------------------------------------------------------------- |
| `pasls_version`  | Override the pinned pasls version Serena downloads by default               |
| `pp`             | Path to FPC compiler driver (must be `fpc` or `fpc.exe`, not `ppc386.exe`)  |
| `fpcdir`         | Path to FPC source directory                                                |
| `lazarusdir`     | Path to Lazarus directory (required for LCL projects)                       |
| `fpc_target`     | Target OS override (e.g., `Win32`, `Win64`, `Linux`)                        |
| `fpc_target_cpu` | Target CPU override (e.g., `i386`, `x86_64`, `aarch64`)                     |

Example configuration:

```yaml
ls_specific_settings:
  pascal:
    pp: "D:/laz32/fpc/bin/i386-win32/fpc.exe"
    fpcdir: "D:/laz32/fpcsrc"
    lazarusdir: "D:/laz32/lazarus"
```

Notes:
- The `pp` setting is the most important for hover and navigation to work correctly.
- Use the FPC compiler driver (`fpc`/`fpc.exe`), not backend compilers like `ppc386.exe`.
- These settings are passed as environment variables to the pasls process.

#### PHP (`Intelephense`)

Serena uses Intelephense for the `php` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install | Override the `intelephense` executable path. |
| `intelephense_version` | `1.14.4` | Override the npm package version Serena installs when `ls_path` is not set. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |
| `ignore_vendor` | `true` | Ignore directories named `vendor` while indexing the project. |
| `maxFileSize` | unset | Forwarded as `intelephense.files.maxSize` in `initializationOptions`. |
| `maxMemory` | unset | Forwarded as `intelephense.maxMemory` in `initializationOptions`. |

#### PHP (`Phpactor`)

Serena uses the `php_phpactor` language key for Phpactor.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed download | Override the Phpactor PHAR path. |
| `phpactor_version` | `2025.12.21.1` | Override the Phpactor PHAR version Serena downloads when `ls_path` is not set. |
| `ignore_vendor` | `true` | Ignore directories named `vendor` while indexing the project. |

#### PowerShell

Serena uses PowerShell Editor Services for PowerShell support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `pses_version` | `4.4.0` | Override the PowerShell Editor Services version Serena downloads. Serena still requires `pwsh` to be available locally. |

#### Python

Serena uses Pyright for the `python` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | current Python executable | Override the Python interpreter Serena uses to run `-m pyright.langserver`. |

Note:
- There is currently no separate `python_ty` language key in Serena's current SolidLSP implementation.

#### Ruby

Serena uses Shopify's `ruby-lsp` for Ruby support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ruby_lsp_version` | `0.26.8` | Override the `ruby-lsp` gem version Serena installs when no project-local or global `ruby-lsp` is already available. |

#### Rust

Serena uses `rust-analyzer` for Rust support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | auto-detected | Override the `rust-analyzer` executable path. Without `ls_path`, Serena prefers `rustup which rust-analyzer`, then `rustup component add rust-analyzer`, then PATH/common install locations. |

#### Scala

Serena uses Metals for Scala support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `metals_version` | `1.6.4` | Override the Metals version Serena bootstraps. |
| `client_name` | `Serena` | Client identifier sent to Metals. |
| `on_stale_lock` | `auto-clean` | How Serena handles stale Metals H2 database locks. Supported values: `auto-clean`, `warn`, `fail`. |
| `log_multi_instance_notice` | `true` | Log a notice when another Metals instance is detected. |

#### SCSS / Sass / CSS

Serena uses [`some-sass-language-server`](https://github.com/wkillerud/some-sass) for the `scss` language key.
**Experimental** — must be explicitly listed in `project.yml`; not auto-detected. Some Sass was chosen over the
generic `vscode-css-language-server` because it provides full workspace-wide `@use` / `@forward` go-to-definition
and find-references for variables, mixins, functions, and placeholders.

Handles `.scss`, `.sass`, and `.css`. The three are dispatched by the LSP language id (`scss`, `sass`, `css`) and
share the same engine; CSS feature toggles default to off upstream and Serena flips them on at startup so that
plain CSS gets symbols, definitions, references, hover, and completion. Lint diagnostics are deliberately left
off (the rules are opinionated about vendor prefixes / empty rules / etc.); only syntax-level diagnostics surface.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install | Override the `some-sass-language-server` executable path. |
| `some_sass_version` | `2.3.8` | Override the npm package version Serena installs when `ls_path` is not set. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |

#### Solidity

Serena uses `@nomicfoundation/solidity-language-server` for Solidity support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install | Override the Solidity language server executable path. |
| `solidity_language_server_version` | `0.8.4` | Override the npm package version Serena installs when `ls_path` is not set. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |

#### SystemVerilog

Serena uses `verible-verilog-ls` for SystemVerilog support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | system PATH or managed download | Override the `verible-verilog-ls` executable path. |
| `verible_version` | `v0.0-4051-g9fdb4057` | Override the Verible release Serena downloads when `ls_path` is not set and no system installation is found. |

#### Terraform

Serena uses `terraform-ls` for Terraform support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `terraform_ls_version` | `0.36.5` | Override the `terraform-ls` version Serena downloads. Terraform itself must still be installed and available in PATH. |

#### TOML

Serena uses [Taplo](https://github.com/tamasfe/taplo) for the `toml` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed download | Override the `taplo` executable path. |
| `taplo_version` | `0.10.0` | Override the Taplo version Serena downloads when `ls_path` is not set. |

#### TypeScript

Serena uses `typescript-language-server` for the `typescript` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install | Override the `typescript-language-server` executable path. |
| `typescript_version` | `5.9.3` | Override the bundled `typescript` npm package version Serena installs when `ls_path` is not set. |
| `typescript_language_server_version` | `5.1.3` | Override the bundled `typescript-language-server` npm package version Serena installs when `ls_path` is not set. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |

TypeScript supports [additional workspace folders](additional-workspace-folders) for cross-package
reference discovery. Configure `additional_workspace_folders` in `project.yml` to enable this feature.

#### TypeScript via `vtsls`

The actual configuration key for vtsls is `typescript_vts`, not `vts`.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `vtsls_version` | `0.2.9` | Override the `@vtsls/language-server` npm package version Serena installs. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |

#### Vue

Serena uses `@vue/language-server` (Volar) for the `vue` language key, together with a companion TypeScript language server.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `vue_language_server_version` | `3.1.5` | Override the bundled `@vue/language-server` npm package version Serena installs. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. If unset on `vue`, Serena falls back to `ls_specific_settings.typescript.npm_registry`. |

Notes:
- `typescript_version` and `typescript_language_server_version` are read from `ls_specific_settings.typescript`, not from `ls_specific_settings.vue`.

#### YAML

Serena uses `yaml-language-server` for the `yaml` language key.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed install | Override the `yaml-language-server` executable path. |
| `yaml_language_server_version` | `1.19.2` | Override the npm package version Serena installs when `ls_path` is not set. |
| `npm_registry` | `null` | Override the npm registry Serena uses for the managed install. |

### Custom Prompts

All of Serena's prompts can be fully customized.
We define prompt as jinja templates in yaml files, and you can inspect our default prompts [here](https://github.com/oraios/serena/tree/main/src/serena/resources/config/prompt_templates).

To override a prompt, simply add a .yml file to the `prompt_templates` folder in your Serena data directory
which defines the prompt with the same name as the default prompt you want to override.
For example, to override the `system_prompt`, you could create a file `~/.serena/prompt_templates/system_prompt.yml` (assuming default Serena data folder location) 
with content like:

```yaml
prompts:
  system_prompt: |
    Whatever you want ...
```

It is advisable to use the default prompt as a starting point and modify it to suit your needs.

### Usage Reporting

On startup, Serena reports anonymous usage data to help us understand Serena usage.
Specifically, we collect the Serena version, the operating system & language backend being used as well as the dashboard enabled status.
No personally identifiable information or project-specific information is collected.

If you want to opt out of usage reporting, set the environment variable `SERENA_USAGE_REPORTING` to `false`.
