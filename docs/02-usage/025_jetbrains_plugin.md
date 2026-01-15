# The Serena JetBrains Plugin

The [JetBrains Plugin](https://plugins.jetbrains.com/plugin/28946-serena/) allows Serena to
leverage the powerful code analysis and editing capabilities of your JetBrains IDE.

```{raw} html
<p>
<a href="https://plugins.jetbrains.com/plugin/28946-serena/">
<img style="background-color:transparent;" src="../_static/images/jetbrains-marketplace-button.png">
</a>
</p>
```

We recommend the JetBrains plugin as the preferred way of using Serena,
especially for users of JetBrains IDEs.

**Purchasing the JetBrains Plugin supports the Serena project.**
The proceeds from plugin sales allow us to dedicate more resources to further developing and improving Serena.

## Configuring Serena 

After installing the plugin, you need to configure Serena to use it.

**Central Configuration**.

Edit the global Serena configuration file located at `~/.serena/serena_config.yml` 
(`%USERPROFILE%\.serena\serena_config.yml` on Windows).
Change the `language_backend` setting as follows:

```yaml
language_backend: JetBrains
```

*Note*: you can also use the button `Edit Global Serena Config` in the Serena MCP dashboard to open the config file in your default editor.

**Per-Instance Configuration**.
The configuration setting in the global config file can be overridden on a 
per-instance basis by providing the arguments `--language-backend JetBrains` when 
launching the Serena MCP server.

**Verifying the Setup**.
You can verify that Serena is using the JetBrains plugin by either checking the dashboard, where
you will see `Languages:
Using JetBrains backend` in the configuration overview.
You will also notice that your client will use the JetBrains-specific tools like `jet_brains_find_symbol` and others like it.


## Advantages of the JetBrains Plugin

There are multiple features that are only available when using the JetBrains plugin:

* **External library indexing**: Dependencies and libraries are fully indexed and accessible to Serena
* **No additional setup**: No need to download or configure separate language servers
* **Enhanced performance**: Faster tool execution thanks to optimized IDE integration
* **Multi-language excellence**: First-class support for polyglot projects with multiple languages and frameworks

We are also working on additional features like a `move_symbol` tool and debugging-related capabilities that
will be available exclusively through the JetBrains plugin.

## Usage with Other Editors

We realize that not everyone uses a JetBrains IDE as their main code editor.
You can still take advantage of the JetBrains plugin by running a JetBrains IDE instance alongside your
preferred editor. Most JetBrains IDEs have a free community edition that you can use for this purpose.
You just need to make sure that the project you are working on is open and indexed in the JetBrains IDE,
so that Serena can connect to it.

## IDE on a Different Host

If your JetBrains IDE runs on a different host than Serena (e.g., IDE on Windows with Serena in WSL2,
or Serena in a Docker container), you can configure the host address using the `SERENA_JETBRAINS_HOST`
environment variable:

```bash
export SERENA_JETBRAINS_HOST=192.168.16.1
```

Or in your MCP client configuration (e.g., `.mcp.json`):

```json
{
  "mcpServers": {
    "serena": {
      "env": {
        "SERENA_JETBRAINS_HOST": "192.168.16.1"
      }
    }
  }
}
```

Replace `192.168.16.1` with the IP address of the host where your JetBrains IDE is running.
