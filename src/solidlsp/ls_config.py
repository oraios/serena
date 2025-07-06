"""
Configuration objects for language servers
"""

import fnmatch
from dataclasses import dataclass, field
from enum import Enum


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

    def __str__(self) -> str:
        return self.value

    def get_source_fn_matcher(self) -> FilenameMatcher:
        match self:
            case self.PYTHON:
                return FilenameMatcher("*.py", "*.pyi")
            case self.JAVA:
                return FilenameMatcher("*.java")
            case self.TYPESCRIPT:
                # see https://github.com/oraios/serena/issues/204
                path_patterns = []
                for prefix in ["c", "m", ""]:
                    for postfix in ["x", ""]:
                        for base_pattern in ["ts", "js"]:
                            path_patterns.append(f"*.{prefix}{base_pattern}{postfix}")
                return FilenameMatcher(*path_patterns)
            case self.CSHARP:
                return FilenameMatcher("*.cs")
            case self.RUST:
                return FilenameMatcher("*.rs")
            case self.GO:
                return FilenameMatcher("*.go")
            case self.RUBY:
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
