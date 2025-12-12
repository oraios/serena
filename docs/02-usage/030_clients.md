# Connecting Your MCP Client

In the following, we provide default configurations for popular MCP-enabled clients.

Depending on your needs, you might want to customize Serena's behaviour by

* [adding command-line arguments](mcp-args)
* [adjusting configuration](050_configuration).

While you may be able to turn off tools through your client's interface (e.g., in VSCode or Claude Desktop),
we **highly** recommend selecting your toolset through the
Serena configuration instead, since Serena's prompts automatically
adjust based on which tools are enabled/disabled.

## General

> Please make sure to read these general instructions before proceeding to the client-specific sections below!

In the section on [running the MCP server](020_running), we described various ways of starting the Serena server. For
brevity, here we present only commands that use the `uvx` way and the `stdio` protocol. You can easily adapt the
commands to your preferred way of running Serena.

Some clients have a per-workspace MCP configuration (e.g., VSCode and Claude Code), while others have a global MCP
configuration (e.g., Codex and Claude Desktop).

- In the per-workspace case, you typically want Serena to start
  within the project directory and never switch to a different project, which is achieved by specifying the
  `--project <path>` argument when starting the MCP server. This also disables the `activate_project` tool.
- In the global configuration case, you must first activate the project you want to work on, which you can do by asking
  the LLM to do so (e.g., "Activate the current dir as project using serena"). In such settings, the `activate_project`
  tool is required.

### Common Pitfalls

Your client may not escape backslashes on Windows (e.g., Claude Desktop does not).
If you are using paths containing backslashes for paths on Windows
(note that you can also just use forward slashes), be sure to escape them correctly (`\\`).

Your client may not find the `uvx` command, even if it is on your system PATH.
In this case, you should provide the full path to the `uvx` executable.

Some language servers may require additional environment variables to be set (e.g. F# on macOS with Homebrew),
which you may need to explicitly add to the MCP server configuration.
Note that for some clients (including Claude Desktop), the spawned processes may not inherit environment variables that
are only configured in your shell
profile (e.g. `.bashrc`, `.zshrc`, etc.); they would need to be set system-wide instead.
An easy fix is to add them explicitly to the MCP server entry: many clients allow adding an `env` key to the `serena`
object, e.g.

```
"env": {
    "DOTNET_ROOT": "/opt/homebrew/Cellar/dotnet/9.0.8/libexec"
}
```

## Claude Code

Serena is a great way to make Claude Code both cheaper and more powerful!

From your project directory, add serena with a command like this,

```shell
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context claude-code --project "$(pwd)"
```

Note:

* We use the `claude-code` context to disable unnecessary tools (avoiding duplication
  with Claude Code's built-in capabilities).
* We specify the current directory as the project directory with `--project "$(pwd)"`, such
  that Serena is configured to work on the current project from the get-go, following
  Claude Code's mode of operation.

## VSCode

While serena can be directly installed from the GitHub MCP server registry, we recommend to set it up manually
(at least for now, until the configuration there has been improved). Just paste the following into
`<your_project>/.vscode/mcp.json`, or edit the entry after using the option `install into workspace`:

```json
{
  "servers": {
    "oraios/serena": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
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

Serena works with OpenAI's Codex CLI out of the box, but you have to use the `codex` context for it to work properly. (
The technical reason is that Codex doesn't fully support the MCP specifications, so some massaging of tools is
required.).

Add a [run command](020_running) to `~/.codex/config.toml` to configure Serena for all Codex sessions;
create the file if it does not exist.
For example, when using `uvx`, add the following section:

```toml
[mcp_servers.serena]
command = "uvx"
args = ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--context", "codex"]
```

After codex has started, you need to activate the project, which you can do by saying:

"Activate the current dir as project using serena"

> If you don't activate the project, you will not be able to use Serena's tools!

That's it! Have a look at `~/.codex/log/codex-tui.log` to see if any errors occurred.

Serena's dashboard will run if you have not disabled it in the configuration, but due to Codex's sandboxing, the web
browser
may not open automatically. You can open it manually by going to `http://localhost:24282/dashboard/index.html` (or a
higher port, if
that was already taken).

> Codex will often show the tools as `failed` even though they are successfully executed. This is not a problem, seems
> to be a bug in Codex. Despite the error message, everything works as expected.

## Claude Desktop

On Windows and macOS there are official [Claude Desktop applications by Anthropic](https://claude.ai/download), for
Linux there is an [open-source
community version](https://github.com/aaddrick/claude-desktop-debian).

To configure MCP server settings, go to File / Settings / Developer / MCP Servers / Edit Config,
which will let you open the JSON file `claude_desktop_config.json`.

Add the `serena` MCP server configuration

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server"
      ]
    }
  }
}
```

Once you have created the new MCP server entry, save the config and then restart Claude Desktop.

:::{attention}
Be sure to fully quit the Claude Desktop application via File / Exit, as regularly closing the application will just
minimize it.
:::

After restarting, you should see Serena's tools in your chat interface (notice the small hammer icon).

For more information on MCP servers with Claude Desktop,
see [the official quick start guide](https://modelcontextprotocol.io/quickstart/user).

## JetBrains Junie

Open Junie, go to the three dots in the top right corner, then Settings / MCP Settings and add Serena to Junie's global
MCP server configuration:

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--context",
        "ide"
      ]
    }
  }
}
```

