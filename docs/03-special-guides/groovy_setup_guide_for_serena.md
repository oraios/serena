# Groovy Setup Guide for Serena

This guide explains how to prepare a Groovy project so that Serena can provide reliable code intelligence via Groovy Language Server and how to configure the server properly.

Serena provides flexible Java runtime management for Groovy Language Server.  
You can either use your system Java installation or let Serena download a bundled Java distribution.  
You need to provide Groovy Language Server JAR file and optionally configure JAR options for optimal performance.

---
## Prerequisites

- Groovy Language Server JAR file
    - Can be any open-source Groovy language server or your custom implementation
    - The JAR must be compatible with standard LSP protocol

---
## Configuration

Configure Groovy Language Server by adding settings to your `~/.serena/serena_config.yml`:

### Basic Configuration

```yaml
ls_specific_settings:
  groovy:
    ls_jar_path: '/path/to/groovy-language-server.jar'
    ls_jar_options: '-Xmx2G -Xms512m'
```

### Custom Java Paths

If you have specific Java installations:

```yaml
ls_specific_settings:
  groovy:
    ls_jar_path: '/path/to/groovy-language-server.jar'
    ls_java_home_path: '/usr/lib/jvm/java-21-openjdk'  # Custom JAVA_HOME directory
    ls_jar_options: '-Xmx2G -Xms512m'                  # Optional JVM options
```

### Configuration Options

- `ls_jar_path`: Absolute path to your Groovy Language Server JAR file (required)
- `ls_java_home_path`: Custom JAVA_HOME directory for Java installation (optional)
    - When specified, Serena will use this Java installation instead of downloading bundled Java
    - Java executable path is automatically determined based on platform:
        - Windows: `{ls_java_home_path}/bin/java.exe`
        - Linux/macOS: `{ls_java_home_path}/bin/java`
    - Validates that Java executable exists at the expected location
- `ls_jar_options`: JVM options for language server (optional)
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