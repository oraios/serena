"""
Configuration parameters for Multilspy.
"""
import fnmatch
from enum import Enum
from dataclasses import dataclass


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
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"
    RUBY = "ruby"
    SWIFT = "swift"

    def __str__(self) -> str:
        return self.value

    def get_source_fn_matcher(self) -> FilenameMatcher:
        match self:
            case self.PYTHON:
                return FilenameMatcher("*.py")
            case self.JAVA:
                return FilenameMatcher("*.java")
            case self.TYPESCRIPT:
                return FilenameMatcher("*.ts", "*.js")
            case self.JAVASCRIPT:
                return FilenameMatcher("*.js")
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
            case _:
                raise ValueError


@dataclass
class MultilspyConfig:
    """
    Configuration parameters
    """
    code_language: Language
    trace_lsp_communication: bool = False

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