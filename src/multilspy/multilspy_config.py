"""
Configuration parameters for Multilspy.
"""
import fnmatch
from enum import Enum
from typing import List
from dataclasses import dataclass, field


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
    JAVASCRIPT = "javascript"
    GO = "go"
    RUBY = "ruby"
    SWIFT = "swift"
    DART = "dart"
    CPP = "cpp"


    def __str__(self) -> str:
        return self.value

    def get_source_fn_matcher(self) -> FilenameMatcher:
        match self:
            case self.PYTHON:
                return FilenameMatcher("*.py", "*.pyi")
            case self.JAVA:
                return FilenameMatcher("*.java")
            case self.TYPESCRIPT:
                return FilenameMatcher("*.ts", "*.js", "*.jsx", "*.tsx")
            case self.JAVASCRIPT:
                return FilenameMatcher("*.js", "*.jsx")
            case self.CSHARP:
                return FilenameMatcher("*.cs")
            case self.RUST:
                return FilenameMatcher("*.rs")
            case self.GO:
                return FilenameMatcher("*.go")
            case self.RUBY:
                return FilenameMatcher("*.rb")
            case self.SWIFT:
                return FilenameMatcher("*.swift")
            case self.CPP:
                return FilenameMatcher("*.cpp", "*.h", "*.hpp", "*.c", "*.hxx", "*.cc", "*.cxx")
            case self.KOTLIN:
                return FilenameMatcher("*.kt", "*.kts")
            case self.DART:
                return FilenameMatcher("*.dart")
            case _:
                raise ValueError(f"Unhandled language: {self}")


@dataclass
class MultilspyConfig:
    """
    Configuration parameters
    """
    code_language: Language
    trace_lsp_communication: bool = False
    start_independent_lsp_process: bool = True
    ignored_paths: list[str] = field(default_factory=list)
    """Paths, dirs or glob-like patterns. The matching will follow the same logic as for .gitignore entries"""
    gitignore_file_content: str | None = None
    """Optional content of the gitignore file. If passed, will be used in addition to the explicitly passed ignored_paths for deciding which paths to ignore."""

    @classmethod
    def from_dict(cls, env: dict):
        """
        Create a MultilspyConfig instance from a dictionary
        """
        import inspect
        return cls(**{
            k: v for k, v in env.items() 
            if k in inspect.signature(cls).parameters
        })
