"""
Query routing for intelligent search selection.

This module determines whether a query should use LSP (structural), vector (semantic),
or hybrid search based on query characteristics.
"""

import logging
import re
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


class SearchMode(Enum):
    """Search mode selection."""

    LSP = "lsp"  # Structural/exact search via LSP
    VECTOR = "vector"  # Semantic search via embeddings
    HYBRID = "hybrid"  # Both LSP and vector, merged with reranking
    CALL_GRAPH = "call_graph"  # Call hierarchy analysis (who calls, what calls)


class QueryRouter:
    """
    Routes queries to appropriate search backends based on query analysis.

    Uses pattern matching and heuristics to classify queries as:
    - LSP: Symbol names, exact identifiers (e.g., "UserService", "authenticate")
    - Vector: Natural language, exploratory (e.g., "find authentication logic")
    - Hybrid: Mixed queries (e.g., "login method with JWT validation")
    """

    # Patterns indicating LSP search
    LSP_INDICATORS = [
        r"^[A-Z][a-zA-Z0-9_]*$",  # PascalCase (class names)
        r"^[a-z][a-zA-Z0-9_]*$",  # camelCase (method/function names)
        r"^[a-z_][a-z0-9_]*$",  # snake_case (Python functions)
        r"^[A-Z_][A-Z0-9_]*$",  # UPPER_SNAKE_CASE (constants)
    ]

    # Keywords indicating vector search
    VECTOR_KEYWORDS = [
        "find",
        "search",
        "locate",
        "discover",
        "where",
        "how",
        "what",
        "which",
        "all",
        "any",
        "logic",
        "code",
        "implementation",
        "handling",
        "validation",
        "processing",
        "management",
    ]

    # Keywords indicating hybrid search
    HYBRID_KEYWORDS = [
        "method",
        "function",
        "class",
        "with",
        "using",
        "that",
        "for",
        "in",
    ]

    # Keywords indicating call graph analysis
    CALL_GRAPH_KEYWORDS = [
        "who calls",
        "what calls",
        "called by",
        "callers",
        "callees",
        "call graph",
        "call hierarchy",
        "incoming calls",
        "outgoing calls",
        "uses",
        "used by",
        "depends on",
        "dependencies",
        "impact",
    ]

    def __init__(self) -> None:
        """Initialize the query router."""
        self._lsp_patterns = [re.compile(pattern) for pattern in self.LSP_INDICATORS]

    def route(self, query: str, mode: Optional[str] = None) -> SearchMode:
        """
        Determine the appropriate search mode for a query.

        :param query: The search query
        :param mode: Optional explicit mode ("lsp", "vector", "hybrid", "auto")
        :return: SearchMode enum value
        """
        # Explicit mode override
        if mode and mode != "auto":
            try:
                return SearchMode(mode.lower())
            except ValueError:
                log.warning(f"Invalid mode '{mode}', falling back to auto-routing")

        # Auto-routing based on query analysis
        return self._classify_query(query)

    def _classify_query(self, query: str) -> SearchMode:
        """
        Classify query based on patterns and keywords.

        Classification logic:
        1. Check for call graph keywords (highest priority)
        2. Check if query matches LSP patterns (identifiers)
        3. Check for vector keywords (exploratory)
        4. Check for hybrid keywords (mixed)
        5. Default to vector for natural language
        """
        query_lower = query.lower().strip()
        words = query_lower.split()

        # Check for call graph keywords first (most specific)
        call_graph_count = sum(1 for kw in self.CALL_GRAPH_KEYWORDS if kw in query_lower)
        if call_graph_count >= 1:
            log.debug(f"Routing to CALL_GRAPH: {call_graph_count} call graph keywords in '{query}'")
            return SearchMode.CALL_GRAPH

        # Single-word queries matching identifier patterns → LSP
        if len(words) == 1:
            for pattern in self._lsp_patterns:
                if pattern.match(query):
                    log.debug(f"Routing to LSP: single identifier '{query}'")
                    return SearchMode.LSP

        # Check for symbol path patterns (e.g., "UserService/authenticate")
        if "/" in query and len(words) == 1:
            log.debug(f"Routing to LSP: symbol path '{query}'")
            return SearchMode.LSP

        # Count keyword matches
        vector_count = sum(1 for kw in self.VECTOR_KEYWORDS if kw in query_lower)
        hybrid_count = sum(1 for kw in self.HYBRID_KEYWORDS if kw in query_lower)

        # Strong vector indicators
        if vector_count >= 2:
            log.debug(f"Routing to VECTOR: {vector_count} vector keywords in '{query}'")
            return SearchMode.VECTOR

        # Hybrid if both vector and hybrid keywords present
        if vector_count >= 1 and hybrid_count >= 1:
            log.debug(f"Routing to HYBRID: mixed keywords in '{query}'")
            return SearchMode.HYBRID

        # Single vector keyword with multiple words → vector
        if vector_count >= 1 and len(words) >= 3:
            log.debug(f"Routing to VECTOR: natural language query '{query}'")
            return SearchMode.VECTOR

        # Hybrid if structural keywords without vector keywords
        if hybrid_count >= 1 and len(words) >= 2:
            log.debug(f"Routing to HYBRID: structural query with context '{query}'")
            return SearchMode.HYBRID

        # Short queries (1-2 words) without clear indicators → LSP
        if len(words) <= 2:
            log.debug(f"Routing to LSP: short query '{query}'")
            return SearchMode.LSP

        # Default: natural language → vector
        log.debug(f"Routing to VECTOR: default for '{query}'")
        return SearchMode.VECTOR

    def get_routing_explanation(self, query: str, mode: Optional[str] = None) -> dict[str, str]:
        """
        Get human-readable explanation of routing decision.

        :param query: The search query
        :param mode: Optional explicit mode
        :return: Dictionary with routing details
        """
        selected_mode = self.route(query, mode)

        explanation = {
            "query": query,
            "selected_mode": selected_mode.value,
            "reason": self._get_reason(query, selected_mode, mode),
        }

        return explanation

    def _get_reason(self, query: str, selected_mode: SearchMode, explicit_mode: Optional[str]) -> str:
        """Generate explanation for routing decision."""
        if explicit_mode and explicit_mode != "auto":
            return f"Explicit mode specified: {explicit_mode}"

        query_lower = query.lower()
        words = query_lower.split()

        if selected_mode == SearchMode.LSP:
            if len(words) == 1:
                return "Single identifier detected (exact symbol search)"
            if "/" in query:
                return "Symbol path pattern detected"
            if len(words) <= 2:
                return "Short query without semantic keywords (exact search)"
            return "Query matches LSP pattern"

        if selected_mode == SearchMode.VECTOR:
            vector_count = sum(1 for kw in self.VECTOR_KEYWORDS if kw in query_lower)
            if vector_count >= 2:
                return f"Multiple semantic keywords detected ({vector_count})"
            if vector_count >= 1 and len(words) >= 3:
                return "Natural language query with semantic intent"
            return "Default semantic search for exploratory query"

        # Hybrid mode
        vector_count = sum(1 for kw in self.VECTOR_KEYWORDS if kw in query_lower)
        hybrid_count = sum(1 for kw in self.HYBRID_KEYWORDS if kw in query_lower)
        return f"Mixed query (vector keywords: {vector_count}, structural keywords: {hybrid_count})"

    def route_with_confidence(self, query: str, mode: Optional[str] = None) -> tuple[SearchMode, float]:
        """
        Determine search mode with confidence score.

        :param query: Search query
        :param mode: Optional explicit mode override
        :return: (SearchMode, confidence) where confidence is 0.0-1.0
        """
        # Explicit mode = high confidence
        if mode and mode != "auto":
            try:
                return SearchMode(mode.lower()), 1.0
            except ValueError:
                pass

        # Auto-routing with confidence
        return self._classify_query_with_confidence(query)

    def _classify_query_with_confidence(self, query: str) -> tuple[SearchMode, float]:
        """
        Classify query and assign confidence score.

        Confidence scoring:
        - 0.9-1.0: Very high confidence (single identifier, clear pattern)
        - 0.7-0.9: High confidence (strong indicators)
        - 0.5-0.7: Medium confidence (mixed signals)
        - 0.3-0.5: Low confidence (ambiguous)
        - 0.0-0.3: Very low (fallback to vector)
        """
        query_lower = query.lower().strip()
        words = query_lower.split()

        # Count indicators
        identifier_matches = sum(1 for pattern in self._lsp_patterns if pattern.match(query))
        vector_count = sum(1 for kw in self.VECTOR_KEYWORDS if kw in query_lower)
        hybrid_count = sum(1 for kw in self.HYBRID_KEYWORDS if kw in query_lower)

        # Single-word identifier (very high confidence LSP)
        if len(words) == 1 and identifier_matches > 0:
            return SearchMode.LSP, 0.95

        # Symbol path pattern (high confidence LSP)
        if "/" in query and len(words) == 1:
            return SearchMode.LSP, 0.90

        # Strong vector indicators (high confidence)
        if vector_count >= 2:
            confidence = min(0.7 + vector_count * 0.05, 0.90)
            return SearchMode.VECTOR, confidence

        # Mixed query with identifier (medium-high confidence hybrid)
        if identifier_matches > 0 and (vector_count > 0 or hybrid_count > 0):
            confidence = min(0.6 + (vector_count + hybrid_count) * 0.1, 0.85)
            return SearchMode.HYBRID, confidence

        # Single vector keyword with multiple words (medium confidence vector)
        if vector_count >= 1 and len(words) >= 3:
            return SearchMode.VECTOR, 0.70

        # Structural keywords (medium confidence hybrid)
        if hybrid_count >= 1 and len(words) >= 2:
            return SearchMode.HYBRID, 0.60

        # Short query (low-medium confidence LSP)
        if len(words) <= 2:
            return SearchMode.LSP, 0.55

        # Default: natural language (low-medium confidence vector)
        return SearchMode.VECTOR, 0.50

    def should_use_fallback(self, confidence: float) -> bool:
        """
        Determine if confidence is low enough to try fallback mode.

        :param confidence: Confidence score from routing
        :return: True if should try fallback mode
        """
        return confidence < 0.60  # Threshold for low confidence

    def get_fallback_mode(self, primary_mode: SearchMode) -> SearchMode:
        """
        Get fallback mode for low-confidence routing.

        Fallback strategy:
        - LSP → HYBRID (expand to semantic)
        - VECTOR → HYBRID (add structural)
        - HYBRID → no fallback (already combines both)
        """
        if primary_mode == SearchMode.LSP or primary_mode == SearchMode.VECTOR:
            return SearchMode.HYBRID
        else:
            return primary_mode  # HYBRID already uses both
