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
    <serena> config edit
    ```

    where `<serena>` is [your way of running Serena](020_running).

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

    <serena> context --help
    <serena> context list
    <serena> context create <context-name>
    <serena> context edit <context-name>
    <serena> context delete <context-name>

where `<serena>` is [your way of running Serena](020_running).

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

Active modes are configured in (from lowest to highest precedence):
  * the global configuration file (`serena_config.yml`)
  * the project configuration file (`project.yml`)
  * at startup via command-line parameters

The two former sources define both **base modes** and **default modes**.
Ultimately, the active modes are the union of base modes and default modes (after applying all overrides).
Command-line parameters override default modes but not base modes.
Base modes should thus be used to define modes that you always want to be active, regardless of command-line parameters.

Command-line parameters for overriding default modes:
When launching the MCP sever, specify modes using `--mode <mode-name>`; multiple modes can be specified, e.g. `--mode planning --mode no-onboarding`.

:::{important}
By default, Serena activates the two modes `interactive` and `editing` (as defined in the global configuration).

As soon as you start to specify modes via the command line, only the modes you explicitly specify will be active, however.
Therefore, if you want to keep the default modes, you must specify them as well.  
For example, to add mode `no-memories` to the default behaviour, specify
```shell
--mode interactive --mode editing --mode no-memories
```

If you want to keep certain modes as always active, regardless of command-line parameters, 
define them as *base modes* in the global or project configuration.
:::

Modes can also be _switched dynamically_ during a session. 
You can instruct the LLM to use the `switch_modes` tool to activate a different set of modes (e.g., "Switch to planning and one-shot modes").
Like command-line parameters, this only affects default modes, not base modes (which remain active).

:::{note}
**Mode Compatibility**: While you can combine modes, some may be semantically incompatible (e.g., `interactive` and `one-shot`). 
Serena currently does not prevent incompatible combinations; it is up to the user to choose sensible mode configurations.
:::

You can manage modes using the `mode` command,

    <serena> mode --help
    <serena> mode list
    <serena> mode create <mode-name>
    <serena> mode edit <mode-name>
    <serena> mode delete <mode-name>

where `<serena>` is [your way of running Serena](020_running).

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
Common examples include: `ansible`, `bash`, `clojure`, `cpp`, `cpp_ccls`, `hlsl`, `kotlin`, `lean4`, `luau`, `markdown`, `php`,
`php_phpactor`, `python`, `rust`, `solidity`, `systemverilog`, `toml`, `typescript`, and `yaml`.

If a language server supports `ls_path`, setting it bypasses Serena's managed download or install for that server.
In that case, any server-specific version or registry settings only apply when `ls_path` is not set.

#### AL

Serena uses the AL language server bundled in the Microsoft Dynamics 365 Business Central VS Code extension.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `al_extension_version` | `18.0.2242655` | Override the AL VS Code extension version Serena downloads from the VS Code Marketplace. |

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

#### Clojure

Serena uses `clojure-lsp` for Clojure support.

Supported settings:

| Setting | Default | Description |
|---|---|---|
| `ls_path` | managed download | Override the `clojure-lsp` executable path. |
| `clojure_lsp_version` | `2026.02.20-16.08.58` | Override the `clojure-lsp` release version Serena downloads when `ls_path` is not set. |

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
| `version` | `1.3.0` | Override the bundled version Serena downloads, or builds from source on macOS, when `ls_path` is not set. |


#### Java (`eclipse.jdt.ls`)

The following settings are supported for the Java language server:

| Setting | Default | Description |
|---|---|---|
| `maven_user_settings` | `~/.m2/settings.xml` | Path to Maven `settings.xml` |
| `gradle_user_home` | `~/.gradle` | Path to Gradle user home directory |
| `gradle_wrapper_enabled` | `false` | Use the project's Gradle wrapper (`gradlew`) instead of the bundled Gradle distribution. Enable this for projects with custom plugins or repositories. |
| `gradle_java_home` | `null` | Path to the JDK used by Gradle. When unset, Gradle uses the bundled JRE. |
| `use_system_java_home` | `false` | Use the system's `JAVA_HOME` environment variable for JDTLS itself. Enable this if your project requires a specific JDK vendor or version for Gradle's JDK checks. |
| `gradle_version` | `8.14.2` | Override the Gradle distribution version Serena downloads by default. |
| `vscode_java_version` | `1.42.0-561` | Override the bundled `vscode-java` runtime bundle version Serena downloads by default. |
| `intellicode_version` | `1.2.30` | Override the IntelliCode VSIX version Serena downloads by default. |
| `jdtls_xmx` | `3G` | Maximum heap size for the JDTLS server JVM. |
| `jdtls_xms` | `100m` | Initial heap size for the JDTLS server JVM. |
| `intellicode_xmx` | `1G` | Maximum heap size for the IntelliCode embedded JVM. |
| `intellicode_xms` | `100m` | Initial heap size for the IntelliCode embedded JVM. |

Note:
- When overriding `vscode_java_version`, Serena still assumes that the downloaded runtime bundle keeps the same internal
  directory layout and file names as the bundled default version.

Example for a project with custom Gradle plugins and JDK requirements:

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
