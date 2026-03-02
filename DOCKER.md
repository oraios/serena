# Docker Setup for Serena (Experimental)

⚠️ **EXPERIMENTAL FEATURE**: The Docker setup for Serena is still experimental and has some limitations. Please read this entire document before using Docker with Serena.

## Overview

Docker support allows you to run Serena in an isolated container environment, which provides better security isolation for the shell tool and consistent dependencies across different systems.

## Benefits

- **Safer shell tool execution**: Commands run in an isolated container environment
- **Consistent dependencies**: No need to manage language servers and dependencies on your host system
- **Cross-platform support**: Works consistently across Windows, macOS, and Linux

## Important Usage Pointers

### Configuration

Serena's configuration and log files are stored in the container in `/workspaces/serena/config/`.
Any local configuration you may have for Serena will not apply; the container uses its own separate configuration.

You can mount a local configuration/data directory to persist settings across container restarts
(which will also contain session log files).
Simply mount your local directory to `/workspaces/serena/config` in the container.
Initially, be sure to add a `serena_config.yml` file to the mounted directory which applies the following
special settings for Docker usage:
```
# Disable the GUI log window since it's not supported in Docker
gui_log_window: False
# Listen on all interfaces for the web dashboard to be accessible from outside the container
web_dashboard_listen_address: 0.0.0.0
# Disable opening the web dashboard on launch (not possible within the container)
web_dashboard_open_on_launch: False
```
Set other configuration options as needed.

### Project Activation Limitations

- **Only mounted directories work**: Projects must be mounted as volumes to be accessible
- Projects outside the mounted directories cannot be activated or accessed
- Since projects are not remembered across container restarts (unless you mount a local configuration as described above), 
  activate them using the full path (e.g. `/workspaces/projects/my-project`) when using dynamic project activation

### Language Support Limitations

The default Docker image does not include dependencies for languages that
require explicit system-level installations.
Only languages that install their requirements on the fly will work out of the box.

### Dashboard Port Configuration

The web dashboard runs on port 24282 (0x5EDA) by default. You can configure this using environment variables:

```bash
# Use default ports
docker-compose up serena

# Use custom ports
SERENA_DASHBOARD_PORT=8080 docker-compose up serena
```

⚠️ **Note**: If the local port is occupied, you'll need to specify a different port using the environment variable.

### Line Ending Issues on Windows

⚠️ **Windows Users**: Be aware of potential line ending inconsistencies:
- Files edited within the Docker container may use Unix line endings (LF)
- Your Windows system may expect Windows line endings (CRLF)
- This can cause issues with version control and text editors
- Configure your Git settings appropriately: `git config core.autocrlf true`

## Quick Start

### Using Docker Compose (Recommended)

1. **Production mode** (for using Serena as MCP server):
   ```bash
   docker-compose up serena
   ```

2. **Development mode** (with source code mounted):
   ```bash
   docker-compose up serena-dev
   ```

Note: Edit the `compose.yaml` file to customize volume mounts for your projects.

### Building the Docker Image Manually

```bash
# Build the image
docker build -t serena .

# Run with current directory mounted
docker run -it --rm \
  -v "$(pwd)":/workspace \
  -p 9121:9121 \
  -p 24282:24282 \
  -e SERENA_DOCKER=1 \
  serena
```

### Using Docker Compose with Merge Compose files

To use Docker Compose with merge files, you can create a `compose.override.yml` file to customize the configuration:

```yaml
services:
  serena:
    # To work with projects, you must mount them as volumes:
    volumes:
      - ./my-project:/workspace/my-project
      - /path/to/another/project:/workspace/another-project
    # Add the context for the IDE assistant option:
    command:
      - "uv run --directory . serena-mcp-server --transport sse --port 9121 --host 0.0.0.0 --context claude-code"
```

See the [Docker Merge Compose files documentation](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/) for more details on using merge files.

## Accessing the Dashboard

Once running, access the web dashboard at:
- Default: http://localhost:24282/dashboard
- Custom port: http://localhost:${SERENA_DASHBOARD_PORT}/dashboard

## Volume Mounting

To work with projects, you must mount them as volumes:

```yaml
# In compose.yaml
volumes:
  - ./my-project:/workspace/my-project
  - /path/to/another/project:/workspace/another-project
```

## Environment Variables

- `SERENA_DOCKER=1`: Set automatically to indicate Docker environment
- `SERENA_PORT`: MCP server port (default: 9121)
- `SERENA_DASHBOARD_PORT`: Web dashboard port (default: 24282)
- `INTELEPHENSE_LICENSE_KEY`: License key for Intelephense PHP LSP premium features (optional)

## Troubleshooting

### Port Already in Use

If you see "port already in use" errors:
```bash
# Check what's using the port
lsof -i :24282  # macOS/Linux
netstat -ano | findstr :24282  # Windows

# Use a different port
SERENA_DASHBOARD_PORT=8080 docker-compose up serena
```

### Configuration Issues

If you need to reset Docker configuration:
```bash
# Remove Docker-specific config
rm serena_config.docker.yml

# Serena will auto-generate a new one on next run
```

### Project Access Issues

Ensure projects are properly mounted:
- Check volume mounts in `docker-compose.yaml`
- Use absolute paths for external projects
- Verify permissions on mounted directories
