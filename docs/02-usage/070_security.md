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
As such tools are, however, an essential part of coding agent workflows, they typically need to be made available. 
Therefore, the only way to *fully* protect against unintended consequences is to use a [sandboxed environment](sandboxing) for running Serena.

## General Recommendations for Risk Reduction

To reduce the risk of unintended consequences, we recommend that you:
- back up your work regularly (keep the project being worked on under version control),
- restrict the set of allowed tools via the [configuration](050_configuration),
- do not expose [Serena's network services](network-security) to untrusted networks.

If you do not fully the trust the client/the LLM, we additionally recommend to monitor tool executions carefully 
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

For the `ty` Python language server, Serena also uses an exact pinned version when invoking it through `uvx`.

```{dropdown} What Serena Downloads by Default for Language Servers
:open:

Only the language servers listed below download or install additional dependencies automatically by default when the required dependency is missing. Everything else either relies on a system-installed server or on tooling you install separately.

### Release Artifacts, Archives, or VSIX Packages

- **AL**: the pinned Microsoft AL VS Code extension (`ms-dynamics-smb.al`) from the VS Code Marketplace.
- **C/C++ (`clangd`)**: pinned `clangd` release archives on supported platforms.
- **C# (Roslyn LS)**: pinned Roslyn language-server NuGet package for the current platform.
- **Clojure**: pinned `clojure-lsp` release artifact.
- **Dart**: pinned Dart SDK archive that contains the language server.
- **Elixir (`expert`)**: pinned Expert release binary, if not already available locally.
- **Groovy**: pinned `vscode-java` runtime bundle used to provide Java for the Groovy LS setup.
- **HLSL / shader-language-server**: pinned GitHub release artifacts on supported prebuilt platforms.
- **Java (`eclipse.jdt.ls`)**: pinned Gradle distribution, pinned `vscode-java` extension bundle, and pinned IntelliCode VSIX.
- **Kotlin**: pinned Kotlin LSP archive.
- **Lua**: pinned `lua-language-server` release archive.
- **Luau**: pinned `luau-lsp` release archive. In Roblox or standard-doc modes it may also download Luau/Roblox docs and type-definition files.
- **Markdown (`marksman`)**: pinned Marksman release binary.
- **MATLAB**: the pinned MathWorks MATLAB VS Code extension from the VS Code Marketplace.
- **OmniSharp (legacy C# backend)**: pinned OmniSharp and Razor plugin archives.
- **Pascal**: pinned Pascal language-server release artifact.
- **PHP (`phpactor`)**: pinned `phpactor.phar`.
- **PowerShell**: pinned PowerShell Editor Services archive.
- **SystemVerilog (`verible`)**: pinned Verible release archive on supported platforms.
- **TOML (`taplo`)**: pinned Taplo release artifact.
- **Terraform**: pinned `terraform-ls` release archive. The Terraform CLI itself must still already be installed.

### npm Package Installs

- **Ansible**: `@ansible/ansible-language-server`
- **Bash**: `bash-language-server`
- **Elm**: `@elm-tooling/elm-language-server`
- **PHP (`intelephense`)**: `intelephense`
- **Solidity**: `@nomicfoundation/solidity-language-server`
- **TypeScript**: `typescript` and `typescript-language-server`
- **Vue**: `@vue/language-server`, plus `typescript` and `typescript-language-server`
- **VTSLS**: `@vtsls/language-server`
- **YAML**: `yaml-language-server`

All of the above are installed with exact pinned package versions by default, into Serena-managed directories.

### Other Package-Manager Based Installs

- **F#**: installs pinned `fsautocomplete` via `dotnet tool install`.
- **Ruby (`ruby-lsp`)**: if not already available through Bundler or as a global executable, Serena installs a pinned `ruby-lsp` gem.
- **Python (`ty`)**: launched through `uvx` / `uv x` using an exact pinned `ty` version.
- **HLSL on macOS**: if no prebuilt binary is used, Serena builds `shader_language_server` from a pinned version using Cargo.

### No Automatic Download by Serena

- **Python (`pyright`)**: Serena uses the locally available Python environment and starts `pyright.langserver` from there.
- **Go (`gopls`)**, **Rust (`rust-analyzer`)**, and several other system-tool based integrations expect the language server to be available locally and do not download it automatically.
```
