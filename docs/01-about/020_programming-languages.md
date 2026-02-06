# Language Support

Serena provides a set of versatile code querying and editing functionalities
based on symbolic understanding of the code.
Equipped with these capabilities, Serena discovers and edits code just like a seasoned developer
making use of an IDE's capabilities would.
Serena can efficiently find the right context and do the right thing even in very large and
complex projects!

There are two alternative technologies powering these capabilities:

* **Language servers** implementing the language server Protocol (LSP) — the free/open-source alternative.
* **The Serena JetBrains Plugin**, which leverages the powerful code analysis and editing
  capabilities of your JetBrains IDE.

You can choose either of these backends depending on your preferences and requirements.

## Language Servers

Serena incorporates a powerful abstraction layer for the integration of language servers 
that implement the language server protocol (LSP).
It even supports multiple language servers in parallel to support polyglot projects.

The language servers themselves are typically open-source projects (like Serena)
or at least freely available for use.

We currently provide direct, out-of-the-box support for the programming languages listed below.
Some languages require additional installations or setup steps, as noted.

* **AL**
* **Bash**
* **C#**
* **C/C++**  
  Default: clangd. Optional alternate: ccls (experimental, opt-in). 
  For best results, provide a `compile_commands.json` at the repository root.
  See the [C/C++ Setup Guide](../03-special-guides/cpp_setup) for details.
* **Clojure**
* **Dart**
* **Elixir**  
  (requires Elixir installation; Expert language server is downloaded automatically)
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
* **Groovy**  
  (requires local groovy-language-server.jar setup via GROOVY_LS_JAR_PATH or configuration)
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
* **Pascal**
  (Free Pascal/Lazarus; automatically downloads pasls binary; set PP and FPCDIR environment variables for source navigation)
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
* **Vue**    
  (3.x with TypeScript; requires Node.js v18+ and npm; supports .vue Single File Components with monorepo detection)
* **YAML**
* **Zig**  
  (requires installation of ZLS - Zig Language Server)

Support for further languages can easily be added by providing a shallow adapter for a new language server implementation,
see Serena's [memory on that](https://github.com/oraios/serena/blob/main/.serena/memories/adding_new_language_support_guide.md).

## The Serena JetBrains Plugin

As an alternative to language servers, the [Serena JetBrains Plugin](https://plugins.jetbrains.com/plugin/28946-serena/)
leverages the powerful code analysis capabilities of JetBrains IDEs. 
The plugin naturally supports all programming languages and frameworks that are supported by JetBrains IDEs, 
including IntelliJ IDEA, PyCharm, Android Studio, AppCode, WebStorm, PhpStorm, RubyMine, GoLand, AppCode, CLion, and others.

When using the plugin, Serena connects to an instance of your JetBrains IDE via the plugin. For users who already
work in a JetBrains IDE, this means Serena seamlessly integrates with the IDE instance you typically have open anyway,
requiring no additional setup or configuration beyond the plugin itself. This approach offers several key advantages:

* **External library indexing**: Dependencies and libraries are fully indexed and accessible to Serena
* **No additional setup**: No need to download or configure separate language servers
* **Enhanced performance**: Faster tool execution thanks to optimized IDE integration
* **Multi-language excellence**: First-class support for polyglot projects with multiple languages and frameworks

Even if you prefer to work in a different code editor, you can still benefit from the JetBrains plugin by running 
a JetBrains IDE instance (most have free community editions) alongside your preferred editor with your project 
opened and indexed. Serena will connect to the IDE for code analysis while you continue working in your editor 
of choice.

```{raw} html
<p>
<a href="https://plugins.jetbrains.com/plugin/28946-serena/">
<img style="background-color:transparent;" src="../_static/images/jetbrains-marketplace-button.png">
</a>
</p>
```

See the [JetBrains Plugin documentation](../02-usage/025_jetbrains_plugin) for usage details.