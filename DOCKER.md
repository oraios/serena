# Docker Setup for Serena (Experimental)

⚠️ **EXPERIMENTAL FEATURE**: The Docker setup for Serena is currently experimental and has several limitations. Please read this entire document before using Docker with Serena.

## Overview

Docker support allows you to run Serena in an isolated container environment, which provides better security isolation for the shell tool and consistent dependencies across different systems.

## Benefits

- **Safer shell tool execution**: Commands run in an isolated container environment
- **Consistent dependencies**: No need to manage language servers and dependencies on your host system
- **Cross-platform support**: Works consistently across Windows, macOS, and Linux

## Important Limitations and Caveats

### 1. Configuration File Conflicts

⚠️ **Critical**: Docker uses a separate configuration file (`serena_config.docker.yml`) to avoid path conflicts. When running in Docker:
- Container paths will be stored in the configuration (e.g., `/workspaces/serena/...`)
- These paths are incompatible with non-Docker usage
- After using Docker, you cannot directly switch back to non-Docker usage without manual configuration adjustment

### 2. Project Activation Limitations

- **Only mounted directories work**: Projects must be mounted as volumes to be accessible
- Projects outside the mounted directories cannot be activated or accessed
- Default setup only mounts the current directory

### 3. GUI Window Disabled

- The GUI log window option is automatically disabled in Docker environments
- Use the web dashboard instead (see below)

### 4. Dashboard Port Configuration

The web dashboard runs on port 24282 (0x5EDA) by default. You can configure this using environment variables:

```bash
# Use default ports
docker-compose up serena

# Use custom ports
SERENA_DASHBOARD_PORT=8080 docker-compose up serena
```

⚠️ **Note**: If the local port is occupied, you'll need to specify a different port using the environment variable.

### 5. Line Ending Issues on Windows

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

### Using Docker directly

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

## Migration Path

To switch between Docker and non-Docker usage:

1. **Docker to Non-Docker**:
   - Manually edit project paths in `serena_config.yml`
   - Change container paths to host paths
   - Or use separate config files for each environment

2. **Non-Docker to Docker**:
   - Projects will be re-registered with container paths
   - Original config remains unchanged

## Future Improvements

We're working on:
- Automatic config migration between environments
- Better project path handling
- Dynamic port allocation
- Windows line-ending handling.
