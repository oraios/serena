<p align="center" style="text-align:center">
  <img src="resources/serena-logo.svg#gh-light-mode-only" style="width:500px">
  <img src="resources/serena-logo-dark-mode.svg#gh-dark-mode-only" style="width:500px">
</p>

* :rocket: Serena is a powerful **coding agent toolkit** capable of turning an LLM into a fully-featured agent that works **directly on your codebase**.
* :wrench: Serena provides essential **semantic code retrieval and editing tools** that are akin to an IDE's capabilities, extracting code entities at the symbol level and exploiting relational structure.
* :free: Serena is **free & open-source**, enhancing the capabilities of LLMs you already have access to free of charge.

### Demonstration

Here is a demonstration of Serena implementing a small feature for itself (a better log GUI) with Claude Desktop.
Note how Serena's tools enable Claude to find and edit the right symbols.

https://github.com/user-attachments/assets/6eaa9aa1-610d-4723-a2d6-bf1e487ba753

### LLM Integration

Serena provides the necessary [tools](#full-list-of-tools) for coding workflows, but an LLM is required to do the actual work,
orchestrating tool use.

Serena can be integrated with an LLM in several ways:
 * by using the **model context protocol (MCP)**.  
   Serena provides an MCP server which integrates with 
     * Claude Desktop, 
     * IDEs like VSCode, Cursor or IntelliJ,
     * Extensions like Cline or Roo Code
     * Goose (for a nice CLI experience)
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
     * Java (_Note_: startup is slow, initial startup especially so)
     * TypeScript
 * indirect support (may require some code changes/manual installation) for:
     * Ruby (untested)
     * Go (untested)
     * C# (untested)
     * Rust (untested)
     * Kotlin (untested)
     * Dart (untested)
     * C/C++ (untested)
     
   These languages are supported by the language server library [multilspy](https://github.com/microsoft/multilspy), which Serena uses under the hood.
   But we did not explicitly test whether the support for these languages actually works.
       
Further languages can, in principle, easily be supported by providing a shallow adapter for a new language server
implementation.


## Table of Contents

<!-- Created with  markdown-toc -i README.md -->
<!-- Install it with npm install -g markdown-toc -->

<!-- toc -->

- [What Can I Use Serena For?](#what-can-i-use-serena-for)
- [Free Coding Agents with Serena](#free-coding-agents-with-serena)
- [Quick Start](#quick-start)
  * [Setup and Configuration](#setup-and-configuration)
  * [MCP Server (Claude Desktop)](#mcp-server-claude-desktop)
  * [Other MCP Clients - Cline, Roo-Code, Cursor, Windsurf etc.](#other-mcp-clients---cline-roo-code-cursor-windsurf-etc)
  * [Goose](#goose)
  * [Agno Agent](#agno-agent)
  * [Other Agent Frameworks](#other-agent-frameworks)
- [Serena's Tools and Configuration](#serenas-tools-and-configuration)
- [Comparison with Other Coding Agents](#comparison-with-other-coding-agents)
  * [Subscription-Based Coding Agents](#subscription-based-coding-agents)
  * [API-Based Coding Agents](#api-based-coding-agents)
  * [Other MCP-Based Coding Agents](#other-mcp-based-coding-agents)
- [Onboarding and Memories](#onboarding-and-memories)
- [Combination with Other MCP Servers](#combination-with-other-mcp-servers)
- [Recommendations on Using Serena](#recommendations-on-using-serena)
  * [Which Model to Choose?](#which-model-to-choose)
  * [Onboarding](#onboarding)
  * [Before Editing Code](#before-editing-code)
  * [Potential Issues in Code Editing](#potential-issues-in-code-editing)
  * [Running Out of Context](#running-out-of-context)
  * [Controlling Tool Execution](#controlling-tool-execution)
  * [Structuring Your Codebase](#structuring-your-codebase)
  * [Logging, Linting, and Testing](#logging-linting-and-testing)
  * [General Advice](#general-advice)
- [Troubleshooting](#troubleshooting)
  * [Serena Logging](#serena-logging)
- [Acknowledgements](#acknowledgements)
- [Customizing Serena](#customizing-serena)
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

- If you just want to turn Claude into a free-to-use coding agent, we recommend using Serena through Claude Desktop.
- If you want to use Gemini or any other model and you want a GUI experience, you should use [Agno](#agno-agent). On macOS you can also use the GUI of [goose](#goose).
- If you prefer using Serena through a CLI, you can use [goose](#goose). There again almost any model is possible.
- If you want to use Serena integrated in your IDE, see the section on [other MCP clients](#other-mcp-clients---cline-roo-code-cursor-windsurf-etc).

### Setup and Configuration

1. Install `uv` (instructions [here](https://docs.astral.sh/uv/getting-started/installation/))
2. Clone the repository to `/path/to/serena`.
3. Copy `serena_config.template.yml` to `serena_config.yml` and adjust settings.
   ```shell
   cp serena_config.template.yml serena_config.yml
   ```
4. Copy `project.template.yml` to `project.yml` and adjust the settings specific to your project
   (add one such file for each project you want Serena to work on). We recommend that you copy
   it to the `.serena` directory of your project, e.g.,
   ```shell
   mkdir -p /myproject/.serena
   cp project.template.yml /myproject/.serena/project.yml
   ```
6. If you want Serena to dynamically switch between projects, add the list of all project files
   created in the previous step to the `projects` list in `serena_config.yml`.

> ⚠️ **Note:** Serena is under active development. We are continuously adding features, improving stability and the UX.
> As a result, configuration may change in a breaking manner. If you have an invalid configuration,
> the MCP server or Serena-based Agent may fail to start (investigate the MCP logs in the former case).
> Check the [changelog](CHANGELOG.md)
> and the configuration templates when updating Serena, adapting your configurations accordingly.

After the initial setup, continue with one of the sections below, depending on how you
want to use Serena.

### MCP Server (Claude Desktop)

1. Create a configuration file for your project, say `myproject.yml` based on the template in [myproject.template.yml](myproject.template.yml).
2. Configure the MCP server in your client.  
   For [Claude Desktop](https://claude.ai/download) (available for Windows and macOS), go to File / Settings / Developer / MCP Servers / Edit Config,
   which will let you open the JSON file `claude_desktop_config.json`. Add the following (with adjusted paths) to enable Serena:

   ```json
   {
       "mcpServers": {
           "serena": {
               "command": "/abs/path/to/uv",
               "args": ["run", "--directory", "/abs/path/to/serena", "serena-mcp-server", "--project-file", "/abs/path/to/myproject.yml"]
           }
       }
   }
   ```
   
   :info: passing the project file is optional if you have set `enable_project_activation` in your configuration,
   as this setting will allow you to simply instruct Claude to activate the project you want to work on.

   If you are using paths containing backslashes for paths on Windows 
   (note that you can also just use forward slashes), be sure to escape them correctly (`\\`).

That's it! Save the config and then restart Claude Desktop.

#### Troubleshooting

Some client/OS/setup configurations were reported to cause issues when using Serena with the standard `stdio` protocol, where the MCP server is started by the client application. 
If you experience such problems, you can start Serena in `sse` mode by running, e.g.,

```shell
uv run --directory /path/to/serena serena-mcp-server --transport sse --port 9121 --project-file /path/to/project.yml
```
(the `--project-file` option is optional). Then configure your client to connect to `http://localhost:9121`.

Note: on Windows and macOS there are official Claude Desktop applications by Anthropic, for Linux there is an [open-source
community version](https://github.com/aaddrick/claude-desktop-debian).

⚠️ Be sure to fully quit the Claude Desktop application, as closing Claude will just minimize it to the system tray – at least on Windows.  

After restarting, you should see Serena's tools in your chat interface (notice the small hammer icon).

⚠️ Tool Names: Claude Desktop (and most MCP Clients) don't resolve the name of the server. So you shouldn't
say something like "use Serena's tools". Instead, you can instruct the LLM to use symbolic tools or to
use a particular tool by referring to its name. Moreover, if you use multiple MCP Servers, you might get
**tool name collisions** which lead to undefined behavior. For example, Serena is currently incompatible with the
[Filesystem MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) due to tool name
collisions.

ℹ️ Note that MCP servers which use stdio as a protocol are somewhat unusual as far as client/server architectures go, as the server
necessarily has to be started by the client in order for communication to take place via the server's standard input/output stream.
In other words, you do not need to start the server yourself. The client application (e.g. Claude Desktop) takes care of this and 
therefore needs to be configured with a launch command.

For more information on MCP servers with Claude Desktop, see [the official quick start guide](https://modelcontextprotocol.io/quickstart/user).

### Claude Code

Serena is a great way to make Claude Code both cheaper and more powerful! We are collecting
several examples for that and have heard very positive feedback so far. Claude Code users can
add serena with

```shell
claude mcp add serena -- /path/to/uv "run" --directory /path/to/serena serena-mcp-server --project-file /path/to/project.yml
```


### Other MCP Clients - Cline, Roo-Code, Cursor, Windsurf etc.

Being an MCP Server, Serena can be included in any MCP Client. The same config as above,
maybe with small client-specific modifications should work. Most of the popular
existing coding assistants (IDE extensions or VSCode-like IDEs) accept connecting
to MCP Servers. Including Serena generally boosts their performance
by providing them tools for symbolic operations.

In this case, the billing for the usage continues to be controlled by the client of your choice
(unlike with the Claude Desktop client). But you may still want to use Serena through such an approach,
e.g., for one of the following reasons:

1. You are already using a coding assistant (say Cline or Cursor) and just want to make it more powerful.
2. You are on Linux and don't want to use the [community-created Claude Desktop](https://github.com/aaddrick/claude-desktop-debian)
3. You want tighter integration of Serena into your IDE and don't mind paying for that

The same considerations as in using Serena for Claude Desktop (in particular, tool name collisions) 
also apply here.

When used in an IDE or extension that has inbuilt AI interactions for coding 
(which is, really, all of them), Serena's full set of tools may lead to unwanted interactions with
the clients internal tools that you as the user may have no control over. This holds especially for the editing tools, which you may want to disable for this purpose.
As we are gaining more experience with Serena used within the various popular clients, we will collect and enhance best practices that enable a smooth experience.

### Goose

[goose](https://github.com/block/goose) is a standalone coding agent which has an integration for MCP servers and offers a CLI (and a GUI on macOS). Using goose is currently the simplest way of running Serena through a CLI with an LLM of your choice.

Follow the instructions [here](https://block.github.io/goose/docs/getting-started/installation/) to install it.

After that, use `goose configure` to add an extension. For adding Serena, choose the option `Command-line Extension`, name it `Serena` and add the following as command:

```
/abs/path/to/uv run --directory /abs/path/to/serena serena-mcp-server /optional/abs/path/to/project.yml
```

Since Serena can do all necessary editing and command operations, you should disable the `developer` extension that goose enables by default.
For that execute

```shell
goose configure
```
again, choose the option `Toggle Extensions`, and make sure Serena is enabled selected while `developer` is not.

That's it. Read through the configuration options of goose to see what you can do with it (which is a lot, like setting different levels of permissions for tool execution).

> Goose does not seem to always properly terminate python processes for MCP servers when a session ends. 
> You may want to disable the Serena GUI and/or to manually cleanup any running python processes after finishing your work
> with goose.

### Agno Agent

Agno is a model-agnostic agent framework that allows you to turn Serena into an agent 
(independent of the MCP technology) with a large number of underlying LLMs. Agno is currently
the simplest way of running Serena in a chat GUI with an LLM of your choice 
(unless you are using a Mac, then you might prefer goose, which requires almost no setup).

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

5. Start the agno agent app with
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

The Agno agent is particularly nice because of the Agno UI, but it is easy to incorporate Serena into any
agent framework (like [pydantic-ai](https://ai.pydantic.dev/), [langgraph](https://langchain-ai.github.io/langgraph/tutorials/introduction/) or others).

You just have to write an adapter of Serena's tools to the tools in the framework of your choice, like
it was done by us for agno in the [SerenaAgnoToolkit](/src/serena/agno.py).

## Serena's Tools and Configuration

Serena combines tools for semantic code retrieval with editing capabilities and shell execution.
Find the complete list of tools [below](#serenas-tools-and-configuration).

The use of all tools is generally recommended, as this allows Serena to provide the most value:
Only by executing shell commands (in particular, tests) can Serena identify and correct mistakes 
autonomously.

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

## Onboarding and Memories

By default, Serena will perform an onboarding process when 
it is started for the first time for a project. 
The goal of the process is for Serena to get familiar with the project
and to store memories, which it can then draw upon in future interactions.

Memories are files stored in `.serena/memories/` in the project directory,
which the agent can choose to read.
Feel free to read and adjust them as needed; you can also add new ones manually.
Every file in the `.serena/memories/` directory is a memory file.

We found the memories to significantly improve the user experience with Serena.
By itself, Serena is instructed to create new memories whenever appropriate.

## Combination with Other MCP Servers

When using Serena through an MCP Client, you can use it together with other MCP servers.
However, beware of tool name collisions! See info on that above.

Currently, there is a collision with the popular Filesystem MCP Server. Since Serena also provides
filesystem operations, there is likely no need to ever enable these two simultaneously.

## Recommendations on Using Serena

We will continue to collect best practices as the Serena community grows. Below a
short overview of things that we learned when using Serena internally.

Most of these recommendations are true for any coding agent, including all agents
mentioned above.

### Which Model to Choose?

To our surprise, Serena seemed to work best with the non-thinking version
of Claude 3.7 vs its thinking version (we haven't yet made extensive comparisons to Gemini).
The thinking version took longer, had more difficulties in using the tools, and often would
just write code without reading enough context.

In our initial experiments, Gemini seemed to work very well. Unfortunately, Gemini does
not support the MCP (yet?), so the only way to use it is through an API-key. On the bright side,
Gemini is comparatively cheap and can handle huge context lengths. 


### Onboarding

In the very first interaction, Serena is instructed to perform an onboarding and
write the first memory files. Sometimes (depending on the LLM), the files are not
written to disk. In that case, just ask Serena to write the memories.

In this phase Serena will usually read and write quite a lot of text and thereby fill
up the context. We recommend that you switch to another conversation 
once the onboarding is performed in order to not run out of tokens. The onboarding will 
only be performed once, unless you explicitly trigger it.

After the onboarding, we recommend that you have a quick look at the memories and,
if necessary, edit them or add additional ones.

### Before Editing Code

It is best to start a code generation task from a clean git state. Not only will
this make it easier for you to inspect the changes, but also the model itself will
have a chance of seeing what it has changed by calling `git diff` and thereby
correct itself or continue working in a followup conversation if needed.

:warning: **Important**: since Serena will write to files using the system-native line endings
and it might want to look at the git diff, it is important to
set `git config core.autocrlf` to `true` on Windows.
With `git config core.autocrlf` set to `false` on Windows, you may end up with huge diffs
only due to line endings. It is generally a good idea to enable this git setting on Windows:

```shell
git config --global core.autocrlf true
```

### Potential Issues in Code Editing

In our experience, LLMs are really bad at counting, i.e. they have problems
inserting blocks of code in the right place. Most editing operations can be performed
on a symbolic level, allowing this problem is overcome. However, sometimes,
line-level insertions are useful.

Serena is instructed to double-check the line numbers and any code blocks that it will
edit, but you may find it useful to explicitly tell it how to edit code if you run into
problems.

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

### Controlling Tool Execution

Claude Desktop will ask you before executing a tool. For most tools you can just safely 
click on "Allow for this Chat", especially if all your files are under
version control. One exception is the `execute_shell_command` tool - there you might want
to inspect each call individually. We recommend reviewing each call to this command and
not enabling it for the whole chat.

### Structuring Your Codebase

Serena uses the code structure for finding, reading and editing code. This means that it will
work well with well-structured code but may fail with fully unstructured one (like a God-class
with enormous, non-modular functions). Type annotations also help a lot here. The better your code,
the better Serena will work. So we generally recommend you to write well-structured, modular and
typed code - it will not only help you but also help your AI ;).

### Logging, Linting, and Testing

Serena cannot debug (no coding assistant can do this at the moment, to our knowledge). This means
that for improving the results within an _agent loop_, Serena needs to acquire information by
executing tests, running scripts, performing linting and so on. It is often very helpful to include many log
messages with explicit information and to have meaningful tests. Especially the latter often help the agent
to self-correct.

We generally recommend to start an editing task from a state where all linting checks and tests pass.

### General Advice

We found that it is often a good idea to spend some time conceptualizing and planning a task
before actually implementing it, especially for non-trivial task. This helps both in achieving
better results and in increasing the feeling of control and staying in the loop. You can
make a detailed plan in one session, where Serena may read a lot of your code to build up the context,
and then continue with the implementation in another (potentially after creating suitable memories).



## Troubleshooting

The support for MCP Servers in Claude Desktop and the various MCP Server SDKs are relatively new developments and may display instabilities.

The working configuration of an MCP server may vary from platform to
platform and from client to client. We recommend always using absolute paths, as relative paths may be sources of
errors. The language server is running in a separate sub-process and is called with asyncio – sometimes
a client may make it crash. If you have Serena's log window enabled, and it disappears, you'll know what happened.

Some clients (like goose) may not properly terminate MCP servers,
look out for hanging python processes and terminate them 
manually, if needed.


### Serena Logging

To help with troubleshooting, we have written a small GUI utility for logging. For most clients, we recommend that you enable it
through the project configuration (`myproject.yml`) if you encounter problems. Many clients also write MCP logs that can help identify issues.

The logging GUI may not work for all clients and on all systems. Currently, it does not work on macOS or within VSCode extensions like Cline.


## Acknowledgements

We built Serena on top of multiple existing open-source technologies, the most important ones being:

1. [multilspy](https://github.com/microsoft/multilspy).
   A beautifully designed wrapper around language servers following the LSP. It
   was not easily extendable with the symbolic
   logic that Serena required, so instead of incorporating it as dependency, we
   copied the source code
   and adapted it to our needs.
2. [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
3. [Agno](https://github.com/agno-agi/agno) and
   the associated [agent-ui](https://github.com/agno-agi/agent-ui),
   which we use to allow Serena to work with any model, beyond the ones
   supporting the MCP.
4. All the language servers that we use through multilspy.

Without these projects, Serena would not have been possible (or would have been significantly more difficult to build).


## Customizing Serena

It is very easy to extend Serena's AI functionality with your own ideas. 
Just implement a new Tool by subclassing from
`serena.agent.Tool` and implement the `apply` method (not part of the interface, see
comment in `Tool`). By default, the `SerenaAgent` will immediately have access to it.

It is also relatively straightforward to add [support for a new language](/CONTRIBUTING.md#adding-a-new-supported-language). We look forward to seeing what the community will come up with! 
For details on contributing, see [here](/CONTRIBUTING.md).

## Full List of Tools

Here is the full list of Serena's tools with a short description (output of `uv run serena-list-tools`):

* `activate_project`: Activates a project by name.
* `check_onboarding_performed`: Checks whether the onboarding was already performed.
* `create_text_file`: Creates/overwrites a file in the project directory.
* `delete_lines`: Deletes a range of lines within a file.
* `delete_memory`: Deletes a memory from Serena's project-specific memory store.
* `execute_shell_command`: Executes a shell command.
* `find_referencing_code_snippets`: Finds code snippets in which the symbol at the given location is referenced.
* `find_referencing_symbols`: Finds symbols that reference the symbol at the given location (optionally filtered by type).
* `find_symbol`: Performs a global (or local) search for symbols with/containing a given name/substring (optionally filtered by type).
* `get_active_project`: Gets the name of the currently active project (if any) and lists existing projects
* `get_symbols_overview`: Gets an overview of the top-level symbols defined in a given file or directory.
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
* `think_about_collected_information`: Thinking tool for pondering the completeness of collected information.
* `think_about_task_adherence`: Thinking tool for determining whether the agent is still on track with the current task.
* `think_about_whether_you_are_done`: Thinking tool for determining whether the task is truly completed.
* `write_memory`: Writes a named memory (for future reference) to Serena's project-specific memory store.
