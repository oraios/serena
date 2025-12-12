# Groovy Setup Guide for Serena

This guide explains how to prepare a Groovy project so that Serena can provide reliable code intelligence via Groovy Language Server and how to configure the server properly.

Serena automatically downloads and manages Java runtime dependencies for Groovy Language Server. However, you need to provide Groovy Language Server JAR file and optionally configure JAR options for optimal performance.

---
## Prerequisites

- Groovy Language Server JAR file
    - Can be any open-source Groovy language server or your custom implementation
    - The JAR must be compatible with standard LSP protocol

---
## Quick Start (Environment Variables)

The easiest way to configure Groovy Language Server is using environment variables:

1. **Set JAR path** (required):
   ```bash
   # Unix/Linux/Mac
   export GROOVY_LS_JAR_PATH='/path/to/groovy-language-server.jar'
   
   # Windows (Command Prompt)
   set GROOVY_LS_JAR_PATH="C:\path\to\groovy-language-server.jar"
   ```

2. **Set JAR options** (optional):
   ```bash
   # Example with memory settings
   export GROOVY_LS_JAR_OPTIONS="-Xmx2G -Xms512m"
   ```

3. **Start Serena** in your Groovy project root:
   ```bash
   serena
   ```

Serena will automatically detect Groovy files and start the language server using the specified JAR file and options.

---
## Manual Setup (Configuration File)

If you prefer permanent configuration, add settings to your `~/.serena/serena_config.yml`:

```yaml
ls_specific_settings:
  groovy:
    ls_jar_path: '/path/to/groovy-language-server.jar'
    ls_jar_options: '-Xmx2G -Xms512m'
```

### Configuration Options

- `ls_jar_path`: Absolute path to your Groovy Language Server JAR file (required)
- `ls_jar_options`: JVM options for the language server (optional)
    - Common options:
        - `-Xmx<size>`: Maximum heap size (e.g., `-Xmx2G` for 2GB)
        - `-Xms<size>`: Initial heap size (e.g., `-Xms512m` for 512MB)

---
## Project Structure Requirements

For optimal Groovy Language Server performance, ensure your project follows standard Groovy/Gradle structure:

```
project-root/
├── src/
│   ├── main/
│   │   ├── groovy/
│   │   └── resources/
│   └── test/
│       ├── groovy/
│       └── resources/
├── build.gradle or build.gradle.kts
├── settings.gradle or settings.gradle.kts
└── gradle/
    └── wrapper/
```

---
## Using Serena with Groovy

- Serena automatically detects Groovy files (`*.groovy`, `*.gvy`) and will start a Groovy Language Server JAR process per project when needed.
- Optimal results require that your project compiles successfully via Gradle or Maven. If compilation fails, fix build errors in your build tool first.

## Reference

- **Groovy Documentation**: [https://groovy-lang.org/documentation.html](https://groovy-lang.org/documentation.html)
- **Gradle Documentation**: [https://docs.gradle.org](https://docs.gradle.org)
- **Serena Configuration**: [../02-usage/050_configuration.md](../02-usage/050_configuration.md)