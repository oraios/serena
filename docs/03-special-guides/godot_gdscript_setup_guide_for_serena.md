# GDScript (Godot Engine) Setup Guide for Serena

This guide explains how to prepare a Godot project so that Serena can provide code intelligence for GDScript (`.gd`) files via Godot's built-in Language Server Protocol (LSP) support.

Unlike most language servers, Serena does **not** launch a separate LSP process for GDScript. Instead, Serena connects over TCP to the LSP server that the Godot editor itself runs while it is open. This means the Godot editor must already be running with your project loaded before you start Serena.

---
## Prerequisites

- Godot Engine 3.x or 4.x installed and available on your system.
- A Godot project with a `project.godot` file at the project root.

No additional language server needs to be installed — Godot ships with a built-in LSP server that is enabled by default.

---
## How It Works

When a Godot project is open in the editor, the editor listens for LSP connections on **TCP port 6008** (the same default for both Godot 3 and Godot 4). Serena connects to this port and communicates using standard LSP Content-Length framing.

Serena automatically detects which major version of Godot your project targets by reading the `config_version` field from `project.godot`:

- `config_version` = 5 → Godot 4
- `config_version` = 4 → Godot 3

If `config_version` is not recognized (e.g. from a future Godot release), Serena logs a warning and still connects — both Godot 3 and Godot 4 use the same port.

No additional configuration is needed for version detection.

---
## Setup Steps

1. Open your Godot project in the Godot editor and allow it to finish loading.

2. Verify that the built-in LSP is enabled (it is on by default):
   - Go to **Editor → Editor Settings → Network → Language Server**
   - Confirm **"Use Language Server"** is checked.
   - Confirm the port is **6008** (the default).

3. Add `gdscript` to the `languages` list in your project's Serena configuration:
   ```yaml
   # .serena/project.yml
   languages:
     - gdscript
   ```

4. Start Serena in your project root. Serena will connect to the already-running Godot editor automatically.

---
## Using Serena with GDScript

- Serena recognizes `.gd` and `.gdscript` files. The language identifier used in LSP communication is `gdscript`.
- The Godot editor must remain open for the entire Serena session. If the editor is closed, Serena will lose its connection and will need to be restarted once the editor is open again.
- On first use, you may see a brief delay while Serena establishes the TCP connection and the editor indexes your project files — this is expected.

---
## Performance Note

Godot's built-in LSP does not implement the `workspace/symbol` request (global symbol search across the whole project). As a result, when Serena performs a workspace-wide symbol search — for example, calling `find_symbol` without a `relative_path` — it must fall back to sending a `textDocument/documentSymbol` request for **every `.gd` file** in the project individually.

For large projects, this initial full-project scan can take **30–60 seconds or more**.

To mitigate this:

- **Pass `relative_path` whenever possible.** Narrowing a search to a specific file or subdirectory avoids scanning the entire workspace.
- **Let the first full scan complete.** Serena caches the results to disk after the initial scan. Subsequent Serena sessions will use the on-disk cache and start instantly.

---
## Known Limitations

| Limitation | Detail |
|---|---|
| No `workspace/symbol` support | Godot's LSP does not implement this request. All symbol lookups fall back to per-file `documentSymbol` requests, making the first full-project scan slow. |
| Editor must stay open | Serena requires the Godot editor to be running throughout the session. Closing the editor breaks the TCP connection; restart Serena after reopening the editor. |
| Slower workspace operations | `find_symbol` and `find_references` across the whole workspace are slower than for languages whose LSP servers support native workspace-wide queries. |

---
## Advanced Configuration

You can customize Serena's GDScript connection via `ls_specific_settings` in your `serena_config.yml` or `project.yml`:

```yaml
ls_specific_settings:
  gdscript:
    port: 6008         # TCP port the Godot editor listens on (default: 6008)
    request_timeout: 30.0  # seconds to wait for an LSP response (default: 30.0)
```

These override the defaults only if explicitly set.

---
## Reference

- Godot LSP documentation: [https://docs.godotengine.org/en/stable/tutorials/editor/external_editor.html](https://docs.godotengine.org/en/stable/tutorials/editor/external_editor.html)
- GDScript language reference: [https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/)
