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

## Reference 
- Metals + sbt: [https://scalameta.org/metals/docs/build-tools/sbt](https://scalameta.org/metals/docs/build-tools/sbt)