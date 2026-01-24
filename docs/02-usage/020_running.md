# Running Murena

Murena is a command-line tool with a variety of sub-commands.
This section describes
 * various ways of running Murena
 * how to run and configure the most important command, i.e. starting the MCP server
 * other useful commands.

## Ways of Running Murena

In the following, we will refer to the command used to run Murena as `<murena>`,
which you should replace with the appropriate command based on your chosen method,
as detailed below.

In general, to get help, append `--help` to the command, i.e.

    <murena> --help
    <murena> <command> --help

### Using uvx

`uvx` is part of `uv`. It can be used to run the latest version of Murena directly from the repository, without an explicit local installation.

    uvx --from git+https://github.com/oraios/murena murena 

Explore the CLI to see some of the customization options that murena provides (more info on them below).

### Local Installation

1. Clone the repository and change into it.

   ```shell
   git clone https://github.com/oraios/murena
   cd murena
   ```

2. Run Murena via

   ```shell
   uv run murena 
   ```

   when within the murena installation directory.   
   From other directories, run it with the `--directory` option, i.e.

   ```shell
    uv run --directory /abs/path/to/murena murena
    ```

:::{note}
Adding the `--directory` option results in the working directory being set to the Murena directory.
As a consequence, you will need to specify paths when using CLI commands that would otherwise operate on the current directory.
:::

(docker)=
### Using Docker 

The Docker approach offers several advantages:

* better security isolation for shell command execution
* no need to install language servers and dependencies locally
* consistent environment across different systems

You can run the Murena MCP server directly via Docker as follows,
assuming that the projects you want to work on are all located in `/path/to/your/projects`:

```shell
docker run --rm -i --network host -v /path/to/your/projects:/workspaces/projects ghcr.io/oraios/murena:latest murena 
```

This command mounts your projects into the container under `/workspaces/projects`, so when working with projects, 
you need to refer to them using the respective path (e.g. `/workspaces/projects/my-project`).

Alternatively, you may use Docker compose with the `compose.yml` file provided in the repository.
See our [advanced Docker usage](https://github.com/oraios/murena/blob/main/DOCKER.md) documentation for more detailed instructions, configuration options, and limitations.

:::{note}
Docker usage is subject to limitations; see the [advanced Docker usage](https://github.com/oraios/murena/blob/main/DOCKER.md) documentation for details.
:::

### Using Nix

If you are using Nix and [have enabled the `nix-command` and `flakes` features](https://nixos.wiki/wiki/flakes), you can run Murena using the following command:

```bash
nix run github:oraios/murena -- <command> [options]
```

You can also install Murena by referencing this repo (`github:oraios/murena`) and using it in your Nix flake. The package is exported as `murena`.

(start-mcp-server)=
## Running the MCP Server

Given your preferred method of running Murena, you can start the MCP server using the `start-mcp-server` command:

    <murena> start-mcp-server [options]  

Note that no matter how you run the MCP server, Murena will, by default, start a web-based dashboard on localhost that will allow you to inspect
the server's operations, logs, and configuration.

:::{tip}
By default, Murena will use language servers for code understanding and analysis.    
With the [Murena JetBrains Plugin](025_jetbrains_plugin), we recently introduced a powerful alternative,
which has several advantages over the language server-based approach.
:::

### Standard I/O Mode

The typical usage involves the client (e.g. Claude Code, Codex or Cursor) running
the MCP server as a subprocess and using the process' stdin/stdout streams to communicate with it.
In order to launch the server, the client thus needs to be provided with the command to run the MCP server.

:::{note}
MCP servers which use stdio as a protocol are somewhat unusual as far as client/server architectures go, as the server
necessarily has to be started by the client in order for communication to take place via the server's standard input/output streams.
In other words, you do not need to start the server yourself. The client application (e.g. Claude Desktop) takes care of this and
therefore needs to be configured with a launch command.
:::

Communication over stdio is the default for the Murena MCP server, so in the simplest
case, you can simply run the `start-mcp-server` command without any additional options.
 
    <murena> start-mcp-server

For example, to run the server in stdio mode via `uvx`, you would run:

    uvx --from git+https://github.com/oraios/murena murena start-mcp-server 
 
See the section ["Configuring Your MCP Client"](030_clients) for specific information on how to configure your MCP client (e.g. Claude Code, Codex, Cursor, etc.)
to use such a launch command.

(streamable-http)=
### Streamable HTTP Mode

When using instead the *Streamable HTTP* mode, you control the server lifecycle yourself,
i.e. you start the server and provide the client with the URL to connect to it.

Simply provide `start-mcp-server` with the `--transport streamable-http` option and optionally provide the desired port
via the `--port` option.

    <murena> start-mcp-server --transport streamable-http --port <port>

For example, to run the Murena MCP server in streamable HTTP mode on port 9121 using uvx,
you would run

    uvx --from git+https://github.com/oraios/murena murena start-mcp-server --transport streamable-http --port 9121

and then configure your client to connect to `http://localhost:9121/mcp`.

Note that while the legacy SSE transport is also supported (via `--transport sse` with corresponding /sse endpoint), its use is discouraged.

(mcp-args)=
### MCP Server Command-Line Arguments

The Murena MCP server supports a wide range of additional command-line options.
Use the command

    <murena> start-mcp-server --help

to get a list of all available options.

Some useful options include:

  * `--project <path|name>`: specify the project to work on by name or path.
  * `--project-from-cwd`: auto-detect the project from current working directory   
    (looking for a directory containing `.murena/project.yml` or `.git` in parent directories, activating the current directory if none is found);  
    This option is intended for CLI-based agents like Claude Code, Gemini and Codex, which are typically started from within the project directory
    and which do not change directories during their operation.
  * `--language-backend JetBrains`: use the Murena JetBrains Plugin as the language backend (overriding the default backend configured in the central configuration)
  * `--context <context>`: specify the operation [context](contexts) in which Murena shall operate
  * `--mode <mode>`: specify one or more [modes](modes) to enable (can be passed several times)
  * `--open-web-dashboard <true|false>`: whether to open the web dashboard on startup (enabled by default)

## Other Commands

Murena provides several other commands in addition to `start-mcp-server`, 
most of which are related to project setup and configuration.

To get a list of available commands, run:

    <murena> --help

To get help on a specific command, run:

    <murena> <command> --help

In general, add `--help` to any command or sub-command to get information about its usage and available options.

Here are some examples of commands you might find useful:

```bash
# get help about a sub-command
<murena> tools list --help

# list all available tools
<murena> tools list --all

# get detailed description of a specific tool
<murena> tools description find_symbol

# creating a new Murena project in the current directory 
<murena> project create

# creating and immediately indexing a project
<murena> project create --index

# indexing the project in the current directory (auto-creates if needed)
<murena> project index

# run a health check on the project in the current directory
<murena> project health-check

# check if a path is ignored by the project
<murena> project is_ignored_path path/to/check

# edit Murena's configuration file
<murena> config edit

# list available contexts
<murena> context list

# create a new context
<murena> context create my-custom-context

# edit a custom context
<murena> context edit my-custom-context

# list available modes
<murena> mode list

# create a new mode
<murena> mode create my-custom-mode

# edit a custom mode
<murena> mode edit my-custom-mode

# list available prompt definitions
<murena> prompts list

# create an override for internal prompts
<murena> prompts create-override prompt-name

# edit a prompt override
<murena> prompts edit-override prompt-name
```

Explore the full set of commands and options using the CLI itself!
