# Connecting Your MCP Client

In the following, we provide default configurations for popular MCP-enabled clients.

Depending on your needs, you might want to customize Serena's behaviour by 
  * [adding command-line arguments](mcp-args)
  * [adjusting configuration](050_configuration).

## Claude Code

Serena is a great way to make Claude Code both cheaper and more powerful!

From your project directory, add serena with a command like this,

```shell
claude mcp add serena -- <serena> start-mcp-server --context ide-assistant --project "$(pwd)"
```

where `<serena>` is [your way of running Serena](020_running).  
For example, when using `uvx`, the above command becomes

```shell
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project "$(pwd)"
```

Note:
  * We use the `ide-assistant` context to disable unnecessary tools (avoiding duplication
    with Claude Code's built-in capabilities).
  * We specify the current directory as the project directory with `--project "$(pwd)"`, such 
    that Serena is configured to work on the current project from the get-go, following 
    Claude Code's mode of operation.
    
Be sure to use at least `v1.0.52` of Claude Code (as earlier versions do not read MCP server system prompts upon startup). 

## Codex

Serena works with OpenAI's Codex CLI out of the box, but you have to use the `codex` context for it to work properly. (The technical reason is that Codex doesn't fully support the MCP specifications, so some massaging of tools is required.).

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

Serena's dashboard will run if you have not disabled it in the configuration, but due to Codex's sandboxing, the web browser
may not open automatically. You can open it manually by going to `http://localhost:24282/dashboard/index.html` (or a higher port, if
that was already taken).

> Codex will often show the tools as `failed` even though they are successfully executed. This is not a problem, seems to be a bug in Codex. Despite the error message, everything works as expected.

## Claude Desktop

On Windows and macOS there are official [Claude Desktop applications by Anthropic](https://claude.ai/download), for Linux there is an [open-source
community version](https://github.com/aaddrick/claude-desktop-debian).

To configure MCP server settings, go to File / Settings / Developer / MCP Servers / Edit Config,
which will let you open the JSON file `claude_desktop_config.json`.

Add the `serena` MCP server configuration, using a [run command](020_running.md) depending on your setup.

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

:::{attention}
Be sure to fully quit the Claude Desktop application via File / Exit, as regularly closing the application will just minimize it.
:::

After restarting, you should see Serena's tools in your chat interface (notice the small hammer icon).

For more information on MCP servers with Claude Desktop, see [the official quick start guide](https://modelcontextprotocol.io/quickstart/user).

## Other Clients

In general, Serena can be used with any MCP-enabled client.
To connect Serena to your favourite client, simply

1. determine how to add a custom MCP server to your client (refer to the client's documentation).
2. add a new MCP server entry by specifying either
    * a [run command](start-mcp-server) that allows the client to start the MCP server in stdio mode as a subprocess, or
    * the URL of the HTTP/SSE endpoint, having started the [Serena MCP server in HTTP/SSE mode](streamable-http) beforehand.

Below, we list some popular categories of clients that Serena can be used with.

### Terminal-Based Clients

There are many terminal-based coding assistants that support MCP servers, such as

 * [Gemini-CLI](https://github.com/google-gemini/gemini-cli), 
 * [Qwen3-Coder](https://github.com/QwenLM/Qwen3-Coder),
 * [rovodev](https://community.atlassian.com/forums/Rovo-for-Software-Teams-Beta/Introducing-Rovo-Dev-CLI-AI-Powered-Development-in-your-terminal/ba-p/3043623),
 * [OpenHands CLI](https://docs.all-hands.dev/usage/how-to/cli-mode) and
 * [opencode](https://github.com/sst/opencode).

They generally benefit from the symbolic tools provided by Serena. You might want to customize some aspects of Serena
by writing your own context, modes or prompts to adjust it to the client's respective internal capabilities (and your general workflow).

### MCP-Enabled IDEs and Coding Clients (Cline, Roo-Code, Cursor, Windsurf, etc.)

Most of the popular existing coding assistants (e.g. IDE extensions) and AI-enabled IDEs themselves support connections
to MCP Servers. Serena generally boosts performance by providing efficient tools for symbolic operations.

We generally **recommend to use the `ide-assistant` context** for these integrations by adding the arguments `--context ide-assistant` 
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
