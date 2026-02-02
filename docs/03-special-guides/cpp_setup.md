# C/C++ Setup Guide for Serena

This guide explains how to prepare a C/C++ project so that Serena can provide reliable code intelligence via clangd or ccls language servers.
This is only necessary if you use the language server variant of Serena, for users of the Serena JetBrains plugin no setup is required
and the limitations described below do not apply.

---

## General

Serena supports two C/C++ language servers, clangd (default) and ccls.
Both have their pros and cons and require a properly configured `compile_commands.json` 
for cross-file reference finding, see below for details.

Your project must have a `compile_commands.json` file at the repository root. 
This file is essential for correct parsing and cross-file reference finding.


## compile_commands.json Requirements

For reliable cross-file reference finding with clangd, your `compile_commands.json` must:

1. **Include proper C++ standard flags** (e.g., `-std=c++17`)
2. **Include all necessary include paths** (`-I` flags)

---

### With clangd

Serena automatically downloads and manages clangd. Since clangd does not properly work with relative paths in `compile_commands.json`,
Serena will detect them and transform them into absolute paths automatically (writing a new `compile_commands.json` file), if needed.

#### Customizing the Compilation Database Location

By default, Serena creates the transformed compilation database at `.serena/compile_commands.json`. 
You can customize this location via project settings:

```yaml
# .serena/project.yml
language_servers:
  cpp:
    compile_commands_dir: custom/rel/path (defaults to .serena)
```

### With ccls

ccls requires manual installation but may perform better in some situations.

#### Installation

**Linux:**
```bash
# Ubuntu/Debian (22.04+)
sudo apt-get install ccls

# Fedora/RHEL
sudo dnf install ccls

# Arch Linux
sudo pacman -S ccls
```

**macOS:**
```bash
brew install ccls
```

**Windows:**

```bash
choco install ccls
```

#### Configuration

After installing ccls, configure Serena to use it via project settings:

```yaml
# .serena/project.yml
language_servers:
  cpp:
    ls: cpp_ccls  # Use ccls instead of clangd
```

ccls can handle relative paths in `compile_commands.json`.

---

## Known Limitations

### Files Created After Server Initialization

Both clangd and ccls have a fundamental limitation: **files created AFTER the language server starts are NOT automatically indexed**.

Cross-file references to/from newly created files will NOT work until:
1. The file is added to `compile_commands.json`
2. The language server is restarted

**Workaround:** Regenerate `compile_commands.json` after creating new files and restart Serena.

### Cross-File Reference Finding

Cross-file references only work for files that:
- Are present in `compile_commands.json`
- Use correct configuration (proper compiler and flags)

If cross-file references don't work, check:
1. All files are listed in `compile_commands.json`
2. Compiler is `clang++` (although `g++` may work with ccls)
3. Include paths are correct

---

## Reference

- Clangd official documentation: https://clangd.llvm.org/
- Clangd project setup: https://clangd.llvm.org/installation#project-setup
- CCLS repository: https://github.com/MaskRay/ccls
