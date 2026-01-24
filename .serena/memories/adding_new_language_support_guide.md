# Adding New Language Support to Murena

This guide explains how to add support for a new programming language to Murena.

## Overview

Adding a new language involves:

1. **Language Server Implementation** - Creating a language-specific server class
2. **Language Registration** - Adding the language to enums and configurations  
3. **Test Repository** - Creating a minimal test project
4. **Test Suite** - Writing comprehensive tests

## Step 1: Language Server Implementation

### 1.1 Create Language Server Class

Create a new file in `src/solidlsp/language_servers/` (e.g., `new_language_server.py`).

#### Providing the Launch Command via a DependencyProvider

All language servers use the `DependencyProvider` pattern to handle 
  * runtime dependency installation/discovery
  * launch command creation (and, optionally, environment setup)

To implement a new language server using the DependencyProvider pattern:
  * Pass `None` for `process_launch_info` in `super().__init__()` - the base class creates it via `_create_dependency_provider()`
  * Implement `_create_dependency_provider()` to return an inner `DependencyProvider` class instance.
    In simple cases, it can be instantiated with only two parameters: 
    ```python
    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
         return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)
    ```
    The resource dir that is passed is the directory in which installed dependencies should be stored!

**Base Classes:**

- **`LanguageServerDependencyProviderSinglePath`** - For language servers with a single core dependency (e.g., an executable or JAR file)
  - Provides automatic support for the `ls_path` custom setting, allowing users to override the core dependency path (if they have it installed it themselves)
  - Implement `_get_or_install_core_dependency()` to return the path to the core dependency, downloading/installing it automatically if necessary
  - Implement `_create_launch_command(core_path)` to build the full command from the core path
  - Reference implementations: `TypeScriptLanguageServer`, `Intelephense`, `ClojureLSP`, `ClangdLanguageServer`, `PyrightServer`

- **`LanguageServerDependencyProvider`** - The base class, which can be directly inherited from for complex cases with multiple dependencies or custom setup
  - Implement `create_launch_command()` directly
  - Reference implementations: `EclipseJDTLS`, `CSharpLanguageServer`, `MatlabLanguageServer`

**Implementation Pointers::**
  - When returning the command, prefer the list-based representation for robustness
  - Override `create_launch_command_env` if the launch command needs environment variables to be set (defaults to `{}` in the base implementation)

You should look at at least one existing implementation of each base class to understand how they work.

### 1.2 LSP Initialization

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

After `_start_server` returns, the language server should be fully operational.
If the server requires that one waits for certain notifications or responses before being ready, implement that logic here.
For an example, see `EclipseJDTLS._start_server`.

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
def create(cls, config: LanguageServerConfig, repository_root_path: str) -> "SolidLanguageServer":
    match config.code_language:
        # Existing cases...
        case Language.NEW_LANGUAGE:
            from solidlsp.language_servers.new_language_server import NewLanguageServer
            return NewLanguageServer(config, repository_root_path)
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

Testing the language server implementation is of crucial importance, and the tests will
form the main part of the review process. Make sure that the tests are up to the standard
of Murena to make the review go smoother.

General rules for tests:

1. Tests for symbols and references should always check that the expected symbol names and references were actually found.
   Just testing that a list came back or that the result is not None is insufficient.
2. Tests should never be skipped, the only exception is skipping based on some package being available or on an unsupported OS.
3. Tests should run in CI, check if there is a suitable GitHub action for installing the dependencies.

### 4.1 Basic Tests

Create `test/solidlsp/new_language/test_new_language_basic.py`.
Have a look at the structure of existing tests, for example, in `test/solidlsp/php/test_php_basic.py`
You should at least test:

1. Finding symbols
2. Finding within-file references
3. Finding cross-file references

Have a look at `test/solidlsp/php/test_php_basic.py` as an example for what should be tested.
Don't forget to add a new language marker to `pytest.ini`.

### 4.2 Integration Tests

Consider adding new cases to the parametrized tests in `test_murena_agent.py` for the new language.


### 5 Documentation

Update:

- **README.md** - Add language to the list of languages
- **docs/01-about/020_programming-languages.md** - Add language to the list and mention any special notes, compatibility or requirements (e.g. installations the user is required to do)
- **CHANGELOG.md** - Document the new language support
