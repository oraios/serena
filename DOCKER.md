# Docker Setup for Serena (Experimental)

⚠️ **EXPERIMENTAL FEATURE**: The Docker setup for Serena is still experimental and has some limitations. Please read this entire document before using Docker with Serena.

## Overview

Docker support allows you to run Serena in an isolated container environment, which provides better security isolation for the shell tool and consistent dependencies across different systems.

## Benefits

- **Safer shell tool execution**: Commands run in an isolated container environment
- **Consistent dependencies**: No need to manage language servers and dependencies on your host system
- **Cross-platform support**: Works consistently across Windows, macOS, and Linux

## Quick Start

The image `ghcr.io/oraios/serena` runs the Serena MCP server over stdio, with the project mounted at `/workspace` activated on startup:

```bash
docker run --rm -i -v /path/to/your/project:/workspace ghcr.io/oraios/serena:latest
```

To use it, configure your MCP client to start the container. For example, for clients using the common `mcpServers` format:

```json
{
  "mcpServers": {
    "serena": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-v", "/path/to/your/project:/workspace", "ghcr.io/oraios/serena:latest"]
    }
  }
}
```

Note: use `-i` only, not `-it`; a TTY corrupts the stdio stream.

Clients that support setting the working directory allow for a portable configuration using a relative mount.
For example, for [Continue](https://continue.dev):

```yaml
name: Serena
version: 0.0.1
schema: v1
mcpServers:
  - name: serena
    type: stdio
    command: docker
    cwd: ${{ secrets.HOST_REPO_PATH }}
    args:
      - run
      - --rm
      - -i
      - -v
      - ./:/workspace
      - ghcr.io/oraios/serena:latest
```

with `HOST_REPO_PATH` set to the absolute path of the project on the host (e.g. in `.continue/.env`).
Using the host path matters when the editor itself runs in a dev container: bind mount paths are resolved by the Docker host, not by the editor's container.

### Passing Further Options

Arguments after the image name replace the default command, so they must include the full `start-mcp-server` invocation, e.g. to set a context:

```bash
docker run --rm -i -v /path/to/your/project:/workspace ghcr.io/oraios/serena:latest \
  start-mcp-server --transport stdio --project /workspace --context ide
```

### Adding Language Support

The image contains Serena only, without any language toolchains.
Build your own image on top of it, adding the toolchains your project needs.
See [`examples/docker/`](examples/docker/) for examples and guidance.

### Using HTTP Instead of stdio

If your client cannot start processes, you may run the server over HTTP instead:

```bash
docker run --rm -p 127.0.0.1:9121:9121 -v /path/to/your/project:/workspace ghcr.io/oraios/serena:latest \
  start-mcp-server --transport streamable-http --host 0.0.0.0 --port 9121 --project /workspace
```

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
- The project mounted at `/workspace` is activated automatically
- Projects outside the mounted directories cannot be activated or accessed
- Since projects are not remembered across container restarts (unless you mount a local configuration as described above),
  activate further projects using their full path inside the container when using dynamic project activation

### Dashboard

The web dashboard listens on port 24282 (0x5EDA) inside the container. To access it, publish the port:

```bash
docker run --rm -i -p 127.0.0.1:24282:24282 -v /path/to/your/project:/workspace ghcr.io/oraios/serena:latest
```

The dashboard is then available at http://localhost:24282/dashboard.
If the port is occupied, map a different host port, e.g. `-p 127.0.0.1:8080:24282`.

### Environment Variables

- `INTELEPHENSE_LICENSE_KEY`: License key for Intelephense PHP LSP premium features (optional).
  Pass it to the container with `-e INTELEPHENSE_LICENSE_KEY=...`.

### Line Ending Issues on Windows

⚠️ **Windows Users**: Be aware of potential line ending inconsistencies:
- Files edited within the Docker container may use Unix line endings (LF)
- Your Windows system may expect Windows line endings (CRLF)
- This can cause issues with version control and text editors
- Configure your Git settings appropriately: `git config core.autocrlf true`

## Developing Serena

The `compose.yaml` in the repository root and the devcontainer configuration are intended for developing Serena itself.
To use Serena with your own project, follow the instructions above.

## Troubleshooting

### Port Already in Use

If you see "port already in use" errors:
```bash
# Check what's using the port
lsof -i :24282  # macOS/Linux
netstat -ano | findstr :24282  # Windows
```
Then map a different host port, as described in [Dashboard](#dashboard).

### Project Access Issues

Ensure projects are properly mounted:
- Check the `-v` volume mounts of your `docker run` command
- Use absolute paths for projects
- Verify permissions on mounted directories. The container runs as a non-root user (UID 1000);
  on Linux hosts, the mounted project must be writable by this user, as Serena stores project data in its `.serena` directory.
