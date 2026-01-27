"""
Query expansion for improved recall in semantic search.

Expands queries with synonyms and related terms to improve retrieval coverage.
"""

import logging

log = logging.getLogger(__name__)


class QueryExpander:
    """
    Expands queries with synonyms and related terms.

    Uses static dictionary approach (no ML) for predictable, fast expansion.
    Conservative to avoid false positives and noise.
    """

    # Domain-specific expansions (coding terminology)
    EXPANSIONS = {
        # Authentication/Authorization
        "auth": ["authentication", "authorize", "login", "credentials"],
        "login": ["signin", "authentication", "auth"],
        "logout": ["signout", "session end"],
        # Database
        "db": ["database", "datastore", "repository", "storage"],
        "sql": ["database", "query", "select"],
        "orm": ["object relational mapping", "database model"],
        # API/Network
        "api": ["endpoint", "route", "handler", "rest"],
        "http": ["request", "response", "web"],
        "rest": ["api", "endpoint", "web service"],
        # Configuration
        "config": ["configuration", "settings", "options", "preferences"],
        "env": ["environment", "configuration", "settings"],
        # Error Handling
        "error": ["exception", "failure", "bug"],
        "exception": ["error", "throw", "catch"],
        # Testing
        "test": ["unittest", "spec", "verify"],
        "mock": ["stub", "fake", "test double"],
        # Common Abbreviations
        "mgr": ["manager"],
        "svc": ["service"],
        "util": ["utility", "helper"],
        "ctx": ["context"],
        "impl": ["implementation"],
    }

    def __init__(self, max_expansions: int = 3):
        """
        Initialize query expander.

        :param max_expansions: Maximum synonyms to add per term (default 3)
        """
        self.max_expansions = max_expansions

    def expand(self, query: str, expand_enabled: bool = True) -> str:
        """
        Expand query with synonyms.

        :param query: Original query string
        :param expand_enabled: Whether to enable expansion (default True)
        :return: Expanded query with synonyms appended
        """
        if not expand_enabled:
            return query

        tokens = query.lower().split()
        expanded_tokens = list(tokens)  # Start with original

        # Add synonyms for known terms
        for token in tokens:
            if token in self.EXPANSIONS:
                synonyms = self.EXPANSIONS[token][: self.max_expansions]
                expanded_tokens.extend(synonyms)
                log.debug(f"Expanded '{token}' → {synonyms}")

        # Remove duplicates while preserving order
        expanded_query = " ".join(dict.fromkeys(expanded_tokens))

        if expanded_query != query:
            log.info(f"Query expansion: '{query}' → '{expanded_query}'")

        return expanded_query

    def add_expansion(self, term: str, expansions: list[str]) -> None:
        """
        Add custom expansion rule (per-project customization).

        :param term: Term to expand
        :param expansions: List of synonyms/expansions
        """
        self.EXPANSIONS[term] = expansions
