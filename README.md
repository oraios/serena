<p align="center" style="text-align:center">
  <img src="resources/serena-logo.svg#gh-light-mode-only" style="width:500px">
  <img src="resources/serena-logo-dark-mode.svg#gh-dark-mode-only" style="width:500px">
</p>

* :rocket: Serena is a powerful **coding agent toolkit** capable of turning an LLM into a fully-featured agent that works **directly on your codebase**.
* :wrench: Serena provides essential **semantic code retrieval and editing tools** that are akin to an IDE's capabilities, extracting code entities at the symbol level and exploiting relational structure. When combined with an existing coding agent, these tools greatly enhance (token) efficiency.
* :free: Serena is **free & open-source**, enhancing the capabilities of LLMs you already have access to free of charge.

### Demonstration

Here is a demonstration of Serena implementing a small feature for itself (a better log GUI) with Claude Desktop.
Note how Serena's tools enable Claude to find and edit the right symbols.

https://github.com/user-attachments/assets/6eaa9aa1-610d-4723-a2d6-bf1e487ba753

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

Serena provides the necessary [tools](#full-list-of-tools) for coding workflows, but an LLM is required to do the actual work,
orchestrating tool use.

For example, **supercharge the performance of Claude Code** with a [one-line shell command](#claude-code).

Serena can be integrated with an LLM in several ways:
 * by using the **model context protocol (MCP)**.  
   Serena provides an MCP server which integrates with 
     * Claude Code and Claude Desktop, 
     * IDEs like VSCode, Cursor or IntelliJ,
     * Extensions like Cline or Roo Code
     * and many others, including [the ChatGPT app soon](https://x.com/OpenAIDevs/status/1904957755829481737)
 * by using **Agno – the model-agnostic agent framework**.  
   Serena's Agno-based agent allows you to turn virtually any LLM into a coding agent, whether it's provided by Google, OpenAI or Anthropic (with a paid API key)
   or a free model provided by Ollama, Together or Anyscale.
 * by incorporating Serena's tools into an agent framework of your choice.  
   Serena's tool implementation is decoupled from the framework-specific code and can thus easily be adapted to any agent framework.

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
With Serena, we provide 
 * direct, out-of-the-box support for:
     * Python
     * TypeScript/Javascript (currently has some instability issues, we are working on it)
     * PHP
     * Go (need to install go and gopls first)
     * Rust
     * C# (requires dotnet to be installed. We switched the underlying language server recently, please report any issues you encounter)
     * Java (_Note_: startup is slow, initial startup especially so. There may be issues with java on macos and linux, we are working on it.)
     * Elixir (Requires NextLS and Elixir install; **Windows not supported** - Next LS does not provide Windows binaries)
     * Clojure
     * C/C++ (You may experience issues with finding references, we are working on it)
 * indirect support (may require some code changes/manual installation) for:
     * Ruby (untested)
     * Kotlin (untested)
     * Dart (untested)
 * custom language servers:
     * You can configure Serena to use any LSP-compliant language server by providing a simple command to start the server. This allows you to add support for any language that has a language server. See the `custom_lsp.template.yml` file in `src/serena/resources` for an example.
     
   These languages are supported by the language server library, but
   we did not explicitly test whether the support for these languages actually works flawlessly.
       
Further languages can, in principle, easily be supported by providing a shallow adapter for a new language server
implementation.


## Table of Contents

<!-- Created with markdown-toc -i README.md -->
<!-- Install it with npm install -g markdown-toc -->

<!-- toc -->

- [What Can I Use Serena For?](#what-can-i-use-serena-for)
- [Free Coding Agents with Serena](#free-coding-agents-with-serena)
- [Quick Start](#quick-start)
  * [Running the Serena MCP Server](#running-the-serena-mcp-server)
    + [Usage](#usage)
        * [Local Installation](#local-installation)
      - [Using uvx](#using-uvx)
      - [Using Docker (Experimental)](#using-docker-experimental)
    + [SSE Mode](#sse-mode)
    + [Command-Line Arguments](#command-line-arguments)
  * [Configuration](#configuration)
  * [Project Activation & Indexing](#project-activation--indexing)
  * [Claude Code](#claude-code)
  * [Claude Desktop](#claude-desktop)
  * [Other MCP Clients (Cline, Roo-Code, Cursor, Windsurf, etc.)](#other-mcp-clients-cline-roo-code-cursor-windsurf-etc)
  * [Agno Agent](#agno-agent)
  * [Other Agent Frameworks](#other-agent-frameworks)
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
- [Full List of Tools](#full-list-of-tools)

<!-- tocstop -->

## What Can I Use Serena For?

You can use Serena for any coding tasks – whether it is focussed on analysis, planning, 
designing new components or refactoring existing ones.
Since Serena's tools allow an LLM to close the cognitive perception-action loop, 
agents based on Serena can autonomously carry out coding tasks from start to finish – 
from the initial analysis to the implementation, testing and, finally, the version
control system commit.

Serena can read, write and execute code, read logs and the terminal output.
While we do not necessarily encourage it, "vibe coding" is certainly possible, and if you 
want to almost feel like "the code no longer exists",
you may find Serena even more adequate for vibing than an agent inside an IDE
(since you will have a separate GUI that really lets you forget).

## Free Coding Agents with Serena

Even the free tier of Anthropic's Claude has support for MCP Servers, so you can use Serena with Claude for free.
Presumably, the same will soon be possible with ChatGPT Desktop once support for MCP servers is added.  
Through Agno, you furthermore have the option to use Serena with a free/open-weights model.

Serena is [Oraios AI](https://oraios-ai.de/)'s contribution to the developer community.  
We use it ourselves on a regular basis.

We got tired of having to pay multiple
IDE-based subscriptions (such as Windsurf or Cursor) that forced us to keep purchasing tokens on top of the chat subscription costs we already had.
The substantial API costs incurred by tools like Claude Code, Cline, Aider and other API-based tools are similarly unattractive.
We thus built Serena with the prospect of being able to cancel most other subscriptions.

## Quick Start

Serena can be used in various ways, below you will find instructions for selected integrations.

- If you just want to turn Claude into a free-to-use coding agent, we recommend using Serena through [Claude Code](#claude-code) or [Claude Desktop](#claude-desktop).
- If you want to use Gemini or any other model, and you want a GUI experience, you can use [Agno](#agno-agent) or one of the many other GUIs that support MCP servers.
- If you want to use Serena integrated in your IDE, see the section on [other MCP clients](#other-mcp-clients---cline-roo-code-cursor-windsurf-etc).

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

###### Local Installation

1. Clone the repository and change into it.
   ```shell
   git clone https://github.com/oraios/serena
   cd serena
   ```
2. Optionally create the configuration file in your home directory, i.e.

      * `~/.serena/serena_config.yml` on Linux and macOS, or
      * `%USERPROFILE%\.serena\serena_config.yml` on Windows.  

   by copying the template and then adjusting it according to your needs:   
   ```shell
   mkdir ~/.serena
   cp src/serena/resources/serena_config.template.yml ~/.serena/serena_config.yml
   ```
   If you just want the default config, you can skip this part, and a config file will be created when you first run Serena.
3. Run the server with `uv`:
   ```shell
   uv run serena-mcp-server
   ```
   When running from outside the serena installation directory, be sure to pass it, i.e. use
   ```shell
    uv run --directory /abs/path/to/serena serena-mcp-server
    ```

##### Using uvx

`uvx` can be used to run the latest version of Serena directly from the repository, without an explicit local installation.

* Windows:
  ```shell
  uvx --from git+https://github.com/oraios/serena serena-mcp-server.exe
  ```
* Other operating systems:
  ```shell
  uvx --from git+https://github.com/oraios/serena serena-mcp-server
  ```

##### Using Docker (Experimental)

⚠️ Docker support is currently experimental with several limitations. Please read the [Docker documentation](DOCKER.md) for important caveats before using it.

You can run the Serena MCP server directly via docker as follows,
assuming that the projects you want to work on are all located in `/path/to/your/projects`:

```shell
docker run --rm -i --network host -v /path/to/your/projects:/workspaces/projects ghcr.io/oraios/serena:latest serena-mcp-server --transport stdio
```

Replace `/path/to/your/projects` with the absolute path to your projects directory. The Docker approach provides:
- Better security isolation for shell command execution
- No need to install language servers and dependencies locally
- Consistent environment across different systems

See the [Docker documentation](DOCKER.md) for detailed setup instructions, configuration options, and known limitations.

#### SSE Mode

ℹ️ Note that MCP servers which use stdio as a protocol are somewhat unusual as far as client/server architectures go, as the server
necessarily has to be started by the client in order for communication to take place via the server's standard input/output stream.
In other words, you do not need to start the server yourself. The client application (e.g. Claude Desktop) takes care of this and
therefore needs to be configured with a launch command. 

When using instead the SSE mode, which uses HTTP-based communication, you control the server lifecycle yourself,
i.e. you start the server and provide the client with the URL to connect to it.

Simply provide `serena-mcp-server` with the `--transport sse` option and optionally provide the port.
For example, to run the Serena MCP server in SSE mode on port 9121 using a local installation,
you would run this command from the Serena directory, 

```shell
uv run serena-mcp-server --transport sse --port 9121
```

and then configure your client to connect to `http://localhost/sse:9121`.


#### Command-Line Arguments

The Serena MCP server supports a wide range of additional command-line options, including the option to run in SSE mode
and to adapt Serena to various [contexts and modes of operation](#modes-and-contexts).

Run with parameter `--help` to get a list of available options.


### Configuration

Serena's behavior (active tools and prompts as well as logging configuration, etc.) is configured in four places:

1. The `serena_config.yml` for general settings that apply to all clients and projects.
   It is located in your user directory under `.serena/serena_config.yml`.
   If you do not explicitly create the file, it will be auto-generated when you first run Serena.
2. In the arguments passed to the `serena-mcp-server` in your client's config (see below), 
   which will apply to all sessions started by the respective client. In particular, the [context](#contexts) parameter
   should be set appropriately for Serena to be best adjusted to existing tools and capabilities of your client.
   See for a detailed explanation. You can override all entries from the `serena_config.yml` through command line arguments.
3. In the `.serena/project.yml` file within your project. This will hold project-level configuration that is used whenever
   that project is activated.
4. Through the currently active set of [modes](#modes).


> ⚠️ **Note:** Serena is under active development. We are continuously adding features, improving stability and the UX.
> As a result, configuration may change in a breaking manner. If you have an invalid configuration,
> the MCP server or Serena-based Agent may fail to start (investigate the MCP logs in the former case).
> Check the [changelog](CHANGELOG.md)
> and the configuration templates when updating Serena, adapting your configurations accordingly.

After the initial setup, continue with one of the sections below, depending on how you
want to use Serena.

You can just ask the LLM to show you the config of your session, Serena has a tool for it.

### Project Activation & Indexing

The recommended way is to just ask the LLM to activate a project by providing it an absolute path to, or,
in case the project was activated in the past, by its name. The default project name is the directory name.

  * "Activate the project /path/to/my_project"
  * "Activate the project my_project"

All projects that have been activated will be automatically added to your `serena_config.yml`, and for each 
project, the file `.serena/project.yml` will be generated. You can adjust the latter, e.g., by changing the name
(which you refer to during the activation) or other options. Make sure to not have two different projects with the
same name.

If you are mostly working with the same project, you can also configure to always activate a project at startup
by passing `--project <path_or_name>` to the `serena-mcp-server` command in your client's MCP config.

ℹ️ For larger projects, we recommend that you index your project to accelerate Serena's tools; otherwise the first
tool application may be very slow.
To do so, run one of these commands the project directory or pass the path to the project as an argument:

* When using a local installation:
  ```shell
  uv run --directory /abs/path/to/serena index-project
  ```
* When using uvx:
  ```shell
  uvx --from git+https://github.com/oraios/serena index-project
  ```

### Claude Code

Serena is a great way to make Claude Code both cheaper and more powerful! 

From your project directory, add serena with a command like this,

```shell
claude mcp add serena -- <serena-mcp-server> --context ide-assistant --project $(pwd)
```

where `<serena-mcp-server>` is your way of [running the Serena MCP server](#running-the-serena-mcp-server).
For example, when using `uvx`, you would run
```shell
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena-mcp-server --context ide-assistant --project $(pwd)
```

ℹ️ Serena comes with an instruction text, and Claude needs to read it to properly use Serena's tools. 
  Once in Claude Code, you can ask to "read Serena's initial instructions" or run `/mcp__serena__initial_instructions` to load the instruction text. 
  Do this whenever you start a new conversation and after any compacting operation to ensure Claude remains properly configured to use Serena's tools.

ℹ️ **NEW**: an alternative to the above is adding the instructions as part of the system prompt, then you will not need to run the command above or to remember re-running it after compacting.
  This can be achieved through starting claude code with `claude --append-system-prompt $(uvx --from git+https://github.com/oraios/serena serena print-system-prompt)`. Note that this is **experimental**, Claude may not understand the instructions correctly in this way, and we haven't thoroughly tested the resulting behavior. Please report any issues you encounter.


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
               "args": ["run", "--directory", "/abs/path/to/serena", "serena-mcp-server"]
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
               "args": ["--from", "git+https://github.com/oraios/serena", "serena-mcp-server"]
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
               "args": ["run", "--rm", "-i", "--network", "host", "-v", "/path/to/your/projects:/workspaces/projects", "ghcr.io/oraios/serena:latest", "serena-mcp-server", "--transport", "stdio"]
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

⚠️ Some clients, currently including Claude Desktop, may leave behind zombie processes. You will have to find and terminate them manually then.
    With Serena, you can activate the [dashboard](#serenas-logs-the-dashboard-and-gui-tool) to prevent unnoted processes and also use the dashboard
    for shutting down Serena.

After restarting, you should see Serena's tools in your chat interface (notice the small hammer icon).

For more information on MCP servers with Claude Desktop, see [the official quick start guide](https://modelcontextprotocol.io/quickstart/user).

### Other MCP Clients (Cline, Roo-Code, Cursor, Windsurf, etc.)

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

### Agno Agent

Agno is a model-agnostic agent framework that allows you to turn Serena into an agent 
(independent of the MCP technology) with a large number of underlying LLMs. Agno is currently
the simplest way of running Serena in a chat GUI with an LLM of your choice.

While Agno is not yet entirely stable, we chose it, because it comes with its own open-source UI, 
making it easy to directly use the agent using a chat interface.  With Agno, Serena is turned into an agent
(so no longer an MCP Server), so it can be used in programmatic ways (for example for benchmarking or within 
your application).

Here's how it works (see also [Agno's documentation](https://docs.agno.com/introduction/playground)):

1. Download the agent-ui code with npx
   ```shell
   npx create-agent-ui@latest
   ```
   or, alternatively, clone it manually:
   ```shell
   git clone https://github.com/agno-agi/agent-ui.git
   cd agent-ui 
   pnpm install 
   pnpm dev
   ```

2. Install serena with the optional requirements:
   ```shell
   # You can also only select agno,google or agno,anthropic instead of all-extras
   uv pip install --all-extras -r pyproject.toml -e .
   ```
   
3. Copy `.env.example` to `.env` and fill in the API keys for the provider(s) you
   intend to use.

4. Start the agno agent app with
   ```shell
   uv run python scripts/agno_agent.py
   ```
   By default, the script uses Claude as the model, but you can choose any model
   supported by Agno (which is essentially any existing model).

5. In a new terminal, start the agno UI with
   ```shell
   cd agent-ui 
   pnpm dev
   ```
   Connect the UI to the agent you started above and start chatting. You will have
   the same tools as in the MCP server version.


Here is a short demo of Serena performing a small analysis task with the newest Gemini model:

https://github.com/user-attachments/assets/ccfcb968-277d-4ca9-af7f-b84578858c62


⚠️ IMPORTANT: In contrast to the MCP server approach, tool execution in the Agno UI does
not ask for the user's permission. The shell tool is particularly critical, as it can perform arbitrary code execution. 
While we have never encountered any issues with
this in our testing with Claude, allowing this may not be entirely safe. 
You may choose to disable certain tools for your setup in your Serena project's
configuration file (`.yml`).

### Other Agent Frameworks

It should be straightforward to incorporate Serena into any
agent framework (like [pydantic-ai](https://ai.pydantic.dev/), [langgraph](https://langchain-ai.github.io/langgraph/tutorials/introduction/) or others).
Typically, you need only to write an adapter for Serena's tools to the tool representation in the framework of your choice, 
as was done by us for Agno with [SerenaAgnoToolkit](/src/serena/agno.py).


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
*   `desktop-app`: Tailored for use with desktop applications like Claude Desktop. This is the default.
*   `agent`: Designed for scenarios where Serena acts as a more autonomous agent, for example, when used with Agno.
*   `ide-assistant`: Optimized for integration into IDEs like VSCode, Cursor, or Cline, focusing on in-editor coding assistance.
Choose the context that best matches the type of integration you are using.

When launching Serena, specify the context using `--context <context-name>`.  
Note that for cases where parameter lists are specified (e.g. Claude Desktop), you must add two parameters to the list.

#### Modes

Modes further refine Serena's behavior for specific types of tasks or interaction styles. Multiple modes can be active simultaneously, allowing you to combine their effects. Modes influence the system prompt and can also alter the set of available tools by excluding certain ones.

Examples of built-in modes include:
*   `planning`: Focuses Serena on planning and analysis tasks.
*   `editing`: Optimizes Serena for direct code modification tasks.
*   `interactive`: Suitable for a conversational, back-and-forth interaction style.
*   `one-shot`: Configures Serena for tasks that should be completed in a single response, often used with `planning` for generating reports or initial plans.
*   `no-onboarding`: Skips the initial onboarding process if it's not needed for a particular session.
*   `onboarding`: (Usually triggered automatically) Focuses on the project onboarding process.

Modes can be set at startup (similar to contexts) but can also be *switched dynamically* during a session. You can instruct the LLM to use the `switch_modes` tool to activate a different set of modes (e.g., "switch to planning and one-shot modes").

When launching Serena, specify modes using `--mode <mode-name>`; multiple modes can be specified, e.g. `--mode planning --mode no-onboarding`.

:warning: **Mode Compatibility**: While you can combine modes, some may be semantically incompatible (e.g., `interactive` and `one-shot`). Serena currently does not prevent incompatible combinations; it is up to the user to choose sensible mode configurations.

#### Customization

You can create your own contexts and modes to precisely tailor Serena to your needs in two ways:
*  **Adding to Serena's configuration directory**: Create new `.yml` files in the `config/contexts/` or `config/modes/` directories within your local Serena repository. These custom contexts/modes will be automatically registered and available for use by their name (filename without the `.yml` extension). They will also appear in listings of available contexts/modes.
*  **Using external YAML files**: When starting Serena, you can provide an absolute path to a custom `.yml` file for a context or mode.

A context or mode YAML file typically defines:
*   `name`: (Optional if filename is used) The name of the context/mode.
*   `prompt`: A string that will be incorporated into Serena's system prompt.
*   `description`: (Optional) A brief description.
*   `excluded_tools`: A list of tool names (strings) to disable when this context/mode is active.

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

The most prominent subscription-based coding agents are parts of IDEs like
Windsurf, Cursor and VSCode.
Serena's functionality is similar to Cursor's Agent, Windsurf's Cascade or
VSCode's
upcoming [agent mode](https://code.visualstudio.com/blogs/2025/02/24/introducing-copilot-agent-mode).

Serena has the advantage of not requiring a subscription.
A potential disadvantage is that it
is not directly integrated into an IDE, so the inspection of newly written code
is not as seamless.

More technical differences are:
* Serena is not bound to a specific IDE.
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

It is also relatively straightforward to add [support for a new programming language](/CONTRIBUTING.md#adding-a-new-supported-language). 

We look forward to seeing what the community will come up with! 
For details on contributing, see [here](/CONTRIBUTING.md).

## Full List of Tools

Here is the full list of Serena's tools with a short description (output of `uv run serena-list-tools`):

 * `activate_project`: Activates a project by name.
 * `check_onboarding_performed`: Checks whether project onboarding was already performed.
 * `create_text_file`: Creates/overwrites a file in the project directory.
 * `delete_lines`: Deletes a range of lines within a file.
 * `delete_memory`: Deletes a memory from Serena's project-specific memory store.
 * `execute_shell_command`: Executes a shell command.
 * `find_referencing_code_snippets`: Finds code snippets in which the symbol at the given location is referenced.
 * `find_referencing_symbols`: Finds symbols that reference the symbol at the given location (optionally filtered by type).
 * `find_symbol`: Performs a global (or local) search for symbols with/containing a given name/substring (optionally filtered by type).
 * `get_active_project`: Gets the name of the currently active project (if any) and lists existing projects
 * `get_current_config`: Prints the current configuration of the agent, including the active modes, tools, and context.
 * `get_symbols_overview`: Gets an overview of the top-level symbols defined in a given file or directory.
 * `initial_instructions`: Gets the initial instructions for the current project.
    Should only be used in settings where the system prompt cannot be set,
    e.g. in clients you have no control over, like Claude Desktop.
 * `insert_after_symbol`: Inserts content after the end of the definition of a given symbol.
 * `insert_at_line`: Inserts content at a given line in a file.
 * `insert_before_symbol`: Inserts content before the beginning of the definition of a given symbol.
 * `list_dir`: Lists files and directories in the given directory (optionally with recursion).
 * `list_memories`: Lists memories in Serena's project-specific memory store.
 * `onboarding`: Performs onboarding (identifying the project structure and essential tasks, e.g. for testing or building).
 * `prepare_for_new_conversation`: Provides instructions for preparing for a new conversation (in order to continue with the necessary context).
 * `read_file`: Reads a file within the project directory.
 * `read_memory`: Reads the memory with the given name from Serena's project-specific memory store.
 * `replace_lines`: Replaces a range of lines within a file with new content.
 * `replace_symbol_body`: Replaces the full definition of a symbol.
 * `restart_language_server`: Restarts the language server, may be necessary when edits not through Serena happen.
 * `search_for_pattern`: Performs a search for a pattern in the project.
 * `summarize_changes`: Provides instructions for summarizing the changes made to the codebase.
 * `switch_modes`: Activates modes by providing a list of their names
 * `think_about_collected_information`: Thinking tool for pondering the completeness of collected information.
 * `think_about_task_adherence`: Thinking tool for determining whether the agent is still on track with the current task.
 * `think_about_whether_you_are_done`: Thinking tool for determining whether the task is truly completed.
 * `write_memory`: Writes a named memory (for future reference) to Serena's project-specific memory store.

