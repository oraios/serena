# The Dashboard and GUI Tool

Murena comes with built-in tools for monitoring and managing the current session:

* the **web-based dashboard** (enabled by default)
  
  The dashboard provides detailed information on your Murena session, the current configuration and provides access to logs.
  Some settings (e.g. the current set of active programming languages) can also be directly modified through the dashboard.

  The dashboard is supported on all platforms.
  
  By default, it will be accessible at `http://localhost:24282/dashboard/index.html`,
  but a higher port may be used if the default port is unavailable/multiple instances are running.

  **We recommend always enabling the dashboard**. If you don't want the browser to open automatically,
  you can disable it while still keeping the dashboard running in the background (see below).

* the **GUI tool** (disabled by default)
  
  The GUI tool is a native application window which displays logs.
  It furthermore allows you to shut down the agent and to access the dashboard's URL (if it is running). 

  This is mainly supported on Windows, but it may also work on Linux; macOS is unsupported.

Both can be configured in Murena's [configuration](050_configuration) file (`murena_config.yml`).
If enabled, they will automatically be opened as soon as the Murena agent/MCP server is started.
For the dashboard, this can be disabled if desired (see below).

## Disabling Automatic Browser Opening

If you prefer not to have the dashboard open automatically (e.g., to avoid focus stealing), you can disable it
by setting `web_dashboard_open_on_launch: False` in your `murena_config.yml` or by passing `--open-web-dashboard False`
to `start-mcp-server` CLI command.

When automatic opening is disabled, you can still access the dashboard by:
* asking the LLM to "open the Murena dashboard", which will open the dashboard in your default browser
  (the tool `open_dashboard` is enabled for this purpose, provided that the dashboard is active, 
  not opened by default and the GUI tool, which can provide the URL, is not enabled)
* navigating directly to the URL (see above)
