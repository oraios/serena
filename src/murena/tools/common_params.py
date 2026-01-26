"""Common parameter descriptions shared across multiple tools."""

COMMON_PARAMS = {
    "max_answer_chars": "Max characters for output. If exceeded, no content returned. -1 uses default from config.",
    "relative_path": "Relative path to file or directory. Defaults to current working directory if not specified.",
    "include_info": "Include additional info (hover-like, docstring and signature) about the symbol. Ignored if include_body is True.",
    "include_body": "Include the symbol's source code.",
    "depth": "Depth for descendants retrieval (e.g., 1 for immediate children). Default 0.",
    "include_kinds": "List of LSP symbol kind integers to include. If not provided, all kinds included.",
    "exclude_kinds": "List of LSP symbol kind integers to exclude. Takes precedence over include_kinds.",
    "context_lines_before": "Number of lines of context to include before each match.",
    "context_lines_after": "Number of lines of context to include after each match.",
    "substring_matching": "Use substring matching for the last element of the pattern.",
    "name_path": "Name path of the symbol (definitions in find_symbol tool apply).",
    "name_path_pattern": "Name path matching pattern for symbol search.",
    "compact_format": "Use compact JSON encoding (30-40% token savings).",
    "use_cache": "Use session symbol cache for faster access. Default True.",
}


def get_param_description(param_name: str) -> str:
    """
    Get standardized description for a common parameter.

    :param param_name: The name of the parameter
    :return: The standardized description, or empty string if not found
    """
    return COMMON_PARAMS.get(param_name, "").strip()
