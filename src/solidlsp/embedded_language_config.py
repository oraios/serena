"""
Configuration for embedded languages handled by companion servers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EmbeddedLanguageConfig:
    """
    Configuration for an embedded language handled by a companion language server.

    Specifies which LSP operations the companion handles and which files to index.
    """

    language_id: str
    file_patterns: list[str]
    handles_definitions: bool = False
    handles_references: bool = False
    handles_rename: bool = False
    handles_completions: bool = False
    handles_diagnostics: bool = False
    priority: int = 0
