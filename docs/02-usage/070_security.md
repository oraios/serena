# Security Considerations

Security is important to us, and we take this topic seriously.

## Serena's Assumptions

The current security model for Serena assumes:

- the local machine is trusted,  
- the MCP client (i.e. the LLM) is trusted,
- the code repository being worked on is trusted,
- user configuration is trusted,
- package manager configuration (e.g. npm) for downloading additional dependencies (i.e. language servers when using Serena with the LSP backend) is trusted.

Serena contains tools for executing shell commands and modifying files.
As such tools are, however, an essential part of coding agent workflows, they typically need to be made available – and need to be made available in a flexible, general form.
Therefore, the only way to *fully* protect against unintended consequences is to use a [sandboxed environment](sandboxing) for running Serena.

:::{admonition} Security Advisories
:class: note
Security advisories are welcome for issues that violate the security model described on this page.
However, reports which amount to noting that Serena's tools can execute commands or modify files
describe intended functionality rather than vulnerabilities, and we will reject advisories that fail to recognise this
or otherwise ignore the above assumptions.  
Sandboxing is the *only* way to fully protect against unintended consequences when using coding agents;
constraints on the tools themselves cannot achieve this and are therefore not an approach we pursue.
:::

## General Recommendations for Risk Reduction

To reduce the risk of unintended consequences, we recommend that you:
- back up your work regularly (keep the project being worked on under version control),
- restrict the set of allowed tools via the [configuration](050_configuration),
- do not expose [Serena's network services](network-security) to untrusted networks.

If you do not fully trust the client/the LLM, we additionally recommend to monitor tool executions carefully 
(provided that your MCP client supports this).

(sandboxing)=
## Sandboxing

Sandboxing is the most effective way to mitigate risks when using coding agents.
[Running Serena inside a docker container](docker) which only exposes the necessary files and tools to the agent is a good way to achieve this.

While setting up a sandboxed environment may require some initial effort, we highly recommend it for all security-conscious users.

(network-security)=
## Network Security

Serena includes several network services:
- the Serena MCP server itself (when run in [HTTP or SSE mode](streamable-http) instead of stdio mode)
- the Serena Dashboard web server
- the Serena JetBrains Plugin server, which runs within the JetBrains IDE (when using the JetBrains language backend)
- the Serena Project Server (only started explicitly for [project querying](query-projects)) 

By default, these services accept connections from localhost only, which is a secure default for most users
(given our assumption that the local machine is trusted; see above).

These services can be reconfigured to listen on other addresses, but doing so may have security implications.
If you need to allow connections from other machines, we recommend that you set up a secure networking environment 
(e.g. using a VPN or SSH tunnels) and ensure that only trusted machines can connect to these services.

## Supply Chain Security

Serena has two language backends with different security characteristics:

- the JetBrains-based variant, which integrates with a running JetBrains IDE, and
- the language-server-based variant (the free variant), which can automatically acquire language server dependencies on demand.

While we can assume that JetBrains IDEs installed by the user do not pose a security risk,
language server dependencies (if not handled with care) could. 
For convenience, Serena downloads or installs certain language server dependencies on demand.
We treat this path as security-sensitive and have hardened it accordingly.

The most important supply chain protections are:

- exact version pinning,
- hash verification,
- host restriction,
- and isolated Serena-managed installation directories.

### Auto-Downloaded Language Server Dependencies

For language servers that are auto-installed by downloading archives, binaries, VSIX packages, NuGet packages, or other release artifacts, Serena uses a hardened shared download path with the following protections:

- **Pinned versions by default**: default downloads use exact versions instead of floating `latest` or nightly channels.
- **Integrity verification**: downloaded artifacts are checked against pinned SHA256 hashes stored in Serena's source code.
- **Host allowlists**: download URLs are restricted to the expected hosts for a given dependency.
- **Safe extraction**: archive extraction validates paths to prevent path traversal and zip-slip style attacks.
- **Managed install locations**: dependencies are installed into Serena-managed directories instead of into the project repository.

In practice, this means that a downloaded artifact must match all of the following:

- the expected version,
- the expected host,
- the expected SHA256 checksum,
- and the expected extraction layout.

If any of these checks fail, Serena aborts the installation instead of continuing.

### npm-Based Language Servers

Some language servers are distributed primarily through npm. For those, Serena currently uses pinned package versions and installs them into Serena-managed directories.

By default, Serena uses the **user's normal npm configuration**. We do **not** force a registry override unless one is explicitly configured. If needed, both the package version and the registry can be overridden through `ls_specific_settings`.

For npm-based installs, Serena's current security posture is based on these rules:

- **Exact package versions are pinned by default**.
- **The install location is isolated from the project** and lives in Serena-managed language-server directories.
- **The user's npm configuration is trusted by default**.
- **Repository and user configuration are assumed to be trusted**.

This means Serena protects well against accidental version drift, but npm installs still rely on the npm ecosystem and package-manager execution model. In particular, Serena does **not** currently use lockfile-based `npm ci` installs for bundled language-server dependencies.

### `uvx` and Python Dependency Pinning

Some parts of Serena rely on `uv` / `uvx`.

One important detail is that `uvx` ignores the lockfile when installing directly from a Git repository. Because of that, we pin Serena's Python dependencies exactly in `pyproject.toml` so that installations from Git still resolve to exact dependency versions rather than floating ranges.

Some language servers also use exact pinned versions when invoking them through `uvx` / `uv tool run`. 
