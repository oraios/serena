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

(trusted-projects)=
## Trusted Projects

Sandboxing limits what Serena can affect while doing what it was asked to do.
The notion of *trusted projects* (introduced in Serena v1.6.0) addresses a different question: 
to what extent may the repository being worked on influence Serena's behaviour in the first place?

A project is an input authored by whoever produced the repository, and it comprises more than source code:
it also carries configuration (`.serena/project.yml`) as well as file system structure.
Trust determines whether such repository-supplied input may influence Serena beyond having the code read and
analysed as code — for example, by executing commands, by changing how dependencies are acquired, or by causing
Serena to access locations outside the project root.
Trust is decided by the project's root path, which is matched against `trusted_project_path_patterns` in Serena's
[global configuration](global-config).

We gate a feature on project trust whenever honouring repository-supplied input could have an effect beyond the
scope of what the user visibly requested: activating a project is not a request to run a command, and searching a
project's files is not a request to read files outside of it.

### A Functionality Boundary, Not a Containment Boundary

Untrusted projects are not sandboxed, restricted or otherwise contained.
They are read, analysed and edited just like any other project; the only difference is that a small set of
capabilities is unavailable to them.
As soon as the agent is asked to do anything at all, the full tool surface applies to an untrusted project as well:
commands can be executed, files can be modified, and the repository's contents can influence the LLM.

Consequently, our assumption that the repository being worked on is trusted (see above) remains fully in force.
Trust patterns eliminate a class of particularly straightforward attacks, namely those requiring no user
interaction beyond opening a project, but exploits can generally not be prevented by such means.
The question to ask is therefore not "is this project safe to work on because it is untrusted?" but rather
"do I trust this repository enough to grant it the additional capabilities?".
If a repository is not trustworthy, [sandboxing](sandboxing) is the answer, not the trust configuration.

### Trust-Gated Features

The set of trust-gated features is subject to change and can be expected to grow.
The settings that require trust are annotated accordingly in the project configuration (see
[configuration](050_configuration)); the two following current examples illustrate the principle:

- `activation_command` is a shell command that a project can request to be run whenever it is activated.
  Without trust gating, merely opening a repository in Serena would execute code chosen by its author,
  before the user has issued a single request.
- `ls_specific_settings` can, among other things, override the package version and the package registry from
  which a language server is acquired.
  Without trust gating, a repository could thereby silently circumvent the supply chain protections described
  below (version pinning, host restrictions) and cause attacker-controlled code to be downloaded and executed.

Note that the effective set of trusted paths depends on the age of your configuration: installations predating
the introduction of this setting retain a pattern that trusts all projects, ensuring that existing workflows are
not broken, whereas newly created configurations trust no project by default.
The applicable value can be inspected in the dashboard.

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
and ensure that only trusted machines can connect to these services.
It is the responsibility of the user to restrict access appropriately, e.g. by placing the service behind a reverse
proxy (adding authentication) or firewall.

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
