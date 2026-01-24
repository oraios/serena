# The Murena JetBrains Plugin

The [JetBrains Plugin](https://plugins.jetbrains.com/plugin/28946-murena/) allows Murena to
leverage the powerful code analysis and editing capabilities of your JetBrains IDE.

```{raw} html
<p>
<a href="https://plugins.jetbrains.com/plugin/28946-murena/">
<img style="background-color:transparent;" src="../_static/images/jetbrains-marketplace-button.png">
</a>
</p>
```

We recommend the JetBrains plugin as the preferred way of using Murena,
especially for users of JetBrains IDEs.

**Purchasing the JetBrains Plugin supports the Murena project.**
The proceeds from plugin sales allow us to dedicate more resources to further developing and improving Murena.


## Advantages of the JetBrains Plugin

There are multiple features that are only available when using the JetBrains plugin:

* **External library indexing**: Dependencies and libraries are fully indexed and accessible to Murena
* **No additional setup**: No need to download or configure separate language servers
* **Enhanced performance**: Faster tool execution thanks to optimized IDE integration
* **Multi-language excellence**: First-class support for polyglot projects with multiple languages and frameworks
* **Enhanced retrieval capabilities**: The plugin supports additional retrieval tools for type hierarchy information as well as fast and reliable documentation/type signature retrieval

We are also working on additional features like a `move_symbol` tool and debugging-related capabilities that
will be available exclusively through the JetBrains plugin.

## Configuring Murena to Use the JetBrains Plugin

After installing the plugin, you need to configure Murena to use it.

**Central Configuration**.

Edit the global Murena configuration file located at `~/.murena/murena_config.yml` 
(`%USERPROFILE%\.murena\murena_config.yml` on Windows).
Change the `language_backend` setting as follows:

```yaml
language_backend: JetBrains
```

*Note*: you can also use the button `Edit Global Murena Config` in the Murena MCP dashboard to open the config file in your default editor.

**Per-Instance Configuration**.
The configuration setting in the global config file can be overridden on a 
per-instance basis by providing the arguments `--language-backend JetBrains` when 
launching the Murena MCP server.

**Verifying the Setup**.
You can verify that Murena is using the JetBrains plugin by either checking the dashboard, where
you will see `Languages:
Using JetBrains backend` in the configuration overview.
You will also notice that your client will use the JetBrains-specific tools like `jet_brains_find_symbol` and others like it.

## Workflow

Having installed the plugin in your IDE and having configured Murena to use the JetBrains backend,
the general workflow is simple:
1. Open the project you want to work on in your JetBrains IDE
2. Open the project's root folder as a project in Murena (see [Project Creation](project-creation-indexing) and [Project Activation](project-activation))
3. Start using Murena tools as usual

Note that the folder that is open in your IDE and the project's root folder must match.

:::{tip}
If you need to work on multiple projects in the same agent session, create a monorepo folder
containing all the projects and open that folder in both Murena and your IDE.
:::

## Usage with Other Editors

We realize that not everyone uses a JetBrains IDE as their main code editor.
You can still take advantage of the JetBrains plugin by running a JetBrains IDE instance alongside your
preferred editor. Most JetBrains IDEs have a free community edition that you can use for this purpose.
You just need to make sure that the project you are working on is open and indexed in the JetBrains IDE, 
so that Murena can connect to it.
