# Connecting Your MCP Client

In the following, we provide general instructions on how to connect Serena to your MCP-enabled client,
as well as specific instructions for popular clients.

(clients-general-instructions)=
## General Instructions

In general, Serena can be used with any MCP-enabled client.
To connect Serena to your favourite client, simply

1. determine how to add a custom MCP server to your client (refer to the client's documentation).
2. add a new MCP server entry by specifying either
    * a [run command](start-mcp-server) that allows the client to start the MCP server in stdio mode as a subprocess, or
    * the URL of the HTTP/SSE endpoint, having started the [Serena MCP server in HTTP/SSE mode](streamable-http) beforehand.

Find concrete examples for popular clients below.

Depending on your needs, you might want to further customize Serena's behaviour by
* [adding command-line arguments](mcp-args)
* [adjusting configuration](050_configuration).

**Mode of Operation**.
Note that some clients have a per-workspace MCP configuration (e.g, VSCode and Claude Code),
while others have a global MCP configuration (e.g. Codex and Claude Desktop).

- In the per-workspace case, you typically want to start Serena with your workspace directory as the project directory 
  and never switch to a different project. This is achieved by specifying the
  `--project <path>` argument with a single-project [context](#contexts) (e.g. `ide` or `claude-code`).
- In the global configuration case, you must first activate the project you want to work on, which you can do by asking
  the LLM to do so (e.g., "Activate the current dir as project using serena"). In such settings, the `activate_project`
  tool is required.

**Tool Selection**.
While you may be able to turn off tools through your client's interface (e.g., in VSCode or Claude Desktop),
we recommend selecting your base tool set through Serena's configuration, as Serena's prompts automatically
adjust based on which tools are enabled/disabled.  
A key mechanism for this is to use the appropriate [context](#contexts) when starting Serena.

(clients-common-pitfalls)=
### Common Pitfalls

**Discoverability of the `serena` command**.
Your client may not find the `serena` CLI command, even if it is on your system PATH.
In this case, a workaround is to provide the full path to the `serena` executable.

**Serena's tools not being used**.
With some clients, you may experience that Serena's tools are not being used.
This is mainly due to problems in the client itself (like a poorly implemented tool discovery). To counteract this,
Serena comes with a set of commands that can be used in _hooks_. See the sections on hooks for Claude Code and VSCode below.

**Environment Variables**.
Some language servers may require additional environment variables to be set (e.g. F# on macOS with Homebrew),
which you may need to explicitly add to the MCP server configuration.
Note that for some clients (e.g. Claude Desktop), the spawned MCP server process may not inherit environment variables that
are only configured in your shell profile (e.g. `.bashrc`, `.zshrc`, etc.); they would need to be set system-wide instead.
An easy fix is to add them explicitly to the MCP server entry.
For example, in Claude Desktop and other clients, you can simply add an `env` key to the `serena`
object, e.g.

```
"env": {
    "DOTNET_ROOT": "/opt/homebrew/Cellar/dotnet/9.0.8/libexec"
}
```

## Copilot in JetBrains

Open the settings of your JetBrains IDE and go to Tools / GitHub Copilot / Model Context Protocol (MCP). Then click
on the Configure button. This will open your global `mcp.json` file, where you can add the following entry for Serena:

```json
{
    "servers": {
      "serena": {
        "type": "stdio",
        "command": "serena",
        "args": [
          "start-mcp-server",
          "--context=jb-copilot-plugin"
        ]
      }
    }
}
```

**Verification.**
Open Copilot, switch to Agent mode, and click on the configure tools button. You should see Serena's tools in the list and be able to start
the Serena server there (you do not generally have to start Serena in the future, Copilot will start the server by itself). If the server is shown as running, Copilot is successfully connected to Serena. Most models will understand how to use Serena's tools out of the box, but for some models you may have to prompt "Activate the current project with Serena and read initial instructions" in the beginning of the chat.

**Recommended Configuration**.
The `jb-copilot-plugin` context (see above) comes with our recommended subset of Serena's tools for Copilot in JetBrains IDEs. We also 
recommend *disabling* the following built-in tools for optimal performance: 
replace_string_in_file, apply_patch, list_dir, file_search, grep_search. Note that running subagents may not use MCP servers, consider deactivating the run_subagent tool as well.

Serena offers better alternatives to these basic tools. If you do prefer to use the built-in tools instead,
you should disable corresponding Serena tools instead to prevent context bloat.

We also recommend marking Serena's tools as approved so you don't have to manually approve them in agent sessions. 
You can do this in Tools / GitHub Copilot / Chat, where at the bottom you can click on the Configure button for MCP tool auto-approval.

## Claude Code

Serena is a great way to make Claude Code both cheaper and more powerful!
To add Serena to Claude Code, you can simply run `serena setup claude-code`. Alternatively, follow the instructions below.

**Global Configuration**. To add the Serena MCP server for all your projects, use the user-level configuration of claude code and the `--project-from-cwd` flag:

```shell
claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd
```

**Per-Project Configuration.** Alternatively, to add Serena only for the current project in the current directory, 
use the command:

```shell
claude mcp add serena -- serena start-mcp-server --context claude-code --project "$(pwd)"
```

**Verification.**
Confirm that Claude Code is connected to Serena by running the `/mcp` command and by reconnecting, if necessary.
If Serena fails to start fast enough, you should set `MCP_TIMEOUT` to a sufficiently high value
(e.g. by adding `export MCP_TIMEOUT=60000` to your shell profile)

**Hooks.**
Due to recent changes (especially dynamic tool loading) in Claude Code, the agent will often fail to make proper use
of Serena's tools, either by failing to load them in the beginning or by forgetting the instructions in a long session
(a behavior known as agent drift). To counteract this, we provide reminder hooks. We **strongly recommend** setting
up the hooks as below (or a variation thereof) for optimal performance of Serena in Claude Code.

:::{note}
While recommended, hooks are an **alpha feature**. Provide feedback via the [GitHub issue tracker](https://github.com/oraios/serena/issues) if you encounter any issues.
:::

To set up hooks, add the following to your Claude Code settings file
(`.claude/settings.json` in your project directory, or `~/.claude/settings.json` globally):

All hooks below are opt-in — include only the ones you want. Add the following to your
Claude Code settings file (`.claude/settings.json` in your project directory, or
`~/.claude/settings.json` globally):

```json
{
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "serena-hooks remind --client=claude-code"
                    }
                ]
            },
            {
                "matcher": "mcp__serena__*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "serena-hooks auto-approve --client=claude-code"
                    }
                ]
            }
        ],
        "SessionStart": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "serena-hooks activate --client=claude-code"
                    }
                ]
            }
        ],
        "Stop": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "serena-hooks cleanup --client=claude-code"
                    }
                ]
            }
        ]
    }
}
```

The hooks will:

- **`remind`**: Nudge the agent to use Serena's symbolic tools when it makes too many consecutive
  `grep` or `read_file` calls without using any Serena tools in between.
- **`activate`**: Prompt the agent to activate the project and read Serena's instructions at session start.
- **`cleanup`**: Clean up hook session data when the session ends.
- **`auto-approve`**: Auto-approve Serena tool calls whenever Claude Code is in `acceptEdits` mode,
  so blanket edit approvals cover Serena's destructive tools (e.g. `replace_symbol_body`,
  `rename_symbol`) instead of prompting on every call.

For more details on Claude Code's hook system, see the
[Claude Code hooks documentation](https://code.claude.com/docs/en/hooks).

## VSCode

You can add Serena to VSCode by running the MCP: Add Server command.
In that dialogue, select the Command (stdio) option. You can decide between installing it globally
or in the workspace (only for the currently open project), and the command you should enter depends on that choice.
(You will be asked to choose after entering the mcp run command.)

**Global.** (Recommended)
Enter `serena start-mcp-server --context=vscode`. Unfortunately, due to a [bug in VSCode](https://github.com/microsoft/vscode/issues/245905),
in this setting Serena won't be able to activate the project automatically. You will have to remember to prompt
"Activate the current dir as project using serena" at the start of each session.

**Workspace.**
Enter `serena start-mcp-server --context=vscode --project ${workspaceFolder}`. This will allow Serena to automatically activate the project,
with the downside that you will have to add Serena to each project you want to use it in.

In both cases, proceed to enter Serena as the name, then select either global or workspace.

**Verification.**
You should be able to see Serena in the tools overview in the AI Chat window.

**Hooks.**
Due to recent changes (especially dynamic tool loading) in VSCode, the agent will often fail to make proper use
of Serena's tools, either by failing to load them in the beginning or by forgetting the instructions in a long session
(a behaviour known as agent drift). To counteract this, we provide reminder hooks. We **strongly recommend** setting
up the hooks as below (or a variation thereof) for optimal performance of Serena in VSCode.


The hooks will:

- **`remind`**: Nudge the agent to use Serena's symbolic tools when it makes too many consecutive
  `grep` or `read_file` calls without using any Serena tools in between.
- **`activate`**: Prompt the agent to activate the project and read Serena's instructions at session start.
- **`cleanup`**: Clean up hook session data when the session ends.

To set this up, create the file `~/.copilot/hooks/serena-hooks.json` with the following content:

```json
{
    "hooks": {
        "PreToolUse": [
            {
                "type": "command",
                "command": "serena-hooks remind --client=vscode"
            }
        ],
        "SessionStart": [
            {
                "type": "command",
                "command": "serena-hooks activate --client=vscode"
            }
        ],
        "Stop": [
            {
                "type": "command",
                "command": "serena-hooks cleanup --client=vscode"
            }
        ]
    }
}
```

The `SessionStart` hook also addresses the global configuration limitation mentioned above — it will
automatically prompt the agent to activate the project directory, so you no longer need to do this manually.

## Copilot CLI

Use the interactive `/mcp add` slash command, choose Serena as the name, STDIO as the server type, and
`serena start-mcp-server --context=copilot-cli --project-from-cwd` as command. Copilot CLI will immediately notify you
that Serena is running if everything is set up correctly or display an error otherwise.

You should add the same **hooks** as in VSCode (see above) if Copilot CLI didn't pick them up automatically.


## Codex (CLI and App)

You can simply run `serena setup codex`.

Alternatively, you can manually add the following to `~/.codex/config.toml` (create the file if it does not exist):

```toml
[mcp_servers.serena]
startup_timeout_sec = 15
command = "serena"
args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]
```

**Verification.**
Run the `/mcp` command and verify that Serena is connected.
The Codex app does not start a session in the project's directory, so when using the app, we recommend
asking Codex to "Activate the current dir as project using serena" at the start of each session (though Codex might
do this automatically).

**Hooks.** The Codex hook system is less refined than of VSCode or Claude Code, but Codex also displays less drift
and is better in using Serena's tools out of the box. If you use the Codex app, you can consider setting up the 
SessionStart hook (see above) to remind the agent to activate the project directory.

## Claude Desktop

On Windows and macOS, there are official [Claude Desktop applications by Anthropic](https://claude.ai/download); for Linux, there is an [open-source
community version](https://github.com/aaddrick/claude-desktop-debian).

To configure MCP server settings, go to File / Settings / Developer / MCP Servers / Edit Config,
which will let you open the JSON file `claude_desktop_config.json`.

Add the `serena` MCP server configuration

```json
{
  "mcpServers": {
    "serena": {
      "command": "serena",
      "args": [
        "start-mcp-server",
        "--context=claude-desktop"
      ]
    }
  }
}
```

If your language server requires specific environment variables to be set (e.g. F# on macOS with Homebrew),
you can add them via an `env` key (see [above](#clients-common-pitfalls)).

**Verification.**
Once you have created the new MCP server entry, save the config and then restart Claude Desktop.

:::{attention}
Be sure to fully quit the Claude Desktop application via File / Exit, as regularly closing the application will just
minimize it.
:::

After restarting, you should see Serena's tools in your chat interface (notice the small hammer icon).

## Copilot CLI

In the interactive mode, you can call `/mcp add` from within the copilot CLI. There, use serena as name, 
STDIO as the server type, and `serena start-mcp-server --context=copilot-cli --project-from-cwd` as command.

Alternatively, add the following to `~/.copilot/mcp-config.json` (create the file if it does not exist):

```json
{
  "mcpServers": {
    "serena": {
      "type": "stdio",
      "command": "serena",
      "tools": [
        "*"
      ],
      "args": [
        "start-mcp-server",
        "--context=copilot-cli",
        "--project-from-cwd"
      ]
    }
  }
}
```

**Verification.**
Copilot should now show that Serena is running, though you may have to restart it.


## JetBrains Junie

For the Junie plugin in JetBrains IDEs you can add Serena either to the global configuration in `~/.junie/mcp/mcp.json` 
or to the project configuration in `<project>/.junie/mcp/mcp.json`. Important, don't add both!
In both cases the entry should be:


```json
{
  "mcpServers": {
    "serena": {
      "command": "serena",
      "args": [
        "start-mcp-server",
        "--context=junie",
        "--project-from-cwd"
      ]
    }
  }
}
```

With the global configuration, Serena will be available in all projects. However,
within the Junie plugin, projects will not be automatically activated in Serena. 
You may thus have to prompt 
Junie to "Activate the current project using serena's activation tool" at the start of each session (though some models are
smart enough to activate the project automatically).

With the project-scoped configuration, Serena will be available only in that project, and the project will automatically
be recognized as active by Serena.


## JetBrains AI Assistant

Go to Settings / Tools / AI Assistant / MCP and enter the following configuration:

```json
{
  "mcpServers": {
    "serena": {
      "command": "serena",
      "args": [
        "start-mcp-server",
        "--context=jb-ai-assistant",
        "--project-from-cwd"
      ]
    }
  }
}
```

Like for Junie, you have the choice between the global and the project-scoped configuration, 
with the same trade-off.

## Antigravity

Add this configuration:

```json
{
  "mcpServers": {
    "serena": {
      "command": "serena",
      "args": [
        "start-mcp-server",
        "--context=antigravity"
      ]
    }
  }
}
```

You will have to prompt Antigravity's agent to "Activate the current project using serena's activation tool" after starting Antigravity in the project directory (once in the first chat enough, all other chat sessions will continue using the same Serena session).


Unlike VSCode, Antigravity does not currently support including the working directory in the MCP configuration.
Also, the current client will be shown as `none` in Serena's dashboard (Antigravity currently does not fully support the MCP specifications). This is not a problem, all tools will work as expected.

## Other Clients

For other clients, follow the [general instructions](#clients-general-instructions) above to set up Serena as an MCP server.

### Terminal-Based Clients

There are many terminal-based coding assistants that support MCP servers, such as

 * [Gemini-CLI](https://github.com/google-gemini/gemini-cli), 
 * [Qwen3-Coder](https://github.com/QwenLM/Qwen3-Coder),
 * [rovodev](https://community.atlassian.com/forums/Rovo-for-Software-Teams-Beta/Introducing-Rovo-Dev-CLI-AI-Powered-Development-in-your-terminal/ba-p/3043623),
 * [OpenHands CLI](https://docs.all-hands.dev/usage/how-to/cli-mode) and
 * [opencode](https://github.com/sst/opencode).

They generally benefit from the symbolic tools provided by Serena. You might want to customize some aspects of Serena
by writing your own context, modes or prompts to adjust it to the client's respective internal capabilities (and your general workflow).

In most cases, the `ide` context is likely to be appropriate for such clients, i.e. add the arguments `--context ide` 
in order to reduce tool duplication.

### MCP-Enabled IDEs and Coding Clients (Cline, Roo-Code, Cursor, Windsurf, etc.)

Most of the popular existing coding assistants (e.g. IDE extensions) and AI-enabled IDEs themselves support connections
to MCP Servers. Serena generally boosts performance by providing efficient tools for symbolic operations.

We generally recommend using the `ide` context for these integrations by adding the arguments `--context ide` 
in order to reduce tool duplication.

### Local GUIs and Agent Frameworks

Over the last months, several technologies have emerged that allow you to run a local GUI client
and connect it to an MCP server. The respective applications will typically work with Serena out of the box.
Some of the leading open source GUI applications are

  * [Jan](https://jan.ai/docs/mcp), 
  * [OpenHands](https://github.com/All-Hands-AI/OpenHands/),
  * [OpenWebUI](https://docs.openwebui.com/openapi-servers/mcp) and 
  * [Agno](https://docs.agno.com/introduction/playground).

These applications allow combining Serena with almost any LLM (including locally running ones) 
and offer various other integrations.
