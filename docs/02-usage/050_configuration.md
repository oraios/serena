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
   
## Global Configuration

The global configuration file allows you to change general settings and defaults that will apply to all projects unless overridden.

### Settings

Some of the configurable settings include:
  * the language backend to use by default (i.e., the JetBrains plugin or language servers)
  * UI settings affecting the [Serena Dashboard and GUI tool](060_dashboard.md)
  * the set of tools to enable/disable by default
  * tool execution parameters (timeout, max. answer length)
  * global ignore rules
  * logging settings
  * advanced settings specific to individual language servers (see [below](ls-specific-settings))

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

Find the concrete definitions of these modes [here](https://github.com/oraios/serena/tree/main/src/serena/resources/config/modes).

:::{important}
By default, Serena activates the two modes `interactive` and `editing`.  

As soon as you start to specify modes, only the modes you explicitly specify will be active, however.
Therefore, if you want to keep the default modes, you must specify them as well.  
For example, to add mode `no-memories` to the default behaviour, specify
```shell
--mode interactive --mode editing --mode no-memories
```
:::

Modes can be set at startup (similar to contexts) but can also be _switched dynamically_ during a session. 
You can instruct the LLM to use the `switch_modes` tool to activate a different set of modes (e.g., "Switch to planning and one-shot modes").

When launching Serena, specify modes using `--mode <mode-name>`; multiple modes can be specified, e.g. `--mode planning --mode no-onboarding`.

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

(ls-specific-settings)=
### Language Server-Specific Settings

Under the key `ls_specific_settings` in `serena_config.yml`, you can you pass per-language, 
language server-specific configuration.

Structure:

```yaml
ls_specific_settings:
  <language>:
    # language-server-specific keys
```

:::{attention}
Most settings are currently undocumented. Please refer to the 
[source code of the respective language server](https://github.com/oraios/serena/tree/main/src/solidlsp/language_servers) 
implementation to determine supported settings.
:::

#### Overriding the Language Server Path

Some language servers, particularly those that use a single core path for the language server (e.g. the main executable),
support overriding that path via the `ls_path` setting.
Therefore, if you have installed the language server yourself and want to use your installation 
instead of Serena's managed installation, you can set the `ls_path` setting as follows:

```yaml
ls_specific_settings:
  <language>:
    ls_path: "/path/to/language-server"
```

This is supported by all language servers deriving their dependency provider from  `LanguageServerDependencyProviderSinglePath`.
Currently, this includes the following languages: `clojure`, `cpp`, `php`, `python`, `typescript`. 
We will add support for more languages over time.

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
