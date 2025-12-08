# Language Support

Serena's semantic code analysis capabilities build on **language servers** using the widely implemented
language server protocol (LSP). The LSP provides a set of versatile code querying
and editing functionalities based on symbolic understanding of the code.
Equipped with these capabilities, Serena discovers and edits code just like a seasoned developer
making use of an IDE's capabilities would.
Serena can efficiently find the right context and do the right thing even in very large and
complex projects! So not only is it free and open-source, it frequently achieves better results
than existing solutions that charge a premium.

Language servers provide support for a wide range of programming languages.
With Serena, we provide direct, out-of-the-box support for:

* **AL**
* **Bash**
* **C#**
* **C/C++**  
  (you may experience issues with finding references, we are working on it)
* **Clojure**
* **Dart**
* **Elixir**  
  (requires installation of NextLS and Elixir; Windows not supported)
* **Elm**  
  (requires Elm compiler)
* **Erlang**  
  (requires installation of beam and [erlang_ls](https://github.com/erlang-ls/erlang_ls); experimental, might be slow or hang)
* **F#**  
  (requires .NET SDK 8.0+; uses FsAutoComplete/Ionide, which is auto-installed; for Homebrew .NET on macOS, set DOTNET_ROOT in your environment)
* **Fortran**   
  (requires installation of fortls: `pip install fortls`)
* **Go**  
  (requires installation of `gopls`)
* **Haskell**  
  (automatically locates HLS via ghcup, stack, or system PATH; supports Stack and Cabal projects)
* **Java**  
* **JavaScript**
* **Julia**
* **Kotlin**  
  (uses the pre-alpha [official kotlin LS](https://github.com/Kotlin/kotlin-lsp), some issues may appear)
* **Lua**
* **Markdown**  
  (must be explicitly specified via `--language markdown` when generating project config, primarily useful for documentation-heavy projects)
* **Nix**  
  (requires nixd installation)
* **Perl**  
  (requires installation of Perl::LanguageServer)
* **PHP**  
  (uses Intelephense LSP; set `INTELEPHENSE_LICENSE_KEY` environment variable for premium features)
* **Python**
* **R**  
  (requires installation of the `languageserver` R package)
* **Ruby**  
  (by default, uses [ruby-lsp](https://github.com/Shopify/ruby-lsp), specify ruby_solargraph as your language to use the previous solargraph based implementation)
* **Rust**  
  (requires [rustup](https://rustup.rs/) - uses rust-analyzer from your toolchain)
* **Scala**  
  (requires some [manual setup](../03-special-guides/scala_setup_guide_for_serena); uses Metals LSP)
* **Swift**
* **TypeScript**
* **Vue** (3.x with TypeScript; requires Node.js v18+ and npm; supports .vue Single File Components with monorepo detection)
* **Zig**  
  (requires installation of ZLS - Zig Language Server)

Support for further languages can easily be added by providing a shallow adapter for a new language server implementation,
see Serena's [memory on that](https://github.com/oraios/serena/blob/main/.serena/memories/adding_new_language_support_guide.md).
