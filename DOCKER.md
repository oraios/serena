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

Serena's configuration and log files are stored in the container in `/home/serena/.serena`.
Any local configuration you may have for Serena will not apply; the container uses its own separate configuration.

You can mount a local configuration/data directory to persist settings across container restarts
(which will also contain session log files).
Simply mount your local directory to `/home/serena/.serena` in the container.
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

A basic example of using Serena for your own toolchain can be seen in `examples/docker/

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

#### Using Serena with other projects

For developing your own project with Serena you may use the following command. 

By default this will mount the local directory that the compose file is started in.

   ```bash
   docker-compose up serena
   ```

To override this behavior pass in the `PROJECT_DIR` environment variable at the CLI or by modifying the compose file. 

   ```bash
   PROJECT_DIR="../reponame" docker-compose up serena
   ```

#### For Serena Development

To develop the Serena codebase you can run the following command

   ```bash
   docker-compose -f compose-dev.yaml up
   ```

### Building the Docker Image Manually

```bash
# Build the image
docker build -t serena .

# Run with current directory mounted
docker run -it --rm \
  -v "$(pwd)":/workspace \
  -p 9121:9121 \
  -p 24282:24282 \
  serena
```

## Accessing the Dashboard

Once running, access the web dashboard at:

http://localhost:24282/dashboard

## Volume Mounting

To work with projects, you must mount them as volumes:

  ```yaml
  # In compose.yaml
  volumes:
    - ./my-project:/workspace/
  ```

   ```bash
   # Using the environment variable
   PROJECT_DIR="../reponame" docker-compose up serena
   ```

## Environment Variables

- `SERENA_PORT`: MCP server port (default: `9121`)
- `SERENA_DASHBOARD_PORT`: Web dashboard port (default: `24282`)
- `PROJECT_DIR`: The local project directory to mount into the container (default: `./`)
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

### Project Access Issues

Ensure projects are properly mounted:
- Check volume mounts in `compose.yaml`
- Use absolute paths for external projects
- Verify permissions on mounted directories