You will have to prompt Junie to "Activate the current project using serena's activation tool" at the
start of each session.

## JetBrains AI Assistant

Here you can set up the more convenient per-project MCP server configuration, as the AI assistant supports specifying
the launch working directory.

Go to Settings / Tools / AI Assistant / MCP and add a new **local** configuration via the `as JSON` option:

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
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

Add this configuration

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--context",
        "ide"
      ]
    }
  }
}
```

At the time of writing (12.2025), it does **not seem to work** due to schema validation issues in Antigravity.
The client starts Serena and then crashes with `[internal] marshal message: string field contains invalid UTF-8`.

## Other Clients

In general, Serena can be used with any MCP-enabled client.
To connect Serena to your favourite client, simply

1. determine how to add a custom MCP server to your client (refer to the client's documentation).
2. add a new MCP server entry by specifying either
    * a [run command](start-mcp-server) that allows the client to start the MCP server in stdio mode as a subprocess, or
    * the URL of the HTTP/SSE endpoint, having started the [Serena MCP server in HTTP/SSE mode](streamable-http)
      beforehand.

Below, we list some popular categories of clients that Serena can be used with.

### Terminal-Based Clients

There are many terminal-based coding assistants that support MCP servers, such as

* [Gemini-CLI](https://github.com/google-gemini/gemini-cli),
* [Qwen3-Coder](https://github.com/QwenLM/Qwen3-Coder),
* [rovodev](https://community.atlassian.com/forums/Rovo-for-Software-Teams-Beta/Introducing-Rovo-Dev-CLI-AI-Powered-Development-in-your-terminal/ba-p/3043623),
* [OpenHands CLI](https://docs.all-hands.dev/usage/how-to/cli-mode) and
* [opencode](https://github.com/sst/opencode).

They generally benefit from the symbolic tools provided by Serena. You might want to customize some aspects of Serena
by writing your own context, modes or prompts to adjust it to the client's respective internal capabilities (and your
general workflow).

### MCP-Enabled IDEs and Coding Clients (Cline, Roo-Code, Cursor, Windsurf, etc.)

Most of the popular existing coding assistants (e.g. IDE extensions) and AI-enabled IDEs themselves support connections
to MCP Servers. Serena generally boosts performance by providing efficient tools for symbolic operations.

We generally **recommend to use the `ide` context** for these integrations by adding the arguments `--context ide`
in order to reduce tool duplication.

### Local GUIs and Agent Frameworks

Over the last months, several technologies have emerged that allow you to run a local GUI client
and connect it to an MCP server. The respective applications will typically work with Serena out of the box.
Some of the leading open source GUI applications are

* [Jan](https://jan.ai/docs/mcp),
* [OpenHands](https://github.com/All-Hands-AI/OpenHands/),
* [OpenWebUI](https://docs.openwebui.com/openapi-servers/mcp) and
* [Agno](https://docs.agno.com/introduction/playground).

These applications allow to combine Serena with almost any LLM (including locally running ones)
and offer various other integrations.
