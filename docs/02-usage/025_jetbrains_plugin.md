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


## Advantages of the JetBrains Plugin

There are multiple features that are only available when using the JetBrains plugin:

* **External library indexing**: Dependencies and libraries are fully indexed and accessible to Serena
* **No additional setup**: No need to download or configure separate language servers
* **Enhanced performance**: Faster tool execution thanks to optimized IDE integration
* **Multi-language excellence**: First-class support for polyglot projects with multiple languages and frameworks
* **Enhanced retrieval capabilities**: The plugin supports additional retrieval tools for type hierarchy information as well as fast and reliable documentation/type signature retrieval

We are also working on additional features like a `move_symbol` tool and debugging-related capabilities that
will be available exclusively through the JetBrains plugin.

## Configuring Serena to Use the JetBrains Plugin

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

## Workflow

Having installed the plugin in your IDE and having configured Serena to use the JetBrains backend,
the general workflow is simple:
1. Open the project you want to work on in your JetBrains IDE
2. Open the project's root folder as a project in Serena (see [Project Creation](project-creation-indexing) and [Project Activation](project-activation))
3. Start using Serena tools as usual

Note that the folder that is open in your IDE and the project's root folder must match.

:::{tip}
If you need to work on multiple projects in the same agent session, create a monorepo folder
containing all the projects and open that folder in both Serena and your IDE.
:::

## Advanced Usage and Configuration

### Using Serena with Multi-Module Projects

JetBrains IDEs support *multi-module projects*, where a project can reference other projects as modules.
Serena, however, requires that a project is self-contained within a single root folder. 
There has to be a one-to-one relationship between the project root folder and the folder that is open in the IDE.

Therefore, to get a multi-module setup working with Serena, the recommended approach is to create a **monorepo folder**,
i.e. a folder that contains all the projects as sub-folders, and open that monorepo folder in both Serena and your IDE.

You do not necessarily need to physically move your projects into a common parent folder; 
you can also use symbolic links to achieve the same effect 
(i.e. use `mklink` on Windows or `ln` on Linux/macOS to link the project folders into a common parent folder).

### Using Serena with Windows Subsystem for Linux (WSL)

JetBrains IDEs have built-in support for WSL, allowing you to run the IDE on Windows while working with code in the WSL environment.
The Serena JetBrains plugin works seamlessly in this setup as well.

#### Using JetBrains Remote Development 

Recommended constellation:
* Your project is in the WSL file system
* Serena is run in WSL (not Windows)
* The IDE has a host component (in WSL) and a client component (on Windows).  
  The Serena JetBrains plugin should normally be **installed in the host** (not the client) for code intelligence to be accessible.

:::{admonition} Plugin Installation Location
:class: note
If the plugin is already installed, check the options on the button for disabling the plugin.
Choose the respective options to ensure the correct installation location (i.e. host, removing it from the client if necessary).
:::

:::{admonition} Using mapped Windows paths in WSL is not recommended!
:class: warning
Keeping your project in the Windows file system and accessing it via `/mnt/` in WSL is extremely slow and not recommended.
:::

**Special Network Setup**.
If you are using a special setup where Serena and the IDE are running on different machines,
make sure Serena can communicate with the JetBrains plugin.
You can configure `jetbrains_plugin_server_address` in your [serena_config.yml](050_configuration) and
configure the listen address of the JetBrains plugin in the IDE via Settings / Tools / Serena
(e.g. set it to 0.0.0.0 to listen on all interfaces, but be aware of the security implications of doing so).

#### Other WSL Integrations (e.g. WSL interpreter) 

* Your project is in the Windows file system
* WSL is used only for running tools (e.g. using a WSL Python interpreter in the IDE)
* Serena, the IDE and the plugin are all running on Windows

In this constellation, no special setup is required.

## Serena Plugin Configuration Options

You can configure plugin options in the IDE under Settings / Tools / Serena.

 * **Listen address** (default: `127.0.0.1`)  
   the address the plugin's server listens on.  
   The default will work as long as Serena is running on the same machine (or on a virtual machine using mirrored networking).
   But if the Serena MCP server is running on a different machine, configure the listen address to ensure that connections are possible.
   You can use `0.0.0.0` to listen on all interfaces (but be aware of the security implications of doing so).

 * **Sync file system before every operation** (default: enabled)  
   whether to synchronise the file system state before processing requests from Serena.  
   This is important to ensure that the plugin does not read stale data, but it can have a performance impact, 
   especially when using slow file systems (e.g. WSL file system while the IDE is running on Windows).
   Note, however, that without synchronisation being forced by the Serena plugin, you will have to ensure synchronisation yourself.
   Operations that apply changes to files in your project that are *not* made either in the IDE itself or by Serena may not be seen by the IDE. 
   Normally, the IDE synchronises automatically when it has the focus, using file watchers to achieve this (though this may or may not work reliably for the WSL file system). 
   Also, if you are working primarily in another application (e.g. AI chat), the IDE may not have the focus frequently. 
   So when external changes are made to your project, you will have to either give the IDE the focus (if that works) or trigger a sync manually (right-click root folder / Reload from Disk).  
   Further, note that even an edit made using, for example, Claude Code's internal editing tools would count as an external modification.
   Only Serena's editing tools are "JetBrains-aware" and will tell the IDE to update the state of the edited file.
   So if you are making AI-based edits using tools other than Serena's tools, do make sure that the lack of synchronisation is not a problem if you decide to disable this option.

## Usage with Other Editors

We realize that not everyone uses a JetBrains IDE as their main code editor.
You can still take advantage of the JetBrains plugin by running a JetBrains IDE instance alongside your
preferred editor. Most JetBrains IDEs have a free community edition that you can use for this purpose.
You just need to make sure that the project you are working on is open and indexed in the JetBrains IDE, 
so that Serena can connect to it.
