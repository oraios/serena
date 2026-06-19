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

If clangd starts in a project that has a `.uproject` file but no `compile_commands.json`,
Serena logs a warning that points back to this guide. Pick one of the following routes to
create the database.

### Route 1: VSCode project files (no extra installs)

UnrealBuildTool's VSCode project generator emits per-project compile commands.
Run it from your engine installation (VSCode itself is not required):

    <Engine>\Build\BatchFiles\Build.bat -projectfiles -project="<YourProject>.uproject" -game -VSCode

This produces `.vscode/compileCommands_<YourProject>.json` inside your project.
Copy or symlink it to the project root as `compile_commands.json`.

If you already use VSCode with UE, the file likely exists; the editor's
"Tools > Refresh Visual Studio Code Project" action maintains it.

### Route 2: UnrealBuildTool's clang database mode (requires LLVM installed)

    <Engine>\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe -mode=GenerateClangDatabase -project="<YourProject>.uproject" <YourProject>Editor Win64 Development -OutputDir="<YourProject's directory>"

This emits clang-native commands (cleanest flags for clangd) but requires a Clang
toolchain installed on Windows.

---
## Recommended project configuration

Generated reflection code (`*.gen.cpp`, `*.generated.h`) legitimately references your
functions, so symbol results can include hits inside `Intermediate/`. UE's build
artifacts are therefore excluded from indexing in your project's `.serena/project.yml`:

    ignored_paths:
      - "Intermediate"
      - "Saved"
      - "Binaries"
      - "DerivedDataCache"

When Serena generates the configuration for a project that has a `.uproject` file at its
root, it adds these entries automatically. Add them by hand only when editing an existing
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
