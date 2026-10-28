# Extending the Serena Docker image

The Serena image (`ghcr.io/oraios/serena`) contains Serena and nothing else: no language toolchains.
Language servers that Serena downloads on the fly often still need a runtime (e.g. Node.js for npm-based servers),
and some languages need their full toolchain to be analysed properly.

Rather than shipping every toolchain for every supported language, the intended workflow is:
build your own image on top of Serena's, adding only what your project needs.

## Examples

| Directory         | Adds                                                                   |
|-------------------|------------------------------------------------------------------------|
| `infrastructure/` | OpenTofu (aliased as `terraform`) and Node.js (for the Ansible language server) |
| `rust/`           | The Rust toolchain, `rust-analyzer`, and a C compiler for build scripts |

Each directory is self-contained. Copy the one closest to your needs into your project and adjust it.

## Usage

Build the image from within the example directory:

```bash
docker compose build
```

Serena communicates with your MCP client over stdio. Configure your client to start the container, mounting your project at `/workspace`:

```bash
docker run --rm -i -v /path/to/your/project:/workspace serena-rust:latest
```

Alternatively, with the compose file (`PROJECT_DIR` defaults to the directory containing `compose.yaml`):

```bash
PROJECT_DIR=/path/to/your/project docker compose run --rm -T serena
```

Pass `--service-ports` to `docker compose run` to make the dashboard reachable at http://localhost:24282/dashboard.

## Writing your own

The image runs as the non-root user `serena`. Keep this in mind when adding toolchains:

* Switch to `USER root` to install things, and back to `USER serena` at the end.
* Install everything at build time. Toolchain directories owned by root cannot be modified at runtime,
  so anything Serena would otherwise install on demand (e.g. `rustup component add rust-analyzer`) must be added in the Dockerfile.
* Point caches that are written at runtime (e.g. `CARGO_HOME`) to a location under `/home/serena`.
* Prefer copying toolchains from their official images (`COPY --from=...`) over install scripts.
