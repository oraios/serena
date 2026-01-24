# Connecting Your MCP Client

In the following, we provide general instructions on how to connect Murena to your MCP-enabled client,
as well as specific instructions for popular clients.

:::{note}
The configurations we provide for particular clients below will run the latest version of Murena
using the `stdio` protocol with `uvx`.  
Adapt the commands to your preferred way of [running Murena](020_running), adding any additional
command-line arguments as needed.
:::

(clients-general-instructions)=
## General Instructions

In general, Murena can be used with any MCP-enabled client.
To connect Murena to your favourite client, simply

1. determine how to add a custom MCP server to your client (refer to the client's documentation).
2. add a new MCP server entry by specifying either
    * a [run command](start-mcp-server) that allows the client to start the MCP server in stdio mode as a subprocess, or
    * the URL of the HTTP/SSE endpoint, having started the [Murena MCP server in HTTP/SSE mode](streamable-http) beforehand.

Find concrete examples for popular clients below.

Depending on your needs, you might want to further customize Murena's behaviour by
* [adding command-line arguments](mcp-args)
* [adjusting configuration](050_configuration).

**Mode of Operation**.
Note that some clients have a per-workspace MCP configuration (e.g, VSCode and Claude Code),
while others have a global MCP configuration (e.g. Codex and Claude Desktop).

- In the per-workspace case, you typically want to start Murena with your workspace directory as the project directory 
  and never switch to a different project. This is achieved by specifying the
  `--project <path>` argument with a single-project [context](#contexts) (e.g. `ide` or `claude-code`).
- In the global configuration case, you must first activate the project you want to work on, which you can do by asking
  the LLM to do so (e.g., "Activate the current dir as project using murena"). In such settings, the `activate_project`
  tool is required.

**Tool Selection**.
While you may be able to turn off tools through your client's interface (e.g., in VSCode or Claude Desktop),
we recommend selecting your base tool set through Murena's configuration, as Murena's prompts automatically
adjust based on which tools are enabled/disabled.  
A key mechanism for this is to use the appropriate [context](#contexts) when starting Murena.

(clients-common-pitfalls)=
### Common Pitfalls

**Escaping Paths Correctly**.
Note that if your client configuration uses JSON, special characters (like backslashes) need to be escaped properly.
In particular, if you are specifying paths containing backslashes on Windows
(note that you can also just use forward slashes), be sure to escape them correctly (`\\`).

**Discoverability of `uvx`**.
Your client may not find the `uvx` command, even if it is on your system PATH.
In this case, a workaround is to provide the full path to the `uvx` executable.

**Environment Variables**.
Some language servers may require additional environment variables to be set (e.g. F# on macOS with Homebrew),
which you may need to explicitly add to the MCP server configuration.
Note that for some clients (e.g. Claude Desktop), the spawned MCP server process may not inherit environment variables that
are only configured in your shell profile (e.g. `.bashrc`, `.zshrc`, etc.); they would need to be set system-wide instead.
An easy fix is to add them explicitly to the MCP server entry.
For example, in Claude Desktop and other clients, you can simply add an `env` key to the `murena`
object, e.g.

```
"env": {
    "DOTNET_ROOT": "/opt/homebrew/Cellar/dotnet/9.0.8/libexec"
}
```

## Claude Code

Murena is a great way to make Claude Code both cheaper and more powerful!

**Per-Project Configuration.** To add the Murena MCP server to the current project in the current directory, 
use this command:

```shell
claude mcp add murena -- uvx --from git+https://github.com/oraios/murena murena start-mcp-server --context claude-code --project "$(pwd)"
```

Note:
  * We use the `claude-code` context to disable unnecessary tools (avoiding duplication
    with Claude Code's built-in capabilities).
  * We specify the current directory as the project directory with `--project "$(pwd)"`, such 
    that Murena is configured to work on the current project from the get-go, following 
    Claude Code's mode of operation.

**Global Configuration**. Alternatively, use `--project-from-cwd` for user-level configuration that works across all projects:

```shell
claude mcp add --scope user murena -- uvx --from git+https://github.com/oraios/murena murena start-mcp-server --context=claude-code --project-from-cwd
```

Whenever you start Claude Code, Murena will search up from the current directory for `.murena/project.yml` or `.git` markers,
activating the current directory as the project if neither is found. 
This mechanism makes it suitable for a single global MCP configuration.

**Maximum Token Efficiency.** To maximize token efficiency, you may want to use Claude Code's 
*on-demand tool loading* feature, which is supported since at least v2.0.74 of Claude Code.
This feature avoids sending all tool descriptions to Claude upon startup, thus saving tokens.
Instead, Claude will search for tools as needed (but there are no guarantees that it will 
search optimally, of course).
To enable this feature, set the environment variable `ENABLE_TOOL_SEARCH=true`.  
Depending on your shell, you can also set this on a per-session basis, e.g. using
```shell
ENABLE_TOOL_SEARCH=true claude
```
in bash/zsh, or using
```shell
set ENABLE_TOOL_SEARCH=true && claude
```
in Windows CMD to launch Claude Code.

## VSCode

While murena can be directly installed from the GitHub MCP server registry, we recommend to set it up manually
(at least for now, until the configuration there has been improved). Just paste the following into
`<your_project>/.vscode/mcp.json`, or edit the entry after using the option `install into workspace`:

```json
{
  "servers": {
    "oraios/murena": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/murena",
        "murena",
        "start-mcp-server",
        "--context",
        "ide",
        "--project",
        "${workspaceFolder}"
      ]
    }
  },
  "inputs": []
}
```

## Codex

Murena works with OpenAI's Codex CLI out of the box, but you have to use the `codex` context for it to work properly. (The technical reason is that Codex doesn't fully support the MCP specifications, so some massaging of tools is required.).

Add a [run command](020_running) to `~/.codex/config.toml` to configure Murena for all Codex sessions;
create the file if it does not exist.
For example, when using `uvx`, add the following section:

```toml
[mcp_servers.murena]
command = "uvx"
args = ["--from", "git+https://github.com/oraios/murena", "murena", "start-mcp-server", "--context", "codex"]
```

After codex has started, you need to activate the project, which you can do by saying:

"Activate the current dir as project using murena"

> If you don't activate the project, you will not be able to use Murena's tools!

That's it! Have a look at `~/.codex/log/codex-tui.log` to see if any errors occurred.

Murena's dashboard will run if you have not disabled it in the configuration, but due to Codex's sandboxing, the web browser
may not open automatically. You can open it manually by going to `http://localhost:24282/dashboard/index.html` (or a higher port, if
that was already taken).

> Codex will often show the tools as `failed` even though they are successfully executed. This is not a problem, seems to be a bug in Codex. Despite the error message, everything works as expected.

## Claude Desktop

On Windows and macOS, there are official [Claude Desktop applications by Anthropic](https://claude.ai/download); for Linux, there is an [open-source
community version](https://github.com/aaddrick/claude-desktop-debian).

To configure MCP server settings, go to File / Settings / Developer / MCP Servers / Edit Config,
which will let you open the JSON file `claude_desktop_config.json`.

Add the `murena` MCP server configuration

```json
{
  "mcpServers": {
    "murena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/murena",
        "murena",
        "start-mcp-server"
      ]
    }
  }
}
```

If your language server requires specific environment variables to be set (e.g. F# on macOS with Homebrew),
you can add them via an `env` key (see [above](#clients-common-pitfalls)).

Once you have created the new MCP server entry, save the config and then restart Claude Desktop.

:::{attention}
Be sure to fully quit the Claude Desktop application via File / Exit, as regularly closing the application will just
minimize it.
:::

After restarting, you should see Murena's tools in your chat interface (notice the small hammer icon).

For more information on MCP servers with Claude Desktop,
see [the official quick start guide](https://modelcontextprotocol.io/quickstart/user).

## JetBrains Junie

Open Junie, go to the three dots in the top right corner, then Settings / MCP Settings and add Murena to Junie's global
MCP server configuration:

```json
{
  "mcpServers": {
    "murena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/murena",
        "murena",
        "start-mcp-server",
        "--context",
        "ide"
      ]
    }
  }
}
```

You will have to prompt Junie to "Activate the current project using murena's activation tool" at the
start of each session.

## JetBrains AI Assistant

Here you can set up the more convenient per-project MCP server configuration, as the AI assistant supports specifying
the launch working directory.

Go to Settings / Tools / AI Assistant / MCP and add a new **local** configuration via the `as JSON` option:

```json
{
  "mcpServers": {
    "murena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/murena",
        "murena",
        "start-mcp-server",
        "--context",
        "ide",
        "--project",
        "$(pwd)"
      ]
    }
  }
}
```

Then make sure to configure the working directory to be the project root.

## Antigravity

Add this configuration:

```json
{
  "mcpServers": {
    "murena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/murena",
        "murena",
        "start-mcp-server",
        "--context",
        "ide"
      ]
    }
  }
}
```

You will have to prompt Antigravity's agent to "Activate the current project using murena's activation tool" after starting Antigravity in the project directory (once in the first chat enough, all other chat sessions will continue using the same Murena session).


Unlike VSCode, Antigravity does not currently support including the working directory in the MCP configuration.
Also, the current client will be shown as `none` in Murena's dashboard (Antigravity currently does not fully support the MCP specifications). This is not a problem, all tools will work as expected.

## Other Clients

For other clients, follow the [general instructions](#clients-general-instructions) above to set up Murena as an MCP server.

### Terminal-Based Clients

There are many terminal-based coding assistants that support MCP servers, such as

 * [Gemini-CLI](https://github.com/google-gemini/gemini-cli), 
 * [Qwen3-Coder](https://github.com/QwenLM/Qwen3-Coder),
 * [rovodev](https://community.atlassian.com/forums/Rovo-for-Software-Teams-Beta/Introducing-Rovo-Dev-CLI-AI-Powered-Development-in-your-terminal/ba-p/3043623),
 * [OpenHands CLI](https://docs.all-hands.dev/usage/how-to/cli-mode) and
 * [opencode](https://github.com/sst/opencode).

They generally benefit from the symbolic tools provided by Murena. You might want to customize some aspects of Murena
by writing your own context, modes or prompts to adjust it to the client's respective internal capabilities (and your general workflow).

In most cases, the `ide` context is likely to be appropriate for such clients, i.e. add the arguments `--context ide` 
in order to reduce tool duplication.

### MCP-Enabled IDEs and Coding Clients (Cline, Roo-Code, Cursor, Windsurf, etc.)

Most of the popular existing coding assistants (e.g. IDE extensions) and AI-enabled IDEs themselves support connections
to MCP Servers. Murena generally boosts performance by providing efficient tools for symbolic operations.

We generally recommend to use the `ide` context for these integrations by adding the arguments `--context ide` 
in order to reduce tool duplication.

### Local GUIs and Agent Frameworks

Over the last months, several technologies have emerged that allow you to run a local GUI client
and connect it to an MCP server. The respective applications will typically work with Murena out of the box.
Some of the leading open source GUI applications are

  * [Jan](https://jan.ai/docs/mcp), 
  * [OpenHands](https://github.com/All-Hands-AI/OpenHands/),
  * [OpenWebUI](https://docs.openwebui.com/openapi-servers/mcp) and 
  * [Agno](https://docs.agno.com/introduction/playground).

These applications allow to combine Murena with almost any LLM (including locally running ones) 
and offer various other integrations.
