"""
Configuration objects for language servers
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer


class FilenameMatcher:
    def __init__(self, *file_extensions: str, case_sensitive: bool = True) -> None:
        """
        :param file_extensions: file extensions, e.g., `.py, .yml`
        :param case_sensitive: whether the file extensions are case-sensitive.
        """
        self._file_extensions = list(set(file_extensions)) if case_sensitive else list(set(ext.lower() for ext in file_extensions))
        self._case_sensitive = case_sensitive

    def is_relevant_filename(self, fn: str) -> bool:
        if not self._case_sensitive:
            fn = fn.lower()
        for ext in self._file_extensions:
            if fn.endswith(ext):
                return True
        return False

    def string_contains_relevant_filename(self, string: str) -> bool:
        """:return: whether ``string`` contains an occurrence of any registered extension as
        a *complete* extension — i.e. the extension must either end the string or be followed
        by a non-extension-character (anything other than a letter, digit, or underscore).
        """
        if self._case_sensitive:
            string = string.lower()
        for ext in self._file_extensions:
            if re.search(rf"{re.escape(ext)}(?:\W|$)", string):
                return True
        return False


class Language(str, Enum):
    """
    Enumeration of language servers supported by SolidLSP.
    """

    CSHARP = "csharp"
    PYTHON = "python"
    RUST = "rust"
    JAVA = "java"
    KOTLIN = "kotlin"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUBY = "ruby"
    DART = "dart"
    CPP = "cpp"
    CPP_CCLS = "cpp_ccls"
    PHP = "php"
    R = "r"
    PERL = "perl"
    CLOJURE = "clojure"
    ELIXIR = "elixir"
    ELM = "elm"
    TERRAFORM = "terraform"
    SWIFT = "swift"
    BASH = "bash"
    CRYSTAL = "crystal"
    ZIG = "zig"
    LUA = "lua"
    LUAU = "luau"
    """Luau Language Server for Roblox's Luau language (typed Lua 5.1 superset).
    Uses luau-lsp by JohnnyMorganz. Automatically downloads the binary if not found.
    Supports .luau files. Configure via .luaurc in the project root.
    """
    NIX = "nix"
    ERLANG = "erlang"
    OCAML = "ocaml"
    AL = "al"
    FSHARP = "fsharp"
    REGO = "rego"
    SCALA = "scala"
    JULIA = "julia"
    FORTRAN = "fortran"
    HASKELL = "haskell"
    HAXE = "haxe"
    """Haxe language server using vshaxe/haxe-language-server.
    Requires Haxe compiler (3.4.0+) and Node.js.
    Discovered from system PATH or vshaxe VSCode extension, otherwise downloaded from Open VSX.
    """
    LEAN4 = "lean4"
    GROOVY = "groovy"
    VUE = "vue"
    POWERSHELL = "powershell"
    PASCAL = "pascal"
    """Pascal Language Server (pasls) for Free Pascal and Lazarus projects.
    Automatically downloads pasls binary. Requires FPC for full functionality.
    Set PP and FPCDIR environment variables for source navigation.
    """
    MATLAB = "matlab"
    """MATLAB language server using the official MathWorks MATLAB Language Server.
    Requires MATLAB R2021b or later and Node.js.
    Set MATLAB_PATH environment variable or configure matlab_path in ls_specific_settings.
    """
    MSL = "msl"
    """mIRC Scripting Language (mSL) language server.
    Supports .mrc files used in mIRC and AdiIRC IRC clients.
    Uses a custom LSP server based on pygls. Automatically sets up
    a virtual environment with pygls dependencies on first use.
    """
    # Experimental or deprecated Language Servers
    TYPESCRIPT_VTS = "typescript_vts"
    """Use the typescript language server through the natively bundled vscode extension via https://github.com/yioneko/vtsls"""
    PYTHON_JEDI = "python_jedi"
    """Jedi language server for Python (instead of pyright, which is the default)"""
    PYTHON_TY = "python_ty"
    """Ty language server for Python (instead of pyright, which is the default)."""
    CSHARP_OMNISHARP = "csharp_omnisharp"
    """OmniSharp language server for C# (instead of the default csharp-ls by microsoft).
    Currently has problems with finding references, and generally seems less stable and performant.
    """
    RUBY_SOLARGRAPH = "ruby_solargraph"
    """Solargraph language server for Ruby (legacy, experimental).
    Use Language.RUBY (ruby-lsp) for better performance and modern LSP features.
    """
    PHP_PHPACTOR = "php_phpactor"
    """Phpactor language server for PHP (instead of Intelephense, which is the default).
    Requires PHP 8.1+ on the system. Fully open-source (MIT license).
    """
    MARKDOWN = "markdown"
    """Marksman language server for Markdown (experimental).
    Must be explicitly specified as the main language, not auto-detected.
    This is an edge case primarily useful when working on documentation-heavy projects.
    """
    YAML = "yaml"
    """YAML language server (experimental).
    Must be explicitly specified as the main language, not auto-detected.
    """
    JSON = "json"
    """JSON language server using vscode-json-languageserver (experimental).
    Provides document symbol navigation and hover for JSON files.
    Must be explicitly specified as the main language, not auto-detected.
    Requires Node.js and npm.
    """
    TOML = "toml"
    """TOML language server using Taplo.
    Supports TOML validation, formatting, and schema support.
    """
    HLSL = "hlsl"
    """Shader language server using shader-language-server (antaalt/shader-sense).
    Supports .hlsl, .hlsli, .fx, .fxh, .cginc, .compute, .shader, .glsl, .vert, .frag, .geom, .tesc, .tese, .comp, .wgsl files.
    Automatically downloads shader-language-server binary.
    """
    SYSTEMVERILOG = "systemverilog"
    """SystemVerilog language server using verible-verilog-ls.
    Supports .sv, .svh, .v, .vh files.
    Automatically downloads verible binary.
    """
    SOLIDITY = "solidity"
    """Solidity language server using the Nomic Foundation Solidity Language Server
    (@nomicfoundation/solidity-language-server).
    Supports .sol files. Provides go-to-definition, find references, document symbols,
    hover, and diagnostics. Requires Node.js and npm.
    Works best with a foundry.toml or hardhat.config.js in the project root.
    """
    ANSIBLE = "ansible"
    """Ansible language server (experimental) using @ansible/ansible-language-server.
    Supports .yaml and .yml files (same extensions as YAML, hence experimental).
    Must be explicitly specified in project.yml. Requires Node.js and npm.
    Requires ``ansible`` in PATH for full functionality.
    """
    HTML = "html"
    """HTML language server (experimental) using vscode-html-language-server from
    Microsoft's vscode-langservers-extracted npm package. Supports *.html and *.htm files.
    Must be explicitly specified in project.yml. Requires Node.js and npm.
    Note: HTML LSP provides in-file element/id symbols only; cross-file references
    are not meaningful for HTML. Also used as a companion server by Angular LS for
    plain HTML documentSymbol support.
    """
    SCSS = "scss"
    """SCSS / Sass / CSS language server (experimental) using some-sass-language-server
    (https://github.com/wkillerud/some-sass). Handles *.scss, *.sass, and *.css.
    Must be explicitly specified in project.yml. Requires Node.js and npm.
    Provides full @use/@forward workspace navigation across SCSS files; CSS support
    relies on the same vscode-css-languageservice engine and is enabled at startup
    via the somesass.css.* feature toggles (which default to off upstream).
    """
    ANGULAR = "angular"
    """Angular Language Server (experimental) using the official @angular/language-server
    (ngserver). Supports *.ts and *.html files (Angular templates can be external or inline).
    Understands Angular template syntax (*ngIf, [prop], (event), {{ interpolation }},
    @if/@for blocks, etc.) and provides type-aware navigation between templates and
    component classes — which the plain HTML and TypeScript LSPs cannot.
    Requires Node.js, npm, and a valid Angular workspace (angular.json or Nx project.json
    at the repository root). When activated, do not also enable typescript or html in
    project.yml — Angular LS supersedes both for Angular projects.
    Must be explicitly specified in project.yml.
    """

    @classmethod
    def iter_all(cls, include_experimental: bool = False, include_non_programming_languages: bool = True) -> Iterable[Self]:
        for lang in cls:
            if include_experimental or not lang.is_experimental():
                if include_non_programming_languages or lang.is_programming_language():
                    yield lang

    def is_experimental(self) -> bool:
        """
        Check if the language server is experimental or deprecated.

        Note for serena users/developers:
        Experimental languages are not autodetected and must be explicitly specified
        in the project.yml configuration.
        """
        return self in {
            self.ANSIBLE,
            self.TYPESCRIPT_VTS,
            self.PYTHON_JEDI,
            self.PYTHON_TY,
            self.CSHARP_OMNISHARP,
            self.RUBY_SOLARGRAPH,
            self.PHP_PHPACTOR,
            self.MARKDOWN,
            self.YAML,
            self.JSON,
            self.TOML,
            self.GROOVY,
            self.CPP_CCLS,
            self.SOLIDITY,
            self.HTML,
            self.SCSS,
            self.ANGULAR,
        }

    def is_programming_language(self) -> bool:
        """Whether the supported language should be considered a programming language.
        Solidlsp supports languages like markdown or json, this method returns False for them.
        """
        return self not in frozenset((self.MARKDOWN, self.JSON, self.TOML, self.YAML, self.ANSIBLE))

    def __str__(self) -> str:
        return self.value

    def get_priority(self) -> int:
        """
        :return: priority of the language for breaking ties between languages; higher is more important.
        """
        # experimental languages have the lowest priority
        if self.is_experimental():
            return 0
        # We assign lower priority to languages that are supersets of others, such that
        # the "larger" language is only chosen when it matches more strongly
        match self:
            # languages that are supersets of others (Vue is superset of TypeScript/JavaScript)
            case self.VUE:
                return 1
            # regular languages
            case _:
                return 2

    def supports_implementation_request(self) -> bool:
        """
        Return whether the default language server for this language supports ``textDocument/implementation``.
        """
        return self.get_ls_class().supports_implementation_request()

    def get_source_fn_matcher(self) -> FilenameMatcher:
        match self:
            case self.PYTHON | self.PYTHON_JEDI | self.PYTHON_TY:
                return FilenameMatcher(".py", ".pyi")
            case self.JAVA:
                return FilenameMatcher(".java")
            case self.TYPESCRIPT | self.TYPESCRIPT_VTS:
                # see https://github.com/oraios/serena/issues/204
                path_patterns = []
                for prefix in ["c", "m", ""]:
                    for postfix in ["x", ""]:
                        for base_pattern in ["ts", "js"]:
                            path_patterns.append(f".{prefix}{base_pattern}{postfix}")
                return FilenameMatcher(*path_patterns)
            case self.CSHARP | self.CSHARP_OMNISHARP:
                return FilenameMatcher(".cs")
            case self.RUST:
                return FilenameMatcher(".rs")
            case self.GO:
                return FilenameMatcher(".go")
            case self.RUBY:
                return FilenameMatcher(".rb", ".erb")
            case self.RUBY_SOLARGRAPH:
                return FilenameMatcher(".rb")
            case self.CPP:
                # From llvm-project/clang/lib/Driver/Types.cpp types::lookupTypeForExtension:
                return FilenameMatcher(
                    # C
                    ".c",
                    ".h",
                    # C++
                    ".c++",
                    ".cc",
                    ".cp",
                    ".cpp",
                    ".cxx",
                    ".hh",
                    ".hpp",
                    ".hxx",
                    # C++ include files
                    ".inl",
                    ".ipp",
                    ".tpp",
                    ".txx",
                    # Objective-C
                    ".m",
                    ".mm",
                    # C++20 module interface files
                    ".c++m",
                    ".cppm",
                    ".cxxm",
                    ".ixx",
                    # CUDA
                    ".cu",
                    # HIP
                    ".hip",
                    # OpenCL
                    ".cl",
                    ".clcpp",
                    case_sensitive=False,
                )
            case self.CPP_CCLS:
                # From llvm-project/clang/lib/Driver/Types.cpp types::lookupTypeForExtension:
                return FilenameMatcher(
                    # C
                    ".c",
                    ".h",
                    # C++
                    ".c++",
                    ".cc",
                    ".cp",
                    ".cpp",
                    ".cxx",
                    ".hh",
                    ".hpp",
                    ".hxx",
                    # C++ include files
                    ".inl",
                    ".ipp",
                    ".tpp",
                    ".txx",
                    # Objective-C
                    ".m",
                    ".mm",
                    case_sensitive=False,
                )
            case self.KOTLIN:
                return FilenameMatcher(".kt", ".kts")
            case self.DART:
                return FilenameMatcher(".dart")
            case self.PHP | self.PHP_PHPACTOR:
                return FilenameMatcher(".php")
            case self.R:
                return FilenameMatcher(".R", ".r", ".Rmd", ".Rnw")
            case self.PERL:
                return FilenameMatcher(".pl", ".pm", ".t")
            case self.CLOJURE:
                return FilenameMatcher(".clj", ".cljs", ".cljc", ".edn")  # codespell:ignore edn
            case self.ELIXIR:
                return FilenameMatcher(".ex", ".exs")
            case self.ELM:
                return FilenameMatcher(".elm")
            case self.TERRAFORM:
                return FilenameMatcher(".tf", ".tfvars", ".tfstate")
            case self.SWIFT:
                return FilenameMatcher(".swift")
            case self.BASH:
                return FilenameMatcher(".sh", ".bash")
            case self.CRYSTAL:
                return FilenameMatcher(".cr")
            case self.YAML:
                return FilenameMatcher(".yaml", ".yml")
            case self.JSON:
                return FilenameMatcher(".json", ".jsonc")
            case self.TOML:
                return FilenameMatcher(".toml")
            case self.ZIG:
                return FilenameMatcher(".zig", ".zon")
            case self.LUA:
                return FilenameMatcher(".lua")
            case self.LUAU:
                return FilenameMatcher(".luau")
            case self.NIX:
                return FilenameMatcher(".nix")
            case self.ERLANG:
                return FilenameMatcher(".erl", ".hrl", ".escript", ".config", ".app", ".app.src")
            case self.OCAML:
                return FilenameMatcher(".ml", ".mli", ".re", ".rei")
            case self.AL:
                return FilenameMatcher(".al", ".dal")
            case self.FSHARP:
                return FilenameMatcher(".fs", ".fsx", ".fsi")
            case self.REGO:
                return FilenameMatcher(".rego")
            case self.MARKDOWN:
                return FilenameMatcher(".md", ".markdown")
            case self.SCALA:
                return FilenameMatcher(".scala", ".sbt")
            case self.JULIA:
                return FilenameMatcher(".jl")
            case self.FORTRAN:
                return FilenameMatcher(".f90", ".f95", ".f03", ".f08", ".f", ".for", ".fpp", case_sensitive=False)
            case self.HASKELL:
                return FilenameMatcher(".hs", ".lhs")
            case self.HAXE:
                return FilenameMatcher(".hx")
            case self.LEAN4:
                return FilenameMatcher(".lean")
            case self.VUE:
                path_patterns = [".vue"]
                for prefix in ["c", "m", ""]:
                    for postfix in ["x", ""]:
                        for base_pattern in ["ts", "js"]:
                            path_patterns.append(f".{prefix}{base_pattern}{postfix}")
                return FilenameMatcher(*path_patterns)
            case self.POWERSHELL:
                return FilenameMatcher(".ps1", ".psm1", ".psd1")
            case self.PASCAL:
                return FilenameMatcher(".pas", ".pp", ".lpr", ".dpr", ".dpk", ".inc")
            case self.GROOVY:
                return FilenameMatcher(".groovy", ".gvy")
            case self.MATLAB:
                return FilenameMatcher(".m", ".mlx", ".mlapp")
            case self.HLSL:
                return FilenameMatcher(
                    ".hlsl",
                    ".hlsli",
                    ".fx",
                    ".fxh",
                    ".cginc",
                    ".compute",
                    ".shader",
                    ".glsl",
                    ".vert",
                    ".frag",
                    ".geom",
                    ".tesc",
                    ".tese",
                    ".comp",
                    ".wgsl",
                )
            case self.SYSTEMVERILOG:
                return FilenameMatcher(".sv", ".svh", ".v", ".vh")
            case self.SOLIDITY:
                return FilenameMatcher(".sol")
            case self.ANSIBLE:
                return FilenameMatcher(".yaml", ".yml")
            case self.MSL:
                return FilenameMatcher(".mrc")
            case self.HTML:
                return FilenameMatcher(".html", ".htm")
            case self.SCSS:
                # *.css is handled by the same engine (vscode-css-languageservice) that powers
                # Microsoft's CSS LS, so we route plain CSS through Some Sass too. The CSS feature
                # toggles default off upstream and are flipped on at initialization time.
                return FilenameMatcher(".scss", ".sass", ".css")
            case self.ANGULAR:
                # Angular templates can be standalone .html files or inline templates
                # within .ts component files; the dual-server architecture handles both.
                # SCSS / styles are deliberately NOT subsumed — use Language.SCSS for those.
                path_patterns = [".html", ".htm"]
                for prefix in ["c", "m", ""]:
                    for postfix in ["x", ""]:
                        path_patterns.append(f".{prefix}ts{postfix}")
                return FilenameMatcher(*path_patterns)
            case _:
                raise ValueError(f"Unhandled language: {self}")

    def get_ls_class(self) -> type["SolidLanguageServer"]:
        match self:
            case self.PYTHON:
                from solidlsp.language_servers.pyright_server import PyrightServer

                return PyrightServer
            case self.PYTHON_JEDI:
                from solidlsp.language_servers.jedi_server import JediServer

                return JediServer
            case self.PYTHON_TY:
                from solidlsp.language_servers.ty_server import TyLanguageServer

                return TyLanguageServer
            case self.JAVA:
                from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS

                return EclipseJDTLS
            case self.KOTLIN:
                from solidlsp.language_servers.kotlin_language_server import KotlinLanguageServer

                return KotlinLanguageServer
            case self.RUST:
                from solidlsp.language_servers.rust_analyzer import RustAnalyzer

                return RustAnalyzer
            case self.CSHARP:
                from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer

                return CSharpLanguageServer
            case self.CSHARP_OMNISHARP:
                from solidlsp.language_servers.omnisharp import OmniSharp

                return OmniSharp
            case self.TYPESCRIPT:
                from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer

                return TypeScriptLanguageServer
            case self.TYPESCRIPT_VTS:
                from solidlsp.language_servers.vts_language_server import VtsLanguageServer

                return VtsLanguageServer
            case self.VUE:
                from solidlsp.language_servers.vue_language_server import VueLanguageServer

                return VueLanguageServer
            case self.GO:
                from solidlsp.language_servers.gopls import Gopls

                return Gopls
            case self.RUBY:
                from solidlsp.language_servers.ruby_lsp import RubyLsp

                return RubyLsp
            case self.RUBY_SOLARGRAPH:
                from solidlsp.language_servers.solargraph import Solargraph

                return Solargraph
            case self.DART:
                from solidlsp.language_servers.dart_language_server import DartLanguageServer

                return DartLanguageServer
            case self.CPP:
                from solidlsp.language_servers.clangd_language_server import ClangdLanguageServer

                return ClangdLanguageServer
            case self.CPP_CCLS:
                from solidlsp.language_servers.ccls_language_server import CCLS

                return CCLS
            case self.PHP:
                from solidlsp.language_servers.intelephense import Intelephense

                return Intelephense
            case self.PHP_PHPACTOR:
                from solidlsp.language_servers.phpactor import PhpactorServer

                return PhpactorServer
            case self.PERL:
                from solidlsp.language_servers.perl_language_server import PerlLanguageServer

                return PerlLanguageServer
            case self.CLOJURE:
                from solidlsp.language_servers.clojure_lsp import ClojureLSP

                return ClojureLSP
            case self.ELIXIR:
                from solidlsp.language_servers.elixir_tools.elixir_tools import ElixirTools

                return ElixirTools
            case self.ELM:
                from solidlsp.language_servers.elm_language_server import ElmLanguageServer

                return ElmLanguageServer
            case self.TERRAFORM:
                from solidlsp.language_servers.terraform_ls import TerraformLS

                return TerraformLS
            case self.SWIFT:
                from solidlsp.language_servers.sourcekit_lsp import SourceKitLSP

                return SourceKitLSP
            case self.BASH:
                from solidlsp.language_servers.bash_language_server import BashLanguageServer

                return BashLanguageServer
            case self.CRYSTAL:
                from solidlsp.language_servers.crystal_language_server import CrystalLanguageServer

                return CrystalLanguageServer
            case self.YAML:
                from solidlsp.language_servers.yaml_language_server import YamlLanguageServer

                return YamlLanguageServer
            case self.JSON:
                from solidlsp.language_servers.json_language_server import JsonLanguageServer

                return JsonLanguageServer
            case self.TOML:
                from solidlsp.language_servers.taplo_server import TaploServer

                return TaploServer
            case self.ZIG:
                from solidlsp.language_servers.zls import ZigLanguageServer

                return ZigLanguageServer
            case self.NIX:
                from solidlsp.language_servers.nixd_ls import NixLanguageServer  # type: ignore

                return NixLanguageServer
            case self.LUA:
                from solidlsp.language_servers.lua_ls import LuaLanguageServer

                return LuaLanguageServer

            case self.LUAU:
                from solidlsp.language_servers.luau_lsp import LuauLanguageServer

                return LuauLanguageServer

            case self.ERLANG:
                from solidlsp.language_servers.erlang_language_server import ErlangLanguageServer

                return ErlangLanguageServer
            case self.OCAML:
                from solidlsp.language_servers.ocaml_lsp_server import OcamlLanguageServer

                return OcamlLanguageServer
            case self.AL:
                from solidlsp.language_servers.al_language_server import ALLanguageServer

                return ALLanguageServer
            case self.REGO:
                from solidlsp.language_servers.regal_server import RegalLanguageServer

                return RegalLanguageServer
            case self.MARKDOWN:
                from solidlsp.language_servers.marksman import Marksman

                return Marksman
            case self.R:
                from solidlsp.language_servers.r_language_server import RLanguageServer

                return RLanguageServer
            case self.SCALA:
                from solidlsp.language_servers.scala_language_server import ScalaLanguageServer

                return ScalaLanguageServer
            case self.JULIA:
                from solidlsp.language_servers.julia_server import JuliaLanguageServer

                return JuliaLanguageServer
            case self.FORTRAN:
                from solidlsp.language_servers.fortran_language_server import FortranLanguageServer

                return FortranLanguageServer
            case self.HASKELL:
                from solidlsp.language_servers.haskell_language_server import HaskellLanguageServer

                return HaskellLanguageServer
            case self.HAXE:
                from solidlsp.language_servers.haxe_language_server import HaxeLanguageServer

                return HaxeLanguageServer
            case self.LEAN4:
                from solidlsp.language_servers.lean4_language_server import Lean4LanguageServer

                return Lean4LanguageServer
            case self.FSHARP:
                from solidlsp.language_servers.fsharp_language_server import FSharpLanguageServer

                return FSharpLanguageServer
            case self.POWERSHELL:
                from solidlsp.language_servers.powershell_language_server import PowerShellLanguageServer

                return PowerShellLanguageServer
            case self.PASCAL:
                from solidlsp.language_servers.pascal_server import PascalLanguageServer

                return PascalLanguageServer
            case self.GROOVY:
                from solidlsp.language_servers.groovy_language_server import GroovyLanguageServer

                return GroovyLanguageServer
            case self.MATLAB:
                from solidlsp.language_servers.matlab_language_server import MatlabLanguageServer

                return MatlabLanguageServer
            case self.HLSL:
                from solidlsp.language_servers.hlsl_language_server import HlslLanguageServer

                return HlslLanguageServer
            case self.SYSTEMVERILOG:
                from solidlsp.language_servers.systemverilog_server import SystemVerilogLanguageServer

                return SystemVerilogLanguageServer
            case self.SOLIDITY:
                from solidlsp.language_servers.solidity_language_server import SolidityLanguageServer

                return SolidityLanguageServer
            case self.ANSIBLE:
                from solidlsp.language_servers.ansible_language_server import AnsibleLanguageServer

                return AnsibleLanguageServer
            case self.MSL:
                from solidlsp.language_servers.msl_language_server import MslLanguageServer

                return MslLanguageServer
            case self.HTML:
                from solidlsp.language_servers.vscode_html_language_server import VsCodeHtmlLanguageServer

                return VsCodeHtmlLanguageServer
            case self.SCSS:
                from solidlsp.language_servers.some_sass_language_server import SomeSassLanguageServer

                return SomeSassLanguageServer
            case self.ANGULAR:
                from solidlsp.language_servers.angular_language_server import AngularLanguageServer

                return AngularLanguageServer
            case _:
                raise ValueError(f"Unhandled language: {self}")

    @classmethod
    def from_ls_class(cls, ls_class: type["SolidLanguageServer"]) -> Self:
        """
        Get the Language enum value from a SolidLanguageServer class.

        :param ls_class: The SolidLanguageServer class to find the corresponding Language for
        :return: The Language enum value
        :raises ValueError: If the language server class is not supported
        """
        for enum_instance in cls:
            if enum_instance.get_ls_class() == ls_class:
                return enum_instance
        raise ValueError(f"Unhandled language server class: {ls_class}")


@dataclass
class LanguageServerConfig:
    """
    Configuration parameters
    """

    code_language: Language
    trace_lsp_communication: bool = False
    start_independent_lsp_process: bool = True
    ignored_paths: list[str] = field(default_factory=list)
    """Paths, dirs or glob-like patterns. The matching will follow the same logic as for .gitignore entries"""
    encoding: str = "utf-8"
    """File encoding to use when reading source files"""

    @classmethod
    def from_dict(cls, env: dict) -> Self:
        import inspect

        return cls(**{k: v for k, v in env.items() if k in inspect.signature(cls).parameters})
