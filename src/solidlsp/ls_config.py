"""
Configuration objects for language servers
"""

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Self


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
    Possible languages with Multilspy.
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
    CLOJURE = "clojure"
    ELIXIR = "elixir"
    TERRAFORM = "terraform"
    SWIFT = "swift"
    BASH = "bash"
    ZIG = "zig"
    LUA = "lua"
    NIX = "nix"
    ERLANG = "erlang"
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

    @classmethod
    def iter_all(cls, include_experimental: bool = False) -> Iterable[Self]:
        for lang in cls:
            if include_experimental or not lang.is_experimental():
                yield lang

    def is_experimental(self) -> bool:
        """
        Check if the language server is experimental or deprecated.
        """
        return self in {self.TYPESCRIPT_VTS, self.PYTHON_JEDI, self.CSHARP_OMNISHARP, self.RUBY_SOLARGRAPH}

    def __str__(self) -> str:
        return self.value

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
            case self.CLOJURE:
                return FilenameMatcher("*.clj", "*.cljs", "*.cljc", "*.edn")  # codespell:ignore edn
            case self.ELIXIR:
                return FilenameMatcher("*.ex", "*.exs")
            case self.TERRAFORM:
                return FilenameMatcher("*.tf", "*.tfvars", "*.tfstate")
            case self.SWIFT:
                return FilenameMatcher("*.swift")
            case self.BASH:
                return FilenameMatcher("*.sh", "*.bash")
            case self.ZIG:
                return FilenameMatcher("*.zig", "*.zon")
            case self.LUA:
                return FilenameMatcher("*.lua")
            case self.NIX:
                return FilenameMatcher("*.nix")
            case self.ERLANG:
                return FilenameMatcher("*.erl", "*.hrl", "*.escript", "*.config", "*.app", "*.app.src")
            case _:
                raise ValueError(f"Unhandled language: {self}")


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

    @classmethod
    def from_dict(cls, env: dict):
        """
        Create a MultilspyConfig instance from a dictionary
        """
        import inspect

        return cls(**{k: v for k, v in env.items() if k in inspect.signature(cls).parameters})
