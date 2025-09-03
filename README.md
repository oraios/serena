<p align="center" style="text-align:center">
  <img src="resources/serena-logo.svg#gh-light-mode-only" style="width:500px">
  <img src="resources/serena-logo-dark-mode.svg#gh-dark-mode-only" style="width:500px">
</p>

* :rocket: Serena is a powerful **coding agent toolkit** capable of turning an LLM into a fully-featured agent that works **directly on your codebase**.
  Unlike most other tools, it is not tied to an LLM, framework or an interface, making it easy to use it in a variety of ways.
* :wrench: Serena provides essential **semantic code retrieval and editing tools** that are akin to an IDE's capabilities, extracting code entities at the symbol level and exploiting relational structure. When combined with an existing coding agent, these tools greatly enhance (token) efficiency.
* :free: Serena is **free & open-source**, enhancing the capabilities of LLMs you already have access to free of charge.

You can think of Serena as providing IDE-like tools to your LLM/coding agent. With it, the agent no longer needs to read entire
files, perform grep-like searches or string replacements to find and edit the right code. Instead, it can use code centered tools like `find_symbol`, `find_referencing_symbols` and `insert_after_symbol`.

<p align="center">
  <em>Serena is under active development! See the latest updates, upcoming features, and lessons learned to stay up to date.</em>
</p>

<p align="center">
  <a href="CHANGELOG.md">
    <img src="https://img.shields.io/badge/Updates-1e293b?style=flat&logo=rss&logoColor=white&labelColor=1e293b" alt="Changelog" />
  </a>
  <a href="roadmap.md">
    <img src="https://img.shields.io/badge/Roadmap-14532d?style=flat&logo=target&logoColor=white&labelColor=14532d" alt="Roadmap" />
  </a>
  <a href="lessons_learned.md">
    <img src="https://img.shields.io/badge/Lessons-Learned-7c4700?style=flat&logo=readthedocs&logoColor=white&labelColor=7c4700" alt="Lessons Learned" />
  </a>
</p>

### LLM Integration

