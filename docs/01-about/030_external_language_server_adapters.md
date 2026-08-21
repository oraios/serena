# External Language Server Adapters

Serena can load language-server integrations provided by installed Python packages. This lets a project use an external language server without adding its adapter to the Serena core.

## How It Works

An adapter package exposes a Python entry point in the `serena.language_servers` group:

```toml
[project.entry-points."serena.language_servers"]
example = "example_serena_adapter:register"
```

Serena discovers these entry points with Python's `importlib.metadata.entry_points()` at the regular `ProjectConfig.load()` lifecycle boundary. The loaded registration function provides the actual Python `SolidLanguageServer` implementation and calls the existing registry API:

```python
from solidlsp.ls_config import FilenameMatcher, register_ls


def register() -> None:
    register_ls(
        id="example",
        matcher=FilenameMatcher(".example"),
        implementation=ExampleLanguageServer,
    )
```

Several external adapters can be installed and registered at the same time. Their IDs can then be used in a project's `.serena/project.yml`:

```yaml
language_servers:
  - example
```

The registered implementation is started and managed by Serena. Serena launches the external server using the adapter's process configuration; it does not search for already-running LSP processes.

## Trust and Security

Only entry points exposed by installed Python packages are considered. Project configuration does not import Python code, accept arbitrary module paths, or perform filesystem-based plugin discovery. Serena does not install plugins automatically or download adapters from a marketplace.

An installed adapter contains executable Python code and therefore has the same trust implications as any other installed Python package. Install adapters only from sources you trust. The project can reference a registered ID, but it cannot cause an arbitrary Python module to be loaded through `project.yml`.

## Errors and IDs

A failure while reading the installed entry-point metadata is reported and leaves discovery retryable. If one adapter fails while loading or registering, Serena reports the entry-point name and distribution when available, rolls back that adapter's registrations, and continues loading other adapters.

A failed adapter ID is not available afterward. If a project references it, normal language-server configuration validation reports an unknown ID. Registered IDs must be unique and cannot replace a built-in Serena language-server ID.

## Built-in and External Integrations

Built-in Serena language servers are implemented and mapped inside the Serena distribution and use the existing built-in language-server IDs. An external adapter is implemented in its own Python package, registers its ID through the entry-point contract above, and supplies the integration required to launch and communicate with its language server.

This mechanism does not change Serena's language auto-detection. External adapters are available when explicitly registered and referenced in project configuration.
