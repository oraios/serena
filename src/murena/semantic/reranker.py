"""
Result reranking using Reciprocal Rank Fusion (RRF).

This module merges results from multiple search sources (LSP + vector) and reranks
them using RRF to produce a unified ranked list.
"""

import logging
from typing import Any

log = logging.getLogger(__name__)


class ResultReranker:
    """
    Reranks and merges search results using Reciprocal Rank Fusion (RRF).

    RRF formula: score = sum(1 / (k + rank_i))
    where k is a constant (typically 60) and rank_i is the rank in source i.
    """

    DEFAULT_K = 60  # RRF constant (standard value from literature)

    def __init__(self, k: int = DEFAULT_K) -> None:
        """
        Initialize the reranker.

        :param k: RRF constant parameter (higher = less emphasis on rank differences)
        """
        self.k = k

    def merge_results(
        self,
        lsp_results: list[dict[str, Any]],
        vector_results: list[dict[str, Any]],
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Merge LSP and vector search results using RRF.

        :param lsp_results: Results from LSP search
        :param vector_results: Results from vector search
        :param max_results: Maximum number of results to return
        :return: Merged and reranked results
        """
        log.debug(f"Merging {len(lsp_results)} LSP + {len(vector_results)} vector results")

        # Build result map with RRF scores
        result_map: dict[str, dict[str, Any]] = {}

        # Process LSP results
        for rank, result in enumerate(lsp_results, start=1):
            key = self._get_result_key(result)
            if key not in result_map:
                result_map[key] = self._init_result_entry(result)
            result_map[key]["rrf_score"] += 1.0 / (self.k + rank)
            result_map[key]["sources"].append("lsp")

        # Process vector results
        for rank, result in enumerate(vector_results, start=1):
            key = self._get_result_key(result)
            if key not in result_map:
                result_map[key] = self._init_result_entry(result)
            result_map[key]["rrf_score"] += 1.0 / (self.k + rank)
            result_map[key]["sources"].append("vector")

        # Sort by RRF score
        merged_results = sorted(
            result_map.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )

        # Limit to max_results
        merged_results = merged_results[:max_results]

        # Clean up internal fields
        for result in merged_results:
            result["sources"] = list(set(result["sources"]))  # Deduplicate sources

        log.debug(f"Merged to {len(merged_results)} results (max={max_results})")

        return merged_results

    def _get_result_key(self, result: dict[str, Any]) -> str:
        """
        Generate unique key for deduplication.

        Key format: "file_path::symbol_path" or "file_path::file_metadata"
        """
        # Compact format
        if "fp" in result:
            file_path = result["fp"]
            name_path = result.get("np", "file_metadata")
            return f"{file_path}::{name_path}"

        # Standard format
        if "relative_path" in result:
            file_path = result["relative_path"]
            name_path = result.get("name_path", "file_metadata")
            return f"{file_path}::{name_path}"

        # Fallback
        return str(result)

    def _init_result_entry(self, result: dict[str, Any]) -> dict[str, Any]:
        """
        Initialize result entry with RRF metadata.

        Preserves original result data and adds:
        - rrf_score: Cumulative RRF score
        - sources: List of sources (lsp, vector)
        """
        entry = result.copy()
        entry["rrf_score"] = 0.0
        entry["sources"] = []
        return entry

    def rerank_with_weights(
        self,
        lsp_results: list[dict[str, Any]],
        vector_results: list[dict[str, Any]],
        lsp_weight: float = 0.5,
        vector_weight: float = 0.5,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Merge results with weighted RRF scores.

        :param lsp_results: Results from LSP search
        :param vector_results: Results from vector search
        :param lsp_weight: Weight for LSP results (0.0 to 1.0)
        :param vector_weight: Weight for vector results (0.0 to 1.0)
        :param max_results: Maximum number of results to return
        :return: Merged and reranked results
        """
        if lsp_weight + vector_weight <= 0:
            log.warning("Invalid weights, using default (0.5, 0.5)")
            lsp_weight = 0.5
            vector_weight = 0.5

        # Normalize weights
        total = lsp_weight + vector_weight
        lsp_weight /= total
        vector_weight /= total

        log.debug(f"Weighted merge: LSP={lsp_weight:.2f}, Vector={vector_weight:.2f}")

        # Build result map with weighted RRF scores
        result_map: dict[str, dict[str, Any]] = {}

        # Process LSP results with weight
        for rank, result in enumerate(lsp_results, start=1):
            key = self._get_result_key(result)
            if key not in result_map:
                result_map[key] = self._init_result_entry(result)
            result_map[key]["rrf_score"] += lsp_weight * (1.0 / (self.k + rank))
            result_map[key]["sources"].append("lsp")

        # Process vector results with weight
        for rank, result in enumerate(vector_results, start=1):
            key = self._get_result_key(result)
            if key not in result_map:
                result_map[key] = self._init_result_entry(result)
            result_map[key]["rrf_score"] += vector_weight * (1.0 / (self.k + rank))
            result_map[key]["sources"].append("vector")

        # Sort by RRF score
        merged_results = sorted(
            result_map.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )

        # Limit to max_results
        merged_results = merged_results[:max_results]

        # Clean up internal fields
        for result in merged_results:
            result["sources"] = list(set(result["sources"]))

        return merged_results

    def explain_merge(
        self,
        lsp_results: list[dict[str, Any]],
        vector_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Generate explanation of merge process.

        :param lsp_results: Results from LSP search
        :param vector_results: Results from vector search
        :return: Dictionary with merge statistics
        """
        merged = self.merge_results(lsp_results, vector_results, max_results=100)

        # Count source combinations
        lsp_only = sum(1 for r in merged if r["sources"] == ["lsp"])
        vector_only = sum(1 for r in merged if r["sources"] == ["vector"])
        both = sum(1 for r in merged if len(r["sources"]) > 1)

        return {
            "lsp_input": len(lsp_results),
            "vector_input": len(vector_results),
            "merged_output": len(merged),
            "lsp_only": lsp_only,
            "vector_only": vector_only,
            "both_sources": both,
            "top_scores": [r["rrf_score"] for r in merged[:5]],
        }