Serena provides the necessary [tools](#list-of-tools) for coding workflows, but an LLM is required to do the actual work,
orchestrating tool use.

For example, **supercharge the performance of Claude Code** with a [one-line shell command](#claude-code).

In general, Serena can be integrated with an LLM in several ways:

* by using the **model context protocol (MCP)**.
  Serena provides an MCP server which integrates with
    * Claude Code and Claude Desktop,
    * Terminal-based clients like Codex, Gemini-CLI, Qwen3-Coder, rovodev, OpenHands CLI and others,
    * IDEs like VSCode, Cursor or IntelliJ,
    * Extensions like Cline or Roo Code
    * Local clients like [OpenWebUI](https://docs.openwebui.com/openapi-servers/mcp), [Jan](https://jan.ai/docs/mcp-examples/browser/browserbase#enable-mcp), [Agno](https://docs.agno.com/introduction/playground) and others
* by using [mcpo to connect it to ChatGPT](docs/serena_on_chatgpt.md) or other clients that don't support MCP but do support tool calling via OpenAPI.
* by incorporating Serena's tools into an agent framework of your choice, as illustrated [here](docs/custom_agent.md).
  Serena's tool implementation is decoupled from the framework-specific code and can thus easily be adapted to any agent framework.

### Serena in Action

#### Demonstration 1: Efficient Operation in Claude Code

A demonstration of Serena efficiently retrieving and editing code within Claude Code, thereby saving tokens and time. Efficient operations are not only useful for saving costs, but also for generally improving the generated code's quality. This effect may be less pronounced in very small projects, but often becomes of crucial importance in larger ones.

https://github.com/user-attachments/assets/ab78ebe0-f77d-43cc-879a-cc399efefd87

#### Demonstration 2: Serena in Claude Desktop

A demonstration of Serena implementing a small feature for itself (a better log GUI) with Claude Desktop.
Note how Serena's tools enable Claude to find and edit the right symbols.

https://github.com/user-attachments/assets/6eaa9aa1-610d-4723-a2d6-bf1e487ba753

### Programming Language Support & Semantic Analysis Capabilities

Serena's semantic code analysis capabilities build on **language servers** using the widely implemented
language server protocol (LSP). The LSP provides a set of versatile code querying
and editing functionalities based on symbolic understanding of the code.
Equipped with these capabilities, Serena discovers and edits code just like a seasoned developer
making use of an IDE's capabilities would.
Serena can efficiently find the right context and do the right thing even in very large and
complex projects! So not only is it free and open-source, it frequently achieves better results
than existing solutions that charge a premium.

Language servers provide support for a wide range of programming languages.
With Serena, we provide direct, out-of-the-box support for:

  * Python
  * TypeScript/Javascript
  * PHP (uses Intelephense LSP; set `INTELEPHENSE_LICENSE_KEY` environment variable for premium features)
  * Go (requires installation of gopls)
  * R (requires installation of the `languageserver` R package)
  * Rust (requires [rustup](https://rustup.rs/) - uses rust-analyzer from your toolchain)
  * C/C++ (you may experience issues with finding references, we are working on it)
  * Zig (requires installation of ZLS - Zig Language Server)
  * C#
  * Ruby (by default, uses [ruby-lsp](https://github.com/Shopify/ruby-lsp), specify ruby_solargraph as your language to use the previous solargraph based implementation)
  * Swift
  * Kotlin (uses the pre-alpha [official kotlin LS](https://github.com/Kotlin/kotlin-lsp), some issues may appear)
  * Java (_Note_: startup is slow, initial startup especially so. There may be issues with java on macos and linux, we are working on it.)
  * Clojure
  * Dart
  * Bash
  * Lua (automatically downloads lua-language-server if not installed)
  * Nix (requires nixd installation)
  * Elixir (requires installation of NextLS and Elixir; **Windows not supported**)
  * Erlang (requires installation of beam and [erlang_ls](https://github.com/erlang-ls/erlang_ls), experimental, might be slow or hang)
  * Scala (via metals, experimental, requires [coursier](https://get-coursier.io/docs/cli-installation) and your project should be compiled when using Serena)

Support for further languages can easily be added by providing a shallow adapter for a new language server implementation,
see Serena's [memory on that](.serena/memories/adding_new_language_support_guide.md).

### Community Feedback

Most users report that Serena has strong positive effects on the results of their coding agents, even when used within
very capable agents like Claude Code. Serena is often described to be a [game changer](https://www.reddit.com/r/ClaudeAI/comments/1lfsdll/try_out_serena_mcp_thank_me_later/), providing an enormous [productivity boost](https://www.reddit.com/r/ClaudeCode/comments/1mguoia/absolutely_insane_improvement_of_claude_code).

Serena excels at navigating and manipulating complex codebases, providing tools that support precise code retrieval and editing in the presence of large, strongly structured codebases.
However, when dealing with tasks that involve only very few/small files, you may not benefit from including Serena on top of your existing coding agent. 
In particular, when writing code from scratch, Serena will not provide much value initially, as the more complex structures that Serena handles more gracefully than simplistic, file-based approaches are yet to be created.

Several videos and blog posts have talked about Serena:

* YouTube:
    * [AI Labs](https://www.youtube.com/watch?v=wYWyJNs1HVk&t=1s)
    * [Yo Van Eyck](https://www.youtube.com/watch?v=UqfxuQKuMo8&t=45s)
    * [JeredBlu](https://www.youtube.com/watch?v=fzPnM3ySmjE&t=32s)

* Blog posts:
    * [Serena's Design Principles](https://medium.com/@souradip1000/deconstructing-serenas-mcp-powered-semantic-code-understanding-architecture-75802515d116)
    * [Serena with Claude Code (in Japanese)](https://blog.lai.so/serena/)
    * [Turning Claude Code into a Development Powerhouse](https://robertmarshall.dev/blog/turning-claude-code-into-a-development-powerhouse/)

## Table of Contents

<!-- Created with markdown-toc -i README.md -->
<!-- Install it with npm install -g markdown-toc -->

<!-- toc -->

- [Quick Start](#quick-start)
  * [Running the Serena MCP Server](#running-the-serena-mcp-server)
    + [Usage](#usage)
      - [Using uvx](#using-uvx)
        * [Local Installation](#local-installation)
      - [Using Docker (Experimental)](#using-docker-experimental)
    + [SSE Mode](#sse-mode)
    + [Command-Line Arguments](#command-line-arguments)
  * [Configuration](#configuration)
  * [Project Activation & Indexing](#project-activation--indexing)
  * [Claude Code](#claude-code)
  * [Codex](#codex)
  * [Other Terminal-Based Clients](#other-terminal-based-clients)
  * [Claude Desktop](#claude-desktop)
  * [MCP Coding Clients (Cline, Roo-Code, Cursor, Windsurf, etc.)](#mcp-coding-clients-cline-roo-code-cursor-windsurf-etc)
  * [Local GUIs and Frameworks](#local-guis-and-frameworks)
- [Detailed Usage and Recommendations](#detailed-usage-and-recommendations)
  * [Tool Execution](#tool-execution)
    + [Shell Execution and Editing Tools](#shell-execution-and-editing-tools)
  * [Modes and Contexts](#modes-and-contexts)
    + [Contexts](#contexts)
    + [Modes](#modes)
    + [Customization](#customization)
  * [Onboarding and Memories](#onboarding-and-memories)
  * [Prepare Your Project](#prepare-your-project)
    + [Structure Your Codebase](#structure-your-codebase)
    + [Start from a Clean State](#start-from-a-clean-state)
    + [Logging, Linting, and Automated Tests](#logging-linting-and-automated-tests)
  * [Prompting Strategies](#prompting-strategies)
  * [Potential Issues in Code Editing](#potential-issues-in-code-editing)
  * [Running Out of Context](#running-out-of-context)
  * [Combining Serena with Other MCP Servers](#combining-serena-with-other-mcp-servers)
  * [Serena's Logs: The Dashboard and GUI Tool](#serenas-logs-the-dashboard-and-gui-tool)
  * [Troubleshooting](#troubleshooting)
- [Comparison with Other Coding Agents](#comparison-with-other-coding-agents)
  * [Subscription-Based Coding Agents](#subscription-based-coding-agents)
  * [API-Based Coding Agents](#api-based-coding-agents)
  * [Other MCP-Based Coding Agents](#other-mcp-based-coding-agents)
- [Acknowledgements](#acknowledgements)
- [Customizing and Extending Serena](#customizing-and-extending-serena)
- [List of Tools](#list-of-tools)

<!-- tocstop -->

## Quick Start

Serena can be used in various ways, below you will find instructions for selected integrations.

* For coding with Claude, we recommend using Serena through [Claude Code](#claude-code) or [Claude Desktop](#claude-desktop). You can also use Serena in most other [terminal-based clients](#other-terminal-based-clients).
* If you want a GUI experience outside an IDE, you can use one of the many [local GUIs](#local-guis-and-frameworks) that support MCP servers.
  You can also connect Serena to many web clients (including ChatGPT) using [mcpo](docs/serena_on_chatgpt.md).
* If you want to use Serena integrated in your IDE, see the section on [other MCP clients](#other-mcp-clients---cline-roo-code-cursor-windsurf-etc).
* You can use Serena as a library for building your own applications. We try to keep the public API stable, but you should still
  expect breaking changes and pin Serena to a fixed version if you use it as a dependency.

Serena is managed by `uv`, so you will need to [install it](https://docs.astral.sh/uv/getting-started/installation/)).

### Running the Serena MCP Server

You have several options for running the MCP server, which are explained in the subsections below.

#### Usage

The typical usage involves the client (Claude Code, Claude Desktop, etc.) running
the MCP server as a subprocess (using stdio communication),
so the client needs to be provided with the command to run the MCP server.
(Alternatively, you can run the MCP server in SSE mode and tell your client
how to connect to it.)

Note that no matter how you run the MCP server, Serena will, by default, start a small web-based dashboard on localhost that will display logs and allow shutting down the
MCP server (since many clients fail to clean up processes correctly).
This and other settings can be adjusted in the [configuration](#configuration) and/or by providing [command-line arguments](#command-line-arguments).

##### Using uvx

`uvx` can be used to run the latest version of Serena directly from the repository, without an explicit local installation.

```shell
uvx --from git+https://github.com/oraios/serena serena start-mcp-server
```

Explore the CLI to see some of the customization options that serena provides (more info on them below).

###### Local Installation

1. Clone the repository and change into it.

   ```shell
   git clone https://github.com/oraios/serena
   cd serena
   ```

2. Optionally edit the configuration file in your home directory with

   ```shell
   uv run serena config edit
   ```

   If you just want the default config, you can skip this part, and a config file will be created when you first run Serena.
3. Run the server with `uv`:

   ```shell
   uv run serena start-mcp-server
   ```

   When running from outside the serena installation directory, be sure to pass it, i.e., use

   ```shell
    uv run --directory /abs/path/to/serena serena start-mcp-server
   ```

##### Using Docker (Experimental)

⚠️ Docker support is currently experimental with several limitations. Please read the [Docker documentation](DOCKER.md) for important caveats before using it.

You can run the Serena MCP server directly via docker as follows,
assuming that the projects you want to work on are all located in `/path/to/your/projects`:

```shell
docker run --rm -i --network host -v /path/to/your/projects:/workspaces/projects ghcr.io/oraios/serena:latest serena start-mcp-server --transport stdio
```

Replace `/path/to/your/projects` with the absolute path to your projects directory. The Docker approach provides:

* Better security isolation for shell command execution
* No need to install language servers and dependencies locally
* Consistent environment across different systems

Alternatively, use docker compose with the `compose.yml` file provided in the repository.

See the [Docker documentation](DOCKER.md) for detailed setup instructions, configuration options, and known limitations.

##### Using Nix

If you are using Nix and [have enabled the `nix-command` and `flakes` features](https://nixos.wiki/wiki/flakes), you can run Serena using the following command:

```bash
nix run github:oraios/serena -- start-mcp-server --transport stdio
```

You can also install Serena by referencing this repo (`github:oraios/serena`) and using it in your Nix flake. The package is exported as `serena`.

#### SSE Mode

ℹ️ Note that MCP servers which use stdio as a protocol are somewhat unusual as far as client/server architectures go, as the server
necessarily has to be started by the client in order for communication to take place via the server's standard input/output stream.
In other words, you do not need to start the server yourself. The client application (e.g. Claude Desktop) takes care of this and
therefore needs to be configured with a launch command.

When using instead the SSE mode, which uses HTTP-based communication, you control the server lifecycle yourself,
i.e. you start the server and provide the client with the URL to connect to it.

Simply provide `start-mcp-server` with the `--transport sse` option and optionally provide the port.
For example, to run the Serena MCP server in SSE mode on port 9121 using a local installation,
you would run this command from the Serena directory,

```shell
uv run serena start-mcp-server --transport sse --port 9121
```

and then configure your client to connect to `http://localhost:9121/sse`.

#### Command-Line Arguments

The Serena MCP server supports a wide range of additional command-line options, including the option to run in SSE mode
and to adapt Serena to various [contexts and modes of operation](#modes-and-contexts).

Run with parameter `--help` to get a list of available options.

### Configuration

Serena is very flexible in terms of configuration. While for most users, the default configurations will work,
you can fully adjust it to your needs by editing a few yaml files. You can disable tools, change Serena's instructions
(what we denote as the `system_prompt`), adjust the output of tools that just provide a prompt, and even adjust tool descriptions.

Serena is configured in four places:

1. The `serena_config.yml` for general settings that apply to all clients and projects.
   It is located in your user directory under `.serena/serena_config.yml`.
   If you do not explicitly create the file, it will be auto-generated when you first run Serena.
   You can edit it directly or use

   ```shell
   uvx --from git+https://github.com/oraios/serena serena config edit
   ```

   (or use the `--directory` command version).
2. In the arguments passed to the `start-mcp-server` in your client's config (see below),
   which will apply to all sessions started by the respective client. In particular, the [context](#contexts) parameter
   should be set appropriately for Serena to be best adjusted to existing tools and capabilities of your client.
   See for a detailed explanation. You can override all entries from the `serena_config.yml` through command line arguments.
3. In the `.serena/project.yml` file within your project. This will hold project-level configuration that is used whenever
   that project is activated. This file will be autogenerated when you first use Serena on that project, but you can also
   generate it explicitly with

   ```shell
   uvx --from git+https://github.com/oraios/serena serena project generate-yml
   ```

   (or use the `--directory` command version).
4. Through the context and modes. Explore the [modes and contexts](#modes-and-contexts) section for more details.

After the initial setup, continue with one of the sections below, depending on how you
want to use Serena.

### Project Activation & Indexing

If you are mostly working with the same project, you can configure to always activate it at startup
by passing `--project <path_or_name>` to the `start-mcp-server` command in your client's MCP config.
This is especially useful for clients which configure MCP servers on a per-project basis, like Claude Code.

Otherwise, the recommended way is to just ask the LLM to activate a project by providing it an absolute path to, or,
in case the project was activated in the past, by its name. The default project name is the directory name.

* "Activate the project /path/to/my_project"
* "Activate the project my_project"

All projects that have been activated will be automatically added to your `serena_config.yml`, and for each
project, the file `.serena/project.yml` will be generated. You can adjust the latter, e.g., by changing the name
(which you refer to during the activation) or other options. Make sure to not have two different projects with the
same name.

ℹ️ For larger projects, we recommend that you index your project to accelerate Serena's tools; otherwise the first
tool application may be very slow.
To do so, run this from the project directory (or pass the path to the project as an argument):

```shell
uvx --from git+https://github.com/oraios/serena serena project index
```

(or use the `--directory` command version).

### Claude Code

Serena is a great way to make Claude Code both cheaper and more powerful!

From your project directory, add serena with a command like this,

```shell
claude mcp add serena -- <serena-mcp-server> --context ide-assistant --project $(pwd)
```

where `<serena-mcp-server>` is your way of [running the Serena MCP server](#running-the-serena-mcp-server).
For example, when using `uvx`, you would run

```shell
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)
```

ℹ️ Serena comes with an instruction text, and Claude needs to read it to properly use Serena's tools.
  As of version `v1.0.52`, claude code reads the instructions of the MCP server, so this **is handled automatically**.
  If you are using an older version, or if Claude fails to read the instructions, you can ask it explicitly
  to "read Serena's initial instructions" or run `/mcp__serena__initial_instructions` to load the instruction text.
  If you want to make use of that, you will have to enable the corresponding tool explicitly by adding `initial_instructions` to the `included_optional_tools`
  in your config.
  Note that you may have to make Claude read the instructions when you start a new conversation and after any compacting operation to ensure Claude remains properly configured to use Serena's tools.

### Codex

Serena works with OpenAI's Codex CLI out of the box, but you have to use the `codex` context for it to work properly. (The technical reason is that Codex doesn't fully support the MCP specifications, so some massaging of tools is required.).

Unlike Claude Code, in Codex you add an MCP server globally and not per project. Add the following to
`~/.codex/config.toml` (create the file if it does not exist):

```toml
[mcp_servers.serena]
command = "uvx"
args = ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--context", "codex"]
```

After codex has started, you need to activate the project, which you can do by saying:

"Activate the current dir as project using serena"

> If you don't activate the project, you will not be able to use Serena's tools!

That's it! Have a look at `~/.codex/log/codex-tui.log` to see if any errors occurred.

The Serena dashboard will run if you have not disabled it in the configuration, but due to Codex's sandboxing the webbrowser
may not open automatically. You can open it manually by going to `http://localhost:24282/dashboard/index.html` (or a higher port, if
that was already taken).

> Codex will often show the tools as `failed` even though they are successfully executed. This is not a problem, seems to be a bug in Codex. Despite the error message, everything works as expected.

### Other Terminal-Based Clients

There are many terminal-based coding assistants that support MCP servers, such as [Codex](https://github.com/openai/codex?tab=readme-ov-file#model-context-protocol-mcp),
[Gemini-CLI](https://github.com/google-gemini/gemini-cli), [Qwen3-Coder](https://github.com/QwenLM/Qwen3-Coder),
[rovodev](https://community.atlassian.com/forums/Rovo-for-Software-Teams-Beta/Introducing-Rovo-Dev-CLI-AI-Powered-Development-in-your-terminal/ba-p/3043623),
the [OpenHands CLI](https://docs.all-hands.dev/usage/how-to/cli-mode) and [opencode](https://github.com/sst/opencode).

They generally benefit from the symbolic tools provided by Serena. You might want to customize some aspects of Serena
by writing your own context, modes or prompts to adjust it to your workflow, to other MCP servers you are using, and to
the client's internal capabilities.

### Claude Desktop

For [Claude Desktop](https://claude.ai/download) (available for Windows and macOS), go to File / Settings / Developer / MCP Servers / Edit Config,
which will let you open the JSON file `claude_desktop_config.json`.
Add the `serena` MCP server configuration, using a [run command](#running-the-serena-mcp-server) depending on your setup.

* local installation:

   ```json
   {
       "mcpServers": {
           "serena": {
               "command": "/abs/path/to/uv",
               "args": ["run", "--directory", "/abs/path/to/serena", "serena", "start-mcp-server"]
           }
       }
   }
   ```

* uvx:

   ```json
   {
       "mcpServers": {
           "serena": {
               "command": "/abs/path/to/uvx",
               "args": ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server"]
           }
       }
  }
  ```

* docker:

  ```json
   {
       "mcpServers": {
           "serena": {
               "command": "docker",
               "args": ["run", "--rm", "-i", "--network", "host", "-v", "/path/to/your/projects:/workspaces/projects", "ghcr.io/oraios/serena:latest", "serena", "start-mcp-server", "--transport", "stdio"]
           }
       }
   }
   ```

If you are using paths containing backslashes for paths on Windows
(note that you can also just use forward slashes), be sure to escape them correctly (`\\`).

That's it! Save the config and then restart Claude Desktop. You are ready for activating your first project.

ℹ️ You can further customize the run command using additional arguments (see [above](#command-line-arguments)).

Note: on Windows and macOS there are official Claude Desktop applications by Anthropic, for Linux there is an [open-source
community version](https://github.com/aaddrick/claude-desktop-debian).

⚠️ Be sure to fully quit the Claude Desktop application, as closing Claude will just minimize it to the system tray – at least on Windows.

⚠️ Some clients may leave behind zombie processes. You will have to find and terminate them manually then.
    With Serena, you can activate the [dashboard](#serenas-logs-the-dashboard-and-gui-tool) to prevent unnoted processes and also use the dashboard
    for shutting down Serena.

After restarting, you should see Serena's tools in your chat interface (notice the small hammer icon).

For more information on MCP servers with Claude Desktop, see [the official quick start guide](https://modelcontextprotocol.io/quickstart/user).

### MCP Coding Clients (Cline, Roo-Code, Cursor, Windsurf, etc.)

Being an MCP Server, Serena can be included in any MCP Client. The same configuration as above,
perhaps with small client-specific modifications, should work. Most of the popular
existing coding assistants (IDE extensions or VSCode-like IDEs) support connections
to MCP Servers. It is **recommended to use the `ide-assistant` context** for these integrations by adding `"--context", "ide-assistant"` to the `args` in your MCP client's configuration. Including Serena generally boosts their performance
by providing them tools for symbolic operations.

In this case, the billing for the usage continues to be controlled by the client of your choice
(unlike with the Claude Desktop client). But you may still want to use Serena through such an approach,
e.g., for one of the following reasons:

1. You are already using a coding assistant (say Cline or Cursor) and just want to make it more powerful.
2. You are on Linux and don't want to use the [community-created Claude Desktop](https://github.com/aaddrick/claude-desktop-debian).
3. You want tighter integration of Serena into your IDE and don't mind paying for that.

### Local GUIs and Frameworks

Over the last months, several technologies have emerged that allow you to run a powerful local GUI
and connect it to an MCP server. They will work with Serena out of the box.
Some of the leading open source GUI technologies offering this are
[Jan](https://jan.ai/docs/mcp), [OpenHands](https://github.com/All-Hands-AI/OpenHands/),
[OpenWebUI](https://docs.openwebui.com/openapi-servers/mcp) and [Agno](https://docs.agno.com/introduction/playground).
They allow combining Serena with almost any LLM (including locally running ones) and offer various other integrations.

## Detailed Usage and Recommendations

### Tool Execution

Serena combines tools for semantic code retrieval with editing capabilities and shell execution.
Serena's behavior can be further customized through [Modes and Contexts](#modes-and-contexts).
Find the complete list of tools [below](#full-list-of-tools).

The use of all tools is generally recommended, as this allows Serena to provide the most value:
Only by executing shell commands (in particular, tests) can Serena identify and correct mistakes
autonomously.

#### Shell Execution and Editing Tools

However, it should be noted that the `execute_shell_command` tool allows for arbitrary code execution.
When using Serena as an MCP Server, clients will typically ask the user for permission
before executing a tool, so as long as the user inspects execution parameters beforehand,
this should not be a problem.
However, if you have concerns, you can choose to disable certain commands in your project's
.yml configuration file.
If you only want to use Serena purely for analyzing code and suggesting implementations
without modifying the codebase, you can enable read-only mode by setting `read_only: true` in your project configuration file.
This will automatically disable all editing tools and prevent any modifications to your codebase while still
allowing all analysis and exploration capabilities.

In general, be sure to back up your work and use a version control system in order to avoid
losing any work.

### Modes and Contexts

Serena's behavior and toolset can be adjusted using contexts and modes.
These allow for a high degree of customization to best suit your workflow and the environment Serena is operating in.

#### Contexts

A context defines the general environment in which Serena is operating.
It influences the initial system prompt and the set of available tools.
A context is set at startup when launching Serena (e.g., via CLI options for an MCP server or in the agent script) and cannot be changed during an active session.

Serena comes with pre-defined contexts:

* `desktop-app`: Tailored for use with desktop applications like Claude Desktop. This is the default.
* `agent`: Designed for scenarios where Serena acts as a more autonomous agent, for example, when used with Agno.
* `ide-assistant`: Optimized for integration into IDEs like VSCode, Cursor, or Cline, focusing on in-editor coding assistance.
Choose the context that best matches the type of integration you are using.

When launching Serena, specify the context using `--context <context-name>`.
Note that for cases where parameter lists are specified (e.g. Claude Desktop), you must add two parameters to the list.

If you are using a local server (such as Llama.cpp) which requires you to use OpenAI-compatible tool descriptions, use context `oaicompat-agent` instead of `agent`.

#### Modes

Modes further refine Serena's behavior for specific types of tasks or interaction styles. Multiple modes can be active simultaneously, allowing you to combine their effects. Modes influence the system prompt and can also alter the set of available tools by excluding certain ones.

Examples of built-in modes include:

* `planning`: Focuses Serena on planning and analysis tasks.
* `editing`: Optimizes Serena for direct code modification tasks.
* `interactive`: Suitable for a conversational, back-and-forth interaction style.
* `one-shot`: Configures Serena for tasks that should be completed in a single response, often used with `planning` for generating reports or initial plans.
* `no-onboarding`: Skips the initial onboarding process if it's not needed for a particular session.
* `onboarding`: (Usually triggered automatically) Focuses on the project onboarding process.

Modes can be set at startup (similar to contexts) but can also be _switched dynamically_ during a session. You can instruct the LLM to use the `switch_modes` tool to activate a different set of modes (e.g., "switch to planning and one-shot modes").

When launching Serena, specify modes using `--mode <mode-name>`; multiple modes can be specified, e.g. `--mode planning --mode no-onboarding`.

:warning: **Mode Compatibility**: While you can combine modes, some may be semantically incompatible (e.g., `interactive` and `one-shot`). Serena currently does not prevent incompatible combinations; it is up to the user to choose sensible mode configurations.

#### Customization

You can create your own contexts and modes to precisely tailor Serena to your needs in two ways:

* You can use Serena's CLI to manage modes and contexts. Check out

    ```shell
    uvx --from git+https://github.com/oraios/serena serena mode --help
    ```

    and

    ```shell
    uvx --from git+https://github.com/oraios/serena serena context --help
    ```

    _NOTE_: Custom contexts/modes are simply YAML files in `<home>/.serena`, they are automatically registered and available for use by their name (filename without the `.yml` extension). If you don't want to use Serena's CLI, you can create and manage them in any way you see fit.
* **Using external YAML files**: When starting Serena, you can also provide an absolute path to a custom `.yml` file for a context or mode.

This customization allows for deep integration and adaptation of Serena to specific project requirements or personal preferences.

### Onboarding and Memories

By default, Serena will perform an **onboarding process** when
it is started for the first time for a project.
The goal of the onboarding is for Serena to get familiar with the project
and to store memories, which it can then draw upon in future interactions.
If an LLM should fail to complete the onboarding and does not actually write the
respective memories to disk, you may need to ask it to do so explicitly.

The onboarding will usually read a lot of content from the project, thus filling
up the context. It can therefore be advisable to switch to another conversation
once the onboarding is complete.
After the onboarding, we recommend that you have a quick look at the memories and,
if necessary, edit them or add additional ones.

**Memories** are files stored in `.serena/memories/` in the project directory,
which the agent can choose to read in subsequent interactions.
Feel free to read and adjust them as needed; you can also add new ones manually.
Every file in the `.serena/memories/` directory is a memory file.
Whenever Serena starts working on a project, the list of memories is
provided, and the agent can decide to read them.
We found that memories can significantly improve the user experience with Serena.

### Prepare Your Project

#### Structure Your Codebase

Serena uses the code structure for finding, reading and editing code. This means that it will
work well with well-structured code but may perform poorly on fully unstructured one (like a "God class"
with enormous, non-modular functions).
Furthermore, for languages that are not statically typed, type annotations are highly beneficial.

#### Start from a Clean State

It is best to start a code generation task from a clean git state. Not only will
this make it easier for you to inspect the changes, but also the model itself will
have a chance of seeing what it has changed by calling `git diff` and thereby
correct itself or continue working in a followup conversation if needed.

:warning: **Important**: since Serena will write to files using the system-native line endings
and it might want to look at the git diff, it is important to
set `git config core.autocrlf` to `true` on Windows.
With `git config core.autocrlf` set to `false` on Windows, you may end up with huge diffs
only due to line endings. It is generally a good idea to globally enable this git setting on Windows:

```shell
git config --global core.autocrlf true
```

#### Logging, Linting, and Automated Tests

Serena can successfully complete tasks in an _agent loop_, where it iteratively
acquires information, performs actions, and reflects on the results.
However, Serena cannot use a debugger; it must rely on the results of program executions,
linting results, and test results to assess the correctness of its actions.
Therefore, software that is designed to meaningful interpretable outputs (e.g. log messages)
and that has a good test coverage is much easier to work with for Serena.

We generally recommend to start an editing task from a state where all linting checks and tests pass.

### Prompting Strategies

We found that it is often a good idea to spend some time conceptualizing and planning a task
before actually implementing it, especially for non-trivial task. This helps both in achieving
better results and in increasing the feeling of control and staying in the loop. You can
make a detailed plan in one session, where Serena may read a lot of your code to build up the context,
and then continue with the implementation in another (potentially after creating suitable memories).

### Potential Issues in Code Editing

In our experience, LLMs are bad at counting, i.e. they have problems
inserting blocks of code in the right place. Most editing operations can be performed
at the symbolic level, allowing this problem is overcome. However, sometimes,
line-level insertions are useful.

Serena is instructed to double-check the line numbers and any code blocks that it will
edit, but you may find it useful to explicitly tell it how to edit code if you run into
problems.
We are working on making Serena's editing capabilities more robust.

### Running Out of Context

For long and complicated tasks, or tasks where Serena has read a lot of content, you
may come close to the limits of context tokens. In that case, it is often a good idea to continue
in a new conversation. Serena has a dedicated tool to create a summary of the current state
of the progress and all relevant info for continuing it. You can request to create this summary and
write it to a memory. Then, in a new conversation, you can just ask Serena to read the memory and
continue with the task. In our experience, this worked really well. On the up-side, since in a
single session there is no summarization involved, Serena does not usually get lost (unlike some
other agents that summarize under the hood), and it is also instructed to occasionally check whether
it's on the right track.

Moreover, Serena is instructed to be frugal with context
(e.g., to not read bodies of code symbols unnecessarily),
but we found that Claude is not always very good in being frugal (Gemini seemed better at it).
You can explicitly instruct it to not read the bodies if you know that it's not needed.

### Combining Serena with Other MCP Servers

When using Serena through an MCP Client, you can use it together with other MCP servers.
However, beware of tool name collisions! See info on that above.

Currently, there is a collision with the popular Filesystem MCP Server. Since Serena also provides
filesystem operations, there is likely no need to ever enable these two simultaneously.

### Serena's Logs: The Dashboard and GUI Tool

Serena provides two convenient ways of accessing the logs of the current session:

* via the **web-based dashboard** (enabled by default)

    This is supported on all platforms.
    By default, it will be accessible at `http://localhost:24282/dashboard/index.html`,
    but a higher port may be used if the default port is unavailable/multiple instances are running.

* via the **GUI tool** (disabled by default)

    This is mainly supported on Windows, but it may also work on Linux; macOS is unsupported.

Both can be enabled, configured or disabled in Serena's configuration file (`serena_config.yml`, see above).
If enabled, they will automatically be opened as soon as the Serena agent/MCP server is started.
The web dashboard will display usage statistics of Serena's tools if you set  `record_tool_usage_stats: True` in your config.

In addition to viewing logs, both tools allow to shut down the Serena agent.
This function is provided, because clients like Claude Desktop may fail to terminate the MCP server subprocess
when they themselves are closed.

### Troubleshooting

Support for MCP Servers in Claude Desktop and the various MCP Server SDKs are relatively new developments and may display instabilities.

The working configuration of an MCP server may vary from platform to
platform and from client to client. We recommend always using absolute paths, as relative paths may be sources of
errors. The language server is running in a separate sub-process and is called with asyncio – sometimes
a client may make it crash. If you have Serena's log window enabled, and it disappears, you'll know what happened.

Some clients may not properly terminate MCP servers, look out for hanging python processes and terminate them manually, if needed.

## Comparison with Other Coding Agents

To our knowledge, Serena is the first fully-featured coding agent where the
entire functionality
is available through an MCP server, thus not requiring API keys or
subscriptions.

### Subscription-Based Coding Agents

Many prominent subscription-based coding agents are parts of IDEs like
Windsurf, Cursor and VSCode.
Serena's functionality is similar to Cursor's Agent, Windsurf's Cascade or
VSCode's agent mode.

Serena has the advantage of not requiring a subscription.
A potential disadvantage is that it
is not directly integrated into an IDE, so the inspection of newly written code
is not as seamless.

More technical differences are:

* Serena is not bound to a specific IDE or CLI.
  Serena's MCP server can be used with any MCP client (including some IDEs),
  and the Agno-based agent provides additional ways of applying its functionality.
* Serena is not bound to a specific large language model or API.
* Serena navigates and edits code using a language server, so it has a symbolic
  understanding of the code.
  IDE-based tools often use a RAG-based or purely text-based approach, which is often
  less powerful, especially for large codebases.
* Serena is open-source and has a small codebase, so it can be easily extended
  and modified.

### API-Based Coding Agents

An alternative to subscription-based agents are API-based agents like Claude
Code, Cline, Aider, Roo Code and others, where the usage costs map directly
to the API costs of the underlying LLM.
Some of them (like Cline) can even be included in IDEs as an extension.
They are often very powerful and their main downside are the (potentially very
high) API costs.

Serena itself can be used as an API-based agent (see the section on Agno above).
We have not yet written a CLI tool or a
dedicated IDE extension for Serena (and there is probably no need for the latter, as
Serena can already be used with any IDE that supports MCP servers).
If there is demand for a Serena as a CLI tool like Claude Code, we will
consider writing one.

The main difference between Serena and other API-based agents is that Serena can
also be used as an MCP server, thus not requiring
an API key and bypassing the API costs. This is a unique feature of Serena.

### Other MCP-Based Coding Agents

There are other MCP servers designed for coding, like [DesktopCommander](https://github.com/wonderwhy-er/DesktopCommanderMCP) and
[codemcp](https://github.com/ezyang/codemcp).
However, to the best of our knowledge, none of them provide semantic code
retrieval and editing tools; they rely purely on text-based analysis.
It is the integration of language servers and the MCP that makes Serena unique
and so powerful for challenging coding tasks, especially in the context of
larger codebases.

## Acknowledgements

We built Serena on top of multiple existing open-source technologies, the most important ones being:

1. [multilspy](https://github.com/microsoft/multilspy).
   A library which wraps language server implementations and adapts them for interaction via Python
   and which provided the basis for our library Solid-LSP (src/solidlsp).
   Solid-LSP provides pure synchronous LSP calls and extends the original library with the symbolic logic
   that Serena required.
2. [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
3. [Agno](https://github.com/agno-agi/agno) and
   the associated [agent-ui](https://github.com/agno-agi/agent-ui),
   which we use to allow Serena to work with any model, beyond the ones
   supporting the MCP.
4. All the language servers that we use through Solid-LSP.

Without these projects, Serena would not have been possible (or would have been significantly more difficult to build).

## Customizing and Extending Serena

It is straightforward to extend Serena's AI functionality with your own ideas.
Simply implement a new tool by subclassing
`serena.agent.Tool` and implement the `apply` method with a signature
that matches the tool's requirements.
Once implemented, `SerenaAgent` will automatically have access to the new tool.

It is also relatively straightforward to add [support for a new programming language](/.serena/memories/adding_new_language_support_guide.md).

We look forward to seeing what the community will come up with!
For details on contributing, see [contributing guidelines](/CONTRIBUTING.md).

## List of Tools

Here is the list of Serena's default tools with a short description (output of `uv run serena tools list`):

* `activate_project`: Activates a project by name.
* `check_onboarding_performed`: Checks whether project onboarding was already performed.
* `create_text_file`: Creates/overwrites a file in the project directory.
* `delete_memory`: Deletes a memory from Serena's project-specific memory store.
* `execute_shell_command`: Executes a shell command.
* `find_file`: Finds files in the given relative paths
* `find_referencing_symbols`: Finds symbols that reference the symbol at the given location (optionally filtered by type).
* `find_symbol`: Performs a global (or local) search for symbols with/containing a given name/substring (optionally filtered by type).
* `get_symbols_overview`: Gets an overview of the top-level symbols defined in a given file.
* `insert_after_symbol`: Inserts content after the end of the definition of a given symbol.
* `insert_before_symbol`: Inserts content before the beginning of the definition of a given symbol.
* `list_dir`: Lists files and directories in the given directory (optionally with recursion).
* `list_memories`: Lists memories in Serena's project-specific memory store.
* `onboarding`: Performs onboarding (identifying the project structure and essential tasks, e.g. for testing or building).
* `prepare_for_new_conversation`: Provides instructions for preparing for a new conversation (in order to continue with the necessary context).
* `read_file`: Reads a file within the project directory.
* `read_memory`: Reads the memory with the given name from Serena's project-specific memory store.
* `replace_regex`: Replaces content in a file by using regular expressions.
* `replace_symbol_body`: Replaces the full definition of a symbol.
* `search_for_pattern`: Performs a search for a pattern in the project.
* `think_about_collected_information`: Thinking tool for pondering the completeness of collected information.
* `think_about_task_adherence`: Thinking tool for determining whether the agent is still on track with the current task.
* `think_about_whether_you_are_done`: Thinking tool for determining whether the task is truly completed.
* `write_memory`: Writes a named memory (for future reference) to Serena's project-specific memory store.

There are several tools that are disabled by default, and have to be enabled explicitly, e.g., through the context or modes.
Note that several of our default contexts do enable some of these tools. For example, the `desktop-app` context enables the `execute_shell_command` tool.

The full list of optional tools is (output of `uv run serena tools list --only-optional`):

* `delete_lines`: Deletes a range of lines within a file.
* `get_current_config`: Prints the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
* `initial_instructions`: Gets the initial instructions for the current project.
    Should only be used in settings where the system prompt cannot be set,
    e.g. in clients you have no control over, like Claude Desktop.
* `insert_at_line`: Inserts content at a given line in a file.
* `jet_brains_find_referencing_symbols`: Finds symbols that reference the given symbol
* `jet_brains_find_symbol`: Performs a global (or local) search for symbols with/containing a given name/substring (optionally filtered by type).
* `jet_brains_get_symbols_overview`: Retrieves an overview of the top-level symbols within a specified file
* `remove_project`: Removes a project from the Serena configuration.
* `replace_lines`: Replaces a range of lines within a file with new content.
* `restart_language_server`: Restarts the language server, may be necessary when edits not through Serena happen.
* `summarize_changes`: Provides instructions for summarizing the changes made to the codebase.
* `switch_modes`: Activates modes by providing a list of their names
