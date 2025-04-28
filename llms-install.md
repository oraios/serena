# MCP Installation instructions

This document is mainly used as instructions for AI-assistants like Cline and others that
try to do an automatic install based on freeform instructions.

0. Make sure `uv` is installed. If not, install it using either `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS, Linux) or
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows). Find the path to the `uv` executable,
   you'll need it later.
1. Clone the repo with `git clone git@github.com:oraios/serena.git` and change into its dir (e.g., `cd serena`)
2. Check if `serena_config.yml` exists. If not, create it  with `cp serena_config.template.yml serena_config.yml`. Read the instructions in the config.
3. In the config, check if the path to your project was added. If not, add it to the `projects` section
4. In your project, create a `.serena` if needed and check whether `project.yml` exists there.
5. If no `project.yml` was found, create it using `cp /path/to/serena/myproject.template.yml /path/to/your/project/.serena/project.yml`
6. Read the instructions in `project.yml`. Make sure the `project.yml` has the correct project language configured. 
   Remove the  project_root entry there.
7. Finally, add the Serena MCP server config like this:

```json
   {
       "mcpServers": {
            ...
           "serena": {
               "command": "/abs/path/to/uv",
               "args": ["run", "--directory", "/abs/path/to/serena", "serena-mcp-server", "/path/to/your/project/.serena/project.yml"]
           }
       }
   }

```
