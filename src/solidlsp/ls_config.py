"""
Configuration objects for language servers
"""

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from solidlsp import SolidLanguageServer


class FilenameMatcher:
    def __init__(self, *patterns: str) -> None:
        """
        :param patterns: fnmatch-compatible patterns
        """
        self.patterns = patterns

    def is_relevant_filename(self, fn: str) -> bool:
        for pattern in self.patterns:
            if fnmatch.fnmatch(fn, pattern):
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
    PHP = "php"
    R = "r"
    PERL = "perl"
    CLOJURE = "clojure"
    ELIXIR = "elixir"
    ELM = "elm"
    TERRAFORM = "terraform"
    SWIFT = "swift"
    BASH = "bash"
    ZIG = "zig"
    LUA = "lua"
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
    VUE = "vue"
    POWERSHELL = "powershell"
    # Experimental or deprecated Language Servers
    TYPESCRIPT_VTS = "typescript_vts"
    """Use the typescript language server through the natively bundled vscode extension via https://github.com/yioneko/vtsls"""
    PYTHON_JEDI = "python_jedi"
    """Jedi language server for Python (instead of pyright, which is the default)"""
    CSHARP_OMNISHARP = "csharp_omnisharp"
    """OmniSharp language server for C# (instead of the default csharp-ls by microsoft).
    Currently has problems with finding references, and generally seems less stable and performant.
    """
    RUBY_SOLARGRAPH = "ruby_solargraph"
    """Solargraph language server for Ruby (legacy, experimental).
    Use Language.RUBY (ruby-lsp) for better performance and modern LSP features.
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
    TOML = "toml"
    """TOML language server using Taplo.
    Supports TOML validation, formatting, and schema support.
    """

    @classmethod
    def iter_all(cls, include_experimental: bool = False) -> Iterable[Self]:
        for lang in cls:
            if include_experimental or not lang.is_experimental():
                yield lang

    def is_experimental(self) -> bool:
        """
        Check if the language server is experimental or deprecated.

        Note for serena users/developers:
        Experimental languages are not autodetected and must be explicitly specified
        in the project.yml configuration.
        """
        return self in {
            self.TYPESCRIPT_VTS,
            self.PYTHON_JEDI,
            self.CSHARP_OMNISHARP,
            self.RUBY_SOLARGRAPH,
            self.MARKDOWN,
            self.YAML,
            self.TOML,
        }

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

    def get_source_fn_matcher(self) -> FilenameMatcher:
        match self:
            case self.PYTHON | self.PYTHON_JEDI:
                return FilenameMatcher("*.py", "*.pyi")
            case self.JAVA:
                return FilenameMatcher("*.java")
            case self.TYPESCRIPT | self.TYPESCRIPT_VTS:
                # see https://github.com/oraios/serena/issues/204
                path_patterns = []
                for prefix in ["c", "m", ""]:
                    for postfix in ["x", ""]:
                        for base_pattern in ["ts", "js"]:
                            path_patterns.append(f"*.{prefix}{base_pattern}{postfix}")
                return FilenameMatcher(*path_patterns)
            case self.CSHARP | self.CSHARP_OMNISHARP:
                return FilenameMatcher("*.cs")
            case self.RUST:
                return FilenameMatcher("*.rs")
            case self.GO:
                return FilenameMatcher("*.go")
            case self.RUBY:
                return FilenameMatcher("*.rb", "*.erb")
            case self.RUBY_SOLARGRAPH:
                return FilenameMatcher("*.rb")
            case self.CPP:
                return FilenameMatcher("*.cpp", "*.h", "*.hpp", "*.c", "*.hxx", "*.cc", "*.cxx")
            case self.KOTLIN:
                return FilenameMatcher("*.kt", "*.kts")
            case self.DART:
                return FilenameMatcher("*.dart")
            case self.PHP:
                return FilenameMatcher("*.php")
            case self.R:
                return FilenameMatcher("*.R", "*.r", "*.Rmd", "*.Rnw")
            case self.PERL:
                return FilenameMatcher("*.pl", "*.pm", "*.t")
            case self.CLOJURE:
                return FilenameMatcher("*.clj", "*.cljs", "*.cljc", "*.edn")  # codespell:ignore edn
            case self.ELIXIR:
                return FilenameMatcher("*.ex", "*.exs")
            case self.ELM:
                return FilenameMatcher("*.elm")
            case self.TERRAFORM:
                return FilenameMatcher("*.tf", "*.tfvars", "*.tfstate")
            case self.SWIFT:
                return FilenameMatcher("*.swift")
            case self.BASH:
                return FilenameMatcher("*.sh", "*.bash")
            case self.YAML:
                return FilenameMatcher("*.yaml", "*.yml")
            case self.TOML:
                return FilenameMatcher("*.toml")
            case self.ZIG:
                return FilenameMatcher("*.zig", "*.zon")
            case self.LUA:
                return FilenameMatcher("*.lua")
            case self.NIX:
                return FilenameMatcher("*.nix")
            case self.ERLANG:
                return FilenameMatcher("*.erl", "*.hrl", "*.escript", "*.config", "*.app", "*.app.src")
            case self.OCAML:
                return FilenameMatcher("*.ml", "*.mli", "*.re", "*.rei")
            case self.AL:
                return FilenameMatcher("*.al", "*.dal")
            case self.FSHARP:
                return FilenameMatcher("*.fs", "*.fsx", "*.fsi")
            case self.REGO:
                return FilenameMatcher("*.rego")
            case self.MARKDOWN:
                return FilenameMatcher("*.md", "*.markdown")
            case self.SCALA:
                return FilenameMatcher("*.scala", "*.sbt")
            case self.JULIA:
                return FilenameMatcher("*.jl")
            case self.FORTRAN:
                return FilenameMatcher(
                    "*.f90", "*.F90", "*.f95", "*.F95", "*.f03", "*.F03", "*.f08", "*.F08", "*.f", "*.F", "*.for", "*.FOR", "*.fpp", "*.FPP"
                )
            case self.HASKELL:
                return FilenameMatcher("*.hs", "*.lhs")
            case self.VUE:
                path_patterns = ["*.vue"]
                for prefix in ["c", "m", ""]:
                    for postfix in ["x", ""]:
                        for base_pattern in ["ts", "js"]:
                            path_patterns.append(f"*.{prefix}{base_pattern}{postfix}")
                return FilenameMatcher(*path_patterns)
            case self.POWERSHELL:
                return FilenameMatcher("*.ps1", "*.psm1", "*.psd1")
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
            case self.PHP:
                from solidlsp.language_servers.intelephense import Intelephense

                return Intelephense
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
            case self.YAML:
                from solidlsp.language_servers.yaml_language_server import YamlLanguageServer

                return YamlLanguageServer
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
            case self.FSHARP:
                from solidlsp.language_servers.fsharp_language_server import FSharpLanguageServer

                return FSharpLanguageServer
            case self.POWERSHELL:
                from solidlsp.language_servers.powershell_language_server import PowerShellLanguageServer

                return PowerShellLanguageServer
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
