# Security Considerations

Security and protection against supply chain attacks are important to us, and we take this topic seriously.

Serena comes in two main variants with different security characteristics:

- the **JetBrains-based variant**, which integrates with a running JetBrains IDE, and
- the **language-server-based variant** (the free variant), which can automatically acquire language-server dependencies on demand.

## JetBrains Variant

The JetBrains variant of Serena is safe by default.

At runtime, Serena does **not** download additional components and does **not** start extra helper processes beyond the Serena MCP server itself. It talks to the already running JetBrains IDE and relies on the IDE's own indexing and language intelligence.

This means that, from a supply-chain perspective, the JetBrains variant has a much smaller runtime attack surface than the language-server-based variant.

## Language-Server Variant

The language-server-based variant supports many languages, including languages whose language servers are not typically preinstalled on a machine. For convenience, Serena can therefore download or install certain language-server dependencies on demand.

We treat this path as security-sensitive and have hardened it accordingly.

### How Serena Secures Downloaded Language-Server Dependencies

For language servers that download archives, binaries, VSIX packages, NuGet packages, or other release artifacts, Serena uses a hardened shared download path with the following protections:

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

### Our Assumptions

The current security model for Serena's language-server variant assumes:

- the local machine is trusted,
- the checked-out repository is trusted,
- user configuration is trusted,
- package-manager configuration such as npm config is trusted unless explicitly overridden,
- and the main risk to defend against is compromised or unexpectedly changing upstream artifacts.

Under these assumptions, the most important supply-chain protections are:

- exact version pinning,
- hash verification,
- host restriction,
- and isolated Serena-managed installation directories.

## Operational Recommendations

As fundamental abilities for a coding agent, Serena contains tools for executing shell commands and modifying files. Therefore, if the respective tool calls are not monitored or restricted, and execution takes place in a sensitive environment, there is a risk of unintended consequences.

To reduce that risk, we recommend that you:

- back up your work regularly, for example by using Git,
- monitor tool executions carefully, if your MCP client supports this,
- consider enabling read-only mode for analysis-only sessions by setting `read_only: True` in `project.yml`,
- restrict the set of allowed tools via the [configuration](050_configuration),
- and use a sandboxed environment for running Serena, for example by [using Docker](docker).

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
