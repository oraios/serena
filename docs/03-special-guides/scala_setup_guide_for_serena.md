# Scala Setup Guide for Serena

This guide explains how to prepare a Scala project so that Serena can provide reliable code intelligence via Metals (Scala LSP) and how to run Scala tests manually.

Serena automatically bootstraps the Metals language server using Coursier when needed. Your project, however, must be importable by a build server (BSP) — typically via Bloop or sbt’s built‑in BSP — so that Metals can compile and index your code.

---
## Prerequisites

Install the following on your system and ensure they are available on `PATH`:

- Java Development Kit (JDK). A modern LTS (e.g., 17 or 21) is recommended.
- `sbt`
- Coursier command (`cs`) or the legacy `coursier` launcher
  - Serena uses `cs` if available; if only `coursier` exists, it will attempt to install `cs`. If neither is present, install Coursier first.

---
## Quick Start (Recommended: VS Code + Metals auto‑import)

1. Open your Scala project in VS Code.
2. When prompted by Metals, accept “Import build”. Wait until the import and initial compile/indexing finish.
3. Run the “Connect to build server” command (id: `build.connect`).
4. Once the import completes, start Serena in your project root and use it.

This flow ensures the `.bloop/` and (if applicable) `.metals/` directories are created and your build is known to the build server that Metals uses.

---
## Manual Setup (No VS Code)

Follow these steps if you prefer a manual setup or you are not using VS Code:

These instructions cover the setup for projects that use sbt as the build tool, with Bloop as the BSP server.


1. Add Bloop to `project/plugins.sbt` in your Scala project:
   ```scala
   // project/plugins.sbt
   addSbtPlugin("ch.epfl.scala" % "sbt-bloop" % "<version>")
   ```
   Replace `<version>` with an appropriate current version from the Metals documentation.

2. Export Bloop configuration with sources:
   ```bash
   sbt -Dbloop.export-jar-classifiers=sources bloopInstall
   ```
   This creates a `.bloop/` directory containing your project’s build metadata for the BSP server.

3. Compile from sbt to verify the build:
   ```bash
   sbt compile
   ```

4. Start Serena in your project root. Serena will bootstrap Metals (if not already present) and connect to the build server using the configuration exported above.

---
## Using Serena with Scala

- Serena automatically detects Scala files (`*.scala`, `*.sbt`) and will start a Metals process per project when needed.
- On first run, you may see messages like “Bootstrapping metals…” in the Serena logs — this is expected.
- Optimal results require that your project compiles successfully via the build server (BSP). If compilation fails, fix build errors in `sbt` first.


Notes:
- Ensure you completed the manual or auto‑import steps so that the build is compiled and indexed; otherwise, code navigation and references may be incomplete until the first successful compile.

---
## Running Multiple Metals Instances

Serena can run alongside other Metals instances (e.g., VS Code with Metals extension) on the same project. This is **fully supported** by Metals via H2 AUTO_SERVER mode.

### How It Works

Metals uses an H2 database (`.metals/metals.mv.db`) to cache semantic information. When multiple Metals instances run on the same project:

- **H2 AUTO_SERVER**: The first instance becomes the TCP server; subsequent instances connect as clients
- **Bloop Build Server**: All instances share a single Bloop process (port 8212)
- **Compilation Results**: Shared via Bloop — no duplicate compilation

### Stale Lock Detection

If a Metals process crashes without proper cleanup, it may leave a stale lock file (`.metals/metals.mv.db.lock.db`). This can prevent proper AUTO_SERVER coordination, causing new instances to fall back to in-memory database mode (degraded experience).

Serena automatically detects and handles stale locks based on your configuration:

```yaml
# ~/.serena/serena_config.yml or .serena/project.yml
ls_specific_settings:
  scala:
    on_stale_lock: "auto-clean"      # auto-clean | warn | fail
    log_multi_instance_notice: true  # Log info when another Metals detected
```

#### Stale Lock Modes

| Mode | Behavior |
|------|----------|
| `auto-clean` | **(Default, Recommended)** Automatically removes stale lock files and proceeds normally. |
| `warn` | Logs a warning but proceeds. Metals may use in-memory database (slower). |
| `fail` | Raises an error and refuses to start. Useful for debugging lock issues. |

---
## Reference 
- Metals + sbt: [https://scalameta.org/metals/docs/build-tools/sbt](https://scalameta.org/metals/docs/build-tools/sbt)
