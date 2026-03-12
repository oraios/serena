# OCaml Setup Guide for Serena

This guide explains how to set up an OCaml project so that Serena can provide code intelligence via ocaml-lsp-server (ocamllsp).

Unlike some other languages, Serena does not download the OCaml language server automatically. You must install it yourself via opam, as OCaml tooling is compiled from source against your specific environment.

---
## Prerequisites

Install the following on your system and ensure they are available on `PATH`:

- **opam** (OCaml package manager)
  - macOS: `brew install opam`
  - Ubuntu/Debian: `sudo apt install opam`
  - Fedora: `sudo dnf install opam`
  - Other: https://opam.ocaml.org/doc/Install.html
- **OCaml compiler** (via opam)
  - OCaml < 5.1 or >= 5.1.1 (OCaml 5.1.0 is **not supported** by ocaml-lsp-server)
  - Recommended: OCaml 4.14.x (stable) or 5.2+ (for cross-file references)
- **ocaml-lsp-server** (via opam)
- **dune** (build system, via opam)

---
## Installation

1. Initialize opam if you haven't already:
   ```bash
   opam init
   eval $(opam env)
   ```

2. Create an opam switch with a compatible OCaml version:
   ```bash
   # For cross-file reference support (recommended)
   opam switch create serena-ocaml ocaml-base-compiler.5.2.1
   eval $(opam env)

   # Or for stable OCaml 4.14.x
   opam switch create serena-ocaml ocaml-base-compiler.4.14.2
   eval $(opam env)
   ```

3. Install the language server and build tools:
   ```bash
   opam install ocaml-lsp-server dune
   ```

4. Verify the installation:
   ```bash
   opam exec -- ocamllsp --version
   opam exec -- ocaml -version
   ```

---
## Cross-File References

Cross-file reference support (finding all usages of a symbol across your project) requires:

- OCaml >= 5.2
- ocaml-lsp-server >= 1.23.0
- dune >= 3.16.0

When these requirements are met, Serena automatically builds the cross-file index during startup via `dune build @ocaml-index`. Without these versions, references are limited to the current file.

---
## Using Serena with OCaml

- Serena automatically detects OCaml files (`*.ml`, `*.mli`) and Reason files (`*.re`, `*.rei`).
- The language server is started via `opam exec -- ocamllsp`, so your opam environment must be configured.
- Ensure your project builds successfully with `dune build` before using Serena for best results.

---
## Troubleshooting

| Problem | Solution |
|---------|----------|
| "opam not found" | Install opam and add it to PATH |
| "OCaml 5.1.0 is incompatible" | Create a new switch: `opam switch create <name> ocaml-base-compiler.5.2.1` |
| "ocaml-lsp-server not found" | `opam install ocaml-lsp-server` |
| Cross-file refs not working | Ensure OCaml >= 5.2 and ocaml-lsp-server >= 1.23.0; run `dune build` first |
| Stale index | Rebuild with `dune build @ocaml-index` |

---
## Reference

- opam: https://opam.ocaml.org
- ocaml-lsp-server: https://github.com/ocaml/ocaml-lsp
- Project-wide occurrences: https://discuss.ocaml.org/t/ann-project-wide-occurrences-in-merlin-and-lsp/14847
