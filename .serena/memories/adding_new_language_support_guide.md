# Adding New Language Support to Serena

This guide explains how to add support for a new programming language to Serena.

## Overview

Adding a new language involves:

1. **Language Server Implementation** - Creating a language-specific server class
2. **Language Registration** - Adding the language to enums and configurations  
3. **Test Repository** - Creating a minimal test project
4. **Test Suite** - Writing comprehensive tests
5. **Runtime Dependencies** - Configuring automatic language server downloads

## Step 1: Language Server Implementation

### 1.1 Create Language Server Class

Create a new file in `src/solidlsp/language_servers/` (e.g., `new_language_server.py`).
Have a look at `intelephense.py` for a reference implementation of a language server which downloads all its dependencies, at `gopls.py` for an LS that needs some preinstalled
dependencies, and on `pyright_server.py` that does not need any additional dependencies
because the language server can be installed directly as python package.


```python
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

class NewLanguageServer(SolidLanguageServer):
    """
    Language server implementation for NewLanguage.
    """
    
    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        # Determine language server command
        cmd = self._get_language_server_command()
        
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "new_language",  # Language ID for LSP
        )
    
    def _get_language_server_command(self) -> list[str]:
        """Get the command to start the language server."""
        # Example: return ["new-language-server", "--stdio"]
        pass
    
    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """Define language-specific directories to ignore."""
        return super().is_ignored_dirname(dirname) or dirname in ["build", "dist", "target"]
```

### 1.2 Language Server Discovery and Installation

For languages requiring automatic installation, implement download logic similar to C#:

```python
@classmethod
def _ensure_server_installed(cls, logger: LanguageServerLogger) -> str:
    """Ensure language server is installed and return path."""
    # Check system installation first
    system_server = shutil.which("new-language-server")
    if system_server:
        return system_server
    
    # Download and install if needed
    server_path = cls._download_and_install_server(logger)
    return server_path

def _download_and_install_server(cls, logger: LanguageServerLogger) -> str:
    """Download and install the language server."""
    # Implementation specific to your language server
    pass
```

### 1.3 LSP Initialization

Override initialization methods if needed:

```python
def _get_initialize_params(self) -> InitializeParams:
    """Return language-specific initialization parameters."""
    return {
        "processId": os.getpid(),
        "rootUri": PathUtils.path_to_uri(self.repository_root_path),
        "capabilities": {
            # Language-specific capabilities
        }
    }

def _start_server(self):
    """Start the language server with custom handlers."""
    # Set up notification handlers
    self.server.on_notification("window/logMessage", self._handle_log_message)
    
    # Start server and initialize
    self.server.start()
    init_response = self.server.send.initialize(self._get_initialize_params())
    self.server.notify.initialized({})
```

## Step 2: Language Registration

### 2.1 Add to Language Enum

In `src/solidlsp/ls_config.py`, add your language to the `Language` enum:

```python
class Language(str, Enum):
    # Existing languages...
    NEW_LANGUAGE = "new_language"
    
    def get_source_fn_matcher(self) -> FilenameMatcher:
        match self:
            # Existing cases...
            case self.NEW_LANGUAGE:
                return FilenameMatcher("*.newlang", "*.nl")  # File extensions
```

### 2.2 Update Language Server Factory

In `src/solidlsp/ls.py`, add your language to the `create` method:

```python
@classmethod
def create(cls, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str) -> "SolidLanguageServer":
    match config.code_language:
        # Existing cases...
        case Language.NEW_LANGUAGE:
            from solidlsp.language_servers.new_language_server import NewLanguageServer
            return NewLanguageServer(config, logger, repository_root_path)
```

## Step 3: Test Repository

### 3.1 Create Test Project

Create a minimal project in `test/resources/repos/new_language/test_repo/`:

```
test/resources/repos/new_language/test_repo/
├── main.newlang              # Main source file
├── lib/
│   └── helper.newlang       # Additional source for testing
├── project.toml             # Project configuration (if applicable)
└── .gitignore              # Ignore build artifacts
```

### 3.2 Example Source Files

Create meaningful source files that demonstrate:

- **Classes/Types** - For symbol testing
- **Functions/Methods** - For reference finding
- **Imports/Dependencies** - For cross-file operations
- **Nested Structures** - For hierarchical symbol testing

Example `main.newlang`:
```
import lib.helper

class Calculator {
    func add(a: Int, b: Int) -> Int {
        return a + b
    }
    
    func subtract(a: Int, b: Int) -> Int {
        return helper.subtract(a, b)  // Reference to imported function
    }
}

class Program {
    func main() {
        let calc = Calculator()
        let result = calc.add(5, 3)  // Reference to add method
        print(result)
    }
}
```

## Step 4: Test Suite

### 4.1 Basic Tests

Create `test/solidlsp/new_language/test_new_language_basic.py`. You should at least test:

1. Finding symbols
2. Finding within-file references
3. Finding cross-file references

Have a look at `test/solidlsp/php/test_php_basic.py` as an example for what should be tested.
Don't forget to add a new language marker to `pytest.ini`.

### 4.2 Integration Tests

Consider adding new cases to the parametrized tests in `test_serena_agent.py` for the new language.


### 5 Documentation

Update:

- **README.md** - Add language to supported languages list
- **CHANGELOG.md** - Document the new language support
- **Language-specific docs** - Installation requirements, known issues
