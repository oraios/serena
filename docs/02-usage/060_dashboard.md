# The Dashboard and GUI Tool

Serena comes with built-in tools for monitoring and managing the current session:

* the **web-based dashboard** (enabled by default)
  
  The dashboard provides detailed information on your Serena session, the current configuration and provides access to logs.
  Some settings (e.g. the current set of active programming languages) can also be directly modified through the dashboard.

  The dashboard is supported on all platforms.
  
  By default, it will be accessible at `http://localhost:24282/dashboard/index.html`,
  but a higher port may be used if the default port is unavailable/multiple instances are running.

* the **GUI tool** (disabled by default)
  
  The GUI tool is a native application window which displays logs.

  This is mainly supported on Windows, but it may also work on Linux; macOS is unsupported.

Both can be configured in Serena's [configuration](050_configuration) file (`serena_config.yml`).
If enabled, they will automatically be opened as soon as the Serena agent/MCP server is started.

## Disabling Automatic Browser Opening

If you prefer not to have the dashboard open automatically (e.g., to avoid focus stealing), you can disable it
by setting `web_dashboard_open_on_launch: False` in your `serena_config.yml`.

When automatic opening is disabled, you can still access the dashboard by:
* Navigating directly to `http://localhost:24282/dashboard/index.html` in your browser
* Asking the AI to use the `open_dashboard` tool, which will open the dashboard in your default browser
