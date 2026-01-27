"""
Language Server Capability Detection for Call Hierarchy.

This module provides capability detection and fallback strategies for call hierarchy
support across 19+ languages. Some language servers have robust call hierarchy support,
while others may have limited or no support.

@since 3.16.0 (LSP Call Hierarchy protocol)
"""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from solidlsp.ls_config import Language


class CallHierarchySupport(str, Enum):
    """
    Level of call hierarchy support for a language server.

    FULL: Complete call hierarchy support (prepare, incoming, outgoing)
    PARTIAL: Limited support (may work for some scenarios)
    FALLBACK: No call hierarchy, fall back to find_referencing_symbols
    UNKNOWN: Support status unknown, attempt and fall back on failure
    """

    FULL = "full"
    PARTIAL = "partial"
    FALLBACK = "fallback"
    UNKNOWN = "unknown"


class CapabilityMatrix:
    """
    Capability matrix for call hierarchy support across all supported languages.

    This class provides:
    - Language-specific capability detection
    - Fallback strategy recommendations
    - Performance characteristics (e.g., cross-file support)

    Based on LSP specification 3.16.0+ and empirical testing.
    """

    # Language servers with FULL call hierarchy support (tested and verified)
    _FULL_SUPPORT = {
        "PYTHON",  # pyright: excellent call hierarchy
        "GO",  # gopls: excellent call hierarchy
        "TYPESCRIPT",  # tsserver: excellent call hierarchy
        "JAVA",  # eclipse.jdt.ls: excellent call hierarchy
        "RUST",  # rust-analyzer: excellent call hierarchy
        "CSHARP",  # csharp-ls: good call hierarchy
        "KOTLIN",  # kotlin-language-server: good call hierarchy
        "CPP",  # clangd: good call hierarchy
        "SWIFT",  # sourcekit-lsp: good call hierarchy
        "VUE",  # vue-language-server: uses TypeScript for <script>
        "SCALA",  # metals: good call hierarchy
    }

    # Language servers with PARTIAL call hierarchy support
    _PARTIAL_SUPPORT = {
        "PHP",  # intelephense: basic call hierarchy
        "RUBY",  # ruby-lsp: basic call hierarchy
        "ELIXIR",  # elixir-ls: limited call hierarchy
        "DART",  # dart analysis server: basic call hierarchy
    }

    # Language servers with NO call hierarchy support (use fallback)
    _FALLBACK_ONLY = {
        "PERL",
        "CLOJURE",
        "ELM",
        "TERRAFORM",
        "BASH",
        "R",
        "MARKDOWN",
        "YAML",
        "TOML",
        "ZIG",
        "LUA",
        "NIX",
        "ERLANG",
        "AL",
        "FSHARP",
        "REGO",
        "JULIA",
        "FORTRAN",
        "HASKELL",
        "GROOVY",
        "POWERSHELL",
        "PASCAL",
        "MATLAB",
    }

    # Experimental/deprecated language servers
    _EXPERIMENTAL = {
        "PYTHON_JEDI",
        "TYPESCRIPT_VTS",
        "CSHARP_OMNISHARP",
        "RUBY_SOLARGRAPH",
    }

    @classmethod
    def get_support_level(cls, language: "Language") -> CallHierarchySupport:
        """
        Get the call hierarchy support level for a language.

        Args:
            language: Language enum instance

        Returns:
            CallHierarchySupport level (FULL, PARTIAL, FALLBACK, UNKNOWN)

        """
        lang_name = language.name

        if lang_name in cls._FULL_SUPPORT:
            return CallHierarchySupport.FULL
        elif lang_name in cls._PARTIAL_SUPPORT:
            return CallHierarchySupport.PARTIAL
        elif lang_name in cls._FALLBACK_ONLY:
            return CallHierarchySupport.FALLBACK
        elif lang_name in cls._EXPERIMENTAL:
            # Experimental languages: try and fall back on failure
            return CallHierarchySupport.UNKNOWN
        else:
            # Unknown language: attempt and fall back
            return CallHierarchySupport.UNKNOWN

    @classmethod
    def has_call_hierarchy(cls, language: "Language") -> bool:
        """
        Check if a language has any level of call hierarchy support.

        Args:
            language: Language enum instance

        Returns:
            True if language has FULL or PARTIAL support, False otherwise

        """
        support = cls.get_support_level(language)
        return support in {CallHierarchySupport.FULL, CallHierarchySupport.PARTIAL}

    @classmethod
    def should_fallback_to_references(cls, language: "Language") -> bool:
        """
        Check if we should immediately fall back to find_referencing_symbols.

        Args:
            language: Language enum instance

        Returns:
            True if we should skip call hierarchy and use references

        """
        support = cls.get_support_level(language)
        return support == CallHierarchySupport.FALLBACK

    @classmethod
    def get_all_supported_languages(cls) -> set[str]:
        """
        Get all languages with FULL or PARTIAL call hierarchy support.

        Returns:
            Set of language names with call hierarchy support

        """
        return cls._FULL_SUPPORT | cls._PARTIAL_SUPPORT

    @classmethod
    def get_fallback_strategy(cls, language: "Language") -> str:
        """
        Get the recommended fallback strategy for a language.

        Args:
            language: Language enum instance

        Returns:
            Human-readable fallback strategy description

        """
        support = cls.get_support_level(language)

        if support == CallHierarchySupport.FULL:
            return "No fallback needed - full call hierarchy support"
        elif support == CallHierarchySupport.PARTIAL:
            return "Attempt call hierarchy, fall back to references on failure"
        elif support == CallHierarchySupport.FALLBACK:
            return "Use find_referencing_symbols (call hierarchy not supported)"
        else:  # UNKNOWN
            return "Attempt call hierarchy, gracefully fall back to references on error"
