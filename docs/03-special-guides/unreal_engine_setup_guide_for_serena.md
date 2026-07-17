# Unreal Engine Setup Guide

This guide explains how to prepare an Unreal Engine 5 C++ project so that Serena's
clangd-based C/C++ support can provide full code intelligence: symbol search,
cross-file references, and symbol-level editing in your hand-written sources.

UE game code uses a macro-based reflection layer (`UCLASS`, `UFUNCTION`, `UPROPERTY`,
`GENERATED_BODY`) and engine types (`TArray`, `TMap`). clangd handles all of this,
provided it receives the compiler flags for your project via a `compile_commands.json`
at the project root. Unreal's build system (UnrealBuildTool) does not produce this
file by default; this guide shows how to obtain it.

---
## Prerequisites

- An Unreal Engine 5 C++ project that has been **built at least once** (the build
  generates the `*.generated.h` headers that your sources include).
- No additional language server: Serena downloads clangd automatically.
- clangd never compiles your code. The compilation database is only a list of flags.

---
## Getting a compilation database

If clangd starts in a project that has a `.uproject` file but no usable
`compile_commands.json`, Serena fails the language server startup with an error that
inlines the command below, because clangd cannot resolve engine headers or reflection
macros without the database. Pick one of the following routes to create it.

None of these routes change how you build. You still compile with MSVC. A clang toolchain,
where a route uses one, only generates the database that clangd reads.

### Route 1 (recommended): UnrealBuildTool's clang database

    <Engine>\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe -mode=GenerateClangDatabase -project="<YourProject>.uproject" <YourProject>Editor Win64 Development -OutputDir="<YourProject's directory>"

This emits clang-native commands. Each entry carries the system-include paths, so clangd
resolves system and engine headers without guessing.

It needs a clang toolchain. Install one from the Visual Studio Installer:
**Modify > Individual Components > "C++ Clang tools for Windows"**. This is not a separate
LLVM download. UnrealBuildTool auto-detects it at `VC\Tools\Llvm\x64`.

- UnrealBuildTool searches for clang in this order: `C:\Program Files\LLVM`, then the
  `LLVM_PATH` environment variable, then the VS-bundled `VC\Tools\Llvm\x64`, then AutoSDK.
  A standalone LLVM install wins if present. Remove it to fall back to the version-matched VS one.
- UE 5.7 expects clang in roughly the 18.1.8 to 20.1.8 range, and the VS component is
  matched. A newer standalone (e.g. 22.x) still generates the database but prints
  `Clang compiler version ... is not a preferred version`.
- `-OutputDir` is required. Without it the file lands in the engine root.
- Build the editor target once before generating, so the `*.generated.h` headers exist.
  After a build you can add `-NoExecCodeGenActions` to skip redundant codegen.

### Route 2 (no clang toolchain): MSVC database

If you cannot add the clang component, append `-Compiler=VisualStudio2022`:

    <Engine>\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe -mode=GenerateClangDatabase -project="<YourProject>.uproject" <YourProject>Editor Win64 Development -Compiler=VisualStudio2022 -OutputDir="<YourProject's directory>"

This produces an MSVC `cl.exe` database and needs no extra toolchain. The entries omit
system-include paths, which MSVC reads from the `INCLUDE` environment variable rather than
the database, so clangd may not resolve standard headers like `<vector>` and logs
`Failed to compile ... index may be incomplete` per file. Symbol tools still work, since
clangd indexes through those errors. To stop them from truncating symbol trees, add a
`.clangd` at the project root (see Troubleshooting):

    CompileFlags:
      Add: [-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH, -ferror-limit=200]

### Route 3 (situational): VSCode project files

UnrealBuildTool's VSCode generator emits per-project compile commands:

    <Engine>\Build\BatchFiles\Build.bat -projectfiles -project="<YourProject>.uproject" -game -VSCode

On an installed engine (Launcher/Fab) with a project outside the engine tree, this writes
an empty array. UnrealBuildTool treats the project as foreign and emits no commands. Verify
the output is a non-empty JSON array before relying on it:

    <YourProject>\.vscode\compileCommands_Default.json

If it contains entries, copy or symlink it to the project root as `compile_commands.json`.
If it is `[]`, use Route 1 or Route 2. The generator works reliably only for source-built
or in-tree engines, or when refreshed from inside the editor via
**Tools > Refresh Visual Studio Code Project**.

### Notes for Rider users

Building the project in Rider never produces `compile_commands.json`. `-VSCode` is a
project-file generator, not an editor mode, and the `.vscode/` directory it creates is
safe to delete afterwards. Use Route 1.

### When to regenerate

Regenerate only when you add a module or change a `*.Build.cs` (new files or compiler
flags). clangd watches `compile_commands.json` and reloads automatically, so routine edits
need no regeneration. If Serena failed to start because the database was missing or empty,
reconnect or restart the MCP after creating it. Serena reads the database only at startup.

---
## Build artifact directories

Generated reflection code (`*.gen.cpp`, `*.generated.h`) legitimately references your
functions, so symbol results could otherwise include hits inside `Intermediate/`. When a
`.uproject` file is present at the project root, the clangd and ccls language servers skip
UE's build and cache directories (`Binaries`, `DerivedDataCache`, `Intermediate`, `Saved`)
during indexing. This is automatic and needs no configuration.

To exclude further paths, add them to `ignored_paths` in your project's
`.serena/project.yml`.

---
## Known behavior

- **`GENERATED_BODY()` and `__LINE__`:** the macro expands using its line number.
  After editing lines above it, clangd may report stale-macro diagnostics until the
  next build regenerates headers. Symbol operations keep working, since clangd is
  designed to operate on code with errors.
- **First index:** large projects take a few minutes to index once; afterwards
  results are incremental. The index cache is kept under `.serena/.cache` inside
  the project.
- **New `UFUNCTION`/`UCLASS` declarations** need a build before their generated
  headers exist.
- **Symbol searches on large projects:** prefer passing `relative_path` to
  `find_symbol`. An unscoped search visits every translation unit, and UE
  files are expensive to parse because each pulls in large engine headers.
- **clangd index logs (MSVC database):** an `Indexed ... (N symbols)` line is a success.
  A following `Failed to compile ... index may be incomplete` means clangd hit errors
  while parsing that file but indexed it anyway. Raise `-ferror-limit` via `.clangd` if
  symbol trees look truncated (see Troubleshooting).

---
## Troubleshooting

Extra flags are easiest to add via a `.clangd` file at the project root, e.g.:

    CompileFlags:
      Add: [-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH, -ferror-limit=200]

- **`STL1000: Unexpected compiler version` errors:** recent MSVC STL headers
  assert a minimum Clang version that may be newer than Serena's bundled clangd.
  Defining `_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH` (see above) silences the
  check; clangd only parses, so the mismatch is harmless.
- **Truncated symbol trees / symbols missing below a certain line:** clangd
  aborts a file's parse after ~20 errors by default, which discards everything
  declared after that point. Raising the limit with `-ferror-limit=200` keeps
  the symbol tree intact even when diagnostics are noisy (common right after
  edits, before the next UE build regenerates headers).
- **Stale results after changing the compilation database:** clangd's index
  shards in `.serena/.cache` were built with the old flags. Delete that cache
  directory and let the project re-index.

---
## Verifying the setup

After activating the project in Serena, a symbol overview of any `UCLASS` header
should list the class with its `UFUNCTION` methods and `UPROPERTY` fields, and
references to a method should resolve to your `Source/` files only.
