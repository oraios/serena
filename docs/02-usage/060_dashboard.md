# The Dashboard and GUI Tool

Serena comes with built-in tools for monitoring and managing the current session:

* the **Serena Dashboard** (enabled by default)
  
  The dashboard provides detailed information on your Serena session, the current configuration and provides access to logs.
  Some settings (e.g. the current set of active programming languages) can also be directly modified through the dashboard.

  The dashboard is supported on all platforms.

* the **GUI Log Viewer** (disabled by default)
  
  The GUI tool is a legacy native application which displays Serena's live logs.

  This is mainly supported on Windows, but it may also work on Linux; macOS is unsupported.

Both can be configured in Serena's [configuration](050_configuration) file (`serena_config.yml`).

## The Serena Dashboard

The dashboard is a web application, which is opened in one of three ways:

  * via a native application wrapper with accompanying tray icon (on supported platforms)
  * via a tray manager that aggregates multiple instances (on supported platforms) 
  * via your default web browser (supported on all platforms)

Configure your preferred interface via the setting `web_dashoard_interface` in [Serena's global configuration file](global-config) (see below).

By default, the dashboard can be accessed at `http://localhost:24282/dashboard/index.html`,
but a higher port may be used if the default port is unavailable/multiple instances are running.

### Features

The dashboard provides ...
 * a detailed overview of
   * the current Serena status and configuration (e.g. active tools, active programming languages, enabled modes and contexts, etc.)
   * ongoing and past tool calls (and statistics on tool usage)
 * access to Serena's live logs
 * the ability to modify settings (e.g. the set of active programming languages) on the fly
 * the ability to edit 
   * configuration files (global `serena_config.yml` and project-specific `project.yml`)
   * memories of the current project
 * the ability to shut down the Serena MCP server.

### Configuring the Dashboard

You can configure settings for the dashboard in the [global configuration file](global-config).

In particular, you can configure
 * the interface through which the dashboard is accessed (see above)
 * whether the dashboard is enabled at all.  
   We highly recommend keeping it enabled, as it provides valuable insights into Serena's operation and allows you to adjust configuration conveniently.
 * whether the dashboard window is opened automatically when Serena is started (see below).
 * network settings (for cases where you might want to access the Dashboard non-locally).

#### Dashboard Opening Behaviour

When Serena is started, the Dashboard window is opened by default in order to make users aware of its existence.

If you prefer not to have this happen, you can prevent it from opening
by setting `web_dashboard_open_on_launch: False` in the [global configuration file](global-config) or by passing `--open-web-dashboard False`
to the `start-mcp-server` CLI command.

On platforms supporting the tray icon (see also configuration option `web_dashboard_interface`), 
you can conveniently open the dashboard at any time by clicking on the tray icon, so automatic
opening is not a requirement to be able to access the dashboard on these platforms.

On other platforms, you may still access it by
* asking the LLM to "open the Serena dashboard", which will open the dashboard in your default browser
  (the tool `open_dashboard` is enabled for this purpose, provided that the dashboard is active, 
  not opened by default and the GUI tool, which can provide the URL, is not enabled)
* navigating directly to the URL (see above).

## The GUI Log Viewer

The Serena GUI Log Viewer is a legacy application which provides access to Serena's live logs.

Via its menu, it furthermore allows you to 
 * shut down the agent
 * access the dashboard's URL (if it is running).

The tool is mainly supported on Windows, but it may work on some Linux systems as well (depending on your desktop environment).

To enable the tool, set `gui_log_window` to `true` in Serena's [global configuration file](global-config).