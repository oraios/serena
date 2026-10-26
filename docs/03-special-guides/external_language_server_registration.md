(external-ls-registration)=
# External Language Server Registration

SolidLSP, Serena's language server framework, is designed to be extensible.
Sometimes, you may need to use Serena with a language server for which there can be no built-in adapter,
e.g. because the language server in question is a custom development which is not yet released.

The general mechanism to make SolidLSP aware of an external language server is to use the
`LanguageServerRegistry` in order to register an `ExternalLanguageServerId`.

You can either do this
  * programmatically, in your own Python code, if you are launching Serena via a custom script
    where this code can be executed before Serena itself is started, or
  * via a Python package that exposes a `solidlsp.language_server_registration` entry point.
    If the Python package is installed in the same environment as Serena, 
    the language server will be automatically registered when Serena starts.

## Registering an External Language Server via a Python Package

Expose a Python entry point in the `solidlsp.language_server_registration` group (`pyproject.toml`):

```toml
[project.entry-points."solidlsp.language_server_registration"]
example = "myls:register_myls"
```

Corresponding contents of `myls/__init__.py`:

```python
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import FilenameMatcher, LanguageServerRegistry, ExternalLanguageServerId


class MyLanguageServerImpl(SolidLanguageServer):
    # implementation of the language server adapter
    pass


def register_myls() -> None:
    LanguageServerRegistry.get_instance().register(
        ExternalLanguageServerId(
            key="myls",
            matcher=FilenameMatcher(".example"),
            implementation=MyLanguageServerImpl
        )
    )
```

The registered key `myls` can subsequently be used in a project's configuration file (`project.yml`)
like any other language server:

```yaml
language_servers:
  - myls
```
